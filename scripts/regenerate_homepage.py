#!/usr/bin/env python3
"""
regenerate_homepage.py

Scans the articles/ folder, parses metadata from each article HTML, then regenerates:
  - index.html (the #articles-grid card list, sorted newest-first)
  - articles_db.json
  - sitemap.xml

Designed to be safe to run repeatedly. Idempotent: running with no changes produces
no diff. Run after committing new articles to keep the homepage in sync.

Usage:
    python scripts/regenerate_homepage.py [--repo-root PATH]

If --repo-root is omitted, assumes script is run from repo root or scripts/.
"""
import argparse, json, os, re, sys, html
from datetime import datetime, timezone
from pathlib import Path

CATEGORY_SLUGS = {
    "immigration": "immigration", "economy": "economy", "nhs": "nhs",
    "democracy": "democracy", "defence": "defence", "pensions": "pensions",
    "housing": "housing", "energy": "energy", "crime": "crime",
    "education": "education",
}

CARD_INDENT = "                        "

def parse_article(path: Path):
    """Extract metadata from a generated article HTML file."""
    text = path.read_text(encoding="utf-8", errors="replace")

    def first_match(pattern, default=None, flags=re.DOTALL):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else default

    # Title — prefer <h1>, fall back to <title>
    h1 = first_match(r'<h1[^>]*>(.*?)</h1>')
    title = re.sub(r'<[^>]+>', '', h1).strip() if h1 else None
    if not title:
        t = first_match(r'<title>(.*?)</title>')
        title = re.sub(r'<[^>]+>', '', t).strip() if t else path.stem

    # Excerpt
    excerpt_html = first_match(r'<p class="article-excerpt">(.*?)</p>')
    excerpt = re.sub(r'<[^>]+>', '', excerpt_html).strip() if excerpt_html else ""
    excerpt = html.unescape(excerpt)

    # Category
    cat = first_match(r'<span class="category-badge">([^<]*)</span>', "Democracy")
    cat_slug = CATEGORY_SLUGS.get(cat.lower(), cat.lower())

    # Date — find first .meta-item that looks like a date
    meta_items = re.findall(r'<span class="meta-item">([^<]*)</span>', text)
    date_str = None
    read_time_str = "5 min read"
    for item in meta_items:
        item = item.strip()
        if "min read" in item.lower():
            read_time_str = item
        elif re.match(r'\d{1,2}\s+\w+\s+\d{4}', item):
            date_str = item

    date_iso = None
    date_card = None
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%d %B %Y")
            date_iso = dt.strftime("%Y-%m-%d")
            date_card = dt.strftime("%-d %b %Y")
        except ValueError:
            pass
    if not date_iso:
        # Fall back to file mtime
        ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        date_iso = ts.strftime("%Y-%m-%d")
        date_card = ts.strftime("%-d %b %Y")

    title = html.unescape(title)

    return {
        "slug": path.stem,
        "title": title,
        "excerpt": excerpt,
        "category": cat,
        "category_slug": cat_slug,
        "date_iso": date_iso,
        "date_card": date_card,
        "read_time": read_time_str,
        "filename": path.name,
    }

def render_card(a):
    title = html.escape(a["title"], quote=False)
    excerpt = html.escape(a["excerpt"], quote=False)
    return (
        f'{CARD_INDENT}<article class="article-card"><a href="/articles/{a["slug"]}.html">'
        f'<div class="card-meta"><span class="category-badge cat-{a["category_slug"]}">{a["category"]}</span></div>'
        f'<h3>{title}</h3>'
        f'<p class="card-excerpt">{excerpt}</p>'
        f'<div class="card-footer"><span>{a["date_card"]}</span><span>{a["read_time"]}</span></div>'
        f'</a></article>'
    )

