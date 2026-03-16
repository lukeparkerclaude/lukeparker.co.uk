# Luke Parker Content Pipeline - Complete File Index

## Quick Navigation

**Getting Started?** → Start with `QUICKSTART.md`

**Need Details?** → See `README.md`

**Setting up Production?** → Follow `DEPLOYMENT.md`

**Want Overview?** → Read `PROJECT_SUMMARY.md` (this is a good starting point)

---

## File Guide

### Main Pipeline Script
- **`scripts/content_pipeline.py`** (809 lines)
  - Complete automated content pipeline
  - Fetches from RSS feeds and web sources
  - Rewrites content using Claude API
  - Generates static HTML pages
  - Manages homepage and database
  - Production-ready with comprehensive error handling
  - Usage: `python scripts/content_pipeline.py [--dry-run] [--limit N] [--verbose]`

### Helper Scripts
- **`scripts/test_feeds.py`** (90 lines)
  - Test all RSS feeds for connectivity
  - Verify feed is working
  - Usage: `python scripts/test_feeds.py` or `python scripts/test_feeds.py --feed "BBC News"`

### HTML Templates
- **`templates/article-template.html`** (400+ lines)
  - Professional HTML template for articles
  - Responsive design
  - Mobile-friendly styling
  - Includes author bio, metadata, source attribution
  - Uses placeholders: {{TITLE}}, {{CONTENT}}, {{CATEGORY}}, {{DATE}}, etc.

- **`index.html`** (350+ lines)
  - Homepage for lukeparker.co.uk
  - Responsive grid layout
  - Article cards component
  - Navigation menu
  - About section
  - Footer with contact info
  - Updated dynamically by pipeline

### Configuration Files
- **`requirements.txt`**
  - Python dependencies: feedparser, anthropic, beautifulsoup4, requests, python-slugify
  - Install with: `pip install -r requirements.txt`

- **`.env.example`**
  - Template for environment variables
  - Copy to `.env` and fill in API key
  - Usage: `export ANTHROPIC_API_KEY='your-key'`

### Data Files
- **`articles_db.json`**
  - JSON database of published articles
  - Tracks metadata: slug, title, category, date, source, source_url
  - Used for deduplication
  - Auto-created/updated by pipeline

- **`articles/`** (directory, created at runtime)
  - Contains generated HTML article files
  - One file per article
  - Named using URL-friendly slugs
  - Example: `reform-uk-pledges-better-council-services.html`

### Documentation

#### Getting Started (MUST READ)
- **`QUICKSTART.md`** (250+ lines)
  - 5-minute setup guide
  - Installation steps
  - API key configuration
  - First test run
  - Verification checklist
  - Common commands
  - Scheduling introduction

#### Full Documentation
- **`README.md`** (650+ lines)
  - Complete feature overview
  - Architecture explanation
  - RSS feed sources (11 feeds)
  - Article categories (9 types)
  - Filtering and relevance scoring
  - Claude rewriting process
  - Static site generation details
  - Database management
  - Homepage updates
  - Sitemap generation
  - Configuration options
  - Customization guide
  - Command-line options
  - Logging details
  - Troubleshooting section
  - Future enhancements

#### Production Deployment
- **`DEPLOYMENT.md`** (700+ lines)
  - Pre-deployment checklist
  - Environment setup (Python, venv, API key)
  - Directory permissions
  - Scheduling options:
    - Cron (Linux/macOS)
    - Systemd Timer (modern Linux)
    - Windows Task Scheduler
  - Monitoring and logging setup
  - Logrotate configuration
  - Health checks
  - Web server configuration (Nginx, Apache)
  - Backup strategies
  - Security hardening
  - Performance optimization
  - Troubleshooting guide

#### Project Overview
- **`PROJECT_SUMMARY.md`** (300+ lines)
  - High-level overview
  - What's included
  - Technology stack
  - Data flow diagram
  - Key capabilities
  - Usage examples
  - Security considerations
  - Performance characteristics
  - Deployment options
  - Monitoring setup
  - File manifest
  - Getting started checklist

#### This File
- **`INDEX.md`** (this file)
  - Navigation guide
  - File descriptions
  - Quick reference

---

## Quick Reference

### Installation
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY='sk-ant-your-key'
```

### First Run
```bash
# Preview (no files saved)
python scripts/content_pipeline.py --dry-run --limit 5

# Actually run
python scripts/content_pipeline.py --limit 5

# Check results
ls articles/
cat articles_db.json
```

### Common Commands
```bash
# Normal run
python scripts/content_pipeline.py

# Limit to N articles
python scripts/content_pipeline.py --limit 10

# Dry run preview
python scripts/content_pipeline.py --dry-run

# Ignore duplicate checking
python scripts/content_pipeline.py --force-refresh

# Verbose logging
python scripts/content_pipeline.py --verbose

# Test RSS feeds
python scripts/test_feeds.py
```

### Scheduling (Cron)
```bash
# Daily at 9 AM
0 9 * * * cd /path/to/lukeparker-site && source .env && python scripts/content_pipeline.py >> logs/pipeline.log 2>&1

# Every 6 hours
0 */6 * * * cd /path/to/lukeparker-site && source .env && python scripts/content_pipeline.py >> logs/pipeline.log 2>&1
```

---

## Content Architecture

### Data Flow
```
11 RSS Feeds + Reform UK Website
    ↓
