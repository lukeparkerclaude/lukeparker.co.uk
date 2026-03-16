#!/usr/bin/env python3
"""
Automated Content Pipeline for lukeparker.co.uk

This script orchestrates the following workflow:
1. Fetches news articles from multiple RSS feeds and web sources
2. Filters articles for relevance to Reform UK and policy reform topics
3. Rewrites articles in Luke Parker's voice using Claude API
4. Generates static HTML pages from a template
5. Updates the homepage index with latest articles
6. Maintains a JSON database of published articles
7. Generates a sitemap for SEO

Requirements (pip install):
- feedparser
- anthropic
- beautifulsoup4
- requests
- python-slugify

Environment variables:
- ANTHROPIC_API_KEY: Your Anthropic API key (required for rewriting)

Usage:
    python content_pipeline.py                    # Run normally
    python content_pipeline.py --dry-run          # Preview without publishing
    python content_pipeline.py --limit 5          # Process max 5 articles
    python content_pipeline.py --force-refresh    # Ignore deduplication
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup
from slugify import slugify

# ============================================================================
# Configuration
# ============================================================================

# Base paths
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
ARTICLES_DIR = BASE_DIR / "articles"
TEMPLATES_DIR = BASE_DIR / "templates"
DB_FILE = BASE_DIR / "articles_db.json"
INDEX_FILE = BASE_DIR / "index.html"
SITEMAP_FILE = BASE_DIR / "sitemap.xml"
ARTICLE_TEMPLATE_FILE = TEMPLATES_DIR / "article-template.html"

# Create directories if they don't exist
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Constants
MAX_ARTICLES_PER_RUN = 50
ARTICLES_ON_HOMEPAGE = 20
MIN_ARTICLE_LENGTH = 100  # characters
REWRITTEN_ARTICLE_MIN_WORDS = 400
REWRITTEN_ARTICLE_MAX_WORDS = 800
API_RATE_LIMIT_DELAY = 1  # seconds between API calls

# User Agent for web requests
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Content categories
CATEGORIES = {
    "Immigration": ["immigration", "border", "asylum", "migration"],
    "Economy": ["economy", "fiscal", "tax", "business", "inflation", "interest rate"],
    "NHS Reform": ["nhs", "health", "healthcare", "hospital", "doctor", "gp"],
    "Policing": ["police", "crime", "law enforcement", "policing"],
    "Education": ["education", "school", "university", "student"],
    "Housing": ["housing", "house", "rent", "property", "affordability"],
    "Democracy": ["democracy", "parliament", "voting", "electoral", "reform bill"],
    "Council Reform": ["council", "local government", "council tax"],
    "General": [],
}

# RSS Feed sources
RSS_FEEDS = [
    {
        "name": "Google News - Reform UK",
        "url": "https://news.google.com/rss/search?q=Reform+UK",
        "priority": 10,
    },
    {
        "name": "Google News - UK Reform Policy",
        "url": "https://news.google.com/rss/search?q=UK+reform+policy",
        "priority": 9,
    },
    {
        "name": "Google News - Immigration Reform UK",
        "url": "https://news.google.com/rss/search?q=immigration+reform+UK",
        "priority": 8,
    },
    {
        "name": "Google News - NHS Reform",
        "url": "https://news.google.com/rss/search?q=NHS+reform",
        "priority": 8,
    },
    {
        "name": "Google News - Policing Reform UK",
        "url": "https://news.google.com/rss/search?q=policing+reform+UK",
        "priority": 8,
    },
    {
        "name": "Google News - Council Reform",
        "url": "https://news.google.com/rss/search?q=council+reform+UK",
        "priority": 7,
    },
    {
        "name": "BBC News Politics",
        "url": "https://feeds.bbc.co.uk/news/politics/rss.xml",
        "priority": 9,
    },
    {
        "name": "The Telegraph Politics",
        "url": "https://www.telegraph.co.uk/politics/index.xml",
        "priority": 8,
    },
    {
        "name": "GB News",
        "url": "https://www.gbnews.com/feed",
        "priority": 7,
    },
    {
        "name": "Daily Express Politics",
        "url": "https://www.express.co.uk/feed/news/politics.xml",
        "priority": 7,
    },
    {
        "name": "Sky News Politics",
        "url": "https://feeds.skynews.com/feeds/rss/uk/politics.xml",
        "priority": 8,
    },
]

# ============================================================================
# Logging Setup
# ============================================================================


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging for the pipeline."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


logger = setup_logging()

# ============================================================================
# Article Fetching
# ============================================================================


def fetch_articles_from_feeds() -> List[Dict]:
    """Fetch articles from all RSS feeds."""
    articles = []
    logger.info(f"Fetching from {len(RSS_FEEDS)} RSS feeds...")

    headers = {"User-Agent": USER_AGENT}

    for feed_config in RSS_FEEDS:
        try:
            logger.debug(f"Fetching: {feed_config['name']}")
            feed = feedparser.parse(feed_config["url"])

            if feed.bozo:
                logger.warning(f"Feed parsing warning for {feed_config['name']}: {feed.bozo_exception}")

            for entry in feed.entries[:10]:  # Limit entries per feed
                article = {
                    "title": entry.get("title", "Untitled"),
                    "description": entry.get("description", entry.get("summary", "")),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": feed_config["name"],
                    "source_url": entry.get("link", ""),
                    "priority": feed_config["priority"],
                }

                # Clean HTML from description
                if article["description"]:
                    soup = BeautifulSoup(article["description"], "html.parser")
                    article["description"] = soup.get_text(strip=True)

                if article["title"] and article["link"]:
                    articles.append(article)

            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            logger.error(f"Error fetching {feed_config['name']}: {e}")

    logger.info(f"Fetched {len(articles)} total articles from feeds")
    return articles


def scrape_reform_party_news() -> List[Dict]:
    """Scrape news from Reform UK official website."""
    articles = []
    try:
        logger.debug("Scraping Reform UK official website...")
        url = "https://www.reformparty.uk"
        headers = {"User-Agent": USER_AGENT}

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Look for news/press release links (adjust selectors based on actual site)
        news_links = soup.find_all("a", class_=["news", "press", "article", "post"])

        for link in news_links[:5]:
            href = link.get("href", "")
            if not href.startswith("http"):
                href = urljoin(url, href)

            article = {
                "title": link.get_text(strip=True),
                "description": "",
                "link": href,
                "published": datetime.now().isoformat(),
                "source": "Reform UK Official",
                "source_url": href,
                "priority": 10,
            }

            if article["title"]:
                articles.append(article)

    except Exception as e:
        logger.warning(f"Could not scrape Reform UK website: {e}")

    return articles


# ============================================================================
# Article Filtering & Ranking
# ============================================================================


def calculate_relevance_score(article: Dict) -> float:
    """
    Calculate relevance score for an article based on keywords and content.
    Returns a score from 0 to 100.
    """
    text = (article["title"] + " " + article["description"]).lower()
    score = 0.0

    # High-priority keywords
    high_priority = ["reform", "reform uk", "policy", "governance"]
    for keyword in high_priority:
        if keyword in text:
            score += 15

    # Medium-priority keywords
    medium_priority = ["uk", "britain", "parliament", "government", "election", "council"]
    for keyword in medium_priority:
        if keyword in text:
            score += 5

    # Category-based scoring
    for category, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword in text:
                score += 3

    # Boost by feed priority
    score += article.get("priority", 5) * 2

    # Penalty for very short content
    if len(article["description"]) < MIN_ARTICLE_LENGTH:
        score -= 20

    return min(score, 100)


def filter_and_rank_articles(articles: List[Dict]) -> List[Dict]:
    """Filter articles by relevance and rank by score."""
    logger.info(f"Filtering {len(articles)} articles for relevance...")

    scored_articles = []
    for article in articles:
        score = calculate_relevance_score(article)
        article["relevance_score"] = score
        if score >= 20:  # Minimum relevance threshold
            scored_articles.append(article)

    # Sort by score (descending) then by priority
    scored_articles.sort(key=lambda x: (-x["relevance_score"], -x.get("priority", 0)))

    logger.info(f"Filtered to {len(scored_articles)} relevant articles")
    return scored_articles


def categorize_article(article: Dict) -> str:
    """Determine the best category for an article."""
    text = (article["title"] + " " + article["description"]).lower()

    category_scores = {}
    for category, keywords in CATEGORIES.items():
        score = sum(1 for keyword in keywords if keyword in text)
        category_scores[category] = score

    best_category = max(category_scores, key=category_scores.get)
    return best_category if category_scores[best_category] > 0 else "General"


# ============================================================================
# Article Rewriting with Claude
# ============================================================================


def get_rewrite_prompt(article: Dict) -> str:
    """Generate the prompt for Claude to rewrite the article."""
    category = categorize_article(article)

    prompt = f"""You are Luke Parker, a Reform UK councillor. You are professional, evidence-based,
