"""SQLite implementation of IDMaintainer interface"""
import threading
import sqlite3 as lite
import datetime
import json
import re

from flathunter.logging import logger
from flathunter.abstract_processor import Processor

__author__ = "Nody"
__version__ = "0.1"
__maintainer__ = "Nody"
__email__ = "harrymcfly@protonmail.com"
__status__ = "Prodction"

class SaveAllExposesProcessor(Processor):
    """Processor that saves all exposes to the database"""

    def __init__(self, config, id_watch):
        self.config = config
        self.id_watch = id_watch

    def process_expose(self, expose):
        """Save a single expose"""
        self.id_watch.save_expose(expose)
        return expose

class IdMaintainer:
    """SQLite back-end for the database"""

    def __init__(self, db_name):
        self.db_name = db_name
        self.threadlocal = threading.local()

    def get_connection(self):
        """Connects to the SQLite database. Connections are thread-local"""
        connection = getattr(self.threadlocal, 'connection', None)
        if connection is None:
            try:
                self.threadlocal.connection = lite.connect(self.db_name)
                connection = self.threadlocal.connection
                cur = self.threadlocal.connection.cursor()
                cur.execute('CREATE TABLE IF NOT EXISTS processed (ID INTEGER)')
                cur.execute('CREATE TABLE IF NOT EXISTS executions (timestamp timestamp)')
                cur.execute('CREATE TABLE IF NOT EXISTS exposes (id INTEGER, created TIMESTAMP, \
                                    crawler STRING, details BLOB, PRIMARY KEY (id, crawler))')
                cur.execute('CREATE TABLE IF NOT EXISTS users \
                                    (id INTEGER PRIMARY KEY, settings BLOB)')
                cur.execute('CREATE TABLE IF NOT EXISTS contacted_titles \
                                    (normalized_title TEXT PRIMARY KEY, original_title TEXT, \
                                    listing_id INTEGER, crawler TEXT, contacted_at TIMESTAMP, listing_url TEXT)')
                self.threadlocal.connection.commit()
            except lite.Error as error:
                logger.error("Error %s:", error.args[0])
                raise error
        return connection

    def is_processed(self, expose_id):
        """Returns true if an expose has already been processed"""
        logger.debug('is_processed(%d)', expose_id)
        cur = self.get_connection().cursor()
        cur.execute('SELECT id FROM processed WHERE id = ?', (expose_id,))
        row = cur.fetchone()
        return row is not None

    def mark_processed(self, expose_id):
        """Mark an expose as processed in the database"""
        logger.debug('mark_processed(%d)', expose_id)
        cur = self.get_connection().cursor()
        cur.execute('INSERT INTO processed VALUES(?)', (expose_id,))
        self.get_connection().commit()

    @staticmethod
    def normalize_title(title):
        """
        Normalize a listing title for cross-reference matching.
        Conservative approach: only removes formatting noise, keeps all distinctive content.
        """
        if not title:
            return ""

        # Convert to lowercase for case-insensitive matching
        normalized = title.lower()

        # Normalize whitespace characters (tabs, newlines, multiple spaces)
        normalized = re.sub(r'\s+', ' ', normalized)

        # Normalize common unicode variations
        replacements = {
            'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss',
            'é': 'e', 'è': 'e', 'ê': 'e',
            'à': 'a', 'á': 'a', 'â': 'a',
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        # Remove common punctuation but keep numbers and letters
        normalized = re.sub(r'[^\w\s]', ' ', normalized)

        # Collapse multiple spaces again after punctuation removal
        normalized = re.sub(r'\s+', ' ', normalized)

        # Trim whitespace
        normalized = normalized.strip()

        return normalized

    def is_title_contacted(self, title):
        """
        Check if a listing with this title has already been contacted.
        Returns True if title was contacted before, False otherwise.
        """
        if not title:
            return False

        normalized = self.normalize_title(title)
        if not normalized:
            return False

        logger.debug('is_title_contacted: checking "%s" (normalized: "%s")', title, normalized)
        cur = self.get_connection().cursor()
        cur.execute('SELECT normalized_title FROM contacted_titles WHERE normalized_title = ?',
                   (normalized,))
        row = cur.fetchone()

        if row is not None:
            logger.info('Title already contacted: "%s"', title)
            return True

        return False

    def mark_title_contacted(self, expose):
        """
        Mark a listing title as contacted in the database.
        Stores normalized title to prevent duplicate contacts across platforms.
        """
        title = expose.get('title', '')
        if not title:
            logger.warning('Cannot mark title as contacted: no title in expose')
            return False

        normalized = self.normalize_title(title)
        if not normalized:
            logger.warning('Cannot mark title as contacted: normalized title is empty')
            return False

        logger.debug('mark_title_contacted: "%s" (normalized: "%s")', title, normalized)

        cur = self.get_connection().cursor()
        try:
            cur.execute(
                'INSERT OR REPLACE INTO contacted_titles \
                 (normalized_title, original_title, listing_id, crawler, contacted_at, listing_url) \
                 VALUES (?, ?, ?, ?, ?, ?)',
                (normalized, title, expose.get('id'), expose.get('crawler'),
                 datetime.datetime.now(), expose.get('url', ''))
            )
            self.get_connection().commit()
            logger.info('Marked title as contacted: "%s"', title)
            return True
        except lite.Error as error:
            logger.error('Error marking title as contacted: %s', error.args[0])
            return False

    def save_expose(self, expose):
        """Saves an expose to a database"""
        cur = self.get_connection().cursor()
        cur.execute('INSERT OR REPLACE INTO exposes(id, created, crawler, details) \
                     VALUES (?, ?, ?, ?)',
                    (int(expose['id']), datetime.datetime.now(),
                     expose['crawler'], json.dumps(expose)))
        self.get_connection().commit()

    def get_exposes_since(self, min_datetime):
        """Loads all exposes since the specified date"""
        def row_to_expose(row):
            obj = json.loads(row[2])
            obj['created_at'] = row[0]
            return obj
        cur = self.get_connection().cursor()
        cur.execute('SELECT created, crawler, details FROM exposes \
                     WHERE created >= ? ORDER BY created DESC', (min_datetime,))
        return list(map(row_to_expose, cur.fetchall()))

    def get_recent_exposes(self, count, filter_set=None):
        """Returns up to 'count' recent exposes, filtered by the provided filter"""
        cur = self.get_connection().cursor()
        cur.execute('SELECT details FROM exposes ORDER BY created DESC')
        res = []
        next_batch = []
        while len(res) < count:
            if len(next_batch) == 0:
                next_batch = cur.fetchmany()
                if len(next_batch) == 0:
                    break
            expose = json.loads(next_batch.pop()[0])
            if filter_set is None or filter_set.is_interesting_expose(expose):
                res.append(expose)
        return res

    def save_settings_for_user(self, user_id, settings):
        """Saves the user settings to the database"""
        cur = self.get_connection().cursor()
        cur.execute('INSERT OR REPLACE INTO users VALUES (?, ?)', (user_id, json.dumps(settings)))
        self.get_connection().commit()

    def get_settings_for_user(self, user_id):
        """Loads the settings for a user from the database"""
        cur = self.get_connection().cursor()
        cur.execute('SELECT settings FROM users WHERE id = ?', (user_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def get_user_settings(self):
        """Loads all users' settings from the database"""
        cur = self.get_connection().cursor()
        cur.execute('SELECT id, settings FROM users')
        res = []
        for row in cur.fetchall():
            res.append((row[0], json.loads(row[1])))
        return res

    def get_last_run_time(self):
        """Returns the time of the last hunt"""
        cur = self.get_connection().cursor()
        cur.execute("SELECT * FROM executions ORDER BY timestamp DESC LIMIT 1")
        row = cur.fetchone()
        if row is None:
            return None
        return datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S.%f')

    def update_last_run_time(self):
        """Saves the time of the most recent hunt to the database"""
        cur = self.get_connection().cursor()
        result = datetime.datetime.now()
        cur.execute('INSERT INTO executions VALUES(?);', (result,))
        self.get_connection().commit()
        return result
