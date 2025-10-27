"""Default Flathunter implementation for the command line"""
import re
import traceback
import time
from itertools import chain
import requests

from flathunter.logging import logger
from flathunter.config import YamlConfig
from flathunter.filter import Filter
from flathunter.processor import ProcessorChain
from flathunter.captcha.captcha_solver import CaptchaUnsolvableError
from flathunter.exceptions import ConfigException

from flathunter.willhaben_contact_processor import WillhabenContactProcessor
from flathunter.wg_gesucht_contact_processor import WgGesuchtContactProcessor
from flathunter.notifiers import SenderTelegram
from flathunter.session_manager import SessionManager

class Hunter:
    """Basic methods for crawling and processing / filtering exposes"""

    def __init__(self, config: YamlConfig, id_watch):
        self.config = config
        if not isinstance(self.config, YamlConfig):
            raise ConfigException(
                "Invalid config for hunter - should be a 'Config' object")
        self.id_watch = id_watch

        # Track last crawl time per crawler to implement per-site delays
        self.last_crawl_times = {}

        # Track last crawl status for each active crawler
        self.crawler_status = {}  # {crawler_name: {'status': 'success'|'error', 'result_count': int, 'message': str}}

        # Initialize telegram notifier for success/failure notifications
        self.telegram_notifier = None
        if 'telegram' in self.config.notifiers():
            self.telegram_notifier = SenderTelegram(self.config)

        # Initialize shared session manager for both processors
        self.session_manager = SessionManager()

        # Initialize willhaben processor with telegram notifier, id_watch, and session manager
        self.willhaben_processor = WillhabenContactProcessor(
            config, self.telegram_notifier, id_watch, self.session_manager
        )

        # Initialize wg-gesucht processor with telegram notifier, id_watch, and session manager
        self.wg_gesucht_processor = WgGesuchtContactProcessor(
            config, self.telegram_notifier, id_watch, self.session_manager
        )


    def get_crawler_delay(self, crawler_name: str) -> int:
        """Get the delay in seconds for a specific crawler from config

        The delay is ADDITIVE: main loop delay + optional crawler-specific delay

        Args:
            crawler_name: Name of the crawler (e.g., 'Immobilienscout')

        Returns:
            Total delay in seconds before this crawler should be run again
        """
        # Main loop delay is the default base delay
        base_delay = self.config.loop_period_seconds()

        # Get optional additional delay for this crawler
        crawler_delays = self.config.get('crawler_delays', {})

        # Normalize crawler name: lowercase and remove underscores
        crawler_key = crawler_name.lower().replace('_', '')

        # Additional delay is added ON TOP of base delay (0 if not specified)
        additional_delay = crawler_delays.get(crawler_key, 0)

        return base_delay + additional_delay

    def should_crawl(self, crawler_name: str) -> bool:
        """Check if enough time has passed since last crawl for this crawler

        Args:
            crawler_name: Name of the crawler

        Returns:
            True if enough time has passed, False otherwise
        """
        last_crawl = self.last_crawl_times.get(crawler_name, 0)
        delay = self.get_crawler_delay(crawler_name)
        elapsed = time.time() - last_crawl

        if elapsed < delay:
            remaining = delay - elapsed
            logger.debug(
                f"Skipping {crawler_name} - only {elapsed:.0f}s elapsed, "
                f"{remaining:.0f}s remaining until next crawl"
            )
            return False

        return True

    def mark_crawler_crawled(self, crawler_name: str):
        """Mark that a crawler has been crawled at the current time

        Args:
            crawler_name: Name of the crawler
        """
        self.last_crawl_times[crawler_name] = time.time()
        logger.debug(f"Marked {crawler_name} as crawled at {time.time()}")

    def _record_crawler_success(self, crawler_name: str, num_results: int):
        """Record a successful crawl"""
        if num_results > 0:
            message = f"Listings successfully fetched, {num_results} new result{'s' if num_results != 1 else ''}"
        else:
            message = "Listings successfully fetched, no new results"

        self.crawler_status[crawler_name] = {
            'status': 'success',
            'result_count': num_results,
            'message': message
        }

    def _record_crawler_failure(self, crawler_name: str, error: str):
        """Record a failed crawl"""
        self.crawler_status[crawler_name] = {
            'status': 'error',
            'result_count': 0,
            'message': f"Error: {error[:80]}"
        }

    def get_crawler_status_report(self) -> str:
        """Generate a concise status report for active crawlers only"""
        if not self.crawler_status:
            return ""

        lines = []
        for crawler_name, status in self.crawler_status.items():
            lines.append(f"[{crawler_name} Crawler] {status['message']}")

        return "\n".join(lines)

    def _log_crawl_summary(self):
        """Log a single-line summary of crawl results"""
        if not self.crawler_status:
            return

        parts = []
        for crawler_name, status in self.crawler_status.items():
            count = status.get('result_count', 0)
            if status['status'] == 'success':
                if count > 0:
                    parts.append(f"{crawler_name}: {count} new")
                else:
                    parts.append(f"{crawler_name}: 0")
            else:
                parts.append(f"{crawler_name}: error")

        if parts:
            logger.info(f"Crawled → {' | '.join(parts)}")

    def _send_contact_success_notification(self, expose):
        """Send a follow-up notification when a listing is successfully contacted"""
        if not self.telegram_notifier:
            logger.warning("Cannot send success notification - telegram notifier not initialized")
            return

        try:
            title = expose.get('title', 'Unknown listing')
            url = expose.get('url', '')

            success_message = (
                f"✅ ERFOLGREICH KONTAKTIERT ✅\n\n"
                f"Listing: {title}\n"
                f"URL: {url}"
            )

            self.telegram_notifier.notify(success_message)
            logger.info(f"✓ Sent success notification for: {title}")
        except Exception as e:
            logger.error(f"✗ Failed to send success notification for {title}: {e}", exc_info=True)

    def crawl_for_exposes(self, max_pages=None):
        """Trigger a new crawl of the configured URLs with per-crawler rate limiting"""
        def try_crawl(searcher, url, max_pages):
            crawler_name = searcher.get_name()

            # Skip if URL doesn't match this crawler's pattern
            if not re.search(searcher.URL_PATTERN, url):
                return []

            # Check if enough time has passed for this crawler
            if not self.should_crawl(crawler_name):
                return []

            try:
                results = searcher.crawl(url, max_pages)
                # Mark crawler as crawled after successful crawl
                self.mark_crawler_crawled(crawler_name)
                # Record success with result count
                self._record_crawler_success(crawler_name, len(results))
                return results
            except CaptchaUnsolvableError as e:
                error_msg = f"Captcha unsolvable"
                # Mark as crawled even on error to avoid hammering
                self.mark_crawler_crawled(crawler_name)
                # Record failure
                self._record_crawler_failure(crawler_name, error_msg)
                return []
            except requests.exceptions.RequestException as e:
                error_msg = f"{type(e).__name__}: {str(e)[:100]}"
                # Mark as crawled even on error to avoid hammering
                self.mark_crawler_crawled(crawler_name)
                # Record failure
                self._record_crawler_failure(crawler_name, error_msg)
                return []
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)[:100]}"
                logger.error(f"✗ {crawler_name} unexpected error: {error_msg}")
                # Mark as crawled even on error to avoid hammering
                self.mark_crawler_crawled(crawler_name)
                # Record failure
                self._record_crawler_failure(crawler_name, error_msg)
                return []

        return chain(*[try_crawl(searcher, url, max_pages)
                       for searcher in self.config.searchers()
                       for url in self.config.target_urls()])

    def hunt_flats(self, max_pages: None|int = None):
        """Crawl, process and filter exposes"""
        # Reset crawler status for this hunt cycle
        self.crawler_status = {}

        # Keep sessions active to prevent expiry
        logger.debug("Checking session validity...")
        self.willhaben_processor.keep_session_active()
        self.wg_gesucht_processor.keep_session_active()

        filter_set = Filter.builder() \
                           .read_config(self.config) \
                           .filter_already_seen(self.id_watch) \
                           .build()

        processor_chain = ProcessorChain.builder(self.config) \
                                        .save_all_exposes(self.id_watch) \
                                        .apply_filter(filter_set) \
                                        .resolve_addresses() \
                                        .calculate_durations() \
                                        .send_messages() \
                                        .build()

        result = []
        # We need to iterate over this list to force the evaluation of the pipeline
        for expose in processor_chain.process(self.crawl_for_exposes(max_pages)):
            try:
                # Contact willhaben BEFORE logging/notifying
                expose = self.willhaben_processor.process_expose(expose)
            except Exception as e:
                logger.error(f"CRITICAL: Willhaben contact processor crashed (continuing): {e}", exc_info=True)
                expose['_auto_contacted'] = False

            try:
                # Contact wg-gesucht BEFORE logging/notifying
                expose = self.wg_gesucht_processor.process_expose(expose)
            except Exception as e:
                logger.error(f"CRITICAL: WG-Gesucht contact processor crashed (continuing): {e}", exc_info=True)
                expose['_auto_contacted'] = False

            try:
                # Send success notification if listing was successfully contacted
                if expose.get('_auto_contacted'):
                    self._send_contact_success_notification(expose)
            except Exception as e:
                logger.error(f"Failed to send contact success notification (continuing): {e}", exc_info=True)

            # Log the result - simple one-liner
            try:
                contacted_marker = " ✓ Contacted" if expose.get('_auto_contacted') else ""
                logger.info(f"→ {expose['title'][:60]}{contacted_marker}")
            except Exception as e:
                logger.error(f"Failed to log expose result: {e}")

            result.append(expose)

        # Log crawler status report - consolidated single line
        try:
            self._log_crawl_summary()
        except Exception as e:
            logger.error(f"Failed to log crawler summary: {e}")

        return result