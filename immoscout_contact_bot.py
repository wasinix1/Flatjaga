#!/usr/bin/env python3
"""
ImmoScout24 Auto-Contact Bot - STANDALONE VERSION
Automatically sends contact messages to ImmoScout24 apartment listings

TRYHARD MODE: Maximum logging, slow & cautious, human-like behavior
"""

import time
import random
import json
import os
import logging
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# SSL FIX
try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
except ImportError:
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass


class ImmoscoutContactBot:
    """ImmoScout24 contact bot with MAXIMUM LOGGING and human-like behavior"""

    def __init__(self, headless=False, delay_min=1.5, delay_max=4.0, message_template=None):
        """
        Initialize the bot

        Args:
            headless: Run Chrome in headless mode (default: False for testing)
            delay_min: Minimum delay between actions in seconds (default: 1.5s - SLOW!)
            delay_max: Maximum delay between actions in seconds (default: 4.0s - CAUTIOUS!)
            message_template: Default message to send (can be overridden per contact)
        """
        self.headless = headless
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.driver = None

        # Default message template
        self.message_template = message_template or (
            "Guten Tag,\n\n"
            "ich habe großes Interesse an der Wohnung und würde mich sehr über "
            "einen Besichtigungstermin freuen.\n\n"
            "Mit freundlichen Grüßen"
        )

        # Setup Chrome options
        self.options = webdriver.ChromeOptions()

        if headless:
            self.options.add_argument('--headless')
            logger.info("🎭 Headless mode ENABLED")
        else:
            logger.info("👀 Visible browser mode (headless=False)")

        # Anti-detection measures
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--no-sandbox')

        # Random window size (looks more human)
        width = random.randint(1200, 1600)
        height = random.randint(900, 1080)
        self.options.add_argument(f'--window-size={width},{height}')
        logger.debug(f"🖥️  Window size: {width}x{height}")

        # File paths
        self.cookies_file = Path.home() / '.immoscout_cookies.json'
        self.contacted_file = Path.home() / '.immoscout_contacted.json'
        self.log_file = Path.home() / '.immoscout_contact_log.jsonl'

        # Track contacted listings
        self.contacted_listings = self._load_contacted_listings()

        logger.info(f"✅ ImmoscoutContactBot initialized")
        logger.info(f"   Delays: {delay_min}-{delay_max}s (SLOW & CAUTIOUS)")
        logger.info(f"   Cookies: {self.cookies_file}")
        logger.info(f"   Contacted: {len(self.contacted_listings)} listings tracked")

    def _load_contacted_listings(self):
        """Load the list of already contacted listing URLs"""
        if self.contacted_file.exists():
            try:
                with open(self.contacted_file, 'r') as f:
                    data = json.load(f)
                    logger.debug(f"📖 Loaded {len(data)} contacted listings from file")
                    return set(data)
            except Exception as e:
                logger.warning(f"⚠️  Failed to load contacted listings: {e}")
                return set()
        else:
            logger.debug("📖 No contacted listings file found (first run)")
            return set()

    def _save_contacted_listing(self, listing_url):
        """Save a listing URL as contacted"""
        self.contacted_listings.add(listing_url)
        with open(self.contacted_file, 'w') as f:
            json.dump(list(self.contacted_listings), f, indent=2)
        logger.debug(f"💾 Saved contacted listing (total: {len(self.contacted_listings)})")

    def _log_to_file(self, listing_url, status, details=None):
        """Log contact attempt to file with timestamp and details"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "url": listing_url,
                "status": status,  # "success", "already_contacted", "error", etc.
                "details": details or {}
            }

            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

            logger.debug(f"📝 Logged to file: {status}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to log to file: {e}")

    def _random_delay(self, min_sec=None, max_sec=None, reason=""):
        """Add a random delay to simulate human behavior

        Args:
            min_sec: Minimum delay in seconds (uses self.delay_min if not specified)
            max_sec: Maximum delay in seconds (uses self.delay_max if not specified)
            reason: Description of why we're waiting (for logging)
        """
        if min_sec is None:
            min_sec = self.delay_min
        if max_sec is None:
            max_sec = self.delay_max

        delay = random.uniform(min_sec, max_sec)
        reason_str = f" ({reason})" if reason else ""
        logger.debug(f"⏳ Waiting {delay:.2f}s{reason_str}")
        time.sleep(delay)

    def _human_type(self, element, text, typing_speed_range=(0.05, 0.15)):
        """Type text with human-like random delays between keystrokes

        Args:
            element: Selenium element to type into
            text: Text to type
            typing_speed_range: Tuple of (min_delay, max_delay) between keystrokes in seconds
        """
        logger.debug(f"⌨️  Typing {len(text)} characters with human-like speed...")

        for char in text:
            element.send_keys(char)
            # Random delay between keystrokes
            delay = random.uniform(*typing_speed_range)
            time.sleep(delay)

        logger.debug("✅ Finished typing")

    def _smooth_scroll_to_element(self, element):
        """Smoothly scroll to an element (looks more human than instant scroll)"""
        logger.debug("📜 Smooth scrolling to element...")

        # Get element position
        y_position = element.location['y']

        # Scroll in steps (looks more human)
        current_scroll = self.driver.execute_script("return window.pageYOffset;")
        target_scroll = y_position - 200  # Leave some space above element

        steps = 5
        scroll_increment = (target_scroll - current_scroll) / steps

        for i in range(steps):
            self.driver.execute_script(f"window.scrollBy(0, {scroll_increment});")
            time.sleep(random.uniform(0.05, 0.15))

        logger.debug("✅ Scrolled to element")

    def start(self):
        """Start the browser"""
        logger.info("🚀 Starting Chrome browser...")

        try:
            self.driver = webdriver.Chrome(options=self.options)

            # Set page load timeout
            self.driver.set_page_load_timeout(60)

            # Execute CDP commands to hide webdriver flag
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": self.driver.execute_script("return navigator.userAgent").replace('Headless', '')
            })

            logger.info("✅ Browser started successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to start browser: {e}")
            return False

    def close(self):
        """Close the browser"""
        if self.driver:
            logger.info("🛑 Closing browser...")
            try:
                self.driver.quit()
                logger.info("✅ Browser closed")
            except Exception as e:
                logger.warning(f"⚠️  Error closing browser: {e}")

    def save_cookies(self):
        """Save current session cookies to file"""
        if not self.driver:
            logger.warning("⚠️  No browser session to save cookies from")
            return False

        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"💾 Saved {len(cookies)} cookies to {self.cookies_file}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save cookies: {e}")
            return False

    def load_cookies(self):
        """Load session cookies from file"""
        if not self.cookies_file.exists():
            logger.warning("⚠️  No cookies file found - you'll need to login")
            return False

        try:
            # First navigate to ImmoScout to set domain
            logger.info("🌐 Navigating to ImmoScout24 to set cookie domain...")
            self.driver.get("https://www.immobilienscout24.de/")
            self._random_delay(2, 4, "initial page load")

            # Load and add cookies
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)

            logger.info(f"🍪 Loading {len(cookies)} cookies...")
            for cookie in cookies:
                try:
                    # Remove domain if it starts with a dot (Selenium doesn't like it)
                    if 'domain' in cookie and cookie['domain'].startswith('.'):
                        cookie['domain'] = cookie['domain'][1:]

                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"  ⚠️  Couldn't add cookie {cookie.get('name', '?')}: {e}")

            logger.info("✅ Cookies loaded - refreshing page...")
            self.driver.refresh()
            self._random_delay(2, 4, "page refresh after cookies")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to load cookies: {e}")
            return False

    def wait_for_manual_login(self, timeout=300):
        """
        Wait for user to manually login in the browser

        Args:
            timeout: Maximum time to wait in seconds (default: 5 minutes)

        Returns:
            True if login detected, False if timeout
        """
        logger.info("⏸️  WAITING FOR MANUAL LOGIN")
        logger.info("=" * 60)
        logger.info("Please login to ImmoScout24 in the browser window.")
        logger.info("Once logged in, the bot will automatically continue.")
        logger.info(f"Timeout: {timeout}s ({timeout//60} minutes)")
        logger.info("=" * 60)

        start_time = time.time()

        # Navigate to login page
        self.driver.get("https://www.immobilienscout24.de/")

        while (time.time() - start_time) < timeout:
            try:
                # Check if we're logged in by looking for user profile elements
                # ImmoScout shows user menu when logged in
                user_elements = self.driver.find_elements(By.CSS_SELECTOR,
                    '[data-testid="header-user-menu"], .user-menu, [href*="/myprofile"]')

                if user_elements:
                    logger.info("✅ LOGIN DETECTED!")
                    self._random_delay(2, 3, "after login detection")
                    return True

                # Show countdown every 10 seconds
                elapsed = int(time.time() - start_time)
                remaining = timeout - elapsed
                if elapsed % 10 == 0:
                    logger.info(f"⏳ Waiting for login... ({remaining}s remaining)")

                time.sleep(1)

            except Exception as e:
                logger.debug(f"  Checking login status: {e}")
                time.sleep(1)

        logger.error(f"❌ Login timeout after {timeout}s")
        return False

    def wait_for_manual_captcha(self, timeout=300):
        """
        Pause and wait for user to manually solve captcha

        Args:
            timeout: Maximum time to wait in seconds (default: 5 minutes)
        """
        logger.warning("🤖 CAPTCHA DETECTED - WAITING FOR MANUAL SOLVE")
        logger.info("=" * 60)
        logger.info("Please solve the captcha in the browser window.")
        logger.info("The bot will automatically continue once solved.")
        logger.info(f"Timeout: {timeout}s ({timeout//60} minutes)")
        logger.info("=" * 60)

        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                # Check if captcha is gone (simple heuristic - can be improved)
                captcha_elements = self.driver.find_elements(By.CSS_SELECTOR,
                    'iframe[src*="captcha"], .captcha, #captcha')

                if not captcha_elements:
                    logger.info("✅ CAPTCHA APPEARS TO BE SOLVED!")
                    self._random_delay(2, 4, "after captcha solve")
                    return True

                # Show countdown every 10 seconds
                elapsed = int(time.time() - start_time)
                remaining = timeout - elapsed
                if elapsed % 10 == 0:
                    logger.info(f"⏳ Waiting for captcha solve... ({remaining}s remaining)")

                time.sleep(1)

            except Exception as e:
                logger.debug(f"  Checking captcha status: {e}")
                time.sleep(1)

        logger.error(f"❌ Captcha timeout after {timeout}s")
        return False

    def send_contact_message(self, listing_url, message=None, quick_questions=None):
        """
        Send a contact message to an ImmoScout24 listing

        Args:
            listing_url: Full URL to the listing
            message: Custom message to send (uses default template if None)
            quick_questions: Dict of quick question checkboxes to check
                           e.g. {'exactAddress': True, 'appointment': True, 'moreInfo': False}

        Returns:
            True if message sent successfully, False otherwise
        """
        logger.info("=" * 80)
        logger.info(f"🎯 CONTACTING LISTING")
        logger.info(f"   URL: {listing_url}")
        logger.info("=" * 80)

        # Check if already contacted
        if listing_url in self.contacted_listings:
            logger.info("⏭️  SKIPPING - Already contacted this listing")
            self._log_to_file(listing_url, "already_contacted")
            return False

        try:
            # Use provided message or default template
            message_text = message or self.message_template
            logger.debug(f"📝 Message length: {len(message_text)} characters")

            # Navigate to listing
            logger.info(f"🌐 Navigating to listing...")
            self.driver.get(listing_url)
            self._random_delay(3, 6, "page load")

            # Take screenshot for debugging
            screenshot_path = Path.home() / f".immoscout_screenshot_{int(time.time())}.png"
            try:
                self.driver.save_screenshot(str(screenshot_path))
                logger.debug(f"📸 Screenshot saved: {screenshot_path}")
            except:
                pass

            # Check for captcha
            logger.debug("🔍 Checking for captcha...")
            captcha_elements = self.driver.find_elements(By.CSS_SELECTOR,
                'iframe[src*="captcha"], .captcha, #captcha')
            if captcha_elements:
                if not self.wait_for_manual_captcha():
                    raise Exception("Captcha not solved in time")

            # Find contact form
            logger.info("🔍 Looking for contact form...")

            try:
                # Wait for contact request block
                contact_block = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="contact-request-block"]'))
                )
                logger.info("✅ Found contact request block!")

                # Scroll to it smoothly
                self._smooth_scroll_to_element(contact_block)
                self._random_delay(1, 2, "after scroll")

            except TimeoutException:
                logger.error("❌ Contact request block not found!")
                logger.debug("🔍 Trying to find contact button instead...")

                # Maybe we need to click a contact button first?
                contact_buttons = self.driver.find_elements(By.CSS_SELECTOR,
                    'button:contains("Kontakt"), a:contains("Kontakt"), [data-testid*="contact"]')

                if contact_buttons:
                    logger.info(f"📍 Found {len(contact_buttons)} contact button(s)")
                    contact_buttons[0].click()
                    self._random_delay(2, 4, "after clicking contact button")

                    # Try finding the form again
                    contact_block = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="contact-request-block"]'))
                    )
                    logger.info("✅ Found contact form after clicking button!")
                else:
                    raise Exception("No contact form or contact button found")

            # Handle quick questions if specified
            if quick_questions:
                logger.info("☑️  Setting quick questions...")

                checkbox_mapping = {
                    'exactAddress': 'quickQuestions.exactAddress',
                    'appointment': 'quickQuestions.appointment',
                    'moreInfo': 'quickQuestions.moreInfo'
                }

                for question_key, should_check in quick_questions.items():
                    if question_key in checkbox_mapping:
                        checkbox_name = checkbox_mapping[question_key]

                        try:
                            checkbox = self.driver.find_element(By.CSS_SELECTOR, f'input[name="{checkbox_name}"]')

                            is_checked = checkbox.get_attribute('aria-checked') == 'true'

                            if should_check and not is_checked:
                                logger.debug(f"  ☑️  Checking: {question_key}")
                                self._smooth_scroll_to_element(checkbox)
                                self._random_delay(0.5, 1, "before checkbox click")
                                checkbox.click()
                                self._random_delay(0.3, 0.7, "after checkbox click")
                            elif not should_check and is_checked:
                                logger.debug(f"  ☐  Unchecking: {question_key}")
                                checkbox.click()
                                self._random_delay(0.3, 0.7, "after checkbox click")
                            else:
                                logger.debug(f"  ✓  {question_key} already in desired state")

                        except Exception as e:
                            logger.warning(f"  ⚠️  Couldn't set {question_key}: {e}")

            # Find message textarea
            logger.info("🔍 Looking for message textarea...")
            try:
                message_textarea = self.driver.find_element(By.CSS_SELECTOR, 'textarea[name="messageBody"]')
                logger.info("✅ Found message textarea!")

                # Scroll to it
                self._smooth_scroll_to_element(message_textarea)
                self._random_delay(1, 2, "before clicking textarea")

                # Click to focus
                message_textarea.click()
                self._random_delay(0.5, 1, "after clicking textarea")

                # Clear any existing text (just in case)
                message_textarea.clear()
                self._random_delay(0.3, 0.6, "after clearing")

                # Type the message with human-like speed
                logger.info("⌨️  Typing message...")
                self._human_type(message_textarea, message_text)

                logger.info("✅ Message typed successfully!")

            except Exception as e:
                logger.error(f"❌ Failed to fill message: {e}")
                raise

            # Find and click submit button
            logger.info("🔍 Looking for submit button...")
            try:
                submit_button = self.driver.find_element(By.CSS_SELECTOR,
                    'button[type="submit"].ContactRequestForm-submit-btn-VBa, button[type="submit"]:contains("Nachricht senden")')
                logger.info("✅ Found submit button!")

                # Scroll to it
                self._smooth_scroll_to_element(submit_button)
                self._random_delay(1, 2, "before clicking submit")

                # Final pause before submission (looks more human - reading the message)
                logger.info("📖 Final review pause (looking human)...")
                self._random_delay(2, 4, "final review")

                # Click submit
                logger.info("🚀 CLICKING SUBMIT...")
                submit_button.click()

                logger.info("✅ SUBMIT CLICKED!")

                # Wait for submission to complete
                self._random_delay(3, 5, "waiting for submission")

                # Check for success indicators
                # (You might need to adjust these selectors based on ImmoScout's response)
                success_indicators = [
                    "Nachricht gesendet",
                    "erfolgreich",
                    "success",
                    "Vielen Dank"
                ]

                page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()

                success = any(indicator.lower() in page_text for indicator in success_indicators)

                if success:
                    logger.info("=" * 80)
                    logger.info("🎉 SUCCESS! Message sent successfully!")
                    logger.info("=" * 80)

                    # Save as contacted
                    self._save_contacted_listing(listing_url)
                    self._log_to_file(listing_url, "success", {"message_length": len(message_text)})

                    return True
                else:
                    logger.warning("⚠️  Submit clicked but no success confirmation found")
                    logger.debug(f"Page text snippet: {page_text[:200]}")

                    # Still save as contacted to avoid duplicates
                    self._save_contacted_listing(listing_url)
                    self._log_to_file(listing_url, "uncertain", {"message_length": len(message_text), "note": "No success confirmation"})

                    return True  # Assume success

            except Exception as e:
                logger.error(f"❌ Failed to click submit: {e}")
                raise

        except Exception as e:
            logger.error(f"❌ FAILED TO CONTACT LISTING: {e}")
            logger.debug(f"Error details: {type(e).__name__}: {str(e)}")

            # Log the failure
            self._log_to_file(listing_url, "error", {"error": str(e)})

            return False


if __name__ == "__main__":
    # Standalone test
    logger.info("🧪 Running standalone test")

    bot = ImmoscoutContactBot(
        headless=False,  # Visible browser for testing
        delay_min=1.5,   # SLOW
        delay_max=4.0,   # CAUTIOUS
    )

    try:
        # Start browser
        if not bot.start():
            logger.error("Failed to start browser")
            exit(1)

        # Try to load cookies
        if not bot.load_cookies():
            logger.info("No cookies found - need to login")

            # Wait for manual login
            if not bot.wait_for_manual_login(timeout=300):
                logger.error("Login failed or timed out")
                exit(1)

            # Save cookies for next time
            bot.save_cookies()

        logger.info("✅ Ready to contact listings!")
        logger.info("Modify the test listing URL below and run again.")

        # TEST LISTING URL - REPLACE WITH ACTUAL URL
        # test_url = "https://www.immobilienscout24.de/expose/123456"
        # bot.send_contact_message(test_url)

    finally:
        input("\nPress Enter to close browser...")
        bot.close()
