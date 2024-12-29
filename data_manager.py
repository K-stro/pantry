import pandas as pd
from datetime import datetime
import os

class DataManager:
    def __init__(self):
        self.products_file = 'products.csv'
        self.history_file = 'price_history.csv'
        self._initialize_storage()

    def _initialize_storage(self):
        """Initialize CSV files if they don't exist"""
        if not os.path.exists(self.products_file):
            pd.DataFrame(columns=[
                'name', 'url', 'current_price', 'alert_price', 'last_updated'
            ]).to_csv(self.products_file, index=False)

        if not os.path.exists(self.history_file):
            pd.DataFrame(columns=[
                'url', 'price', 'timestamp'
            ]).to_csv(self.history_file, index=False)

    def add_product(self, name: str, url: str, price: float, alert_price: float) -> bool:
        """Add a new product to track"""
        try:
            products = pd.read_csv(self.products_file)

            # Check if product already exists
            if url in products['url'].values:
                return False

            # Add new product
            new_product = pd.DataFrame([{
                'name': name,
                'url': url,
                'current_price': price,
                'alert_price': alert_price,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }])

            products = pd.concat([products, new_product], ignore_index=True)
            products.to_csv(self.products_file, index=False)

            # Add first price point to history
            self.update_price(url, price, datetime.now())
            return True
        except Exception as e:
            print(f"Error adding product: {e}")
            return False

    def delete_product(self, url: str) -> bool:
        """Delete a product and its price history"""
        try:
            # Remove from products file
            products = pd.read_csv(self.products_file)
            products = products[products['url'] != url]
            products.to_csv(self.products_file, index=False)

            # Remove from history file
            history = pd.read_csv(self.history_file)
            history = history[history['url'] != url]
            history.to_csv(self.history_file, index=False)
            return True
        except Exception as e:
            print(f"Error deleting product: {e}")
            return False

    def update_price(self, url: str, price: float, timestamp: datetime):
        """Update price for a product and record in history"""
        try:
            # Update current price
            products = pd.read_csv(self.products_file)
            products.loc[products['url'] == url, 'current_price'] = price
            products.loc[products['url'] == url, 'last_updated'] = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            products.to_csv(self.products_file, index=False)

            # Add to history
            history = pd.read_csv(self.history_file)
            new_record = pd.DataFrame([{
                'url': url,
                'price': price,
                'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
            }])
            history = pd.concat([history, new_record], ignore_index=True)
            history.to_csv(self.history_file, index=False)
            return True
        except Exception as e:
            print(f"Error updating price: {e}")
            return False

    def get_all_products(self) -> pd.DataFrame:
        """Get all tracked products"""
        try:
            return pd.read_csv(self.products_file)
        except Exception as e:
            print(f"Error getting products: {e}")
            return pd.DataFrame()

    def get_price_history(self, url: str) -> pd.DataFrame:
        """Get price history for a specific product"""
        try:
            history = pd.read_csv(self.history_file)
            product_history = history[history['url'] == url].copy()
            product_history['timestamp'] = pd.to_datetime(product_history['timestamp'])
            return product_history.sort_values('timestamp')
        except Exception as e:
            print(f"Error getting price history: {e}")
            return pd.DataFrame()