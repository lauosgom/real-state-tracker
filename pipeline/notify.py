"""
Notifications for new listings and price changes.
Uses ntfy.sh (free, no signup) for push notifications
and Gmail SMTP for email digests.
"""

import os
import json
import smtplib
import logging
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")          # e.g. "my-realestate-alerts-abc123"
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")


def _format_listing(listing: dict) -> str:
    price = f"${listing['price']:,.0f}" if listing.get("price") else "N/A"
    beds = listing.get("beds", "?")
    baths = listing.get("baths", "?")
    sqft = f"{listing['sqft']:,}" if listing.get("sqft") else "N/A"
    addr = f"{listing.get('address', '')}, {listing.get('city', '')}, {listing.get('state', '')}"
    return f"{addr} | {price} | {beds}bd/{baths}ba | {sqft} sqft"


def send_push(title: str, message: str, url: str = "") -> None:
    """Send a push notification via ntfy.sh (free, open source)."""
    if not NTFY_TOPIC:
        return
    try:
        data = json.dumps({
            "topic": NTFY_TOPIC,
            "title": title,
            "message": message,
            "click": url,
            "priority": 3,
        }).encode()
        req = urllib.request.Request(
            "https://ntfy.sh",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info(f"Push sent: {title}")
    except Exception as e:
        logger.error(f"Push notification failed: {e}")


def _build_email_html(new_listings: list[dict], price_changes: list[dict]) -> str:
    def listing_rows(items, change_type="new"):
        rows = ""
        for l in items:
            price = f"${l['price']:,.0f}" if l.get("price") else "N/A"
            prev = f"${l['prev_price']:,.0f}" if l.get("prev_price") else ""
            price_display = f"{prev} → {price}" if change_type == "price" and prev else price
            addr = f"{l.get('address', '')}, {l.get('city', '')}, {l.get('state', '')} {l.get('zip', '')}"
            beds = l.get("beds", "?")
            baths = l.get("baths", "?")
            sqft = f"{l['sqft']:,}" if l.get("sqft") else "N/A"
            url = l.get("url", "#")
            source = l.get("source", "").capitalize()
            rows += f"""
            <tr>
              <td style="padding:8px;border-bottom:1px solid #eee">
                <a href="{url}" style="color:#1a73e8;text-decoration:none;font-weight:500">{addr}</a>
                <span style="color:#888;font-size:12px;margin-left:6px">via {source}</span>
              </td>
              <td style="padding:8px;border-bottom:1px solid #eee;white-space:nowrap">{price_display}</td>
              <td style="padding:8px;border-bottom:1px solid #eee">{beds}bd / {baths}ba</td>
              <td style="padding:8px;border-bottom:1px solid #eee">{sqft} sqft</td>
            </tr>"""
        return rows

    sections = ""
    if new_listings:
        sections += f"""
        <h2 style="color:#1a73e8;margin-top:24px">🏠 {len(new_listings)} New Listing(s)</h2>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px">
          <tr style="background:#f8f9fa;color:#555">
            <th style="padding:8px;text-align:left">Address</th>
            <th style="padding:8px;text-align:left">Price</th>
            <th style="padding:8px;text-align:left">Size</th>
            <th style="padding:8px;text-align:left">Sqft</th>
          </tr>
          {listing_rows(new_listings, 'new')}
        </table>"""

    if price_changes:
        sections += f"""
        <h2 style="color:#e8710a;margin-top:24px">💰 {len(price_changes)} Price Change(s)</h2>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px">
          <tr style="background:#f8f9fa;color:#555">
            <th style="padding:8px;text-align:left">Address</th>
            <th style="padding:8px;text-align:left">Price</th>
            <th style="padding:8px;text-align:left">Size</th>
            <th style="padding:8px;text-align:left">Sqft</th>
          </tr>
          {listing_rows(price_changes, 'price')}
        </table>"""

    return f"""
    <html><body style="font-family:sans-serif;max-width:800px;margin:auto;padding:20px;color:#333">
      <h1 style="border-bottom:2px solid #1a73e8;padding-bottom:8px">Real Estate Tracker Update</h1>
      {sections}
      <p style="color:#aaa;font-size:12px;margin-top:32px">Powered by your GCP + Apify tracker</p>
    </body></html>"""


def send_email_digest(new_listings: list[dict], price_changes: list[dict]) -> None:
    """Send an HTML email digest via Gmail."""
    if not all([GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFY_EMAIL]):
        logger.info("Email not configured, skipping.")
        return
    if not new_listings and not price_changes:
        logger.info("Nothing to report, skipping email.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏠 RE Tracker: {len(new_listings)} new, {len(price_changes)} price changes"
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL

    plain = "\n".join([_format_listing(l) for l in new_listings + price_changes])
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(_build_email_html(new_listings, price_changes), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
        logger.info(f"Email sent to {NOTIFY_EMAIL}")
    except Exception as e:
        logger.error(f"Email failed: {e}")


def notify(new_listings: list[dict], price_changes: list[dict]) -> None:
    """Send all notifications."""
    if new_listings:
        count = len(new_listings)
        first = new_listings[0]
        send_push(
            title=f"🏠 {count} new listing{'s' if count > 1 else ''}",
            message=_format_listing(first) + ("..." if count > 1 else ""),
            url=first.get("url", ""),
        )
    if price_changes:
        count = len(price_changes)
        first = price_changes[0]
        send_push(
            title=f"💰 {count} price change{'s' if count > 1 else ''}",
            message=_format_listing(first),
            url=first.get("url", ""),
        )
    send_email_digest(new_listings, price_changes)
