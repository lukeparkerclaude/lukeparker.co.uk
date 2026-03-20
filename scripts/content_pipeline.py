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

# Anti-Reform detection: negative/hostile phrases that indicate criticism of Reform UK
ANTI_REFORM_PHRASES = [
    "breach data laws", "breach law", "breaking the law",
    "reform's support is falling", "support is falling", "polls falling",
    "educate themselves", "month off",
    "doesn't know where", "crypto donations",
    "skip mandatory", "skipped debate", "avoid the ballot",
    "heated row", "defends himself",
    "scandal", "disarray", "infighting", "in-fighting",
    "slammed", "blasted", "under fire", "faces backlash",
    "extremist", "far right", "far-right",
    "racist", "xenophob", "islamophob",
    "laughing stock", "embarrass",
    "u-turn", "flip-flop", "hypocrisy", "hypocrit",
    "lacks credibility", "not credible",
    "amateurish", "incompeten",
    "failed", "failure",  # only when paired with Reform
    "dangerous", "threat to democracy",
    "populist",
    "implode", "collapse",
    "defection", "defectors",
    "chaos",
    "grift", "grifter",
]

# Sources known for consistently hostile Reform UK coverage
HOSTILE_SOURCES = [
    "byline times", "bylinetimes",
    "the new european", "neweuropean",
    "led by donkeys",
    "hope not hate", "hopenothate",
]

# Sources that sometimes run anti-Reform pieces - apply extra scrutiny
SCRUTINY_SOURCES = [
    "the guardian", "guardian",
    "the independent", "independent",
    "the mirror", "mirror",
    "huffington post", "huffpost",
    "the new statesman", "newstatesman",
    "opendemocracy",
    "politico",
]

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


def is_anti_reform(article: Dict) -> bool:
    """
    Detect if an article is critical/negative about Reform UK.
    Returns True if the article should be BLOCKED.
    """
    title = article["title"].lower()
    description = article.get("description", "").lower()
    text = title + " " + description
    source = article.get("source", "").lower()
    source_url = article.get("source_url", "").lower()

    # Block articles from consistently hostile sources
    for hostile in HOSTILE_SOURCES:
        if hostile in source or hostile in source_url or hostile in title:
            logger.info(f"BLOCKED (hostile source '{hostile}'): {article['title'][:60]}")
            return True

    # Check for anti-Reform phrases in title (title is most important signal)
    for phrase in ANTI_REFORM_PHRASES:
        if phrase in title:
            logger.info(f"BLOCKED (anti-Reform phrase '{phrase}' in title): {article['title'][:60]}")
            return True

    # For scrutiny sources, also check description for anti-Reform phrases
    is_scrutiny_source = any(s in source or s in source_url or s in title for s in SCRUTINY_SOURCES)
    if is_scrutiny_source:
        for phrase in ANTI_REFORM_PHRASES:
            if phrase in text:
                logger.info(f"BLOCKED (scrutiny source + anti-Reform phrase '{phrase}'): {article['title'][:60]}")
                return True

        # Extra check: if article mentions Reform UK AND is from a scrutiny source,
        # look for negative framing words near "reform"
        if "reform" in title:
            negative_framings = [
                "row", "crisis", "backlash", "controversy", "controversial",
                "question", "probe", "investigate", "concern", "worry",
                "anger", "fury", "outrage", "condemn", "criticis", "attack",
                "warn", "alarm", "fear",
            ]
            for framing in negative_framings:
                if framing in title:
                    logger.info(f"BLOCKED (scrutiny source + negative framing '{framing}'): {article['title'][:60]}")
                    return True

    return False


def is_reform_relevant(article: Dict) -> bool:
    """
    Check if article is actually relevant to Reform UK or reform policy topics.
    Filters out articles that just happen to mention 'reform' in passing.
    """
    title = article["title"].lower()
    text = (title + " " + article.get("description", "")).lower()

    # Must mention Reform UK specifically, or be about policy reform topics we care about
    direct_reform = ["reform uk", "reform party", "reform councillor", "reform council",
                     "nigel farage", "richard tice", "reform mp", "reform mps"]

    policy_topics = ["immigration reform", "nhs reform", "council tax", "policing reform",
                     "civil service reform", "education reform", "housing reform",
                     "governance reform", "electoral reform", "government waste",
                     "council reform"]

    has_direct = any(term in text for term in direct_reform)
    has_policy = any(term in text for term in policy_topics)

    return has_direct or has_policy


