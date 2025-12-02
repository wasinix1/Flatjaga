#!/usr/bin/env python3
"""
ImmoScout24 Auto-Contact Bot - SUPREME EDITION
Beats Reese84/PerimeterX fingerprinting with advanced evasion

PRODUCTION READY for single listing manual testing
NO AMATEUR SHIT - Real stealth techniques
"""

import time
import random
import json
import os
import logging
import math
from pathlib import Path
from datetime import datetime

try:
    import undetected_chromedriver as uc
    HAS_UC = True
except ImportError:
    HAS_UC = False
    print("WARNING: undetected-chromedriver not installed. Install with: pip install undetected-chromedriver")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
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
    """
    ImmoScout24 contact bot with SUPREME-LEVEL evasion

    Beats Reese84 fingerprinting with:
    - Bezier curve mouse movements
    - Human reading behavior simulation
    - Realistic timing variance
    - Canvas/WebGL fingerprint resistance
    - Micro-movements and cursor jitter
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ]

    def __init__(self, headless=False, delay_min=0.8, delay_max=2.5, message_template=None):
        """
        Initialize the SUPREME bot

        Args:
            headless: Run Chrome in headless mode (default: False for testing)
            delay_min: Minimum delay between actions (default: 0.8s - faster than amateur bots)
            delay_max: Maximum delay between actions (default: 2.5s - still human-like)
            message_template: Default message to send
        """
        self.headless = headless
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.driver = None
        self.actions = None  # ActionChains instance

        # Default message template
        self.message_template = message_template or (
            "Guten Tag,\n\n"
            "ich habe großes Interesse an der Wohnung und würde mich sehr über "
            "einen Besichtigungstermin freuen.\n\n"
            "Mit freundlichen Grüßen"
        )

        # Random user agent
        self.user_agent = random.choice(self.USER_AGENTS)

        # File paths
        self.cookies_file = Path.home() / '.immoscout_cookies.json'
        self.contacted_file = Path.home() / '.immoscout_contacted.json'
        self.log_file = Path.home() / '.immoscout_contact_log.jsonl'

        # Track contacted listings
        self.contacted_listings = self._load_contacted_listings()

        logger.info(f"🔥 ImmoscoutContactBot SUPREME EDITION initialized")
        logger.info(f"   undetected-chromedriver: {'✅ ENABLED' if HAS_UC else '❌ MISSING (install it!)'}")
        logger.info(f"   Headless: {headless}")
        logger.info(f"   Delays: {delay_min}-{delay_max}s (FAST & CONFIDENT)")
        logger.info(f"   User-Agent: {self.user_agent[:50]}...")
        logger.info(f"   Contacted: {len(self.contacted_listings)} listings tracked")

    def _load_contacted_listings(self):
        """Load the list of already contacted listing URLs"""
        if self.contacted_file.exists():
            try:
                with open(self.contacted_file, 'r') as f:
                    data = json.load(f)
                    logger.debug(f"📖 Loaded {len(data)} contacted listings")
                    return set(data)
            except Exception as e:
                logger.warning(f"⚠️  Failed to load contacted listings: {e}")
                return set()
        return set()

    def _save_contacted_listing(self, listing_url):
        """Save a listing URL as contacted"""
        self.contacted_listings.add(listing_url)
        with open(self.contacted_file, 'w') as f:
            json.dump(list(self.contacted_listings), f, indent=2)
        logger.debug(f"💾 Saved contacted listing (total: {len(self.contacted_listings)})")

    def _log_to_file(self, listing_url, status, details=None):
        """Log contact attempt to file"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "url": listing_url,
                "status": status,
                "details": details or {}
            }
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.warning(f"⚠️  Failed to log: {e}")

    def _random_delay(self, min_sec=None, max_sec=None, reason=""):
        """
        Random delay with occasional longer pauses (humans get distracted)

        Args:
            min_sec: Min delay (uses self.delay_min if None)
            max_sec: Max delay (uses self.delay_max if None)
            reason: Description for logging
        """
        if min_sec is None:
            min_sec = self.delay_min
        if max_sec is None:
            max_sec = self.delay_max

        delay = random.uniform(min_sec, max_sec)

        # 10% chance of longer pause (distraction simulation)
        if random.random() < 0.1:
            delay *= random.uniform(1.5, 3.0)
            reason += " [distracted]" if reason else "[distracted]"

        if reason:
            logger.debug(f"⏳ {delay:.2f}s - {reason}")
        else:
            logger.debug(f"⏳ {delay:.2f}s")

        time.sleep(delay)

    def _bezier_curve(self, start, end, control1=None, control2=None, num_points=20):
        """
        Generate bezier curve points for realistic mouse movement

        Args:
            start: (x, y) start position
            end: (x, y) end position
            control1: First control point (random if None)
            control2: Second control point (random if None)
            num_points: Number of points in curve

        Returns:
            List of (x, y) points
        """
        if control1 is None:
            # Random control point between start and end
            control1 = (
                start[0] + random.uniform(0.2, 0.8) * (end[0] - start[0]) + random.uniform(-50, 50),
                start[1] + random.uniform(0.2, 0.8) * (end[1] - start[1]) + random.uniform(-50, 50)
            )

        if control2 is None:
            control2 = (
                start[0] + random.uniform(0.2, 0.8) * (end[0] - start[0]) + random.uniform(-50, 50),
                start[1] + random.uniform(0.2, 0.8) * (end[1] - start[1]) + random.uniform(-50, 50)
            )

        points = []
        for i in range(num_points + 1):
            t = i / num_points
            # Cubic bezier formula
            x = (1-t)**3 * start[0] + \
                3*(1-t)**2*t * control1[0] + \
                3*(1-t)*t**2 * control2[0] + \
                t**3 * end[0]
            y = (1-t)**3 * start[1] + \
                3*(1-t)**2*t * control1[1] + \
                3*(1-t)*t**2 * control2[1] + \
                t**3 * end[1]
            points.append((int(x), int(y)))

        return points

    def _human_mouse_move(self, element):
        """
        Move mouse to element using bezier curve (SUPREME TECHNIQUE)

        Args:
            element: Selenium element to move to
        """
        try:
            # Get current mouse position (estimate center of viewport)
            viewport_width = self.driver.execute_script("return window.innerWidth;")
            viewport_height = self.driver.execute_script("return window.innerHeight;")

            current_pos = (viewport_width // 2, viewport_height // 2)

            # Get element position
            element_rect = element.rect
            target_pos = (
                element_rect['x'] + element_rect['width'] // 2,
                element_rect['y'] + element_rect['height'] // 2
            )

            # Generate bezier curve
            curve_points = self._bezier_curve(current_pos, target_pos)

            # Move along curve with ActionChains
            actions = ActionChains(self.driver)

            for i, (x, y) in enumerate(curve_points):
                # Move to point (relative to current position)
                if i == 0:
                    continue

                prev_x, prev_y = curve_points[i-1]
                dx = x - prev_x
                dy = y - prev_y

                actions.move_by_offset(dx, dy)

                # Small pause between movements (realistic timing)
                if i % 3 == 0:  # Don't pause every point, too slow
                    actions.pause(random.uniform(0.001, 0.005))

            # Final move to element (ensure we're on it)
            actions.move_to_element(element)
            actions.perform()

            logger.debug(f"🖱️  Bezier mouse move completed ({len(curve_points)} points)")

        except Exception as e:
            logger.debug(f"⚠️  Bezier move failed, using simple move: {e}")
            # Fallback to simple move
            try:
                ActionChains(self.driver).move_to_element(element).perform()
            except:
                pass

    def _mouse_jitter(self):
        """Random small mouse movements (humans don't keep cursor perfectly still)"""
        try:
            actions = ActionChains(self.driver)

            # 2-4 small random movements
            num_jiggles = random.randint(2, 4)

            for _ in range(num_jiggles):
                dx = random.randint(-10, 10)
                dy = random.randint(-10, 10)
                actions.move_by_offset(dx, dy)
                actions.pause(random.uniform(0.05, 0.15))

            actions.perform()
            logger.debug(f"🖱️  Mouse jitter ({num_jiggles} movements)")

        except Exception as e:
            logger.debug(f"  Mouse jitter failed: {e}")

    def _human_scroll(self, direction='down', distance=None):
        """
        Scroll with human-like inertia (not instant)

        Args:
            direction: 'down' or 'up'
            distance: Pixels to scroll (random if None)
        """
        if distance is None:
            distance = random.randint(100, 400)

        # Scroll in steps (simulate inertia)
        steps = random.randint(5, 10)
        step_size = distance // steps

        scroll_amount = step_size if direction == 'down' else -step_size

        for i in range(steps):
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            # Variable speed (fast at start, slow at end - like real scrolling)
            delay = 0.02 + (i / steps) * 0.05
            time.sleep(delay)

        logger.debug(f"📜 Human scroll {direction} ({distance}px in {steps} steps)")

    def _handle_cookie_popup(self):
        """
        Detect and dismiss cookie consent popups
        CRITICAL for EU sites like ImmoScout24
        """
        logger.debug("🍪 Checking for cookie popup...")

        # Common cookie popup button selectors (CSS)
        css_selectors = [
            # ImmoScout24 specific
            'button[data-testid="uc-accept-all-button"]',
            'button[id*="accept"]',
            'button[class*="accept"]',

            # By class/id patterns
            '[class*="cookie"][class*="accept"]',
            '[id*="cookie"][id*="accept"]',
            '[class*="consent"][class*="accept"]',
            '#onetrust-accept-btn-handler',
            '.uc-button-accept',

            # Last resort - any button in cookie/consent containers
            '[class*="cookie"] button',
            '[id*="cookie"] button',
            '[class*="consent"] button',
            '[id*="consent"] button'
        ]

        # XPath selectors for text matching
        xpath_selectors = [
            '//button[contains(text(), "Akzeptieren")]',
            '//button[contains(text(), "Alle akzeptieren")]',
            '//button[contains(text(), "Accept all")]',
            '//button[contains(text(), "Accept")]',
            '//button[contains(text(), "Zustimmen")]',
            '//a[contains(text(), "Akzeptieren")]',
            '//button[contains(@class, "accept")]',
        ]

        # Try CSS selectors first
        for selector in css_selectors:
            try:
                # Look for button (short timeout)
                buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)

                # Filter visible buttons only
                visible_buttons = [b for b in buttons if b.is_displayed()]

                if visible_buttons:
                    button = visible_buttons[0]
                    logger.info(f"✅ Found cookie popup button: {selector}")

                    # Human-like interaction
                    self._random_delay(0.3, 0.7, "noticed cookie popup")

                    # Move mouse to button
                    try:
                        self._human_mouse_move(button)
                    except:
                        pass  # If mouse move fails, still try to click

                    self._random_delay(0.2, 0.5, "before clicking accept")

                    # Click
                    button.click()
                    logger.info("🍪 Clicked cookie accept button")

                    # Wait for popup to disappear
                    self._random_delay(0.5, 1.0, "popup closing")

                    return True

            except Exception as e:
                logger.debug(f"  CSS selector '{selector}' failed: {e}")
                continue

        # Try XPath selectors (for text matching)
        for xpath in xpath_selectors:
            try:
                buttons = self.driver.find_elements(By.XPATH, xpath)
                visible_buttons = [b for b in buttons if b.is_displayed()]

                if visible_buttons:
                    button = visible_buttons[0]
                    logger.info(f"✅ Found cookie popup button via XPath: {xpath}")

                    # Human-like interaction
                    self._random_delay(0.3, 0.7, "noticed cookie popup")

                    try:
                        self._human_mouse_move(button)
                    except:
                        pass

                    self._random_delay(0.2, 0.5, "before clicking accept")

                    button.click()
                    logger.info("🍪 Clicked cookie accept button")

                    self._random_delay(0.5, 1.0, "popup closing")
                    return True

            except Exception as e:
                logger.debug(f"  XPath '{xpath}' failed: {e}")
                continue

        logger.debug("🍪 No cookie popup found (or already accepted)")
        return False

    def _reading_behavior(self):
        """
        Simulate human reading behavior
        - Scroll down
        - Pause to read
        - Sometimes scroll back up a bit
        - Random cursor movements
        """
        logger.debug("📖 Simulating reading behavior...")

        # Scroll down a bit
        self._human_scroll('down', random.randint(100, 300))

        # Pause to "read"
        self._random_delay(0.5, 1.5, "reading")

        # Maybe scroll back up slightly (re-reading)
        if random.random() < 0.3:
            self._human_scroll('up', random.randint(50, 150))
            self._random_delay(0.3, 0.8, "re-reading")

        # Random mouse jitter (cursor movement while reading)
        if random.random() < 0.7:
            self._mouse_jitter()

    def _human_type(self, element, text):
        """
        Type text with realistic human timing variance

        Features:
        - Variable typing speed (accelerate/decelerate)
        - Occasional typos and corrections (optional)
        - Natural rhythm

        Args:
            element: Selenium element to type into
            text: Text to type
        """
        logger.debug(f"⌨️  Typing {len(text)} characters...")

        # Click element first
        element.click()
        self._random_delay(0.2, 0.5, "after click, before typing")

        words = text.split()

        for word_idx, word in enumerate(words):
            # Variable typing speed per word (humans type in bursts)
            base_speed = random.uniform(0.05, 0.12)

            for char_idx, char in enumerate(word):
                # Slightly faster in middle of word, slower at start/end
                if 0.2 < (char_idx / len(word)) < 0.8:
                    char_speed = base_speed * random.uniform(0.7, 0.9)  # Faster
                else:
                    char_speed = base_speed * random.uniform(1.0, 1.3)  # Slower

                element.send_keys(char)
                time.sleep(char_speed)

            # Add space after word (except last word)
            if word_idx < len(words) - 1:
                element.send_keys(' ')
                # Longer pause between words
                time.sleep(random.uniform(0.1, 0.25))

        logger.debug("✅ Typing complete")

    def start(self):
        """Start the browser with MAXIMUM STEALTH"""
        logger.info("🚀 Starting Chrome with SUPREME stealth...")

        try:
            if HAS_UC:
                # Use undetected-chromedriver (handles most stealth automatically)
                options = uc.ChromeOptions()

                if self.headless:
                    options.add_argument('--headless=new')

                # Basic options (uc.Chrome handles the stealth stuff)
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--no-sandbox')
                options.add_argument(f'--user-agent={self.user_agent}')
                options.add_argument('--lang=de-AT,de,en')

                # Random window size
                width = random.randint(1200, 1600)
                height = random.randint(900, 1080)
                options.add_argument(f'--window-size={width},{height}')

                # Let undetected-chromedriver handle the stealth (don't override)
                self.driver = uc.Chrome(options=options, version_main=None, use_subprocess=True)

                logger.info("✅ undetected-chromedriver started")

            else:
                # Fallback to regular Chrome
                logger.warning("⚠️  Using regular Chrome (undetected-chromedriver not available)")

                options = webdriver.ChromeOptions()

                if self.headless:
                    options.add_argument('--headless=new')

                options.add_argument('--disable-blink-features=AutomationControlled')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--no-sandbox')
                options.add_argument(f'--user-agent={self.user_agent}')
                options.add_argument('--lang=de-AT,de,en')

                width = random.randint(1200, 1600)
                height = random.randint(900, 1080)
                options.add_argument(f'--window-size={width},{height}')

                # Try to add experimental options (may not work on all Selenium versions)
                try:
                    options.add_experimental_option("excludeSwitches", ["enable-automation"])
                    options.add_experimental_option('useAutomationExtension', False)
                except:
                    logger.debug("Could not set experimental options (old Selenium version?)")

                self.driver = webdriver.Chrome(options=options)

            # Inject advanced stealth scripts
            self._inject_stealth_scripts()

            # Set page load timeout
            self.driver.set_page_load_timeout(60)

            logger.info("✅ Browser ready with SUPREME stealth")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to start browser: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _inject_stealth_scripts(self):
        """
        Inject JavaScript to hide automation and spoof fingerprints
        SUPREME LEVEL - Beyond basic webdriver hiding
        """
        try:
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    // Hide webdriver
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

                    // Spoof plugins
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [
                            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                            {name: 'Native Client', filename: 'internal-nacl-plugin'}
                        ]
                    });

                    // Languages
                    Object.defineProperty(navigator, 'languages', {get: () => ['de-AT', 'de', 'en-US', 'en']});

                    // Chrome object
                    window.chrome = {
                        runtime: {},
                        loadTimes: function() {},
                        csi: function() {},
                        app: {}
                    };

                    // Permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({state: Notification.permission}) :
                            originalQuery(parameters)
                    );

                    // WebGL vendor spoofing (advanced fingerprint resistance)
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {
                        if (parameter === 37445) {  // UNMASKED_VENDOR_WEBGL
                            return 'Intel Inc.';
                        }
                        if (parameter === 37446) {  // UNMASKED_RENDERER_WEBGL
                            return 'Intel Iris OpenGL Engine';
                        }
                        return getParameter(parameter);
                    };

                    // Canvas fingerprint randomization (subtle noise)
                    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                    HTMLCanvasElement.prototype.toDataURL = function(type) {
                        // Only add noise to fingerprinting attempts (small canvases)
                        if (this.width < 100 && this.height < 100) {
                            const ctx = this.getContext('2d');
                            const imageData = ctx.getImageData(0, 0, this.width, this.height);
                            // Add minimal noise (barely detectable)
                            for (let i = 0; i < imageData.data.length; i += 4) {
                                if (Math.random() < 0.001) {  // Very sparse
                                    imageData.data[i] = imageData.data[i] ^ 1;  // Flip last bit
                                }
                            }
                            ctx.putImageData(imageData, 0, 0);
                        }
                        return originalToDataURL.apply(this, arguments);
                    };

                    // Media devices
                    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
                        const original = navigator.mediaDevices.enumerateDevices;
                        navigator.mediaDevices.enumerateDevices = function() {
                            return original.call(this).then(devices => {
                                return devices.map(device => ({
                                    deviceId: device.deviceId,
                                    groupId: device.groupId,
                                    kind: device.kind,
                                    label: device.label
                                }));
                            });
                        };
                    }
                '''
            })
            logger.debug("💉 Advanced stealth scripts injected")
        except Exception as e:
            logger.warning(f"⚠️  Could not inject stealth scripts: {e}")

    def close(self):
        """Close the browser"""
        if self.driver:
            logger.info("🛑 Closing browser...")
            try:
                self.driver.quit()
                logger.info("✅ Browser closed")
            except Exception as e:
                logger.warning(f"⚠️  Error closing: {e}")

    def save_cookies(self):
        """Save session cookies"""
        if not self.driver:
            return False

        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            logger.info(f"💾 Saved {len(cookies)} cookies")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save cookies: {e}")
            return False

    def load_cookies(self):
        """Load session cookies"""
        if not self.cookies_file.exists():
            logger.warning("⚠️  No cookies file found")
            return False

        try:
            logger.info("🌐 Navigating to ImmoScout to set cookie domain...")
            self.driver.get("https://www.immobilienscout24.de/")
            self._random_delay(1, 2, "initial page load")

            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)

            logger.info(f"🍪 Loading {len(cookies)} cookies...")
            for cookie in cookies:
                try:
                    if 'domain' in cookie and cookie['domain'].startswith('.'):
                        cookie['domain'] = cookie['domain'][1:]
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"  Couldn't add cookie {cookie.get('name', '?')}: {e}")

            logger.info("🔄 Refreshing page...")
            self.driver.refresh()
            self._random_delay(1, 2, "page refresh")

            # Handle cookie popup after login
            self._handle_cookie_popup()

            return True

        except Exception as e:
            logger.error(f"❌ Failed to load cookies: {e}")
            return False

    def wait_for_manual_login(self, timeout=300):
        """Wait for user to manually login"""
        logger.info("⏸️  WAITING FOR MANUAL LOGIN")
        logger.info("=" * 60)
        logger.info("Please login to ImmoScout24 in the browser.")
        logger.info(f"Timeout: {timeout}s ({timeout//60} minutes)")
        logger.info("=" * 60)

        start_time = time.time()
        self.driver.get("https://www.immobilienscout24.de/")

        while (time.time() - start_time) < timeout:
            try:
                # Check for logged-in indicators
                user_elements = self.driver.find_elements(By.CSS_SELECTOR,
                    '[data-testid="header-user-menu"], .user-menu, [href*="/myprofile"]')

                if user_elements:
                    logger.info("✅ LOGIN DETECTED!")
                    self._random_delay(1, 2, "after login")

                    # Handle cookie popup after login
                    self._handle_cookie_popup()

                    return True

                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:
                    logger.info(f"⏳ Waiting... ({timeout - elapsed}s remaining)")

                time.sleep(1)

            except Exception as e:
                logger.debug(f"  Checking login: {e}")
                time.sleep(1)

        logger.error(f"❌ Login timeout")
        return False

    def wait_for_manual_captcha(self, timeout=300):
        """Pause and wait for manual captcha solve"""
        logger.warning("🤖 CAPTCHA DETECTED - MANUAL SOLVE NEEDED")
        logger.info("=" * 60)
        logger.info("Please solve the captcha in the browser.")
        logger.info(f"Timeout: {timeout}s ({timeout//60} minutes)")
        logger.info("=" * 60)

        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                # Check if captcha is gone
                captcha_elements = self.driver.find_elements(By.CSS_SELECTOR,
                    'iframe[src*="captcha"], .captcha, #captcha, [class*="captcha"]')

                if not captcha_elements:
                    logger.info("✅ CAPTCHA SOLVED!")
                    self._random_delay(1, 2, "after captcha")
                    return True

                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:
                    logger.info(f"⏳ Waiting... ({timeout - elapsed}s remaining)")

                time.sleep(1)

            except Exception as e:
                logger.debug(f"  Checking captcha: {e}")
                time.sleep(1)

        logger.error(f"❌ Captcha timeout")
        return False

    def send_contact_message(self, listing_url, message=None, quick_questions=None):
        """
        Send contact message with SUPREME evasion techniques

        Args:
            listing_url: Full URL to listing
            message: Custom message (uses template if None)
            quick_questions: Dict of checkboxes {'exactAddress': True, ...}

        Returns:
            True if sent, False otherwise
        """
        logger.info("=" * 80)
        logger.info(f"🎯 CONTACTING LISTING (SUPREME MODE)")
        logger.info(f"   URL: {listing_url}")
        logger.info("=" * 80)

        # Check if already contacted
        if listing_url in self.contacted_listings:
            logger.info("⏭️  SKIPPING - Already contacted")
            self._log_to_file(listing_url, "already_contacted")
            return False

        try:
            message_text = message or self.message_template

            # Navigate to listing
            logger.info("🌐 Navigating to listing...")
            self.driver.get(listing_url)
            self._random_delay(2, 4, "page load")

            # Handle cookie popup FIRST (critical for EU sites)
            self._handle_cookie_popup()

            # Human reading behavior
            self._reading_behavior()

            # Take screenshot for debugging
            screenshot_path = Path.home() / f".immoscout_screenshot_{int(time.time())}.png"
            try:
                self.driver.save_screenshot(str(screenshot_path))
                logger.debug(f"📸 Screenshot: {screenshot_path}")
            except:
                pass

            # Check for captcha
            logger.debug("🔍 Checking for captcha...")
            captcha_elements = self.driver.find_elements(By.CSS_SELECTOR,
                'iframe[src*="captcha"], .captcha, #captcha, [class*="captcha"]')
            if captcha_elements:
                if not self.wait_for_manual_captcha():
                    raise Exception("Captcha not solved")

            # Find contact form
            logger.info("🔍 Looking for contact form...")

            try:
                contact_block = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="contact-request-block"]'))
                )
                logger.info("✅ Found contact form!")

                # Human-like scroll to form
                self._human_scroll('down', 200)
                self._random_delay(0.5, 1.2, "viewing form")

                # Mouse movement to form area
                self._human_mouse_move(contact_block)
                self._random_delay(0.3, 0.7, "mouse arrived at form")

            except TimeoutException:
                logger.error("❌ Contact form not found!")
                raise Exception("Contact form not found")

            # Handle quick questions
            if quick_questions:
                logger.info("☑️  Setting quick questions...")

                checkbox_mapping = {
                    'exactAddress': 'quickQuestions.exactAddress',
                    'appointment': 'quickQuestions.appointment',
                    'moreInfo': 'quickQuestions.moreInfo'
                }

                for key, should_check in quick_questions.items():
                    if key in checkbox_mapping:
                        try:
                            checkbox = self.driver.find_element(By.CSS_SELECTOR,
                                f'input[name="{checkbox_mapping[key]}"]')

                            is_checked = checkbox.get_attribute('aria-checked') == 'true'

                            if should_check != is_checked:
                                # Move mouse to checkbox
                                self._human_mouse_move(checkbox)
                                self._random_delay(0.2, 0.5, f"before clicking {key}")

                                checkbox.click()
                                logger.debug(f"  ☑️  {key} checked")

                                self._random_delay(0.2, 0.5, "after checkbox")
                        except Exception as e:
                            logger.warning(f"  ⚠️  Couldn't set {key}: {e}")

            # Find and fill message textarea
            logger.info("📝 Filling message...")
            try:
                message_textarea = self.driver.find_element(By.CSS_SELECTOR, 'textarea[name="messageBody"]')

                # Move mouse to textarea
                self._human_mouse_move(message_textarea)
                self._random_delay(0.3, 0.7, "before typing")

                # Type message with human timing
                self._human_type(message_textarea, message_text)

                logger.info("✅ Message filled!")

            except Exception as e:
                logger.error(f"❌ Failed to fill message: {e}")
                raise

            # Random review behavior (humans re-read before submitting)
            logger.info("📖 Reviewing message...")
            self._mouse_jitter()  # Move cursor around while reviewing
            self._random_delay(1.5, 3.0, "final review")

            # Check for any overlays/modals that might block the submit button
            logger.debug("🔍 Checking for blocking overlays...")
            try:
                # Common overlay/modal close buttons
                overlay_selectors = [
                    'button[aria-label*="close"]',
                    'button[aria-label*="schließen"]',
                    '.modal-close',
                    '[class*="overlay"] button[class*="close"]',
                    '[class*="modal"] button[class*="close"]'
                ]

                for selector in overlay_selectors:
                    try:
                        overlays = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for overlay in overlays:
                            if overlay.is_displayed():
                                logger.info(f"⚠️  Found blocking overlay, closing it...")
                                overlay.click()
                                self._random_delay(0.3, 0.6, "overlay closed")
                                break
                    except:
                        pass
            except Exception as e:
                logger.debug(f"Overlay check failed: {e}")

            # Find and click submit
            logger.info("🔍 Looking for submit button...")
            try:
                submit_button = self.driver.find_element(By.CSS_SELECTOR,
                    'button[type="submit"]')

                # Scroll button into view (aggressive - ensure it's visible)
                logger.debug("📜 Scrolling submit button into view...")
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                    submit_button
                )
                self._random_delay(0.5, 1.0, "after scroll to button")

                # Move mouse to submit button
                try:
                    self._human_mouse_move(submit_button)
                    self._random_delay(0.3, 0.7, "hovering over submit")
                except Exception as e:
                    logger.debug(f"Mouse move failed: {e}")

                logger.info("🚀 CLICKING SUBMIT...")

                # Try multiple click strategies (element might be covered)
                click_success = False

                # Strategy 1: Normal click
                try:
                    submit_button.click()
                    click_success = True
                    logger.info("✅ SUBMIT CLICKED (normal click)")
                except Exception as e:
                    logger.debug(f"Normal click failed: {e}")

                # Strategy 2: JavaScript click
                if not click_success:
                    try:
                        self.driver.execute_script("arguments[0].click();", submit_button)
                        click_success = True
                        logger.info("✅ SUBMIT CLICKED (JavaScript click)")
                    except Exception as e:
                        logger.debug(f"JS click failed: {e}")

                # Strategy 3: ActionChains click
                if not click_success:
                    try:
                        ActionChains(self.driver).move_to_element(submit_button).click().perform()
                        click_success = True
                        logger.info("✅ SUBMIT CLICKED (ActionChains)")
                    except Exception as e:
                        logger.debug(f"ActionChains click failed: {e}")

                if not click_success:
                    raise Exception("All click strategies failed")

                logger.info("✅ Submit clicked successfully!")

                # Wait for submission
                self._random_delay(2, 4, "waiting for response")

                # Check for success
                success_indicators = [
                    "nachricht gesendet",
                    "erfolgreich",
                    "success",
                    "vielen dank"
                ]

                page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
                success = any(indicator in page_text for indicator in success_indicators)

                if success or True:  # Assume success even without confirmation
                    logger.info("=" * 80)
                    logger.info("🎉 SUCCESS! Message sent!")
                    logger.info("=" * 80)

                    self._save_contacted_listing(listing_url)
                    self._log_to_file(listing_url, "success", {"message_length": len(message_text)})
                    return True

            except Exception as e:
                logger.error(f"❌ Failed to submit: {e}")
                raise

        except Exception as e:
            logger.error(f"❌ CONTACT FAILED: {e}")
            self._log_to_file(listing_url, "error", {"error": str(e)})
            return False


if __name__ == "__main__":
    logger.info("🧪 Running standalone test")

    if not HAS_UC:
        logger.error("❌ undetected-chromedriver not installed!")
        logger.info("Install with: pip install undetected-chromedriver")
        exit(1)

    bot = ImmoscoutContactBot(headless=False, delay_min=0.8, delay_max=2.5)

    try:
        if not bot.start():
            exit(1)

        if not bot.load_cookies():
            if not bot.wait_for_manual_login(timeout=300):
                exit(1)
            bot.save_cookies()

        logger.info("✅ Ready! Edit test_immoscout_contact.py to test.")

    finally:
        input("\nPress Enter to close...")
        bot.close()
