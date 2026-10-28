# Weekly Tech Digest

Every week this service collects tech and science news from RSS feeds (software engineering, AI/ML,
science, tech industry, SpaceX/NASA, cybersecurity), has Claude write LinkedIn posts, and emails each one to you with a link
to review it. Nothing is posted until you click **Post to LinkedIn** on that page.

There are two kinds of posts:

- **Digest** (`DIGEST_DAY`, Fridays): the 3-5 most significant stories of the week.
- **Story posts** (`SPOTLIGHT_DAY`, Mondays and Wednesdays): an email offers the 4 most relevant stories
  right now, from different topics. Pick one and Claude writes a post that goes deeper on it, published with
  the article's cover image. You can change or remove the image on the review page.

Stories linked in a post from the last 14 days are never offered again.

## Files

- `feeds.py`: the RSS sources. Add or remove feeds here.
- `writer.py`: the Claude prompts that pick stories and write the posts.
- `linkedin.py`: LinkedIn login (OAuth), image upload and posting.
- `app.py`: the web pages (status, approval) and the weekly schedule.
- `preview.py`: prints a draft without saving, emailing or posting anything.

## Run locally

```bash
cp .env.example .env        # fill in the secrets
.venv/bin/python preview.py # see what a draft looks like (add "spotlight" for a story post)
.venv/bin/uvicorn app:app --port 8000
```

Open `http://localhost:8000/?key=<ADMIN_KEY>`, click **Connect LinkedIn**, then one of the **Generate** buttons.

On Vercel the schedule comes from the `crons` in `vercel.json` (times in UTC), not from the `*_DAY` variables.

## Deploy on Railway

1. Create a service from this folder (`railway up`) and attach a volume mounted at `/data`.
2. Set the variables from `.env.example`, with `DATA_DIR=/data` and `PUBLIC_URL` set to the service domain.
3. Add `<PUBLIC_URL>/callback` under **Authorized redirect URLs** in the LinkedIn app's Auth tab.
4. Open `<PUBLIC_URL>/?key=<ADMIN_KEY>` and connect LinkedIn.

LinkedIn logins last 60 days. The service emails you a reconnect link when fewer than 10 days are left.
