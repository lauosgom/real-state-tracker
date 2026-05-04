"""
BigQuery storage layer.
- Creates the dataset + table if they don't exist
- Upserts listings (detects new, price changes, removals)
- Returns newly added listings for notifications
"""

import os
import logging
from datetime import datetime, timezone

from google.cloud import bigquery
from google.api_core.exceptions import NotFound

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
DATASET_ID = os.environ.get("BQ_DATASET", "real_estate")
TABLE_ID = os.environ.get("BQ_TABLE", "listings")
FULL_TABLE = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

# ---------- Schema ----------

SCHEMA = [
    bigquery.SchemaField("address_key",    "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("source",         "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("source_id",      "STRING"),
    bigquery.SchemaField("url",            "STRING"),
    bigquery.SchemaField("address",        "STRING"),
    bigquery.SchemaField("city",           "STRING"),
    bigquery.SchemaField("state",          "STRING"),
    bigquery.SchemaField("zip",            "STRING"),
    bigquery.SchemaField("price",          "FLOAT"),
    bigquery.SchemaField("beds",           "INTEGER"),
    bigquery.SchemaField("baths",          "FLOAT"),
    bigquery.SchemaField("sqft",           "INTEGER"),
    bigquery.SchemaField("lot_sqft",       "INTEGER"),
    bigquery.SchemaField("property_type",  "STRING"),
    bigquery.SchemaField("year_built",     "INTEGER"),
    bigquery.SchemaField("days_on_market", "INTEGER"),
    bigquery.SchemaField("lat",            "FLOAT"),
    bigquery.SchemaField("lng",            "FLOAT"),
    bigquery.SchemaField("description",    "STRING"),
    bigquery.SchemaField("hoa_fee",        "FLOAT"),
    bigquery.SchemaField("tax_annual",     "FLOAT"),
    bigquery.SchemaField("zestimate",      "FLOAT"),
    bigquery.SchemaField("price_per_sqft", "FLOAT"),
    bigquery.SchemaField("status",          "STRING"),
    bigquery.SchemaField("search_location", "STRING"),   # the query used, e.g. "Austin, TX"
    bigquery.SchemaField("scraped_at",     "TIMESTAMP"),
    # Change tracking
    bigquery.SchemaField("first_seen_at",  "TIMESTAMP"),
    bigquery.SchemaField("last_seen_at",   "TIMESTAMP"),
    bigquery.SchemaField("prev_price",     "FLOAT"),
    bigquery.SchemaField("is_new",         "BOOL"),
    bigquery.SchemaField("price_changed",  "BOOL"),
]


def get_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT_ID)


def ensure_table(client: bigquery.Client) -> None:
    """Create dataset and table if they don't exist."""
    # Dataset
    dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_ID}")
    dataset_ref.location = "US"
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        client.create_dataset(dataset_ref)
        logger.info(f"Created dataset {DATASET_ID}")

    # Table
    table_ref = client.dataset(DATASET_ID).table(TABLE_ID)
    try:
        client.get_table(table_ref)
    except NotFound:
        table = bigquery.Table(table_ref, schema=SCHEMA)
        # Partition by scraped_at for cost-efficient queries
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="scraped_at",
        )
        table.clustering_fields = ["state", "city", "status"]
        client.create_table(table)
        logger.info(f"Created table {FULL_TABLE}")


def get_existing(client: bigquery.Client, address_keys: list[str]) -> dict[str, dict]:
    """
    Fetch existing rows for the given address keys.
    Returns dict keyed by address_key.
    """
    if not address_keys:
        return {}

    keys_str = ", ".join(f"'{k}'" for k in address_keys)
    query = f"""
        SELECT address_key, price, first_seen_at, last_seen_at
        FROM `{FULL_TABLE}`
        WHERE address_key IN ({keys_str})
        QUALIFY ROW_NUMBER() OVER (PARTITION BY address_key ORDER BY scraped_at DESC) = 1
    """
    try:
        rows = client.query(query).result()
        return {row["address_key"]: dict(row) for row in rows}
    except NotFound:
        return {}


def upsert_listings(listings: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Insert all listings into BigQuery, flagging new ones and price changes.
    Returns (new_listings, price_changed_listings).
    """
    if not listings:
        return [], []

    client = get_client()
    ensure_table(client)

    # Check which ones we've seen before
    keys = [l["address_key"] for l in listings]
    existing = get_existing(client, keys)

    now = datetime.now(timezone.utc).isoformat()
    rows_to_insert = []
    new_listings = []
    price_changes = []

    for listing in listings:
        key = listing["address_key"]
        prev = existing.get(key)

        if prev is None:
            # Brand new listing
            listing["is_new"] = True
            listing["price_changed"] = False
            listing["first_seen_at"] = now
            listing["last_seen_at"] = now
            listing["prev_price"] = None
            new_listings.append(listing)
        else:
            listing["is_new"] = False
            listing["first_seen_at"] = prev["first_seen_at"]
            listing["last_seen_at"] = now
            prev_price = float(prev["price"]) if prev["price"] else None
            curr_price = listing.get("price")
            if prev_price and curr_price and abs(curr_price - prev_price) > 100:
                listing["price_changed"] = True
                listing["prev_price"] = prev_price
                price_changes.append(listing)
            else:
                listing["price_changed"] = False
                listing["prev_price"] = prev_price

        rows_to_insert.append(listing)

    # Stream insert into BigQuery
    table_ref = client.dataset(DATASET_ID).table(TABLE_ID)
    errors = client.insert_rows_json(table_ref, rows_to_insert)
    if errors:
        logger.error(f"BigQuery insert errors: {errors}")
    else:
        logger.info(f"Inserted {len(rows_to_insert)} rows → {len(new_listings)} new, {len(price_changes)} price changes")

    return new_listings, price_changes


def query_new_since(hours: int = 24) -> list[dict]:
    """Fetch all listings first seen in the last N hours — useful for reporting."""
    client = get_client()
    query = f"""
        SELECT *
        FROM `{FULL_TABLE}`
        WHERE is_new = TRUE
          AND first_seen_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        ORDER BY first_seen_at DESC
    """
    rows = client.query(query).result()
    return [dict(row) for row in rows]
