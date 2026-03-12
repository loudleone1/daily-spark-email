# Daily Spark Email

This repo sends a daily "Wild-Ideas Daily Spark" email from GitHub Actions, so it keeps running even when you are not logged in locally.

## What it does

- Runs every hour in GitHub Actions.
- Checks whether it is your configured local send hour.
- Generates a fresh daily spark email with OpenAI.
- Sends the email through your SMTP provider.

## GitHub setup

Add these repository secrets:

- `OPENAI_API_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `FROM_EMAIL`
- `TO_EMAIL`

Example SMTP setup for your domain mailbox:

- `SMTP_HOST` your provider's SMTP server
- `SMTP_PORT` usually `587`
- `SMTP_USERNAME` usually `lou@jessicamarks.com`
- `SMTP_PASSWORD` your mailbox password or app password
- `FROM_EMAIL` `lou@jessicamarks.com`
- `TO_EMAIL` wherever you want to receive the email

Add these repository variables if you want to override defaults:

- `TIMEZONE` default: `America/New_York`
- `TARGET_HOUR_LOCAL` default: `8`
- `OPENAI_MODEL` default: `gpt-5`
- `SPARK_EXTRA_CONTEXT` optional extra steering for the prompt
- `SMTP_STARTTLS` default: `true`
- `SMTP_TIMEOUT_SECONDS` default: `60`
- `HTTP_TIMEOUT_SECONDS` default: `120`
- `HTTP_MAX_ATTEMPTS` default: `3`

## Enable it

1. Push this repo to GitHub.
2. Add the secrets and optional variables in the repository settings.
3. Enable GitHub Actions for the repo.
4. Run the `Daily Spark Email` workflow once with `workflow_dispatch` to verify delivery.

## Notes

- GitHub scheduled workflows can run a few minutes late. This setup handles that by checking the local hour instead of relying on a single UTC cron time.
- Your SMTP provider must allow authenticated sending from `FROM_EMAIL`.
