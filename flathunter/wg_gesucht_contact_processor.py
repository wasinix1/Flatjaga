"""
WG-Gesucht Auto-Contact Processor - WITH AUTO-RECOVERY
Detects browser crashes and restarts automatically
"""

from flathunter.logging import logger
from wg_gesucht_contact_bot import WgGesuchtContactBot, SessionExpiredException
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
import time
import json
from pathlib import Path
from datetime import datetime


class WgGesuchtContactProcessor:
    """Processor that auto-contacts WG-Gesucht listings - with crash recovery"""

    def __init__(self, config, telegram_notifier=None):
        self.config = config
        self.bot = None
        self.bot_ready = False
        self.total_contacted = 0
        self.total_errors = 0
        self.telegram_notifier = telegram_notifier

        # Get config options
        self.enabled = config.get('wg_gesucht_auto_contact', False)
        self.template_index = config.get('wg_gesucht_template_index', 0)
        self.headless = config.get('wg_gesucht_headless', True)
        self.headless_original = self.headless  # Remember original setting
        self.current_headless = self.headless  # Track current mode

        # Setup failure log file
        self.failure_log_file = Path.home() / '.wg_gesucht_contact_failures.jsonl'

        logger.info(f"WG-Gesucht auto-contact processor initialized (with auto-recovery, enabled={self.enabled}, headless={self.headless})")

    def _log_failure_to_file(self, expose, error_message, error_type="unknown"):
        """Log contact failure to file with timestamp and details"""
        try:
            failure_entry = {
                "timestamp": datetime.now().isoformat(),
                "url": expose.get('url', 'N/A'),
                "title": expose.get('title', 'N/A'),
                "error_type": error_type,
                "error_message": str(error_message),
                "total_errors": self.total_errors
            }

            # Append to JSONL file (one JSON object per line)
            with open(self.failure_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(failure_entry, ensure_ascii=False) + '\n')

            logger.debug(f"Logged failure to {self.failure_log_file}")

        except Exception as e:
            logger.error(f"Failed to log failure to file: {e}")

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
                f"Fehler: {error_message[:200]}\n\n"
                f"Gesamt Fehler: {self.total_errors}"
            )

            self.telegram_notifier.notify(failure_message)
            logger.info(f"Sent failure notification for: {title}")

        except Exception as e:
            logger.error(f"Failed to send failure notification: {e}")

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

    def _restart_bot(self, use_headless=None):
        """
        Kill and restart the browser

        Args:
            use_headless: Override headless mode (None = use current setting)
        """
        if use_headless is not None:
            logger.warning(f"Browser crashed or disconnected - restarting with headless={use_headless}...")
        else:
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

        # Try to reinit with specified headless mode
        return self._init_bot(use_headless=use_headless)

    def _init_bot(self, use_headless=None):
        """
        Lazy init the selenium bot

        Args:
            use_headless: Override headless mode (None = use current setting)
        """
        if self.bot_ready:
            return True

        if not self.enabled:
            return False

        # Determine headless mode to use
        if use_headless is not None:
            headless_mode = use_headless
            self.current_headless = use_headless
        else:
            headless_mode = self.current_headless

        try:
            logger.info(f"Starting WG-Gesucht contact bot (headless={headless_mode})...")
            self.bot = WgGesuchtContactBot(
                headless=headless_mode,
                template_index=self.template_index
            )
            self.bot.start()

            if not self.bot.load_cookies():
                logger.warning(
                    "No WG-Gesucht session found. "
                    "Run standalone bot to login first."
                )
                return False

            self.bot_ready = True
            logger.info(f"✓ WG-Gesucht bot ready (headless={headless_mode}, stats: {self.total_contacted} contacted, {self.total_errors} errors)")
            return True

        except Exception as e:
            logger.error(f"Failed to start WG-Gesucht bot: {e}")
            return False

    def process_expose(self, expose):
        """
        Process a single expose - contact if WG-Gesucht
        WITH AUTO-RECOVERY: Restarts browser if it crashes
        WITH HEADLESS FALLBACK: Retries with headless=false if headless mode fails
        """
        # Check if it's WG-Gesucht
        crawler = expose.get('crawler', '').lower()
        url = expose.get('url', '')

        if 'wg-gesucht' not in url and 'wg_gesucht' not in crawler:
            return expose  # Not WG-Gesucht, pass through

        # Init bot if needed
        if not self._init_bot():
            return expose  # Bot failed, pass through

        # Track if we should try headless fallback
        tried_non_headless = False

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
                    # Reset to original headless mode after success
                    if self.current_headless != self.headless_original:
                        self.current_headless = self.headless_original
                        logger.info(f"Resetting to headless={self.headless_original} for next listing")
                else:
                    logger.debug(f"Already contacted or skipped ({elapsed:.1f}s)")
                    expose['_auto_contacted'] = False

                # Success - break out of retry loop
                break

            except SessionExpiredException as e:
                elapsed = time.time() - start_time
                self.total_errors += 1
                logger.error(f"Session expired ({elapsed:.1f}s) - run standalone bot to re-login")
                expose['_auto_contacted'] = False

                # Log failure with special category
                self._log_failure_to_file(expose, str(e), "session_expired")

                # Stop processing - session is expired, mark bot as not ready
                self.bot_ready = False
                # Don't try headless fallback for session expiration
                tried_non_headless = True
                break

            except (InvalidSessionIdException, WebDriverException) as e:
                elapsed = time.time() - start_time

                if self._is_browser_dead(e):
                    self.total_errors += 1
                    error_msg = f"Browser crashed ({elapsed:.1f}s)"
                    logger.error(error_msg)

                    # Try to restart browser and retry
                    if attempt < max_retries - 1:
                        if self._restart_bot():
                            continue  # Try again with new browser
                        else:
                            logger.error("Failed to restart browser")
                            expose['_auto_contacted'] = False
                            # Log failure but don't notify yet - might try headless fallback
                            self._log_failure_to_file(expose, "Failed to restart browser", "browser_crash")
                            break
                    else:
                        logger.error("Max retries reached")
                        expose['_auto_contacted'] = False
                        # Log failure but don't notify yet - might try headless fallback
                        self._log_failure_to_file(expose, "Max retries reached after browser crash", "browser_crash_max_retries")
                        break
                else:
                    # Some other WebDriver error
                    self.total_errors += 1
                    error_msg = f"WebDriver error ({elapsed:.1f}s): {e}"
                    logger.error(error_msg)
                    expose['_auto_contacted'] = False
                    # Log failure but don't notify yet - might try headless fallback
                    self._log_failure_to_file(expose, str(e), "webdriver_error")
                    break

            except Exception as e:
                elapsed = time.time() - start_time
                self.total_errors += 1
                error_msg = f"Unexpected error ({elapsed:.1f}s): {e}"
                logger.error(error_msg)
                expose['_auto_contacted'] = False
                # Log failure but don't notify yet - might try headless fallback
                self._log_failure_to_file(expose, str(e), "unexpected_error")
                break

        # HEADLESS FALLBACK: If failed in headless mode, try with visible browser
        if (expose.get('_auto_contacted') == False and
            self.headless_original and
            not tried_non_headless and
            self.current_headless):

            logger.warning("Contact failed in headless mode - trying with visible browser (headless=false)...")
            tried_non_headless = True

            # Restart browser in non-headless mode
            if self._restart_bot(use_headless=False):
                # Try one more time with visible browser
                start_time = time.time()
                try:
                    title = expose.get('title', 'Unknown')
                    logger.info(f"Auto-contacting with visible browser: {title[:50]}...")

                    success = self.bot.send_contact_message(url)

                    elapsed = time.time() - start_time
                    if success:
                        self.total_contacted += 1
                        logger.info(f"✓ Contacted successfully with visible browser ({elapsed:.1f}s, total: {self.total_contacted})")
                        expose['_auto_contacted'] = True
                        # Success with non-headless - keep using it for consistency
                        logger.info("Non-headless mode succeeded - will use it for remaining listings")
                    else:
                        logger.debug(f"Already contacted or skipped ({elapsed:.1f}s)")
                        expose['_auto_contacted'] = False
                        # Now send notifications since all retry options exhausted
                        self._send_failure_notification(expose, "Fehler auch mit sichtbarem Browser")

                except SessionExpiredException as e:
                    elapsed = time.time() - start_time
                    logger.error(f"Session expired in non-headless mode ({elapsed:.1f}s)")
                    expose['_auto_contacted'] = False
                    self.bot_ready = False
                    # Don't send notification for session expiration

                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.error(f"Error in non-headless mode ({elapsed:.1f}s): {e}")
                    expose['_auto_contacted'] = False
                    # Send notification since all options exhausted
                    self._send_failure_notification(expose, f"Fehler auch mit sichtbarem Browser: {str(e)[:100]}")
            else:
                logger.error("Failed to restart browser in non-headless mode")
                # Send notification since we couldn't even try the fallback
                self._send_failure_notification(expose, "Neustart mit sichtbarem Browser fehlgeschlagen")

        # If we failed and didn't try headless fallback, send notification now
        elif expose.get('_auto_contacted') == False and not tried_non_headless:
            self._send_failure_notification(expose, "Kontakt fehlgeschlagen")

        return expose

    def cleanup(self):
        """Cleanup - call this when flathunter exits"""
        if self.bot:
            try:
                logger.info(f"Closing WG-Gesucht bot (final stats: {self.total_contacted} contacted, {self.total_errors} errors)")
                self.bot.close()
            except Exception as e:
                logger.error(f"Error closing bot: {e}")

    def __del__(self):
        """Cleanup on object destruction"""
        self.cleanup()
