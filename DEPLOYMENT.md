# Deployment Guide

Production setup for lukeparker.co.uk content pipeline.

## Pre-Deployment Checklist

- [ ] Python 3.8+ installed
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Anthropic API key obtained
- [ ] RSS feeds tested: `python scripts/test_feeds.py`
- [ ] Dry run successful: `python scripts/content_pipeline.py --dry-run`
- [ ] First real run tested: `python scripts/content_pipeline.py --limit 5`
- [ ] Articles generated correctly
- [ ] Homepage updates working
- [ ] Web server configured (if applicable)
- [ ] Backups scheduled
- [ ] Monitoring set up

## Environment Setup

### 1. System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3 python3-pip python3-venv

# macOS
brew install python3
```

### 2. Virtual Environment (Recommended)

```bash
cd /path/to/lukeparker-site
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. API Key Management

#### Option A: Environment Variable

```bash
export ANTHROPIC_API_KEY='sk-ant-your-key'
```

#### Option B: .env File (Better for Deployment)

```bash
cp .env.example .env
# Edit .env and add your API key
nano .env
```

Update cron jobs to load .env:

```bash
0 9 * * * cd /path/to/lukeparker-site && source .env && python scripts/content_pipeline.py
```

#### Option C: Secrets Management (Production)

For production servers, use proper secrets management:

```bash
# Using environment variable from secrets system
systemctl set-environment ANTHROPIC_API_KEY=$(cat /etc/secrets/anthropic-api-key)
```

## Directory Permissions

```bash
# Allow pipeline to write articles
chmod 755 /path/to/lukeparker-site
chmod 755 /path/to/lukeparker-site/articles
chmod 755 /path/to/lukeparker-site/templates

# Allow web server to read articles
chown -R www-data:www-data /path/to/lukeparker-site/articles
chmod 755 /path/to/lukeparker-site/articles
chmod 644 /path/to/lukeparker-site/articles/*.html
```

## Scheduling

### Option 1: Cron (Recommended for Linux/macOS)

#### Setup

```bash
# Edit crontab
crontab -e

# Add scheduling rules (see examples below)
```

#### Examples

Daily at 9 AM:
```bash
0 9 * * * cd /path/to/lukeparker-site && source .env && python scripts/content_pipeline.py >> logs/pipeline.log 2>&1
```

Every 6 hours:
```bash
0 */6 * * * cd /path/to/lukeparker-site && source .env && python scripts/content_pipeline.py >> logs/pipeline.log 2>&1
```

Twice daily (9 AM and 5 PM):
```bash
0 9,17 * * * cd /path/to/lukeparker-site && source .env && python scripts/content_pipeline.py >> logs/pipeline.log 2>&1
```

Three times daily:
```bash
0 9,13,21 * * * cd /path/to/lukeparker-site && source .env && python scripts/content_pipeline.py >> logs/pipeline.log 2>&1
```

Weekdays only:
```bash
0 9 * * 1-5 cd /path/to/lukeparker-site && source .env && python scripts/content_pipeline.py >> logs/pipeline.log 2>&1
```

#### Cron Timing Tips

