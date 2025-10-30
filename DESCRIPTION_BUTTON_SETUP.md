# Telegram Description Button Feature

## Overview

This feature adds an inline "📄 Beschreibung anzeigen" button to every listing notification in Telegram. When clicked, it retrieves and displays the full listing description from the database.

**Key benefits:**
- ✅ No chat clutter - descriptions only shown on demand
- ✅ Works even after listings are deleted from willhaben
- ✅ Automatically saves descriptions for contacted listings
- ✅ Zero extra page loads (extracts during contact flow)

## How It Works

1. **Listing Found** → Telegram notification sent with "📄 Beschreibung anzeigen" button
2. **Auto-Contact Triggered** → Browser opens, contact form submitted
3. **Contact Succeeds** → Description extracted (browser still open, no extra load!)
4. **Description Saved** → Stored in database (merged into existing expose record)
5. **Button Clicked** → Callback handler queries database and sends description

## Setup Instructions

### Option 1: Run Manually (Quick Test)

```bash
cd /home/user/Flatjaga
python3 scripts/run_callback_handler.py
```

Press `Ctrl+C` to stop.

### Option 2: Run as Systemd Service (Recommended)

This will auto-start the callback handler on boot and restart it if it crashes.

1. **Copy service file to systemd directory:**
   ```bash
   sudo cp flathunter-callback-handler.service /etc/systemd/system/
   ```

2. **Reload systemd and enable the service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable flathunter-callback-handler
   ```

3. **Start the service:**
   ```bash
   sudo systemctl start flathunter-callback-handler
   ```

4. **Check status:**
   ```bash
   sudo systemctl status flathunter-callback-handler
   ```

5. **View logs:**
   ```bash
   # Real-time logs
   sudo journalctl -u flathunter-callback-handler -f

   # Last 100 lines
   sudo journalctl -u flathunter-callback-handler -n 100
   ```

### Managing the Service

```bash
# Stop the service
sudo systemctl stop flathunter-callback-handler

# Restart the service
sudo systemctl restart flathunter-callback-handler

# Disable auto-start
sudo systemctl disable flathunter-callback-handler
```

## Usage

1. **Receive listing notification** in Telegram with the button
2. **Click "📄 Beschreibung anzeigen"**
3. **Get description** as a reply (if available)

**Notes:**
- Only contacted listings have descriptions saved
- Button works for all listings, but shows "not available" message if description wasn't extracted
- Old listings (before this feature) won't have descriptions

## Architecture

### New Files

- `flathunter/telegram_callback_handler.py` - Polls Telegram for button presses
- `scripts/run_callback_handler.py` - Startup script
- `flathunter-callback-handler.service` - Systemd service file

### Modified Files

- `flathunter/willhaben_contact_bot.py` - Added `extract_description()` method
- `flathunter/willhaben_contact_processor.py` - Extracts & saves description after contact
- `flathunter/idmaintainer.py` - Added `update_expose_description()` and `get_expose_by_id()`
- `flathunter/notifiers/sender_telegram.py` - Added inline keyboard buttons

### Database

Descriptions are stored in the existing `exposes` table as part of the JSON `details` BLOB:

```json
{
  "id": 12345,
  "title": "3-Zimmer Wohnung",
  "price": "€850/month",
  ...
  "description": "Full description text here..."
}
```

No schema changes required!

## Troubleshooting

### Button doesn't respond

1. Check if callback handler is running:
   ```bash
   sudo systemctl status flathunter-callback-handler
   ```

2. Check logs for errors:
   ```bash
   sudo journalctl -u flathunter-callback-handler -n 50
   ```

### "Description not available" message

This is normal for:
- Listings that weren't contacted yet (description only saved after contact)
- Old listings (before this feature was implemented)
- Listings where description extraction failed

### Service won't start

1. Check service file permissions:
   ```bash
   ls -l /etc/systemd/system/flathunter-callback-handler.service
   ```

2. Check Python path:
   ```bash
   which python3
   ```

3. Test manually first:
   ```bash
   cd /home/user/Flatjaga
   python3 scripts/run_callback_handler.py
   ```

## Performance Impact

- **Minimal** - Description extraction adds ~0.1-0.5s after successful contact
- **Non-blocking** - Doesn't slow down contact flow
- **Smart** - Uses already-open browser, no extra page loads
- **Storage** - Only contacted listings (~10% of all listings) get descriptions saved

## Future Enhancements

Possible improvements:
- Add "Show Images" button
- Add "Show Full Details" button with all fields
- Export description to PDF
- Search descriptions with keywords

---

**Questions?** Check the logs or test manually with `python3 scripts/run_callback_handler.py`
