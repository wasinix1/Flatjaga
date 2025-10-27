#!/usr/bin/env python3
"""
derStandard.at Auto-Contact Bot
Automatically sends contact messages to apartment listings
No login required - uses profile data to fill contact forms
"""

import time
import random
import json
import signal
import logging
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)


class DerStandardContactBot:
    def __init__(self, profile_path=None, headless=False, delay_min=0.5, delay_max=2.0):
        """
        Initialize the bot with Chrome WebDriver

        Args:
            profile_path: Path to derStandard profile JSON file
            headless: Run Chrome in headless mode (no visible browser)
            delay_min: Minimum delay between actions in seconds
            delay_max: Maximum delay between actions in seconds
        """
        self.options = webdriver.ChromeOptions()
        self.delay_min = delay_min
        self.delay_max = delay_max

        if headless:
            self.options.add_argument('--headless')

        # Make it look more like a real browser
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)

        self.headless = headless
        self.driver = None

        # Load profile data
        if profile_path is None:
            profile_path = Path(__file__).parent.parent / 'profiles' / 'derStandard_profile.json'

        self.profile = self._load_profile(profile_path)

        # Track contacted listings
        self.contacted_file = Path.home() / '.derstandard_contacted.json'
        self.contacted_listings = self._load_contacted_listings()

        logger.info("derStandard bot initialized")

    def _load_profile(self, profile_path):
        """Load user profile data from JSON file"""
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)

            # Validate required fields
            required_fields = ['firstName', 'lastName', 'email', 'message']
            missing_fields = [field for field in required_fields if not profile.get(field)]

            if missing_fields:
                raise ValueError(f"Profile missing required fields: {', '.join(missing_fields)}")

            logger.info(f"Loaded derStandard profile from {profile_path}")
            return profile

        except FileNotFoundError:
            logger.error(f"Profile file not found: {profile_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in profile file: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading profile: {e}")
            raise

    def _load_contacted_listings(self):
        """Load the list of already contacted listing IDs"""
        if self.contacted_file.exists():
            try:
                with open(self.contacted_file, 'r') as f:
                    return set(json.load(f))
            except Exception as e:
                logger.warning(f"Could not load contacted listings: {e}")
                return set()
        return set()

    def _save_contacted_listing(self, listing_id):
        """Save a listing ID as contacted"""
        try:
            self.contacted_listings.add(listing_id)
            with open(self.contacted_file, 'w') as f:
                json.dump(list(self.contacted_listings), f)
            logger.debug(f"Saved listing {listing_id} as contacted")
        except Exception as e:
            logger.error(f"Could not save contacted listing: {e}")

    def _random_delay(self, min_sec=None, max_sec=None):
        """Add a random delay to simulate human behavior

        Args:
            min_sec: Minimum delay in seconds (uses self.delay_min if not specified)
            max_sec: Maximum delay in seconds (uses self.delay_max if not specified)
        """
        if min_sec is None:
            min_sec = self.delay_min
        if max_sec is None:
            max_sec = self.delay_max

        time.sleep(random.uniform(min_sec, max_sec))

    def _try_click_element(self, element, description="element"):
        """Try multiple strategies to click an element.

        Args:
            element: Selenium WebElement to click
            description: Description for logging

        Returns:
            True if click succeeded, False otherwise
        """
        strategies = [
            ("normal click", lambda e: e.click()),
            ("JavaScript click", lambda e: self.driver.execute_script("arguments[0].click();", e)),
            ("scroll and click", lambda e: (
                self.driver.execute_script("arguments[0].scrollIntoView(true);", e),
                time.sleep(0.1),
                e.click()
            )),
        ]

        for strategy_name, strategy_func in strategies:
            try:
                strategy_func(element)
                logger.debug(f"✓ Clicked {description} using {strategy_name}")
                return True
            except Exception as e:
                logger.debug(f"  {strategy_name} failed for {description}: {e}")
                continue

        logger.warning(f"✗ All click strategies failed for {description}")
        return False

    def _handle_popups(self):
        """Handle any popups that might appear (cookies, privacy).
        Can be called at any time - checks for multiple popup types.

        Returns:
            True if any popup was handled, False otherwise
        """
        handled = False

        # Try to accept cookies
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                try:
                    if not button.is_displayed():
                        continue
                    button_text = button.text.lower()
                    if any(word in button_text for word in ['akzeptieren', 'accept', 'zustimmen', 'agree', 'alle']):
                        if self._try_click_element(button, "cookie button"):
                            logger.info("✓ Accepted cookies")
                            handled = True
                            self._random_delay(0.2, 0.4)
                            break
                except:
                    continue
        except:
            pass

        # Try to accept privacy popup
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                try:
                    if not button.is_displayed():
                        continue
                    if "datenschutz" in button.text.lower() and any(word in button.text.lower() for word in ['ok', 'verstanden', 'akzeptieren']):
                        if self._try_click_element(button, "privacy button"):
                            logger.info("✓ Accepted privacy popup")
                            handled = True
                            self._random_delay(0.2, 0.4)
                            break
                except:
                    continue
        except:
            pass

        return handled

    def start(self):
        """Start the Chrome WebDriver"""
        try:
            self.driver = webdriver.Chrome(options=self.options)
            logger.info("Browser started for derStandard")
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            raise

    def close(self):
        """Close the browser with timeout to prevent hanging"""
        if not self.driver:
            return

        def timeout_handler(signum, frame):
            raise TimeoutError("Browser quit() operation timed out")

        try:
            # Set 10-second timeout for browser quit operation
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)

            try:
                self.driver.quit()
                signal.alarm(0)  # Cancel alarm if quit succeeds
                logger.info("Browser closed")
            except TimeoutError:
                signal.alarm(0)  # Cancel alarm
                logger.error("Browser quit() timed out after 10s - forcing cleanup")

                # Try to force kill the browser process
                try:
                    self.driver.service.process.kill()
                    logger.warning("Killed browser process forcefully")
                except Exception as e:
                    logger.error(f"Could not force-kill browser: {e}")

                logger.info("Browser closed (forced after timeout)")

        except Exception as e:
            signal.alarm(0)  # Always cancel alarm
            logger.error(f"Error during browser close: {e}")

            # Try force kill as last resort
            try:
                if hasattr(self, 'driver') and hasattr(self.driver, 'service'):
                    self.driver.service.process.kill()
                    logger.warning("Force-killed browser after error")
            except:
                pass
        finally:
            signal.alarm(0)  # Ensure alarm is always cancelled

    def is_already_contacted(self, listing_url):
        """Check if we've already contacted this listing"""
        # Extract listing ID from URL (usually in /detail/{id} format)
        import re
        match = re.search(r'/detail/(\d+)', listing_url)
        if match:
            listing_id = match.group(1)
            return listing_id in self.contacted_listings
        return False

    def send_contact_message(self, listing_url):
        """
        Send a contact message to a specific listing with adaptive form detection.

        Args:
            listing_url: Full URL to the derStandard listing

        Returns:
            True if message sent successfully, False otherwise
        """
        # Check if already contacted
        if self.is_already_contacted(listing_url):
            logger.info(f"Already contacted: {listing_url}")
            return False

        # Extract listing ID for tracking
        import re
        match = re.search(r'/detail/(\d+)', listing_url)
        listing_id = match.group(1) if match else listing_url.split('/')[-1]

        try:
            logger.info(f"Opening listing: {listing_url}")
            self.driver.get(listing_url)
            self._random_delay(0.5, 1.0)

            # Handle popups that might appear on page load
            self._handle_popups()
            self._random_delay(0.3, 0.6)

            # Wait for contact form to be present
            logger.info("Looking for contact form...")
            try:
                form = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "contactForm"))
                )
                logger.info("Found contact form")
            except TimeoutException:
                logger.error("Contact form not found - may not be available for this listing")
                return False

            # Scroll form into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", form)
            self._random_delay(0.2, 0.4)

            # Fill out the form fields
            logger.info("Filling form fields...")

            # First name (required)
            try:
                first_name_field = self.driver.find_element(By.ID, "firstName")
                first_name_field.clear()
                first_name_field.send_keys(self.profile['firstName'])
                logger.debug("✓ Filled first name")
                self._random_delay(0.1, 0.2)
            except Exception as e:
                logger.error(f"Could not fill first name: {e}")
                return False

            # Last name (required)
            try:
                last_name_field = self.driver.find_element(By.ID, "lastName")
                last_name_field.clear()
                last_name_field.send_keys(self.profile['lastName'])
                logger.debug("✓ Filled last name")
                self._random_delay(0.1, 0.2)
            except Exception as e:
                logger.error(f"Could not fill last name: {e}")
                return False

            # Email (required)
            try:
                email_field = self.driver.find_element(By.ID, "email")
                email_field.clear()
                email_field.send_keys(self.profile['email'])
                logger.debug("✓ Filled email")
                self._random_delay(0.1, 0.2)
            except Exception as e:
                logger.error(f"Could not fill email: {e}")
                return False

            # Phone number (optional)
            if self.profile.get('phoneNumber'):
                try:
                    phone_field = self.driver.find_element(By.ID, "phoneNumber")
                    phone_field.clear()
                    phone_field.send_keys(self.profile['phoneNumber'])
                    logger.debug("✓ Filled phone number")
                    self._random_delay(0.1, 0.2)
                except Exception as e:
                    logger.debug(f"Could not fill phone number (optional): {e}")

            # Message (required)
            try:
                message_field = self.driver.find_element(By.ID, "message")
                message_field.clear()
                message_field.send_keys(self.profile['message'])
                logger.debug("✓ Filled message")
                self._random_delay(0.2, 0.4)
            except Exception as e:
                logger.error(f"Could not fill message: {e}")
                return False

            # Find and click submit button
            logger.info("Looking for submit button...")
            try:
                submit_button = self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
                if not submit_button.is_displayed() or not submit_button.is_enabled():
                    logger.error("Submit button not visible or enabled")
                    return False

                logger.info("Submitting form...")
                self._random_delay(0.2, 0.4)

                if not self._try_click_element(submit_button, "submit button"):
                    logger.error("Failed to click submit button")
                    return False

                logger.info("Form submitted")
                self._random_delay(0.5, 1.0)

            except Exception as e:
                logger.error(f"Could not find or click submit button: {e}")
                return False

            # Handle any popups after submission
            self._handle_popups()
            self._random_delay(0.3, 0.6)

            # Check for success (derStandard may show confirmation or redirect)
            logger.info("Waiting for confirmation...")
            success_found = False

            # Try multiple strategies to detect success
            for attempt in range(10):
                self._random_delay(0.3, 0.5)

                try:
                    # Strategy 1: Look for success message text
                    success_texts = ['erfolgreich', 'gesendet', 'übermittelt', 'danke']
                    for text in success_texts:
                        elements = self.driver.find_elements(By.XPATH, f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{text}')]")
                        if elements and any(el.is_displayed() for el in elements):
                            success_found = True
                            logger.info(f"Found success indicator: '{text}'")
                            break

                    if success_found:
                        break

                    # Strategy 2: Check if form is gone (may indicate redirect or success)
                    try:
                        form_still_present = self.driver.find_element(By.ID, "contactForm").is_displayed()
                        if not form_still_present:
                            success_found = True
                            logger.info("Form disappeared - likely successful")
                            break
                    except NoSuchElementException:
                        success_found = True
                        logger.info("Form no longer in DOM - likely successful")
                        break

                except Exception as e:
                    logger.debug(f"Error checking for success (attempt {attempt+1}): {e}")
                    continue

            if success_found:
                self._save_contacted_listing(listing_id)
                logger.info(f"✓ Message sent successfully to {listing_id}")
                return True
            else:
                logger.warning("Could not confirm message was sent - assuming failure")
                return False

        except TimeoutException:
            logger.error(f"Timeout waiting for elements on {listing_url}")
            return False
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}", exc_info=True)
            return False

    def test_single_listing(self, listing_url):
        """
        Test the bot on a single listing
        Good for debugging and initial testing
        """
        print("\n=== Testing Single Listing ===")

        self.start()

        # Refresh to apply any settings
        self.driver.get('https://immobilien.derstandard.at')
        self._random_delay()

        # Accept cookies if needed
        self._handle_popups()

        # Send the message
        success = self.send_contact_message(listing_url)

        print("\n=== Test Complete ===")
        print(f"Result: {'SUCCESS' if success else 'FAILED'}")

        input("\nPress Enter to close browser...")
        self.close()


def main():
    """
    Test script - run this to test on a single listing
    """
    print("=" * 50)
    print("derStandard Auto-Contact Bot")
    print("=" * 50)

    # Get listing URL from user
    print("\nPaste a derStandard listing URL to test:")
    listing_url = input("> ").strip()

    if not listing_url:
        print("No URL provided, exiting...")
        return

    # Create bot and test
    bot = DerStandardContactBot(headless=False)
    bot.test_single_listing(listing_url)


if __name__ == "__main__":
    main()
