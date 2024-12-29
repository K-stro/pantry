import trafilatura
import re
from typing import Optional, Dict
import requests
from bs4 import BeautifulSoup
import json

class PriceTracker:
    def __init__(self):
        self.price_patterns = [
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $XX.XX or $X,XXX.XX
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD',  # XX.XX USD
            r'Price:\s*\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # Price: $XX.XX
        ]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def _extract_price(self, text: str) -> Optional[float]:
        """Extract price from text using multiple patterns"""
        if not text:
            return None

        # Try each pattern
        for pattern in self.price_patterns:
            matches = re.search(pattern, text)
            if matches:
                try:
                    # Remove commas and convert to float
                    price_str = matches.group(1).replace(',', '')
                    return float(price_str)
                except (ValueError, IndexError):
                    continue
        return None

    def fetch_product_info(self, url: str) -> Optional[Dict]:
        """Fetch product information from the given URL"""
        try:
            # Download and extract content
            downloaded = trafilatura.fetch_url(url, headers=self.headers)
            if not downloaded:
                return None

            # Extract main content
            text_content = trafilatura.extract(downloaded)
            price = self._extract_price(text_content)

            if not price:
                # Try getting structured data
                response = requests.get(url, headers=self.headers)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Look for structured price data
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict):
                            if 'offers' in data and 'price' in data['offers']:
                                price = float(data['offers']['price'])
                                break
                    except (json.JSONDecodeError, ValueError):
                        continue

            if price:
                # Extract product name from meta tags or title
                name = None
                soup = BeautifulSoup(downloaded, 'html.parser')
                meta_title = soup.find('meta', property='og:title')
                if meta_title:
                    name = meta_title['content']
                else:
                    title = soup.find('title')
                    if title:
                        name = title.text.strip()

                if not name:
                    name = f"Product from {url}"

                return {
                    'name': name,
                    'price': price,
                    'url': url
                }
            return None

        except Exception as e:
            print(f"Error fetching product info: {e}")
            return None

    def get_current_price(self, url: str) -> Optional[float]:
        """Get the current price from the product URL"""
        try:
            product_info = self.fetch_product_info(url)
            return product_info['price'] if product_info else None
        except Exception as e:
            print(f"Error getting current price: {e}")
            return None