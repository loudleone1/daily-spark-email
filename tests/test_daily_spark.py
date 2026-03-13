import io
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import daily_spark


class FixedDateTime:
    @classmethod
    def now(cls, tz=None):
        from datetime import datetime

        return datetime(2026, 3, 12, 8, 15, tzinfo=tz)


class LateDateTime:
    @classmethod
    def now(cls, tz=None):
        from datetime import datetime

        return datetime(2026, 3, 13, 11, 54, tzinfo=tz)


class EarlyDateTime:
    @classmethod
    def now(cls, tz=None):
        from datetime import datetime

        return datetime(2026, 3, 13, 7, 15, tzinfo=tz)


class DailySparkTests(unittest.TestCase):
    def test_post_json_retries_after_timeout_and_succeeds(self):
        class FakeResponse:
            def __init__(self, body: str):
                self.body = body

            def read(self):
                return self.body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        side_effects = [TimeoutError("slow"), FakeResponse('{"ok": true}')]

        with patch.dict(os.environ, {"HTTP_MAX_ATTEMPTS": "3", "HTTP_TIMEOUT_SECONDS": "1"}, clear=False):
            with patch("scripts.daily_spark.urllib.request.urlopen", side_effect=side_effects) as mock_urlopen:
                with patch("scripts.daily_spark.time.sleep") as mock_sleep:
                    response = daily_spark.post_json("https://example.com", {"a": 1}, {"X-Test": "1"})

        self.assertEqual(response, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(2)

    def test_post_json_fails_after_max_attempts(self):
        with patch.dict(os.environ, {"HTTP_MAX_ATTEMPTS": "2", "HTTP_TIMEOUT_SECONDS": "1"}, clear=False):
            with patch("scripts.daily_spark.urllib.request.urlopen", side_effect=socket.timeout("timed out")):
                with patch("scripts.daily_spark.time.sleep"):
                    with self.assertRaises(RuntimeError) as error:
                        daily_spark.post_json("https://example.com", {"a": 1}, {"X-Test": "1"})

        self.assertIn("failed after 2 attempts", str(error.exception))

    def test_build_prompt_includes_sections_and_context(self):
        with patch.dict(os.environ, {"SPARK_EXTRA_CONTEXT": "Lean toward unexpected field trips."}, clear=False):
            prompt = daily_spark.build_prompt("Thursday, March 12, 2026")

        self.assertIn("Wild Spark", prompt)
        self.assertIn("Ideas", prompt)
        self.assertIn("Actions Today", prompt)
        self.assertIn("Bigger Bets", prompt)
        self.assertIn("Question to Chase", prompt)
        self.assertIn("Lean toward unexpected field trips.", prompt)

    def test_markdownish_to_html_converts_headings_and_bullets(self):
        content = "# Wild Spark\n\n## Ideas\n- Meet a stranger at the horse barn\n1. Book a train to somewhere random"
        html = daily_spark.markdownish_to_html(content)

        self.assertIn("<h1>Wild Spark</h1>", html)
        self.assertIn("<h2>Ideas</h2>", html)
        self.assertIn("• Meet a stranger at the horse barn", html)
        self.assertIn("1. Book a train to somewhere random", html)

    def test_generate_email_calls_openai_with_expected_payload(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-5", "TIMEZONE": "America/New_York"},
            clear=False,
        ):
            with patch.object(daily_spark, "datetime", FixedDateTime):
                with patch.object(daily_spark, "post_json", return_value={"output_text": "## Wild Spark\nHello"}) as mock_post:
                    text = daily_spark.generate_email()

        self.assertEqual(text, "## Wild Spark\nHello")
        args = mock_post.call_args[0]
        self.assertEqual(args[0], daily_spark.OPENAI_API_URL)
        self.assertEqual(args[1]["model"], "gpt-5")
        self.assertIn("Write a daily email called", args[1]["input"])
        self.assertEqual(args[2]["Authorization"], "Bearer test-key")

    def test_extract_response_text_falls_back_to_output_content(self):
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "## Wild Spark"},
                        {"type": "output_text", "text": "Try something improbable today."},
                    ],
                }
            ]
        }

        text = daily_spark.extract_response_text(response)

        self.assertEqual(text, "## Wild Spark\nTry something improbable today.")

    def test_send_email_uses_smtp_with_subject_and_html(self):
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "lou@jessicamarks.com",
                "SMTP_PASSWORD": "smtp-password",
                "FROM_EMAIL": "spark@example.com",
                "TO_EMAIL": "me@example.com",
                "TIMEZONE": "America/New_York",
            },
            clear=False,
        ):
            with patch.object(daily_spark, "datetime", FixedDateTime):
                with patch("scripts.daily_spark.smtplib.SMTP") as mock_smtp:
                    result = daily_spark.send_email("# Wild Spark\nHello")

        self.assertEqual(result["id"], "smtp-20260312")
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=60)
        server = mock_smtp.return_value.__enter__.return_value
        self.assertEqual(server.ehlo.call_count, 2)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("lou@jessicamarks.com", "smtp-password")
        server.send_message.assert_called_once()

        message = server.send_message.call_args[0][0]
        self.assertEqual(message["Subject"], "Wild-Ideas Daily Spark | Mar 12, 2026")
        self.assertEqual(message["From"], "spark@example.com")
        self.assertEqual(message["To"], "me@example.com")
        payloads = message.get_payload()
        self.assertEqual(len(payloads), 2)
        self.assertIn("Wild Spark", payloads[0].get_payload())
        self.assertIn("<h1>Wild Spark</h1>", payloads[1].get_payload())

    def test_main_skips_when_not_target_hour(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"TIMEZONE": "America/New_York", "TARGET_HOUR_LOCAL": "8", "SENT_MARKER_DIR": temp_dir},
                clear=False,
            ):
                with patch.object(daily_spark, "datetime", EarlyDateTime):
                    output = io.StringIO()
                    with redirect_stdout(output):
                        exit_code = daily_spark.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("Skipping send", output.getvalue())

    def test_main_sends_when_run_late_after_target_hour(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"TIMEZONE": "America/New_York", "TARGET_HOUR_LOCAL": "8", "SENT_MARKER_DIR": temp_dir},
                clear=False,
            ):
                with patch.object(daily_spark, "datetime", LateDateTime):
                    with patch.object(daily_spark, "generate_email", return_value="# Wild Spark\nHello"):
                        with patch.object(daily_spark, "send_email", return_value={"id": "email_late"}):
                            output = io.StringIO()
                            with redirect_stdout(output):
                                exit_code = daily_spark.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("Sent daily spark email: email_late", output.getvalue())

    def test_main_skips_if_already_sent_today(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"TIMEZONE": "America/New_York", "TARGET_HOUR_LOCAL": "8", "SENT_MARKER_DIR": temp_dir},
                clear=False,
            ):
                with patch.object(daily_spark, "datetime", LateDateTime):
                    daily_spark.mark_sent_today(daily_spark.datetime.now())
                    output = io.StringIO()
                    with redirect_stdout(output):
                        exit_code = daily_spark.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("already sent", output.getvalue())

    def test_main_force_send_bypasses_hour_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "TIMEZONE": "America/New_York",
                    "TARGET_HOUR_LOCAL": "9",
                    "FORCE_SEND": "true",
                    "SENT_MARKER_DIR": temp_dir,
                },
                clear=False,
            ):
                with patch.object(daily_spark, "datetime", FixedDateTime):
                    with patch.object(daily_spark, "generate_email", return_value="# Wild Spark\nHello"):
                        with patch.object(daily_spark, "send_email", return_value={"id": "email_456"}):
                            output = io.StringIO()
                            with redirect_stdout(output):
                                exit_code = daily_spark.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("Sent daily spark email: email_456", output.getvalue())

    def test_main_force_send_bypasses_already_sent_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "TIMEZONE": "America/New_York",
                    "TARGET_HOUR_LOCAL": "8",
                    "FORCE_SEND": "true",
                    "SENT_MARKER_DIR": temp_dir,
                },
                clear=False,
            ):
                with patch.object(daily_spark, "datetime", LateDateTime):
                    daily_spark.mark_sent_today(daily_spark.datetime.now())
                    with patch.object(daily_spark, "generate_email", return_value="# Wild Spark\nHello"):
                        with patch.object(daily_spark, "send_email", return_value={"id": "email_789"}):
                            output = io.StringIO()
                            with redirect_stdout(output):
                                exit_code = daily_spark.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("Sent daily spark email: email_789", output.getvalue())


if __name__ == "__main__":
    unittest.main()
