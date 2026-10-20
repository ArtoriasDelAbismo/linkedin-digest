"""RSS sources and article fetching."""

import calendar
import html
import re
import time
from dataclasses import dataclass

import feedparser

# (topic, source name, feed URL)
FEEDS = [
    ("Software engineering", "GitHub Blog", "https://github.blog/feed/"),
    ("Software engineering", "InfoQ", "https://feed.infoq.com/"),
    ("Software engineering", "Hacker News (best)", "https://hnrss.org/best"),
    ("AI / ML", "Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("AI / ML", "MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("AI / ML", "Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Science", "Quanta Magazine", "https://www.quantamagazine.org/feed/"),
    ("Science", "Nature", "https://www.nature.com/nature.rss"),
    ("Science", "Phys.org", "https://phys.org/rss-feed/"),
    ("Tech industry", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("Tech industry", "The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Tech industry", "TechCrunch", "https://techcrunch.com/feed/"),
    ("SpaceX / NASA", "NASA", "https://www.nasa.gov/news-release/feed/"),
    ("SpaceX / NASA", "SpaceNews", "https://spacenews.com/feed/"),
    ("SpaceX / NASA", "NASASpaceflight", "https://www.nasaspaceflight.com/feed/"),
]

MAX_PER_FEED = 10
SUMMARY_CHARS = 400


@dataclass
class Article:
    topic: str
    source: str
    title: str
    link: str
    summary: str
    published: float


def _clean(raw: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    return re.sub(r"\s+", " ", text).strip()[:SUMMARY_CHARS]


def fetch_articles(days: int = 7) -> list[Article]:
    """Return recent articles from all feeds, newest first, deduplicated by link."""
    cutoff = time.time() - days * 86400
    seen: set[str] = set()
    articles: list[Article] = []
    for topic, source, url in FEEDS:
        feed = feedparser.parse(url, agent="WeeklyTechDigest/1.0")
        if feed.bozo and not feed.entries:
            print(f"[feeds] {source}: failed ({feed.get('bozo_exception')})")
            continue
        count = 0
        for entry in feed.entries:
            parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            published = calendar.timegm(parsed) if parsed else time.time()
            link = entry.get("link", "")
            if published < cutoff or not link or link in seen:
                continue
            seen.add(link)
            articles.append(Article(topic, source, _clean(entry.get("title", "")), link,
                                    _clean(entry.get("summary", "")), published))
            count += 1
            if count >= MAX_PER_FEED:
                break
    articles.sort(key=lambda a: a.published, reverse=True)
    return articles
