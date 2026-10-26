"""Web service: LinkedIn login, draft approval page, and the weekly schedule (digest and story of the week)."""

import hashlib
import hmac
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from html import escape

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

load_dotenv()

import db  # noqa: E402  (DATA_DIR must be loaded from .env first)
import linkedin  # noqa: E402
from feeds import fetch_articles, find_image  # noqa: E402
from notify import notify  # noqa: E402
from writer import write_digest, write_spotlight  # noqa: E402

REAUTH_WARNING_DAYS = 10
# How far back to look for posts whose stories the story of the week must not repeat
RECENT_POSTS_DAYS = 14
_URL = re.compile(r"https?://\S+")
OAUTH_STATE_TTL = 600
# On Vercel nothing runs between requests, so Vercel Cron calls /cron instead of the in-process scheduler
ON_VERCEL = bool(os.getenv("VERCEL"))


def public_url(path: str) -> str:
    return os.environ["PUBLIC_URL"].rstrip("/") + path


def check_key(key: str) -> None:
    expected = os.environ.get("ADMIN_KEY", "")
    if not expected or not secrets.compare_digest(key, expected):
        raise HTTPException(403, "Wrong key")


def _sign(value: str) -> str:
    return hmac.new(os.environ["ADMIN_KEY"].encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def make_oauth_state() -> str:
    """A signed, timestamped state value, so the login check survives across serverless instances."""
    issued = str(int(time.time()))
    return f"{issued}.{_sign(issued)}"


def valid_oauth_state(state: str) -> bool:
    issued, _, sig = state.partition(".")
    return (issued.isdigit() and secrets.compare_digest(sig, _sign(issued))
            and time.time() - int(issued) < OAUTH_STATE_TTL)


def check_login() -> None:
    """Email a login link when LinkedIn is not connected or the login is about to expire."""
    auth = db.get_auth()
    login = public_url(f"/login?key={os.environ['ADMIN_KEY']}")
    if not auth:
        notify("Connect LinkedIn to your Weekly Tech Digest", f"Connect your LinkedIn account so drafts can be posted:\n{login}")
    elif auth["expires_at"] - time.time() < REAUTH_WARNING_DAYS * 86400:
        days = max(0, int((auth["expires_at"] - time.time()) / 86400))
        notify(f"LinkedIn login expires in {days} days", f"Reconnect LinkedIn to keep posting:\n{login}")


def weekly_job() -> str | None:
    """Draft this week's digest and email the approval link. Returns the draft id."""
    check_login()
    articles = fetch_articles()
    if not articles:
        notify("Weekly Tech Digest: no articles found", "No articles were found this week. Check the feeds.")
        return None
    text = write_digest(articles)
    draft_id = db.new_draft(text)
    notify("Your weekly LinkedIn digest is ready to review",
           f"Review, edit and post it here:\n{public_url('/draft/' + draft_id)}\n\n"
           f"Nothing is posted until you click Post.\n\n---\n\n{text}")
    return draft_id


def spotlight_candidates() -> tuple[list, list[str]]:
    """This week's articles minus those linked in recent posts, and the text of those posts."""
    recent = [d["text"] for d in db.recent_drafts(RECENT_POSTS_DAYS)]
    used = {u.rstrip(".,;:!?)") for text in recent for u in _URL.findall(text)}
    return [a for a in fetch_articles() if a.link not in used], recent


def spotlight_job() -> str | None:
    """Draft a post about the story of the week, with its cover image, and email the approval link."""
    check_login()
    articles, recent = spotlight_candidates()
    if not articles:
        notify("Story of the week: no articles found", "No new articles were found this week. Check the feeds.")
        return None
    article, text = write_spotlight(articles, recent)
    image_url = find_image(article)
    draft_id = db.new_draft(text, kind="spotlight", image_url=image_url or None, image_alt=article.title)
    image_note = (f"Image: {image_url}" if image_url
                  else "No cover image was found for this article. Add an image URL on the review page.")
    notify("Your story of the week is ready to review",
           f"Review, edit and post it here:\n{public_url('/draft/' + draft_id)}\n\n"
           f"Nothing is posted until you click Post.\n\nStory: {article.title} ({article.source})\n"
           f"{image_note}\n\n---\n\n{text}")
    return draft_id


JOBS = {"digest": weekly_job, "spotlight": spotlight_job}


def schedule(prefix: str, default_day: str) -> dict:
    """The cron day, hour and timezone for a job, from DIGEST_* or SPOTLIGHT_* variables."""
    return {
        "day_of_week": os.getenv(f"{prefix}_DAY", default_day),
        "hour": int(os.getenv(f"{prefix}_HOUR", os.getenv("DIGEST_HOUR", "9"))),
        "timezone": os.getenv(f"{prefix}_TZ", os.getenv("DIGEST_TZ", "UTC")),
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if ON_VERCEL:
        yield
        return
    scheduler = BackgroundScheduler()
    scheduler.add_job(weekly_job, CronTrigger(**schedule("DIGEST", "mon")))
    scheduler.add_job(spotlight_job, CronTrigger(**schedule("SPOTLIGHT", "tue")))
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Weekly Tech Digest</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:720px;margin:0 auto;padding:16px;background:#f7f7f5;color:#1d1d1b}}
textarea{{width:100%;box-sizing:border-box;min-height:60vh;font:15px/1.5 system-ui,sans-serif;padding:12px;border:1px solid #ccc;border-radius:8px}}
button{{font-size:16px;padding:10px 18px;border-radius:8px;border:0;cursor:pointer;margin:8px 8px 0 0}}
input[type=url]{{width:100%;box-sizing:border-box;font:15px system-ui,sans-serif;padding:8px;border:1px solid #ccc;border-radius:8px}}
.cover{{max-width:100%;border-radius:8px;display:block;margin:8px 0}}
.post{{background:#0a66c2;color:#fff}} .skip{{background:#ddd}} .muted{{color:#666;font-size:14px}}
@media (prefers-color-scheme:dark){{body{{background:#1b1b1a;color:#eee}}textarea,input[type=url]{{background:#262624;color:#eee;border-color:#444}}.skip{{background:#444;color:#eee}}.muted{{color:#aaa}}}}
</style></head><body>{body}</body></html>"""


def page(body: str) -> HTMLResponse:
    return HTMLResponse(PAGE.format(body=body))


@app.get("/")
def status(key: str = ""):
    check_key(key)
    auth = db.get_auth()
    if auth:
        days = int((auth["expires_at"] - time.time()) / 86400)
        who = f"Connected as <b>{escape(auth['name'])}</b>. Login expires in {days} days."
    else:
        who = "LinkedIn is not connected yet."
    return page(f"""<h1>Weekly Tech Digest</h1><p>{who}</p>
<p><a href="/login?key={escape(key)}">Connect / reconnect LinkedIn</a></p>
<form method="post" action="/run?key={escape(key)}">
<button class="post" name="kind" value="digest">Generate a digest now</button>
<button class="post" name="kind" value="spotlight">Generate a story of the week now</button></form>
<p class="muted">The digest is drafted every {_when("DIGEST", "mon")} and the story of the week
every {_when("SPOTLIGHT", "tue")}.</p>""")


def _when(prefix: str, default_day: str) -> str:
    s = schedule(prefix, default_day)
    return escape(f"{s['day_of_week']} at {s['hour']}:00 {s['timezone']}")


@app.post("/run")
def run_now(key: str = "", kind: str = Form("digest")):
    check_key(key)
    if kind not in JOBS:
        raise HTTPException(400, "Unknown kind")
    draft_id = JOBS[kind]()
    if not draft_id:
        return page("<p>No articles found.</p>")
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


@app.get("/cron")
@app.get("/cron/{kind}")
def cron(kind: str = "digest", authorization: str = Header("")):
    """Called weekly by Vercel Cron, which sends the CRON_SECRET as a bearer token."""
    expected = os.environ.get("CRON_SECRET", "")
    if not expected or not secrets.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(401)
    if kind not in JOBS:
        raise HTTPException(404)
    return {"draft_id": JOBS[kind]()}


@app.get("/login")
def login(key: str = ""):
    check_key(key)
    return RedirectResponse(linkedin.authorize_url(make_oauth_state()))


@app.get("/callback")
def callback(state: str = "", code: str = "", error: str = "", error_description: str = ""):
    if error:
        return page(f"<p>LinkedIn login failed: {escape(error_description or error)}</p>")
    if not valid_oauth_state(state):
        raise HTTPException(400, "Login link expired or invalid, start again from the status page")
    auth = linkedin.exchange_code(code)
    db.save_auth(**auth)
    return page(f"<p>Connected as <b>{escape(auth['name'])}</b>. You can close this page.</p>")


@app.get("/draft/{draft_id}")
def show_draft(draft_id: str):
    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(404)
    if draft["status"] != "pending":
        link = ""
        if draft["post_urn"]:
            link = f' <a href="https://www.linkedin.com/feed/update/{escape(draft["post_urn"])}/">View it on LinkedIn</a>.'
        return page(f"<p>This draft was already {escape(draft['status'])}.{link}</p>")
    image = ""
    if draft["kind"] == "spotlight":
        url = escape(draft["image_url"] or "")
        preview = f'<img class="cover" src="{url}" alt="{escape(draft["image_alt"] or "")}">' if url else ""
        image = f"""<p><label>Image URL (leave empty to post without an image)<br>
<input type="url" name="image_url" value="{url}"></label></p>{preview}"""
    title = "This week's story" if draft["kind"] == "spotlight" else "This week's digest"
    return page(f"""<h1>{title}</h1>
<p class="muted">Edit anything you like, then post it. Nothing goes to LinkedIn until you click Post.</p>
<form method="post">{image}
<textarea name="text" oninput="c.textContent=this.value.length">{escape(draft['text'])}</textarea>
<p class="muted"><span id="c">{len(draft['text'])}</span> / 3000 characters</p>
<button class="post" name="action" value="post" onclick="return confirm('Post this to LinkedIn?')">Post to LinkedIn</button>
<button class="skip" name="action" value="skip">Skip this week</button>
</form>""")


@app.post("/draft/{draft_id}")
def act_on_draft(draft_id: str, action: str = Form(...), text: str = Form(""), image_url: str = Form("")):
    draft = db.get_draft(draft_id)
    if not draft or draft["status"] != "pending":
        raise HTTPException(404)
    if action == "skip":
        db.update_draft(draft_id, status="skipped")
        return page("<p>Skipped. See you next week.</p>")
    text = text.strip()
    if not text or len(text) > 3000:
        return page("<p>The post must be between 1 and 3000 characters. Go back and shorten it.</p>")
    auth = db.get_auth()
    if not auth or auth["expires_at"] < time.time():
        return page("<p>LinkedIn login expired. Reconnect from your status page, then come back to this page.</p>")
    image_url = image_url.strip() if draft["kind"] == "spotlight" else ""
    db.update_draft(draft_id, text=text, image_url=image_url or None)
    image_urn = None
    if image_url:
        try:
            image_urn = linkedin.upload_image(auth["access_token"], auth["person_urn"], image_url)
        except Exception as e:  # noqa: BLE001  (show any download or upload failure on the page)
            return page(f"<p>Could not upload the image: {escape(str(e))}</p>"
                        "<p>Go back and try another image URL, or clear it to post without an image.</p>")
    post_urn = linkedin.create_post(auth["access_token"], auth["person_urn"], text,
                                    image_urn, draft["image_alt"] or "")
    db.update_draft(draft_id, status="posted", post_urn=post_urn)
    return page(f'<p>Posted! <a href="https://www.linkedin.com/feed/update/{escape(post_urn)}/">View it on LinkedIn</a>.</p>')
