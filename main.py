"""
NHS Inform Scraper — Main Orchestrator

Scrapes all conditions from the NHS Inform A-Z index,
extracts structured content, and stores results in MongoDB.

Usage:
    python main.py                          # Scrape all conditions
    python main.py --limit 5               # Scrape first 5 only (testing)
    python main.py --force                  # Re-scrape already stored conditions
    python main.py --mongo-uri "mongodb://user:pass@host:port"
    python main.py --delay 2.0             # Custom delay between requests
"""

import sys
import time
import logging
import argparse

from config import MONGO_URI, REQUEST_DELAY
from scraper.index_scraper import scrape_index
from scraper.condition_scraper import scrape_condition
from storage.mongo_store import MongoStore


def setup_logging(verbose: bool = False):
    """Configure logging for the scraper."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("cloudscraper").setLevel(logging.WARNING)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape NHS Inform conditions A-Z and store in MongoDB."
    )
    parser.add_argument(
        "--mongo-uri",
        default=MONGO_URI,
        help=f"MongoDB connection URI (default: {MONGO_URI})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY,
        help=f"Seconds between requests (default: {REQUEST_DELAY})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of conditions to scrape (0 = all, default: 0)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-scrape conditions even if already in MongoDB",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger("main")

    # ── 1. Connect to MongoDB ────────────────────────────────────────
    logger.info("Connecting to MongoDB...")
    store = MongoStore(uri=args.mongo_uri)
    if not store.connect():
        logger.error(
            "Could not connect to MongoDB. Is it running? "
            "Use --mongo-uri to specify a custom connection string."
        )
        sys.exit(1)

    # ── 2. Scrape the A-Z index ──────────────────────────────────────
    logger.info("Scraping A-Z index...")
    conditions = scrape_index()
    if not conditions:
        logger.error("No conditions found on the index page. Exiting.")
        store.close()
        sys.exit(1)

    total = len(conditions)
    if args.limit > 0:
        conditions = conditions[: args.limit]
        logger.info(f"Limiting to first {args.limit} of {total} conditions.")
    else:
        logger.info(f"Will scrape all {total} conditions.")

    # ── 3. Scrape each condition ─────────────────────────────────────
    scraped = 0
    skipped = 0
    failed = 0
    batch = []  # accumulate for batch storage

    for i, cond in enumerate(conditions, 1):
        name = cond["name"]
        url = cond["url"]

        # Skip if already stored (unless --force)
        if not args.force and store.condition_exists(url):
            logger.info(f"[{i}/{len(conditions)}] Skipping (exists): {name}")
            skipped += 1
            continue

        # Scrape the condition page
        doc = scrape_condition(name, url)
        if doc:
            batch.append(doc)
            scraped += 1

            # Store in batches of 20 for efficiency
            if len(batch) >= 20:
                store.store_batch(batch)
                batch = []
        else:
            failed += 1

        # Progress log
        logger.info(
            f"[{i}/{len(conditions)}] "
            f"Done: {scraped} | Skipped: {skipped} | Failed: {failed}"
        )

        # Polite delay between requests
        if i < len(conditions):
            time.sleep(args.delay)

    # Store remaining batch
    if batch:
        store.store_batch(batch)

    # ── 4. Summary ───────────────────────────────────────────────────
    stats = store.get_stats()
    logger.info("=" * 60)
    logger.info("SCRAPING COMPLETE")
    logger.info(f"  Scraped:  {scraped}")
    logger.info(f"  Skipped:  {skipped}")
    logger.info(f"  Failed:   {failed}")
    logger.info("-" * 60)
    logger.info("DATABASE STATS:")
    logger.info(f"  Total documents:       {stats['total']}")
    logger.info(f"  With symptoms:         {stats['with_symptoms']}")
    logger.info(f"  With causes:           {stats['with_causes']}")
    logger.info(f"  With warnings:         {stats['with_warnings']}")
    logger.info(f"  With recommendations:  {stats['with_recommendations']}")
    logger.info("=" * 60)

    store.close()


if __name__ == "__main__":
    main()
