"""Expose crawler for Willhaben"""
import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup, Tag
from flathunter.logging import logger
from flathunter.abstract_crawler import Crawler


class Willhaben(Crawler):
    """Implementation of Crawler interface for Willhaben"""

    URL_PATTERN = re.compile(r'https://www\.willhaben\.at')

    def __init__(self, config):
        super().__init__(config)
        self.config = config

    def extract_data(self, soup: BeautifulSoup) -> List[Dict]:
        """Extracts all exposes from a provided Soup object"""
        entries = []

        try:
            # Find all listing links
            listings = soup.find_all('a', {'data-testid': lambda x: x and x.startswith('search-result-entry-header')})

            if not listings:
                logger.warning("No listings found on page - page structure may have changed or no results available")
                return entries

            logger.debug('Found %d listings on page', len(listings))

            for listing in listings:
                details = self.parse_listing(listing)
                if details:
                    entries.append(details)

            logger.info('Successfully extracted %d out of %d listings', len(entries), len(listings))

        except Exception as e:
            logger.error("Error extracting data from Willhaben page: %s", str(e), exc_info=True)

        return entries

    def parse_listing(self, listing: Tag) -> Optional[Dict]:
        """Parse a single listing element to extract details"""
        listing_id = "unknown"
        try:
            # Extract ID
            listing_id = listing.get('id', '').replace('search-result-entry-header-', '')
            if not listing_id:
                logger.warning("No listing ID found in listing element - skipping")
                return None

            # Extract title
            title_el = listing.find('h3')
            title = title_el.text.strip() if title_el else None
            if not title:
                logger.warning("No title found for listing %s - skipping (page structure may have changed)", listing_id)
                return None

            # Extract URL
            href = listing.get('href', '')
            if not href:
                logger.warning("No URL found for listing %s ('%s') - skipping", listing_id, title)
                return None
            url = f"https://www.willhaben.at{href}"

            # Extract price
            price_el = listing.find('span', {'data-testid': lambda x: x and 'price' in x})
            price = price_el.text.strip() if price_el else "N/A"
            if not price_el:
                logger.debug("No price found for listing %s - using 'N/A'", listing_id)

            # Extract size and rooms
            attributes = listing.find('div', {'data-testid': lambda x: x and 'teaser-attributes' in x})
            size = ""
            rooms = ""
            if attributes:
                attr_divs = attributes.find_all('div', class_='Text-sc-10o2fdq-0')
                for attr in attr_divs:
                    text = attr.text.strip()
                    if 'm²' in text:
                        size = text
                    elif 'Zimmer' in text:
                        # Extract just the number
                        room_match = re.search(r'(\d+)', text)
                        rooms = room_match.group(1) if room_match else ""
            else:
                logger.debug("No attributes section found for listing %s", listing_id)

            # Extract address
            address_el = listing.find('span', {'aria-label': lambda x: x and 'Ort' in x})
            address = address_el.text.strip() if address_el else url
            if not address_el:
                logger.debug("No address found for listing %s - using URL as fallback", listing_id)

            # Extract image
            img_el = listing.find('img')
            image = img_el.get('src', '') if img_el else None

            details = {
                'id': int(listing_id),
                'image': image,
                'url': url,
                'title': title,
                'price': price,
                'size': size,
                'rooms': rooms,
                'address': address,
                'crawler': self.get_name()
            }

            logger.debug("Successfully parsed listing %s: %s", listing_id, title)
            return details

        except ValueError as e:
            logger.error("Invalid listing ID format for '%s': %s", listing_id, str(e))
            return None
        except Exception as e:
            logger.error("Unexpected error parsing listing %s: %s", listing_id, str(e), exc_info=True)
            return None

    def load_address(self, url: str) -> Optional[str]:
        """Extract address from expose itself"""
        # The address is already in the listing preview, but we can override if needed
        logger.debug("Address extraction from detail page not implemented for Willhaben - using preview address")
        return None