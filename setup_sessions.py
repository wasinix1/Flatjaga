#!/usr/bin/env python3
"""
Setup Sessions Script
Unified script to manually login to Willhaben and/or WG-Gesucht
"""

import sys
from pathlib import Path

def setup_willhaben():
    """Setup Willhaben session with manual login"""
    print("\n" + "="*60)
    print("WILLHABEN SESSION SETUP")
    print("="*60)

    try:
        from willhaben_contact_bot import WillhabenContactBot

        bot = WillhabenContactBot(headless=False)
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

def setup_wggesucht():
    """Setup WG-Gesucht session with manual login"""
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
        # Stealth mode not needed for manual login
        bot = WgGesuchtContactBot(headless=False, stealth_mode=False)
        bot.start()

        # Explicitly call manual login (used only in setup, not during automated runs)
        bot._login_manual()

        print("\n✓ WG-Gesucht session saved!")

        bot.close()
        return True

    except Exception as e:
        print(f"\n✗ Error setting up WG-Gesucht session: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main menu for session setup"""
    print("\n" + "="*60)
    print("FLATJAGA SESSION SETUP")
    print("="*60)
    print("\nThis script helps you login to Willhaben and WG-Gesucht")
    print("so that Flatjaga can automatically contact listings.\n")
    print("Options:")
    print("  1. Setup Willhaben session")
    print("  2. Setup WG-Gesucht session")
    print("  3. Setup both")
    print("  q. Quit")
    print("="*60)

    choice = input("\nEnter your choice (1/2/3/q): ").strip().lower()

    if choice == 'q':
        print("\nExiting...")
        return

    success = True

    if choice in ['1', '3']:
        if not setup_willhaben():
            success = False

    if choice in ['2', '3']:
        if not setup_wggesucht():
            success = False

    if choice not in ['1', '2', '3']:
        print("\n✗ Invalid choice. Please run again and select 1, 2, 3, or q.")
        return

    if success:
        print("\n" + "="*60)
        print("✓ SETUP COMPLETE!")
        print("="*60)
        print("\nYou can now run Flatjaga normally:")
        print("  python flathunt.py")
        print("\nThe bots will use your saved sessions to automatically")
        print("contact new listings.\n")
    else:
        print("\n" + "="*60)
        print("⚠ SETUP INCOMPLETE")
        print("="*60)
        print("\nSome sessions failed to setup. Please check the errors above")
        print("and try again.\n")

if __name__ == "__main__":
    main()
