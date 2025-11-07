"""Expose crawler for WgGesucht"""
import re
import time
import random
from typing import Optional, List, Dict, Any, Union

import requests
from bs4 import BeautifulSoup, Tag

from flathunter.logger_config import logger
from flathunter.abstract_crawler import Crawler


def get_title(title_row: Tag) -> str:
    """Parse the title from the expose title element"""
    return title_row.text.strip()


def get_url(title_row: Tag) -> Optional[str]:
    """Parse the expose URL from the expose title element"""
    a_element = title_row.find('a')
    if not isinstance(a_element, Tag) \
            or not a_element.has_attr('href') \
            or not isinstance(a_element.attrs['href'], str):
        return None
    return 'https://www.wg-gesucht.de/' + a_element.attrs['href'].removeprefix("/")


def extract_href_style(row: Tag) -> Optional[str]:
    """Extract the style attribute from a image div"""
    div = row.find('div', {"class": "card_image"})
    if not isinstance(div, Tag):
        return None
    a_element = div.find('a')
    if not isinstance(a_element, Tag) or not a_element.has_attr('style'):
        return None
    style = a_element.attrs['style']
    if not isinstance(style, str):
        return None
    return style


def get_image_url(row: Tag) -> Optional[str]:
    """Parse the image url from the expose"""
    try:
        href_style = extract_href_style(row)
        if href_style is None:
            return None
        image_match = re.match(r'background-image: url\((.*)\);', href_style)
        if image_match is None:
            logger.debug("Image style attribute found but URL pattern not matched: %s", href_style[:100])
            return None
        return image_match[1]
    except Exception as e:
        logger.debug("Error extracting image URL: %s", str(e))
        return None


def get_rooms(row: Tag) -> str:
    """Parse the number of rooms from the expose"""
    try:
        details_el = row.find("div", {"class": "col-xs-11"})
        if not isinstance(details_el, Tag):
            return ""
        detail_string = details_el.text.strip().split("|")
        details_array = list(map(lambda s: re.sub(' +', ' ',
                                                  re.sub(r'\W', ' ', s.strip())),
                                 detail_string))
        if not details_array or len(details_array) == 0:
            return ""
        rooms_tmp = re.findall(r'\d Zimmer', details_array[0])
        return rooms_tmp[0][:1] if rooms_tmp else ""
    except (IndexError, AttributeError) as e:
        logger.debug("Error parsing room count: %s", str(e))
        return ""
    except Exception as e:
        logger.debug("Unexpected error parsing room count: %s", str(e))
        return ""


def get_price(numbers_row: Tag) -> Optional[str]:
    """Parse the price from the expose"""
    price_el = numbers_row.find("div", {"class": "col-xs-3"})
    if not isinstance(price_el, Tag):
        return None
    return price_el.text.strip()


def get_dates(numbers_row: Tag) -> List[str]:
    """Parse the advert dates from the expose"""
    date_el = numbers_row.find("div", {"class": "text-center"})
    if not isinstance(date_el, Tag):
        return []
    return re.findall(r'\d{2}.\d{2}.\d{4}', date_el.text)


def get_size(numbers_row: Tag) -> List[str]:
    """Parse the room size from the expose"""
    size_el = numbers_row.find("div", {"class": "text-right"})
    if not isinstance(size_el, Tag):
        return []
    return re.findall(r'\d{1,4}\sm²', size_el.text)

def is_verified_company(row: Tag) -> bool:
    """Filter out ads from 'Verified Companies'"""
    verified_el = row.find("span", {"class": "label_verified"})
    if isinstance(verified_el, Tag):
        return True
    return False

