"""
Normalize raw listings from each Apify actor into a unified schema.
Every source has different field names — this maps them all to one shape.
"""

import hashlib
import re
from datetime import datetime, timezone


def _clean_price(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^\d.]", "", str(val))
    return float(cleaned) if cleaned else None


def _clean_int(val) -> int | None:
    try:
        return int(float(str(val).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _address_key(address: str) -> str:
    """Create a consistent fingerprint for deduplication."""
    normalized = re.sub(r"[^a-z0-9]", "", address.lower())
    return hashlib.md5(normalized.encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- per-source normalizers ----------

def _from_zillow(raw: dict) -> dict:
    addr = raw.get("address", {})
    full_address = addr.get("streetAddress", "") if isinstance(addr, dict) else str(addr)
    city = addr.get("city", "") if isinstance(addr, dict) else ""
    state = addr.get("state", "") if isinstance(addr, dict) else ""
    zipcode = addr.get("zipcode", "") if isinstance(addr, dict) else ""
    return {
        "source": "zillow",
        "source_id": str(raw.get("zpid", "")),
        "url": raw.get("detailUrl") or raw.get("hdpUrl", ""),
        "address": full_address,
        "city": city,
        "state": state,
        "zip": zipcode,
        "price": _clean_price(raw.get("price") or raw.get("unformattedPrice")),
        "beds": _clean_int(raw.get("beds") or raw.get("bedrooms")),
        "baths": _clean_float(raw.get("baths") or raw.get("bathrooms")),
        "sqft": _clean_int(raw.get("livingArea") or raw.get("area")),
        "lot_sqft": _clean_int(raw.get("lotAreaValue")),
        "property_type": raw.get("homeType", ""),
        "year_built": _clean_int(raw.get("yearBuilt")),
        "days_on_market": _clean_int(raw.get("daysOnZillow")),
        "lat": raw.get("latitude"),
        "lng": raw.get("longitude"),
        "description": raw.get("description", ""),
        "hoa_fee": _clean_price(raw.get("hoaFee")),
        "tax_annual": _clean_price(raw.get("taxAnnualAmount")),
        "zestimate": _clean_price(raw.get("zestimate")),
        "price_per_sqft": _clean_price(raw.get("pricePerSquareFoot")),
        "status": raw.get("homeStatus", "FOR_SALE"),
    }


def _from_realtor(raw: dict) -> dict:
    loc = raw.get("location", {}) or {}
    addr = loc.get("address", {}) or {}
    return {
        "source": "realtor",
        "source_id": str(raw.get("property_id") or raw.get("listing_id", "")),
        "url": raw.get("permalink") or raw.get("url", ""),
        "address": addr.get("line", ""),
        "city": addr.get("city", ""),
        "state": addr.get("state_code", ""),
        "zip": addr.get("postal_code", ""),
        "price": _clean_price(raw.get("list_price") or raw.get("price")),
        "beds": _clean_int(raw.get("description", {}).get("beds") or raw.get("beds")),
        "baths": _clean_float(raw.get("description", {}).get("baths_consolidated") or raw.get("baths")),
        "sqft": _clean_int(raw.get("description", {}).get("sqft") or raw.get("sqft")),
        "lot_sqft": _clean_int(raw.get("description", {}).get("lot_sqft")),
        "property_type": raw.get("description", {}).get("type", ""),
        "year_built": _clean_int(raw.get("description", {}).get("year_built")),
        "days_on_market": _clean_int(raw.get("list_date_delta") or raw.get("days_on_market")),
        "lat": raw.get("location", {}).get("coordinate", {}).get("lat"),
        "lng": raw.get("location", {}).get("coordinate", {}).get("lon"),
        "description": raw.get("description", {}).get("text", ""),
        "hoa_fee": _clean_price(raw.get("hoa", {}).get("fee")),
        "tax_annual": None,
        "zestimate": None,
        "price_per_sqft": None,
        "status": "FOR_SALE",
    }


def _from_redfin(raw: dict) -> dict:
    return {
        "source": "redfin",
        "source_id": str(raw.get("mlsId") or raw.get("listingId", "")),
        "url": raw.get("url", ""),
        "address": raw.get("streetAddress") or raw.get("address", ""),
        "city": raw.get("city", ""),
        "state": raw.get("state", ""),
        "zip": raw.get("zip") or raw.get("zipCode", ""),
        "price": _clean_price(raw.get("price") or raw.get("listPrice")),
        "beds": _clean_int(raw.get("beds") or raw.get("bedrooms")),
        "baths": _clean_float(raw.get("baths") or raw.get("bathrooms")),
        "sqft": _clean_int(raw.get("sqFt") or raw.get("sqft")),
        "lot_sqft": _clean_int(raw.get("lotSize")),
        "property_type": raw.get("propertyType", ""),
        "year_built": _clean_int(raw.get("yearBuilt")),
        "days_on_market": _clean_int(raw.get("daysOnMarket")),
        "lat": raw.get("latitude") or raw.get("lat"),
        "lng": raw.get("longitude") or raw.get("lng"),
        "description": raw.get("remarks") or raw.get("description", ""),
        "hoa_fee": _clean_price(raw.get("hoa")),
        "tax_annual": _clean_price(raw.get("taxesDue")),
        "zestimate": None,
        "price_per_sqft": None,
        "status": "FOR_SALE",
    }


def _from_trulia(raw: dict) -> dict:
    return {
        "source": "trulia",
        "source_id": str(raw.get("id") or raw.get("listingId", "")),
        "url": raw.get("url", ""),
        "address": raw.get("address") or raw.get("streetAddress", ""),
        "city": raw.get("city", ""),
        "state": raw.get("state", ""),
        "zip": raw.get("zipCode") or raw.get("zip", ""),
        "price": _clean_price(raw.get("price") or raw.get("listingPrice")),
        "beds": _clean_int(raw.get("bedrooms") or raw.get("beds")),
        "baths": _clean_float(raw.get("bathrooms") or raw.get("baths")),
        "sqft": _clean_int(raw.get("floorSpace") or raw.get("sqft")),
        "lot_sqft": _clean_int(raw.get("lotSize")),
        "property_type": raw.get("propertyType", ""),
        "year_built": _clean_int(raw.get("yearBuilt")),
        "days_on_market": _clean_int(raw.get("daysOnTrulia") or raw.get("daysOnMarket")),
        "lat": raw.get("latitude"),
        "lng": raw.get("longitude"),
        "description": raw.get("description", ""),
        "hoa_fee": _clean_price(raw.get("hoaMonthly")),
        "tax_annual": _clean_price(raw.get("annualTax")),
        "zestimate": None,
        "price_per_sqft": None,
        "status": "FOR_SALE",
    }


def _from_homes(raw: dict) -> dict:
    return {
        "source": "homes",
        "source_id": str(raw.get("id") or raw.get("listingId", "")),
        "url": raw.get("listingUrl") or raw.get("url", ""),
        "address": raw.get("address", ""),
        "city": raw.get("city", ""),
        "state": raw.get("state", ""),
        "zip": raw.get("zipCode") or raw.get("zip", ""),
        "price": _clean_price(raw.get("price") or raw.get("listPrice")),
        "beds": _clean_int(raw.get("beds") or raw.get("bedrooms")),
        "baths": _clean_float(raw.get("baths") or raw.get("bathrooms")),
        "sqft": _clean_int(raw.get("area") or raw.get("sqft")),
        "lot_sqft": _clean_int(raw.get("lotSize")),
        "property_type": raw.get("propertyType", ""),
        "year_built": _clean_int(raw.get("yearBuilt")),
        "days_on_market": _clean_int(raw.get("daysOnMarket")),
        "lat": raw.get("latitude"),
        "lng": raw.get("longitude"),
        "description": raw.get("description", ""),
        "hoa_fee": _clean_price(raw.get("hoa")),
        "tax_annual": _clean_price(raw.get("estimateAnnualTax")),
        "zestimate": None,
        "price_per_sqft": None,
        "status": "FOR_SALE",
    }


NORMALIZERS = {
    "zillow": _from_zillow,
    "realtor": _from_realtor,
    "redfin": _from_redfin,
    "trulia": _from_trulia,
    "homes": _from_homes,
}


def _clean_float(val) -> float | None:
    try:
        return float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return None


def normalize_all(
    raw_by_source: dict[str, list[dict]],
    search_location: str = "",
) -> list[dict]:
    """
    Normalize all raw results, deduplicate by address fingerprint,
    and add metadata fields for BigQuery.

    search_location is the query string used (e.g. "Austin, TX") — stored
    as a field so you can filter/group by location in BigQuery.
    """
    seen_keys: set[str] = set()
    listings: list[dict] = []
    scraped_at = _now()

    for source, raws in raw_by_source.items():
        normalizer = NORMALIZERS.get(source)
        if not normalizer:
            continue
        for raw in raws:
            try:
                listing = normalizer(raw)
            except Exception:
                continue

            full_address = f"{listing['address']} {listing['city']} {listing['state']} {listing['zip']}"
            key = _address_key(full_address)

            if key in seen_keys:
                # Duplicate — already seen from another source
                continue
            seen_keys.add(key)

            listing["address_key"] = key
            listing["scraped_at"] = scraped_at
            listing["search_location"] = search_location
            listings.append(listing)

    return listings
