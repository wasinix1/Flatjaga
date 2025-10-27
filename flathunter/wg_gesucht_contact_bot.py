"""
WG-Gesucht Contact Bot
Automates contacting WG-Gesucht listings using Selenium.
Handles session management internally (like willhaben bot).
"""

import time
import json
import os
import random
import signal
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import logging

logger = logging.getLogger(__name__)

COOKIE_FILE = str(Path.home() / '.wg_gesucht_cookies.json')
WG_GESUCHT_URL = 'https://www.wg-gesucht.de'


class SessionExpiredException(Exception):
    """Raised when WG-Gesucht session has expired and re-login is required."""
    pass


class ContactFailedException(Exception):
    """Raised when contact flow fails for any reason."""
    pass


class WgGesuchtContactBot:
    """
    WG-Gesucht contact automation bot.
    Handles session management and contact flow internally.
    """
    
    def __init__(self, headless=True, template_index=0, delay_min=0.5, delay_max=1.5):
        """
        Initialize bot with session management.

        Args:
            headless: Run browser in headless mode (default True)
            template_index: Which template to use (default 0 = first)
            delay_min: Minimum delay between actions in seconds
            delay_max: Maximum delay between actions in seconds
        """
        self.headless = headless
        self.template_index = template_index
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.driver = None
        self.session_valid = False

        logger.info("Initializing WG-Gesucht bot...")

    def start(self):
        """Start the bot and initialize the driver."""
        self._init_driver()
        # Note: Session loading is handled by load_cookies() method, called by processor
        # Manual login should only happen in setup_sessions.py, not during automated runs
    
    def _random_delay(self, min_sec=None, max_sec=None):
        """Add random delay to mimic human behavior.

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

    def _init_driver(self):
        """Create Selenium driver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=chrome_options)
        logger.info("Chrome driver initialized")

    def load_cookies(self):
        """Load saved session cookies. Returns True if session is valid."""
        if os.path.exists(COOKIE_FILE):
            logger.info("Found saved session, loading cookies...")
            if self._load_cookies():
                self.session_valid = True
                return True
            else:
                self.session_valid = False
                return False
        else:
            logger.warning("No saved session found")
            self.session_valid = False
            return False
    
    def _load_or_login(self):
        """Load saved session or prompt for manual login."""
        # Check if cookies exist
        if os.path.exists(COOKIE_FILE):
            logger.info("Found saved session, loading cookies...")
            if self._load_cookies():
                logger.info("✓ Session loaded successfully")
                self.session_valid = True
                return
        
        # No cookies or loading failed - need manual login
        logger.info("No saved session found, manual login required")
        self._login_manual()
    
    def _load_cookies(self):
        """Load cookies from file and validate session."""
        try:
            with open(COOKIE_FILE, 'r') as f:
                cookies = json.load(f)
            
            # Navigate to site first
            self.driver.get(WG_GESUCHT_URL)
            
            # Add cookies
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.warning(f"Error adding cookie: {e}")
            
            # Refresh to apply cookies
            self.driver.get(WG_GESUCHT_URL)
            time.sleep(0.3)  # Reduced from 1s for performance
            
            # Validate session
            if self._validate_session():
                return True
            else:
                logger.warning("Session validation failed")
                return False
        
        except Exception as e:
            logger.error(f"Error loading cookies: {e}")
            return False
    
    def _validate_session(self):
        """
        Check if session is valid by looking for logged-in elements.
        More robust validation - checks multiple indicators.
        """
        try:
            # Look for "Mein Konto" link (only visible when logged in)
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.LINK_TEXT, "Mein Konto"))
            )

            # Additional check: verify we're not on login page
            if 'login' in self.driver.current_url.lower():
                logger.warning("Session validation failed - on login page")
                return False

            # Check for logout link as additional confirmation
            try:
                self.driver.find_element(By.LINK_TEXT, "Logout")
                logger.info("Session validated - user is logged in")
                return True
            except NoSuchElementException:
                # Mein Konto exists but no logout - unusual but accept it
                logger.info("Session validated - Mein Konto found")
                return True

        except TimeoutException:
            logger.warning("Session validation failed - Mein Konto not found")
            return False
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False
    
    def _login_manual(self):
        """Prompt user to login manually and save session."""
        print("\n" + "="*60)
        print("🔐 WG-GESUCHT MANUAL LOGIN REQUIRED")
        print("="*60)
        print("\n1. Browser window is open at wg-gesucht.de")
        print("2. Please login to your account")
        print("3. After logging in, press ENTER here to continue\n")
        
        # Navigate to login page
        self.driver.get(WG_GESUCHT_URL)
        
        # Wait for user to login
        input("Press ENTER after you've logged in... ")
        
        # Validate login
        if not self._validate_session():
            print("\n❌ Login validation failed. Please ensure you're logged in.")
            input("Press ENTER to try again... ")
            
            if not self._validate_session():
                raise Exception("Login validation failed. Cannot proceed without valid session.")
        
        # Save cookies
        self._save_cookies()
        self.session_valid = True
        print("\n✓ Login successful! Session saved.\n")
    
    def _save_cookies(self):
        """Save current cookies to file."""
        cookies = self.driver.get_cookies()
        with open(COOKIE_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"Cookies saved to {COOKIE_FILE}")
    
    def send_contact_message(self, listing_url, timeout=10):
        """
        Contact a WG-Gesucht listing.
        
        Flow:
        1. Navigate to contact page (convert URL)
        2. Handle cookie popup
        3. Handle security tips popup
        4. Click "Vorlage einfügen" button
        5. Select template in modal
        6. Click "VORLAGE EINFÜGEN" to insert
        7. Click "Senden" to send
        8. Verify success
        
        Args:
            listing_url: Full URL to WG-Gesucht listing
            timeout: Max seconds to wait for elements (default 10)
        
        Returns:
            True if successful, False otherwise
        """
        
        if not self.session_valid:
            logger.error("Session invalid - cannot contact listing")
            raise SessionExpiredException("Session is not valid - re-login required")
        
        try:
            logger.info(f"Contacting listing: {listing_url}")
            
            # Convert to contact URL
            if '/nachricht-senden/' not in listing_url:
                parts = listing_url.split('wg-gesucht.de/')
                if len(parts) == 2:
                    contact_url = f"{parts[0]}wg-gesucht.de/nachricht-senden/{parts[1]}"
                    logger.info(f"  → Converted to: {contact_url}")
                    listing_url = contact_url
            
            # Navigate to contact page
            self.driver.get(listing_url)
            self._random_delay(1, 2)
            
            # Check session
            if 'login' in self.driver.current_url.lower():
                logger.error("Session expired - redirected to login")
                self.session_valid = False
                raise SessionExpiredException("Session expired - redirected to login page")
            
            # Cookie popup
            try:
                accept_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Alle akzeptieren')]"))
                )
                self.driver.execute_script("arguments[0].click();", accept_btn)
                logger.info("  ✓ Accepted cookies")
                self._random_delay(0.5, 1)
            except TimeoutException:
                pass
            
            # Adaptive popup handling
            security_done = False
            template_opened = False
            
            for attempt in range(10):
                self._random_delay(0.3, 0.7)
                
                # Security tips
                if not security_done:
                    try:
                        confirm_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Ich habe die Sicherheitstipps gelesen')]")
                        if confirm_btn.is_displayed():
                            self.driver.execute_script("arguments[0].click();", confirm_btn)
                            logger.info("  ✓ Dismissed security tips")
                            security_done = True
                            self._random_delay(0.5, 1)
                            continue
                    except:
                        security_done = True
                
                # Template button (opens modal)
                if security_done and not template_opened:
                    try:
                        template_span = self.driver.find_element(By.CSS_SELECTOR, "span[data-text_insert_template='Vorlage einfügen']")
                        parent_btn = template_span.find_element(By.XPATH, "./..")
                        if parent_btn.is_displayed():
                            self.driver.execute_script("arguments[0].click();", parent_btn)
                            logger.info("  ✓ Opened template modal")
                            template_opened = True
                            self._random_delay(0.5, 1)
                            break
                    except:
                        pass
            
            if not template_opened:
                logger.error("Could not open template modal")
                return False
            
            # Wait for modal header
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, "//p[contains(text(), 'Wählen Sie eine Nachrichtenvorlage')]"))
                )
                logger.info("  ✓ Template modal visible")
            except TimeoutException:
                logger.error("Modal didn't appear")
                return False
            
            self._random_delay(0.3, 0.7)

            # Click template label with smart wait
            try:
                # Smart wait: Check if template labels are loaded (max 5 attempts over ~1.5s)
                labels = None
                for check_attempt in range(5):
                    labels = self.driver.find_elements(By.CLASS_NAME, "message_template_label")
                    if labels and len(labels) > self.template_index:
                        logger.info(f"✓ Template labels loaded (detected on check #{check_attempt+1})")
                        break
                    if check_attempt < 4:
                        time.sleep(0.3)

                if not labels or len(labels) <= self.template_index:
                    logger.error(f"Template {self.template_index} not found (only {len(labels) if labels else 0} available)")
                    return False

                label = labels[self.template_index]

                # Try multiple click strategies to ensure selection
                clicked = False
                strategies = [
                    ("JavaScript click", lambda: self.driver.execute_script("arguments[0].click();", label)),
                    ("scroll and JS click", lambda: (
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", label),
                        time.sleep(0.1),
                        self.driver.execute_script("arguments[0].click();", label)
                    )),
                ]

                for strategy_name, strategy_func in strategies:
                    try:
                        strategy_func()
                        logger.info(f"  ✓ Selected template {self.template_index} using {strategy_name}")
                        clicked = True
                        break
                    except Exception as e:
                        logger.debug(f"{strategy_name} failed: {e}")

                if not clicked:
                    logger.error("All template selection strategies failed")
                    return False

            except Exception as e:
                logger.error(f"Could not select template: {e}")
                return False

            self._random_delay(0.3, 0.7)

            # Click insert button in modal
            try:
                insert_btn = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "use_message_template"))
                )
                self.driver.execute_script("arguments[0].click();", insert_btn)
                logger.info("  ✓ Clicked insert template button")
            except TimeoutException:
                logger.error("Insert button not found")
                return False

            # Verify template was actually inserted into message field
            self._random_delay(0.3, 0.7)
            try:
                # Smart wait: Check if message field has content after insertion
                message_field = None
                has_content = False

                for check_attempt in range(5):
                    try:
                        # Try common message field selectors
                        message_field = self.driver.find_element(By.ID, "message_input")
                    except:
                        try:
                            message_field = self.driver.find_element(By.NAME, "message")
                        except:
                            try:
                                message_field = self.driver.find_element(By.CSS_SELECTOR, "textarea[name='message']")
                            except:
                                pass

                    if message_field:
                        content = message_field.get_attribute("value") or ""
                        js_content = self.driver.execute_script("return arguments[0].value;", message_field) or ""

                        if content.strip() or js_content.strip():
                            has_content = True
                            logger.info(f"✓ Template inserted successfully (verified on check #{check_attempt+1})")
                            break

                    if check_attempt < 4:
                        time.sleep(0.3)

                if not has_content:
                    logger.warning("⚠️ Could not verify template was inserted - message field appears empty")

            except Exception as e:
                logger.debug(f"Template insertion verification failed: {e}")

            self._random_delay(0.5, 1)
            
            # Click send button
            try:
                send_btn = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "conversation_send_button"))
                )
                self.driver.execute_script("arguments[0].click();", send_btn)
                logger.info("  ✓ Clicked send")
            except TimeoutException:
                logger.error("Send button not found")
                return False
            
            # Wait for success
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'erfolgreich')]"))
                )
                logger.info("  ✅ Message sent successfully!")
                return True
            except TimeoutException:
                logger.error("Success confirmation not found")
                return False
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False
    
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


