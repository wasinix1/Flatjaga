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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
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

    def _wait_for_react_stability(self, timeout=3.0):
        """
        Wait for React components to stabilize before interacting with the form.
        Monitors DOM mutations and waits for them to settle.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if stable, False if timeout
        """
        try:
            stability_script = """
            return new Promise((resolve) => {
                let timeoutId;
                const observer = new MutationObserver(() => {
                    clearTimeout(timeoutId);
                    timeoutId = setTimeout(() => {
                        observer.disconnect();
                        resolve(true);
                    }, 300);
                });

                observer.observe(document.body, {
                    childList: true,
                    subtree: true,
                    attributes: true
                });

                // Initial timeout
                timeoutId = setTimeout(() => {
                    observer.disconnect();
                    resolve(true);
                }, 300);

                // Safety timeout
                setTimeout(() => {
                    observer.disconnect();
                    resolve(false);
                }, arguments[0] * 1000);
            });
            """
            result = self.driver.execute_async_script(stability_script, timeout)
            if result:
                logger.debug("✓ React components stabilized")
            else:
                logger.debug("React stability timeout - proceeding anyway")
            return result
        except Exception as e:
            logger.debug(f"React stability check failed: {e} - proceeding anyway")
            return False

    def _get_mietprofil_checkbox(self, timeout=5):
        """
        Get the Mietprofil teilen checkbox element.

        Returns:
            WebElement if found, None if not found
        """
        try:
            wait = WebDriverWait(self.driver, timeout)
            # Clean XPath without //form// prefix for better compatibility
            xpath = "//label[.//span[contains(text(), 'Mietprofil teilen')]]/input[@type='checkbox']"

            checkbox = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            logger.debug(f"✓ Found Mietprofil checkbox")
            return checkbox
        except TimeoutException:
            logger.debug(f"Mietprofil checkbox not found within {timeout}s")
            return None
        except Exception as e:
            logger.debug(f"Error finding Mietprofil checkbox: {e}")
            return None

    def _verify_mietprofil_state(self):
        """
        Verify Mietprofil checkbox state using both DOM and FormData.
        FormData is what actually gets submitted - this is the source of truth.

        Returns:
            Tuple[bool, bool]: (is_checked_in_formdata, needs_manual_check)
            - is_checked_in_formdata: True if checkbox is in FormData (will be submitted)
            - needs_manual_check: True if state couldn't be determined reliably
        """
        verify_script = """
        const checkbox = document.evaluate(
            "//label[.//span[contains(text(), 'Mietprofil teilen')]]/input[@type='checkbox']",
            document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
        ).singleNodeValue;

        if (!checkbox) return {error: "not_found"};

        const form = checkbox.closest('form');
        if (!form) return {error: "no_form"};

        const formData = new FormData(form);
        const inFormData = formData.has(checkbox.name);

        return {
            dom_checked: checkbox.checked,
            in_formdata: inFormData,
            checkbox_name: checkbox.name
        };
        """

        try:
            result = self.driver.execute_script(verify_script)

            if result.get('error'):
                logger.debug(f"Mietprofil checkbox check: {result.get('error')}")
                return False, True  # Not found, needs manual verification

            dom_checked = result.get('dom_checked')
            in_formdata = result.get('in_formdata')

            logger.info(f"Mietprofil state: DOM={dom_checked}, FormData={in_formdata}")

            # IDEAL: Both true (logged-in user with profile)
            if dom_checked and in_formdata:
                logger.info("✓ Mietprofil checked and in FormData")
                return True, False

            # BAD: Not in FormData (even if DOM shows checked)
            if not in_formdata:
                logger.warning("⚠️  Mietprofil NOT in FormData - profile won't be shared")
                return False, True

            # EDGE: In FormData but DOM unchecked (shouldn't happen)
            return in_formdata, False

        except Exception as e:
            logger.warning(f"Error verifying Mietprofil state: {e}")
            return False, True  # Error, needs manual verification

    def _apply_js_event_strategy(self):
        """
        Apply JS full event simulation strategy to check the Mietprofil checkbox.
        Simulates complete mouse interaction with proper event bubbling.
        """
        try:
            self.driver.execute_script("""
                const checkbox = document.evaluate(
                    "//label[.//span[contains(text(), 'Mietprofil teilen')]]/input[@type='checkbox']",
                    document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                ).singleNodeValue;

                if (checkbox) {
                    const events = [
                        new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}),
                        new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}),
                        new MouseEvent('click', {bubbles: true, cancelable: true, view: window}),
                    ];

                    events.forEach(event => checkbox.dispatchEvent(event));
                    checkbox.dispatchEvent(new Event('change', {bubbles: true}));
                    checkbox.dispatchEvent(new Event('input', {bubbles: true}));
                }
            """)
            logger.debug("Applied JS event simulation strategy")
        except Exception as e:
            logger.debug(f"JS event strategy failed: {e}")
            raise

    def _apply_selenium_actions_strategy(self):
        """
        Apply Selenium ActionChains strategy to check the Mietprofil checkbox.
        Uses native Selenium interaction for maximum compatibility.
        """
        try:
            checkbox = self.driver.find_element(By.XPATH,
                "//label[.//span[contains(text(), 'Mietprofil teilen')]]/input[@type='checkbox']")

            actions = ActionChains(self.driver)
            actions.move_to_element(checkbox).click().perform()
            logger.debug("Applied Selenium ActionChains strategy")
        except Exception as e:
            logger.debug(f"Selenium actions strategy failed: {e}")
            raise

    def _attempt_mietprofil_check(self):
        """
        Attempt to check the Mietprofil checkbox using proven strategies.
        Tries JS event simulation first, then Selenium actions as fallback.

        Returns:
            True if checkbox is successfully checked, False otherwise
        """
        strategies = [
            ("JS Full Event Simulation", self._apply_js_event_strategy),
            ("Selenium ActionChains", self._apply_selenium_actions_strategy)
        ]

        for strategy_name, strategy_func in strategies:
            logger.info(f"Attempting: {strategy_name}")

            try:
                strategy_func()
                time.sleep(1.0)  # Wait for React to update

                # Verify it worked
                is_checked, _ = self._verify_mietprofil_state()
                if is_checked:
                    logger.info(f"✓ Success with: {strategy_name}")
                    return True
                else:
                    logger.warning(f"Strategy '{strategy_name}' executed but checkbox still not checked")
            except Exception as e:
                logger.warning(f"Strategy '{strategy_name}' failed: {e}")
                continue

        logger.error("All strategies failed to check Mietprofil")
        return False

    def _ensure_mietprofil_checked(self):
        """
        Ensure Mietprofil checkbox is checked before submission.
        Production-ready orchestration: stabilize → scroll → verify → check → verify.
        BEST EFFORT - tries hard but won't block submission on failure.

        Returns:
            True if checkbox is verified as checked, False otherwise
        """
        try:
            logger.info("🔍 Verifying Mietprofil checkbox...")

            # Step 1: Wait for React components to stabilize
            logger.debug("Waiting for React stability...")
            self._wait_for_react_stability(timeout=3.0)

            # Step 2: Find the checkbox
            checkbox = self._get_mietprofil_checkbox(timeout=5)
            if checkbox is None:
                logger.warning("⚠️  Mietprofil checkbox not found (form may not have it)")
                return False

            # Step 3: Scroll checkbox into view
            logger.debug("Scrolling checkbox into view...")
            try:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});",
                    checkbox
                )
                time.sleep(0.3)  # Allow smooth scroll to complete
            except Exception as e:
                logger.debug(f"Scroll failed: {e} - continuing anyway")

            # Step 4: Verify current state
            is_checked, needs_check = self._verify_mietprofil_state()

            if is_checked:
                logger.info("✅ Mietprofil already checked and in FormData")
                return True

            if not needs_check:
                # State is clear but checkbox is not checked - this shouldn't happen
                logger.warning("Unexpected state: clear but not checked - will attempt to check")

            # Step 5: Checkbox not checked - attempt to check it
            logger.warning("⚠️  Mietprofil NOT checked - attempting to check it...")

            # Only attempt if we're certain it needs checking
            if needs_check or not is_checked:
                success = self._attempt_mietprofil_check()

                if success:
                    logger.info("✅ Mietprofil successfully checked")
                    return True
                else:
                    logger.error("❌ Failed to check Mietprofil checkbox")
                    return False

            # Shouldn't reach here, but default to False
            return False

        except Exception as e:
            logger.error(f"Critical error in Mietprofil verification: {e}", exc_info=True)
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
        self.wait = WebDriverWait(self.driver, 10)  # Default 10s timeout
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

            # Final check: Ensure Mietprofil is checked before submission (email forms only)
            # BEST EFFORT - we try to check it, but don't block submission if it fails
            if form_type == "email":
                logger.info("Verifying Mietprofil checkbox before submission...")
                checkbox_result = self._ensure_mietprofil_checked()
                if checkbox_result:
                    logger.info("✅ Mietprofil checkbox verified and checked")
                else:
                    logger.warning("⚠️ Mietprofil checkbox verification failed - continuing with submission anyway")
                    logger.warning("The message will still be sent, but may not include tenant profile")

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
