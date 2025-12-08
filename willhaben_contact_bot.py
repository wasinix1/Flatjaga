#!/usr/bin/env python3
"""
Willhaben Auto-Contact Bot
Automatically sends contact messages to apartment listings
"""

import time
import random
import json
import os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class WillhabenContactBot:
    def __init__(self, headless=False):
        """
        Initialize the bot with Chrome WebDriver
        
        Args:
            headless: Run Chrome in headless mode (no visible browser)
        """
        self.options = webdriver.ChromeOptions()
        
        if headless:
            self.options.add_argument('--headless')
        
        # Make it look more like a real browser
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = None
        self.cookies_file = Path.home() / '.willhaben_cookies.json'
        self.contacted_file = Path.home() / '.willhaben_contacted.json'
        self.contacted_listings = self._load_contacted_listings()
    
    def _load_contacted_listings(self):
        """Load the list of already contacted listing IDs"""
        if self.contacted_file.exists():
            with open(self.contacted_file, 'r') as f:
                return set(json.load(f))
        return set()
    
    def _save_contacted_listing(self, listing_id):
        """Save a listing ID as contacted"""
        self.contacted_listings.add(listing_id)
        with open(self.contacted_file, 'w') as f:
            json.dump(list(self.contacted_listings), f)
    
    def _random_delay(self, min_sec=0.5, max_sec=2.0):
        """Add a random delay to simulate human behavior"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def accept_cookies(self):
        """Accept cookie banner if it appears - optimized for speed"""
        try:
            # Give page a moment to load, then immediately grab all buttons
            time.sleep(0.5)
            
            # Find all buttons on page
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            
            # Look for cookie accept button by text
            for button in buttons:
                try:
                    button_text = button.text.lower()
                    if any(word in button_text for word in ['akzeptieren', 'accept', 'zustimmen', 'agree', 'alle']):
                        button.click()
                        print("✓ Cookies accepted")
                        time.sleep(0.3)
                        return True
                except:
                    continue
                    
            print("  (No cookie banner found)")
            return False
        except Exception as e:
            print("  (Cookie acceptance skipped)")
            return False
    
    def accept_privacy_popup(self):
        """Accept the 'Zu deiner Sicherheit' privacy popup if it appears - optimized"""
        try:
            time.sleep(0.3)  # Brief pause
            
            # Look for "Ja, ich stimme zu" button
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                try:
                    if "ja, ich stimme zu" in button.text.lower():
                        button.click()
                        print("✓ Privacy popup accepted")
                        time.sleep(0.3)
                        return True
                except:
                    continue
                    
            print("  (No privacy popup)")
            return False
        except Exception as e:
            print("  (Privacy popup skipped)")
            return False
    
    def start(self):
        """Start the Chrome WebDriver with auto version matching"""
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=self.options)
        print("✓ Browser started")
    
    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            print("✓ Browser closed")
    
    def save_cookies(self):
        """Save cookies to file for session persistence"""
        cookies = self.driver.get_cookies()
        with open(self.cookies_file, 'w') as f:
            json.dump(cookies, f)
        print(f"✓ Cookies saved to {self.cookies_file}")
    
    def load_cookies(self):
        """Load cookies from file to resume session"""
        if not self.cookies_file.exists():
            return False
        
        # Need to visit the domain first before adding cookies
        self.driver.get('https://www.willhaben.at')
        self._random_delay()
        
        with open(self.cookies_file, 'r') as f:
            cookies = json.load(f)
        
        for cookie in cookies:
            # Selenium doesn't like some cookie fields
            if 'expiry' in cookie:
                cookie['expiry'] = int(cookie['expiry'])
            self.driver.add_cookie(cookie)
        
        print("✓ Cookies loaded")
        return True
    
    def login_manual(self):
        """
        Open login page and wait for user to login manually
        Then save the session cookies
        """
        print("\n=== Manual Login Required ===")
        print("1. The browser will open to the Willhaben login page")
        print("2. Please login with your credentials")
        print("3. Once logged in, come back here and press Enter")
        print("=============================\n")
        
        # Navigate to main page first, then click login to trigger SSO
        self.driver.get('https://www.willhaben.at')
        self._random_delay(1, 2)
        
        # Try to find and click the login button
        try:
            login_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Anmelden"))
            )
            login_button.click()
            self._random_delay(1, 2)
        except:
            # If can't find button, just go to SSO directly
            self.driver.get('https://sso.willhaben.at/auth/realms/willhaben/protocol/openid-connect/auth?response_type=code&client_id=bbx-bff&scope=openid&redirect_uri=https://www.willhaben.at/webapi/oauth2/code/sso')
            self._random_delay(1, 2)
        
        input("Press Enter once you've logged in successfully...")
        
        # Save the session
        self.save_cookies()
        print("✓ Login session saved!")
    
    def is_already_contacted(self, listing_url):
        """Check if we've already contacted this listing"""
        # Extract listing ID from URL (usually the last part)
        listing_id = listing_url.rstrip('/').split('/')[-1]
        return listing_id in self.contacted_listings
    
    def send_contact_message(self, listing_url):
        """
        Send a contact message to a specific listing
        
        Args:
            listing_url: Full URL to the willhaben listing
            
        Returns:
            True if message sent successfully, False otherwise
        """
        # Check if already contacted
        if self.is_already_contacted(listing_url):
            print(f"⊘ Already contacted: {listing_url}")
            return False
        
        listing_id = listing_url.rstrip('/').split('/')[-1]
        
        try:
            print(f"\n→ Opening listing: {listing_url}")
            self.driver.get(listing_url)
            self._random_delay(0.5, 1)  # Reduced
            
            # Wait for the contact form to appear
            wait = WebDriverWait(self.driver, 10)
            
            # Find the contact form - could be either email form or messaging form
            print("→ Looking for contact form...")
            form_found = False
            form_type = None
            
            # Try to find email form (company listings)
            try:
                wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'form[data-testid="ad-contact-form-email"]'))
                )
                form_type = "email"
                form_found = True
                print("  (Found company listing form)")
            except:
                pass
            
            # Try to find messaging form (private listings)
            if not form_found:
                try:
                    wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'form[data-testid="ad-contact-form-messaging"]'))
                    )
                    form_type = "messaging"
                    form_found = True
                    print("  (Found private listing form)")
                except Exception as e:
                    print(f"  (Could not find messaging form: {str(e)})")
                    raise Exception("Could not find contact form")
            
            # If it's an email form (company listing), check the boxes
            if form_type == "email":
                # Click the "Ist eine Besichtigung möglich?" checkbox
                # The checkbox input is hidden, so we use JavaScript to click it
                print("→ Checking 'Ist eine Besichtigung möglich?' box...")
                viewing_checkbox = wait.until(
                    EC.presence_of_element_located((By.ID, "contactSuggestions-6"))
                )
                self.driver.execute_script("arguments[0].click();", viewing_checkbox)
                self._random_delay(0.3, 0.8)
                
                # Mietprofil checkbox: Should be auto-checked for logged-in users
                # We don't interact with it to avoid race conditions with React hydration
                print("  (Mietprofil checkbox should be auto-checked)")
                
                # Find and click the email submit button
                print("→ Clicking email submit button...")
                submit_button = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="ad-request-send-mail"]'))
                )
            else:
                # For messaging form (private listing), need to fill the message textarea
                print("→ Looking for message textarea...")
                try:
                    message_textarea = self.driver.find_element(By.ID, "mailContent")
                    if not message_textarea.get_attribute("value"):
                        print("→ Filling message field...")
                        # Add a simple message (you can customize this)
                        message_text = "Guten Tag,\n\nich interessiere mich für diese Wohnung und würde gerne einen Besichtigungstermin vereinbaren.\n\nMit freundlichen Grüßen"
                        message_textarea.send_keys(message_text)
                        self._random_delay(0.3, 0.8)
                except:
                    pass
                
                # Find the submit button
                print("→ Looking for message submit button...")
                try:
                    submit_button = wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="ad-request-send-message"]'))
                    )
                    print(f"  (Found button with text: '{submit_button.text}')")
                except Exception as e:
                    print(f"  ✗ Could not find submit button: {str(e)}")
                    # Try to find ANY submit button as fallback
                    print("  → Trying to find any submit button...")
                    submit_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
                    print(f"  → Found {len(submit_buttons)} submit buttons")
                    for btn in submit_buttons:
                        print(f"    - Button text: '{btn.text}', testid: {btn.get_attribute('data-testid')}")
                    raise
            
            # Click whichever button we found
            print(f"→ About to submit form via button: '{submit_button.text}'")
            print(f"  (Button testid: {submit_button.get_attribute('data-testid')})")
            
            # Add a small delay before clicking
            self._random_delay(0.8, 1.5)
            
            # Try clicking the button normally first (not JavaScript) to trigger proper form validation
            try:
                submit_button.click()
                print("✓ Button clicked (normal click)!")
            except:
                # If normal click fails, fall back to JavaScript
                print("  (Normal click failed, trying JavaScript...)")
                self.driver.execute_script("arguments[0].click();", submit_button)
                print("✓ Button clicked (JavaScript)!")
            
            self._random_delay(1, 2)  # Longer delay after click to let form submit
            
            # Privacy popup appears after clicking submit - accept it
            print("→ Accepting privacy popup...")
            self.accept_privacy_popup()
            self._random_delay(0.5, 1)  # Reduced
            
            # Check for success message
            print("→ Waiting for confirmation...")
            # Could be either "E-Mail wurde erfolgreich" or "Nachricht wurde erfolgreich"
            success_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'wurde erfolgreich')]")
            
            if success_elements:
                # Mark as contacted
                self._save_contacted_listing(listing_id)
                print(f"✓ Message sent successfully to {listing_id}!")
                return True
            else:
                print(f"✗ Could not confirm message was sent")
                return False
            
        except TimeoutException:
            print(f"✗ Timeout waiting for contact form on {listing_url}")
            return False
        except Exception as e:
            print(f"✗ Error sending message: {str(e)}")
            return False
    
    def test_single_listing(self, listing_url):
        """
        Test the bot on a single listing
        Good for debugging and initial testing
        """
        print("\n=== Testing Single Listing ===")
        
        self.start()
        
        # Try to load existing session
        if self.load_cookies():
            print("✓ Using saved session")
        else:
            print("! No saved session found")
            self.login_manual()
        
        # Refresh to apply cookies
        self.driver.get('https://www.willhaben.at')
        self._random_delay()
        
        # Accept cookies if needed
        self.accept_cookies()
        
        # Send the message
        success = self.send_contact_message(listing_url)
        
        print("\n=== Test Complete ===")
        print(f"Result: {'SUCCESS' if success else 'FAILED'}")
        
        input("\nPress Enter to close browser...")
        self.close()


def main():
    """
    Test script - run this to test on a single listing
    """
    print("=" * 50)
    print("Willhaben Auto-Contact Bot")
    print("=" * 50)
    
    # Get listing URL from user
    print("\nPaste a Willhaben listing URL to test:")
    listing_url = input("> ").strip()
    
    if not listing_url:
        print("No URL provided, exiting...")
        return
    
    # Create bot and test
    bot = WillhabenContactBot(headless=False)
    bot.test_single_listing(listing_url)


if __name__ == "__main__":
    main()
