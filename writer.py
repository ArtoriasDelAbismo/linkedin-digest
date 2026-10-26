"""Turns a week of articles into LinkedIn posts with Claude: the weekly digest and the story of the week."""

import os
import re
from datetime import datetime, timezone

import anthropic

from feeds import Article

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

SYSTEM = """You write a weekly LinkedIn digest of tech and science news for a professional audience.

From the candidate articles, pick the 3-5 most significant and interesting stories of the week,
spread across topics (software engineering, AI/ML, science, tech industry, SpaceX/NASA) when the
week allows. Prefer substantive developments over rumors, deals or product minutiae.

Write the post in plain text, since LinkedIn does not render markdown:
- An opening hook line, then a blank line.
- For each story: a short bold-free headline line starting with an emoji that fits the topic,
  1-2 sentences on what happened and why it matters, then the article URL on its own line.
  Put a blank line between stories.
- A closing line inviting readers to share which story stood out to them.
- 3-5 relevant hashtags on the last line.

Write the whole post in {language}, translating headlines and summaries from the source
articles (hashtags may stay in English when that is how they are commonly used).

Keep it under 2,500 characters. Be accurate: only state what the article title and summary
support, and never invent numbers or quotes. Output only the post text."""

SPOTLIGHT_SYSTEM = """You write a weekly LinkedIn post that goes deep on the single most important tech or
science story of the week, for a professional audience. The post is published with the article's
cover image.

From the candidate articles, pick the one story with the most significance and lasting impact.
Prefer substantive developments over rumors, deals or product minutiae.

Write the post in plain text, since LinkedIn does not render markdown:
- An opening hook line that makes people stop scrolling, then a blank line.
- 2-3 short paragraphs: what happened, why it matters, and what to watch next.
- The article URL on its own line.
- A closing question that invites discussion.
- 3-5 relevant hashtags on the last line.

Write the whole post in {language}, translating from the source article (hashtags may stay in
English when that is how they are commonly used).

Keep it under 1,800 characters. Be accurate: only state what the article title and summary
support, and never invent numbers or quotes.

The first line of your output must be STORY: followed by the number of the article you picked,
e.g. "STORY: 7". Then output only the post text."""


def _format(articles: list[Article]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        date = datetime.fromtimestamp(a.published, timezone.utc).strftime("%Y-%m-%d")
        lines.append(f"[{i}] ({a.topic} | {a.source} | {date}) {a.title}\nURL: {a.link}\n{a.summary}")
    return "\n\n".join(lines)


def _write(system: str, articles: list[Article], extra: str = "") -> str:
    voice = os.getenv("AUTHOR_VOICE", "").strip()
    system = system.format(language=os.getenv("POST_LANGUAGE", "English")) + (f"\n\nAbout the author, to match their voice and perspective: {voice}" if voice else "")
    # Only needed for API keys that aren't scoped to a workspace
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
    client = anthropic.Anthropic(default_headers={"anthropic-workspace-id": workspace} if workspace else None)
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": "Candidate articles from the past week:\n\n" + _format(articles) + extra}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to write the post: {response.stop_details}")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError(f"Empty draft (stop_reason={response.stop_reason})")
    return text


def write_digest(articles: list[Article]) -> str:
    return _write(SYSTEM, articles)


def write_spotlight(articles: list[Article], recent_posts: list[str] = ()) -> tuple[Article, str]:
    """Pick the story of the week and write a post about it. Returns the article and the post text.

    recent_posts are posts already published or drafted; their stories are not picked again,
    even when another outlet reports them.
    """
    extra = ""
    if recent_posts:
        extra = ("\n\nThese posts already covered some stories recently. Do not pick a story they cover, "
                 "even from a different source:\n\n" + "\n\n---\n\n".join(recent_posts))
    text = _write(SPOTLIGHT_SYSTEM, articles, extra)
    m = re.match(r"STORY:\s*\[?(\d+)\]?\s*\n", text)
    if not m or not 1 <= int(m.group(1)) <= len(articles):
        raise RuntimeError(f"Claude did not say which story it picked:\n{text[:200]}")
    return articles[int(m.group(1)) - 1], text[m.end():].strip()
