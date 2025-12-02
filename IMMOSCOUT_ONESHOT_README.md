# ImmoScout24 Contact Bot - ONESHOT EDITION 🎯

**TRYHARD MODE**: Maximum logging, slow & cautious, human-like behavior

## Quick Start

### 1. First Run - Setup Session

```bash
python test_immoscout_contact.py
```

- Browser will open
- **Manually login** to ImmoScout24
- Bot will detect login and save cookies
- Session saved for future runs!

### 2. Edit Test Script

Open `test_immoscout_contact.py` and edit:

```python
# Replace with your actual listing URL
TEST_LISTING_URL = "https://www.immobilienscout24.de/expose/123456"

# Customize your message
CUSTOM_MESSAGE = """Your message here..."""

# Check boxes you want
QUICK_QUESTIONS = {
    'exactAddress': True,      # Genaue Adresse
    'appointment': True,        # Besichtigungstermin
    'moreInfo': False,          # Mehr Informationen
}
```

### 3. Run Test

```bash
python test_immoscout_contact.py
```

Bot will:
- ✅ Load your saved session (no login needed!)
- ✅ Navigate to listing
- ✅ Fill contact form with human-like typing
- ✅ Check quick question boxes
- ✅ Submit message
- ✅ Verify success

## Features

### 🎭 Anti-Detection
- Stealth mode (hides automation flags)
- Random delays (1.5-4.0s between actions)
- Human-like typing speed
- Smooth scrolling
- Random window sizes

### 📝 Detailed Logging
- Every action logged with timestamps
- Screenshots saved for debugging
- Full error details
- Success/failure tracking

### 🍪 Session Management
- Cookies saved to `~/.immoscout_cookies.json`
- Auto-loads session on next run
- No repeated logins needed

### 📊 Contact Tracking
- Tracks contacted listings in `~/.immoscout_contacted.json`
- Prevents duplicate messages
- Full contact log in `~/.immoscout_contact_log.jsonl`

### 🤖 Captcha Support
- **Manual solving** for testing (bot pauses and waits)
- **Capmonster integration** ready (for production)

## Files Created

| File | Purpose |
|------|---------|
| `immoscout_contact_bot.py` | Main bot class (standalone, no dependencies) |
| `test_immoscout_contact.py` | Test script for single listings |
| `~/.immoscout_cookies.json` | Saved session cookies |
| `~/.immoscout_contacted.json` | Tracked contacted listings |
| `~/.immoscout_contact_log.jsonl` | Detailed contact log |

## Next Steps

1. **Test with real listing** - Get a URL, edit test script, run it!
2. **Refine selectors** - If form detection fails, we'll adjust
3. **Add config.yaml integration** - For auto-contact in main loop
4. **Create processor** - Like `wg_gesucht_contact_processor.py`

## Troubleshooting

### "Contact request block not found"
- Check if listing requires login
- Check if you need to click "Kontakt" button first
- Send screenshot to debug

### "Already contacted this listing"
- Bot prevents duplicates
- Delete `~/.immoscout_contacted.json` to reset

### Captcha appears
- Bot will pause and wait for manual solve
- Solve it in the browser
- Bot continues automatically

### Session expired
- Delete `~/.immoscout_cookies.json`
- Run test script again
- Login manually

## Settings

Edit bot settings in `test_immoscout_contact.py`:

```python
HEADLESS = False    # True = background, False = visible browser
DELAY_MIN = 1.5     # Minimum delay (seconds)
DELAY_MAX = 4.0     # Maximum delay (seconds)
```

**Recommended for testing**: `HEADLESS=False` (watch it work!)
**Recommended for production**: `HEADLESS=True` (faster, less resources)

## Log Levels

All logs go to console with timestamps:

- `DEBUG` - Every action (typing, scrolling, waiting)
- `INFO` - Important milestones (form found, message sent)
- `WARNING` - Potential issues (captcha, no cookies)
- `ERROR` - Failures (form not found, timeout)

---

**Ready to one-shot those f***ers! 🚀**