and passionate about reform and governance improvements. Your writing style is authoritative
but accessible, combining policy expertise with genuine concern for better government.

Rewrite this news article from your perspective as a Reform UK councillor and thought leader:

ORIGINAL TITLE: {article['title']}

ORIGINAL CONTENT:
{article['description'][:2000]}  # Limit input to avoid token overflow

REWRITE REQUIREMENTS:
1. Write 400-800 words
2. Use first person where appropriate ("I believe", "we need", "this demonstrates")
3. Incorporate Reform UK perspective and values (reducing government waste, improving efficiency,
   holding government accountable)
4. Include 2-3 subheadings to structure the article
5. Make it SEO-friendly with natural keyword inclusion
6. DO NOT copy the original text verbatim - rewrite substantially with your own analysis
7. Add specific Reform UK policy positions or references where relevant
8. Include a call to action or forward-looking statement at the end
9. Maintain professional tone while showing passion for reform
10. Category: {category}

Output ONLY the rewritten article content, starting immediately with the text (no intro/outro).
Structure with subheadings using ## format for markdown-style headers."""

    return prompt


def rewrite_article_with_claude(article: Dict, client: Anthropic, dry_run: bool = False) -> Optional[str]:
    """Rewrite an article using Claude API."""
    if dry_run:
        logger.info(f"[DRY RUN] Would rewrite: {article['title']}")
        return f"[DRY RUN PLACEHOLDER] Rewritten version of {article['title']}"

    try:
        logger.debug(f"Rewriting with Claude: {article['title'][:60]}...")

        prompt = get_rewrite_prompt(article)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        rewritten_content = message.content[0].text.strip()

        # Validate minimum word count
        word_count = len(rewritten_content.split())
        if word_count < REWRITTEN_ARTICLE_MIN_WORDS:
            logger.warning(
                f"Rewritten article too short ({word_count} words): {article['title'][:60]}"
            )
            return None

        logger.debug(f"Successfully rewrote article ({word_count} words)")
        return rewritten_content

    except Exception as e:
        logger.error(f"Error rewriting article with Claude: {e}")
        return None


