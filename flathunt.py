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
from flathunter.logger_config import logger, configure_logging
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


def get_session_info():
    """Get information about saved sessions"""
    sessions = {}

    # Check for willhaben session
    willhaben_cookies = Path.home() / '.willhaben_cookies.json'
    if willhaben_cookies.exists():
        sessions['willhaben'] = {'path': willhaben_cookies, 'name': 'Willhaben'}

    # Check for wg-gesucht session
    wggesucht_cookies = Path.home() / '.wg_gesucht_cookies.json'
    if wggesucht_cookies.exists():
        sessions['wg-gesucht'] = {'path': wggesucht_cookies, 'name': 'WG-Gesucht'}

    return sessions


def clear_session(service_key):
    """Clear a specific session"""
    sessions = get_session_info()
    if service_key not in sessions:
        print(f"  ✗ No {sessions.get(service_key, {}).get('name', service_key)} session found")
        return False

    try:
        sessions[service_key]['path'].unlink()
        print(f"  ✓ Cleared {sessions[service_key]['name']} session")
        return True
    except Exception as e:
        logger.error(f"Failed to clear {sessions[service_key]['name']} session: {e}")
        return False


def setup_session(service_key):
    """Setup a specific session interactively"""
    if service_key == 'willhaben':
        print("\n" + "="*60)
        print("WILLHABEN SESSION SETUP")
        print("="*60)
        try:
            from flathunter.willhaben_contact_bot import WillhabenContactBot
            bot = WillhabenContactBot(headless=False, use_stealth=False)
            bot.start()

            # Check if session already exists
            if bot.load_cookies():
                print("\n✓ Existing Willhaben session loaded successfully!")
                print("\nTesting session...")
                bot.driver.get('https://www.willhaben.at')
                print("✓ Session appears to be valid\n")

                response = input("Session exists. Re-login anyway? (y/N): ").strip().lower()
                if response != 'y':
                    print("Keeping existing session.")
                    bot.close()
                    return True

            # Do manual login
            bot.login_manual()
            print("\n✓ Willhaben session saved!")
            bot.close()
            return True

        except Exception as e:
            print(f"\n✗ Error setting up Willhaben session: {e}")
            return False

    elif service_key == 'wg-gesucht':
        print("\n" + "="*60)
        print("WG-GESUCHT SESSION SETUP")
        print("="*60)
        try:
            from flathunter.wg_gesucht_contact_bot import WgGesuchtContactBot

            # Check if session already exists
            cookie_file = Path.home() / '.wg_gesucht_cookies.json'
            if cookie_file.exists():
                print("\n✓ Existing WG-Gesucht session found!")
                response = input("Session exists. Re-login anyway? (y/N): ").strip().lower()
                if response != 'y':
                    print("Keeping existing session.")
                    return True

                # Delete old session to force re-login
                cookie_file.unlink()
                print("Old session deleted. Proceeding with new login...\n")

            # Initialize in non-headless mode for manual login
            bot = WgGesuchtContactBot(headless=False, stealth_mode=False)
            bot.start()

            # Explicitly call manual login
            bot._login_manual()
            print("\n✓ WG-Gesucht session saved!")
            bot.close()
            return True

        except Exception as e:
            print(f"\n✗ Error setting up WG-Gesucht session: {e}")
            import traceback
            traceback.print_exc()
            return False

    return False


