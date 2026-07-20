#!/usr/bin/env python3
"""Install a new week of picks in index.html and archive the outgoing week.

Usage:
    python3 scripts/update_week.py picks.json [--dry-run]

The JSON payload looks like:

{
  "date": "July 17, 2026",
  "intro": "Sentence or two introducing the week. May contain HTML entities.",
  "books": [
    {
      "title": "Thunder and Mercy",
      "author": "Jennifer Robin Barr",
      "genres": "Historical fiction / Mystery",
      "ages": "Ages 10&ndash;14",
      "star": "Starred &middot; School Library Journal",   // optional
      "blurb": "...",
      "lola": "...",
      "source": "July 14, 2026 &middot; Calkins Creek &middot; ...",
      "isbn13": "9781635923261",
      "isbn10": "1635923263"                                // optional; drives cover art
    }
    // ... 5 total
  ]
}

Text fields are inserted verbatim, so write real HTML entities (&mdash;, &eacute;)
rather than raw unicode, matching the rest of the page.

The script is deliberately strict: it refuses to run if the page does not look
the way it expects, so a malformed edit fails loudly instead of silently
mangling the archive.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

ARCHIVE_H3_STYLE = (
    "font-family: 'Libre Baskerville', serif; font-size: 1.1rem; "
    "color: #4a2040; margin: 2rem 0 1rem;"
)


def fail(msg):
    sys.exit(f"error: {msg}")


def slug_for(date_str):
    """'July 3, 2026' -> 'week-2026-07-03'"""
    try:
        return "week-" + datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        fail(f"could not parse date {date_str!r}; expected e.g. 'July 3, 2026'")


def render_card(book, n):
    for field in ("title", "author", "genres", "ages", "blurb", "lola", "source", "isbn13"):
        if not book.get(field):
            fail(f"book {n} is missing required field {field!r}")

    if book.get("isbn10"):
        cover = (
            f'        <img src="https://m.media-amazon.com/images/P/{book["isbn10"]}'
            f'.01.L.jpg" alt="{book["title"]}">\n'
        )
    else:
        cover = ""

    star = (
        f'          <span class="pill pill-star">{book["star"]}</span>\n'
        if book.get("star")
        else ""
    )

    return (
        f"<!-- {n} -->\n"
        '    <div class="book-card">\n'
        '      <div class="book-cover">\n'
        f'        <span class="pick-num">{n}</span>\n'
        f"{cover}"
        "      </div>\n"
        '      <div class="book-info">\n'
        f'        <h3>{book["title"]}</h3>\n'
        f'        <div class="author">{book["author"]}</div>\n'
        '        <div class="tags">\n'
        f'          <span class="pill pill-genre">{book["genres"]}</span>\n'
        f'          <span class="pill pill-age">{book["ages"]}</span>\n'
        f"{star}"
        "        </div>\n"
        f'        <p class="blurb">{book["blurb"]}</p>\n'
        '        <div class="lola-note">\n'
        f'          <b>For Lola:</b> {book["lola"]}\n'
        "        </div>\n"
        f'        <div class="source">{book["source"]}</div>\n'
        f'        <a href="https://bookshop.org/p/books?keywords={book["isbn13"]}"'
        ' class="buy-link" target="_blank" rel="noopener">Buy at Bookshop.org</a>\n'
        "      </div>\n"
        "    </div>\n"
    )


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if len(args) != 1:
        fail("usage: update_week.py picks.json [--dry-run]")

    payload = json.loads(Path(args[0]).read_text())
    new_date = payload.get("date")
    intro = payload.get("intro")
    books = payload.get("books") or []

    if not new_date or not intro:
        fail("payload needs both 'date' and 'intro'")
    if len(books) != 5:
        fail(f"expected exactly 5 books, got {len(books)}")

    html = INDEX.read_text()

    # ---- locate the live section -------------------------------------------
    try:
        sec_start = html.index('<section id="this-week">')
        cards_start = html.index("<!-- 1 -->", sec_start)
        cards_end = html.index("  </section>", cards_start)
    except ValueError:
        fail("index.html does not match the expected structure; aborting")

    m = re.search(r'<div class="date">(.*?)</div>', html[sec_start:cards_start])
    if not m:
        fail("could not find the current week date")
    old_date = m.group(1).strip()

    if old_date == new_date:
        fail(f"index.html is already showing {new_date}; nothing to do")

    old_slug = slug_for(old_date)
    if f'id="{old_slug}"' in html:
        fail(f"{old_slug} is already archived; aborting to avoid a duplicate")

    # ---- archive the outgoing week -----------------------------------------
    old_cards = re.sub(
        r"^\s*<!-- \d+ -->\n", "", html[cards_start:cards_end].rstrip(), flags=re.M
    )
    archived = (
        f"    <!-- Archived: {old_date} -->\n"
        f'    <div class="archive-week" id="{old_slug}">\n'
        f'      <h3 style="{ARCHIVE_H3_STYLE}">{old_date}</h3>\n\n'
        f"{old_cards}\n"
        "    </div>\n\n"
    )

    # ---- swap in the new week ----------------------------------------------
    new_cards = "\n    ".join(render_card(b, i + 1) for i, b in enumerate(books))
    html = html[:cards_start] + new_cards + "\n" + html[cards_end:]

    html = html.replace(
        f'<div class="date">{old_date}</div>',
        f'<div class="date">{new_date}</div>',
        1,
    )

    intro_open = html.index('<p class="intro-note">') + len('<p class="intro-note">\n')
    intro_close = html.index("    </p>", intro_open)
    html = html[:intro_open] + f"      {intro}\n" + html[intro_close:]

    # ---- archive list + block, newest first --------------------------------
    old_li = (
        '      <li>\n        <a href="#this-week">' + old_date + "</a>\n"
        "        <span>&mdash; current</span>\n      </li>\n"
    )
    if old_li not in html:
        fail("could not find the 'current' entry in the archive list")
    html = html.replace(
        old_li,
        '      <li>\n        <a href="#this-week">' + new_date + "</a>\n"
        "        <span>&mdash; current</span>\n      </li>\n"
        f'      <li>\n        <a href="#{old_slug}">{old_date}</a>\n      </li>\n',
        1,
    )

    anchor = re.search(r"    <!-- Archived: ", html)
    if anchor:
        html = html[: anchor.start()] + archived + html[anchor.start() :]
    else:
        marker = "    </ul>\n"
        idx = html.index(marker) + len(marker)
        html = html[:idx] + "\n" + archived + html[idx:]

    # ---- sanity checks before writing --------------------------------------
    live = html[html.index('<section id="this-week">') : html.index('<hr class="section-rule">')]
    if live.count('class="book-card"') != 5:
        fail("post-edit check failed: live section does not have exactly 5 cards")
    for tag in ("div", "section", "p", "a", "h3", "span"):
        opens = len(re.findall(rf"<{tag}\b", html))
        closes = len(re.findall(rf"</{tag}\b", html))
        if opens != closes:
            fail(f"post-edit check failed: <{tag}> unbalanced ({opens} open, {closes} close)")

    if dry_run:
        print(f"dry run OK: would archive {old_date} ({old_slug}) and install {new_date}")
        return

    INDEX.write_text(html)
    print(f"archived {old_date} as {old_slug}; installed {new_date}")


if __name__ == "__main__":
    main()
