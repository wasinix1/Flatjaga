"""
Willhaben Auto-Contact Processor - WITH AUTO-RECOVERY
Detects browser crashes and restarts automatically
"""

from flathunter.logging import logger
from willhaben_contact_bot import WillhabenContactBot
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
import time


class WillhabenContactProcessor:
    """Processor that auto-contacts willhaben listings - with crash recovery"""
    
    def __init__(self, config):
        self.config = config
        self.bot = None
        self.bot_ready = False
        self.total_contacted = 0
        self.total_errors = 0
        logger.info("Willhaben auto-contact processor initialized (with auto-recovery)")
    
    def _is_browser_dead(self, error):
        """Check if error indicates browser crash"""
        error_str = str(error).lower()
        dead_indicators = [
            'invalid session id',
            'session deleted',
            'browser has closed',
            'disconnected: not connected to devtools',
            'chrome not reachable'
        ]
        return any(indicator in error_str for indicator in dead_indicators)
    
    def _restart_bot(self):
        """Kill and restart the browser"""
        logger.warning("Browser crashed or disconnected - restarting...")
        
        # Close old browser if it exists
        if self.bot:
            try:
                self.bot.close()
            except:
                pass  # Already dead, that's fine
        
        self.bot = None
        self.bot_ready = False
        
        # Wait a moment before restarting
        time.sleep(2)
        
        # Try to reinit
        return self._init_bot()
    
    def _init_bot(self):
        """Lazy init the selenium bot"""
        if self.bot_ready:
            return True
        
        try:
            logger.info("Starting willhaben contact bot (headless)...")
            self.bot = WillhabenContactBot(headless=True)
            self.bot.start()
            
            if not self.bot.load_cookies():
                logger.warning(
                    "No willhaben session found. "
                    "Run 'python willhaben_contact_bot.py' to login first."
                )
                return False
            
            self.bot_ready = True
            logger.info(f"✓ Willhaben bot ready (stats: {self.total_contacted} contacted, {self.total_errors} errors)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start willhaben bot: {e}")
            return False
    
    def process_expose(self, expose):
        """
        Process a single expose - contact if willhaben
        WITH AUTO-RECOVERY: Restarts browser if it crashes
        """
        # Check if it's willhaben
        crawler = expose.get('crawler', '').lower()
        url = expose.get('url', '')
        
        if 'willhaben' not in crawler and 'willhaben.at' not in url:
            return expose  # Not willhaben, pass through
        
        # Init bot if needed
        if not self._init_bot():
            return expose  # Bot failed, pass through
        
        # Try to contact (with auto-recovery)
        max_retries = 2
        for attempt in range(max_retries):
            start_time = time.time()
            try:
                title = expose.get('title', 'Unknown')
                logger.info(f"Auto-contacting: {title[:50]}..." + 
                           (f" (retry {attempt+1})" if attempt > 0 else ""))
                
                success = self.bot.send_contact_message(url)
                
                elapsed = time.time() - start_time
                if success:
                    self.total_contacted += 1
                    logger.info(f"✓ Contacted successfully ({elapsed:.1f}s, total: {self.total_contacted})")
                    expose['_auto_contacted'] = True
                else:
                    logger.debug(f"Already contacted or skipped ({elapsed:.1f}s)")
                    expose['_auto_contacted'] = False
                
                # Success - break out of retry loop
                break
                
            except (InvalidSessionIdException, WebDriverException) as e:
                elapsed = time.time() - start_time
                
                if self._is_browser_dead(e):
                    self.total_errors += 1
                    logger.error(f"Browser crashed ({elapsed:.1f}s)")
                    
                    # Try to restart browser and retry
                    if attempt < max_retries - 1:
                        if self._restart_bot():
                            continue  # Try again with new browser
                        else:
                            logger.error("Failed to restart browser - giving up")
                            expose['_auto_contacted'] = False
                            break
                    else:
                        logger.error("Max retries reached - giving up on this listing")
                        expose['_auto_contacted'] = False
                else:
                    # Some other WebDriver error
                    logger.error(f"WebDriver error ({elapsed:.1f}s): {e}")
                    expose['_auto_contacted'] = False
                    break
                    
            except Exception as e:
                elapsed = time.time() - start_time
                self.total_errors += 1
                logger.error(f"Unexpected error ({elapsed:.1f}s): {e}")
                expose['_auto_contacted'] = False
                break
        
        return expose
    
    def close(self):
        """Cleanup - call this when flathunter exits"""
        if self.bot:
            try:
                logger.info(f"Closing willhaben bot (final stats: {self.total_contacted} contacted, {self.total_errors} errors)")
                self.bot.close()
            except Exception as e:
                logger.error(f"Error closing bot: {e}")