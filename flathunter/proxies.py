""" Gets proxies """
import requests
from lxml.html import fromstring

def get_proxies():
    """
    Gets random, free proxies
    """
    url = "https://free-proxy-list.net/"
    response = requests.get(url, timeout=30)
    parser = fromstring(response.text)
    proxies = set()
    for i in parser.xpath('//tbody/tr')[:250]:
        if i.xpath('.//td[7][contains(text(),"yes")]'):
            # Grabbing IP and corresponding PORT
            proxy = ":".join([i.xpath('.//td[1]/text()')[0], i.xpath('.//td[2]/text()')[0]])
            proxies.add(proxy)
    return proxies
