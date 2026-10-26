"""Print a draft without saving, emailing or posting anything.

    python preview.py              # the weekly digest
    python preview.py spotlight    # the story of the week, with its image URL
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from feeds import fetch_articles, find_image  # noqa: E402
from writer import write_digest, write_spotlight  # noqa: E402

if __name__ == "__main__":
    if sys.argv[1:] == ["spotlight"]:
        from app import spotlight_candidates

        articles, recent = spotlight_candidates()
        print(f"{len(articles)} candidate articles not used in the last {len(recent)} posts\n")
        article, text = write_spotlight(articles, recent)
        print(f"Story: {article.title} ({article.source})\nImage: {find_image(article) or '(none found)'}\n")
        print(text)
    else:
        articles = fetch_articles()
        print(f"{len(articles)} candidate articles\n")
        print(write_digest(articles))