def regenerate_index_html(index_path: Path, articles):
    text = index_path.read_text(encoding="utf-8")
    cards = "\n".join(render_card(a) for a in articles)

    # Replace whole content between <div id="articles-grid"> and the matching </div></section>
    pattern = re.compile(
        r'(<div id="articles-grid">)(.*?)(\s*</div>\s*</section>)',
        re.DOTALL,
    )
    new_text, n = pattern.subn(
        lambda m: m.group(1) + "\n" + cards + "\n                " + m.group(3).lstrip(),
        text,
        count=1,
    )
    if n != 1:
        raise RuntimeError("Could not locate #articles-grid in index.html")
    if new_text != text:
        index_path.write_text(new_text, encoding="utf-8")
    return new_text != text

def regenerate_articles_db(db_path: Path, articles):
    entries = []
    for i, a in enumerate(articles, start=1):
        entries.append({
            "id": i,
            "title": a["title"],
            "slug": a["slug"],
            "date": a["date_iso"],
            "category": a["category_slug"],
            "excerpt": a["excerpt"],
            "readTime": a["read_time"],
            "url": f"/articles/{a['slug']}.html",
        })
    payload = {
        "articles": entries,
        "last_updated": datetime.utcnow().isoformat(),
    }
    new_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    old_text = db_path.read_text(encoding="utf-8") if db_path.exists() else ""

    # Idempotency: ignore last_updated when comparing
    def strip_ts(t):
        return re.sub(r'"last_updated":\s*"[^"]*"', '', t)
    if strip_ts(new_text) != strip_ts(old_text):
        db_path.write_text(new_text, encoding="utf-8")
        return True
    return False

def regenerate_sitemap(sitemap_path: Path, articles):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             '  <url>',
             f'    <loc>https://lukeparker.co.uk/</loc>',
             f'    <lastmod>{today}</lastmod>',
             '    <priority>1.0</priority>',
             '  </url>',
             '  <url>',
             '    <loc>https://lukeparker.co.uk/about.html</loc>',
             f'    <lastmod>{today}</lastmod>',
             '    <priority>0.7</priority>',
             '  </url>']
    for a in articles:
        lines += ['  <url>',
                  f'    <loc>https://lukeparker.co.uk/articles/{a["slug"]}.html</loc>',
                  f'    <lastmod>{a["date_iso"]}</lastmod>',
                  '    <priority>0.8</priority>',
                  '  </url>']
    lines.append('</urlset>')
    new_text = "\n".join(lines) + "\n"
    old_text = sitemap_path.read_text(encoding="utf-8") if sitemap_path.exists() else ""
    if new_text != old_text:
        sitemap_path.write_text(new_text, encoding="utf-8")
        return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=None)
    args = ap.parse_args()

    if args.repo_root:
        root = Path(args.repo_root).resolve()
    else:
        # Try cwd, then parent (if running from scripts/)
        cwd = Path.cwd()
        if (cwd / "articles").is_dir() and (cwd / "index.html").is_file():
            root = cwd
        elif (cwd.parent / "articles").is_dir() and (cwd.parent / "index.html").is_file():
            root = cwd.parent
        else:
            print("ERROR: cannot locate repo root with articles/ and index.html", file=sys.stderr)
            sys.exit(1)

    articles_dir = root / "articles"
    paths = sorted(articles_dir.glob("*.html"))
    if not paths:
        print("ERROR: no articles found", file=sys.stderr)
        sys.exit(1)

    parsed = [parse_article(p) for p in paths]
    # Sort newest first by date_iso, tie-broken by filename mtime
    parsed.sort(key=lambda a: (a["date_iso"], a["filename"]), reverse=True)

    changed = []
    if regenerate_index_html(root / "index.html", parsed):
        changed.append("index.html")
    if regenerate_articles_db(root / "articles_db.json", parsed):
        changed.append("articles_db.json")
    if regenerate_sitemap(root / "sitemap.xml", parsed):
        changed.append("sitemap.xml")

    print(f"Articles: {len(parsed)}")
    print(f"Changed: {', '.join(changed) if changed else 'nothing (already in sync)'}")

if __name__ == "__main__":
    main()