def session_manager_menu():
    """Interactive session management menu"""
    while True:
        sessions = get_session_info()

        print("\n" + "="*60)
        print("SESSION MANAGER")
        print("="*60)

        if sessions:
            print("\nCurrent sessions:")
            if 'willhaben' in sessions:
                print("  ✓ Willhaben")
            if 'wg-gesucht' in sessions:
                print("  ✓ WG-Gesucht")
        else:
            print("\n  No sessions found")

        print("\n" + "="*60)
        print("Options:")
        print("  [1]  Setup Willhaben session")
        print("  [2]  Setup WG-Gesucht session")
        print("  [3]  Setup both sessions")
        print("  [4]  Clear Willhaben session")
        print("  [5]  Clear WG-Gesucht session")
        print("  [6]  Clear all sessions")
        print("  [c]  Continue with current sessions")
        print("  [q]  Quit")
        print("="*60)

        choice = input("\nEnter your choice: ").strip().lower()

        if choice == 'q':
            print("\nExiting...")
            import sys
            sys.exit(0)
        elif choice == 'c':
            print("\nContinuing with current sessions...\n")
            return
        elif choice == '1':
            setup_session('willhaben')
        elif choice == '2':
            setup_session('wg-gesucht')
        elif choice == '3':
            setup_session('willhaben')
            setup_session('wg-gesucht')
        elif choice == '4':
            clear_session('willhaben')
        elif choice == '5':
            clear_session('wg-gesucht')
        elif choice == '6':
            clear_session('willhaben')
            clear_session('wg-gesucht')
        else:
            print("\n✗ Invalid choice. Please try again.")


def check_saved_sessions():
    """Check for saved sessions and provide interactive options"""
    sessions = get_session_info()

    # If no sessions found, offer to set them up
    if not sessions:
        print("\n" + "="*60)
        print("NO SESSIONS FOUND")
        print("="*60)
        print("\nYou need to setup sessions for auto-contact to work.")
        response = input("\nSetup sessions now? (Y/n): ").strip().lower()

        if response != 'n':
            session_manager_menu()
        else:
            print("\nContinuing without sessions (auto-contact disabled)...\n")
        return

    # Show saved sessions and prompt
    print("\n" + "="*60)
    print("SAVED SESSIONS FOUND")
    print("="*60)
    for key, info in sessions.items():
        print(f"  ✓ {info['name']}")
    print("="*60)
    print("\nOptions:")
    print("  [ENTER]  Use saved sessions and continue")
    print("  [x]      Clear/manage sessions")
    print("  [s]      Setup/refresh sessions")
    print("  [q]      Quit")
    print("="*60)

    response = input("\nChoice: ").strip().lower()

    if response == 'q':
        print("\nExiting...")
        import sys
        sys.exit(0)
    elif response == 'x' or response == 's':
        session_manager_menu()
    else:
        print("\nUsing saved sessions...\n")


def launch_flat_hunt(config, heartbeat: Heartbeat):
    """Starts the crawler / notification loop"""
    id_watch = IdMaintainer(f'{config.database_location()}/processed_ids.db')

    time_from = dtime.fromisoformat(config.loop_pause_from())
    time_till = dtime.fromisoformat(config.loop_pause_till())

    wait_during_period(time_from, time_till)

    hunter = Hunter(config, id_watch)

    # Check for disabled processors from previous run
    disabled = hunter.session_manager.get_disabled_processors()
    if disabled:
        print("\n" + "="*60)
        print("⚠️  SESSION EXPIRY WARNING")
        print("="*60)
        for proc in disabled:
            print(f"  • {proc['name'].upper()}: Session expired")
            print(f"    Reason: {proc['reason']}")
            print(f"    Disabled at: {proc['disabled_at']}")
        print("\nRun 'python setup_sessions.py' to re-login.")
        print("Sessions will be validated on first use.")
        print("="*60 + "\n")

        # Send telegram notification if available
        if hunter.telegram_notifier:
            message = "⚠️ FLATHUNT RESTARTED - SESSION EXPIRY DETECTED ⚠️\n\n"
            for proc in disabled:
                message += f"• {proc['name'].upper()}: {proc['reason']}\n"
            message += "\nRun 'python setup_sessions.py' to re-login.\n"
            message += "Sessions will be validated on first use."
            hunter.telegram_notifier.notify(message)

    # Reset all processors to enabled (will be validated on first use)
    hunter.session_manager.reset_all()

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
