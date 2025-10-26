# Blacklist Online Listings Tool

## Purpose

This tool prevents accidentally spamming contacts when database files get cleaned up during updates. It fetches all currently online Willhaben listings from your configured search URLs and marks them as already seen/contacted in all tracking systems.

## What It Does

The script marks listings in **three tracking systems**:

1. **`processed_ids.db`** - Main SQLite database (processed table)
2. **`processed_ids.db`** - Title tracking for cross-platform duplicates (contacted_titles table)
3. **`~/.willhaben_contacted.json`** - Willhaben-specific contacted cache

## Usage

### Quick Start (Recommended)

```bash
# Dry run to see what would be blacklisted
./blacklist-online.sh --dry-run

# Actually blacklist the listings
./blacklist-online.sh
```

### Manual Docker Usage

```bash
# If container is running
docker-compose exec app python blacklist_online_listings.py --dry-run

# If container is not running
docker-compose run --rm app python blacklist_online_listings.py --dry-run
```

### Local Execution (if you have dependencies installed)

```bash
# Dry run
python blacklist_online_listings.py --dry-run

# Execute
python blacklist_online_listings.py
```

## When To Use This

Run this tool when:

- **Before updating** - Prevent re-contacting listings if DB files are affected
- **After DB cleanup** - If you accidentally deleted or reset the database files
- **Initial setup** - When first configuring Flathunter to avoid contacting old listings
- **Migration** - When moving to a new server or environment

## What Gets Blacklisted

The script:

1. Reads Willhaben URLs from `config.yaml`
2. Crawls the **first page** of each search URL
3. Extracts all current listings (typically 20-30 per URL)
4. Marks each listing in all three tracking systems

## Output Example

```
============================================================
Blacklist Online Listings Tool
============================================================

Loading configuration from /usr/src/app/config.yaml
Found 1 Willhaben URL(s) in config:
  - https://www.willhaben.at/iad/immobilien/mietwohnungen/...

Fetching listings from configured URLs...

Crawling: https://www.willhaben.at/iad/immobilien/mietwohnungen/...
  Found 25 listings

============================================================
Total listings to blacklist: 25
============================================================

[1/25] ID: 123456789
  Title: 2-Zimmer Wohnung in Wien 6. Bezirk...
  URL: https://www.willhaben.at/iad/immobilien/...
  → NEW - will be blacklisted

[2/25] ID: 987654321
  Title: Schöne 3-Zimmer Wohnung...
  URL: https://www.willhaben.at/iad/immobilien/...
  ✓ Already in processed_ids
  ✓ Already in contacted_titles

...

============================================================
SUMMARY
============================================================
Total listings found:           25
Already in processed_ids:       10
Already in contacted_titles:    8
Already in willhaben cache:     7
Newly blacklisted:              5

✓ All listings have been blacklisted successfully!
============================================================
```

## Options

### --dry-run

Shows what would be blacklisted without making any changes. **Always recommended to run first** to verify the listings before actually blacklisting them.

```bash
./blacklist-online.sh --dry-run
```

## Safety

- **Non-destructive** - Only adds listings to tracking systems, never removes
- **Idempotent** - Safe to run multiple times (shows "already blacklisted")
- **Dry-run mode** - Preview changes before committing

## Files Modified

When run without `--dry-run`, the script modifies:

- `processed_ids.db` - Adds listing IDs to `processed` and `contacted_titles` tables
- `~/.willhaben_contacted.json` - Adds listing IDs to Willhaben cache

## Technical Details

The script uses the existing Flathunter infrastructure:

- **Crawler**: Uses `flathunter.crawler.willhaben.Willhaben` to fetch listings
- **Config**: Reads from `config.yaml` (same as main Flathunter)
- **Tracking**: Uses `flathunter.idmaintainer.IdMaintainer` for database operations

## Troubleshooting

### "No Willhaben URLs found in config"

Make sure your `config.yaml` contains at least one Willhaben URL in the `urls` section:

```yaml
urls:
  - https://www.willhaben.at/iad/immobilien/mietwohnungen/...
```

### "ModuleNotFoundError: No module named 'dotenv'"

You need to run the script inside the Docker container using the wrapper script:

```bash
./blacklist-online.sh
```

### "docker-compose is not installed"

Install Docker and docker-compose, or run the script directly if you have Python dependencies installed locally.

## Source Files

- `blacklist_online_listings.py` - Main Python script
- `blacklist-online.sh` - Docker wrapper script (recommended)
- `BLACKLIST_TOOL.md` - This documentation
