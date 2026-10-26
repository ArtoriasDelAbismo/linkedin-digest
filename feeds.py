"""RSS sources and article fetching."""

import calendar
import html
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import feedparser
import httpx

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
    image: str = ""  # image URL from the feed entry, if it had one


def _clean(raw: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    return re.sub(r"\s+", " ", text).strip()[:SUMMARY_CHARS]


def _entry_image(entry) -> str:
    for media in entry.get("media_content", []) + entry.get("media_thumbnail", []):
        if media.get("url") and media.get("medium", "image") == "image":
            return media["url"]
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image/") and enc.get("href"):
            return enc["href"]
    return ""


_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*("[^"]*"|\'[^\']*\')')
_IMAGE_PROPS = ("og:image:secure_url", "og:image:url", "og:image", "twitter:image", "twitter:image:src")


def find_image(article: Article) -> str:
    """The article's cover image: its og:image / twitter:image, else the image from the feed entry."""
    try:
        r = httpx.get(article.link, headers={"User-Agent": "Mozilla/5.0 WeeklyTechDigest/1.0"},
                      follow_redirects=True, timeout=20)
        found = {}
        for tag in _META.findall(r.text[:500_000]):
            attrs = {k.lower(): html.unescape(v[1:-1]).strip() for k, v in _ATTR.findall(tag)}
            prop = (attrs.get("property") or attrs.get("name") or "").lower()
            if prop in _IMAGE_PROPS and attrs.get("content"):
                found.setdefault(prop, attrs["content"])
        for prop in _IMAGE_PROPS:
            if prop in found:
                return urljoin(str(r.url), found[prop])
    except httpx.HTTPError as e:
        print(f"[feeds] could not open {article.link}: {e}")
    return article.image


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
                                    _clean(entry.get("summary", "")), published, _entry_image(entry)))
            count += 1
            if count >= MAX_PER_FEED:
                break
    articles.sort(key=lambda a: a.published, reverse=True)
    return articles
