#!/usr/bin/env python3
"""
Blacklist Online Listings Script

This script fetches all currently online Willhaben listings from the configured URLs
and marks them as already seen/contacted in all tracking systems. This prevents
accidentally spamming contacts if the database files get cleaned up during updates.

Usage:
    python blacklist_online_listings.py [--dry-run]

Options:
    --dry-run    Show what would be blacklisted without actually doing it
"""

import sys
import os
import argparse
from pathlib import Path

# Add flathunter directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flathunter.config import Config
from flathunter.idmaintainer import IdMaintainer
from flathunter.crawler.willhaben import Willhaben
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_willhaben_contacted_cache():
    """Load the Willhaben-specific contacted listings cache"""
    contacted_file = Path.home() / '.willhaben_contacted.json'
    if contacted_file.exists():
        with open(contacted_file, 'r') as f:
            return set(json.load(f))
    return set()


def save_willhaben_contacted_cache(contacted_listings):
    """Save the Willhaben-specific contacted listings cache"""
    contacted_file = Path.home() / '.willhaben_contacted.json'
    with open(contacted_file, 'w') as f:
        json.dump(list(contacted_listings), f, indent=2)


def blacklist_online_listings(dry_run=False):
    """
    Fetch all currently online listings and mark them as already seen/contacted

    Args:
        dry_run: If True, only show what would be done without making changes
    """
    # Load configuration
    config_path = Path(__file__).parent / 'config.yaml'
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return 1

    logger.info(f"Loading configuration from {config_path}")
    config = Config(str(config_path))

    # Get Willhaben URLs from config
    willhaben_urls = [url for url in config.urls() if 'willhaben.at' in url]

    if not willhaben_urls:
        logger.warning("No Willhaben URLs found in config!")
        return 0

    logger.info(f"Found {len(willhaben_urls)} Willhaben URL(s) in config:")
    for url in willhaben_urls:
        logger.info(f"  - {url}")

    # Initialize tracking systems
    id_watch = IdMaintainer(f'{config.database_location()}/processed_ids.db')
    willhaben_cache = load_willhaben_contacted_cache()

    # Initialize Willhaben crawler
    crawler = Willhaben(config)

    # Collect all listings
    all_listings = []
    logger.info("\nFetching listings from configured URLs...")

    for url in willhaben_urls:
        logger.info(f"\nCrawling: {url}")
        try:
            # Crawl the URL (just first page to get current listings)
            listings = crawler.get_results(url, max_pages=1)
            logger.info(f"  Found {len(listings)} listings")
            all_listings.extend(listings)
        except Exception as e:
            logger.error(f"  Error crawling URL: {e}")
            continue

    if not all_listings:
        logger.warning("\nNo listings found to blacklist!")
        return 0

    logger.info(f"\n{'='*60}")
    logger.info(f"Total listings to blacklist: {len(all_listings)}")
    logger.info(f"{'='*60}\n")

    # Statistics
    stats = {
        'total': len(all_listings),
        'already_processed': 0,
        'already_contacted_title': 0,
        'already_in_cache': 0,
        'newly_blacklisted': 0
    }

    # Process each listing
    for i, listing in enumerate(all_listings, 1):
        listing_id = listing.get('id')
        listing_title = listing.get('title', 'N/A')
        listing_url = listing.get('url', 'N/A')

        logger.info(f"[{i}/{len(all_listings)}] ID: {listing_id}")
        logger.info(f"  Title: {listing_title[:60]}...")
        logger.info(f"  URL: {listing_url}")

        # Check current status
        already_processed = id_watch.is_processed(listing_id)
        already_contacted = id_watch.is_title_contacted(listing_title)
        already_cached = str(listing_id) in willhaben_cache

        if already_processed:
            logger.info(f"  ✓ Already in processed_ids")
            stats['already_processed'] += 1

        if already_contacted:
            logger.info(f"  ✓ Already in contacted_titles")
            stats['already_contacted_title'] += 1

        if already_cached:
            logger.info(f"  ✓ Already in willhaben cache")
            stats['already_in_cache'] += 1

        # Check if this is new to all systems
        is_new = not (already_processed or already_contacted or already_cached)

        if is_new:
            stats['newly_blacklisted'] += 1
            logger.info(f"  → NEW - will be blacklisted")

            if not dry_run:
                # Mark in all tracking systems
                id_watch.mark_processed(listing_id)
                id_watch.mark_title_contacted(listing)
                willhaben_cache.add(str(listing_id))

        logger.info("")  # Blank line for readability

    # Save the updated cache
    if not dry_run:
        save_willhaben_contacted_cache(willhaben_cache)
        logger.info("✓ Updated Willhaben contacted cache")

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Total listings found:           {stats['total']}")
    logger.info(f"Already in processed_ids:       {stats['already_processed']}")
    logger.info(f"Already in contacted_titles:    {stats['already_contacted_title']}")
    logger.info(f"Already in willhaben cache:     {stats['already_in_cache']}")
    logger.info(f"Newly blacklisted:              {stats['newly_blacklisted']}")

    if dry_run:
        logger.info("\n⚠ DRY RUN - No changes were made")
        logger.info("Run without --dry-run to actually blacklist these listings")
    else:
        logger.info("\n✓ All listings have been blacklisted successfully!")

    logger.info(f"{'='*60}\n")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Blacklist all currently online Willhaben listings'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )

    args = parser.parse_args()

    try:
        return blacklist_online_listings(dry_run=args.dry_run)
    except KeyboardInterrupt:
        logger.info("\n\nInterrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\nUnexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
