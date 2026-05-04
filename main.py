"""
Real Estate Tracker — main entry point.

Usage:
    # Single location
    python main.py --locations "Austin, TX"

    # Multiple locations
    python main.py --locations "Austin, TX" "Denver, CO" "Nashville, TN"

    # From a config file (one location per line)
    python main.py --locations-file locations.txt

    # Specific sources only
    python main.py --locations "Austin, TX" --sources zillow redfin

    # Dry run (no writes, no notifications)
    python main.py --locations "Austin, TX" "Denver, CO" --dry-run
"""

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("re-tracker")


def scrape_location(location: str, sources: list[str], dry_run: bool) -> tuple[list, list]:
    """Scrape, normalize, store, and return (new_listings, price_changes) for one location."""
    from scrapers.apify_runners import run_all
    from pipeline.normalize import normalize_all
    from pipeline.bigquery_store import upsert_listings

    logger.info(f"── Scraping: {location}")
    raw_by_source = run_all(location, sources)
    logger.info(f"   Raw per source: { {k: len(v) for k, v in raw_by_source.items()} }")

    listings = normalize_all(raw_by_source, search_location=location)
    logger.info(f"   After dedupe: {len(listings)} unique listings")

    if not listings:
        return [], []

    if dry_run:
        for l in listings[:3]:
            logger.info(f"   Sample: {l['address']}, {l['city']}, {l['state']} | ${l.get('price', 'N/A')}")
        return [], []

    return upsert_listings(listings)


def main():
    parser = argparse.ArgumentParser(description="Real Estate multi-source tracker")

    loc_group = parser.add_mutually_exclusive_group(required=True)
    loc_group.add_argument(
        "--locations",
        nargs="+",
        metavar="LOCATION",
        help='One or more locations, e.g. "Austin, TX" "Denver, CO"',
    )
    loc_group.add_argument(
        "--locations-file",
        metavar="FILE",
        help="Path to a text file with one location per line",
    )

    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["zillow", "realtor", "redfin", "trulia", "homes"],
        default=["zillow", "realtor", "redfin", "trulia", "homes"],
        help="Which sources to scrape (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and normalize but don't write to BigQuery or send notifications",
    )
    args = parser.parse_args()

    # Validate required env vars
    required = ["APIFY_TOKEN", "GCP_PROJECT_ID"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        logger.error(f"Missing required env vars: {missing}")
        sys.exit(1)

    # Resolve locations list
    if args.locations_file:
        with open(args.locations_file) as f:
            locations = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    else:
        locations = args.locations

    if not locations:
        logger.error("No locations provided.")
        sys.exit(1)

    logger.info(f"Starting run: {len(locations)} location(s), sources: {args.sources}")
    if args.dry_run:
        logger.info("DRY RUN — no writes or notifications")

    # Accumulate results across all locations for a single combined notification
    all_new: list[dict] = []
    all_price_changes: list[dict] = []

    for location in locations:
        try:
            new, price_changes = scrape_location(location, args.sources, args.dry_run)
            all_new.extend(new)
            all_price_changes.extend(price_changes)
        except Exception as e:
            logger.error(f"Failed to process '{location}': {e}", exc_info=True)

    logger.info(
        f"All locations done — {len(all_new)} new listings, "
        f"{len(all_price_changes)} price changes total"
    )

    if not args.dry_run and (all_new or all_price_changes):
        from pipeline.notify import notify
        notify(all_new, all_price_changes)

    logger.info("Done ✓")


if __name__ == "__main__":
    main()
