# Telegram Archive Feature

## Overview

The archive feature automatically captures listing details (images + description) when successfully contacted, and provides on-demand access via Telegram inline buttons.

## Features

- ✅ **Automatic capture**: Stores listing HTML, images, and description after successful contact
- ✅ **On-demand viewing**: Click button in Telegram to view full archive (images + description)
- ✅ **Clean UI**: Main channel stays clean, archives sent as replies when requested
- ✅ **Fail-safe design**: Archive failures never break contact process
- ✅ **Optional local backup**: Archives can be saved to disk for long-term storage

## How It Works

### Contact Flow

```
1. Listing contacted successfully
   ↓
2. Page HTML captured from browser
   ↓
3. Images and description extracted from HTML
   ↓
4. Archive stored in JSON file (~/.flathunter_telegram_archives.json)
   ↓
5. Telegram notification sent with "📷 View Archive" button
   ↓
6. User clicks button → Bot sends images + description as reply
```

### User Experience

**Normal notification:**
```
✅ Kontaktiert
3-Zimmer-Wohnung zu vermieten

[📷 View Archive]  ← Click to view
```

**After clicking button:**
```
✅ Kontaktiert                    ← Original message
3-Zimmer-Wohnung zu vermieten

  📦 Listing Archiv              ← Reply with archive

  📝 Beschreibung:
  [Full listing description...]

  [11 photos as media group]
```

## Configuration

### Enable the Feature

Add to your `config.yaml`:

```yaml
# Enable archive feature (default: false)
telegram_archive_contacted: true

# Optional: Custom archive path (default: ~/.flathunter_archives)
telegram_archive_path: "~/.flathunter_archives"

# Optional: Archive retention in days (default: 30)
telegram_archive_retention_days: 30
```

### Disable the Feature

Simply set `telegram_archive_contacted: false` or remove the setting entirely (disabled by default).

## Architecture

### Components

1. **archive_manager.py** - Extracts images and descriptions from HTML
2. **telegram_archive_handler.py** - Manages button callbacks and archive storage
3. **sender_telegram.py** - Extended with inline button support
4. **Contact processors** - Capture page HTML after successful contact
5. **hunter.py** - Coordinates archive creation and notifications

### Storage

**Telegram Archives (JSON):**
- **Location**: `~/.flathunter_telegram_archives.json`
- **Format**: `{archive_id: {archive_data, chat_id, created_at}}`
- **Retention**: Automatically cleaned up after `telegram_archive_retention_days`

**Local Backups (Optional):**
- **Location**: `~/.flathunter_archives/` (configurable)
- **Structure**:
  ```
  ~/.flathunter_archives/
  ├── 20251210_145500_1086115793/
  │   ├── metadata.json
  │   ├── description.txt
  │   └── images.json
  └── ...
  ```

### Supported Platforms

- ✅ **Willhaben** - Full support (images + description)
- ✅ **WG-Gesucht** - Full support (images + description)

## Error Handling

### Fallback Logic

The archive feature is designed to **never break the contact process**. If anything fails:

1. Archive extraction fails → Falls back to regular notification
2. Storage fails → Falls back to regular notification
3. Button send fails → Falls back to regular notification
4. Callback handler crashes → Button doesn't work, but everything else continues

### Error Scenarios

| Scenario | Behavior | User Impact |
|----------|----------|-------------|
| Archive disabled | Regular notifications sent | No archive button |
| HTML extraction fails | Warning logged, fallback to regular notification | No archive button |
| Images not found | Partial archive (description only) | Button works, no images |
| Description not found | Partial archive (images only) | Button works, no description |
| Storage full | Error logged, skip local backup | Button works, no local backup |
| Telegram API error | Fallback to regular notification | No archive button |

## Technical Details

### HTML Extraction

**Willhaben:**
- Images: `<img data-testid="image-*">`
- Description: `<div data-testid="ad-description-Objektbeschreibung">`

**WG-Gesucht:**
- Images: Gallery images with specific classes
- Description: Various description div selectors (fallback chain)

### Telegram Integration

**Polling:**
- Uses `getUpdates` API with long polling (5s timeout)
- Lightweight background thread
- Graceful error handling with exponential backoff

**Callback Queries:**
- Format: `archive:<archive_id>`
- Security: Verifies chat_id matches archive owner
- Response: Sends images + description as reply to original message

### Performance

**Impact on Contact Process:**
- Additional time: ~100ms (capturing page_source)
- Memory: Minimal (HTML stored in expose dict temporarily)
- Network: No extra requests (uses existing browser session)

**Archive Creation:**
- Time: ~2-5 seconds (HTML parsing + image URL extraction)
- Storage: ~500KB per archive (metadata + HTML snapshot)
- Local backup: Optional, adds ~1 second if enabled

## Maintenance

### Cleanup

Archives are automatically cleaned up based on `telegram_archive_retention_days`:

- **Telegram JSON**: Old entries removed on startup
- **Local backups**: Directories older than retention period deleted

### Manual Cleanup

```bash
# View all archives
cat ~/.flathunter_telegram_archives.json

# Delete all archives
rm ~/.flathunter_telegram_archives.json
rm -rf ~/.flathunter_archives/

# Delete archives older than X days
find ~/.flathunter_archives/ -type d -mtime +30 -exec rm -rf {} \;
```

## Troubleshooting

### Button doesn't work

1. Check logs for callback handler errors
2. Verify `telegram_archive_contacted: true` in config
3. Check if archive was stored: `cat ~/.flathunter_telegram_archives.json`
4. Restart bot to reinitialize polling thread

### No images in archive

1. Check if images exist on listing page
2. Review logs for extraction warnings
3. HTML structure may have changed (update selectors)

### Archive not created

1. Check if contact was successful (only successful contacts are archived)
2. Verify page HTML was captured (check logs for warnings)
3. Check disk space (local backup may fail if full)

### High memory usage

1. Disable local backups (remove `telegram_archive_path`)
2. Reduce retention period (`telegram_archive_retention_days: 7`)
3. Manually clean up old archives

## Testing

### Test Archive Feature

1. Enable in config: `telegram_archive_contacted: true`
2. Run bot and wait for a contact
3. Check Telegram for button
4. Click button and verify archive is sent
5. Check logs for any warnings

### Test Fallback

1. Break one component (e.g., invalid archive path)
2. Contact should still succeed
3. Regular notification should be sent
4. Warning should appear in logs

## Future Improvements

- [ ] Download actual image files (not just URLs)
- [ ] Support for more platforms
- [ ] Archive search/browse interface
- [ ] PDF export of archives
- [ ] Archive sharing between users

## Credits

Feature designed and implemented for automatic listing archival with fail-safe design principles.
