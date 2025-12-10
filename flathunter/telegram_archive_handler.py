"""Telegram archive handler - manages callback buttons and on-demand archive sending"""
import json
import time
import threading
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timedelta

import requests

from flathunter.logger_config import logger


class TelegramArchiveHandler:
    """Handles Telegram callback queries for archive buttons"""

    def __init__(self, bot_token: str, sender_telegram=None):
        """
        Initialize archive handler

        Args:
            bot_token: Telegram bot token
            sender_telegram: SenderTelegram instance for sending archives
        """
        self.bot_token = bot_token
        self.sender_telegram = sender_telegram

        # Storage file
        self.storage_file = Path.home() / '.flathunter_telegram_archives.json'

        # API endpoints
        self.get_updates_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        self.answer_callback_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"

        # Polling state
        self.polling_thread = None
        self.polling_active = False
        self.last_update_id = 0

        # Load existing archives
        self.archives = self._load_archives()

    def _load_archives(self) -> Dict:
        """Load archives from storage file"""
        try:
            if self.storage_file.exists():
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    archives = json.load(f)
                logger.info(f"Loaded {len(archives)} archives from storage")
                return archives
            return {}
        except Exception as e:
            logger.error(f"Failed to load archives: {e}", exc_info=True)
            return {}

    def _save_archives(self) -> bool:
        """Save archives to storage file"""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.archives, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save archives: {e}", exc_info=True)
            return False

    def store_archive(self, archive_data: Dict, chat_id: int) -> Optional[str]:
        """
        Store archive data for later retrieval

        Args:
            archive_data: Dict with images, description, metadata
            chat_id: Telegram chat ID

        Returns:
            archive_id if successful, None otherwise
        """
        try:
            # Generate unique archive ID (short for Telegram's 64 byte callback_data limit)
            # Format: timestamp_hash (e.g., "20251210_205720_a3f9")
            import hashlib
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            url = archive_data['metadata'].get('url', '')
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]  # First 8 chars of hash
            archive_id = f"{timestamp}_{url_hash}"

            # Store archive
            self.archives[archive_id] = {
                'archive_data': archive_data,
                'chat_id': chat_id,
                'created_at': datetime.now().isoformat()
            }

            # Save to disk
            if self._save_archives():
                logger.info(f"Stored archive: {archive_id}")
                return archive_id
            else:
                logger.error(f"Failed to save archive {archive_id} to disk")
                return None

        except Exception as e:
            logger.error(f"Failed to store archive: {e}", exc_info=True)
            return None

    def get_archive(self, archive_id: str) -> Optional[Dict]:
        """
        Retrieve archive by ID

        Args:
            archive_id: Archive identifier

        Returns:
            Archive dict or None if not found
        """
        return self.archives.get(archive_id)

    def start_polling(self):
        """Start polling for callback queries in background thread"""
        if self.polling_active:
            logger.warning("Polling already active")
            return

        self.polling_active = True
        self.polling_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.polling_thread.start()
        logger.info("Started Telegram callback polling thread")

    def stop_polling(self):
        """Stop polling thread"""
        self.polling_active = False
        if self.polling_thread:
            self.polling_thread.join(timeout=10)
        logger.info("Stopped Telegram callback polling thread")

    def _polling_loop(self):
        """Main polling loop - runs in background thread"""
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self.polling_active:
            try:
                # Get updates from Telegram
                params = {
                    'offset': self.last_update_id + 1,
                    'timeout': 5,  # Long polling timeout
                    'allowed_updates': json.dumps(['callback_query'])
                }

                response = requests.get(self.get_updates_url, params=params, timeout=10)

                if response.status_code == 200:
                    consecutive_errors = 0  # Reset error counter

                    data = response.json()
                    if data.get('ok') and data.get('result'):
                        for update in data['result']:
                            self.last_update_id = max(self.last_update_id, update['update_id'])

                            # Handle callback query
                            if 'callback_query' in update:
                                self._handle_callback_query(update['callback_query'])

                else:
                    consecutive_errors += 1
                    logger.warning(f"getUpdates failed with status {response.status_code}")

            except requests.exceptions.Timeout:
                # Timeout is normal with long polling, just continue
                pass
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in polling loop: {e}", exc_info=True)

            # If too many consecutive errors, back off
            if consecutive_errors >= max_consecutive_errors:
                logger.error(f"Too many consecutive errors ({consecutive_errors}), backing off for 30s")
                time.sleep(30)
                consecutive_errors = 0

            # Small delay between polls (unless long polling timed out)
            time.sleep(0.1)

    def _handle_callback_query(self, callback_query: Dict):
        """
        Handle a callback query from a button click

        Args:
            callback_query: Telegram callback_query object
        """
        try:
            callback_id = callback_query['id']
            callback_data = callback_query.get('data', '')
            message = callback_query.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            message_id = message.get('message_id')

            logger.info(f"Received callback: {callback_data} from chat {chat_id}")

            # Parse callback data (format: "archive:<archive_id>")
            if not callback_data.startswith('archive:'):
                logger.warning(f"Unknown callback data format: {callback_data}")
                self._answer_callback(callback_id, "⚠️ Ungültiger Befehl")
                return

            archive_id = callback_data.replace('archive:', '')

            # Retrieve archive
            archive = self.get_archive(archive_id)
            if not archive:
                logger.warning(f"Archive not found: {archive_id}")
                self._answer_callback(callback_id, "⚠️ Archiv nicht gefunden")
                return

            # Verify chat_id matches (security check)
            if archive['chat_id'] != chat_id:
                logger.warning(f"Chat ID mismatch for archive {archive_id}: {chat_id} != {archive['chat_id']}")
                self._answer_callback(callback_id, "⚠️ Zugriff verweigert")
                return

            # Answer callback first (removes loading state)
            self._answer_callback(callback_id, "📦 Archiv wird geladen...")

            # Send archive as reply
            self._send_archive_reply(
                chat_id=chat_id,
                reply_to_message_id=message_id,
                archive_data=archive['archive_data']
            )

        except Exception as e:
            logger.error(f"Error handling callback query: {e}", exc_info=True)
            try:
                callback_id = callback_query.get('id')
                if callback_id:
                    self._answer_callback(callback_id, "⚠️ Fehler beim Laden")
            except:
                pass

    def _answer_callback(self, callback_id: str, text: str = ""):
        """
        Answer a callback query to remove loading state

        Args:
            callback_id: Callback query ID
            text: Optional text to show as notification
        """
        try:
            payload = {
                'callback_query_id': callback_id,
                'text': text
            }
            response = requests.post(self.answer_callback_url, data=payload, timeout=10)

            if response.status_code != 200:
                logger.warning(f"Failed to answer callback: {response.status_code}")

        except Exception as e:
            logger.error(f"Error answering callback: {e}")

    def _send_archive_reply(self, chat_id: int, reply_to_message_id: int, archive_data: Dict):
        """
        Send archive (images + description) as reply to the original message

        Args:
            chat_id: Telegram chat ID
            reply_to_message_id: Message ID to reply to
            archive_data: Archive data with images and description
        """
        try:
            if not self.sender_telegram:
                logger.error("Cannot send archive - sender_telegram not set")
                return

            images = archive_data.get('images', [])
            description = archive_data.get('description', '')
            metadata = archive_data.get('metadata', {})

            # Build message text
            message_parts = []

            # Add metadata header
            message_parts.append("📦 Listing Archiv")
            message_parts.append("")

            # Add description
            if description:
                # Truncate if too long (Telegram has 4096 char limit for captions)
                max_desc_len = 3000
                if len(description) > max_desc_len:
                    description = description[:max_desc_len] + "... (gekürzt)"

                message_parts.append("📝 Beschreibung:")
                message_parts.append(description)
            else:
                message_parts.append("📝 Keine Beschreibung verfügbar")

            message_text = "\n".join(message_parts)

            # Send images and description
            if images:
                self.sender_telegram.send_archive_reply(
                    chat_id=chat_id,
                    reply_to_message_id=reply_to_message_id,
                    images=images,
                    description_text=message_text
                )
                logger.info(f"Sent archive with {len(images)} images to chat {chat_id}")
            else:
                # No images, just send description as text
                self.sender_telegram.send_text_reply(
                    chat_id=chat_id,
                    reply_to_message_id=reply_to_message_id,
                    text=message_text
                )
                logger.info(f"Sent archive (no images) to chat {chat_id}")

        except Exception as e:
            logger.error(f"Error sending archive reply: {e}", exc_info=True)

    def cleanup_old_archives(self, retention_days: int = 30) -> int:
        """
        Remove archives older than retention_days

        Args:
            retention_days: Number of days to keep archives

        Returns:
            Number of archives deleted
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            deleted_count = 0

            archives_to_delete = []

            for archive_id, archive in self.archives.items():
                created_at_str = archive.get('created_at')
                if not created_at_str:
                    continue

                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    if created_at < cutoff_date:
                        archives_to_delete.append(archive_id)
                except:
                    pass

            # Delete old archives
            for archive_id in archives_to_delete:
                del self.archives[archive_id]
                deleted_count += 1

            if deleted_count > 0:
                self._save_archives()
                logger.info(f"Cleaned up {deleted_count} old archives")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old archives: {e}", exc_info=True)
            return 0
