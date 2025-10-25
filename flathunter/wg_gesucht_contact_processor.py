"""
WG-Gesucht Contact Processor
Integrates WG-Gesucht auto-contact into flathunter processing chain.
"""

from wg_gesucht_contact_bot import WgGesuchtContactBot
import logging

logger = logging.getLogger(__name__)


class WgGesuchtContactProcessor:
    """
    Processor that contacts WG-Gesucht listings before sending notifications.
    Follows same pattern as WillhabenContactProcessor.
    """
    
    def __init__(self, config, telegram_notifier=None):
        """
        Initialize processor with config.

        Config options:
            wg_gesucht_auto_contact: bool - Enable auto-contact (default False)
            wg_gesucht_template_index: int - Which template to use (default 0)
            wg_gesucht_headless: bool - Run in headless mode (default True)
        """
        self.config = config
        self.bot = None
        self.bot_ready = False
        self.telegram_notifier = telegram_notifier

        # Get config options
        self.enabled = config.get('wg_gesucht_auto_contact', False)
        self.template_index = config.get('wg_gesucht_template_index', 0)
        self.headless = config.get('wg_gesucht_headless', True)

        logger.info(f"WgGesuchtContactProcessor initialized (enabled={self.enabled})")

    def _send_failure_notification(self, expose, error_message):
        """Send Telegram notification when contact fails"""
        if not self.telegram_notifier:
            return

        try:
            title = expose.get('title', 'Unknown listing')
            url = expose.get('url', '')

            failure_message = (
                f"⚠️ WG-GESUCHT KONTAKT FEHLGESCHLAGEN ⚠️\n\n"
                f"Listing: {title}\n"
                f"URL: {url}\n"
                f"Fehler: {error_message[:200]}"
            )

            self.telegram_notifier.notify(failure_message)
            logger.info(f"Sent failure notification for: {title}")

        except Exception as e:
            logger.error(f"Failed to send failure notification: {e}")

    def _init_bot(self):
        """Initialize bot if needed. Returns True if bot is ready."""
        if self.bot_ready:
            return True
        
        if not self.enabled:
            return False
        
        try:
            logger.info("Starting WG-Gesucht bot...")
            self.bot = WgGesuchtContactBot(
                headless=self.headless,
                template_index=self.template_index
            )
            
            if not self.bot.session_valid:
                logger.error(
                    "WG-Gesucht session not valid. "
                    "Run standalone test to login first."
                )
                return False
            
            self.bot_ready = True
            logger.info("✓ WG-Gesucht bot ready")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start WG-Gesucht bot: {e}")
            return False
    
    def process_expose(self, expose):
        """
        Process a listing expose. If it's a WG-Gesucht listing, contact it.
        
        Args:
            expose: Listing expose dict with at least 'url' field
        
        Returns:
            expose: Modified expose with 'contacted' flag if successful
        """
        
        # Check if this is a WG-Gesucht listing
        url = expose.get('url', '')
        crawler = expose.get('crawler', '').lower()
        
        if 'wg-gesucht' not in url and 'wg_gesucht' not in crawler:
            return expose  # Not WG-Gesucht, pass through
        
        # Init bot if needed
        if not self._init_bot():
            return expose  # Bot failed, pass through
        
        # Try to contact listing
        try:
            title = expose.get('title', 'Unknown')
            logger.info(f"Auto-contacting WG-Gesucht listing: {title}")

            success = self.bot.send_contact_message(url)

            if success:
                logger.info("✓ Successfully contacted")
                expose['_auto_contacted'] = True
            else:
                logger.warning("⚠️  Failed to contact listing")
                expose['_auto_contacted'] = False

                # If session became invalid, stop trying
                if not self.bot.session_valid:
                    error_msg = "Session invalid. Disabling bot for this run."
                    logger.error(f"⚠️  {error_msg}")
                    self.bot_ready = False
                    self._send_failure_notification(expose, error_msg)
                else:
                    self._send_failure_notification(expose, "Failed to send contact message")

        except Exception as e:
            error_msg = f"Error contacting WG-Gesucht listing: {e}"
            logger.error(error_msg)
            expose['_auto_contacted'] = False
            self._send_failure_notification(expose, str(e))
        
        return expose
    
    def cleanup(self):
        """Clean up resources (close browser)."""
        if self.bot:
            logger.info("Closing WG-Gesucht bot...")
            try:
                self.bot.close()
            except Exception as e:
                logger.error(f"Error closing bot: {e}")
            self.bot = None
            self.bot_ready = False
    
    def __del__(self):
        """Cleanup on object destruction."""
        self.cleanup()
