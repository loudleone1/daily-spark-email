import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import daily_spark


class FixedDateTime:
    @classmethod
    def now(cls, tz=None):
        from datetime import datetime

        return datetime(2026, 3, 12, 8, 15, tzinfo=tz)


class DailySparkTests(unittest.TestCase):
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

    def test_send_email_calls_resend_with_subject_and_html(self):
        with patch.dict(
            os.environ,
            {
                "RESEND_API_KEY": "resend-key",
                "FROM_EMAIL": "spark@example.com",
                "TO_EMAIL": "me@example.com",
                "TIMEZONE": "America/New_York",
            },
            clear=False,
        ):
            with patch.object(daily_spark, "datetime", FixedDateTime):
                with patch.object(daily_spark, "post_json", return_value={"id": "email_123"}) as mock_post:
                    result = daily_spark.send_email("# Wild Spark\nHello")

        self.assertEqual(result["id"], "email_123")
        args = mock_post.call_args[0]
        self.assertEqual(args[0], daily_spark.RESEND_API_URL)
        self.assertEqual(args[1]["subject"], "Wild-Ideas Daily Spark | Mar 12, 2026")
        self.assertEqual(args[1]["from"], "spark@example.com")
        self.assertEqual(args[1]["to"], ["me@example.com"])
        self.assertIn("<h1>Wild Spark</h1>", args[1]["html"])
        self.assertEqual(args[2]["Authorization"], "Bearer resend-key")
        self.assertEqual(args[2]["Idempotency-Key"], "wild-ideas-daily-spark-2026-03-12")

    def test_main_skips_when_not_target_hour(self):
        with patch.dict(os.environ, {"TIMEZONE": "America/New_York", "TARGET_HOUR_LOCAL": "9"}, clear=False):
            with patch.object(daily_spark, "datetime", FixedDateTime):
                output = io.StringIO()
                with redirect_stdout(output):
                    exit_code = daily_spark.main()

        self.assertEqual(exit_code, 0)
        self.assertIn("Skipping send", output.getvalue())

    def test_main_force_send_bypasses_hour_check(self):
        with patch.dict(
            os.environ,
            {
                "TIMEZONE": "America/New_York",
                "TARGET_HOUR_LOCAL": "9",
                "FORCE_SEND": "true",
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


if __name__ == "__main__":
    unittest.main()
