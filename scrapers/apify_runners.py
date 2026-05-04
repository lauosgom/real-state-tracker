"""
Apify actor runners for each real estate source.
Each function triggers an actor and returns raw results.
"""

import os
import time
import logging
from apify_client import ApifyClient

logger = logging.getLogger(__name__)

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
client = ApifyClient(APIFY_TOKEN)

# Max items per source per run — keeps costs within free $5/mo budget
MAX_ITEMS = int(os.environ.get("MAX_ITEMS_PER_SOURCE", 50))


def _run_actor(actor_id: str, run_input: dict) -> list[dict]:
    """Run an Apify actor and return dataset items."""
    logger.info(f"Running actor {actor_id} ...")
    run = client.actor(actor_id).call(run_input=run_input)
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    logger.info(f"  → {len(items)} items from {actor_id}")
    return items


def scrape_zillow(location: str) -> list[dict]:
    return _run_actor(
        "epctex/zillow-scraper",
        {
            "searchTerm": location,
            "listingType": "for_sale",
            "sortBy": "newest",
            "maxItems": MAX_ITEMS,
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        },
    )


def scrape_realtor(location: str) -> list[dict]:
    return _run_actor(
        "epctex/realtor-scraper",
        {
            "searchTerm": location,
            "listingType": "for_sale",
            "sortBy": "newest",
            "maxItems": MAX_ITEMS,
            "proxy": {"useApifyProxy": True},
        },
    )


def scrape_redfin(location: str) -> list[dict]:
    return _run_actor(
        "automation-lab/redfin-scraper",
        {
            "location": location,
            "listingType": "for_sale",
            "maxItems": MAX_ITEMS,
            "proxy": {"useApifyProxy": True},
        },
    )


def scrape_trulia(location: str) -> list[dict]:
    return _run_actor(
        "igolaizola/trulia-scraper",
        {
            "location": location,
            "listingType": "buy",
            "maxItems": MAX_ITEMS,
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        },
    )


def scrape_homes(location: str) -> list[dict]:
    return _run_actor(
        "epctex/homes-com-scraper",
        {
            "search": location,
            "listingType": "for_sale",
            "maxItems": MAX_ITEMS,
            "proxy": {"useApifyProxy": True},
        },
    )


SCRAPERS = {
    "zillow": scrape_zillow,
    "realtor": scrape_realtor,
    "redfin": scrape_redfin,
    "trulia": scrape_trulia,
    "homes": scrape_homes,
}


def run_all(location: str, sources: list[str] | None = None) -> dict[str, list[dict]]:
    """
    Run all (or selected) scrapers for a given location.
    Returns a dict keyed by source name.
    """
    sources = sources or list(SCRAPERS.keys())
    results = {}
    for name in sources:
        try:
            results[name] = SCRAPERS[name](location)
            time.sleep(2)  # polite delay between actors
        except Exception as e:
            logger.error(f"Scraper '{name}' failed: {e}")
            results[name] = []
    return results
