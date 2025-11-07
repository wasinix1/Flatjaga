#!/usr/bin/env python3
"""
Manual test script for WG-Gesucht stealth mode contact bot.
Tests the stealth discovery and contact flow on a specific listing.
"""

import sys
import logging
from flathunter.wg_gesucht_contact_bot import WgGesuchtContactBot

# Setup logging to see detailed output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_contact(listing_url, stealth_mode=True, headless=False, template_index=0):
    """
    Test contacting a WG-Gesucht listing.

    Args:
        listing_url: Full URL to the listing
        stealth_mode: Enable stealth mode (default: True)
        headless: Run in headless mode (default: False for testing)
        template_index: Which template to use (default: 0)
    """
    print("\n" + "="*70)
    print("WG-GESUCHT STEALTH MODE TEST")
    print("="*70)
    print(f"Listing URL: {listing_url}")
    print(f"Stealth Mode: {stealth_mode}")
    print(f"Headless: {headless}")
    print(f"Template Index: {template_index}")
    print("="*70 + "\n")

    bot = None
    try:
        # Initialize bot
        print("→ Initializing bot...")
        bot = WgGesuchtContactBot(
            headless=headless,
            template_index=template_index,
            delay_min=0.5,
            delay_max=1.5,
            stealth_mode=stealth_mode
        )

        # Start browser
        print("→ Starting browser...")
        bot.start()

        # Load saved session
        print("→ Loading saved session...")
        if not bot.load_cookies():
            print("\n❌ ERROR: No saved session found!")
            print("→ Please run 'python setup_sessions.py' first to login.\n")
            return False

        if not bot.session_valid:
            print("\n❌ ERROR: Session is not valid!")
            print("→ Please run 'python setup_sessions.py' to re-login.\n")
            return False

        print("✓ Session loaded and valid\n")

        # Contact the listing
        print("→ Attempting to contact listing...\n")
        success = bot.send_contact_message(listing_url)

        print("\n" + "="*70)
        if success:
            print("✅ TEST SUCCESSFUL - Message sent!")
        else:
            print("❌ TEST FAILED - Could not send message")
        print("="*70 + "\n")

        return success

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user\n")
        return False

    except Exception as e:
        print(f"\n\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean up
        if bot:
            print("\n→ Closing browser...")
            bot.close()
            print("✓ Browser closed\n")


if __name__ == "__main__":
    # Check if URL was provided
    if len(sys.argv) < 2:
        print("\nUsage: python test_wg_stealth.py <listing_url> [options]")
        print("\nOptions:")
        print("  --no-stealth       Disable stealth mode")
        print("  --headless         Run in headless mode (visible by default for testing)")
        print("  --template N       Use template N (default: 0)")
        print("\nExamples:")
        print("  # Test with stealth mode (visible browser)")
        print("  python test_wg_stealth.py 'https://www.wg-gesucht.de/...'")
        print("\n  # Test without stealth mode")
        print("  python test_wg_stealth.py 'https://www.wg-gesucht.de/...' --no-stealth")
        print("\n  # Test in headless mode")
        print("  python test_wg_stealth.py 'https://www.wg-gesucht.de/...' --headless")
        print("\n  # Use template 1 instead of 0")
        print("  python test_wg_stealth.py 'https://www.wg-gesucht.de/...' --template 1")
        print()
        sys.exit(1)

    # Parse arguments
    listing_url = sys.argv[1]
    stealth_mode = "--no-stealth" not in sys.argv
    headless = "--headless" in sys.argv

    template_index = 0
    if "--template" in sys.argv:
        try:
            idx = sys.argv.index("--template")
            template_index = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("❌ ERROR: --template requires a number")
            sys.exit(1)

    # Run test
    success = test_contact(
        listing_url=listing_url,
        stealth_mode=stealth_mode,
        headless=headless,
        template_index=template_index
    )

    sys.exit(0 if success else 1)
