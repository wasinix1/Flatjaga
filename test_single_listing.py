#!/usr/bin/env python3
"""
Test WG-Gesucht Contact Bot on a Single Listing
Quick script to test template button functionality with full logging
"""

import sys
import logging
from pathlib import Path

# Setup logging to show all INFO messages
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s|%(filename)s|%(levelname)-8s]: %(message)s',
    datefmt='%Y/%m/%d %H:%M:%S'
)

def test_single_listing(listing_url, headless=False, stealth_mode=False, template_index=0):
    """
    Test contacting a single WG-Gesucht listing with full diagnostic logging.

    Args:
        listing_url: Full URL to WG-Gesucht listing
        headless: Run browser in headless mode (default False for debugging)
        stealth_mode: Enable stealth mode (default False for faster testing)
        template_index: Which template to use (default 0)

    Returns:
        True if contact succeeded, False otherwise
    """
    try:
        from flathunter.wg_gesucht_contact_bot import WgGesuchtContactBot

        print("\n" + "="*70)
        print("WG-GESUCHT SINGLE LISTING TEST")
        print("="*70)
        print(f"\nListing URL: {listing_url}")
        print(f"Headless: {headless}")
        print(f"Stealth Mode: {stealth_mode}")
        print(f"Template Index: {template_index}")
        print("\n" + "="*70 + "\n")

        # Initialize bot
        bot = WgGesuchtContactBot(
            headless=headless,
            stealth_mode=stealth_mode,
            template_index=template_index
        )

        # Start browser and load session
        bot.start()

        # Check if session exists
        cookie_file = Path.home() / '.wg_gesucht_cookies.json'
        if not cookie_file.exists():
            print("\n" + "!"*70)
            print("ERROR: No saved session found!")
            print("!"*70)
            print("\nPlease run setup_sessions.py first to login:")
            print("  python setup_sessions.py")
            print("\nThen try this script again.\n")
            bot.close()
            return False

        # Load cookies
        if not bot.load_cookies():
            print("\n" + "!"*70)
            print("ERROR: Failed to load session (cookies may be expired)")
            print("!"*70)
            print("\nPlease re-login using:")
            print("  python setup_sessions.py")
            print("\nThen try this script again.\n")
            bot.close()
            return False

        print("\n✓ Session loaded successfully\n")

        # Attempt to contact listing
        print("Starting contact flow...\n")
        success = bot.send_contact_message(listing_url)

        print("\n" + "="*70)
        if success:
            print("✅ TEST PASSED - Message sent successfully!")
        else:
            print("❌ TEST FAILED - Could not send message")
            print("\nCheck the logs above for detailed diagnostics:")
            print("  → Which template button strategy was tried")
            print("  → Which click method succeeded/failed")
            print("  → Element properties (classes, visibility, etc.)")
        print("="*70 + "\n")

        # Close browser
        bot.close()

        return success

    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user (Ctrl+C)\n")
        return False
    except Exception as e:
        print("\n" + "!"*70)
        print(f"EXCEPTION: {type(e).__name__}: {e}")
        print("!"*70)
        import traceback
        traceback.print_exc()
        print()
        return False


def main():
    """Main entry point with argument parsing"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Test WG-Gesucht contact bot on a single listing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Test with visible browser (recommended for debugging)
  python test_single_listing.py "https://www.wg-gesucht.de/wohnungen-in-Wien.12345.html"

  # Test in headless mode
  python test_single_listing.py "URL" --headless

  # Test with stealth mode enabled
  python test_single_listing.py "URL" --stealth

  # Test with specific template (second template = index 1)
  python test_single_listing.py "URL" --template 1
        '''
    )

    parser.add_argument(
        'url',
        help='Full URL to WG-Gesucht listing'
    )

    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode (default: visible browser for debugging)'
    )

    parser.add_argument(
        '--stealth',
        action='store_true',
        help='Enable stealth mode with human-like behavior (default: off)'
    )

    parser.add_argument(
        '--template',
        type=int,
        default=0,
        help='Template index to use (default: 0 = first template)'
    )

    args = parser.parse_args()

    # Validate URL
    if not args.url.startswith('https://www.wg-gesucht.de/'):
        print("\n❌ ERROR: URL must be a WG-Gesucht listing")
        print(f"   Got: {args.url}")
        print(f"   Expected format: https://www.wg-gesucht.de/wohnungen-in-*.html\n")
        sys.exit(1)

    # Run test
    success = test_single_listing(
        args.url,
        headless=args.headless,
        stealth_mode=args.stealth,
        template_index=args.template
    )

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
