import os
import unittest
import pytest

from flathunter.crawler.derstandard import DerStandard
from test.utils.config import StringConfig


class DerStandardCrawlerTest(unittest.TestCase):
    """Test suite for DerStandard crawler"""

    # Example URL - update with actual search URL if needed
    TEST_URL = 'https://immobilien.derstandard.at/suche?etage%5Bvon%5D=&etage%5Bbis%5D=&flaeche%5Bvon%5D=&flaeche%5Bbis%5D=&kaufpreis%5Bvon%5D=&kaufpreis%5Bbis%5D=&miete%5Bvon%5D=&miete%5Bbis%5D=&nebenkosten%5Bvon%5D=&nebenkosten%5Bbis%5D=&provision%5Bvon%5D=&provision%5Bbis%5D=&zimmer%5Bvon%5D=&zimmer%5Bbis%5D='

    DUMMY_CONFIG = """
    verbose: true
    urls:
      - https://immobilien.derstandard.at/suche
    """

    def setUp(self):
        self.crawler = DerStandard(StringConfig(string=self.DUMMY_CONFIG))

    def test_url_pattern(self):
        """Test that the URL pattern matches derstandard.at URLs"""
        test_urls = [
            'https://immobilien.derstandard.at/suche',
            'https://immobilien.derstandard.at/detail/12345'
        ]
        for url in test_urls:
            self.assertIsNotNone(
                self.crawler.URL_PATTERN.search(url),
                f"URL pattern should match {url}"
            )

    def test_url_pattern_rejects_other_sites(self):
        """Test that the URL pattern does not match other sites"""
        test_urls = [
            'https://www.immobilienscout24.de/suche',
            'https://www.willhaben.at/suche',
            'https://derstandard.at/story/12345'  # Main site, not immobilien
        ]
        for url in test_urls:
            self.assertIsNone(
                self.crawler.URL_PATTERN.search(url),
                f"URL pattern should not match {url}"
            )

    @pytest.mark.skip(reason="Integration test - enable when testing with live site")
    def test_extract_data_live(self):
        """Integration test - fetches real data from derstandard.at"""
        soup = self.crawler.get_page(self.TEST_URL)
        self.assertIsNotNone(soup, "Should get a soup from the URL")

        entries = self.crawler.extract_data(soup)
        self.assertIsNotNone(entries, "Should parse entries from search URL")

        if len(entries) > 0:
            # Verify first entry has required fields
            self.assertTrue(entries[0]['id'] > 0, "ID should be parsed")
            self.assertTrue(
                entries[0]['url'].startswith("https://immobilien.derstandard.at"),
                "URL should start with BASE_URL"
            )

            # Verify all required fields exist (even if some are empty)
            for attr in ['title', 'url', 'id', 'crawler']:
                self.assertIn(attr, entries[0], f"{attr} should be present")
                if attr in ['title', 'url', 'crawler']:
                    self.assertTrue(entries[0][attr], f"{attr} should not be empty")

            # Optional fields should exist but can be empty
            for attr in ['price', 'size', 'rooms', 'address', 'image']:
                self.assertIn(attr, entries[0], f"{attr} should be present")

    def test_crawler_name(self):
        """Test that crawler returns correct name"""
        self.assertEqual(self.crawler.get_name(), "DerStandard")

    def test_extract_data_empty_soup(self):
        """Test that extract_data handles empty soup gracefully"""
        from bs4 import BeautifulSoup
        empty_soup = BeautifulSoup("", 'lxml')
        entries = self.crawler.extract_data(empty_soup)
        self.assertEqual(entries, [], "Should return empty list for empty soup")

    def test_extract_data_invalid_soup(self):
        """Test that extract_data handles invalid HTML gracefully"""
        from bs4 import BeautifulSoup
        invalid_soup = BeautifulSoup("<html><body><p>No listings here</p></body></html>", 'lxml')
        entries = self.crawler.extract_data(invalid_soup)
        self.assertEqual(entries, [], "Should return empty list for invalid HTML")


if __name__ == '__main__':
    unittest.main()
