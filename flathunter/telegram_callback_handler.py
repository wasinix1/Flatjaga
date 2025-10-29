#!/usr/bin/env python3
"""
Telegram Callback Handler for Listing Descriptions
Listens for inline button presses and returns listing descriptions from database
"""

import time
import json
import logging
import requests
from pathlib import Path

from flathunter.config import YamlConfig
from flathunter.idmaintainer import IdMaintainer

logger = logging.getLogger(__name__)


class TelegramCallbackHandler:
    """Handles Telegram inline button callbacks for listing descriptions"""

    def __init__(self, config_path=None):
        """
        Initialize the callback handler

        Args:
            config_path: Path to config.yaml (defaults to ./config.yaml)
        """
        # Load config
        if config_path is None:
            config_path = Path.cwd() / "config.yaml"

        self.config = YamlConfig(str(config_path))
        self.bot_token = self.config.telegram_bot_token()

        # Database
        db_location = self.config.database_location()
        db_name = Path(db_location) / "processed_ids.db"
        self.id_maintainer = IdMaintainer(str(db_name))

        # API URLs
        self.get_updates_url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        self.send_message_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.answer_callback_url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"

        # Track last update ID to avoid processing same callback twice
        self.last_update_id = None

        logger.info("Telegram callback handler initialized")

    def get_updates(self, timeout=30):
        """
        Poll Telegram API for updates (including callback queries)

        Args:
            timeout: Long polling timeout in seconds

        Returns:
            list: List of updates, or empty list on error
        """
        try:
            params = {
                'timeout': timeout,
                'allowed_updates': ['callback_query']  # Only get button presses
            }

            if self.last_update_id is not None:
                params['offset'] = self.last_update_id + 1

            response = requests.get(self.get_updates_url, params=params, timeout=timeout + 5)

            if response.status_code != 200:
                logger.error(f"Error getting updates: {response.status_code} - {response.text}")
                return []

            data = response.json()

            if not data.get('ok'):
                logger.error(f"Telegram API error: {data}")
                return []

            return data.get('result', [])

        except requests.exceptions.Timeout:
            # Timeout is expected with long polling
            return []
        except Exception as e:
            logger.error(f"Error polling updates: {e}")
            return []

    def answer_callback_query(self, callback_query_id, text=None):
        """
        Answer a callback query (removes loading animation on button)

        Args:
            callback_query_id: The callback query ID
            text: Optional text to show in a toast notification
        """
        try:
            params = {'callback_query_id': callback_query_id}
            if text:
                params['text'] = text

            requests.post(self.answer_callback_url, params=params, timeout=5)
        except Exception as e:
            logger.warning(f"Error answering callback query: {e}")

    def send_message(self, chat_id, text, reply_to_message_id=None):
        """
        Send a text message to a chat

        Args:
            chat_id: The chat/user ID
            text: The message text
            reply_to_message_id: Optional message ID to reply to
        """
        try:
            payload = {
                'chat_id': str(chat_id),
                'text': text,
                'parse_mode': 'HTML'  # Enable HTML formatting
            }

            if reply_to_message_id:
                payload['reply_to_message_id'] = reply_to_message_id

            response = requests.post(self.send_message_url, json=payload, timeout=10)

            if response.status_code != 200:
                logger.error(f"Error sending message: {response.status_code} - {response.text}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    def parse_callback_data(self, callback_data):
        """
        Parse callback data to extract listing info

        Format: "desc_<listing_id>_<crawler>"
        Example: "desc_12345_Willhaben"

        Args:
            callback_data: The callback data string

        Returns:
            tuple: (listing_id, crawler) or (None, None) if invalid
        """
        try:
            parts = callback_data.split('_', 2)  # Split into max 3 parts

            if len(parts) < 3 or parts[0] != 'desc':
                logger.warning(f"Invalid callback data format: {callback_data}")
                return None, None

            listing_id = int(parts[1])
            crawler = parts[2]

            return listing_id, crawler

        except (ValueError, IndexError) as e:
            logger.warning(f"Error parsing callback data '{callback_data}': {e}")
            return None, None

    def format_description_message(self, expose):
        """
        Format the description as a nice message

        Args:
            expose: The expose dictionary

        Returns:
            str: Formatted message
        """
        title = expose.get('title', 'Unknown')
        description = expose.get('description', '')
        url = expose.get('url', '')
        listing_id = expose.get('id', 'N/A')

        if description:
            # Truncate if too long (Telegram has 4096 char limit)
            max_desc_length = 3500  # Leave room for header/footer
            if len(description) > max_desc_length:
                description = description[:max_desc_length] + "\n\n[... beschreibung gekürzt ...]"

            message = f"📄 <b>Beschreibung:</b> {title}\n\n"
            message += f"{description}\n\n"
            message += f"🔗 <a href='{url}'>Zum Inserat</a>\n"
            message += f"<i>Listing #{listing_id}</i>"
        else:
            message = f"ℹ️ <b>{title}</b>\n\n"
            message += "Keine Beschreibung verfügbar.\n\n"
            message += "Die Beschreibung wird nur für kontaktierte Inserate gespeichert.\n\n"
            message += f"<i>Listing #{listing_id}</i>"

        return message

    def handle_callback_query(self, callback_query):
        """
        Handle a single callback query (button press)

        Args:
            callback_query: The callback query object from Telegram
        """
        try:
            callback_id = callback_query.get('id')
            callback_data = callback_query.get('data')
            message = callback_query.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            message_id = message.get('message_id')

            logger.info(f"Received callback: {callback_data} from chat {chat_id}")

            # Parse callback data
            listing_id, crawler = self.parse_callback_data(callback_data)

            if listing_id is None:
                self.answer_callback_query(callback_id, "❌ Ungültiger Button")
                self.send_message(chat_id, "❌ Fehler: Ungültige Button-Daten")
                return

            # Answer callback query immediately (removes loading animation)
            self.answer_callback_query(callback_id, "🔍 Lade Beschreibung...")

            # Get expose from database
            expose = self.id_maintainer.get_expose_by_id(listing_id, crawler)

            if expose is None:
                logger.warning(f"Expose {listing_id} ({crawler}) not found in database")
                self.send_message(
                    chat_id,
                    f"❌ Inserat #{listing_id} nicht in der Datenbank gefunden.",
                    reply_to_message_id=message_id
                )
                return

            # Format and send description
            description_msg = self.format_description_message(expose)
            self.send_message(chat_id, description_msg, reply_to_message_id=message_id)

            logger.info(f"✓ Sent description for listing {listing_id} to chat {chat_id}")

        except Exception as e:
            logger.error(f"Error handling callback query: {e}", exc_info=True)
            try:
                self.send_message(chat_id, f"❌ Fehler beim Laden der Beschreibung: {str(e)[:100]}")
            except:
                pass

    def run(self, poll_interval=1):
        """
        Main loop - continuously poll for callbacks

        Args:
            poll_interval: Seconds to wait between polls (for long polling, this is mostly ignored)
        """
        logger.info("Starting callback handler loop...")
        logger.info("Press Ctrl+C to stop")

        consecutive_errors = 0
        max_consecutive_errors = 10

        try:
            while True:
                try:
                    # Get updates (long polling with 30s timeout)
                    updates = self.get_updates(timeout=30)

                    # Reset error counter on successful poll
                    if consecutive_errors > 0:
                        logger.info("Connection restored")
                        consecutive_errors = 0

                    # Process each update
                    for update in updates:
                        # Update last_update_id to mark this update as processed
                        update_id = update.get('update_id')
                        if update_id:
                            self.last_update_id = update_id

                        # Handle callback query if present
                        callback_query = update.get('callback_query')
                        if callback_query:
                            self.handle_callback_query(callback_query)

                    # Small delay between polls (only when not using long polling)
                    if not updates:
                        time.sleep(poll_interval)

                except KeyboardInterrupt:
                    raise  # Re-raise to exit cleanly

                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"Error in main loop ({consecutive_errors}/{max_consecutive_errors}): {e}")

                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"Too many consecutive errors ({consecutive_errors}), exiting...")
                        break

                    # Exponential backoff
                    backoff_time = min(2 ** consecutive_errors, 60)
                    logger.info(f"Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")

        logger.info("Callback handler stopped")


def main():
    """Main entry point"""
    import sys

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(Path.home() / '.telegram_callback_handler.log')
        ]
    )

    # Get config path from args or use default
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    # Create and run handler
    handler = TelegramCallbackHandler(config_path)
    handler.run()


if __name__ == "__main__":
    main()
