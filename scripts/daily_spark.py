#!/usr/bin/env python3

import html
import json
import os
from pathlib import Path
import socket
import smtplib
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo


OPENAI_API_URL = "https://api.openai.com/v1/responses"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def post_json(url: str, payload: dict, headers: dict) -> dict:
    timeout_seconds = int(os.environ.get("HTTP_TIMEOUT_SECONDS", "120"))
    max_attempts = int(os.environ.get("HTTP_MAX_ATTEMPTS", "3"))

    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            if attempt == max_attempts:
                raise RuntimeError(
                    f"Request to {url} failed after {max_attempts} attempts: {exc}"
                ) from exc
            time.sleep(attempt * 2)

    raise RuntimeError(f"Request to {url} failed without a response.")


def extract_response_text(response: dict) -> str:
    text = response.get("output_text", "").strip()
    if text:
        return text

    fragments: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                value = content.get("text", "")
                if value:
                    fragments.append(value)

    return "\n".join(fragment for fragment in fragments if fragment).strip()


def should_send_now() -> tuple[bool, datetime]:
    timezone_name = os.environ.get("TIMEZONE", "America/New_York")
    target_hour = int(os.environ.get("TARGET_HOUR_LOCAL", "8"))
    now = datetime.now(ZoneInfo(timezone_name))
    return now.hour >= target_hour, now


def marker_path_for_now(now: datetime) -> Path:
    base_dir = Path(os.environ.get("SENT_MARKER_DIR", ".daily-spark-state"))
    return base_dir / f"sent-{now.strftime('%Y-%m-%d')}.marker"


def was_already_sent_today(now: datetime) -> bool:
    return marker_path_for_now(now).exists()


def mark_sent_today(now: datetime) -> None:
    marker_path = marker_path_for_now(now)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(now.isoformat(), encoding="utf-8")


def build_prompt(today_local: str) -> str:
    extra_context = os.environ.get("SPARK_EXTRA_CONTEXT", "").strip()
    extra_block = f"\nAdditional context: {extra_context}\n" if extra_context else "\n"
    return f"""Write a daily email called "Wild-Ideas Daily Spark".

Date: {today_local}
Audience: one person, written like a provocative personal spark note for the morning.

Core direction:
- Doing what makes you feel young
- Doing what would cause me to jump up with excitement to start the day
- Meeting new people
- Going to new places
- Starting new projects
- Going on adventures
- Life is not about time, it's a collection of experiences. Increase the number of your experiences.
- Finding passions within
- Strategy and outsmarting common beliefs
- Adventure
- Inventing and creating
- Animals and farm
- What did you love when nothing else mattered?
{extra_block}
Requirements:
- Keep it concrete, emotionally alive, and surprising.
- Include exactly these sections with markdown headings:
  1. Wild Spark
  2. Ideas
  3. Actions Today
  4. Bigger Bets
  5. Question to Chase
- In Ideas, give 5 distinct ideas spanning social, place-based, project-based, adventurous, and unconventional directions.
- In Actions Today, give 3 specific actions that can be done today with low friction.
- In Bigger Bets, include 3 bolder out-of-the-box ideas, with at least one that breaks a common assumption.
- The Question to Chase section must be a single strong question.
- Keep total length between 350 and 600 words.
- Avoid filler, corporate tone, and generic self-help language.
"""


def generate_email() -> str:
    api_key = require_env("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-5")
    _, now = should_send_now()
    prompt = build_prompt(now.strftime("%A, %B %-d, %Y"))

    payload = {
        "model": model,
        "input": prompt,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = post_json(OPENAI_API_URL, payload, headers)
    text = extract_response_text(response)
    if not text:
        raise RuntimeError("OpenAI response did not include output_text.")
    return text


def markdownish_to_html(content: str) -> str:
    lines = content.splitlines()
    html_parts: list[str] = [
        "<html><body style=\"font-family: Georgia, serif; line-height: 1.55; color: #1f2937;\">"
    ]

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        escaped = html.escape(line)
        if line.startswith("# "):
            html_parts.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            html_parts.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("- "):
            html_parts.append(f"<p style=\"margin: 0 0 10px 18px;\">• {html.escape(line[2:].strip())}</p>")
        elif len(line) > 3 and line[0].isdigit() and line[1:3] == ". ":
            html_parts.append(f"<p style=\"margin: 0 0 10px 18px;\">{escaped}</p>")
        else:
            html_parts.append(f"<p>{escaped}</p>")

    html_parts.append("</body></html>")
    return "".join(html_parts)


def send_email(content: str) -> dict:
    smtp_host = require_env("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = require_env("SMTP_USERNAME")
    smtp_password = require_env("SMTP_PASSWORD")
    from_email = require_env("FROM_EMAIL")
    to_email = require_env("TO_EMAIL")
    timezone_name = os.environ.get("TIMEZONE", "America/New_York")
    now = datetime.now(ZoneInfo(timezone_name))
    subject = f"Wild-Ideas Daily Spark | {now.strftime('%b %-d, %Y')}"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(content)
    message.add_alternative(markdownish_to_html(content), subtype="html")

    with smtplib.SMTP(smtp_host, smtp_port, timeout=int(os.environ.get("SMTP_TIMEOUT_SECONDS", "60"))) as server:
        server.ehlo()
        if os.environ.get("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes", "on"}:
            server.starttls()
            server.ehlo()
        server.login(smtp_username, smtp_password)
        server.send_message(message)

    return {"id": f"smtp-{now.strftime('%Y%m%d')}"}


def main() -> int:
    force_send = os.environ.get("FORCE_SEND", "").lower() in {"1", "true", "yes", "on"}
    send_now, now = should_send_now()
    if was_already_sent_today(now) and not force_send:
        print(
            f"Skipping send. Daily spark already sent for {now.strftime('%Y-%m-%d')} in "
            f"{os.environ.get('TIMEZONE', 'America/New_York')}."
        )
        return 0

    if not send_now and not force_send:
        print(
            f"Skipping send. Local time in {os.environ.get('TIMEZONE', 'America/New_York')} is "
            f"{now.strftime('%Y-%m-%d %H:%M')}."
        )
        return 0

    content = generate_email()
    result = send_email(content)
    mark_sent_today(now)
    print(f"Sent daily spark email: {result.get('id', 'unknown id')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
