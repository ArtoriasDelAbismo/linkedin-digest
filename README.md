# Weekly Tech Digest

Every week this service collects tech and science news from RSS feeds (software engineering, AI/ML,
science, tech industry, SpaceX/NASA), has Claude write one LinkedIn digest post, and emails it to you with a link
to review it. Nothing is posted until you click **Post to LinkedIn** on that page.

## Files

- `feeds.py`: the RSS sources. Add or remove feeds here.
- `writer.py`: the Claude prompt that picks stories and writes the post.
- `linkedin.py`: LinkedIn login (OAuth) and posting.
- `app.py`: the web pages (status, approval) and the weekly schedule.
- `preview.py`: prints a draft without saving, emailing or posting anything.

## Run locally

```bash
cp .env.example .env        # fill in the secrets
.venv/bin/python preview.py # see what a draft looks like
.venv/bin/uvicorn app:app --port 8000
```

Open `http://localhost:8000/?key=<ADMIN_KEY>`, click **Connect LinkedIn**, then **Generate a draft now**.

## Deploy on Railway

1. Create a service from this folder (`railway up`) and attach a volume mounted at `/data`.
2. Set the variables from `.env.example`, with `DATA_DIR=/data` and `PUBLIC_URL` set to the service domain.
3. Add `<PUBLIC_URL>/callback` under **Authorized redirect URLs** in the LinkedIn app's Auth tab.
4. Open `<PUBLIC_URL>/?key=<ADMIN_KEY>` and connect LinkedIn.

LinkedIn logins last 60 days. The service emails you a reconnect link when fewer than 10 days are left.
