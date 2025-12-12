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

COOKIE_FILE = str(Path.home() / '.wg_gesucht_cookies.json')
WG_GESUCHT_URL = 'https://www.wg-gesucht.de'


class SessionExpiredException(Exception):
    """Raised when WG-Gesucht session has expired and re-login is required."""
    pass


class ContactFailedException(Exception):
    """Raised when contact flow fails for any reason."""
    pass


class HumanBehavior:
    """Simulates human-like browser interactions."""

    @staticmethod
    def realistic_delay(min_sec=1, max_sec=3, action_type="normal"):
        """
        Human-realistic delays with variation based on action type.

        Action types:
        - "reading": Longer pause (user is reading content)
        - "thinking": Medium pause (user is deciding what to do)
        - "typing": Very short pause (between keystrokes)
        - "micro": Very short pause (quick interactions)
        - "normal": Standard interaction delay
        """
        base_delays = {
            "reading": (3, 7),
            "thinking": (2, 5),
            "typing": (0.05, 0.25),
            "micro": (0.3, 0.7),
            "normal": (min_sec, max_sec)
        }

        min_d, max_d = base_delays.get(action_type, (min_sec, max_sec))
        delay = random.uniform(min_d, max_d)

        # Add micro-pauses for realism (humans don't have perfectly smooth timing)
        if random.random() < 0.3:  # 30% chance of slight hesitation
            delay += random.uniform(0.1, 0.5)

        time.sleep(delay)

    @staticmethod
    def human_type(element, text, driver):
        """
        Type text like a human - with realistic speed variation.

        Humans don't type at constant speed:
        - Sometimes fast (comfortable words)
        - Sometimes slow (thinking/complex words)
        - Occasional mistakes (rare, but happens)
        """
        # Clear field first
        element.clear()
        time.sleep(random.uniform(0.1, 0.3))

        words = text.split(' ')
        for i, word in enumerate(words):
            # Type word character by character
            for char in word:
                element.send_keys(char)

                # Variable typing speed
                if random.random() < 0.7:  # 70% normal speed
                    time.sleep(random.uniform(0.08, 0.15))
                elif random.random() < 0.15:  # 15% fast (familiar text)
                    time.sleep(random.uniform(0.03, 0.06))
                else:  # 15% slow (thinking/careful)
                    time.sleep(random.uniform(0.2, 0.4))

            # Add space after word (if not last word)
            if i < len(words) - 1:
                element.send_keys(' ')
                time.sleep(random.uniform(0.1, 0.2))

        # Small pause after finishing typing (user reviews what they wrote)
        time.sleep(random.uniform(0.5, 1.5))

    @staticmethod
    def human_scroll(driver, direction="down", distance=None):
        """
        Scroll like a human reading the page.

        Args:
            direction: "down" or "up"
            distance: Pixels to scroll (None = random)
        """
        if distance is None:
            distance = random.randint(200, 500)

        scroll_amount = distance if direction == "down" else -distance

        # Scroll in chunks (humans don't scroll in one perfect motion)
        chunks = random.randint(2, 4)
        chunk_size = scroll_amount // chunks

        for _ in range(chunks):
            driver.execute_script(f"window.scrollBy(0, {chunk_size});")
            time.sleep(random.uniform(0.1, 0.3))

        # Pause after scrolling (reading content)
        time.sleep(random.uniform(0.5, 1.5))

    @staticmethod
    def move_to_element_human(driver, element):
        """
        Move cursor to element in a human-like way.
        Not actual cursor movement, but simulates the timing/behavior.
        """
        # Scroll element into view first (like a human would)
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
            element
        )

        # Wait a moment (human eyes track movement)
        time.sleep(random.uniform(0.3, 0.8))

        # Small pause before interacting (human aims cursor)
        time.sleep(random.uniform(0.2, 0.5))

    @staticmethod
    def human_click(driver, element, description="element"):
        """
        Click element with human-like behavior.
        Includes hover simulation and realistic timing.
        """
        try:
            # Move to element
            HumanBehavior.move_to_element_human(driver, element)

            # Hover before click (simulate mouse movement)
            driver.execute_script("""
                var element = arguments[0];
                var event = new MouseEvent('mouseover', {
                    'view': window,
                    'bubbles': true,
                    'cancelable': true
                });
                element.dispatchEvent(event);
            """, element)

            # Small delay (human hand-eye coordination)
            time.sleep(random.uniform(0.1, 0.3))

            # Click
            element.click()

            logger.debug(f"✓ Human-clicked {description}")
            return True

        except Exception as e:
            # Fallback to JS click
            try:
                driver.execute_script("arguments[0].click();", element)
                logger.debug(f"✓ JS-clicked {description} (fallback)")
                return True
            except:
                logger.warning(f"✗ Failed to click {description}: {e}")
                return False


