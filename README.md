# Real Estate Tracker

Multi-source real estate listing tracker. Scrapes Zillow, Realtor.com, Redfin, Trulia, and Homes.com daily, deduplicates across sources, stores everything in BigQuery, and notifies you of new listings and price drops.

**Fully free stack:**
- Apify free plan ($5/mo credits, no card needed)
- BigQuery free tier (10 GB storage, 1 TB queries/mo)
- GitHub Actions free tier (2,000 min/mo scheduler)
- ntfy.sh (free push notifications)
- Gmail SMTP (free email digests)

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/your-username/re-tracker
cd re-tracker
pip install -r requirements.txt
```

### 2. Apify

1. Sign up at [apify.com](https://apify.com) (no credit card)
2. Go to **Settings → Integrations → API token**
3. Copy your token

### 3. GCP / BigQuery

```bash
# Create a project (if you don't have one)
gcloud projects create your-project-id

# Enable BigQuery
gcloud services enable bigquery.googleapis.com --project your-project-id

# Create a service account for GitHub Actions
gcloud iam service-accounts create re-tracker \
  --display-name "Real Estate Tracker" \
  --project your-project-id

# Grant BigQuery access
gcloud projects add-iam-policy-binding your-project-id \
  --member "serviceAccount:re-tracker@your-project-id.iam.gserviceaccount.com" \
  --role "roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding your-project-id \
  --member "serviceAccount:re-tracker@your-project-id.iam.gserviceaccount.com" \
  --role "roles/bigquery.jobUser"

# Download the key (for GitHub Actions)
gcloud iam service-accounts keys create gcp-key.json \
  --iam-account re-tracker@your-project-id.iam.gserviceaccount.com
```

The table and dataset are created automatically on first run.

### 4. Push notifications (optional)

```bash
# Install ntfy on your phone (iOS/Android), then subscribe to your topic
# Pick any unique string as your topic — treat it like a password
NTFY_TOPIC=my-realestate-abc123
```

### 5. Environment variables

```bash
cp .env.example .env
# Fill in your values
```

For local runs:
```bash
export $(cat .env | xargs)
```

### 6. GitHub Actions (scheduler)

Add these as **repository secrets** (Settings → Secrets → Actions):

| Secret | Value |
|---|---|
| `APIFY_TOKEN` | Your Apify API token |
| `GCP_PROJECT_ID` | Your GCP project ID |
| `GCP_SERVICE_ACCOUNT_KEY` | Contents of `gcp-key.json` |
| `NTFY_TOPIC` | Your ntfy topic (optional) |
| `GMAIL_USER` | Gmail address (optional) |
| `GMAIL_APP_PASSWORD` | Gmail app password (optional) |
| `NOTIFY_EMAIL` | Where to send digests (optional) |

The workflow runs automatically every day at 8am UTC.

---

## Usage

```bash
# Scrape all sources for a location
python main.py --location "Austin, TX"

# Scrape specific sources only
python main.py --location "Austin, TX" --sources zillow redfin

# Test without writing to BigQuery
python main.py --location "Austin, TX" --dry-run
```

---

## Querying BigQuery

```sql
-- New listings in the last 24 hours
SELECT address, city, price, beds, baths, sqft, source, url
FROM `your-project.real_estate.listings`
WHERE is_new = TRUE
  AND first_seen_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
ORDER BY price ASC;

-- Price drops this week
SELECT address, city, prev_price, price,
       (prev_price - price) AS drop_amount,
       ROUND(100 * (prev_price - price) / prev_price, 1) AS drop_pct
FROM `your-project.real_estate.listings`
WHERE price_changed = TRUE
  AND price < prev_price
  AND scraped_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY drop_pct DESC;

-- Inventory by city
SELECT city, state, COUNT(*) AS listings, AVG(price) AS avg_price
FROM `your-project.real_estate.listings`
WHERE status = 'FOR_SALE'
GROUP BY city, state
ORDER BY listings DESC;
```

---

## Staying within free limits

- `MAX_ITEMS_PER_SOURCE=50` keeps each Apify run cheap (~$0.20–0.40/run)
- Running all 5 sources daily ≈ $1–2/mo in Apify credits — well within the free $5
- BigQuery: 10 GB free storage, and partitioning by `scraped_at` keeps query costs near zero
- GitHub Actions: one daily run uses ~5 minutes, far under the 2,000 free minutes/mo
