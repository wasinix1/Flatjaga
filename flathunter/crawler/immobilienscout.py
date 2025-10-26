"""Expose crawler for ImmobilienScout"""
import re
import time
import random
from urllib.parse import urlencode, urlparse, parse_qs

import requests

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger
from flathunter.schemas.immobilienscout import ImmoscoutQuery

STATIC_URL_PATTERN = re.compile(r'https://www\.immobilienscout24\.de')

class Immobilienscout(Crawler):
    """Implementation of Crawler interface for ImmobilienScout"""

    URL_PATTERN = STATIC_URL_PATTERN

    # Rotate user agents to avoid detection
    MOBILE_USER_AGENTS = [
        "ImmoScout_27.3_26.0_._",
        "ImmoScout_27.4_26.1_._",
        "ImmoScout_27.2_25.9_._",
        "ImmoScout_28.0_27.0_._",
        "ImmoScout_27.5_26.2_._",
    ]

    RESULT_LIMIT = 50

    FALLBACK_IMAGE_URL = "https://www.static-immobilienscout24.de/statpic/placeholder_house/" + \
                         "496c95154de31a357afa978cdb7f15f0_placeholder_medium.png"

    def get_headers(self) -> dict:
        """Get headers with a random user agent to avoid detection"""
        return {
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": random.choice(self.MOBILE_USER_AGENTS)
        }


    def get_immoscout_query(self, search_url: str) -> ImmoscoutQuery:
        """Builds an Immoscout query from a web interface URL,
        transforms and validates parameters"""
        parsed_url = urlparse(search_url)
        path_elements = parsed_url.path.split("/")

        real_estate_type = path_elements.pop()
        geocodes = None
        if "radius" in path_elements:
            search_type = "radius"
        else:
            search_type = "region"
            geocodes = "/".join(path_elements[2:])
        _ = parse_qs(parsed_url.query)
        query_params: dict[str, str | list[str]] = {}
        # split comma-separated query param values into list
        for k in _: # pylint: disable=consider-using-dict-items
            query_params[k] = [v for value in _[k] for v in value.split(",")]
            # unpack single item lists unless ImmoscoutQuery expects a list
            if len(query_params[k]) == 1 and k not in (
                "apartmenttypes",
                "energyefficiencyclasses",
                "equipment",
                "exclusioncriteria",
                "heatingtypes",
                "petsallowedtypes"
            ):
                query_params[k] = query_params[k][0]
        return ImmoscoutQuery(
            realestatetype=real_estate_type, # type: ignore
            searchtype=search_type,
            geocodes=geocodes,
            # set pagesize to result limit to minimize number of API requests
            pagesize=self.RESULT_LIMIT,
            **query_params # type: ignore
        )

    def compose_api_url(self, query: ImmoscoutQuery) -> str:
        """Constructs a mobile API URL from an Immoscout query"""
        api_url = "https://api.mobile.immobilienscout24.de/search/list?"
        query_dict = query.model_dump(exclude_none=True)
        for k, v in query_dict.items():
            # join list items to comma-separated query parameter string
            if isinstance(v, list):
                query_dict[k] = ",".join(v)
        return api_url + urlencode(query_dict)

    def fetch_api_data(self, search_url: str, page_no: int | None = None,
                      retry_count: int = 0) -> requests.Response:
        """Applies a page number to a formatted API URL and fetches the exposes at that page

        Implements exponential backoff with jitter for retries to avoid rate limiting.

        Args:
            search_url: API URL with page number placeholder
            page_no: Page number to fetch
            retry_count: Current retry attempt (for internal use)

        Returns:
            Response object from the API

        Raises:
            requests.exceptions.RequestException: If all retries are exhausted
        """
        max_retries = 3
        base_delay = 5  # seconds

        data = {
            "supportedResultListType": [],
            "userData": {}
        }

        try:
            response = requests.post(
                search_url.format(page_no),
                headers=self.get_headers(),
                json=data,
                timeout=30
            )

            # Check for rate limiting (HTTP 429) or server errors (5xx)
            if response.status_code == 429:
                logger.warning("ImmoScout rate limit hit (HTTP 429)")
                raise requests.exceptions.RequestException("Rate limited")
            elif response.status_code >= 500:
                logger.warning(f"ImmoScout server error (HTTP {response.status_code})")
                raise requests.exceptions.RequestException("Server error")

            return response

        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as exc:
            if retry_count >= max_retries:
                logger.error(
                    f"ImmoScout API failed after {max_retries} retries - likely rate limited or down"
                )
                raise

            # Exponential backoff with jitter to avoid thundering herd
            delay = base_delay * (2 ** retry_count) + random.uniform(0, 3)
            logger.warning(
                f"ImmoScout request failed ({type(exc).__name__}), "
                f"retrying in {delay:.1f}s (attempt {retry_count + 1}/{max_retries})"
            )
            time.sleep(delay)

            return self.fetch_api_data(search_url, page_no, retry_count + 1)

    def extract_data(self, raw_data: dict) -> list:
        """Extracts all exposes from a JSON dictionary"""
        entries = []

        results = filter(
            lambda entry: entry.get("type") == "EXPOSE_RESULT",
            raw_data.get("resultListItems") or []
        )
        for expose in results:
            expose_details = expose.get("item")
            details = {
                'id': int(expose_details.get("id")),
                'url': "https://www.immobilienscout24.de/expose/" + expose_details.get("id"),
                # remove height and width parameters from image URL
                'image': re.sub(
                    r"(.+?(?:\.(?:jpe?g|png))).*",
                    r"\1",
                    expose_details.get("titlePicture", {}).get("preview", self.FALLBACK_IMAGE_URL),
                    flags=re.IGNORECASE
                ),
                'title': expose_details.get("title", ""),
                'address': expose_details.get("address", {}).get("line", ""),
                'crawler': self.get_name()
            }
            flat_attributes = [
                attribute.get("value") for attribute in expose_details.get("attributes")
            ]
            for attr in flat_attributes:
                if "€" in attr:
                    details["price"] = attr.replace("\xa0€", "")
                elif "m²" in attr:
                    details["size"] = attr.replace("\xa0m²", "")
                elif "Zi." in attr:
                    details["rooms"] = attr.replace("\xa0Zi.", "")
            entries.append(details)

        logger.debug('Number of entries found: %d', len(entries))
        return entries

    def get_results(self, search_url: str, max_pages: int | None = None) -> list:
        """Fetches the exposes from the ImmoScout mobile API, starting at the provided URL"""
        query = self.get_immoscout_query(search_url)
        api_url = self.compose_api_url(query)
        if '&pagenumber' in api_url:
            api_url = re.sub(r"&pagenumber=[0-9]", "&pagenumber={0}", api_url)
        else:
            api_url = api_url + '&pagenumber={0}'
        logger.debug("Got search URL %s", api_url)

        page_no = 1
        listings = self.fetch_api_data(api_url, page_no).json()

        no_of_results = listings["totalResults"]

        # get data from first page
        entries = self.extract_data(listings)

        # iterate over all remaining pages
        while len(entries) < min(no_of_results, self.RESULT_LIMIT) and \
                (max_pages is None or page_no < max_pages):
            logger.debug(
                '(Next page) Number of entries: %d / Number of results: %d',
                len(entries), no_of_results)

            # Add delay between pages to avoid rate limiting (2-4 seconds)
            delay = random.uniform(2.0, 4.0)
            logger.debug(f"Waiting {delay:.1f}s before fetching next page")
            time.sleep(delay)

            page_no += 1
            listings = self.fetch_api_data(api_url, page_no).json()
            cur_entries = self.extract_data(listings)
            entries.extend(cur_entries)
        return entries
