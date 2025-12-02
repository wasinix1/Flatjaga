"""Expose crawler for derStandard.at Immobilien"""
import re
import hashlib
from typing import List, Dict, Optional

from bs4 import BeautifulSoup, Tag

from flathunter.logger_config import logger
from flathunter.abstract_crawler import Crawler


class DerStandard(Crawler):
    """Implementation of Crawler interface for derStandard.at Immobilien

    Austrian newspaper real estate portal - typically clean HTML structure
    """

    URL_PATTERN = re.compile(r'https://immobilien\.derstandard\.at')
    BASE_URL = "https://immobilien.derstandard.at"

    def __init__(self, config):
        super().__init__(config)
        self.config = config

    def extract_data(self, soup: BeautifulSoup) -> List[Dict]:
        """Extracts all exposes from a provided Soup object"""
        entries = []

        try:
            # Find all listing elements using multiple strategies
            listings = self._find_listings(soup)

            if not listings:
                logger.warning("No listings found on page - page structure may have changed or no results available")
                return entries

            logger.debug('Found %d potential listings on page', len(listings))

            for listing in listings:
                details = self.parse_listing(listing)
                if details:
                    entries.append(details)

            logger.debug('Successfully extracted %d out of %d derStandard listings', len(entries), len(listings))

        except Exception as e:
            logger.error("Error extracting data from derStandard page: %s", str(e), exc_info=True)

        return entries

    def _find_listings(self, soup: BeautifulSoup) -> List[Tag]:
        """Find listing elements using multiple strategies for robustness"""

        # Strategy 1: Find all links to detail pages (most reliable)
        detail_links = soup.find_all('a', href=re.compile(r'/detail/\d+'))
        if detail_links:
            # Get unique parent containers
            containers = []
            seen = set()
            for link in detail_links:
                # Find the nearest article/div parent that contains the full listing
                parent = link.find_parent(['article', 'div', 'li'])
                if parent and id(parent) not in seen:
                    containers.append(parent)
                    seen.add(id(parent))

            if containers:
                logger.debug("Found %d listings via detail page links", len(containers))
                return containers

        # Strategy 2: Find by common class patterns
        class_patterns = [
            ('listing', soup.find_all(class_=re.compile(r'listing', re.I))),
            ('card', soup.find_all(class_=re.compile(r'card', re.I))),
            ('result', soup.find_all(class_=re.compile(r'result', re.I))),
            ('item', soup.find_all(class_=re.compile(r'item', re.I))),
        ]

        for name, elements in class_patterns:
            # Filter to elements that have links (likely listings)
            elements = [e for e in elements if isinstance(e, Tag) and e.find('a', href=True)]
            # Reasonable listing count to avoid header/footer items
            if 5 <= len(elements) <= 100:
                logger.debug("Found %d listings via '%s' class pattern", len(elements), name)
                return elements

        # Strategy 3: Semantic HTML articles
        articles = soup.find_all('article')
        if articles:
            # Filter to articles with links
            articles = [a for a in articles if isinstance(a, Tag) and a.find('a', href=True)]
            if 5 <= len(articles) <= 100:
                logger.debug("Found %d listings via <article> semantic tags", len(articles))
                return articles

        logger.warning("Could not identify listing structure - all strategies failed")
        return []

    def parse_listing(self, container: Tag) -> Optional[Dict]:
        """Parse a single listing container to extract details"""
        listing_id = "unknown"
        try:
            # Extract URL and ID first (critical fields)
            url, listing_id = self._extract_url_and_id(container)
            if not url or not listing_id:
                logger.warning("No URL or ID found in listing element - skipping")
                return None

            # Extract title
            title = self._extract_title(container)
            if not title:
                logger.warning("No title found for listing %s - skipping (page structure may have changed)", listing_id)
                return None

            # Extract optional fields with fallbacks
            image = self._extract_image(container)
            if not image:
                logger.debug("No image URL found for listing %s", listing_id)

            price = self._extract_price(container)
            if not price:
                logger.debug("No price found for listing %s - using empty string", listing_id)

            size = self._extract_size(container)
            if not size:
                logger.debug("No size information found for listing %s", listing_id)

            rooms = self._extract_rooms(container)
            if not rooms:
                logger.debug("No room count found for listing %s", listing_id)

            address = self._extract_address(container)
            if not address:
                logger.debug("No address found for listing %s - using URL as fallback", listing_id)
                address = url

            details = {
                'id': listing_id,
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

    def _extract_url_and_id(self, container: Tag) -> tuple:
        """Extract URL and listing ID from container

        Returns:
            Tuple of (url, listing_id) or (None, None) if not found
        """
        # Find detail page link
        link = container.find('a', href=re.compile(r'/detail/\d+'))
        if not link:
            # Try any link as fallback
            link = container.find('a', href=True)

        if not link or not isinstance(link, Tag):
            return None, None

        href = link.get('href', '')
        if not href:
            return None, None

        # Make absolute URL
        if href.startswith('/'):
            url = self.BASE_URL + href
        elif href.startswith('http'):
            url = href
        else:
            url = self.BASE_URL + '/' + href

        # Extract ID from URL
        id_match = re.search(r'/detail/(\d+)', url)
        if id_match:
            listing_id = int(id_match.group(1))
        else:
            # Generate hash-based ID as fallback
            listing_id = int(hashlib.sha256(url.encode()).hexdigest(), 16) % 10**10
            logger.debug("No numeric ID in URL, using hash-based ID: %s", listing_id)

        return url, listing_id

    def _extract_title(self, container: Tag) -> str:
        """Extract listing title from container"""
        # Try heading tags first (most semantic)
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5']:
            title_elem = container.find(tag)
            if title_elem and isinstance(title_elem, Tag):
                title = title_elem.get_text(strip=True)
                if title:
                    return title

        # Try common title classes
        title_elem = container.find(class_=re.compile(r'title|headline|heading', re.I))
        if title_elem and isinstance(title_elem, Tag):
            title = title_elem.get_text(strip=True)
            if title:
                return title

        # Try link text as fallback
        link = container.find('a', href=True)
        if link and isinstance(link, Tag):
            title = link.get('title') or link.get_text(strip=True)
            if title:
                return title

        return ""

    def _extract_image(self, container: Tag) -> Optional[str]:
        """Extract listing image URL from container"""
        img = container.find('img')
        if not img or not isinstance(img, Tag):
            return None

        # Try multiple image source attributes (handles lazy loading)
        for attr in ['src', 'data-src', 'data-lazy-src']:
            img_url = img.get(attr)
            if img_url and isinstance(img_url, str) and img_url.startswith('http'):
                return img_url

        return None

    def _extract_price(self, container: Tag) -> str:
        """Extract price from container"""
        # Look for € symbol in text
        price_text = container.find(text=re.compile(r'€'))
        if price_text:
            parent = price_text.find_parent()
            if parent and isinstance(parent, Tag):
                price_str = parent.get_text(strip=True)
                # Clean up (remove extra whitespace, newlines)
                price_str = ' '.join(price_str.split())
                return price_str

        # Try common price classes
        price_elem = container.find(class_=re.compile(r'price|preis', re.I))
        if price_elem and isinstance(price_elem, Tag):
            return price_elem.get_text(strip=True)

        return ""

    def _extract_size(self, container: Tag) -> str:
        """Extract apartment size from container"""
        # Look for m² symbol in text
        size_text = container.find(text=re.compile(r'm[²2]', re.I))
        if size_text:
            parent = size_text.find_parent()
            if parent and isinstance(parent, Tag):
                size_str = parent.get_text(strip=True)
                # Extract just the size part (e.g., "75 m²")
                size_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', size_str, re.I)
                if size_match:
                    return size_match.group(0)
                return size_str

        # Try common size classes
        size_elem = container.find(class_=re.compile(r'size|area|flaeche', re.I))
        if size_elem and isinstance(size_elem, Tag):
            return size_elem.get_text(strip=True)

        return ""

    def _extract_rooms(self, container: Tag) -> str:
        """Extract number of rooms from container"""
        # Look for "Zimmer" or "Zi." in text
        rooms_text = container.find(text=re.compile(r'Zimmer|Zi\.', re.I))
        if rooms_text:
            parent = rooms_text.find_parent()
            if parent and isinstance(parent, Tag):
                rooms_str = parent.get_text(strip=True)
                # Extract just the number
                room_match = re.search(r'(\d+)', rooms_str)
                if room_match:
                    return room_match.group(1)
                return rooms_str

        # Try common room classes
        rooms_elem = container.find(class_=re.compile(r'room|zimmer', re.I))
        if rooms_elem and isinstance(rooms_elem, Tag):
            text = rooms_elem.get_text(strip=True)
            room_match = re.search(r'(\d+)', text)
            if room_match:
                return room_match.group(1)

        return ""

    def _extract_address(self, container: Tag) -> str:
        """Extract address/location from container"""
        # Try common address classes
        addr_elem = container.find(class_=re.compile(r'address|location|ort|adresse', re.I))
        if addr_elem and isinstance(addr_elem, Tag):
            return addr_elem.get_text(strip=True)

        # Look for Vienna postal codes (1xxx Wien pattern)
        text = container.get_text()
        vienna_match = re.search(r'1\d{3}\s+Wien[^,]*', text)
        if vienna_match:
            return vienna_match.group(0).strip()

        # Look for any Austrian postal code pattern
        postal_match = re.search(r'\d{4}\s+[A-ZÄÖÜ][a-zäöü]+', text)
        if postal_match:
            return postal_match.group(0).strip()

        return ""

    def load_address(self, url: str) -> Optional[str]:
        """Extract detailed address from expose detail page

        This method can be used to get more detailed address information
        from the individual listing page if needed.
        """
        try:
            soup = self.get_soup_from_url(url)
            if not soup:
                logger.warning("Failed to load page for address extraction: %s", url)
                return None

            # Try multiple selectors for detail page address
            address_selectors = [
                soup.find(class_=re.compile(r'address|location|ort|adresse', re.I)),
                soup.find(attrs={'itemprop': 'address'}),
                soup.find(text=re.compile(r'1\d{3}\s+Wien')),
            ]

            for elem in address_selectors:
                if elem:
                    if isinstance(elem, Tag):
                        address = elem.get_text(strip=True)
                    else:
                        # Text node - get parent
                        parent = elem.find_parent()
                        address = parent.get_text(strip=True) if parent and isinstance(parent, Tag) else str(elem)

                    if address:
                        logger.debug("Successfully extracted detailed address: %s", address)
                        return address

            logger.debug("No detailed address found in expose page: %s", url)
            return None

        except Exception as e:
            logger.error("Error loading address from %s: %s", url, str(e), exc_info=True)
            return None
