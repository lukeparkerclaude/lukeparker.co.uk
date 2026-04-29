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

Date detection (in order, first hit wins):
  1. <span class="meta-item">D Month YYYY</span>  (used by the modern article template)
  2. Any "DD Month YYYY" or "Month YYYY" date string anywhere in the HTML body
  3. Filename slug ending in "-month-year" (e.g. "...-april-2026.html") -> 28th of that month
  4. Git log first-commit date for the file (if git available)
  5. File mtime (least preferred - all new clones have today's mtime)
"""
import argparse, json, os, re, sys, html, subprocess
from datetime import datetime, timezone, date
from pathlib import Path

CATEGORY_SLUGS = {
    "immigration": "immigration", "economy": "economy", "nhs": "nhs",
    "democracy": "democracy", "defence": "defence", "pensions": "pensions",
    "housing": "housing", "energy": "energy", "crime": "crime",
    "education": "education",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

CARD_INDENT = "                        "

def parse_date_from_text(text):
    """Try to find a date string in text. Supports several common formats."""
    months_alt = '|'.join(MONTHS.keys())
    # 'D Month YYYY' or 'DD Month YYYY'  (e.g. '19 March 2026')
    m = re.search(rf'\b(\d{{1,2}})\s+({months_alt})\s+(\d{{4}})\b', text, re.IGNORECASE)
    if m:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            pass
    # 'Month D, YYYY' or 'Month DD, YYYY'  (e.g. 'March 19, 2026')
    m = re.search(rf'\b({months_alt})\s+(\d{{1,2}}),?\s+(\d{{4}})\b', text, re.IGNORECASE)
    if m:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            pass
    # 'YYYY-MM-DD' ISO
    m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # 'Month YYYY' (no day) — last resort, low priority because too coarse
    m = re.search(rf'\b({months_alt})\s+(\d{{4}})\b', text, re.IGNORECASE)
    if m:
        try:
            return date(int(m.group(2)), MONTHS[m.group(1).lower()], 28)
        except ValueError:
            pass
    return None

def parse_date_from_slug(slug):
    """Slug like 'foo-bar-april-2026' -> April 28, 2026."""
    m = re.search(r'(?:^|-)(' + '|'.join(MONTHS.keys()) + r')-(\d{4})(?:-|$)', slug, re.IGNORECASE)
    if m:
        try:
            return date(int(m.group(2)), MONTHS[m.group(1).lower()], 28)
        except ValueError:
            pass
    return None

_GIT_DATE_CACHE = {}
def parse_date_from_git(path: Path, repo_root: Path):
    """Use git log to find the first commit date for this file."""
    if path in _GIT_DATE_CACHE:
        return _GIT_DATE_CACHE[path]
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--follow", "--format=%aI", "--", str(path.relative_to(repo_root))],
            capture_output=True, text=True, cwd=str(repo_root), timeout=10,
        )
        lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if lines:
            iso = lines[-1]  # Last line in the log is the first commit (oldest)
            d = datetime.fromisoformat(iso).date()
            _GIT_DATE_CACHE[path] = d
            return d
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    _GIT_DATE_CACHE[path] = None
    return None

def parse_article(path: Path, repo_root: Path):
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
    title = html.unescape(title)

    # Excerpt — prefer .article-excerpt, then meta description, then empty
    excerpt_html = first_match(r'<p class="article-excerpt">(.*?)</p>')
    if excerpt_html:
        excerpt = re.sub(r'<[^>]+>', '', excerpt_html).strip()
    else:
        meta = first_match(r'<meta name="description" content="([^"]*)"', flags=0)
        excerpt = meta or ""
    excerpt = html.unescape(excerpt)
    # Strip leading markdown headers for legacy articles
    excerpt = re.sub(r'^#+\s*', '', excerpt).strip()

    # Category
    cat = first_match(r'<span class="category-badge[^"]*">([^<]*)</span>', "Democracy")
    cat_slug_raw = cat.lower().strip()
    cat_slug = CATEGORY_SLUGS.get(cat_slug_raw, cat_slug_raw.split()[0] if cat_slug_raw else "democracy")

    # Read time
    read_time_str = "5 min read"
    for item in re.findall(r'<span class="meta-item">([^<]*)</span>', text):
        if "min read" in item.lower():
            read_time_str = item.strip()
            break

    # Date detection — try meta-item first
    parsed_date = None
    for item in re.findall(r'<span class="meta-item">([^<]*)</span>', text):
        d = parse_date_from_text(item)
        if d:
            parsed_date = d
            break
    # Then anywhere in the article body
    if not parsed_date:
        body = first_match(r'<article[^>]*>(.*?)</article>', "")
        if body:
            parsed_date = parse_date_from_text(body)
    # Then filename slug
    if not parsed_date:
        parsed_date = parse_date_from_slug(path.stem)
    # Then git history
    if not parsed_date:
        parsed_date = parse_date_from_git(path, repo_root)
    # Then mtime fallback
    if not parsed_date:
        parsed_date = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()

    return {
        "slug": path.stem,
        "title": title,
        "excerpt": excerpt,
        "category": cat,
        "category_slug": cat_slug,
        "date_iso": parsed_date.strftime("%Y-%m-%d"),
        "date_card": parsed_date.strftime("%-d %b %Y"),
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

    parsed = [parse_article(p, root) for p in paths]
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