# pylint: disable=too-many-return-statements
def parse_expose_element_to_details(row: Tag, crawler: str) -> Optional[Dict]:
    """Parse an Expose soup element to an Expose details dictionary"""
    url = "unknown"
    try:
        title_row = row.find('h2', {"class": "truncate_title"})
        if title_row is None or not isinstance(title_row, Tag):
            logger.warning("No title element found in listing - skipping (page structure may have changed)")
            return None
        if is_verified_company(row):
            logger.debug("Verified company listing detected - skipping")
            return None
        title = get_title(title_row)
        url = get_url(title_row)
        if url is None:
            logger.warning("No expose URL found for listing '%s' - skipping", title)
            return None
        image = get_image_url(row)
        if image is None:
            logger.debug("No image URL found for expose %s", url)
        rooms = get_rooms(row)
        if not rooms:
            logger.debug("No room count found for expose %s", url)
        numbers_row = row.find("div", {"class": "middle"})
        if not isinstance(numbers_row, Tag):
            logger.warning("No numbers section found for expose %s - skipping (page structure may have changed)", url)
            return None
        price = get_price(numbers_row)
        if price is None:
            logger.debug("No price found for expose %s", url)
        dates = get_dates(numbers_row)
        if len(dates) == 0:
            logger.warning("No availability dates found for expose %s - skipping", url)
            return None
        size = get_size(numbers_row)
        if len(size) == 0:
            logger.warning("No size information found for expose %s - skipping", url)
            return None

        if len(dates) == 2:
            title = f"{title} vom {dates[0]} bis {dates[1]}"
        else:
            title = f"{title} ab dem {dates[0]}"

        details = {
            'id': int(url.split('.')[-2]),
            'image': image,
            'url': url,
            'title': title,
            'price': price,
            'size': size[0],
            'rooms': rooms,
            'address': url,
            'crawler': crawler
        }
        if len(dates) == 2:
            details['from'] = dates[0]
            details['to'] = dates[1]
        elif len(dates) == 1:
            details['from'] = dates[0]

        logger.debug("Successfully parsed expose: %s", title)
        return details

    except (ValueError, IndexError) as e:
        logger.error("Error parsing expose ID from URL %s: %s", url, str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error parsing expose %s: %s", url, str(e), exc_info=True)
        return None


def liste_attribute_filter(element: Union[Tag, str]) -> bool:
    """Return true for elements whose 'id' attribute starts with 'liste-' 
    and are not contained in the 'premium_user_extra_list' container"""
    if not isinstance(element, Tag):
        return False
    if not element.attrs or "id" not in element.attrs:
        return False
    if not element.parent or not element.parent.attrs or "class" not in element.parent.attrs:
        return False
    return element.attrs["id"].startswith('liste-') and \
        'premium_user_extra_list' not in element.parent.attrs["class"]


class WgGesucht(Crawler):
    """Implementation of Crawler interface for WgGesucht"""

    URL_PATTERN = re.compile(r'https://www\.wg-gesucht\.de')

    def __init__(self, config):
        super().__init__(config)
        self.config = config

    # pylint: disable=too-many-locals
    def extract_data(self, raw_data: BeautifulSoup) -> List[Dict]:
        """Extracts all exposes from a provided Soup object"""
        entries = []

        try:
            findings = raw_data.find_all(liste_attribute_filter)
            if not findings:
                logger.warning("No listing elements found on page - page structure may have changed or no results available")
                return entries

            existing_findings = [
                e for e in findings
                if isinstance(e, Tag) and e.has_attr('class') and not 'display-none' in e['class']
            ]

            logger.debug('Found %d total listings (%d visible)', len(findings), len(existing_findings))

            for row in existing_findings:
                details = parse_expose_element_to_details(row, self.get_name())
                if details is None:
                    continue
                entries.append(details)

            logger.debug('Successfully extracted %d out of %d WG-Gesucht listings', len(entries), len(existing_findings))

        except Exception as e:
            logger.error("Error extracting data from WG-Gesucht page: %s", str(e), exc_info=True)

        return entries

    def load_address(self, url) -> Optional[str]:
        """Extract address from expose itself"""
        try:
            response = self.get_soup_from_url(url)
            if not response:
                logger.warning("Failed to load page for address extraction: %s", url)
                return None

            address_div = response.find('div', {"class": "col-sm-4 mb10"})
            if not isinstance(address_div, Tag):
                logger.debug("No address container found in expose page: %s", url)
                return None

            a_element = address_div.find("a", {"href": "#mapContainer"})
            if not isinstance(a_element, Tag):
                logger.debug("No address link found in expose page: %s", url)
                return None

            address = ' '.join(a_element.text.strip().split())
            logger.debug("Successfully extracted address for %s: %s", url, address)
            return address

        except Exception as e:
            logger.error("Error loading address from %s: %s", url, str(e), exc_info=True)
            return None

    def get_soup_from_url(
            self,
            url: str,
            driver: Optional[Any] = None,
            checkbox: bool = False,
            afterlogin_string: Optional[str] = None,
            retry_count: int = 0) -> BeautifulSoup:
        """
        Creates a Soup object from the HTML at the provided URL

        Overwrites the method inherited from abstract_crawler. This is
        necessary as we need to reload the page once for all filters to
        be applied correctly on wg-gesucht.

        Implements exponential backoff with jitter for retries to avoid rate limiting.

        Args:
            url: URL to fetch
            driver: Optional Selenium driver
            checkbox: Captcha checkbox flag
            afterlogin_string: String to wait for after login
            retry_count: Current retry attempt (for internal use)
        """
        max_retries = 3
        base_delay = 5  # seconds

        try:
            sess = requests.session()
            # First page load to set filters; response is discarded
            logger.debug("Loading WG-Gesucht page (first request to set filters): %s", url)
            sess.get(url, headers=self.HEADERS, timeout=30)
            # Second page load
            logger.debug("Loading WG-Gesucht page (second request): %s", url)
            resp = sess.get(url, headers=self.HEADERS, timeout=30)

            # Check for rate limiting (HTTP 429) or server errors (5xx)
            if resp.status_code == 429:
                logger.warning("WG-Gesucht rate limit hit (HTTP 429)")
                raise requests.exceptions.RequestException("Rate limited")
            elif resp.status_code >= 500:
                logger.warning(f"WG-Gesucht server error (HTTP {resp.status_code})")
                raise requests.exceptions.RequestException("Server error")
            elif resp.status_code not in (200, 405):
                logger.error("Received HTTP %d from WG-Gesucht for URL %s: %s",
                           resp.status_code, url, resp.content[:200])
            elif resp.status_code == 200:
                logger.debug("Successfully loaded page: %s", url)

            if self.config.use_proxy():
                logger.debug("Using proxy for URL: %s", url)
                return self.get_soup_with_proxy(url)
            if driver is not None:
                logger.debug("Using webdriver for URL: %s", url)
                driver.get(url)
                if re.search("initGeetest", driver.page_source):
                    logger.info("Geetest captcha detected, attempting to resolve...")
                    self.resolve_geetest(driver)
                elif re.search("g-recaptcha", driver.page_source):
                    logger.info("reCAPTCHA detected, attempting to resolve...")
                    self.resolve_recaptcha(
                        driver, checkbox, afterlogin_string or "")
                return BeautifulSoup(driver.page_source, 'lxml')
            return BeautifulSoup(resp.content, 'lxml')

        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as exc:
            if retry_count >= max_retries:
                logger.error(
                    f"WG-Gesucht page load failed after {max_retries} retries - likely rate limited or down: {url}"
                )
                # Return empty soup after exhausting retries
                return BeautifulSoup("", 'lxml')

            # Exponential backoff with jitter to avoid thundering herd
            delay = base_delay * (2 ** retry_count) + random.uniform(0, 3)
            logger.warning(
                f"WG-Gesucht request failed ({type(exc).__name__}), "
                f"retrying in {delay:.1f}s (attempt {retry_count + 1}/{max_retries})"
            )
            time.sleep(delay)

            return self.get_soup_from_url(url, driver, checkbox, afterlogin_string, retry_count + 1)

        except Exception as e:
            logger.error("Unexpected error loading WG-Gesucht page %s: %s", url, str(e), exc_info=True)
            return BeautifulSoup("", 'lxml')