- `0 9 * * *` = 9:00 AM every day
- `0 */6 * * *` = Every 6 hours (0, 6, 12, 18 o'clock)
- `0 9,13,21 * * *` = 9 AM, 1 PM, 9 PM
- `0 9 * * 1-5` = Weekdays only

#### View Logs

```bash
# Recent cron runs
tail -f logs/pipeline.log

# Cron job history
grep CRON /var/log/syslog  # Linux
log stream --predicate 'process == "cron"'  # macOS
```

### Option 2: Systemd Timer (Linux)

Create systemd service file:

```ini
# /etc/systemd/system/lukeparker-pipeline.service
[Unit]
Description=Luke Parker Content Pipeline
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/lukeparker-site
Environment="ANTHROPIC_API_KEY=sk-ant-xxx"
ExecStart=/usr/bin/python3 scripts/content_pipeline.py
StandardOutput=journal
StandardError=journal
User=luke-parker
```

Create timer file:

```ini
# /etc/systemd/system/lukeparker-pipeline.timer
[Unit]
Description=Luke Parker Content Pipeline Timer
Requires=lukeparker-pipeline.service

[Timer]
# Run daily at 9 AM
OnCalendar=daily
OnCalendar=*-*-* 09:00:00

# Run every 6 hours
# OnCalendar=*-*-* 00,06,12,18:00:00

Unit=lukeparker-pipeline.service

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable lukeparker-pipeline.timer
sudo systemctl start lukeparker-pipeline.timer

# Check status
sudo systemctl status lukeparker-pipeline.timer
sudo journalctl -u lukeparker-pipeline.service -f
```

### Option 3: Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Name: "Luke Parker Pipeline"
4. Trigger: Daily at 9:00 AM
5. Action: Start program
   - Program: `C:\Python\python.exe`
   - Arguments: `scripts\content_pipeline.py`
   - Start in: `C:\path\to\lukeparker-site`
6. Set environment variable in batch wrapper:

Create `run_pipeline.bat`:

```batch
@echo off
set ANTHROPIC_API_KEY=sk-ant-your-key
cd C:\path\to\lukeparker-site
python scripts\content_pipeline.py >> logs\pipeline.log 2>&1
```

Then schedule `run_pipeline.bat` instead.

## Monitoring & Logging

### Log Directory

```bash
mkdir -p /path/to/lukeparker-site/logs
```

### Logrotate Configuration (Linux)

Create `/etc/logrotate.d/lukeparker`:

```
/path/to/lukeparker-site/logs/*.log {
    weekly
    rotate 4
    compress
    delaycompress
    notifempty
    create 0644 www-data www-data
    sharedscripts
    postrotate
        systemctl restart lukeparker-pipeline.timer > /dev/null 2>&1 || true
    endscript
}
```

### Real-Time Monitoring

```bash
# Watch logs as they're written
tail -f logs/pipeline.log

# Monitor with color highlighting
tail -f logs/pipeline.log | grep --color=auto -E '(ERROR|WARNING|FAIL|OK|SUCCESS)'

# Count articles per day
grep "Successfully processed" logs/pipeline.log | wc -l
```

### Health Check

Create a health check script:

```bash
#!/bin/bash
# check_pipeline.sh

LAST_RUN=$(stat -f %m logs/pipeline.log)  # macOS
# LAST_RUN=$(stat -c %Y logs/pipeline.log)  # Linux

NOW=$(date +%s)
AGE=$(($NOW - $LAST_RUN))

# Alert if last run was >12 hours ago
if [ $AGE -gt 43200 ]; then
    echo "WARNING: Pipeline hasn't run in $(($AGE / 3600)) hours"
    # Send alert (email, Slack, etc)
fi
```

Run from cron:

```bash
0 * * * * /path/to/lukeparker-site/check_pipeline.sh
```

## Web Server Configuration

### Nginx

```nginx
server {
    listen 80;
    server_name lukeparker.co.uk;
    root /path/to/lukeparker-site;

    location / {
        try_files $uri $uri/ =404;
    }

    location /articles/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /sitemap.xml {
        expires 7d;
    }

    location /articles_db.json {
        deny all;  # Hide database
    }

    # Redirect old URLs if needed
    # rewrite ^/old-article$ /articles/new-article.html permanent;
}
```

### Apache

```apache
<Directory /path/to/lukeparker-site>
    Options Indexes FollowSymLinks
    AllowOverride All
    Require all granted
</Directory>

<Files articles_db.json>
    Deny from all
</Files>

<Directory /path/to/lukeparker-site/articles>
    ExpiresActive On
    ExpiresByType text/html "access plus 30 days"
    Header set Cache-Control "public, immutable"
</Directory>
```

## Backups

### Manual Backup

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/path/to/backups"

mkdir -p $BACKUP_DIR

# Backup articles and database
tar -czf $BACKUP_DIR/lukeparker_$DATE.tar.gz \
    /path/to/lukeparker-site/articles/ \
    /path/to/lukeparker-site/articles_db.json \
    /path/to/lukeparker-site/index.html

# Keep only last 30 days
find $BACKUP_DIR -name "lukeparker_*.tar.gz" -mtime +30 -delete

echo "Backup complete: lukeparker_$DATE.tar.gz"
```

Schedule daily:

```bash
0 2 * * * /path/to/lukeparker-site/backup.sh
```

### Automated Cloud Backup

```bash
#!/bin/bash
# backup_to_s3.sh - Requires AWS CLI

aws s3 cp \
    /path/to/lukeparker-site/articles_db.json \
    s3://your-bucket/lukeparker-backups/articles_db_$(date +%Y%m%d).json
```

## Performance Optimization

### Content Caching

Add to cron job to cache static assets:

```bash
0 9 * * * cd /path/to/lukeparker-site && \
  source .env && \
  python scripts/content_pipeline.py && \
  python -m http.server --directory articles 8000 &  # Optional: cache warmup
```

### Database Optimization

Monitor database size:

```bash
ls -lh articles_db.json
# If >10MB, consider archiving old articles
```

Archive old articles:

```bash
#!/bin/bash
# archive_old_articles.py would move articles >1 year old
# to articles/archive/ directory
```

### API Rate Limiting

Current settings (adjust if needed):

- `API_RATE_LIMIT_DELAY = 1` second between API calls
- `MAX_ARTICLES_PER_RUN = 50` articles per execution

Increase delay to reduce costs:

```python
API_RATE_LIMIT_DELAY = 2  # 2 second delay between rewrites
```

Decrease articles per run:

```python
python scripts/content_pipeline.py --limit 10  # Only 10 articles
```

## Security

### Protect Sensitive Files

```bash
# Hide API key in .env
chmod 600 /path/to/lukeparker-site/.env
chown luke-parker:luke-parker /path/to/lukeparker-site/.env

# Hide database
chmod 600 /path/to/lukeparker-site/articles_db.json

# Allow public read of articles
chmod 644 /path/to/lukeparker-site/articles/*.html
```

### Monitor Access

```bash
# Check who can read sensitive files
ls -la articles_db.json .env

# Audit logs
tail -f /var/log/auth.log | grep lukeparker
```

### API Key Rotation

1. Generate new key in Anthropic console
2. Update .env file
3. Test with dry run: `python scripts/content_pipeline.py --dry-run`
4. Schedule next run to use new key
5. Revoke old key in console

## Troubleshooting

### Pipeline not running

**Check cron logs:**
```bash
grep CRON /var/log/syslog
# Or systemd
journalctl -u lukeparker-pipeline.service
```

### "Command not found" in cron

Use full paths:

```bash
# Bad:
0 9 * * * cd /path && python script.py

# Good:
0 9 * * * cd /path && /usr/bin/python3 script.py
```

### Articles not updating

```bash
# Check if pipeline is running
ps aux | grep content_pipeline

# Test manually
cd /path/to/lukeparker-site
source .env
python scripts/content_pipeline.py --verbose

# Check permissions
ls -la articles/
ls -la articles_db.json
```

### API errors

- Check API key is valid
- Check rate limiting (no more than 1 req/sec)
- Check quota on Anthropic console
- Increase `API_RATE_LIMIT_DELAY` if getting throttled

### SSL/HTTPS

For production, use HTTPS:

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name lukeparker.co.uk;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name lukeparker.co.uk;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Rest of config...
}
```

Use Let's Encrypt for free certificates:

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot certonly -d lukeparker.co.uk
```

## Support & Maintenance

### Monthly Maintenance

- [ ] Review logs for errors
- [ ] Check API usage and costs
- [ ] Verify article count growing
- [ ] Test RSS feeds: `python scripts/test_feeds.py`
- [ ] Review search rankings
- [ ] Update dependencies: `pip install --upgrade -r requirements.txt`

### Quarterly Maintenance

- [ ] Audit file permissions
- [ ] Test disaster recovery
- [ ] Review and rotate logs
- [ ] Update security patches

### Annual Maintenance

- [ ] Review costs vs. benefits
- [ ] Consider model upgrades (Claude 4, etc.)
- [ ] Evaluate new content sources
- [ ] Archive old articles
- [ ] Performance analysis
