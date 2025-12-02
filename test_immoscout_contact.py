#!/usr/bin/env python3
"""
Test script for ImmoScout24 contact bot
Quick & easy testing with a single listing URL
"""

import logging
from immoscout_contact_bot import ImmoscoutContactBot

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION - EDIT THESE
# ============================================================================

# Replace with your actual ImmoScout24 listing URL
TEST_LISTING_URL = "https://www.immobilienscout24.de/expose/XXXXXX"

# Custom message (optional - uses default if None)
CUSTOM_MESSAGE = """Guten Tag,

ich habe großes Interesse an der Wohnung und würde mich sehr über einen Besichtigungstermin freuen.

Ich bin auf der Suche nach einer langfristigen Mietwohnung in Wien und Ihre Wohnung entspricht genau meinen Vorstellungen.

Mit freundlichen Grüßen
Daniel Gruber"""

# Quick questions to check (optional)
QUICK_QUESTIONS = {
    'exactAddress': True,      # Genaue Adresse
    'appointment': True,        # Besichtigungstermin
    'moreInfo': False,          # Mehr Informationen
}

# Bot settings
HEADLESS = False  # Set to True to run in background (no visible browser)
DELAY_MIN = 0.8   # Minimum delay in seconds (FAST & CONFIDENT - like sneaker bots)
DELAY_MAX = 2.5   # Maximum delay in seconds (STILL HUMAN-LIKE)

# ============================================================================
# MAIN TEST
# ============================================================================

def main():
    logger.info("=" * 80)
    logger.info("🧪 IMMOSCOUT24 CONTACT BOT - TEST SCRIPT")
    logger.info("=" * 80)

    # Validate URL
    if "XXXXXX" in TEST_LISTING_URL or not TEST_LISTING_URL.startswith("https://www.immobilienscout24"):
        logger.error("❌ ERROR: Please set TEST_LISTING_URL to a real ImmoScout24 listing!")
        logger.info("   Edit this file and replace TEST_LISTING_URL with your listing URL")
        return

    # Create bot
    logger.info(f"🤖 Creating bot...")
    logger.info(f"   Headless: {HEADLESS}")
    logger.info(f"   Delays: {DELAY_MIN}-{DELAY_MAX}s")

    bot = ImmoscoutContactBot(
        headless=HEADLESS,
        delay_min=DELAY_MIN,
        delay_max=DELAY_MAX,
        message_template=CUSTOM_MESSAGE
    )

    try:
        # Start browser
        logger.info("🚀 Starting browser...")
        if not bot.start():
            logger.error("❌ Failed to start browser")
            return

        # Try to load cookies
        logger.info("🍪 Loading cookies...")
        if not bot.load_cookies():
            logger.warning("⚠️  No cookies found - need to login first")
            logger.info("")
            logger.info("=" * 80)
            logger.info("📋 FIRST RUN - LOGIN REQUIRED")
            logger.info("=" * 80)
            logger.info("1. Browser will open")
            logger.info("2. Login to your ImmoScout24 account")
            logger.info("3. Bot will detect login and save cookies")
            logger.info("4. Next run will use saved cookies (no login needed)")
            logger.info("=" * 80)
            logger.info("")

            # Wait for manual login
            if not bot.wait_for_manual_login(timeout=300):
                logger.error("❌ Login failed or timed out")
                return

            # Save cookies for next time
            logger.info("💾 Saving cookies for future runs...")
            bot.save_cookies()

        logger.info("✅ Session ready!")
        logger.info("")

        # Contact the listing
        logger.info("=" * 80)
        logger.info("🎯 CONTACTING LISTING")
        logger.info("=" * 80)
        logger.info(f"URL: {TEST_LISTING_URL}")
        logger.info(f"Message: {len(CUSTOM_MESSAGE)} characters")
        logger.info(f"Quick questions: {QUICK_QUESTIONS}")
        logger.info("=" * 80)
        logger.info("")

        success = bot.send_contact_message(
            listing_url=TEST_LISTING_URL,
            message=CUSTOM_MESSAGE,
            quick_questions=QUICK_QUESTIONS
        )

        logger.info("")
        logger.info("=" * 80)
        if success:
            logger.info("✅ TEST COMPLETE - MESSAGE SENT!")
        else:
            logger.info("⚠️  TEST COMPLETE - MESSAGE NOT SENT (already contacted or error)")
        logger.info("=" * 80)

    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("")
        logger.info("🛑 Closing browser in 5 seconds...")
        logger.info("   (Press Ctrl+C to close immediately)")
        try:
            import time
            time.sleep(5)
        except KeyboardInterrupt:
            pass
        bot.close()

        logger.info("")
        logger.info("📊 Test Results:")
        logger.info(f"   Contacted listings: {len(bot.contacted_listings)}")
        logger.info(f"   Log file: {bot.log_file}")
        logger.info(f"   Cookies: {bot.cookies_file}")
        logger.info("")


if __name__ == "__main__":
    main()
