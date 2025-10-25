#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Flathunter - search for flats by crawling property portals, and receive telegram
   messages about them. This is the main command-line executable, for running on the
   console. To run as a webservice, look at main.py"""

import time
from datetime import time as dtime
from pathlib import Path
import json

from flathunter.argument_parser import parse
from flathunter.logging import logger, configure_logging
from flathunter.idmaintainer import IdMaintainer
from flathunter.hunter import Hunter
from flathunter.config import Config
from flathunter.heartbeat import Heartbeat
from flathunter.time_utils import get_random_time_jitter, wait_during_period

__author__ = "Jan Harrie"
__version__ = "1.0"
__maintainer__ = "Nody"
__email__ = "harrymcfly@protonmail.com"
__status__ = "Production"


def check_saved_sessions():
    """Check for saved sessions and prompt user for confirmation"""
    sessions_found = []

    # Check for willhaben session
    willhaben_cookies = Path.home() / '.willhaben_cookies.json'
    if willhaben_cookies.exists():
        try:
            with open(willhaben_cookies, 'r') as f:
                cookies = json.load(f)
                # Try to extract username or email if available in cookies
                user_info = "saved session"
                for cookie in cookies:
                    if cookie.get('name') in ['username', 'email', 'user']:
                        user_info = cookie.get('value', user_info)
                        break
                sessions_found.append(('willhaben', willhaben_cookies, user_info))
        except:
            # If we can't read the file, just show that it exists
            sessions_found.append(('willhaben', willhaben_cookies, 'saved session'))

    # If no sessions found, just continue
    if not sessions_found:
        return

    # Show saved sessions and prompt
    print("\n" + "="*60)
    print("SAVED SESSIONS FOUND")
    print("="*60)
    for service, path, info in sessions_found:
        print(f"  • {service.upper()}: {info}")
    print("="*60)
    print("\nPress ENTER to use saved session(s), or 'x' to switch account: ", end='', flush=True)

    response = input().strip().lower()

    if response == 'x':
        print("\nClearing saved sessions...")
        for service, path, _ in sessions_found:
            try:
                path.unlink()
                print(f"  ✓ Cleared {service} session")
            except Exception as e:
                logger.error(f"Failed to clear {service} session: {e}")
        print("\nYou can now login with a different account.")
        print("Run 'python willhaben_contact_bot.py' to setup a new session.\n")
        return
    else:
        print("Using saved session(s)...\n")


def launch_flat_hunt(config, heartbeat: Heartbeat):
    """Starts the crawler / notification loop"""
    id_watch = IdMaintainer(f'{config.database_location()}/processed_ids.db')

    time_from = dtime.fromisoformat(config.loop_pause_from())
    time_till = dtime.fromisoformat(config.loop_pause_till())

    wait_during_period(time_from, time_till)

    hunter = Hunter(config, id_watch)
    hunter.hunt_flats()
    counter = 0

    while config.loop_is_active():
        wait_during_period(time_from, time_till)

        counter += 1
        counter = heartbeat.send_heartbeat(counter)
        if config.random_jitter_enabled():
            sleep_period = get_random_time_jitter(config.loop_period_seconds())
        else:
            sleep_period = config.loop_period_seconds()
        time.sleep(sleep_period)
        hunter.hunt_flats()


def main():
    """Processes command-line arguments, loads the config, launches the flathunter"""
    # load config
    args = parse()
    config_handle = args.config
    if config_handle is not None:
        config = Config(config_handle.name)
    else:
        config = Config()

    # setup logging
    configure_logging(config)

    # initialize search plugins for config
    config.init_searchers()

    # check config
    notifiers = config.notifiers()
    if 'mattermost' in notifiers \
            and not config.mattermost_webhook_url():
        logger.error("No Mattermost webhook configured. Starting like this would be pointless...")
        return
    if 'telegram' in notifiers:
        if not config.telegram_bot_token():
            logger.error(
                "No Telegram bot token configured. Starting like this would be pointless..."
            )
            return
        if len(config.telegram_receiver_ids()) == 0:
            logger.warning("No Telegram receivers configured - nobody will get notifications.")
    if 'apprise' in notifiers \
            and not config.get('apprise', {}):
        logger.error("No apprise url configured. Starting like this would be pointless...")
        return
    if 'slack' in notifiers \
            and not config.slack_webhook_url():
        logger.error("No Slack webhook url configured. Starting like this would be pointless...")
        return

    if len(config.target_urls()) == 0:
        logger.error("No URLs configured. Starting like this would be pointless...")
        return

    # check for saved sessions and prompt user
    check_saved_sessions()

    # get heartbeat instructions
    heartbeat_interval = args.heartbeat
    heartbeat = Heartbeat(config, heartbeat_interval)

    # start hunting for flats
    launch_flat_hunt(config, heartbeat)


if __name__ == "__main__":
    main()
