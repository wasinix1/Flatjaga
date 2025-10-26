"""Default Flathunter implementation for the command line"""
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

        # Health monitoring: track crawler statistics
        self.crawler_health = {}  # {crawler_name: {attempts, successes, failures, last_success_time, last_error, results_found}}

        # Initialize telegram notifier for success/failure notifications
        self.telegram_notifier = None
        if 'telegram' in self.config.notifiers():
            self.telegram_notifier = SenderTelegram(self.config)

        # Initialize willhaben processor with telegram notifier and id_watch
        self.willhaben_processor = WillhabenContactProcessor(config, self.telegram_notifier, id_watch)

        # Initialize wg-gesucht processor with telegram notifier and id_watch
        self.wg_gesucht_processor = WgGesuchtContactProcessor(config, self.telegram_notifier, id_watch)


    def get_crawler_delay(self, crawler_name: str) -> int:
        """Get the delay in seconds for a specific crawler from config

        Args:
            crawler_name: Name of the crawler (e.g., 'Immobilienscout')

        Returns:
            Delay in seconds before this crawler should be run again
        """
        delays = self.config.get('crawler_delays', {})
        default_delay = delays.get('default', 60)

        # Normalize crawler name: lowercase and remove underscores
        crawler_key = crawler_name.lower().replace('_', '')

        return delays.get(crawler_key, default_delay)

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

    def _init_crawler_health(self, crawler_name: str):
        """Initialize health tracking for a crawler if not already done"""
        if crawler_name not in self.crawler_health:
            self.crawler_health[crawler_name] = {
                'attempts': 0,
                'successes': 0,
                'failures': 0,
                'last_success_time': None,
                'last_error': None,
                'results_found': 0
            }

    def _record_crawler_success(self, crawler_name: str, num_results: int):
        """Record a successful crawl"""
        self._init_crawler_health(crawler_name)
        self.crawler_health[crawler_name]['attempts'] += 1
        self.crawler_health[crawler_name]['successes'] += 1
        self.crawler_health[crawler_name]['last_success_time'] = time.time()
        self.crawler_health[crawler_name]['results_found'] += num_results

    def _record_crawler_failure(self, crawler_name: str, error: str):
        """Record a failed crawl"""
        self._init_crawler_health(crawler_name)
        self.crawler_health[crawler_name]['attempts'] += 1
        self.crawler_health[crawler_name]['failures'] += 1
        self.crawler_health[crawler_name]['last_error'] = error

    def get_health_report(self) -> str:
        """Generate a health report for all crawlers"""
        if not self.crawler_health:
            return "No crawler activity yet"

        lines = ["", "=" * 60, "CRAWLER HEALTH REPORT", "=" * 60]
        for crawler_name, stats in self.crawler_health.items():
            success_rate = (stats['successes'] / stats['attempts'] * 100) if stats['attempts'] > 0 else 0
            lines.append(f"\n{crawler_name}:")
            lines.append(f"  Attempts: {stats['attempts']} | Successes: {stats['successes']} | Failures: {stats['failures']}")
            lines.append(f"  Success Rate: {success_rate:.1f}%")
            lines.append(f"  Results Found: {stats['results_found']}")

            if stats['last_success_time']:
                elapsed = time.time() - stats['last_success_time']
                if elapsed < 3600:
                    time_ago = f"{elapsed/60:.0f}m ago"
                elif elapsed < 86400:
                    time_ago = f"{elapsed/3600:.1f}h ago"
                else:
                    time_ago = f"{elapsed/86400:.1f}d ago"
                lines.append(f"  Last Success: {time_ago}")
            else:
                lines.append(f"  Last Success: Never")

            if stats['last_error']:
                lines.append(f"  Last Error: {stats['last_error'][:80]}")

        lines.append("=" * 60)
        return "\n".join(lines)

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

            # Check if enough time has passed for this crawler
            if not self.should_crawl(crawler_name):
                return []

            try:
                logger.info(f"Crawling {crawler_name}: {url}")
                results = searcher.crawl(url, max_pages)
                # Mark crawler as crawled after successful crawl
                self.mark_crawler_crawled(crawler_name)
                # Record success with result count
                self._record_crawler_success(crawler_name, len(results))
                logger.info(f"✓ {crawler_name} crawled successfully - found {len(results)} results")
                return results
            except CaptchaUnsolvableError as e:
                error_msg = f"Captcha unsolvable"
                logger.warning(f"✗ {crawler_name} failed: {error_msg}")
                # Mark as crawled even on error to avoid hammering
                self.mark_crawler_crawled(crawler_name)
                # Record failure
                self._record_crawler_failure(crawler_name, error_msg)
                return []
            except requests.exceptions.RequestException as e:
                error_msg = f"{type(e).__name__}: {str(e)[:100]}"
                logger.warning(f"✗ {crawler_name} failed: {error_msg}")
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
            # Contact willhaben BEFORE logging/notifying
            expose = self.willhaben_processor.process_expose(expose)

            # Contact wg-gesucht BEFORE logging/notifying
            expose = self.wg_gesucht_processor.process_expose(expose)

            # Send success notification if listing was successfully contacted
            if expose.get('_auto_contacted'):
                self._send_contact_success_notification(expose)

            # Log the result
            contacted_marker = "✅ [CONTACTED]" if expose.get('_auto_contacted') else ""
            logger.info('New offer: %s %s', expose['title'], contacted_marker)

            result.append(expose)

        # Log health report to show crawler status
        logger.info(self.get_health_report())

        return result