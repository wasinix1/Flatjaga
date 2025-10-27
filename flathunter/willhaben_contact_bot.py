#!/usr/bin/env python3
"""
Willhaben Auto-Contact Bot
Automatically sends contact messages to apartment listings
"""

import time
import random
import json
import os
import logging
import signal
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)


class SessionExpiredException(Exception):
    """Raised when willhaben session has expired and re-login is needed"""
    pass


class WillhabenContactBot:
    def __init__(self, headless=False, delay_min=0.5, delay_max=2.0):
        """
        Initialize the bot with Chrome WebDriver
        Initialize the bot with Stealth Chrome WebDriver

        Args:
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
        self.cookies_file = Path.home() / '.willhaben_cookies.json'
        self.contacted_file = Path.home() / '.willhaben_contacted.json'
        self.contacted_listings = self._load_contacted_listings()
        logger.info("Willhaben bot initialized")
    
    def _load_contacted_listings(self):
        """Load the list of already contacted listing IDs"""
        if self.contacted_file.exists():
            with open(self.contacted_file, 'r') as f:
                return set(json.load(f))
        return set()
    
    def _save_contacted_listing(self, listing_id):
        """Save a listing ID as contacted"""
        self.contacted_listings.add(listing_id)
        with open(self.contacted_file, 'w') as f:
            json.dump(list(self.contacted_listings), f)
    
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
        """Handle any popups that might appear (cookies, privacy, security).
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
                    if "ja, ich stimme zu" in button.text.lower():
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

    def accept_cookies(self):
        """Accept cookie banner if it appears - uses new popup handler"""
        return self._handle_popups()

    def accept_privacy_popup(self):
        """Accept privacy popup if it appears - uses new popup handler"""
        return self._handle_popups()
    
    def start(self):
        """Start the Chrome WebDriver"""
        self.driver = webdriver.Chrome(options=self.options)
        print("✓ Browser started")
        logger.info("Browser started for Willhaben")
    
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
                print("✓ Browser closed")
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

                print("✓ Browser closed (forced)")
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
    
    def save_cookies(self):
        """Save cookies to file for session persistence"""
        cookies = self.driver.get_cookies()
        with open(self.cookies_file, 'w') as f:
            json.dump(cookies, f)
        print(f"✓ Cookies saved to {self.cookies_file}")
    
    def load_cookies(self):
        """Load cookies from file to resume session"""
        if not self.cookies_file.exists():
            return False

        # Need to visit the domain first before adding cookies
        self.driver.get('https://www.willhaben.at')
        # Brief delay to let domain load before adding cookies
        time.sleep(0.1)

        with open(self.cookies_file, 'r') as f:
            cookies = json.load(f)

        for cookie in cookies:
            # Selenium doesn't like some cookie fields
            if 'expiry' in cookie:
                cookie['expiry'] = int(cookie['expiry'])
            self.driver.add_cookie(cookie)

        print("✓ Cookies loaded")
        return True

    def login_manual(self):
        """
        Open login page and wait for user to login manually
        Then save the session cookies
        """
        print("\n=== Manual Login Required ===")
        print("1. The browser will open to the Willhaben login page")
        print("2. Please login with your credentials")
        print("3. Once logged in, come back here and press Enter")
        print("=============================\n")
        
        # Navigate to main page first, then click login to trigger SSO
        self.driver.get('https://www.willhaben.at')
        self._random_delay(1, 2)
        
        # Try to find and click the login button
        try:
            login_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Anmelden"))
            )
            login_button.click()
            self._random_delay(1, 2)
        except:
            # If can't find button, just go to SSO directly
            self.driver.get('https://sso.willhaben.at/auth/realms/willhaben/protocol/openid-connect/auth?response_type=code&client_id=bbx-bff&scope=openid&redirect_uri=https://www.willhaben.at/webapi/oauth2/code/sso')
            self._random_delay(1, 2)
        
        input("Press Enter once you've logged in successfully...")
        
        # Save the session
        self.save_cookies()
        print("✓ Login session saved!")
    
    def is_already_contacted(self, listing_url):
        """Check if we've already contacted this listing"""
        # Extract listing ID from URL (usually the last part)
        listing_id = listing_url.rstrip('/').split('/')[-1]
        return listing_id in self.contacted_listings
    
    def send_contact_message(self, listing_url):
        """
        Send a contact message to a specific listing with adaptive form detection.

        Args:
            listing_url: Full URL to the willhaben listing

        Returns:
            True if message sent successfully, False otherwise
        """
        # Check if already contacted
        if self.is_already_contacted(listing_url):
            logger.info(f"Already contacted: {listing_url}")
            return False

        listing_id = listing_url.rstrip('/').split('/')[-1]

        try:
            logger.info(f"Opening listing: {listing_url}")
            self.driver.get(listing_url)
            self._random_delay(0.5, 1.0)

            # Quick check if we got redirected to login page
            if 'sso.willhaben.at' in self.driver.current_url:
                logger.error("Session expired - redirected to login")
                raise SessionExpiredException("Session expired")

            # Handle popups that might appear on page load
            self._handle_popups()
            self._random_delay(0.3, 0.6)

            # Adaptive form detection - try multiple approaches
            form_found = False
            form_type = None
            submit_button = None
            max_attempts = 15

            logger.info("Looking for contact form...")
            for attempt in range(max_attempts):
                self._random_delay(0.3, 0.5)

                if attempt > 0 and attempt % 5 == 0:
                    logger.debug(f"Still looking for form/button... (attempt {attempt+1}/{max_attempts})")

                # Check for popups at any time
                self._handle_popups()

                # Try to find email form (company listings)
                if not form_found:
                    try:
                        email_form = self.driver.find_element(By.CSS_SELECTOR, 'form[data-testid="ad-contact-form-email"]')
                        if email_form.is_displayed():
                            form_type = "email"
                            form_found = True
                            logger.info("Found company listing form (email)")
                            continue
                    except:
                        pass

                # Try to find messaging form (private listings)
                if not form_found:
                    try:
                        messaging_form = self.driver.find_element(By.CSS_SELECTOR, 'form[data-testid="ad-contact-form-messaging"]')
                        if messaging_form.is_displayed():
                            form_type = "messaging"
                            form_found = True
                            logger.info("Found private listing form (messaging)")
                            continue
                    except:
                        pass

                # If form found, process it
                if form_found and form_type == "email":
                    # Email form: Check boxes
                    # Viewing checkbox (optional)
                    try:
                        viewing_checkbox = self.driver.find_element(By.ID, "contactSuggestions-6")
                        if viewing_checkbox and not viewing_checkbox.is_selected():
                            self._try_click_element(viewing_checkbox, "viewing checkbox")
                            logger.info("✓ Checked viewing option")
                            self._random_delay(0.1, 0.2)
                        else:
                            logger.debug("Viewing checkbox already selected")
                    except Exception as e:
                        logger.debug(f"Viewing checkbox not found or not available: {e}")

                    # Mietprofil checkbox (CRITICAL - must always be checked)
                    # Smart wait: Check if JavaScript has populated checkbox state (max 5 attempts over ~1.5s)
                    try:
                        mietprofil_checkbox = self.driver.find_element(By.ID, "shareTenantProfile")

                        checkbox_checked = False
                        for check_attempt in range(5):
                            is_selected = mietprofil_checkbox.is_selected()
                            has_checked_attr = self.driver.execute_script("return arguments[0].checked;", mietprofil_checkbox)

                            if is_selected or has_checked_attr:
                                checkbox_checked = True
                                logger.info(f"✓ Mietprofil checkbox already checked (detected on check #{check_attempt+1})")
                                break

                            # Quick delay between checks (total ~1.5s max if not checked)
                            if check_attempt < 4:
                                time.sleep(0.3)

                        # Get full diagnostic info for logging
                        is_selected = mietprofil_checkbox.is_selected()
                        is_displayed = mietprofil_checkbox.is_displayed()
                        is_enabled = mietprofil_checkbox.is_enabled()
                        has_disabled_attr = self.driver.execute_script("return arguments[0].disabled;", mietprofil_checkbox)
                        has_checked_attr = self.driver.execute_script("return arguments[0].checked;", mietprofil_checkbox)

                        logger.info(f"Mietprofil checkbox state: selected={is_selected}, displayed={is_displayed}, "
                                   f"is_enabled()={is_enabled}, disabled_attr={has_disabled_attr}, checked_attr={has_checked_attr}")

                        if checkbox_checked:
                            pass  # Already logged above, nothing more to do
                        else:
                            # Checkbox is NOT checked - we MUST check it
                            logger.warning("⚠️ Mietprofil checkbox is NOT checked - attempting to check it...")

                            # Try multiple strategies to check the box
                            success = False

                            # Strategy 1: Direct JavaScript click (bypasses visibility/enabled checks)
                            try:
                                self.driver.execute_script("arguments[0].click();", mietprofil_checkbox)
                                self._random_delay(0.2, 0.3)
                                if mietprofil_checkbox.is_selected():
                                    logger.info("✓ Mietprofil checked via JavaScript click")
                                    success = True
                            except Exception as e:
                                logger.debug(f"JavaScript click failed: {e}")

                            # Strategy 2: Click the label (often works for styled checkboxes)
                            if not success:
                                try:
                                    label = self.driver.find_element(By.CSS_SELECTOR, 'label[for="shareTenantProfile"]')
                                    if not label:
                                        # Try finding by the checkbox's parent label
                                        label = self.driver.execute_script("return arguments[0].closest('label');", mietprofil_checkbox)
                                    if label:
                                        self.driver.execute_script("arguments[0].click();", label)
                                        self._random_delay(0.2, 0.3)
                                        if mietprofil_checkbox.is_selected():
                                            logger.info("✓ Mietprofil checked via label click")
                                            success = True
                                except Exception as e:
                                    logger.debug(f"Label click failed: {e}")

                            # Strategy 3: Set checked property directly via JavaScript
                            if not success:
                                try:
                                    self.driver.execute_script("""
                                        arguments[0].checked = true;
                                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                                        arguments[0].dispatchEvent(new Event('click', { bubbles: true }));
                                    """, mietprofil_checkbox)
                                    self._random_delay(0.2, 0.3)
                                    if mietprofil_checkbox.is_selected():
                                        logger.info("✓ Mietprofil checked via JavaScript property + events")
                                        success = True
                                except Exception as e:
                                    logger.debug(f"JavaScript property set failed: {e}")

                            # Final verification
                            final_state = mietprofil_checkbox.is_selected()
                            if success or final_state:
                                logger.info(f"✓ Mietprofil checkbox is NOW checked (final verification: {final_state})")
                            else:
                                logger.error("❌ CRITICAL: All strategies failed - Mietprofil checkbox NOT checked!")
                                logger.error(f"   This means the Mietprofil will NOT be sent with the contact request!")

                        self._random_delay(0.1, 0.2)
                    except NoSuchElementException:
                        logger.warning("⚠️ Mietprofil checkbox not found on this page (might not be available for this listing type)")
                    except Exception as e:
                        logger.error(f"❌ CRITICAL: Could not find/check Mietprofil checkbox: {e}")

                    # Find submit button
                    try:
                        submit_button = self.driver.find_element(By.CSS_SELECTOR, 'button[data-testid="ad-request-send-mail"]')
                        if submit_button and submit_button.is_displayed() and submit_button.is_enabled():
                            logger.info("Found email submit button")
                            break  # Exit loop - button found
                    except Exception as e:
                        logger.debug(f"Could not find email submit button yet: {e}")

                elif form_found and form_type == "messaging":
                    # Messaging form: Check if textarea needs filling
                    # Wait for pre-filled content to load (for logged-in users with saved messages)
                    try:
                        message_textarea = self.driver.find_element(By.ID, "mailContent")
                        if message_textarea:
                            # Smart wait: Check for pre-filled content (max 5 attempts over ~1.5s)
                            has_content = False
                            for check_attempt in range(5):
                                existing_value = message_textarea.get_attribute("value") or ""
                                existing_text = self.driver.execute_script("return arguments[0].value;", message_textarea) or ""

                                if existing_value.strip() or existing_text.strip():
                                    has_content = True
                                    logger.info(f"✓ Pre-filled message detected (check #{check_attempt+1})")
                                    break

                                # Quick delay between checks (total ~1.5s max if no content found)
                                if check_attempt < 4:
                                    time.sleep(0.3)

                            if has_content:
                                logger.info("Using pre-saved message template")
                                self._random_delay(0.1, 0.2)
                            else:
                                # No pre-filled content found after waiting - fill with default
                                message_text = "Guten Tag,\n\nich interessiere mich für diese Wohnung und würde gerne einen Besichtigungstermin vereinbaren.\n\nMit freundlichen Grüßen"
                                message_textarea.send_keys(message_text)
                                logger.warning("No pre-filled message found - using default message")
                                self._random_delay(0.1, 0.3)
                    except Exception as e:
                        logger.debug(f"Could not check/fill message field: {e}")

                    # Find submit button
                    try:
                        submit_button = self.driver.find_element(By.CSS_SELECTOR, 'button[data-testid="ad-request-send-message"]')
                        if submit_button and submit_button.is_displayed() and submit_button.is_enabled():
                            logger.info("Found message submit button")
                            break  # Exit loop - button found
                    except Exception as e:
                        logger.debug(f"Could not find message submit button yet: {e}")

            if not form_found:
                logger.error(f"Could not find contact form after {max_attempts} attempts")
                return False

            if not submit_button:
                logger.error(f"Could not find submit button after {max_attempts} attempts (form_type={form_type})")
                return False

            # Submit the form with multiple click strategies
            logger.info(f"Submitting form (type: {form_type})")
            self._random_delay(0.2, 0.4)

            if not self._try_click_element(submit_button, "submit button"):
                logger.error("Failed to click submit button")
                return False

            logger.info("Form submitted")
            self._random_delay(0.5, 1.0)

            # Handle any popups after submission
            self._handle_popups()
            self._random_delay(0.3, 0.6)

            # Check for success message
            logger.info("Waiting for confirmation...")
            success_found = False
            for attempt in range(10):
                self._random_delay(0.3, 0.5)
                try:
                    success_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'wurde erfolgreich')]")
                    if success_elements and any(el.is_displayed() for el in success_elements):
                        success_found = True
                        break
                except:
                    pass

            if success_found:
                self._save_contacted_listing(listing_id)
                logger.info(f"✓ Message sent successfully to {listing_id}")
                return True
            else:
                logger.warning("Could not confirm message was sent")
                return False

        except SessionExpiredException:
            raise
        except TimeoutException:
            logger.error(f"Timeout waiting for contact form on {listing_url}")
            return False
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False
    
    def test_single_listing(self, listing_url):
        """
        Test the bot on a single listing
        Good for debugging and initial testing
        """
        print("\n=== Testing Single Listing ===")
        
        self.start()
        
        # Try to load existing session
        if self.load_cookies():
            print("✓ Using saved session")
        else:
            print("! No saved session found")
            self.login_manual()
        
        # Refresh to apply cookies
        self.driver.get('https://www.willhaben.at')
        self._random_delay()
        
        # Accept cookies if needed
        self.accept_cookies()
        
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
    print("Willhaben Auto-Contact Bot")
    print("=" * 50)
    
    # Get listing URL from user
    print("\nPaste a Willhaben listing URL to test:")
    listing_url = input("> ").strip()
    
    if not listing_url:
        print("No URL provided, exiting...")
        return
    
    # Create bot and test
    bot = WillhabenContactBot(headless=False)
    bot.test_single_listing(listing_url)


if __name__ == "__main__":
    main()
