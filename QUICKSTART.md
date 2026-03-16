# Quick Start Guide

Get the lukeparker.co.uk content pipeline running in 5 minutes.

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `feedparser` - Parse RSS feeds
- `anthropic` - Claude API client
- `beautifulsoup4` - HTML parsing
- `requests` - HTTP requests
- `python-slugify` - URL-friendly slugs

## 2. Get Your API Key

1. Go to https://console.anthropic.com
2. Create an account or log in
3. Generate a new API key
4. Copy the key (starts with `sk-ant-`)

## 3. Set Environment Variable

```bash
# On Linux/macOS
export ANTHROPIC_API_KEY='sk-ant-your-key-here'

# On Windows PowerShell
$env:ANTHROPIC_API_KEY='sk-ant-your-key-here'

# Or create .env file (optional)
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
```

## 4. Test with Dry Run

Preview what the pipeline will do without publishing:

```bash
python scripts/content_pipeline.py --dry-run
```

Expected output:
```
======================================================================
LUKEPARKER.CO.UK CONTENT PIPELINE
======================================================================
DRY RUN MODE - No files will be published

--- FETCHING ARTICLES ---
Fetching from 11 RSS feeds...
Fetched 150+ total articles from feeds

--- FILTERING & RANKING ---
Filtered to 30+ relevant articles

--- PROCESSING ARTICLES ---
[1/5] Processing: Reform UK Pledges Better Council Services...
[DRY RUN] Would rewrite: Reform UK Pledges Better Council Services
[DRY RUN] Would save: /articles/reform-uk-pledges-better-council-services.html

======================================================================
PIPELINE COMPLETE
======================================================================
```

## 5. Run for Real

Process up to 5 articles on your first run:

```bash
python scripts/content_pipeline.py --limit 5
```

Check results:
- New articles in `articles/` directory
- Updated `articles_db.json` with metadata
- Updated `index.html` with article cards
- Generated `sitemap.xml` for SEO

## 6. Verify Output

### Check article files
```bash
ls -lah articles/
# Should see .html files like: reform-uk-pledges-better-council-services.html
```

### Check database
```bash
cat articles_db.json
# Should show articles with metadata
```

### Check homepage
```bash
cat index.html | grep -A 5 'articles-grid'
# Should see article cards in the grid
```

## What Happens During a Run

1. **Fetches articles** from 11 RSS feeds (BBC, Telegraph, GB News, etc.)
2. **Filters** articles for relevance (300+ sources → 30+ relevant)
3. **Deduplicates** against existing database
4. **Rewrites** each article in Luke Parker's voice using Claude
5. **Generates** static HTML pages
6. **Updates** homepage index
7. **Creates** sitemap for SEO

Total time: ~2-5 minutes for 5 articles (depends on API response times)

## Common Commands

```bash
# Normal run (up to 50 articles)
python scripts/content_pipeline.py

# Preview without publishing
python scripts/content_pipeline.py --dry-run

# Process only 3 articles
python scripts/content_pipeline.py --limit 3

# Reprocess all articles (ignore duplicates)
python scripts/content_pipeline.py --force-refresh

# See detailed logs
python scripts/content_pipeline.py --verbose

# Combine options
python scripts/content_pipeline.py --dry-run --limit 10 --verbose
```

## Directory Structure After First Run

```
lukeparker-site/
├── scripts/
│   └── content_pipeline.py
├── templates/
│   └── article-template.html
├── articles/                    # NEW
│   ├── reform-uk-better-council.html
│   ├── nhs-reform-policies.html
│   └── ...
├── articles_db.json            # NEW - Article metadata
├── sitemap.xml                 # NEW - SEO sitemap
├── index.html                  # UPDATED with article cards
└── ...
```

## Scheduling Regular Runs

Once you're confident it works, schedule runs with cron:

```bash
# Edit crontab
crontab -e

# Add this line for daily 9 AM runs
0 9 * * * cd /path/to/lukeparker-site && export ANTHROPIC_API_KEY='sk-ant-xxx' && python scripts/content_pipeline.py >> pipeline.log 2>&1

# Or every 6 hours
0 */6 * * * cd /path/to/lukeparker-site && export ANTHROPIC_API_KEY='sk-ant-xxx' && python scripts/content_pipeline.py >> pipeline.log 2>&1
```

Check logs:
```bash
tail -f pipeline.log
```

## Troubleshooting

### Issue: "ANTHROPIC_API_KEY not set"

**Fix**: Make sure you exported the environment variable:
```bash
export ANTHROPIC_API_KEY='sk-ant-your-key'
python scripts/content_pipeline.py
```

### Issue: "Module not found" error

**Fix**: Install dependencies:
```bash
pip install -r requirements.txt
```

### Issue: No articles processed

**Fix**: Check with verbose mode:
```bash
python scripts/content_pipeline.py --verbose --limit 3
```

This shows which articles passed filtering and why.

### Issue: Article cards don't appear on homepage

**Fix**: Make sure `index.html` has the grid container:
```bash
grep -n 'articles-grid' index.html
```

Should output a line number. If not, add this to index.html:
```html
<div id="articles-grid">
    <!-- Articles inserted here -->
</div>
```

## Next Steps

1. **Customize the voice** - Edit `get_rewrite_prompt()` in `content_pipeline.py`
2. **Adjust HTML styling** - Modify `templates/article-template.html`
3. **Add more feeds** - Update `RSS_FEEDS` list
4. **Schedule runs** - Set up cron job
5. **Monitor performance** - Check logs regularly

## Getting Help

For detailed documentation, see:
- `README.md` - Full documentation
- `scripts/content_pipeline.py` - Inline code comments
- `templates/article-template.html` - Template customization

## Costs

Claude Sonnet 4 rewriting:
- ~$0.01-0.02 per article
- 50 articles ≈ $0.50-1.00
- Minimal cost for a professional news pipeline

To optimize costs:
- Use `--limit 5` to process fewer articles per run
- Increase relevance threshold to filter more aggressively
- Consider Claude Haiku for faster, cheaper rewrites
