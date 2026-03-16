#!/usr/bin/env python3
"""
Test helper script to verify RSS feeds are working.

Usage:
    python scripts/test_feeds.py                 # Test all feeds
    python scripts/test_feeds.py --feed "BBC News Politics"
"""

import feedparser
import argparse
import sys
from pathlib import Path

# Add parent dir to path to import content_pipeline
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.content_pipeline import RSS_FEEDS, USER_AGENT

def test_feed(feed_config: dict) -> bool:
    """Test a single RSS feed."""
    name = feed_config['name']
    url = feed_config['url']

    print(f"\nTesting: {name}")
    print(f"URL: {url}")

    try:
        feed = feedparser.parse(url)

        if feed.bozo:
            print(f"  WARNING: {feed.bozo_exception}")

        entry_count = len(feed.entries)
        print(f"  Status: OK ({entry_count} articles)")

        if entry_count > 0:
            first = feed.entries[0]
            print(f"  Latest: {first.get('title', 'No title')[:60]}")

        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Test RSS feeds for the content pipeline",
        epilog="Examples: python test_feeds.py  OR  python test_feeds.py --feed 'BBC News Politics'"
    )

    parser.add_argument(
        '--feed',
        type=str,
        help="Test specific feed by name (substring matching)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("RSS FEED TEST UTILITY")
    print("=" * 70)

    if args.feed:
        # Filter feeds by name
        matching_feeds = [f for f in RSS_FEEDS if args.feed.lower() in f['name'].lower()]

        if not matching_feeds:
            print(f"No feeds found matching: {args.feed}")
            print("\nAvailable feeds:")
            for f in RSS_FEEDS:
                print(f"  - {f['name']}")
            sys.exit(1)

        feeds_to_test = matching_feeds
    else:
        feeds_to_test = RSS_FEEDS

    print(f"\nTesting {len(feeds_to_test)} feed(s)...\n")

    results = []
    for feed_config in feeds_to_test:
        success = test_feed(feed_config)
        results.append((feed_config['name'], success))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} feeds working")

    if passed == total:
        print("\nAll feeds OK! Pipeline should work properly.")
        return 0
    else:
        print(f"\n{total - passed} feed(s) failed. Check your internet connection.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