Fetch ~300 articles
    ↓
Filter by relevance (~30 articles remain)
    ↓
Check database (deduplication)
    ↓
Rewrite with Claude Sonnet 4
    ↓
Generate HTML using template
    ↓
Update article database
    ↓
Update homepage index
    ↓
Generate sitemap.xml
    ↓
Publish static files
```

### Article Categories
1. Immigration
2. Economy
3. NHS Reform
4. Policing
5. Education
6. Housing
7. Democracy
8. Council Reform
9. General

### RSS Feed Sources
- Google News (6 custom searches)
- BBC News Politics
- The Telegraph
- GB News
- Daily Express
- Sky News
- Reform UK official website

---

## Key Features

- **Fully Automated** - No manual intervention
- **Smart Filtering** - Relevance scoring system
- **AI Rewriting** - Claude API integration
- **Static Site** - Fast, secure, scalable
- **Deduplication** - No duplicate articles
- **SEO Ready** - Sitemap, metadata, canonical URLs
- **Responsive Design** - Mobile-friendly templates
- **Comprehensive Logging** - Debug-level information
- **Rate Limited** - Respectful API usage
- **Production Ready** - Error handling, validation, robustness

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.8+ |
| API | Anthropic Claude Sonnet 4 |
| RSS Parsing | feedparser |
| HTML Parsing | BeautifulSoup4 |
| HTTP Requests | requests |
| URL Slugs | python-slugify |
| Web Server | Nginx/Apache (optional) |
| Scheduling | Cron/Systemd/Task Scheduler |

---

## Customization Hotspots

Edit these files to customize:

1. **Luke Parker's Voice**
   - File: `scripts/content_pipeline.py`
   - Function: `get_rewrite_prompt()`
   - Change: The Claude prompt and instructions

2. **HTML Styling**
   - File: `templates/article-template.html` and `index.html`
   - Change: CSS styles, colors, layout

3. **Categories & Keywords**
   - File: `scripts/content_pipeline.py`
   - Dict: `CATEGORIES`
   - Change: Add/modify categories and keywords

4. **RSS Feeds**
   - File: `scripts/content_pipeline.py`
   - List: `RSS_FEEDS`
   - Change: Add/remove/update feed sources

5. **Filtering Logic**
   - File: `scripts/content_pipeline.py`
   - Function: `calculate_relevance_score()`
   - Change: Scoring parameters and thresholds

---

## System Requirements

- Python 3.8 or newer
- ~500MB disk space (grows with articles)
- Internet connection (for RSS feeds and API)
- Anthropic API key (free with credit)
- Optional: Web server (Nginx, Apache, etc.)

---

## Costs

Using Claude Sonnet 4:
- ~$0.01-0.02 per article rewrite
- 50 articles ≈ $0.50-1.00
- Daily runs: ~$5-10/month

To reduce costs:
- Use `--limit` to process fewer articles
- Use Claude Haiku instead (change in script)
- Increase relevance threshold

---

## Support Resources

- **Getting Started**: `QUICKSTART.md`
- **How Things Work**: `README.md`
- **Production Setup**: `DEPLOYMENT.md`
- **Project Overview**: `PROJECT_SUMMARY.md`
- **Code Comments**: `scripts/content_pipeline.py` (inline docs)
- **Test Feeds**: `python scripts/test_feeds.py`

---

## Troubleshooting

### Can't find a file?
Check the complete file list above.

### How do I customize X?
1. Find the section in `README.md` "Customization"
2. Check the "Customization Hotspots" table above
3. Look at inline comments in the Python script

### Pipeline not running?
1. Check `QUICKSTART.md` step 2-3 (API key setup)
2. Run: `python scripts/test_feeds.py` (verify feeds work)
3. Run: `python scripts/content_pipeline.py --verbose` (see what's happening)
4. See `README.md` "Troubleshooting" section

### Want to schedule automated runs?
See `DEPLOYMENT.md` sections on:
- Cron scheduling
- Systemd timers
- Windows Task Scheduler

---

## File Statistics

- **Total Files**: 12
- **Total Lines**: 2,815+
- **Code**: ~900 lines (Python + HTML templates)
- **Documentation**: ~1,900 lines (guides + inline comments)
- **Productivity Ratio**: 2+ docs per line of code

---

## Checklist: Before First Run

- [ ] Python 3.8+ installed
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Anthropic API key obtained
- [ ] API key set: `export ANTHROPIC_API_KEY='sk-ant-...'`
- [ ] Feeds tested: `python scripts/test_feeds.py`
- [ ] Dry run successful: `python scripts/content_pipeline.py --dry-run`
- [ ] First run completed: `python scripts/content_pipeline.py --limit 5`
- [ ] Articles generated: `ls articles/`
- [ ] Database created: `cat articles_db.json`
- [ ] Homepage updated: Check `index.html`

---

## Next Steps

1. **Immediate**: Read `QUICKSTART.md`
2. **Setup**: Follow installation steps
3. **Test**: Run dry-run and first real run
4. **Customize**: Update templates and prompts
5. **Deploy**: Follow `DEPLOYMENT.md`
6. **Monitor**: Set up logging and health checks
7. **Maintain**: Regular updates and backups

---

**Created**: 2025-03-16
**Status**: Production Ready
**Location**: `/sessions/epic-dazzling-babbage/lukeparker-site/`
