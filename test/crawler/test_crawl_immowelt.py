import pytest

from flathunter.crawler.immowelt import Immowelt
from test.test_util import count
from test.utils.config import StringConfig

DUMMY_CONFIG = """
urls:
  - https://www.immowelt.de/classified-search?distributionTypes=Rent&estateTypes=House,Apartment&locations=AD08DE8634&order=Default&m=homepage_new_search_classified_search_result
    """

TEST_URL = 'https://www.immowelt.de/classified-search?distributionTypes=Rent&estateTypes=House,Apartment&locations=AD08DE8634&order=Default&m=homepage_new_search_classified_search_result'

@pytest.fixture
def crawler():
    return Immowelt(StringConfig(string=DUMMY_CONFIG))


def test_crawler(crawler):
    soup = crawler.get_page(TEST_URL)
    assert soup is not None
    entries = crawler.extract_data(soup)
    assert entries is not None
    assert len(entries) > 0
    assert entries[0]['id']
    assert entries[0]['url'].startswith("https://www.immowelt.de/expose")
    for attr in [ 'title', 'price', 'size', 'rooms', 'address' ]:
        assert entries[0][attr] is not None

def test_dont_crawl_other_urls(crawler):
    exposes = crawler.crawl("https://www.example.com")
    assert count(exposes) == 0

def test_process_expose_fetches_details(crawler):
    soup = crawler.get_page(TEST_URL)
    assert soup is not None
    entries = crawler.extract_data(soup)
    assert entries is not None
    assert len(entries) > 0
    updated_entries = [ crawler.get_expose_details(expose) for expose in entries ]
    for expose in updated_entries:
        print(expose)
        for attr in [ 'title', 'price', 'size', 'rooms', 'address', 'from' ]:
            assert expose[attr] is not None
