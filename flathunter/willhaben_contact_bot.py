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

    def _debug_log_element(self, element, description="element"):
        """
        Log comprehensive debug information about an element.

        Args:
            element: Selenium WebElement to debug
            description: Description for logging
        """
        try:
            logger.debug(f"=== DEBUG INFO FOR {description.upper()} ===")

            # Basic attributes
            logger.debug(f"  Tag: {element.tag_name}")
            logger.debug(f"  ID: {element.get_attribute('id') or 'N/A'}")
            logger.debug(f"  Name: {element.get_attribute('name') or 'N/A'}")
            logger.debug(f"  Type: {element.get_attribute('type') or 'N/A'}")
            logger.debug(f"  Class: {element.get_attribute('class') or 'N/A'}")
            logger.debug(f"  Data-testid: {element.get_attribute('data-testid') or 'N/A'}")

            # State
            logger.debug(f"  Displayed: {element.is_displayed()}")
            logger.debug(f"  Enabled: {element.is_enabled()}")
            logger.debug(f"  Selected: {element.is_selected()}")

            # Position & Size
            location = element.location
            size = element.size
            logger.debug(f"  Location: x={location['x']}, y={location['y']}")
            logger.debug(f"  Size: width={size['width']}, height={size['height']}")

            # Checked property (for checkboxes)
            checked_prop = self.driver.execute_script("return arguments[0].checked;", element)
            logger.debug(f"  Checked property (JS): {checked_prop}")

            # HTML structure
            outer_html = self.driver.execute_script("return arguments[0].outerHTML;", element)
            logger.debug(f"  HTML: {outer_html[:200]}...")

            # Computed CSS
            display = self.driver.execute_script("return window.getComputedStyle(arguments[0]).display;", element)
            visibility = self.driver.execute_script("return window.getComputedStyle(arguments[0]).visibility;", element)
            opacity = self.driver.execute_script("return window.getComputedStyle(arguments[0]).opacity;", element)
            pointer_events = self.driver.execute_script("return window.getComputedStyle(arguments[0]).pointerEvents;", element)
            logger.debug(f"  CSS display: {display}")
            logger.debug(f"  CSS visibility: {visibility}")
            logger.debug(f"  CSS opacity: {opacity}")
            logger.debug(f"  CSS pointer-events: {pointer_events}")

            # Parent info
            parent = self.driver.execute_script("return arguments[0].parentElement;", element)
            if parent:
                parent_tag = self.driver.execute_script("return arguments[0].tagName;", parent)
                parent_class = self.driver.execute_script("return arguments[0].className;", parent)
                logger.debug(f"  Parent: <{parent_tag}> class='{parent_class}'")

            logger.debug(f"=== END DEBUG INFO ===")

        except Exception as e:
            logger.error(f"Error logging debug info for {description}: {e}")

    def _get_mietprofil_checkbox(self, timeout=5):
        """
        Get the Mietprofil checkbox element with explicit wait.
        Uses XPath to find the checkbox within a label containing "Mietprofil teilen" text.

        Args:
            timeout: Maximum time to wait for element (default 5 seconds)

        Returns:
            WebElement if found, None if not found within timeout
        """
        try:
            # XPath that finds the checkbox input inside a label with "Mietprofil teilen" text
            xpath = "//form//label[.//span[contains(text(), 'Mietprofil teilen')]]/input[@type='checkbox']"

            checkbox = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            logger.debug("Found Mietprofil checkbox via XPath")
            return checkbox
        except TimeoutException:
            logger.warning(f"Mietprofil checkbox not found within {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Error finding Mietprofil checkbox: {e}")
            return None

    def _get_mietprofil_checkbox_state(self):
        """
        Check if Mietprofil checkbox is currently checked.

        Returns:
            True if checked, False if unchecked
        """
        try:
            checkbox = self._get_mietprofil_checkbox(timeout=3)
            if checkbox is None:
                logger.warning("Mietprofil checkbox not found - assuming unchecked")
                return False

            # Check via element property (most reliable)
            is_checked = checkbox.is_selected()
            logger.debug(f"Mietprofil checkbox state: {'checked' if is_checked else 'unchecked'}")
            return is_checked

        except Exception as e:
            logger.error(f"Error checking Mietprofil state: {e}")
            return False

    def _ensure_mietprofil_checked(self):
        """
        Ensure Mietprofil checkbox is checked before submission.
        Uses multiple strategies with extensive logging.
        BEST EFFORT - will try hard but won't block submission on failure.

        Returns:
            True if checkbox is checked (or we made it checked), False if failed
        """
        try:
            logger.info("=== STARTING MIETPROFIL CHECKBOX VERIFICATION ===")

            # Step 1: Find checkbox with multiple selectors
            checkbox = None
            selectors = [
                ("XPath (label text)", By.XPATH, "//form//label[.//span[contains(text(), 'Mietprofil teilen')]]/input[@type='checkbox']"),
                ("CSS (data-testid)", By.CSS_SELECTOR, "input[data-testid='share-tenant-profile-checkbox']"),
                ("ID", By.ID, "shareTenantProfile"),
                ("Name", By.CSS_SELECTOR, "input[name='shareTenantProfile']"),
            ]

            for selector_name, by_type, selector_value in selectors:
                try:
                    logger.debug(f"Trying selector: {selector_name}")
                    checkbox = WebDriverWait(self.driver, 2).until(
                        EC.presence_of_element_located((by_type, selector_value))
                    )
                    logger.info(f"✓ Found checkbox using: {selector_name}")
                    break
                except TimeoutException:
                    logger.debug(f"  Selector '{selector_name}' not found")
                    continue
                except Exception as e:
                    logger.debug(f"  Selector '{selector_name}' error: {e}")
                    continue

            if checkbox is None:
                logger.warning("⚠️ Cannot find Mietprofil checkbox - form may not have it or not loaded yet")
                logger.warning("Proceeding with submission anyway (best effort)")
                return False

            # Step 2: Log detailed debug info about the checkbox
            logger.info("Found Mietprofil checkbox - logging debug info...")
            self._debug_log_element(checkbox, "Mietprofil checkbox")

            # Step 3: Check current state
            is_checked_selected = checkbox.is_selected()
            is_checked_js = self.driver.execute_script("return arguments[0].checked;", checkbox)

            logger.info(f"Current state: is_selected()={is_checked_selected}, JS checked={is_checked_js}")

            if is_checked_selected or is_checked_js:
                logger.info("✓ Mietprofil already checked - no action needed")
                return True

            # Not checked - need to check it
            logger.warning("⚠️ Mietprofil NOT checked - attempting to check it now...")

            # Step 4: Try multiple click/check strategies
            strategies = []

            # Get label element for strategies that need it
            label = None
            try:
                label = self.driver.execute_script("return arguments[0].parentElement;", checkbox)
                if label:
                    logger.debug(f"Found parent label: <{label.tag_name}>")
                    self._debug_log_element(label, "Mietprofil label")
            except Exception as e:
                logger.warning(f"Could not get parent label: {e}")

            # Define all strategies
            strategies.append(("Regular click on label", lambda: label.click() if label else None))
            strategies.append(("JavaScript click on label", lambda: self.driver.execute_script("arguments[0].click();", label) if label else None))
            strategies.append(("Regular click on checkbox", lambda: checkbox.click()))
            strategies.append(("JavaScript click on checkbox", lambda: self.driver.execute_script("arguments[0].click();", checkbox)))
            strategies.append(("JavaScript set checked=true", lambda: self.driver.execute_script("arguments[0].checked = true;", checkbox)))
            strategies.append(("JavaScript set checked + dispatch change", lambda: self.driver.execute_script("""
                arguments[0].checked = true;
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('click', { bubbles: true }));
            """, checkbox)))
            strategies.append(("Send Space key to checkbox", lambda: checkbox.send_keys(Keys.SPACE)))

            # ActionChains strategy
            def action_chains_click():
                actions = ActionChains(self.driver)
                actions.move_to_element(checkbox).click().perform()

            strategies.append(("ActionChains click on checkbox", action_chains_click))

            # Scroll and click label
            def scroll_and_click_label():
                if label:
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", label)
                    time.sleep(0.2)
                    label.click()

            strategies.append(("Scroll into view + click label", scroll_and_click_label))

            # Try each strategy
            success = False
            for strategy_num, (strategy_name, strategy_func) in enumerate(strategies, 1):
                try:
                    logger.info(f"Strategy {strategy_num}/{len(strategies)}: {strategy_name}")

                    # Execute strategy
                    strategy_func()
                    logger.debug(f"  Executed {strategy_name}")

                    # Wait for any animations/React updates
                    time.sleep(0.4)

                    # Check if it worked
                    is_checked_after = checkbox.is_selected()
                    is_checked_js_after = self.driver.execute_script("return arguments[0].checked;", checkbox)

                    logger.debug(f"  After {strategy_name}: is_selected()={is_checked_after}, JS checked={is_checked_js_after}")

                    if is_checked_after or is_checked_js_after:
                        logger.info(f"✅ SUCCESS! {strategy_name} worked!")
                        success = True
                        break
                    else:
                        logger.warning(f"  Strategy '{strategy_name}' didn't check the box")

                except Exception as e:
                    logger.warning(f"  Strategy '{strategy_name}' failed: {e}")
                    continue

            # Step 5: Final verification
            if success:
                logger.info("✅ Mietprofil successfully checked!")
                return True
            else:
                logger.error("❌ All strategies failed - checkbox still not checked")
                logger.warning("⚠️ Proceeding with submission anyway (best effort)")
                return False

        except Exception as e:
            logger.error(f"Critical error in Mietprofil verification: {e}", exc_info=True)
            logger.warning("⚠️ Proceeding with submission anyway (best effort)")
            return False
        finally:
            logger.info("=== END MIETPROFIL CHECKBOX VERIFICATION ===")


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