class WgGesuchtContactBot:
    """
    WG-Gesucht contact automation bot.
    Handles session management and contact flow internally.
    """
    
    def __init__(self, headless=True, template_index=0, delay_min=0.5, delay_max=1.5, stealth_mode=False):
        """
        Initialize bot with session management.

        Args:
            headless: Run browser in headless mode (default True)
            template_index: Which template to use (default 0 = first)
            delay_min: Minimum delay between actions in seconds
            delay_max: Maximum delay between actions in seconds
            stealth_mode: Enable stealth mode with undetected-chromedriver and human-like behavior (default False)
        """
        self.headless = headless
        self.template_index = template_index
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.stealth_mode = stealth_mode
        self.driver = None
        self.session_valid = False

        logger.info(f"Initializing WG-Gesucht bot (stealth_mode={stealth_mode})...")

    def start(self):
        """Start the bot and initialize the driver."""
        self._init_driver()
        # Note: Session loading is handled by load_cookies() method, called by processor
        # Manual login should only happen in setup_sessions.py, not during automated runs
    
    def _random_delay(self, min_sec=None, max_sec=None, action_type="normal"):
        """Add random delay to mimic human behavior.

        Args:
            min_sec: Minimum delay in seconds (uses self.delay_min if not specified)
            max_sec: Maximum delay in seconds (uses self.delay_max if not specified)
            action_type: Type of action for stealth mode (reading, thinking, typing, normal)
        """
        if self.stealth_mode:
            # Use human-realistic delays in stealth mode
            HumanBehavior.realistic_delay(
                min_sec=min_sec or self.delay_min,
                max_sec=max_sec or self.delay_max,
                action_type=action_type
            )
        else:
            # Use simple random delay in regular mode
            if min_sec is None:
                min_sec = self.delay_min
            if max_sec is None:
                max_sec = self.delay_max
            time.sleep(random.uniform(min_sec, max_sec))

    def _click_element(self, element, description="element"):
        """Click element with optional stealth behavior.

        Args:
            element: Selenium WebElement to click
            description: Description for logging

        Returns:
            True if click succeeded, False otherwise
        """
        if self.stealth_mode:
            # Use human-like clicking in stealth mode
            return HumanBehavior.human_click(self.driver, element, description)
        else:
            # Use regular click strategies
            return self._try_click_element(element, description)

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

    def _click_element_verbose(self, element, description="element"):
        """
        Click element with detailed INFO-level logging for each strategy.
        Used for critical operations where we need full visibility.

        Args:
            element: Selenium WebElement to click
            description: Description for logging

        Returns:
            True if click succeeded, False otherwise
        """
        click_strategies = [
            ("normal click", lambda e: e.click()),
            ("JavaScript click", lambda e: self.driver.execute_script("arguments[0].click();", e)),
            ("scroll into view and click", lambda e: (
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", e),
                time.sleep(0.2),
                e.click()
            )),
        ]

        for i, (strategy_name, strategy_func) in enumerate(click_strategies, 1):
            logger.info(f"        → Click attempt {i}/{len(click_strategies)}: {strategy_name}")
            try:
                strategy_func(element)
                logger.info(f"          ✓ {strategy_name} succeeded")
                return True
            except Exception as e:
                error_msg = str(e)[:100] if str(e) else type(e).__name__
                logger.info(f"          ✗ {strategy_name} failed: {type(e).__name__}: {error_msg}")

        logger.warning(f"        ✗ All {len(click_strategies)} click strategies failed for {description}")
        return False

    def _verify_modal_opened(self, timeout=3):
        """
        Verify template modal actually opened after clicking template button.

        Args:
            timeout: Seconds to wait for modal

        Returns:
            True if modal is present, False otherwise
        """
        try:
            # Primary check: modal header text
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH,
                    "//p[contains(text(), 'Wählen Sie eine Nachrichtenvorlage')]"))
            )
            logger.info(f"          ✓ Modal header found")
            return True
        except TimeoutException:
            logger.info(f"          → Modal header not found, trying fallback check...")
            # Fallback: check for template labels (the actual template list)
            try:
                labels = self.driver.find_elements(By.CLASS_NAME, "message_template_label")
                if labels:
                    logger.info(f"          ✓ Modal verified via template labels (found {len(labels)})")
                    return True
                else:
                    logger.info(f"          ✗ No template labels found")
                    return False
            except Exception as e:
                logger.info(f"          ✗ Fallback check failed: {type(e).__name__}")
                return False

    def _load_template_from_file(self):
        """
        Load template text from message_templates.json file.

        Uses template_index to select from templates array, or falls back to active_template_id.

        Returns:
            str: Template text, or None if loading failed
        """
        try:
            template_file = Path(__file__).parent / 'config' / 'message_templates.json'

            if not template_file.exists():
                logger.warning(f"  → Template file not found: {template_file}")
                return None

            with open(template_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            templates = data.get('templates', [])

            if not templates:
                logger.warning(f"  → No templates found in file")
                return None

            # Try to use template_index first
            if 0 <= self.template_index < len(templates):
                template_text = templates[self.template_index].get('text', '')
                logger.info(f"  → Loaded template {self.template_index} from file ({len(template_text)} chars)")
                return template_text

            # Fallback: use active_template_id
            active_id = data.get('active_template_id')
            if active_id:
                for template in templates:
                    if template.get('id') == active_id:
                        template_text = template.get('text', '')
                        logger.info(f"  → Loaded active template (id={active_id}) from file ({len(template_text)} chars)")
                        return template_text

            # Last resort: use first template
            template_text = templates[0].get('text', '')
            logger.info(f"  → Loaded first template from file ({len(template_text)} chars)")
            return template_text

        except Exception as e:
            logger.error(f"  → Failed to load template from file: {type(e).__name__}: {str(e)[:100]}")
            return None

    def _fill_message_directly(self):
        """
        FALLBACK: Bypass template modal and fill message textarea directly from file.

        This is used when the template button/modal approach fails.
        More reliable since it doesn't depend on modal UI.

        Returns:
            True if message was filled successfully, False otherwise
        """
        logger.info(f"  → FALLBACK: Filling message field directly (bypassing modal)")

        # Load template from file
        template_text = self._load_template_from_file()
        if not template_text:
            logger.error(f"  ✗ Could not load template text from file")
            return False

        # Find message textarea
        logger.info(f"  → Looking for message textarea...")
        textarea_selectors = [
            (By.ID, "message_input"),
            (By.CSS_SELECTOR, "textarea[name='content']"),
            (By.CSS_SELECTOR, "textarea.form-control.wgg_input"),
        ]

        textarea = None
        for selector_type, selector_value in textarea_selectors:
            try:
                textarea = self.driver.find_element(selector_type, selector_value)
                logger.info(f"  ✓ Found textarea using {selector_type}={selector_value}")
                break
            except NoSuchElementException:
                continue

        if not textarea:
            logger.error(f"  ✗ Could not find message textarea with any selector")
            return False

        # Fill textarea with human-like typing (avoid bot detection)
        logger.info(f"  → Filling textarea with template ({len(template_text)} chars)...")
        try:
            # Clear first
            textarea.clear()

            # Human hesitation before starting (looks like reading template)
            time.sleep(random.uniform(0.3, 0.8))

            # ALWAYS use human typing for direct fill (wgg_input may monitor for bots)
            # This creates realistic keystroke timing, events, and variations
            logger.info(f"  → Using human-like typing to avoid detection...")
            HumanBehavior.human_type(textarea, template_text, self.driver)

            # Verify content
            content = textarea.get_attribute('value') or ''
            if len(content) >= len(template_text) * 0.9:  # Allow 10% variance
                logger.info(f"  ✓ Message filled successfully ({len(content)} chars)")
                return True
            else:
                logger.warning(f"  ⚠ Message may not be fully filled (expected ~{len(template_text)}, got {len(content)})")
                return True  # Continue anyway

        except Exception as e:
            logger.error(f"  ✗ Failed to fill textarea: {type(e).__name__}: {str(e)[:100]}")
            return False

    def _find_and_click_template_button(self, max_attempts=3):
        """
        Find and click template button with comprehensive logging and fallback strategies.

        Uses primary CSS selector with text-based fallback, plus dropdown flow for alternate UI.
        Tries 3 click methods per element to handle overlays/interceptions.

        Args:
            max_attempts: Maximum retry attempts (default 3)

        Returns:
            True if template modal opened successfully, False otherwise
        """
        # Direct button selectors (prioritized by reliability)
        direct_button_strategies = [
            {
                "name": "CSS: span.new_conversation_message_template_btn",
                "method": By.CSS_SELECTOR,
                "value": "span.new_conversation_message_template_btn",
            },
            {
                "name": "XPath: by text 'Vorlage einfügen'",
                "method": By.XPATH,
                "value": "//span[contains(., 'Vorlage einfügen') and contains(@class, 'conversation_action_button')]",
            },
        ]

        for attempt in range(max_attempts):
            logger.info(f"  → Template Button Discovery (Attempt {attempt+1}/{max_attempts})")
            self._random_delay(action_type="micro")

            # Try direct button strategies
            logger.info(f"    → Trying direct button strategies...")
            for strategy in direct_button_strategies:
                logger.info(f"      → Strategy: {strategy['name']}")

                try:
                    # Try to find element
                    element = self.driver.find_element(strategy['method'], strategy['value'])

                    # Log element details for diagnostics
                    classes = element.get_attribute('class') or 'none'
                    style = element.get_attribute('style') or 'none'
                    text_content = element.text or ''
                    tag_name = element.tag_name
                    is_displayed = element.is_displayed()
                    is_enabled = element.is_enabled()

                    # Truncate long values for readability
                    classes_short = classes[:80] + '...' if len(classes) > 80 else classes
                    style_short = style[:80] + '...' if len(style) > 80 else style
                    text_short = text_content[:40] + '...' if len(text_content) > 40 else text_content

                    logger.info(f"        ✓ Found element: <{tag_name}>")
                    logger.info(f"          Classes: {classes_short}")
                    logger.info(f"          Text: '{text_short}'")
                    logger.info(f"          Displayed: {is_displayed}, Enabled: {is_enabled}")
                    logger.info(f"          Style: {style_short}")

                    if not is_displayed:
                        logger.info(f"        ✗ Element not displayed, trying next strategy")
                        continue

                    if not is_enabled:
                        logger.info(f"        ⚠ Element not enabled, but will try to click anyway")

                    # Try sophisticated JS click with full event dispatch
                    logger.info(f"        → Attempting sophisticated JS click (full events)...")
                    try:
                        # Dispatch complete mouse event sequence with proper properties
                        self.driver.execute_script("""
                            var element = arguments[0];
                            var rect = element.getBoundingClientRect();
                            var centerX = rect.left + rect.width / 2;
                            var centerY = rect.top + rect.height / 2;

                            // Full event sequence: mousedown → mouseup → click
                            ['mouseover', 'mouseenter', 'mousemove', 'mousedown', 'mouseup', 'click'].forEach(function(eventType) {
                                var event = new MouseEvent(eventType, {
                                    view: window,
                                    bubbles: true,
                                    cancelable: true,
                                    clientX: centerX,
                                    clientY: centerY,
                                    screenX: centerX + window.screenX,
                                    screenY: centerY + window.screenY,
                                    button: 0,
                                    buttons: eventType === 'mousedown' ? 1 : 0
                                });
                                element.dispatchEvent(event);
                            });
                        """, element)

                        logger.info(f"        ✓ Sophisticated JS click dispatched")
                        time.sleep(0.2)  # Let events propagate

                        # Verify modal opened
                        logger.info(f"        → Verifying modal opened...")
                        if self._verify_modal_opened(timeout=3):
                            logger.info(f"      ✓✓ SUCCESS: Template modal opened via {strategy['name']}")
                            return True
                        else:
                            logger.warning(f"        ✗ Click succeeded but modal didn't open")
                            logger.info(f"        → Continuing to next strategy...")
                    except Exception as e:
                        logger.warning(f"        ✗ Sophisticated click failed: {type(e).__name__}")
                        logger.info(f"        → Continuing to next strategy...")

                except NoSuchElementException:
                    logger.info(f"        ✗ Element not found with this selector")
                except Exception as e:
                    error_msg = str(e)[:100] if str(e) else ''
                    logger.info(f"        ✗ Exception: {type(e).__name__}: {error_msg}")

            # Try dropdown flow (alternate site version)
            logger.info(f"    → Trying dropdown flow (alternate version)...")
            try:
                dropdown_btn = self.driver.find_element(By.ID, "conversation_controls_dropdown")

                is_displayed = dropdown_btn.is_displayed()
                logger.info(f"      ✓ Found dropdown button (displayed: {is_displayed})")

                if is_displayed:
                    logger.info(f"      → Clicking dropdown button...")
                    if self._click_element(dropdown_btn, "dropdown"):
                        logger.info(f"      ✓ Dropdown menu opened")
                        self._random_delay(action_type="micro")

                        # Wait for and click template link in dropdown
                        logger.info(f"      → Waiting for template link in dropdown...")
                        try:
                            template_link = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.message_template_btn"))
                            )
                            logger.info(f"      ✓ Template link found, clicking...")
                            if self._click_element(template_link, "template link"):
                                # Verify modal opened
                                logger.info(f"      → Verifying modal opened...")
                                if self._verify_modal_opened(timeout=3):
                                    logger.info(f"    ✓✓ SUCCESS: Template modal opened via dropdown flow")
                                    return True
                                else:
                                    logger.warning(f"      ✗ Click succeeded but modal didn't open")
                            else:
                                logger.warning(f"      ✗ Could not click template link")
                        except TimeoutException:
                            logger.info(f"      ✗ Template link not found in dropdown menu")
                    else:
                        logger.info(f"      ✗ Could not click dropdown button")
                else:
                    logger.info(f"      ✗ Dropdown button not displayed")

            except NoSuchElementException:
                logger.info(f"      ✗ Dropdown button not found (conversation_controls_dropdown)")
            except Exception as e:
                error_msg = str(e)[:100] if str(e) else ''
                logger.info(f"      ✗ Dropdown flow exception: {type(e).__name__}: {error_msg}")

            logger.info(f"    → All strategies failed for attempt {attempt+1}, will retry...")

        logger.error(f"  ✗✗ FAILED: Could not open template modal after {max_attempts} attempts")
        logger.error(f"     All selector and click strategies exhausted")
        return False

    def _init_driver(self):
        """Create Selenium driver with optional stealth mode."""
        # If stealth mode is enabled, try to use undetected-chromedriver
        if self.stealth_mode:
            try:
                import undetected_chromedriver as uc
                logger.info("Using undetected-chromedriver for stealth mode")

                # Use undetected-chromedriver
                options = uc.ChromeOptions()
                if self.headless:
                    options.add_argument('--headless=new')

                # Additional stealth options
                options.add_argument('--disable-blink-features=AutomationControlled')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-web-security')
                options.add_argument('--disable-features=IsolateOrigins,site-per-process')

                # Random window size to avoid fingerprinting
                window_sizes = [(1920, 1080), (1366, 768), (1536, 864), (1440, 900)]
                width, height = random.choice(window_sizes)
                options.add_argument(f'--window-size={width},{height}')

                self.driver = uc.Chrome(options=options, version_main=None)

                # Additional JavaScript-level anti-detection
                self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                    "userAgent": self.driver.execute_script("return navigator.userAgent").replace('Headless', '')
                })

                # Remove webdriver property
                self.driver.execute_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)

                logger.info(f"Undetected Chrome driver initialized ({width}x{height})")
                return

            except ImportError:
                logger.warning("undetected_chromedriver not installed, falling back to regular Chrome")
                logger.warning("Install with: pip install undetected-chromedriver")
                logger.warning("Stealth mode will use regular Chrome with basic anti-detection")

        # Regular Chrome driver (or fallback from stealth mode)
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Use webdriver-manager for auto version matching
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        mode = "stealth (fallback)" if self.stealth_mode else "regular"
        logger.info(f"Chrome driver initialized ({mode} mode, auto-matched version)")

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
        Check if session is valid by looking for logged-in welcome text.
        Uses welcome_text div which ONLY exists when logged in.
        """
        try:
            # Primary check: welcome text (only exists when authenticated)
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.welcome_text"))
            )

            # Additional check: verify we're not on login page
            if 'login' in self.driver.current_url.lower():
                logger.warning("Session validation failed - on login page")
                return False

            logger.info("Session validated - welcome text found")
            return True

        except TimeoutException:
            logger.warning("Session validation failed - welcome text not found")
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
        Contact listing using STEALTH DISCOVERY: find button href, navigate naturally.
        Mimics a user who discovered the URL pattern or inspected the page source.

        Flow (with 3 fallback methods):
        1. Visit listing page
        2. Verify logged in state (check for welcome_text, retry cookie load if needed)
        3. Browse naturally (scroll, read)
        4. Discover contact URL: Method 1: Click visible button | Method 2: Extract href | Method 3: Construct URL
        5. Handle popups (security tips, cookies)
        6. Select and insert template
        7. Send message
        8. Verify success

        Args:
            listing_url: Full URL to WG-Gesucht listing
            timeout: Max seconds to wait for elements (default 10)

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Contacting listing: {listing_url}")

            # Ensure we start on listing page (not contact page)
            if '/nachricht-senden/' in listing_url:
                listing_url = listing_url.replace('/nachricht-senden/', '/')
                logger.info(f"  → Adjusted to listing page: {listing_url}")

            # STEP 1: Visit listing page (human browsing)
            logger.info("  → Visiting listing page...")
            self.driver.get(listing_url)
            self._random_delay(action_type="reading")

            # STEP 2: Verify logged in state AFTER loading page
            logger.info("  → Verifying logged in state...")
            if not self._validate_session():
                logger.warning("  → Not logged in - retrying cookie/session loading...")

                # Retry: reload cookies and validate again
                if not self._load_cookies():
                    logger.error("Session cookie reload failed")
                    self.session_valid = False
                    raise SessionExpiredException("Session cookie reload failed")

                # Re-verify after cookie reload
                if not self._validate_session():
                    logger.error("Session validation failed after cookie reload")
                    self.session_valid = False
                    raise SessionExpiredException("Session validation failed after retry")

                logger.info("  ✓ Session validated after cookie reload")
            else:
                logger.info("  ✓ Session validated - user is logged in")

            # STEP 3: Human browsing behavior - read and scroll
            logger.info("  → Browsing listing (human behavior)...")
            if self.stealth_mode:
                HumanBehavior.human_scroll(self.driver, distance=random.randint(250, 450))
                HumanBehavior.realistic_delay(action_type="reading")

                # Scroll back up sometimes (natural behavior)
                if random.random() < 0.35:
                    HumanBehavior.human_scroll(self.driver, direction="up", distance=random.randint(100, 250))
                    HumanBehavior.realistic_delay(action_type="micro")
            else:
                # Non-stealth mode: still do some scrolling
                HumanBehavior.human_scroll(self.driver, distance=random.randint(150, 350))
                self._random_delay(1, 2)

            # Handle cookie popup
            try:
                accept_btn = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH,
                        "//button[contains(text(), 'Accept') or contains(text(), 'Alle akzeptieren')]"))
                )
                self._click_element(accept_btn, "cookie button")
                logger.info("  ✓ Accepted cookies")
                self._random_delay(action_type="micro")
            except TimeoutException:
                pass

            # STEP 4: STEALTH DISCOVERY - Find contact URL without clicking hidden button
            logger.info("  → Discovering contact URL (3 methods with fallbacks)...")

            contact_url = None
            discovery_method = None

            # Method 1: Look for visible button first (ideal case)
            logger.info("  → Method 1: Checking for visible 'Nachricht senden' button...")
            try:
                visible_button = self.driver.find_element(By.XPATH,
                    "//a[contains(@class, 'wgg_orange') and contains(text(), 'Nachricht senden') and not(contains(@style, 'display: none'))]"
                )
                if visible_button.is_displayed():
                    logger.info("  ✓ Found visible button - clicking normally")
                    self._random_delay(action_type="thinking")
                    if self._click_element(visible_button, "visible Nachricht senden button"):
                        self._random_delay(action_type="reading")
                        # Clicked visible button - we're now on contact page naturally
                        contact_url = self.driver.current_url
                        discovery_method = "visible_button_click"
                        logger.info(f"  ✓ Method 1 SUCCESS: Navigated to: {contact_url}")
            except Exception as e:
                logger.debug(f"  ✗ Method 1 failed: {e}")

            # Method 2: Extract href from hidden button, then navigate (looks like user found the URL)
            if not contact_url:
                logger.info("  → Method 2: Extracting href from page source...")
                try:
                    # Find button in page source (any button, even hidden)
                    hidden_buttons = self.driver.find_elements(By.XPATH,
                        "//a[contains(@href, 'nachricht-senden')]"
                    )

                    if hidden_buttons:
                        contact_url = hidden_buttons[0].get_attribute('href')
                        discovery_method = "href_extraction"
                        logger.info(f"  ✓ Discovered contact URL from page: {contact_url}")

                        # CRITICAL: Don't click hidden element - navigate naturally
                        # This simulates: user inspected page source OR typed URL OR bookmarked it

                        # Add human behavior: maybe scroll around more (looking for button)
                        if random.random() < 0.6 and self.stealth_mode:  # 60% of time in stealth mode
                            logger.info("  → Scrolling to look for contact button...")
                            HumanBehavior.human_scroll(self.driver, distance=random.randint(300, 600))
                            HumanBehavior.realistic_delay(action_type="thinking")

                        # Pause (user "decides" to navigate directly)
                        self._random_delay(action_type="thinking")

                        # Navigate to URL (like typing it in address bar or clicking bookmark)
                        logger.info("  → Navigating to contact page...")
                        self.driver.get(contact_url)
                        self._random_delay(action_type="reading")
                        logger.info(f"  ✓ Method 2 SUCCESS: Navigated to contact page")
                    else:
                        logger.debug("  ✗ Method 2 failed: No buttons with 'nachricht-senden' found")

                except Exception as e:
                    logger.error(f"  ✗ Method 2 failed: Could not discover contact URL: {e}")

            # Method 3: Fallback - construct URL manually (last resort)
            if not contact_url:
                logger.warning("  → Method 3: Constructing contact URL manually (fallback)")
                try:
                    # Extract listing ID from URL
                    # Pattern: https://www.wg-gesucht.de/[...].12345.html -> nachricht-senden/[...].12345.html
                    contact_url = listing_url.replace('wg-gesucht.de/', 'wg-gesucht.de/nachricht-senden/')
                    discovery_method = "url_construction"

                    # Simulate user "figuring out" the URL pattern
                    self._random_delay(action_type="thinking")
                    logger.info(f"  → Trying constructed contact URL: {contact_url}")
                    self.driver.get(contact_url)
                    self._random_delay(action_type="reading")
                    logger.info(f"  ✓ Method 3: Navigated to constructed URL")
                except Exception as e:
                    logger.error(f"  ✗ Method 3 failed: {e}")
                    return False

            # Verify we're on contact page
            if '/nachricht-senden/' not in self.driver.current_url:
                logger.error(f"  ✗ Not on contact page after {discovery_method}: {self.driver.current_url}")
                logger.error("  → Listing may not be contactable or all methods failed")
                return False

            logger.info(f"  ✓ On contact page (via {discovery_method})")

            # STEP 5: Handle security popup
            logger.info("  → Checking for security tips popup...")
            try:
                confirm_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH,
                        "//button[contains(text(), 'Ich habe die Sicherheitstipps gelesen')]"))
                )
                logger.info("  → Security popup found, dismissing...")
                self._click_element(confirm_btn, "security tips")
                logger.info("  ✓ Dismissed security tips")
                self._random_delay(action_type="thinking")
            except TimeoutException:
                logger.info("  → No security popup (already dismissed or not shown)")
            except Exception as e:
                logger.warning(f"  → Security popup handling failed: {type(e).__name__}: {str(e)[:80]}")

            # STEP 6: Fill message field (modal approach with direct fallback)
            logger.info("  → Opening template modal...")
            modal_opened = self._find_and_click_template_button()

            message_filled = False  # Track if message was successfully filled

            if modal_opened:
                # Modal approach succeeded - try to select and insert template
                logger.info(f"  → Selecting template {self.template_index}...")
                try:
                    # Wait longer for templates to load (modal can be slow)
                    labels = None
                    max_wait = 10  # seconds
                    poll_interval = 0.5  # check every 0.5s
                    attempts = int(max_wait / poll_interval)

                    for check_attempt in range(attempts):
                        labels = self.driver.find_elements(By.CLASS_NAME, "message_template_label")
                        if labels and len(labels) > self.template_index:
                            logger.info(f"  ✓ Found {len(labels)} templates after {(check_attempt + 1) * poll_interval:.1f}s")
                            break
                        if check_attempt < attempts - 1:
                            if check_attempt % 4 == 0:  # Log every 2 seconds
                                logger.info(f"  → Templates not ready yet (found {len(labels) if labels else 0}), retrying... ({(check_attempt + 1) * poll_interval:.1f}s elapsed)")
                            time.sleep(poll_interval)

                    if not labels or len(labels) <= self.template_index:
                        logger.warning(f"  ⚠ Template {self.template_index} not found after {max_wait}s (only {len(labels) if labels else 0} available)")
                        raise Exception("Template not found in modal")

                    logger.info(f"  → Clicking template {self.template_index}...")
                    label = labels[self.template_index]
                    if not self._click_element(label, f"template {self.template_index}"):
                        logger.warning("  ⚠ Could not select template")
                        raise Exception("Could not click template label")

                    logger.info(f"  ✓ Selected template {self.template_index}")

                    self._random_delay(action_type="thinking")

                    # Insert template
                    logger.info("  → Looking for insert button...")
                    insert_btn = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "use_message_template"))
                    )
                    logger.info("  → Found insert button, clicking...")
                    if not self._click_element(insert_btn, "insert button"):
                        logger.warning("  ⚠ Could not click insert button")
                        raise Exception("Could not click insert button")

                    logger.info("  ✓ Template inserted into message field")
                    message_filled = True  # Modal approach succeeded!
                    self._random_delay(action_type="thinking")

                except Exception as e:
                    logger.warning(f"  ⚠ Modal template insertion failed: {e}")
                    logger.warning("  → Closing modal before fallback...")

                    # Close modal to prevent overlay conflicts
                    try:
                        # Try common close button selectors
                        close_selectors = [
                            (By.XPATH, "//button[contains(@class, 'close')]"),
                            (By.XPATH, "//span[@aria-hidden='true' and contains(text(), '×')]"),
                            (By.XPATH, "//button[contains(text(), '×')]"),
                            (By.CSS_SELECTOR, "button.close"),
                        ]

                        modal_closed = False
                        for selector_type, selector_value in close_selectors:
                            try:
                                close_btn = self.driver.find_element(selector_type, selector_value)
                                if close_btn.is_displayed():
                                    close_btn.click()
                                    time.sleep(0.3)  # Let modal close animation complete
                                    logger.info(f"  ✓ Closed modal")
                                    modal_closed = True
                                    break
                            except:
                                continue

                        if not modal_closed:
                            logger.debug(f"  → No close button found (modal may auto-close)")

                    except Exception as close_error:
                        logger.debug(f"  → Could not close modal: {close_error} (proceeding anyway)")

            # If modal failed OR template insertion failed, use direct fill fallback
            if not message_filled:
                logger.warning("  ⚠ Using direct fill fallback...")
                if not self._fill_message_directly():
                    logger.error("  ✗ Both modal and direct fill approaches failed")
                    return False

                self._random_delay(action_type="thinking")

            # Verify template insertion (optional, best effort)
            try:
                message_field = None
                for check_attempt in range(3):
                    try:
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
                        if content.strip():
                            logger.info(f"  ✓ Template insertion verified (length: {len(content)} chars)")
                            break

                    if check_attempt < 2:
                        time.sleep(0.3)

                if not content.strip():
                    logger.warning("  ⚠️ Could not verify template insertion - message field appears empty (proceeding anyway)")
            except Exception as e:
                logger.debug(f"  → Template verification skipped: {e}")

            # Send message
            logger.info("  → Sending message...")
            try:
                send_btn = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "conversation_send_button"))
                )
                if not self._click_element(send_btn, "send button"):
                    logger.error("  ✗ Could not click send button")
                    return False
                logger.info("  ✓ Clicked send button")
            except TimeoutException:
                logger.error("  ✗ Send button not found")
                return False

            # Wait for success confirmation
            logger.info("  → Waiting for success confirmation...")
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'erfolgreich')]"))
                )
                logger.info("  ✅ Message sent successfully!")
                return True
            except TimeoutException:
                logger.error("  ✗ Success confirmation not found - message may not have been sent")
                return False

        except SessionExpiredException:
            # Re-raise session exceptions
            raise
        except Exception as e:
            logger.error(f"  ✗ Unexpected error in send_contact_message: {e}")
            import traceback
            logger.debug(f"  → Traceback: {traceback.format_exc()}")
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


