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
    def __init__(self, headless=False, delay_min=0.5, delay_max=2.0, enforce_mietprofil_sharing=False, mietprofil_stable_mode=False):
        """
        Initialize the bot with Chrome WebDriver
        Initialize the bot with Stealth Chrome WebDriver

        Args:
            headless: Run Chrome in headless mode (no visible browser)
            delay_min: Minimum delay between actions in seconds
            delay_max: Maximum delay between actions in seconds
            enforce_mietprofil_sharing: Actively enforce Mietprofil checkbox is checked
            mietprofil_stable_mode: Enable enhanced stealth and retry features for Mietprofil
        """
        self.options = webdriver.ChromeOptions()
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.enforce_mietprofil_sharing = enforce_mietprofil_sharing
        self.mietprofil_stable_mode = mietprofil_stable_mode

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

    def _wait_for_network_idle(self, timeout=3.0, idle_time=0.5):
        """
        Wait for network activity to become idle (stable mode feature).
        Uses performance API to detect when no new network requests are made.

        Args:
            timeout: Maximum time to wait in seconds
            idle_time: How long network must be idle to consider it stable

        Returns:
            True if network became idle, False if timeout
        """
        try:
            start_time = time.time()
            last_request_count = 0
            stable_since = None

            while time.time() - start_time < timeout:
                # Get current network request count via Performance API
                current_count = self.driver.execute_script(
                    "return window.performance.getEntriesByType('resource').length;"
                )

                if current_count == last_request_count:
                    # No new requests
                    if stable_since is None:
                        stable_since = time.time()
                    elif time.time() - stable_since >= idle_time:
                        logger.debug(f"✓ Network idle detected after {time.time() - start_time:.2f}s")
                        return True
                else:
                    # New requests detected, reset stability timer
                    stable_since = None
                    last_request_count = current_count

                time.sleep(0.1)

            logger.debug(f"Network idle timeout after {timeout}s")
            return False

        except Exception as e:
            logger.debug(f"Network idle check failed: {e}")
            return False

    def _get_comprehensive_checkbox_state(self, checkbox_element):
        """
        Get definitive checkbox state using multiple verification methods.

        Args:
            checkbox_element: The checkbox input element

        Returns:
            dict with state information and confidence level
        """
        state = {
            'is_selected': False,
            'js_checked': False,
            'has_checked_class': False,
            'svg_visible': False,
            'confidence': 'low',
            'checked': False
        }

        try:
            # Method 1: Selenium is_selected()
            state['is_selected'] = checkbox_element.is_selected()

            # Method 2: JavaScript checked property
            state['js_checked'] = self.driver.execute_script(
                "return document.getElementById('shareTenantProfile')?.checked === true;"
            )

            # Method 3: Check CSS classes on styled wrapper (React visual state)
            try:
                wrapper = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "div.Checkbox__StyledCheckbox-sc-7kkiwa-9, [data-testid='share-tenant-profile-checkbox'] ~ div"
                )
                wrapper_classes = wrapper.get_attribute('class') or ''
                # Some React checkbox implementations add a 'checked' class or similar
                state['has_checked_class'] = 'checked' in wrapper_classes.lower()
            except:
                pass

            # Method 4: Check if checkmark SVG is visible
            try:
                checkmark_svg = self.driver.find_element(
                    By.CSS_SELECTOR,
                    "svg.Checkbox__CheckboxIcon-sc-7kkiwa-0, .Checkbox__CheckboxInputWrapper-sc-7kkiwa-8 svg"
                )
                state['svg_visible'] = checkmark_svg.is_displayed()
            except:
                pass

            # Determine confidence and final state
            checks = [state['is_selected'], state['js_checked'], state['svg_visible']]
            true_count = sum(1 for c in checks if c)

            if true_count >= 2:
                state['confidence'] = 'high'
                state['checked'] = True
            elif true_count == 1:
                state['confidence'] = 'medium'
                state['checked'] = state['is_selected'] or state['js_checked']  # Trust these over SVG
            else:
                state['confidence'] = 'high'
                state['checked'] = False

            logger.debug(
                f"State check: is_selected={state['is_selected']}, "
                f"js_checked={state['js_checked']}, svg_visible={state['svg_visible']}, "
                f"confidence={state['confidence']}, final={state['checked']}"
            )

            return state

        except Exception as e:
            logger.debug(f"Comprehensive state check error: {e}")
            state['confidence'] = 'low'
            return state

    def _verify_checkbox_state_persistence(self, checkbox_element, expected_state, wait_time=0.5):
        """
        Verify that checkbox state persists after a delay (stable mode feature).
        Protects against React re-renders that might uncheck the box.

        Args:
            checkbox_element: The checkbox input element
            expected_state: Expected state (True for checked)
            wait_time: How long to wait before re-checking

        Returns:
            True if state persisted, False if changed
        """
        try:
            time.sleep(wait_time)
            final_state = self._get_comprehensive_checkbox_state(checkbox_element)

            if final_state['checked'] == expected_state:
                logger.debug(f"✓ State persistence verified: {expected_state}")
                return True
            else:
                logger.warning(f"✗ State changed! Expected {expected_state}, got {final_state['checked']}")
                return False

        except Exception as e:
            logger.debug(f"State persistence check error: {e}")
            return False

    def _ensure_element_in_viewport(self, element, description="element"):
        """
        Ensure element is in viewport before interacting (stable mode feature).
        Scrolls smoothly if needed to appear more human-like.

        Args:
            element: Selenium WebElement
            description: Description for logging

        Returns:
            True if element is/became visible in viewport
        """
        try:
            # Check if element is already in viewport
            in_viewport = self.driver.execute_script(
                """
                var elem = arguments[0];
                var rect = elem.getBoundingClientRect();
                return (
                    rect.top >= 0 &&
                    rect.left >= 0 &&
                    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                );
                """,
                element
            )

            if in_viewport:
                logger.debug(f"✓ {description} already in viewport")
                return True

            # Scroll element into view with smooth behavior (more human-like)
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                element
            )
            time.sleep(random.uniform(0.3, 0.5))  # Wait for smooth scroll

            logger.debug(f"✓ Scrolled {description} into viewport")
            return True

        except Exception as e:
            logger.debug(f"Viewport check/scroll error for {description}: {e}")
            return False

    def _enforce_mietprofil_checkbox(self, max_wait_seconds=3.0):
        """
        Robustly enforce that the Mietprofil (tenant profile) checkbox is checked.
        Waits for React components to fully load before interacting.

        FAST mode: Simple state verification, single attempt, 4 click strategies.
        STABLE mode: Network idle wait, 4-method state detection, persistence verification,
                     viewport scrolling, randomized strategies, and 3 retries with exponential backoff.

        Args:
            max_wait_seconds: Maximum time to wait for checkbox to be ready (default 3.0s)

        Returns:
            True if checkbox is successfully checked, False otherwise
        """
        mode = "STABLE" if self.mietprofil_stable_mode else "FAST"
        logger.info(f"Enforcing Mietprofil checkbox [{mode} mode]...")

        max_retries = 3 if self.mietprofil_stable_mode else 1
        base_backoff = 0.5

        for retry_attempt in range(max_retries):
            try:
                if retry_attempt > 0:
                    backoff_time = base_backoff * (2 ** (retry_attempt - 1))
                    logger.info(f"Retry attempt {retry_attempt + 1}/{max_retries} (backoff: {backoff_time}s)")
                    time.sleep(backoff_time)

                # STABLE MODE: Wait for network idle before proceeding
                if self.mietprofil_stable_mode:
                    logger.debug("Waiting for network idle...")
                    self._wait_for_network_idle(timeout=2.0, idle_time=0.5)

                # Wait for checkbox element to be present with variable delays (stealth)
                checkbox_element = None
                checkbox_stable = False

                # Use data-testid as primary selector (more stable than dynamic classes)
                selectors = [
                    (By.CSS_SELECTOR, "[data-testid='share-tenant-profile-checkbox']"),
                    (By.ID, "shareTenantProfile"),
                ]

                check_delay = 0.2
                max_attempts = int(max_wait_seconds / check_delay)

                for attempt in range(max_attempts):
                    # Variable delays in stable mode (more human-like)
                    if self.mietprofil_stable_mode and attempt > 0:
                        check_delay = random.uniform(0.15, 0.25)

                    try:
                        # Try multiple selectors
                        for selector_type, selector_value in selectors:
                            try:
                                checkbox_element = self.driver.find_element(selector_type, selector_value)
                                if checkbox_element:
                                    break
                            except NoSuchElementException:
                                continue

                        if not checkbox_element:
                            time.sleep(check_delay)
                            continue

                        # Verify wrapper exists (React hydration complete)
                        try:
                            wrapper = self.driver.find_element(
                                By.CSS_SELECTOR,
                                "div.Checkbox__StyledCheckbox-sc-7kkiwa-9, [data-testid='share-tenant-profile-checkbox'] ~ div"
                            )
                            if wrapper and checkbox_element:
                                checkbox_stable = True
                                logger.debug(f"✓ Checkbox stable (attempt {attempt + 1})")
                                break
                        except NoSuchElementException:
                            pass

                    except NoSuchElementException:
                        pass

                    time.sleep(check_delay)

                if not checkbox_stable or not checkbox_element:
                    logger.warning(f"Mietprofil checkbox not stable after {max_wait_seconds}s")
                    if retry_attempt < max_retries - 1:
                        continue
                    return False

                # Additional delay for React event handlers
                handler_delay = random.uniform(0.25, 0.35) if self.mietprofil_stable_mode else 0.3
                time.sleep(handler_delay)

                # STABLE MODE: Ensure element in viewport
                if self.mietprofil_stable_mode:
                    self._ensure_element_in_viewport(checkbox_element, "Mietprofil checkbox")

                # Check current state with comprehensive detection
                if self.mietprofil_stable_mode:
                    state = self._get_comprehensive_checkbox_state(checkbox_element)
                    is_checked = state['checked']
                    logger.debug(f"Initial state: {state['checked']} (confidence: {state['confidence']})")
                else:
                    # FAST mode: simple checks
                    is_checked = checkbox_element.is_selected()
                    js_checked = self.driver.execute_script(
                        "return document.getElementById('shareTenantProfile')?.checked === true;"
                    )
                    is_checked = is_checked or js_checked
                    logger.debug(f"Initial state: {is_checked}")

                if is_checked:
                    # STABLE MODE: Verify persistence
                    if self.mietprofil_stable_mode:
                        if self._verify_checkbox_state_persistence(checkbox_element, True, wait_time=0.5):
                            logger.info("✓ Mietprofil checkbox already checked (verified)")
                            return True
                        else:
                            logger.warning("State unstable, forcing re-check...")
                    else:
                        logger.info("✓ Mietprofil checkbox already checked")
                        return True

                # Checkbox not checked - enforce it
                logger.info("Mietprofil checkbox not checked - enforcing...")

                # Define click strategies (label first for stealth)
                strategies = [
                    ("click label", lambda: self.driver.find_element(
                        By.CSS_SELECTOR,
                        "label.Checkbox__CheckboxLabel-sc-7kkiwa-7, [for='shareTenantProfile']"
                    ).click()),
                    ("click input element", lambda: checkbox_element.click()),
                    ("click styled wrapper", lambda: self.driver.find_element(
                        By.CSS_SELECTOR,
                        "div.Checkbox__StyledCheckbox-sc-7kkiwa-9"
                    ).click()),
                    ("click via JavaScript", lambda: self.driver.execute_script(
                        "document.getElementById('shareTenantProfile')?.click();"
                    )),
                ]

                # STABLE MODE: Randomize strategy order (less predictable)
                if self.mietprofil_stable_mode:
                    random.shuffle(strategies)

                for strategy_name, strategy_func in strategies:
                    try:
                        strategy_func()

                        # Variable wait for React update
                        react_delay = random.uniform(0.2, 0.3) if self.mietprofil_stable_mode else 0.2
                        time.sleep(react_delay)

                        # Verify it's now checked
                        if self.mietprofil_stable_mode:
                            state_after = self._get_comprehensive_checkbox_state(checkbox_element)
                            success = state_after['checked']
                        else:
                            is_checked_after = checkbox_element.is_selected()
                            js_checked_after = self.driver.execute_script(
                                "return document.getElementById('shareTenantProfile')?.checked === true;"
                            )
                            success = is_checked_after or js_checked_after

                        if success:
                            # STABLE MODE: Verify persistence
                            if self.mietprofil_stable_mode:
                                if self._verify_checkbox_state_persistence(checkbox_element, True, wait_time=0.5):
                                    logger.info(f"✓ Checkbox enforced via {strategy_name} (verified)")
                                    return True
                                else:
                                    logger.warning(f"{strategy_name} succeeded but state didn't persist")
                                    continue
                            else:
                                logger.info(f"✓ Checkbox enforced via {strategy_name}")
                                return True
                        else:
                            logger.debug(f"  {strategy_name} clicked but not checked")

                    except Exception as e:
                        logger.debug(f"  {strategy_name} failed: {e}")
                        continue

                # All strategies failed this attempt
                if retry_attempt < max_retries - 1:
                    logger.warning(f"All strategies failed, will retry ({retry_attempt + 1}/{max_retries})...")
                    continue
                else:
                    logger.warning("✗ Failed to enforce Mietprofil checkbox after all retries")
                    return False

            except Exception as e:
                logger.error(f"Error in enforcement attempt {retry_attempt + 1}: {e}")
                if retry_attempt < max_retries - 1:
                    continue
                return False

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

                    # Mietprofil checkbox handling
                    if self.enforce_mietprofil_sharing:
                        # Enforce mode: Actively ensure checkbox is checked
                        self._enforce_mietprofil_checkbox()
                        self._random_delay(0.1, 0.2)
                    else:
                        # Default mode: Should be auto-checked for logged-in users
                        # We don't interact with it to avoid race conditions with React hydration
                        logger.info("Mietprofil checkbox should be auto-checked (logged-in users)")

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
