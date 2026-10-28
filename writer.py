"""Turns a week of articles into LinkedIn posts with Claude: the weekly digest and single-story posts."""

import os
import re
from datetime import datetime, timezone

import anthropic

from feeds import Article

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

SYSTEM = """You write a weekly LinkedIn digest of tech and science news for a professional audience.

From the candidate articles, pick the 3-5 most significant and interesting stories of the week,
spread across topics (software engineering, AI/ML, science, tech industry, SpaceX/NASA,
cybersecurity) when the week allows. Prefer substantive developments over rumors, deals or product minutiae.

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

RANK_SYSTEM = """You pick stories for LinkedIn posts that each go deep on one tech, science or
cybersecurity story, for a professional audience. The author chooses which one to post.

From the candidate articles, pick the {count} most relevant stories right now: significant,
with lasting impact, and worth discussing. Prefer substantive developments over rumors, deals or
product minutiae. Pick each one from a different topic when the candidates allow, so the author
has a real choice of subject.

Output exactly {count} lines, most relevant first, each in this form:
STORY: <article number> | <one sentence in {language} on why it matters>
Output nothing else."""

SPOTLIGHT_SYSTEM = """You write a LinkedIn post that goes deep on one tech, science or cybersecurity story,
for a professional audience. The post is published with the article's cover image.

Write the post in plain text, since LinkedIn does not render markdown:
- An opening hook line that makes people stop scrolling, then a blank line.
- 2-3 short paragraphs: what happened, why it matters, and what to watch next.
- The article URL on its own line.
- A closing question that invites discussion.
- 3-5 relevant hashtags on the last line.

Write the whole post in {language}, translating from the source article (hashtags may stay in
English when that is how they are commonly used).

Keep it under 1,800 characters. Be accurate: only state what the article title and summary
support, and never invent numbers or quotes. Output only the post text."""


def _format(articles: list[Article]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        date = datetime.fromtimestamp(a.published, timezone.utc).strftime("%Y-%m-%d")
        lines.append(f"[{i}] ({a.topic} | {a.source} | {date}) {a.title}\nURL: {a.link}\n{a.summary}")
    return "\n\n".join(lines)


def _write(system: str, content: str, **fields) -> str:
    voice = os.getenv("AUTHOR_VOICE", "").strip()
    system = system.format(language=os.getenv("POST_LANGUAGE", "English"), **fields) + (f"\n\nAbout the author, to match their voice and perspective: {voice}" if voice else "")
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
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to write the post: {response.stop_details}")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError(f"Empty draft (stop_reason={response.stop_reason})")
    return text


def write_digest(articles: list[Article]) -> str:
    return _write(SYSTEM, "Candidate articles from the past week:\n\n" + _format(articles))


def rank_stories(articles: list[Article], recent_posts: list[str] = (), count: int = 4) -> list[tuple[Article, str]]:
    """The most relevant stories to post about, each with why it matters, most relevant first.

    recent_posts are posts already published or drafted; their stories are left out,
    even when another outlet reports them.
    """
    content = "Candidate articles from the past week:\n\n" + _format(articles)
    if recent_posts:
        content += ("\n\nThese posts already covered some stories recently. Do not pick a story they cover, "
                    "even from a different source:\n\n" + "\n\n---\n\n".join(recent_posts))
    text = _write(RANK_SYSTEM, content, count=count)
    picks, seen = [], set()
    for m in re.finditer(r"^STORY:\s*\[?(\d+)\]?\s*\|\s*(.+)$", text, re.M):
        n = int(m.group(1))
        if 1 <= n <= len(articles) and n not in seen:
            seen.add(n)
            picks.append((articles[n - 1], m.group(2).strip()))
    if not picks:
        raise RuntimeError(f"Claude did not list any stories:\n{text[:200]}")
    return picks[:count]


def write_spotlight(article: Article) -> str:
    """Write a post that goes deep on one story."""
    return _write(SPOTLIGHT_SYSTEM, "The story:\n\n" + _format([article]))