def contact_listing(driver, listing_url, template_index=0, timeout=10):
    """
    Contact a WG-Gesucht listing using saved session.
    
    Flow:
    1. Navigate to listing
    2. Click "Nachricht senden" button
    3. Handle security tips popup (auto-appears)
    4. Click "Vorlage einfügen" button on message page
    5. Select template in modal
    6. Click insert template
    7. Click send
    8. Verify success
    
    Args:
        driver: Selenium WebDriver with valid session
        listing_url: Full URL to WG-Gesucht listing
        template_index: Which template checkbox to click (default 0 = first)
        timeout: Max seconds to wait for elements (default 10)
    
    Returns:
        True if successful
        
    Raises:
        SessionExpiredException: If session expired
        ContactFailedException: If contact flow fails
    """
    
    try:
        print(f"📧 Contacting listing: {listing_url}")
        
        # Step 1: Navigate to listing
        driver.get(listing_url)
        
        # Check if we got redirected to login (session expired)
        if 'login' in driver.current_url.lower():
            mark_session_invalid()
            raise SessionExpiredException("Session expired - redirected to login")
        
        # Step 2: Click "Nachricht senden" button
        # Looking for orange button with text "Nachricht senden"
        try:
            send_button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'btn') and contains(text(), 'Nachricht senden')]"))
            )
            send_button.click()
            print("  ✓ Clicked 'Nachricht senden' button")
        except TimeoutException:
            raise ContactFailedException("Could not find 'Nachricht senden' button")
        
        # Step 3: Handle security tips popup (auto-appears)
        # Wait for modal with "Wichtige Sicherheitstipps"
        try:
            # Wait for the security modal to appear
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Wichtige Sicherheitstipps')]"))
            )
            
            # Click the yellow button "Ich habe die Sicherheitstipps gelesen"
            confirm_button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Ich habe die Sicherheitstipps gelesen')]"))
            )
            confirm_button.click()
            print("  ✓ Dismissed security tips popup")
        except TimeoutException:
            # Security popup might not appear every time, continue
            print("  ⚠️  Security tips popup didn't appear (may have been dismissed before)")
        
        # Small wait for page to settle after popup
        time.sleep(0.3)  # Reduced from 1s for performance
        
        # Step 4: Click "Vorlage einfügen" button to open template selector
        try:
            template_button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Vorlage einfügen') or contains(., 'Vorlage einfügen')]"))
            )
            template_button.click()
            print("  ✓ Clicked 'Vorlage einfügen' button")
        except TimeoutException:
            raise ContactFailedException("Could not find 'Vorlage einfügen' button")
        
        # Step 5: Handle template selection modal (now it appears)
        # Wait for modal with "Wählen Sie eine Nachrichtenvorlage"
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Wählen Sie eine Nachrichtenvorlage')]"))
            )
            print("  ✓ Template selector modal opened")
        except TimeoutException:
            raise ContactFailedException("Template selector modal didn't appear")
        
        # Click checkbox at template_index (default 0 = first checkbox) with smart wait
        try:
            # Smart wait: Check if checkboxes are loaded (max 5 attempts over ~1.5s)
            checkboxes = None
            for check_attempt in range(5):
                checkboxes = driver.find_elements(By.XPATH, "//input[@type='checkbox']")
                if checkboxes and len(checkboxes) > template_index:
                    print(f"  ✓ Template checkboxes loaded (check #{check_attempt+1})")
                    break
                if check_attempt < 4:
                    time.sleep(0.3)

            if not checkboxes or len(checkboxes) <= template_index:
                raise ContactFailedException(f"Template index {template_index} not found (only {len(checkboxes) if checkboxes else 0} templates available)")

            # Click the checkbox at the specified index
            checkbox = checkboxes[template_index]

            # Try multiple strategies to ensure selection
            clicked = False
            strategies = [
                ("JavaScript click", lambda: driver.execute_script("arguments[0].click();", checkbox)),
                ("set checked + events", lambda: driver.execute_script("""
                    arguments[0].checked = true;
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('click', { bubbles: true }));
                """, checkbox)),
            ]

            for strategy_name, strategy_func in strategies:
                try:
                    strategy_func()
                    print(f"  ✓ Selected template {template_index} using {strategy_name}")
                    clicked = True
                    break
                except Exception as e:
                    print(f"  {strategy_name} failed: {e}")

            if not clicked:
                raise ContactFailedException("All template selection strategies failed")

        except Exception as e:
            raise ContactFailedException(f"Could not select template: {e}")
        
        # Step 6: Click "VORLAGE EINFÜGEN" button in modal
        try:
            insert_button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'VORLAGE EINFÜGEN')]"))
            )
            insert_button.click()
            print("  ✓ Clicked 'VORLAGE EINFÜGEN' button")
        except TimeoutException:
            raise ContactFailedException("Could not find 'VORLAGE EINFÜGEN' button")
        
        # Small wait for template to be inserted
        time.sleep(0.3)  # Reduced from 1s for performance
        
        # Step 7: Click "Senden" button (final send)
        try:
            send_final = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn') and contains(text(), 'Senden')]"))
            )
            send_final.click()
            print("  ✓ Clicked final 'Senden' button")
        except TimeoutException:
            raise ContactFailedException("Could not find final 'Senden' button")
        
        # Step 8: Wait for success banner containing "erfolgreich"
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'erfolgreich')]"))
            )
            print("  ✅ Message sent successfully!")
            return True
        except TimeoutException:
            raise ContactFailedException("Success confirmation not found")
    
    except SessionExpiredException:
        # Re-raise session exceptions
        raise
    
    except Exception as e:
        # Log other failures
        print(f"  ❌ Failed to contact listing: {e}")
        raise ContactFailedException(str(e))


def contact_listing_safe(driver, listing_url, template_index=0):
    """
    Safe wrapper around contact_listing that catches exceptions.
    Returns True/False instead of raising exceptions.
    Marks session as invalid if session expired.
    """
    try:
        return contact_listing(driver, listing_url, template_index)
    except SessionExpiredException as e:
        print(f"⚠️  Session expired: {e}")
        mark_session_invalid()
        return False
    except ContactFailedException as e:
        print(f"⚠️  Contact failed: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Unexpected error: {e}")
        return False