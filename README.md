# Daily Spark Email

This repo sends a daily "Wild-Ideas Daily Spark" email from GitHub Actions, so it keeps running even when you are not logged in locally.

## What it does

- Runs every hour in GitHub Actions.
- Checks whether it is your configured local send hour.
- Generates a fresh daily spark email with OpenAI.
- Sends the email through Resend.
- Uses a daily idempotency key to avoid duplicate sends for the same day.

## GitHub setup

Add these repository secrets:

- `OPENAI_API_KEY`
- `RESEND_API_KEY`
- `FROM_EMAIL`
- `TO_EMAIL`

`FROM_EMAIL` must be a sender address allowed by your Resend account and verified domain setup.

Add these repository variables if you want to override defaults:

- `TIMEZONE` default: `America/New_York`
- `TARGET_HOUR_LOCAL` default: `8`
- `OPENAI_MODEL` default: `gpt-5`
- `SPARK_EXTRA_CONTEXT` optional extra steering for the prompt

## Enable it

1. Push this repo to GitHub.
2. Add the secrets and optional variables in the repository settings.
3. Enable GitHub Actions for the repo.
4. Run the `Daily Spark Email` workflow once with `workflow_dispatch` to verify delivery.

## Notes

- GitHub scheduled workflows can run a few minutes late. This setup handles that by checking the local hour instead of relying on a single UTC cron time.
- Resend requires a verified sending domain or an allowed test sender, depending on your plan and setup.
