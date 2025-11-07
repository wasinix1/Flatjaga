"""
WG-Gesucht Auto-Contact Processor - WITH AUTO-RECOVERY
Detects browser crashes and restarts automatically
"""

from flathunter.logger_config import logger
from flathunter.wg_gesucht_contact_bot import WgGesuchtContactBot, SessionExpiredException
from flathunter.session_manager import SessionManager
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
import time
import json
from pathlib import Path
from datetime import datetime


class WgGesuchtContactProcessor:
    """Processor that auto-contacts WG-Gesucht listings - with crash recovery and headless fallback"""

    def __init__(self, config, telegram_notifier=None, id_watch=None, session_manager=None):
        """
        Initialize processor with config.

        Config options:
            wg_gesucht_auto_contact: bool - Enable auto-contact (default False)
            wg_gesucht_template_index: int - Which template to use (default 0)
            wg_gesucht_headless: bool - Run in headless mode (default True)
            wg_gesucht_delay_min: float - Minimum delay between actions (default 0.5)
            wg_gesucht_delay_max: float - Maximum delay between actions (default 1.5)
            wg_gesucht_stealth_mode: bool - Enable stealth mode with undetected-chromedriver (default False)
        """
        self.config = config
        self.bot = None
        self.bot_ready = False
        self.total_contacted = 0
        self.total_errors = 0
        self.telegram_notifier = telegram_notifier
        self.id_watch = id_watch
        self.session_manager = session_manager or SessionManager()

        # Get config options
        self.enabled = config.get('wg_gesucht_auto_contact', False)
        self.template_index = config.get('wg_gesucht_template_index', 0)
        self.headless = config.get('wg_gesucht_headless', True)
        self.delay_min = config.get('wg_gesucht_delay_min', 0.5)
        self.delay_max = config.get('wg_gesucht_delay_max', 1.5)
        self.stealth_mode = config.get('wg_gesucht_stealth_mode', False)

        # Track headless mode for fallback
        self.headless_original = self.headless  # Remember original setting
        self.current_headless = self.headless  # Track current mode

        # Setup failure log file
        self.failure_log_file = Path.home() / '.wg_gesucht_contact_failures.jsonl'

        logger.info(f"WG-Gesucht auto-contact processor initialized (with auto-recovery, enabled={self.enabled}, headless={self.headless}, stealth_mode={self.stealth_mode}, title cross-ref enabled, session tracking enabled)")

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

    def _restart_bot(self, use_headless=None, increase_delays=False):
        """
        Kill and restart the browser

        Args:
            use_headless: Override headless mode (None = use current setting)
            increase_delays: If True, double the delays for more cautious approach
        """
        if use_headless is not None:
            logger.warning(f"Browser crashed or disconnected - restarting with headless={use_headless}...")
        else:
            logger.warning("Browser crashed or disconnected - restarting...")

        if increase_delays:
            logger.info("Using higher delays for more cautious approach")

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

        # Try to reinit with specified headless mode and delays
        return self._init_bot(use_headless=use_headless, increase_delays=increase_delays)

    def _init_bot(self, use_headless=None, increase_delays=False, _retry_with_visible=True):
        """
        Lazy init the selenium bot with automatic fallback to visible browser

        Args:
            use_headless: Override headless mode (None = use current setting)
            increase_delays: If True, double the delays for more cautious approach
            _retry_with_visible: Internal flag to control fallback retry (prevents infinite recursion)
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

        # Determine delays to use
        if increase_delays:
            delay_min = self.delay_min * 2
            delay_max = self.delay_max * 2
        else:
            delay_min = self.delay_min
            delay_max = self.delay_max

        try:
            logger.info(f"Starting WG-Gesucht contact bot (headless={headless_mode}, delays={delay_min}-{delay_max}s, stealth_mode={self.stealth_mode})...")
            self.bot = WgGesuchtContactBot(
                headless=headless_mode,
                template_index=self.template_index,
                delay_min=delay_min,
                delay_max=delay_max,
                stealth_mode=self.stealth_mode
            )
            self.bot.start()

            if not self.bot.load_cookies():
                logger.warning(
                    "No WG-Gesucht session found. "
                    "Run 'python setup_sessions.py' to login first."
                )

                # FALLBACK: If headless mode and we haven't tried visible browser yet
                if headless_mode and _retry_with_visible and self.headless_original:
                    logger.warning("Session loading failed in headless mode - retrying with visible browser...")
                    # Close failed bot
                    if self.bot:
                        try:
                            self.bot.close()
                        except:
                            pass
                    self.bot = None
                    # Retry with visible browser (don't retry again to prevent infinite loop)
                    return self._init_bot(use_headless=False, increase_delays=increase_delays, _retry_with_visible=False)

                return False

            if not self.bot.session_valid:
                logger.error(
                    "WG-Gesucht session not valid. "
                    "Run 'python setup_sessions.py' to login first."
                )

                # FALLBACK: If headless mode and we haven't tried visible browser yet
                if headless_mode and _retry_with_visible and self.headless_original:
                    logger.warning("Session validation failed in headless mode - retrying with visible browser...")
                    # Close failed bot
                    if self.bot:
                        try:
                            self.bot.close()
                        except:
                            pass
                    self.bot = None
                    # Retry with visible browser (don't retry again to prevent infinite loop)
                    return self._init_bot(use_headless=False, increase_delays=increase_delays, _retry_with_visible=False)

                return False

            self.bot_ready = True

            # Update session timestamp on successful initialization
            self.session_manager.update_timestamp('wg_gesucht', valid=True)

            logger.info(f"✓ WG-Gesucht bot ready (headless={headless_mode}, stats: {self.total_contacted} contacted, {self.total_errors} errors)")
            return True

        except Exception as e:
            logger.error(f"Failed to start WG-Gesucht bot: {e}")

            # FALLBACK: If headless mode and we haven't tried visible browser yet
            if headless_mode and _retry_with_visible and self.headless_original:
                logger.warning(f"Bot initialization failed in headless mode ({e}) - retrying with visible browser...")
                # Close failed bot
                if self.bot:
                    try:
                        self.bot.close()
                    except:
                        pass
                self.bot = None
                # Retry with visible browser (don't retry again to prevent infinite loop)
                return self._init_bot(use_headless=False, increase_delays=increase_delays, _retry_with_visible=False)

            return False

    def keep_session_active(self):
        """
        Check and validate session to prevent expiry.
        Opens browser if 2+ hours have passed since last validation.
        Uses headless=false for stability during validation.
        """
        # Check if processor is enabled in config
        if not self.enabled:
            return True

        # Check if processor is disabled by session manager
        if not self.session_manager.is_enabled('wg_gesucht'):
            logger.warning("WG-Gesucht processor is disabled - skipping session check")
            return False

        # Check if validation is needed
        if not self.session_manager.needs_validation('wg_gesucht'):
            return True

        logger.info("WG-Gesucht session validation needed (2+ hours elapsed)")

        # Start browser with headless=false for stability
        temp_bot = None
        try:
            logger.info("Opening browser for session validation (headless=false)...")
            temp_bot = WgGesuchtContactBot(
                headless=False,
                template_index=self.template_index,
                delay_min=self.delay_min,
                delay_max=self.delay_max,
                stealth_mode=self.stealth_mode
            )
            temp_bot.start()

            # Load cookies and validate
            if not temp_bot.load_cookies():
                logger.error("No WG-Gesucht session found during validation")
                self.session_manager.disable('wg_gesucht', "No session cookies found")

                # Send telegram notification
                if self.telegram_notifier:
                    self.telegram_notifier.notify(
                        "⚠️ WG-GESUCHT SESSION EXPIRED ⚠️\n\n"
                        "Session cookies not found.\n"
                        "Please run 'python setup_sessions.py' to re-login.\n\n"
                        "Auto-contact for WG-Gesucht is now DISABLED until restart."
                    )
                return False

            # Session valid flag should be set by load_cookies
            if not temp_bot.session_valid:
                logger.error("WG-Gesucht session validation failed")
                self.session_manager.disable('wg_gesucht', "Session validation failed")

                # Send telegram notification
                if self.telegram_notifier:
                    self.telegram_notifier.notify(
                        "⚠️ WG-GESUCHT SESSION EXPIRED ⚠️\n\n"
                        "Session validation failed.\n"
                        "Please run 'python setup_sessions.py' to re-login.\n\n"
                        "Auto-contact for WG-Gesucht is now DISABLED until restart."
                    )
                return False

            # Session is valid
            logger.info("✓ WG-Gesucht session validated successfully")
            self.session_manager.update_timestamp('wg_gesucht', valid=True)
            return True

        except Exception as e:
            logger.error(f"Session validation failed: {e}")
            self.session_manager.disable('wg_gesucht', f"Validation error: {str(e)[:100]}")

            # Send telegram notification
            if self.telegram_notifier:
                self.telegram_notifier.notify(
                    f"⚠️ WG-GESUCHT SESSION VALIDATION FAILED ⚠️\n\n"
                    f"Error: {str(e)[:200]}\n\n"
                    f"Please run 'python setup_sessions.py' to re-login.\n\n"
                    f"Auto-contact for WG-Gesucht is now DISABLED until restart."
                )
            return False

        finally:
            # Always close browser after validation
            if temp_bot:
                try:
                    temp_bot.close()
                    logger.info("Closed validation browser")
                except Exception as e:
                    logger.warning(f"Error closing validation browser: {e}")

    def process_expose(self, expose):
        """
        Process a single expose - contact if WG-Gesucht
        WITH AUTO-RECOVERY: Restarts browser if it crashes
        WITH HEADLESS FALLBACK: Retries with headless=false if headless mode fails
        WITH TITLE CROSS-REFERENCE: Prevents duplicate contacts across platforms
        """
        # Check if it's WG-Gesucht
        crawler = expose.get('crawler', '').lower()
        url = expose.get('url', '')

        if 'wg-gesucht' not in url and 'wg_gesucht' not in crawler:
            return expose  # Not WG-Gesucht, pass through

        # Check if processor is disabled
        if not self.session_manager.is_enabled('wg_gesucht'):
            logger.warning("WG-Gesucht processor is disabled - skipping listing")
            expose['_auto_contacted'] = False
            return expose

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

        # Track if we should try headless fallback
        tried_non_headless = False
        tried_browser_restart = False

        # Try to contact (with auto-recovery)
        # Try 2 times, then restart browser with higher delays and try 2 more times
        max_retries_per_attempt = 2
        for browser_session in range(2):  # Two browser sessions: normal, then with higher delays
            # If this is the second session, restart browser with higher delays
            if browser_session == 1:
                logger.warning("Failed twice - restarting browser with higher delays for more cautious approach")
                if not self._restart_bot(increase_delays=True):
                    logger.error("Failed to restart browser with higher delays")
                    expose['_auto_contacted'] = False
                    self._log_failure_to_file(expose, "Failed to restart browser with higher delays", "browser_restart_failed")
                    break
                tried_browser_restart = True

            for attempt in range(max_retries_per_attempt):
                start_time = time.time()
                try:
                    title = expose.get('title', 'Unknown')
                    retry_msg = f" (session {browser_session+1}, attempt {attempt+1})" if browser_session > 0 or attempt > 0 else ""
                    if retry_msg:
                        logger.info(f"  Retry: {retry_msg}")

                    success = self.bot.send_contact_message(url)

                    elapsed = time.time() - start_time
                    if success:
                        self.total_contacted += 1
                        logger.debug(f"Contact successful ({elapsed:.1f}s, total: {self.total_contacted})")
                        expose['_auto_contacted'] = True

                        # Mark title as contacted to prevent duplicates across platforms
                        if self.id_watch:
                            self.id_watch.mark_title_contacted(expose)

                        # Reset to original headless mode after success
                        if self.current_headless != self.headless_original:
                            self.current_headless = self.headless_original
                            logger.info(f"Resetting to headless={self.headless_original} for next listing")

                        # Success - exit all retry loops
                        browser_session = 999  # Break outer loop
                        break
                    else:
                        logger.debug(f"Already contacted or skipped ({elapsed:.1f}s)")
                        expose['_auto_contacted'] = False
                        # Not a success - continue to next attempt
                        continue

                except SessionExpiredException as e:
                    elapsed = time.time() - start_time
                    self.total_errors += 1
                    logger.error(f"Session expired ({elapsed:.1f}s) - run standalone bot to re-login")
                    expose['_auto_contacted'] = False

                    # Log failure with special category
                    self._log_failure_to_file(expose, str(e), "session_expired")

                    # Disable processor until restart
                    self.session_manager.disable('wg_gesucht', "Session expired during contact")

                    # Send telegram notification
                    if self.telegram_notifier:
                        self.telegram_notifier.notify(
                            "⚠️ WG-GESUCHT SESSION EXPIRED ⚠️\n\n"
                            "Session expired while contacting listing.\n"
                            "Please run 'python setup_sessions.py' to re-login.\n\n"
                            "Auto-contact for WG-Gesucht is now DISABLED until restart."
                        )

                    # Stop processing - session is expired, mark bot as not ready
                    self.bot_ready = False
                    # Don't try headless fallback for session expiration
                    tried_non_headless = True
                    browser_session = 999  # Break outer loop
                    break

                except (InvalidSessionIdException, WebDriverException) as e:
                    elapsed = time.time() - start_time

                    if self._is_browser_dead(e):
                        self.total_errors += 1
                        error_msg = f"Browser crashed ({elapsed:.1f}s)"
                        logger.error(error_msg)

                        # Try to restart browser and retry within this session
                        if attempt < max_retries_per_attempt - 1:
                            if self._restart_bot(increase_delays=(browser_session == 1)):
                                continue  # Try again with new browser
                            else:
                                logger.error("Failed to restart browser")
                                expose['_auto_contacted'] = False
                                self._log_failure_to_file(expose, "Failed to restart browser", "browser_crash")
                                break
                        else:
                            # Max retries for this session - will try next session or give up
                            logger.error(f"Max retries reached for session {browser_session+1}")
                            expose['_auto_contacted'] = False
                            self._log_failure_to_file(expose, f"Max retries reached in session {browser_session+1}", "browser_crash_max_retries")
                            break
                    else:
                        # Some other WebDriver error
                        self.total_errors += 1
                        error_msg = f"WebDriver error ({elapsed:.1f}s): {e}"
                        logger.error(error_msg)
                        expose['_auto_contacted'] = False
                        self._log_failure_to_file(expose, str(e), "webdriver_error")
                        break

                except Exception as e:
                    elapsed = time.time() - start_time
                    self.total_errors += 1
                    error_msg = f"Unexpected error ({elapsed:.1f}s): {e}"
                    logger.error(error_msg)
                    expose['_auto_contacted'] = False
                    self._log_failure_to_file(expose, str(e), "unexpected_error")
                    break

            # If we succeeded, break out of browser_session loop
            if expose.get('_auto_contacted') == True:
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
                    logger.info(f"  Retry with visible browser...")

                    success = self.bot.send_contact_message(url)

                    elapsed = time.time() - start_time
                    if success:
                        self.total_contacted += 1
                        logger.debug(f"Contact successful with visible browser ({elapsed:.1f}s, total: {self.total_contacted})")
                        expose['_auto_contacted'] = True
                        # Success with non-headless - keep using it for consistency
                        logger.info("  Non-headless mode succeeded - will use it for remaining listings")
                    else:
                        logger.debug(f"Already contacted or skipped ({elapsed:.1f}s)")
                        expose['_auto_contacted'] = False
                        # Now send notifications since all retry options exhausted
                        self._send_failure_notification(expose, "Fehler auch mit sichtbarem Browser")

                except SessionExpiredException as e:
                    elapsed = time.time() - start_time
                    logger.error(f"Session expired in non-headless mode ({elapsed:.1f}s)")
                    expose['_auto_contacted'] = False

                    # Disable processor until restart
                    self.session_manager.disable('wg_gesucht', "Session expired during non-headless retry")

                    # Send telegram notification
                    if self.telegram_notifier:
                        self.telegram_notifier.notify(
                            "⚠️ WG-GESUCHT SESSION EXPIRED ⚠️\n\n"
                            "Session expired during non-headless retry.\n"
                            "Please run 'python setup_sessions.py' to re-login.\n\n"
                            "Auto-contact for WG-Gesucht is now DISABLED until restart."
                        )

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

        # Close browser after BOTH success AND failure to ensure fresh start for next listing
        final_status = "success" if expose.get('_auto_contacted') == True else "failure"
        logger.info(f"Closing browser after {final_status} to ensure fresh start for next listing")
        if self.bot:
            try:
                self.bot.close()
            except Exception as e:
                logger.warning(f"Error closing browser after {final_status}: {e}")
        self.bot = None
        self.bot_ready = False

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
