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

    def __init__(self, config, id_watch=None):
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
        self.id_watch = id_watch

        # Get config options
        self.enabled = config.get('wg_gesucht_auto_contact', False)
        self.template_index = config.get('wg_gesucht_template_index', 0)
        self.headless = config.get('wg_gesucht_headless', True)

        logger.info(f"WgGesuchtContactProcessor initialized (enabled={self.enabled}, title cross-ref enabled)")
    
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
        WITH TITLE CROSS-REFERENCE: Prevents duplicate contacts across platforms

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

        # Check if title was already contacted (cross-platform check)
        if self.id_watch:
            title = expose.get('title', '')
            if self.id_watch.is_title_contacted(title):
                logger.info(f"Skipping - title already contacted: {title[:50]}...")
                expose['_auto_contacted'] = False
                return expose

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

                # Mark title as contacted to prevent duplicates across platforms
                if self.id_watch:
                    self.id_watch.mark_title_contacted(expose)
            else:
                logger.warning("⚠️  Failed to contact listing")
                expose['_auto_contacted'] = False

                # If session became invalid, stop trying
                if not self.bot.session_valid:
                    logger.error("⚠️  Session invalid. Disabling bot for this run.")
                    self.bot_ready = False
        
        except Exception as e:
            logger.error(f"Error contacting WG-Gesucht listing: {e}")
            expose['_auto_contacted'] = False
        
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
