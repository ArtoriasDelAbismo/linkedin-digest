"""Print a digest draft without saving, emailing or posting anything: python preview.py"""

from dotenv import load_dotenv

load_dotenv()

from feeds import fetch_articles  # noqa: E402
from writer import write_digest  # noqa: E402

if __name__ == "__main__":
    articles = fetch_articles()
    print(f"{len(articles)} candidate articles\n")
    print(write_digest(articles))
