#!/usr/bin/env python3
"""
Test script for archive feature - simulates a successful contact
Usage: python archive_test.py "LISTING_URL"
"""
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flathunter.config import Config
from flathunter.archive_manager import ArchiveManager
from flathunter.telegram_archive_handler import TelegramArchiveHandler
from flathunter.notifiers import SenderTelegram
from flathunter.logger_config import logger
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time


def create_test_driver():
    """Create a headless Chrome driver"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=options)
    return driver


def test_archive_for_url(listing_url: str, config_path: str = None):
    """
    Test archive feature by fetching a listing page and creating an archive

    Args:
        listing_url: URL of the listing to archive
        config_path: Optional path to config file
    """
    print(f"\n{'='*70}")
    print(f"ARCHIVE TEST")
    print(f"{'='*70}\n")
    print(f"Testing archive for: {listing_url}\n")

    try:
        # Load config
        if config_path:
            config = Config(config_path)
        else:
            # Try to find config.yaml in current directory
            import os
            default_config = 'config.yaml'
            if os.path.exists(default_config):
                print(f"Using config file: {default_config}")
                config = Config(default_config)
            else:
                print(f"⚠️  No config.yaml found in current directory")
                print(f"   Please provide config path: python archive_test.py URL config.yaml")
                print(f"   Or set FLATHUNTER_TARGET_URLS environment variable\n")
                return False

        # Check if archive is enabled
        if not config.get('telegram_archive_contacted', False):
            print("⚠️  WARNING: telegram_archive_contacted is not enabled in config.yaml")
            print("   The feature will work in test mode, but won't work in production.")
            print("   To enable: set telegram_archive_contacted: true\n")

        # Initialize components
        print("Initializing archive components...")
        archive_manager = ArchiveManager(config)

        telegram_notifier = None
        archive_handler = None
        if 'telegram' in config.notifiers():
            telegram_notifier = SenderTelegram(config)
            archive_handler = TelegramArchiveHandler(
                bot_token=telegram_notifier.bot_token,
                sender_telegram=telegram_notifier
            )
            # Start polling
            archive_handler.start_polling()
            print("✓ Telegram components initialized")
        else:
            print("⚠️  No Telegram configured - will skip button test")

        # Determine crawler type
        crawler = 'Unknown'
        if 'willhaben.at' in listing_url:
            crawler = 'Willhaben'
        elif 'wg-gesucht.de' in listing_url:
            crawler = 'WG-Gesucht'

        print(f"✓ Detected crawler: {crawler}")

        # Create driver and fetch page
        print(f"\nFetching page...")
        driver = create_test_driver()

        try:
            driver.get(listing_url)
            time.sleep(3)  # Wait for page to load

            # For Willhaben: Scroll through gallery to load all images
            if 'willhaben.at' in listing_url:
                print(f"Scrolling through Willhaben gallery to load all images...")
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.common.exceptions import NoSuchElementException, TimeoutException

                # Wait for gallery container to be present
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '.flickity-viewport, [class*="gallery"], [class*="carousel"]'))
                    )
                    time.sleep(1)  # Give Flickity time to fully initialize
                    print("  Gallery container found")
                except TimeoutException:
                    print("  Warning: Gallery container not found")

                clicks = 0
                max_clicks = 30
                consecutive_failures = 0
                max_consecutive_failures = 3

                while clicks < max_clicks and consecutive_failures < max_consecutive_failures:
                    try:
                        # Try multiple selectors
                        next_button = None
                        selectors = [
                            'button.flickity-prev-next-button.next',
                            'button.flickity-button.next',
                            'button[aria-label*="Next" i]',
                            '.flickity-prev-next-button.next'
                        ]

                        for selector in selectors:
                            try:
                                next_button = driver.find_element(By.CSS_SELECTOR, selector)
                                if next_button:
                                    break
                            except NoSuchElementException:
                                continue

                        if not next_button or not next_button.is_displayed():
                            break

                        # Use JavaScript click (more reliable)
                        driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(0.4)
                        clicks += 1
                        consecutive_failures = 0

                    except (NoSuchElementException, Exception) as e:
                        consecutive_failures += 1
                        if consecutive_failures >= max_consecutive_failures:
                            break

                print(f"✓ Clicked through gallery {clicks} times")
                time.sleep(0.5)

            page_source = driver.page_source
            print(f"✓ Page loaded ({len(page_source)} bytes)")

            # Create mock expose
            expose = {
                'url': listing_url,
                'title': 'Test Listing',
                'price': '€850',
                'size': '60m²',
                'rooms': '2',
                'address': 'Test Address',
                'crawler': crawler,
                '_auto_contacted': True
            }

            # Extract archive data
            print(f"\nExtracting archive data...")
            archive_data = archive_manager.extract_archive_data(
                page_source, listing_url, expose
            )

            if not archive_data:
                print("✗ Failed to extract archive data")
                return False

            images = archive_data.get('images', [])
            description = archive_data.get('description', '')

            print(f"✓ Extracted {len(images)} images")
            if images:
                print(f"  Sample image URLs:")
                for i, img in enumerate(images[:3], 1):
                    print(f"    {i}. {img[:80]}...")

            print(f"✓ Extracted description ({len(description)} chars)")
            if description:
                preview = description[:200].replace('\n', ' ')
                print(f"  Preview: {preview}...")

            # Save locally
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            listing_id = listing_url.split('/')[-1] or 'test'
            archive_id = f"{timestamp}_{listing_id}"

            print(f"\nSaving archive locally...")
            if archive_manager.save_archive_locally(archive_data, archive_id):
                print(f"✓ Saved to: {archive_manager.archive_path / archive_id}")
            else:
                print(f"✗ Failed to save locally")

            # Test Telegram integration
            if telegram_notifier and archive_handler:
                print(f"\nTesting Telegram button...")

                # Store archive for first receiver
                receiver_id = telegram_notifier.receiver_ids[0] if telegram_notifier.receiver_ids else None

                if not receiver_id:
                    print("✗ No Telegram receivers configured")
                else:
                    stored_id = archive_handler.store_archive(archive_data, receiver_id)

                    if stored_id:
                        print(f"✓ Archive stored with ID: {stored_id}")

                        # Send message with button
                        result = telegram_notifier.send_with_inline_button(
                            chat_id=receiver_id,
                            message=f"🧪 TEST: Archive for\n{expose['title']}",
                            button_text="📷 View Archive (Test)",
                            callback_data=f"archive:{stored_id}"
                        )

                        if result:
                            print(f"✓ Sent Telegram message with button to chat {receiver_id}")
                            print(f"\n{'='*70}")
                            print(f"SUCCESS! Check your Telegram and click the button.")
                            print(f"{'='*70}\n")
                        else:
                            print(f"✗ Failed to send Telegram message")
                    else:
                        print(f"✗ Failed to store archive")

            print(f"\n{'='*70}")
            print(f"Test completed successfully!")
            print(f"{'='*70}\n")

            # Keep polling thread alive for a bit to handle button clicks
            if archive_handler:
                print("Waiting 60 seconds for button clicks (press Ctrl+C to exit early)...")
                try:
                    time.sleep(60)
                except KeyboardInterrupt:
                    print("\nExiting...")

                archive_handler.stop_polling()

            return True

        finally:
            driver.quit()

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python archive_test.py \"LISTING_URL\" [config_path]")
        print(f"\nExamples:")
        print(f"  python archive_test.py \"https://www.willhaben.at/iad/immobilien/d/wohnung/...\"")
        print(f"  python archive_test.py \"https://www.wg-gesucht.de/...\" /path/to/config.yaml")
        print(f"\nNote: If config_path is not provided, looks for config.yaml in current directory")
        sys.exit(1)

    listing_url = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else None

    success = test_archive_for_url(listing_url, config_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