# ============================================================================
# Static HTML Generation
# ============================================================================


def load_article_template() -> str:
    """Load the article template HTML."""
    if not ARTICLE_TEMPLATE_FILE.exists():
        logger.warning(f"Article template not found at {ARTICLE_TEMPLATE_FILE}")
        logger.info("Creating basic default template...")
        return DEFAULT_ARTICLE_TEMPLATE

    with open(ARTICLE_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return f.read()


DEFAULT_ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE}} | Luke Parker - Reform UK Councillor</title>
    <meta name="description" content="{{EXCERPT}}">
    <meta name="author" content="Luke Parker">
    <meta name="keywords" content="{{CATEGORY}}, Reform UK, policy, governance">
    <link rel="canonical" href="https://lukeparker.co.uk/articles/{{SLUG}}.html">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }
        article { background: #fff; padding: 30px; border-radius: 8px; }
        h1 { color: #1a1a1a; border-bottom: 3px solid #0066cc; padding-bottom: 10px; }
        h2 { color: #0066cc; margin-top: 30px; }
        .meta { color: #666; font-size: 0.9em; margin-bottom: 20px; }
        .category { display: inline-block; background: #0066cc; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; margin-right: 10px; }
        .content { margin-top: 20px; }
        footer { margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.9em; color: #666; }
    </style>
</head>
<body>
    <article>
        <span class="category">{{CATEGORY}}</span>
        <h1>{{TITLE}}</h1>
        <div class="meta">
            <strong>By Luke Parker</strong> | Published: {{DATE}} | {{READ_TIME}} min read
        </div>
        <div class="content">
            {{CONTENT}}
        </div>
        <footer>
            <p>This article represents the views and analysis of Luke Parker, a Reform UK councillor focused on
            improving governance and policy. For more information, visit <a href="https://lukeparker.co.uk">lukeparker.co.uk</a></p>
            <p>Original source: <a href="{{SOURCE_URL}}">{{SOURCE}}</a></p>
        </footer>
    </article>
</body>
</html>"""


def calculate_read_time(content: str) -> int:
    """Calculate estimated read time in minutes."""
    words = len(content.split())
    return max(1, round(words / 200))  # Assume 200 words per minute


def convert_markdown_to_html(text: str) -> str:
    """Convert markdown-style headers to HTML."""
    # Convert ## headers to <h2>
    text = re.sub(r"^## (.+)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    # Convert # headers to <h1>
    text = re.sub(r"^# (.+)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)
    # Convert line breaks to paragraphs
    paragraphs = text.split("\n\n")
    paragraphs = [f"<p>{p}</p>" if p.strip() and not p.startswith("<") else p for p in paragraphs]
    return "\n".join(paragraphs)


def generate_article_html(article: Dict, rewritten_content: str) -> str:
    """Generate HTML for a single article."""
    template = load_article_template()

    category = categorize_article(article)
    read_time = calculate_read_time(rewritten_content)
    excerpt = rewritten_content[:200].replace("<p>", "").replace("</p>", "").strip()

    # Convert markdown to HTML
    html_content = convert_markdown_to_html(rewritten_content)

    replacements = {
        "{{TITLE}}": article["title"],
        "{{CONTENT}}": html_content,
        "{{CATEGORY}}": category,
        "{{DATE}}": datetime.now().strftime("%B %d, %Y"),
        "{{READ_TIME}}": str(read_time),
        "{{SLUG}}": article["slug"],
        "{{EXCERPT}}": excerpt,
        "{{SOURCE}}": article["source"],
        "{{SOURCE_URL}}": article["source_url"],
    }

    html = template
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)

    return html


def save_article_html(article: Dict, html_content: str) -> Path:
    """Save article HTML to file."""
    file_path = ARTICLES_DIR / f"{article['slug']}.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Saved article: {file_path}")
    return file_path


# ============================================================================
# Database Management
# ============================================================================


def load_articles_db() -> Dict:
    """Load the articles database."""
    if DB_FILE.exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"articles": [], "last_updated": None}


def save_articles_db(db: Dict) -> None:
    """Save the articles database."""
    db["last_updated"] = datetime.now().isoformat()
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    logger.debug(f"Saved articles database with {len(db['articles'])} articles")


def article_exists(article: Dict, db: Dict) -> bool:
    """Check if an article already exists in the database (by source_url)."""
    source_url = article.get("source_url", "")
    for existing in db["articles"]:
        if existing.get("source_url") == source_url:
            return True
    return False


def add_article_to_db(article: Dict, db: Dict) -> None:
    """Add article to database."""
    db_entry = {
        "slug": article["slug"],
        "title": article["title"],
        "category": categorize_article(article),
        "date": datetime.now().isoformat(),
        "source": article["source"],
        "source_url": article["source_url"],
        "original_title": article["title"],
    }
    db["articles"].insert(0, db_entry)  # Insert at beginning (newest first)
    logger.debug(f"Added article to database: {article['slug']}")


# ============================================================================
# Homepage Index Management
# ============================================================================


def generate_article_card_html(db_article: Dict) -> str:
    """Generate HTML for an article card on the homepage."""
    slug = db_article["slug"]
    date = datetime.fromisoformat(db_article["date"]).strftime("%d %b %Y")
    category = db_article.get("category", "General")
    cat_class = "cat-" + category.lower().replace(" ", "-")
    excerpt = db_article.get("excerpt", "")[:160]
    read_time = db_article.get("read_time", "3 min read")

    return f"""            <article class="article-card">
                <a href="/articles/{slug}.html">
                    <div class="card-meta">
                        <span class="category-badge {cat_class}">{category}</span>
                    </div>
                    <h3>{db_article['title']}</h3>
                    <p class="card-excerpt">{excerpt}</p>
                    <div class="card-footer">
                        <span>{date}</span>
                        <span>{read_time}</span>
                    </div>
                </a>
            </article>"""


def update_homepage_index(dry_run: bool = False) -> None:
    """Update the homepage index with latest articles."""
    if not INDEX_FILE.exists():
        logger.warning(f"Index file not found: {INDEX_FILE}")
        return

    db = load_articles_db()

    # Get the latest articles for homepage
    latest_articles = db["articles"][: ARTICLES_ON_HOMEPAGE]

    # Generate article cards HTML
    article_cards = "\n".join([generate_article_card_html(article) for article in latest_articles])

    # Read current index
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index_content = f.read()

    # Find and replace the articles grid
    # Look for a div with id="articles-grid" or class="articles-grid"
    pattern = r'(<div[^>]*(?:id|class)="?articles-grid"?[^>]*>)(.*?)(</div>)'
    replacement = r"\1\n" + article_cards + r"\n    \3"

    new_content = re.sub(pattern, replacement, index_content, flags=re.DOTALL)

    if new_content == index_content:
        logger.warning("Could not find articles-grid in index.html - article cards not updated")
        logger.info("Ensure index.html has: <div id=\"articles-grid\"> or <div class=\"articles-grid\">")
    else:
        if not dry_run:
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                f.write(new_content)
            logger.info("Updated homepage index with latest articles")
        else:
            logger.info("[DRY RUN] Would update homepage index")


# ============================================================================
# Sitemap Generation
# ============================================================================


def generate_sitemap(dry_run: bool = False) -> None:
    """Generate sitemap.xml for SEO."""
    db = load_articles_db()

    sitemap_entries = ['<?xml version="1.0" encoding="UTF-8"?>']
    sitemap_entries.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # Add homepage
    sitemap_entries.append(
        """  <url>
    <loc>https://lukeparker.co.uk/</loc>
    <lastmod>{}</lastmod>
    <priority>1.0</priority>
  </url>""".format(datetime.now().strftime("%Y-%m-%d"))
    )

    # Add article pages
    for article in db["articles"]:
        date = datetime.fromisoformat(article["date"]).strftime("%Y-%m-%d")
        sitemap_entries.append(
            f"""  <url>
    <loc>https://lukeparker.co.uk/articles/{article['slug']}.html</loc>
    <lastmod>{date}</lastmod>
    <priority>0.8</priority>
  </url>"""
        )

    sitemap_entries.append("</urlset>")

    sitemap_content = "\n".join(sitemap_entries)

    if not dry_run:
        with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
            f.write(sitemap_content)
        logger.info(f"Generated sitemap.xml with {len(db['articles'])} articles")
    else:
        logger.info(f"[DRY RUN] Would generate sitemap with {len(db['articles'])} articles")


# ============================================================================
# Main Pipeline
# ============================================================================


def main() -> None:
    """Main pipeline orchestration."""
    parser = argparse.ArgumentParser(
        description="Automated content pipeline for lukeparker.co.uk",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python content_pipeline.py                    # Run normally
  python content_pipeline.py --dry-run          # Preview without publishing
  python content_pipeline.py --limit 5          # Process max 5 articles
  python content_pipeline.py --force-refresh    # Ignore deduplication
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without publishing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_ARTICLES_PER_RUN,
        help=f"Maximum articles to process (default: {MAX_ARTICLES_PER_RUN})",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore deduplication and process all articles",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 70)
    logger.info("LUKEPARKER.CO.UK CONTENT PIPELINE")
    logger.info("=" * 70)

    if args.dry_run:
        logger.info("DRY RUN MODE - No files will be published")

    # Initialize Anthropic client
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    # Load existing database
    db = load_articles_db()
    logger.info(f"Loaded database with {len(db['articles'])} existing articles")

    # Fetch articles from all sources
    logger.info("\n--- FETCHING ARTICLES ---")
    all_articles = fetch_articles_from_feeds()
    reform_articles = scrape_reform_party_news()
    all_articles.extend(reform_articles)
    logger.info(f"Total articles from all sources: {len(all_articles)}")

    # Filter and rank by relevance
    logger.info("\n--- FILTERING & RANKING ---")
    filtered_articles = filter_and_rank_articles(all_articles)

    # Deduplicate and limit
    logger.info("\n--- DEDUPLICATION ---")
    new_articles = []
    for article in filtered_articles:
        if args.force_refresh or not article_exists(article, db):
            new_articles.append(article)
            if len(new_articles) >= args.limit:
                break

    logger.info(f"Processing {len(new_articles)} new articles")

    if not new_articles:
        logger.info("No new articles to process")
        logger.info("=" * 70)
        return

    # Process each article
    logger.info("\n--- PROCESSING ARTICLES ---")
    processed_count = 0

    for i, article in enumerate(new_articles, 1):
        logger.info(f"\n[{i}/{len(new_articles)}] Processing: {article['title'][:70]}...")

        # Generate URL-friendly slug
        article["slug"] = slugify(article["title"], max_length=100)

        # Rewrite with Claude
        rewritten = rewrite_article_with_claude(article, client, dry_run=args.dry_run)

        if not rewritten:
            logger.warning(f"Skipping article (rewrite failed): {article['title'][:60]}")
            continue

        # Generate HTML
        html = generate_article_html(article, rewritten)

        # Save HTML file
        if not args.dry_run:
            save_article_html(article, html)
            add_article_to_db(article, db)
        else:
            logger.info(f"[DRY RUN] Would save: /articles/{article['slug']}.html")

        processed_count += 1

        # Rate limiting
        time.sleep(API_RATE_LIMIT_DELAY)

    logger.info(f"\n--- RESULTS ---")
    logger.info(f"Successfully processed: {processed_count} articles")

    # Update homepage and sitemap
    if processed_count > 0 and not args.dry_run:
        logger.info("\n--- UPDATING INDEX & SITEMAP ---")
        save_articles_db(db)
        update_homepage_index(dry_run=args.dry_run)
        generate_sitemap(dry_run=args.dry_run)

    elif args.dry_run and processed_count > 0:
        logger.info("\n--- DRY RUN SUMMARY ---")
        update_homepage_index(dry_run=True)
        generate_sitemap(dry_run=True)

    logger.info("=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