def calculate_relevance_score(article: Dict) -> float:
    """
    Calculate relevance score for an article based on keywords and content.
    Returns a score from 0 to 100.
    """
    text = (article["title"] + " " + article["description"]).lower()
    score = 0.0

    # High-priority keywords
    high_priority = ["reform uk", "reform party", "reform councillor"]
    for keyword in high_priority:
        if keyword in text:
            score += 20

    # Medium-priority keywords
    medium_priority = ["nigel farage", "richard tice", "council tax",
                       "immigration", "nhs reform", "policing reform"]
    for keyword in medium_priority:
        if keyword in text:
            score += 10

    # Lower-priority general keywords
    general_keywords = ["uk", "britain", "parliament", "government", "election", "council"]
    for keyword in general_keywords:
        if keyword in text:
            score += 3

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
    """Filter articles by relevance, block anti-Reform content, and rank by score."""
    logger.info(f"Filtering {len(articles)} articles for relevance...")

    blocked_count = 0
    irrelevant_count = 0
    scored_articles = []

    for article in articles:
        # STEP 1: Block anti-Reform articles
        if is_anti_reform(article):
            blocked_count += 1
            continue

        # STEP 2: Check if actually relevant to Reform UK
        if not is_reform_relevant(article):
            irrelevant_count += 1
            logger.debug(f"Skipped (not Reform-relevant): {article['title'][:60]}")
            continue

        # STEP 3: Score remaining articles
        score = calculate_relevance_score(article)
        article["relevance_score"] = score
        if score >= 20:  # Minimum relevance threshold
            scored_articles.append(article)

    # Sort by score (descending) then by priority
    scored_articles.sort(key=lambda x: (-x["relevance_score"], -x.get("priority", 0)))

    logger.info(f"Blocked {blocked_count} anti-Reform articles")
    logger.info(f"Skipped {irrelevant_count} irrelevant articles")
    logger.info(f"Filtered to {len(scored_articles)} relevant pro-Reform articles")
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

    prompt = f"""You are Luke Parker, a Reform UK County Councillor for Preston East on Lancashire County Council.
You are professional, evidence-based, and passionate about reform and governance improvements.
Your writing style is authoritative but accessible, combining policy expertise with genuine concern
for better government.

IMPORTANT: If the original article below is CRITICAL of Reform UK, NEGATIVE about Reform UK,
or paints Reform UK in a bad light, respond with EXACTLY the text "REJECT_ANTI_REFORM" and nothing else.
Only rewrite articles that are POSITIVE about Reform UK, or neutral news that can be framed positively
from a Reform UK perspective.

Rewrite this news article from your perspective as a Reform UK councillor and thought leader:

ORIGINAL TITLE: {article['title']}

ORIGINAL CONTENT:
{article['description'][:2000]}

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
11. Write a NEW headline that is positive and supportive of Reform UK. Start with the headline on the first line.

Output ONLY the rewritten article content, starting with the new headline on line 1, then the article body.
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

        # Check if Claude flagged this as anti-Reform
        if "REJECT_ANTI_REFORM" in rewritten_content:
            logger.info(f"Claude rejected as anti-Reform: {article['title'][:60]}")
            return None

        # Extract new headline if present (first line)
        lines = rewritten_content.split("\n", 1)
        if len(lines) > 1 and not lines[0].startswith("#") and not lines[0].startswith("<"):
            new_headline = lines[0].strip().lstrip("# ").strip()
            if new_headline and len(new_headline) > 10:
                article["title"] = new_headline
                rewritten_content = lines[1].strip()

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


def normalize_title(title: str) -> str:
    """Normalize a title for comparison by removing common variations."""
    title = title.lower().strip()
    # Remove source attribution (e.g. "- The Guardian", "| BBC News")
    title = re.sub(r'\s*[-–—|]\s*(the\s+)?(guardian|independent|telegraph|bbc|sky|express|gb news|yahoo|times|mirror|mail|sun|byline|politics home|church times|european conservative|nation\.cymru|staffordshire).*$', '', title, flags=re.IGNORECASE)
    # Remove punctuation and extra whitespace
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def titles_are_similar(title1: str, title2: str) -> bool:
    """
    Check if two titles are about the same topic using word overlap.
    Returns True if they're likely duplicates.
    """
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)

    # Exact match after normalization
    if norm1 == norm2:
        return True

    # Word overlap check
    words1 = set(norm1.split())
    words2 = set(norm2.split())

    # Remove common stop words
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
                  "for", "of", "and", "or", "but", "with", "by", "from", "as", "its",
                  "that", "this", "it", "be", "has", "have", "had", "do", "does", "did",
                  "will", "would", "could", "should", "may", "might", "can", "shall",
                  "uk", "reform", "party", "says", "said", "after", "new", "over"}
    words1 = words1 - stop_words
    words2 = words2 - stop_words

    if not words1 or not words2:
        return False

    # Calculate Jaccard similarity
    intersection = words1 & words2
    union = words1 | words2
    similarity = len(intersection) / len(union) if union else 0

    return similarity >= 0.45  # 45% word overlap = likely same topic


def article_exists(article: Dict, db: Dict) -> bool:
    """Check if an article already exists in the database (by URL or topic similarity)."""
    source_url = article.get("source_url", "")
    article_title = article.get("title", "")

    for existing in db["articles"]:
        # Check exact URL match
        if source_url and existing.get("source_url") == source_url:
            logger.debug(f"Duplicate (same URL): {article_title[:60]}")
            return True

        # Check title similarity (catches same topic from different sources)
        existing_title = existing.get("title", existing.get("original_title", ""))
        if titles_are_similar(article_title, existing_title):
            logger.debug(f"Duplicate (similar title): '{article_title[:50]}' ~ '{existing_title[:50]}'")
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

    # Find and replace the articles grid content
    # The grid is: <div id="articles-grid">...articles...</div>\n            </section>
    # We need to match everything between the opening div and the </div> that precedes </section>
    pattern = r'(<div\s+id="articles-grid">).*?(</div>\s*</section>)'
    replacement = r"\1\n" + article_cards + r"\n            \2"

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
