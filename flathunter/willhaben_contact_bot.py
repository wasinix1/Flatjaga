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

# SSL FIX (before any HTTPS usage)
try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
except ImportError:
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass

logger = logging.getLogger(__name__)


class SessionExpiredException(Exception):
    """Raised when willhaben session has expired and re-login is needed"""
    pass


class AlreadyContactedException(Exception):
    """Raised when a listing has already been contacted"""
    pass


class WillhabenContactBot:
    def __init__(self, headless=False, delay_min=0.5, delay_max=2.0, use_stealth=False):
        """
        Initialize the bot with Chrome WebDriver or StealthDriver

        Args:
            headless: Run Chrome in headless mode (no visible browser)
            delay_min: Minimum delay between actions in seconds
            delay_max: Maximum delay between actions in seconds
            use_stealth: Use StealthDriver with undetected-chromedriver (default: False)
        """
        self.headless = headless
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.use_stealth = use_stealth
        self.driver = None
        self.stealth_driver = None  # For StealthDriver wrapper

        # Setup options for regular Chrome
        self.options = webdriver.ChromeOptions()

        if not use_stealth:
            # Regular Chrome setup
            if headless:
                self.options.add_argument('--headless')

            # Basic stealth features (always enabled)
            self.options.add_argument('--disable-blink-features=AutomationControlled')
            self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
            self.options.add_experimental_option('useAutomationExtension', False)

        self.cookies_file = Path.home() / '.willhaben_cookies.json'
        self.contacted_file = Path.home() / '.willhaben_contacted.json'
        self.contacted_listings = self._load_contacted_listings()

        stealth_mode = "stealth" if use_stealth else "standard"
        logger.info(f"Willhaben bot initialized (mode: {stealth_mode}, headless: {headless})")
    
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

        if self.use_stealth and self.stealth_driver:
            # Use StealthDriver's smart delay (includes random pauses)
            self.stealth_driver.smart_delay(min_sec, max_sec)
        else:
            # Standard random delay
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

        // Additional debugging info
        let formDataValue = null;
        for (let [key, value] of formData.entries()) {
            if (key === checkbox.name) {
                formDataValue = value;
                break;
            }
        }

        return {
            dom_checked: checkbox.checked,
            in_formdata: inFormData,
            checkbox_name: checkbox.name,
            checkbox_id: checkbox.id,
            checkbox_value: checkbox.value,
            formdata_value: formDataValue
        };
        """

        try:
            result = self.driver.execute_script(verify_script)

            if result.get('error'):
                logger.debug(f"Mietprofil checkbox check: {result.get('error')}")
                return False, True  # Not found, needs manual verification

            dom_checked = result.get('dom_checked')
            in_formdata = result.get('in_formdata')
            checkbox_name = result.get('checkbox_name')
            checkbox_id = result.get('checkbox_id')
            formdata_value = result.get('formdata_value')

            logger.info(f"Mietprofil state: DOM={dom_checked}, FormData={in_formdata}")
            logger.debug(f"  Checkbox details: name='{checkbox_name}', id='{checkbox_id}', formdata_value={formdata_value}")

            # IMPORTANT: DOM checked is what matters for checkboxes!
            # FormData for checkboxes can be unreliable - if DOM shows checked, trust it
            if dom_checked:
                if in_formdata:
                    logger.info("✓ Mietprofil checked (DOM + FormData both confirm)")
                else:
                    logger.info("✓ Mietprofil checked (DOM confirms, FormData may update on submit)")
                return True, False

            # DOM shows unchecked - definitely not checked
            if not dom_checked:
                logger.warning("⚠️  Mietprofil NOT checked (DOM confirms)")
                return False, True

            # Shouldn't reach here
            return False, True

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

    def _load_message_template(self):
        """
        Load active message template from JSON config file.

        Returns:
            str: Message text from active template, or hardcoded fallback on error
        """
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config', 'message_templates.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            active_id = config.get('active_template_id', 1)
            templates = config.get('templates', [])

            # Find active template by ID
            for template in templates:
                if template.get('id') == active_id:
                    text = template.get('text', '')
                    if text:
                        logger.debug(f"Loaded template ID {active_id} from config")
                        return text

            # Fallback to first template if active_id not found
            if templates and templates[0].get('text'):
                logger.warning(f"Template ID {active_id} not found, using first available template")
                return templates[0].get('text', '')

            raise ValueError("No valid templates found in config")

        except Exception as e:
            logger.warning(f"Could not load template from JSON ({e}), using hardcoded fallback")
            return "Guten Tag,\n\nich interessiere mich für diese Wohnung und würde gerne einen Besichtigungstermin vereinbaren.\n\nMit freundlichen Grüßen"

    def _verify_message_prefill(self, message_textarea, max_attempts=3):
        """
        Verify if message textarea has pre-filled content with 100% certainty.
        Waits for React stability and checks multiple times to ensure accuracy.

        Args:
            message_textarea: WebElement of the textarea
            max_attempts: Maximum number of verification attempts

        Returns:
            bool: True if pre-filled content is present, False if truly empty
        """
        try:
            logger.debug("Verifying message pre-fill status...")

            # Wait for React stability first
            self._wait_for_react_stability(timeout=3.0)

            # Scroll textarea into view
            try:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});",
                    message_textarea
                )
                time.sleep(0.2)
            except Exception as e:
                logger.debug(f"Scroll failed: {e} - continuing anyway")

            # Multiple verification checks with different methods
            for attempt in range(max_attempts):
                # Method 1: Selenium getAttribute
                value_attr = message_textarea.get_attribute("value") or ""

                # Method 2: JavaScript .value property
                value_js = self.driver.execute_script("return arguments[0].value;", message_textarea) or ""

                # Method 3: JavaScript textContent
                text_content = self.driver.execute_script("return arguments[0].textContent;", message_textarea) or ""

                # Method 4: Selenium .text property
                selenium_text = message_textarea.text or ""

                # Check if any method found content
                if value_attr.strip() or value_js.strip() or text_content.strip() or selenium_text.strip():
                    logger.info(f"✓ Pre-filled message detected (attempt {attempt + 1}/{max_attempts})")
                    logger.debug(f"  Content length: {max(len(value_attr), len(value_js), len(text_content), len(selenium_text))} chars")
                    return True

                # Wait before next check (with increasing intervals)
                if attempt < max_attempts - 1:
                    wait_time = 0.3 + (attempt * 0.1)  # 0.3s, 0.4s, 0.5s, etc.
                    time.sleep(wait_time)

            # After all attempts, confirmed empty
            logger.info(f"✓ Confirmed: No pre-filled message (verified {max_attempts} times)")
            return False

        except Exception as e:
            logger.warning(f"Error verifying message pre-fill: {e}")
            # On error, assume empty to be safe (will fill with default)
            return False

    def _ensure_message_filled(self):
        """
        Ensure message textarea is filled before submission.
        Production-ready orchestration: find → verify → fill if needed.
        BEST EFFORT - tries hard but won't block submission on failure.

        Returns:
            True if message field has content (pre-filled or filled), False otherwise
        """
        try:
            logger.info("🔍 Verifying message field...")

            # Step 1: Find the message textarea
            try:
                message_textarea = self.driver.find_element(By.ID, "mailContent")
            except Exception as e:
                logger.warning(f"⚠️  Message textarea not found: {e}")
                return False

            # Check if config enforces template usage over pre-fill
            try:
                config_path = os.path.join(os.path.dirname(__file__), 'config', 'message_templates.json')
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                enforce_template = config.get('use_template_over_prefill', False)
            except:
                enforce_template = False

            # Step 2: Verify if pre-filled (unless config enforces template)
            if enforce_template:
                logger.info("Config enforces template usage - skipping pre-fill check")
            else:
                has_prefill = self._verify_message_prefill(message_textarea, max_attempts=3)
                if has_prefill:
                    logger.info("✅ Using pre-filled message template")
                    return True

            # Step 3: No pre-fill - fill with template text
            logger.info("Filling message field with default text...")
            try:
                message_text = self._load_message_template()
                message_textarea.send_keys(message_text)
                logger.info("✅ Message field filled with default text")
                return True
            except Exception as e:
                logger.error(f"❌ Failed to fill message field: {e}")
                return False

        except Exception as e:
            logger.error(f"Critical error in message field verification: {e}", exc_info=True)
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
        """Start the Chrome WebDriver (regular or stealth)"""
        if self.use_stealth:
            # Use StealthDriver
            from flathunter.stealth_driver import StealthDriver
            self.stealth_driver = StealthDriver(headless=self.headless)
            self.stealth_driver.start()
            self.driver = self.stealth_driver.driver
            logger.info("Stealth browser started for Willhaben")
        else:
            # Use regular Chrome
            self.driver = webdriver.Chrome(options=self.options)
            logger.info("Browser started for Willhaben")

        self.wait = WebDriverWait(self.driver, 10)  # Default 10s timeout
        print("✓ Browser started")
    
    def close(self):
        """Close the browser with timeout to prevent hanging"""
        if not self.driver:
            return

        if self.use_stealth and self.stealth_driver:
            # Use StealthDriver's quit method
            try:
                self.stealth_driver.quit()
                print("✓ Browser closed")
            except Exception as e:
                logger.error(f"Error closing stealth browser: {e}")
            return

        # Regular Chrome cleanup with timeout protection
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
            raise AlreadyContactedException(f"Already contacted: {listing_url}")

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
                    # Viewing checkbox (optional) - JS click + verify
                    try:
                        viewing_checkbox = self.driver.find_element(By.ID, "contactSuggestions-6")
                        self.driver.execute_script("arguments[0].click();", viewing_checkbox)
                        time.sleep(0.1)
                        is_checked = self.driver.execute_script("return arguments[0].checked;", viewing_checkbox)
                        if is_checked:
                            logger.debug("✓ Viewing checkbox verified checked")
                    except Exception as e:
                        logger.debug(f"Viewing checkbox not available: {e}")

                    # Find submit button
                    try:
                        submit_button = self.driver.find_element(By.CSS_SELECTOR, 'button[data-testid="ad-request-send-mail"]')
                        if submit_button and submit_button.is_displayed() and submit_button.is_enabled():
                            logger.info("Found email submit button")
                            break  # Exit loop - button found
                    except Exception as e:
                        logger.debug(f"Could not find email submit button yet: {e}")

                elif form_found and form_type == "messaging":
                    # Messaging form: Find submit button only
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

            # Final verification before submission
            # BEST EFFORT - we try to verify/prepare, but don't block submission if it fails

            # Check Mietprofil on ALL forms (will gracefully skip if not present)
            logger.info("Verifying Mietprofil checkbox before submission...")
            checkbox_result = self._ensure_mietprofil_checked()
            if checkbox_result:
                logger.info("✅ Mietprofil checkbox verified and checked")
            else:
                logger.debug("Mietprofil checkbox not found or verification failed (may not exist on this form type)")

            # Verify message field for ALL form types (both email and messaging)
            logger.info(f"Verifying message field for {form_type} form...")
            message_result = self._ensure_message_filled()
            if message_result:
                logger.info("✅ Message field verified and ready")
            else:
                logger.warning("⚠️ Message field verification failed - continuing with submission anyway")
                logger.warning("The message may be empty or invalid")

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
