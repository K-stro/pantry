import pandas as pd
from datetime import datetime, time
import json
from pathlib import Path
import logging

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PantryDataManager:
    def __init__(self):
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.pantry_file = self.data_dir / "pantry_locations.json"
        self.data = None
        self._initialize_data()

    def _initialize_data(self):
        """Initialize data structure with default values"""
        try:
            if self.pantry_file.exists():
                with open(self.pantry_file, 'r') as f:
                    data = json.load(f)
                    if self._validate_data_structure(data):
                        self.data = data
                        logger.info("Successfully loaded pantry data from file")
                    else:
                        logger.error("Invalid data structure in pantry locations file")
                        self._create_default_data()
            else:
                logger.info("No existing pantry data file found, creating default data")
                self._create_default_data()
        except Exception as e:
            logger.error(f"Error initializing pantry data: {e}", exc_info=True)
            self._create_default_data()

    def _validate_data_structure(self, data):
        """Validate the data structure"""
        try:
            if not isinstance(data, dict):
                return False
            if "locations" not in data or not isinstance(data["locations"], list):
                return False
            if "service_descriptions" not in data or not isinstance(data["service_descriptions"], dict):
                return False

            # Validate each location entry
            for location in data["locations"]:
                required_fields = ["name", "address", "lat", "lon", "operating_hours", 
                                 "services", "capacity", "current_inventory"]
                if not all(field in location for field in required_fields):
                    return False

            return True
        except Exception as e:
            logger.error(f"Error validating data structure: {e}")
            return False

    def _create_default_data(self):
        """Create default data structure with sample pantry locations"""
        logger.info("Creating default pantry data structure")
        self.data = {
            "locations": [
                {
                    "name": "Mission District Food Pantry",
                    "address": "2111 Mission St, San Francisco, CA 94110",
                    "lat": 37.7629,
                    "lon": -122.4194,
                    "operating_hours": {
                        "monday": {"open": "9:00", "close": "17:00"},
                        "wednesday": {"open": "9:00", "close": "17:00"},
                        "friday": {"open": "9:00", "close": "17:00"}
                    },
                    "services": ["food_distribution", "nutrition_education"],
                    "capacity": 1000,
                    "current_inventory": 750
                },
                {
                    "name": "Richmond District Community Pantry",
                    "address": "375 7th Ave, San Francisco, CA 94118",
                    "lat": 37.7833,
                    "lon": -122.4667,
                    "operating_hours": {
                        "tuesday": {"open": "10:00", "close": "18:00"},
                        "thursday": {"open": "10:00", "close": "18:00"},
                        "saturday": {"open": "9:00", "close": "14:00"}
                    },
                    "services": ["food_distribution", "mobile_pantry"],
                    "capacity": 800,
                    "current_inventory": 600
                }
            ],
            "service_descriptions": {
                "food_distribution": "Regular food distribution to community members",
                "nutrition_education": "Nutrition and cooking education programs",
                "mobile_pantry": "Mobile food distribution service",
                "snap_assistance": "SNAP benefits application assistance"
            }
        }
        self.save_data()
        logger.info("Default pantry data created and saved")

    def save_data(self):
        """Save pantry data to file"""
        try:
            with open(self.pantry_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            logger.info("Pantry data saved successfully")
        except Exception as e:
            logger.error(f"Error saving pantry data: {e}", exc_info=True)

    def get_all_locations(self):
        """Return all pantry locations as a DataFrame"""
        try:
            if self.data and "locations" in self.data:
                return pd.DataFrame(self.data["locations"])
            logger.warning("No pantry locations data available")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error retrieving pantry locations: {e}", exc_info=True)
            return pd.DataFrame()

    def get_pantry_status(self, pantry_name):
        """Get current status of a specific pantry"""
        try:
            if not self.data or "locations" not in self.data:
                return None

            pantry = next((p for p in self.data["locations"] if p["name"] == pantry_name), None)
            if not pantry:
                return None

            return {
                "is_open": self.is_pantry_open(pantry_name),
                "current_inventory": pantry["current_inventory"],
                "capacity": pantry["capacity"],
                "inventory_percentage": (pantry["current_inventory"] / pantry["capacity"]) * 100,
                "services": pantry["services"]
            }
        except Exception as e:
            logger.error(f"Error getting pantry status: {e}", exc_info=True)
            return None

    def is_pantry_open(self, pantry_name, current_time=None):
        """Check if a pantry is currently open"""
        try:
            if current_time is None:
                current_time = datetime.now()

            if not self.data or "locations" not in self.data:
                return False

            pantry = next((p for p in self.data["locations"] if p["name"] == pantry_name), None)
            if not pantry or "operating_hours" not in pantry:
                return False

            day = current_time.strftime('%A').lower()
            if day not in pantry["operating_hours"]:
                return False

            hours = pantry["operating_hours"][day]
            current_time = current_time.time()
            open_time = datetime.strptime(hours["open"], "%H:%M").time()
            close_time = datetime.strptime(hours["close"], "%H:%M").time()

            return open_time <= current_time <= close_time
        except Exception as e:
            logger.error(f"Error checking pantry open status: {e}", exc_info=True)
            return False

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        from math import radians, sin, cos, sqrt, atan2

        R = 6371  # Earth's radius in kilometers

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c

    def get_nearby_locations(self, lat, lon, max_distance_km=10):
        if self.data is None or "locations" not in self.data:
            return pd.DataFrame()

        locations = pd.DataFrame(self.data["locations"])
        locations['distance'] = locations.apply(
            lambda row: self._calculate_distance(lat, lon, row['lat'], row['lon']),
            axis=1
        )
        return locations[locations['distance'] <= max_distance_km].sort_values('distance')

    def update_inventory(self, pantry_name, new_inventory):
        if self.data is None or "locations" not in self.data:
            return False

        for location in self.data["locations"]:
            if location["name"] == pantry_name:
                location["current_inventory"] = new_inventory
                self.save_data()
                return True
        return False

    def get_service_descriptions(self):
        """Get descriptions of available services"""
        try:
            if self.data is None:
                return {}
            return self.data.get("service_descriptions", {})
        except Exception as e:
            logger.error(f"Error getting service descriptions: {e}", exc_info=True)
            return {}