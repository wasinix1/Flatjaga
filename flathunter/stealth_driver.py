"""
Stealth Driver for Bot Detection Resistance
Production-ready stealth browser for apartment hunting
"""

import undetected_chromedriver as uc
import random
import time
import logging
import os

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


class StealthDriver:
    """Production-ready stealth browser for apartment hunting"""

    USER_AGENTS = [
        # Real user agents from Vienna (check your analytics)
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]

    def __init__(self, headless=True):
        self.headless = headless
        self.driver = None
        self.session_start = time.time()
        self.actions_count = 0

    def start(self):
        """Start the stealth browser with anti-detection measures"""
        options = uc.ChromeOptions()

        if self.headless:
            options.add_argument('--headless=new')  # New headless mode is better

        # Essential anti-detection args
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument(f'--window-size={random.randint(1366, 1920)},{random.randint(768, 1080)}')

        # Random user agent
        options.add_argument(f'--user-agent={random.choice(self.USER_AGENTS)}')

        # Language/locale (match your target region)
        options.add_argument('--lang=de-AT')

        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        try:
            self.driver = uc.Chrome(options=options, version_main=None)
            self._inject_stealth_scripts()
            logger.info(f"Stealth browser started (headless={self.headless})")
        except Exception as e:
            logger.error(f"Failed to start stealth browser: {e}")
            # Fallback to regular Chrome if undetected-chromedriver fails
            logger.info("Falling back to regular Chrome driver")
            from selenium import webdriver
            chrome_options = webdriver.ChromeOptions()
            if self.headless:
                chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument(f'--user-agent={random.choice(self.USER_AGENTS)}')
            chrome_options.add_argument('--lang=de-AT')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Regular Chrome driver started (fallback)")

    def _inject_stealth_scripts(self):
        """Make browser look more human"""
        try:
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['de-AT', 'de', 'en']});
                    window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}};
                '''
            })
        except Exception as e:
            logger.warning(f"Could not inject stealth scripts (may not be supported): {e}")

    def smart_delay(self, min_sec=0.5, max_sec=2.0):
        """Human-like random delays"""
        delay = random.uniform(min_sec, max_sec)

        # Occasionally pause longer (humans get distracted)
        if random.random() < 0.1:  # 10% chance
            delay *= random.uniform(2, 4)

        time.sleep(delay)

    def should_restart(self):
        """Restart browser periodically to avoid memory leaks & detection"""
        # Restart every 2 hours or 100 actions
        hours_running = (time.time() - self.session_start) / 3600
        return hours_running > 2 or self.actions_count > 100

    def navigate(self, url, auto_delay=False):
        """Navigate with anti-detection measures

        Args:
            url: URL to navigate to
            auto_delay: If True, adds automatic delay after navigation (default False)
                       Callers should handle their own delays for better control
        """
        self.actions_count += 1

        # Check if we should restart
        if self.should_restart():
            logger.info("Restarting browser (prevent detection & leaks)")
            self.restart()

        self.driver.get(url)

        # Only auto-delay if explicitly requested (callers usually handle delays themselves)
        if auto_delay:
            self.smart_delay(0.3, 0.6)  # Reduced from 1-2s to 0.3-0.6s

    def restart(self):
        """Clean restart"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.start()
        self.session_start = time.time()
        self.actions_count = 0

    def quit(self):
        """Close the browser"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Stealth browser closed")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
