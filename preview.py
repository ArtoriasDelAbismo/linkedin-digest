"""Print a draft without saving, emailing or posting anything.

    python preview.py              # the weekly digest
    python preview.py spotlight    # the stories a story post would offer, and the post for the first one
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from feeds import fetch_articles, find_image  # noqa: E402
from writer import rank_stories, write_digest, write_spotlight  # noqa: E402

if __name__ == "__main__":
    if sys.argv[1:] == ["spotlight"]:
        from app import spotlight_candidates

        articles, recent = spotlight_candidates()
        print(f"{len(articles)} candidate articles not used in the last {len(recent)} posts\n")
        picks = rank_stories(articles, recent)
        for i, (a, why) in enumerate(picks, 1):
            print(f"{i}. [{a.topic}] {a.title} ({a.source})\n   {why}")
        article = picks[0][0]
        print(f"\nPost for story 1. Image: {find_image(article) or '(none found)'}\n")
        print(write_spotlight(article))
    else:
        articles = fetch_articles()
        print(f"{len(articles)} candidate articles\n")
        print(write_digest(articles))
