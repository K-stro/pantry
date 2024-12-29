import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import pandas as pd
import numpy as np
import json
import os
from pathlib import Path
import socketio
import queue
import threading
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2
import bcrypt
from twilio.rest import Client
import secrets
import random
from pantry_data import PantryDataManager
from diagnostic_report import DiagnosticReport
from password_reset import PasswordResetManager
import logging
from google_maps_integration import (
    init_google_maps, add_marker, center_map, 
    draw_route, clear_routes, add_heat_map
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize session state for map
if 'map_initialized' not in st.session_state:
    st.session_state.map_initialized = False

# Add IoT simulation class
class IoTSimulator:
    def __init__(self):
        self.last_update = datetime.now()
        self.update_interval = timedelta(seconds=30)

    def get_sensor_data(self):
        if datetime.now() - self.last_update >= self.update_interval:
            self.last_update = datetime.now()
            return {
                'temperature': random.uniform(18.0, 24.0),
                'humidity': random.uniform(40.0, 60.0),
                'door_status': random.choice(['closed', 'open']),
                'power_status': random.choice(['normal', 'backup']),
                'last_maintenance': (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat()
            }
        return None

# Create data directory if it doesn't exist
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)

# Function to calculate distance between two points using Haversine formula
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in kilometers

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c

    return distance

# Function to find nearest pantries
def find_nearest_pantries(user_lat, user_lon, pantries_df, max_distance=10):
    distances = []
    for _, pantry in pantries_df.iterrows():
        try:
            dist = calculate_distance(user_lat, user_lon, pantry['lat'], pantry['lon'])
            status = st.session_state.pantry_manager.get_pantry_status(pantry['name'])

            # Only add pantries within the max distance
            if dist <= max_distance:
                distances.append({
                    'name': pantry['name'],
                    'distance': dist,
                    'status': 'Open' if status and status['is_open'] else 'Closed',
                    'lat': pantry['lat'],
                    'lon': pantry['lon'],
                    'inventory_percentage': status['inventory_percentage'] if status else 0
                })
        except Exception as e:
            logger.error(f"Error processing pantry {pantry['name']}: {e}")
            continue

    return sorted(distances, key=lambda x: x['distance'])

# Function to load data from local storage
def load_local_data(filename, default_data):
    try:
        with open(data_dir / filename, 'r') as f:
            data = pd.DataFrame(json.load(f))
            # Convert date strings back to datetime objects if 'last_donation' column exists
            if 'last_donation' in data.columns:
                data['last_donation'] = pd.to_datetime(data['last_donation'])
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data

# Function to save data to local storage
def save_local_data(data, filename):
    # Convert DataFrame to records with timestamp handling
    if isinstance(data, pd.DataFrame):
        records = []
        for record in data.to_dict('records'):
            # Convert any Timestamp objects to ISO format strings
            processed_record = {}
            for key, value in record.items():
                if isinstance(value, pd.Timestamp):
                    processed_record[key] = value.isoformat()
                else:
                    processed_record[key] = value
            records.append(processed_record)
    else:
        records = data

    with open(data_dir / filename, 'w') as f:
        json.dump(records, f)

# Page configuration
st.set_page_config(
    page_title="Smart Community Pantry",
    page_icon="🥫",
    layout="wide"
)

# Initialize session state for offline mode
if 'is_online' not in st.session_state:
    st.session_state.is_online = True
if 'pending_updates' not in st.session_state:
    st.session_state.pending_updates = []

# Initialize session state for IoT simulation with local storage
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()

# Initialize IoT simulator in session state
if 'iot_simulator' not in st.session_state:
    st.session_state.iot_simulator = IoTSimulator()

# Initialize user management session state
if 'current_user' not in st.session_state:
    st.session_state.current_user = None
if 'users' not in st.session_state:
    st.session_state.users = pd.DataFrame(columns=[
        'username', 'password_hash', 'role', 'phone', 'email',
        'notifications_enabled', 'preferred_pantry', 'created_at',
        'privacy_settings', 'profile_visibility', 'contact_sharing',
        'activity_visibility', 'data_sharing'
    ])
    save_local_data(st.session_state.users, 'users.json')

if 'password_reset_manager' not in st.session_state:
    st.session_state.password_reset_manager = PasswordResetManager()
if 'password_reset_stage' not in st.session_state:
    st.session_state.password_reset_stage = 'initial'
if 'reset_email' not in st.session_state:
    st.session_state.reset_email = None


# Update the inventory data structure
default_inventory = pd.DataFrame({
    'item_id': range(1, 11),
    'name': ['Rice', 'Beans', 'Pasta', 'Canned Soup', 'Cereal', 
             'Fresh Vegetables', 'Bread', 'Milk', 'Baby Formula', 'Personal Hygiene Kit'],
    'category': ['Grains', 'Proteins', 'Grains', 'Canned Goods', 'Breakfast', 
                'Produce', 'Bakery', 'Dairy', 'Baby Care', 'Hygiene'],
    'quantity': [100, 80, 120, 50, 75, 30, 45, 60, 25, 40],
    'capacity': [150, 100, 150, 100, 100, 50, 60, 80, 40, 60],
    'min_threshold': [30, 20, 30, 20, 25, 10, 15, 20, 10, 15],
    'expiry_date': [(datetime.now() + timedelta(days=x)).isoformat() for x in [365, 365, 365, 730, 180, 7, 3, 14, 180, 365]],
    'temperature': [20.0] * 10,
    'humidity': [45.0] * 10,
    'storage_condition': ['room_temp', 'room_temp', 'room_temp', 'room_temp', 'room_temp',
                         'refrigerated', 'room_temp', 'refrigerated', 'room_temp', 'room_temp']
})

# Load inventory from local storage or use default
if 'inventory' not in st.session_state:
    try:
        loaded_inventory = load_local_data('inventory.json', default_inventory)
        # Ensure all required columns are present
        for col in default_inventory.columns:
            if col not in loaded_inventory.columns:
                loaded_inventory[col] = default_inventory[col]
        st.session_state.inventory = loaded_inventory
    except Exception as e:
        st.error(f"Error loading inventory: {e}")
        st.session_state.inventory = default_inventory

# Initialize PantryDataManager in session state
if 'pantry_manager' not in st.session_state:
    st.session_state.pantry_manager = PantryDataManager()

# Update the pantry locations section
st.session_state.pantry_locations = st.session_state.pantry_manager.get_all_locations()

# Default donor data
default_donors = pd.DataFrame({
    'donor_id': range(1, 8),
    'name': ['John Smith', 'Sarah Johnson', 'Bay Area Foods Co.', 'Community Kitchen', 
            'Local Grocery Store', 'Michael Chang', 'Emma Wilson'],
    'total_donations': [1500, 850, 3200, 2100, 1800, 650, 950],
    'donation_frequency': [12, 8, 24, 15, 20, 5, 9],
    'last_donation': pd.date_range(end=datetime.now(), periods=7, freq='D'),
    'badge_level': ['Gold', 'Silver', 'Platinum', 'Gold', 'Gold', 'Bronze', 'Silver']
})

# Load donors from local storage or use default
if 'donors' not in st.session_state:
    st.session_state.donors = load_local_data('donors.json', default_donors)

# Connection status in sidebar
with st.sidebar:
    st.header("Connection Status")
    connection_status = "🟢 Online" if st.session_state.is_online else "🔴 Offline"
    st.markdown(f"### {connection_status}")

    if not st.session_state.is_online:
        st.warning("⚠️ Working in Offline Mode")
        if st.session_state.pending_updates:
            st.info(f"📝 {len(st.session_state.pending_updates)} updates pending sync")

    # Simulate connection toggle (for testing)
    if st.button("Toggle Connection (Test)"):
        st.session_state.is_online = not st.session_state.is_online
        st.rerun()

    # Force sync when online
    if st.session_state.is_online and st.session_state.pending_updates and st.button("Sync Pending Updates"):
        try:
            # Here you would implement the actual sync logic
            save_local_data(st.session_state.inventory, 'inventory.json')
            save_local_data(st.session_state.pantry_locations, 'pantry_locations.json')
            save_local_data(st.session_state.donors, 'donors.json')
            st.session_state.pending_updates = []
            st.success("✅ All updates synchronized!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Sync failed: {str(e)}")

    if st.session_state.current_user:
        st.markdown(f"### 👤 Welcome, {st.session_state.current_user['username']}")
        if st.button("Logout"):
            st.session_state.current_user = None
            st.rerun()


# Header
st.title("🥫 Smart Community Pantry Management")

# Initialize chat history in session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'chat_queue' not in st.session_state:
    st.session_state.chat_queue = queue.Queue()
if 'last_message_time' not in st.session_state:
    st.session_state.last_message_time = datetime.now()


# Create tabs for different views
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📍 Pantry Map", "📊 Inventory Status", "📈 Historical Trends", 
    "🏆 Donor Leaderboard", "💬 Community Chat", "🎯 Resource Matching",
    "👤 User Management", "🔧 System Diagnostics"
])

with tab1:
    st.subheader("Community Pantry Locations")
    # Placeholder for Google Map integration in future update.
    st.write("Google Map will be displayed here.")


with tab2:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Inventory Status")

        # Group items by category
        categories = st.session_state.inventory['category'].unique()
        for category in categories:
            st.markdown(f"### {category}")
            category_items = st.session_state.inventory[
                st.session_state.inventory['category'] == category
            ]

            for _, item in category_items.iterrows():
                with st.container():
                    progress = item['quantity'] / item['capacity'] * 100
                    col_a, col_b, col_c = st.columns([3, 1, 1])

                    with col_a:
                        st.markdown(f"**{item['name']}**")
                        st.progress(progress / 100)

                    with col_b:
                        st.metric("Quantity", f"{item['quantity']}/{item['capacity']}")

                    with col_c:
                        expiry = pd.to_datetime(item['expiry_date'])
                        days_until_expiry = (expiry - pd.Timestamp.now()).days
                        st.metric("Expires In", f"{days_until_expiry} days")

                    sensor_col1, sensor_col2, sensor_col3 = st.columns(3)
                    with sensor_col1:
                        temp_status = "🟢" if 18 <= item['temperature'] <= 24 else "🔴"
                        st.metric(f"Temperature {temp_status}", f"{item['temperature']:.1f}°C")
                    with sensor_col2:
                        humidity_status = "🟢" if 40 <= item['humidity'] <= 60 else "🔴"
                        st.metric(f"Humidity {humidity_status}", f"{item['humidity']:.1f}%")
                    with sensor_col3:
                        st.metric("Storage", item['storage_condition'].replace('_', ' ').title())

    with col2:
        st.subheader("Alerts & Notifications")

        # System Status
        sensor_data = st.session_state.iot_simulator.get_sensor_data()
        if sensor_data:
            st.markdown("### 🔌 System Status")
            st.markdown(f"Power: {'🟢' if sensor_data['power_status'] == 'normal' else '🔴'} {sensor_data['power_status'].title()}")
            st.markdown(f"Door: {'🟢' if sensor_data['door_status'] == 'closed' else '🔴'} {sensor_data['door_status'].title()}")
            st.markdown(f"Last Maintenance: {pd.to_datetime(sensor_data['last_maintenance']).strftime('%Y-%m-%d')}")
            st.markdown("---")

        # Alerts
        alert_count = 0
        for _, item in st.session_state.inventory.iterrows():
            # Low stock alert
            if item['quantity'] <= item['min_threshold']:
                st.error(f"⚠️ Low Stock Alert: {item['name']} is below minimum threshold ({item['quantity']} units remaining)")
                alert_count += 1

            # Temperature alert
            if item['storage_condition'] == 'room_temp' and (item['temperature'] < 18 or item['temperature'] > 24):
                st.error(f"🌡️ Temperature Alert: {item['name']} storage temperature is outside safe range ({item['temperature']:.1f}°C)")
                alert_count += 1
            elif item['storage_condition'] == 'refrigerated' and (item['temperature'] < 2 or item['temperature'] > 6):
                st.error(f"❄️ Refrigeration Alert: {item['name']} temperature is outside safe range ({item['temperature']:.1f}°C)")
                alert_count += 1

            # Humidity alert
            if item['humidity'] < 40 or item['humidity'] > 60:
                st.warning(f"💧 Humidity Alert: {item['name']} storage humidity is outside safe range ({item['humidity']:.1f}%)")
                alert_count += 1

            # Expiry alert
            expiry = pd.to_datetime(item['expiry_date'])
            days_until_expiry = (expiry - pd.Timestamp.now()).days
            if days_until_expiry <= 7:
                st.error(f"📅 Expiry Alert: {item['name']} will expire in {days_until_expiry} days")
                alert_count += 1

        if alert_count == 0:
            st.success("✅ All systems normal. No alerts at this time.")

with tab3:
    st.subheader("Inventory Trends")
    dates = pd.date_range(start='2024-01-01', end=datetime.now(), freq='D')
    historical_data = pd.DataFrame({
        'date': dates,
        'rice_qty': 100 + np.random.normal(0, 10, len(dates)),
        'beans_qty': 80 + np.random.normal(0, 8, len(dates)),
        'pasta_qty': 120 + np.random.normal(0, 12, len(dates))
    })

    fig = go.Figure()
    for item in ['rice_qty', 'beans_qty', 'pasta_qty']:
        fig.add_trace(go.Scatter(
            x=historical_data['date'],
            y=historical_data[item],
            name=item.replace('_qty', '').title(),
            mode='lines'
        ))

    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis_title="Date",
        yaxis_title="Quantity",
        legend_title="Items"
    )
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("🏆 Community Donor Leaderboard")

    # Social Impact Summary Card
    st.markdown("""
    <div style='padding: 1rem; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 1rem;'>
        <h3 style='text-align: center;'>🌟 Community Impact</h3>
        <p style='text-align: center; font-size: 1.2em;'>Together, we've made a difference!</p>
    </div>
    """, unsafe_allow_html=True)

    impact_col1, impact_col2, impact_col3 = st.columns(3)
    with impact_col1:
        total_donations = st.session_state.donors['total_donations'].sum()
        st.metric("Total Items Donated", f"{total_donations:,}")
    with impact_col2:
        total_donors = len(st.session_state.donors)
        st.metric("Active Donors", str(total_donors))
    with impact_col3:
        avg_donation = int(st.session_state.donors['total_donations'].mean())
        st.metric("Average Donation Size", str(avg_donation))

    # Social Sharing Section
    st.markdown("### 📱 Share Our Impact")
    share_col1, share_col2, share_col3 = st.columns(3)

    with share_col1:
        twitter_text = f"🎉 Our community has donated {total_donations:,} items to help fight food insecurity! Join us in making a difference! #CommunityPantry #FoodSecurity"
        twitter_url = f"https://twitter.com/intent/tweet?text={twitter_text}"
        st.markdown(f"[![Tweet](https://img.shields.io/twitter/url?style=social&url=https%3A%2F%2Fgithub.com)]({twitter_url})")

    with share_col2:
        linkedin_text = f"Our community has donated {total_donations:,} items to help fight food insecurity. Join us in making a difference!"
        linkedin_url = f"https://www.linkedin.com/sharing/share-offsite/?url=https://community-pantry.org&title=Community Impact&summary={linkedin_text}"
        st.markdown("[![Share on LinkedIn](https://img.shields.io/badge/Share-LinkedIn-blue)](" + linkedin_url + ")")

    with share_col3:
        fb_text = f"Join our community in fighting food insecurity! We've donated {total_donations:,} items so far!"
        fb_url = f"https://www.facebook.com/sharer/sharer.php?u=https://community-pantry.org&quote={fb_text}"
        st.markdown("[![Share on Facebook](https://img.shields.io/badge/Share-Facebook-blue)](" + fb_url + ")")

    st.markdown("---")

    st.markdown("""
    ### Recognition Badges
    - 🏆 **Platinum**: Outstanding community contributors (3000+ items donated)
    - 🥇 **Gold**: Major contributors (1500+ items donated)
    - 🥈 **Silver**: Regular contributors (750+ items donated)
    - 🥉 **Bronze**: Rising contributors (500+ items donated)
    """)

    sorted_donors = st.session_state.donors.sort_values('total_donations', ascending=False)

    st.markdown("### Top Contributors")
    for idx, donor in sorted_donors.iterrows():
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            badge_emoji = {
                'Platinum': '🏆',
                'Gold': '🥇',
                'Silver': '🥈',
                'Bronze': '🥉'
            }

            with col1:
                st.markdown(f"#### {badge_emoji[donor['badge_level']]} {donor['name']}")
                # Handle both datetime objects and strings
                donation_date = donor['last_donation']
                if isinstance(donation_date, str):
                    donation_date = pd.to_datetime(donation_date)
                st.caption(f"Last donation: {donation_date.strftime('%Y-%m-%d')}")

            with col2:
                st.metric("Total Donations", f"{donor['total_donations']} items")

            with col3:
                st.metric("Frequency", f"{donor['donation_frequency']} times")

            with col4:
                share_text = f"Congratulations to {donor['name']} for earning {badge_emoji[donor['badge_level']]} badge with {donor['total_donations']} donations! #CommunityHeroes"
                tweet_url = f"https://twitter.com/intent/tweet?text={share_text}"
                st.markdown(f"[🎉 Celebrate]({tweet_url})")

            st.markdown("---")

    # Monthly Statistics with Sharing
    st.subheader("📊 Monthly Impact")
    stats_text = f"This month, {len(st.session_state.donors)} donors contributed {st.session_state.donors['total_donations'].sum():,} items, averaging {int(st.session_state.donors['total_donations'].mean())} items per donation. Join us in making a difference!"

    stats_col1, stats_col2 = st.columns([3, 1])
    with stats_col1:
        st.info(stats_text)
    with stats_col2:
        share_url = f"https://twitter.com/intent/tweet?text={stats_text}"
        st.markdown(f"[📢 Share Monthly Impact]({share_url})")

with tab5:
    st.subheader("💬 Community Chat Support")

    # Chat interface container
    chat_container = st.container()

    # User input section
    st.markdown("---")
    message_col, send_col = st.columns([4, 1])

    with message_col:
        user_message = st.text_input("Type your message:", key="message_input", 
                                   placeholder="Ask a question or share updates...")

    with send_col:
        send_button = st.button("Send", use_container_width=True)

    # Display connection status for chat
    if not st.session_state.is_online:
        st.warning("📢 Chat is in offline mode. Messages will be sent when connection is restored.")

    # Process pending messages when online
    if st.session_state.is_online and not st.session_state.chat_queue.empty():
        with st.spinner("Syncing pending messages..."):
            while not st.session_state.chat_queue.empty():
                pending_msg = st.session_state.chat_queue.get()
                st.session_state.chat_history.append(pending_msg)

    # Handle new message
    if send_button and user_message:
        new_message = {
            'user': "You",
            'message': user_message,
            'timestamp': datetime.now(),
            'status': 'pending' if not st.session_state.is_online else 'sent'
        }

        if st.session_state.is_online:
            st.session_state.chat_history.append(new_message)
            # Here you would implement the actual message sending to a backend
        else:
            st.session_state.chat_queue.put(new_message)

        # Clear input
        st.session_state.message_input = ""

    # Display chat history
    with chat_container:
        for msg in st.session_state.chat_history:
            message_container = st.container()

            with message_container:
                cols = st.columns([1, 4])
                with cols[0]:
                    st.markdown(f"**{msg['user']}**")
                with cols[1]:
                    st.write(msg['message'])
                    status_emoji = "🕒" if msg['status'] == 'pending' else "✅"
                    st.caption(f"{msg['timestamp'].strftime('%H:%M')} {status_emoji}")

            st.markdown("---")

    # Simulated automated responses (for demo)
    if st.session_state.is_online and st.session_state.chat_history:
        last_msg = st.session_state.chat_history[-1]
        time_since_last = datetime.now() - st.session_state.last_message_time

        if last_msg['user'] == "You" and time_since_last > timedelta(seconds=2):
            auto_response = {
                'user': "Community Support",
                'message': "Thank you for your message! A community volunteer will respond shortly. In the meantime, you can check our FAQ section or browse available resources.",
                'timestamp': datetime.now(),
                'status': 'sent'
            }
            st.session_state.chat_history.append(auto_response)
            st.session_state.last_message_time = datetime.now()
            st.experimental_rerun()

with tab6:
    st.subheader("🎯 Resource Matching")

    try:
        if not st.session_state.map_initialized:
            st.info("Loading Google Maps...")
            if init_google_maps():
                st.session_state.map_initialized = True
                st.success("Map loaded successfully!")
                logger.info("Google Maps initialized successfully")
            else:
                st.error("Failed to load Google Maps. Please check if the API key is configured correctly.")
                logger.error("Failed to initialize Google Maps")
    except Exception as e:
        logger.error(f"Error during map initialization: {e}")
        st.error("An error occurred while loading the map. Please try refreshing the page.")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### Find Nearby Resources")
        user_location = st.text_input(
            "Enter your location (e.g., zip code or address)",
            placeholder="Enter your location..."
        )
        max_distance = st.slider("Maximum distance (km)", 1, 20, 5)

        # Demo coordinates for San Francisco neighborhoods
        demo_locations = {
            "Mission District": [37.7599, -122.4148],
            "Richmond": [37.7802, -122.4828],
            "Sunset": [37.7517, -122.4931],
            "SOMA": [37.7785, -122.4056],
            "Bayview": [37.7299, -122.3932]
        }

        selected_demo = st.selectbox(
            "Or select a demo location:", 
            [""] + list(demo_locations.keys())
        )

        if st.button("Find Nearby Pantries"):
            try:
                if selected_demo:
                    user_lat, user_lon = demo_locations[selected_demo]
                else:
                    # In a real implementation, you would use a geocoding service here
                    # For demo, we'll use Mission District coordinates as default
                    user_lat, user_lon = 37.7599, -122.4148

                logger.info(f"Finding pantries near: {user_lat}, {user_lon}")

                # Center map on user location
                center_map(user_lat, user_lon)

                # Add user marker
                add_marker(
                    user_lat, user_lon,
                    "Your Location",
                    "<div>Your current location</div>",
                    "http://maps.google.com/mapfiles/ms/icons/blue-dot.png"
                )

                # Find and display nearby pantries
                nearest_pantries = find_nearest_pantries(
                    user_lat, user_lon,
                    st.session_state.pantry_locations,
                    max_distance
                )

                if nearest_pantries:
                    logger.info(f"Found {len(nearest_pantries)} nearby pantries")

                    # Clear any existing routes
                    clear_routes()

                    # Add pantry markers and routes
                    for pantry in nearest_pantries:
                        # Create info window content
                        info_content = f"""
                        <div style='width: 200px'>
                            <h4>{pantry['name']}</h4>
                            <p>Distance: {pantry['distance']:.1f} km</p>
                            <p>Status: {pantry['status']}</p>
                            <p>Inventory: {pantry.get('inventory_percentage', 0):.1f}% full</p>
                        </div>
                        """

                        # Add marker for each pantry
                        icon = "http://maps.google.com/mapfiles/ms/icons/green-dot.png" \
                               if pantry['status'] == 'Open' else \
                               "http://maps.google.com/mapfiles/ms/icons/red-dot.png"

                        add_marker(
                            pantry['lat'],
                            pantry['lon'],
                            pantry['name'],
                            info_content,
                            icon
                        )

                        # Draw route to pantry
                        draw_route(
                            user_lat, user_lon,
                            pantry['lat'], pantry['lon']
                        )

                    # Add heat map of pantry locations
                    locations = [(p['lat'], p['lon']) for p in nearest_pantries]
                    add_heat_map(locations)
                else:
                    st.warning("No pantries found within the specified distance.")
                    logger.warning(f"No pantries found within {max_distance}km of {user_lat}, {user_lon}")

            except Exception as e:
                logger.error(f"Error finding nearby pantries: {str(e)}")
                st.error("Error finding nearby pantries. Please try again.")

    with col2:
        if 'nearest_pantries' in locals() and nearest_pantries:
            st.markdown("### Nearest Pantries")
            for idx, pantry in enumerate(nearest_pantries, 1):
                with st.container():
                    st.markdown(f"#### {idx}. {pantry['name']}")
                    st.markdown(f"📍 Distance: {pantry['distance']:..1f} km")
                    status_icon = "🟢" if pantry['status'] == 'Open' else "🔴"
                    st.markdown(f"Status: {status_icon} {pantry['status']}")
                    st.progress(min(1.0, pantry.get('inventory_percentage', 0) / 100))
                    st.markdown("---")
        else:
            st.info("Enter your location to find nearby pantries and available resources.")

with tab7:
    if not st.session_state.current_user:
        st.subheader("👤 User Management")

        tab_login, tab_register = st.tabs(["Login", "Register"])

        with tab_login:
            st.markdown("### Login")
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Login"):
                    user_data = st.session_state.users[
                        st.session_state.users['username'] == login_username
                    ]

                    if not user_data.empty:
                        stored_hash = user_data.iloc[0]['password_hash']
                        if bcrypt.checkpw(login_password.encode('utf-8'), 
                                            stored_hash.encode('utf-8')):
                            st.session_state.current_user = user_data.iloc[0].to_dict()
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid password")
                    else:
                        st.error("User not found")

            with col2:
                if st.button("Forgot Password?"):
                    logger.info("User clicked Forgot Password button")
                    st.session_state.password_reset_stage = 'email_entry'
                    st.rerun()

            try:
                # Password Reset Flow
                if st.session_state.password_reset_stage == 'email_entry':
                    st.markdown("### Reset Password")
                    reset_email = st.text_input("Enter your email address", key="reset_email")

                    if st.button("Send Verification Code"):
                        logger.info(f"Attempting to send verification code to {reset_email}")
                        user_data = st.session_state.users[
                            st.session_state.users['email'] == reset_email
                        ]

                        if not user_data.empty:
                            # Generate and send verification code
                            code = st.session_state.password_reset_manager.generate_verification_code(reset_email)
                            if code and st.session_state.password_reset_manager.send_verification_email(reset_email, code):
                                st.session_state.password_reset_stage = 'verify_code'
                                st.session_state.reset_email = reset_email
                                st.success("Verification code sent! Please check your email.")
                                logger.info(f"Verification code sent successfully to {reset_email}")
                                st.rerun()
                            else:
                                st.error("Failed to send verification code. Please try again.")
                                logger.error(f"Failed to send verification code to {reset_email}")
                        else:
                            st.error("No account found with this email address")
                            logger.warning(f"No account found for email: {reset_email}")

                elif st.session_state.password_reset_stage == 'verify_code':
                    st.markdown("### Enter Verification Code")
                    verification_code = st.text_input("Enter the 6-digit code sent to your email", key="verification_code")

                    if st.button("Verify Code"):
                        logger.info(f"Attempting to verify code for {st.session_state.reset_email}")
                        if st.session_state.password_reset_manager.verify_code(st.session_state.reset_email, verification_code):
                            # Generate reset token
                            token = st.session_state.password_reset_manager.generate_reset_token(st.session_state.reset_email)
                            reset_url = f"http://{os.getenv('REPL_SLUG')}.{os.getenv('REPL_OWNER')}.repl.co/reset?token={token}"

                            if st.session_state.password_reset_manager.send_reset_email(st.session_state.reset_email, reset_url):
                                st.success("Password reset link has been sent to your email!")
                                logger.info(f"Reset link sent successfully to {st.session_state.reset_email}")
                                st.session_state.password_reset_stage = 'initial'
                                st.rerun()
                            else:
                                st.error("Failed to send reset email. Please try again.")
                                logger.error(f"Failed to send reset email to {st.session_state.reset_email}")
                        else:
                            st.error("Invalid or expired verification code")
                            logger.warning(f"Invalid verification code attempt for {st.session_state.reset_email}")

            except Exception as e:
                logger.error(f"Error in password reset flow: {str(e)}")
                st.error("An error occurred during the password reset process. Please try again.")
                st.session_state.password_reset_stage = 'initial'

    else:
        st.subheader("User Settings")

        user_data = st.session_state.users[
            st.session_state.users['username'] == st.session_state.current_user['username']
        ].iloc[0]

        tab1, tab2 = st.tabs(["Profile Information", "Privacy Settings"])

        with tab1:
            st.markdown("### Profile Information")
            st.markdown(f"**Role:** {user_data['role']}")
            st.markdown(f"**Email:** {user_data['email']}")
            st.markdown(f"**Phone:** {user_data['phone']}")

            if user_data['role'] == "Receiver":
                st.markdown("### Preferred Pantry")
                preferred_pantry = st.selectbox(
                    "Select your preferred pantry",
                    st.session_state.pantry_locations['name'].tolist(),
                    index=st.session_state.pantry_locations['name'].tolist().index(
                        user_data['preferred_pantry']
                    ) if user_data['preferred_pantry'] else 0
                )

        with tab2:
            st.markdown("### Privacy Controls")

            profile_visibility = st.selectbox(
                "Profile Visibility",
                ["Public", "Community Members Only", "Private"],
                index=["Public", "Community Members Only", "Private"].index(
                    user_data['profile_visibility']
                ) if 'profile_visibility' in user_data else 0
            )

            contact_sharing = st.multiselect(
                "Share Contact Information With:",
                ["Community Administrators", "Verified Donors", "All Community Members", "None"],
                default=user_data['contact_sharing'] if 'contact_sharing' in user_data else ["Community Administrators"]
            )

            activity_visibility = st.selectbox(
                "Activity History Visibility",
                ["Public", "Community Members Only", "Private"],
                index=["Public", "Community Members Only", "Private"].index(
                    user_data['activity_visibility']
                ) if 'activity_visibility' in user_data else 0
            )

            data_sharing = st.multiselect(
                "Share My Data For:",
                ["Community Statistics", "Impact Reports", "Resource Matching", "Research"],
                default=user_data['data_sharing'] if 'data_sharing' in user_data else ["Community Statistics", "Resource Matching"]
            )

            st.markdown("### Notification Settings")
            notifications = st.checkbox(
                "Enable notifications",
                value=user_data['notifications_enabled']
            )

            if notifications:
                st.checkbox("New donations in your area", value=True)
                st.checkbox("Resource availability updates", value=True)
                st.checkbox("Community events", value=True)

        if st.button("Save Changes"):
            # Update user preferences and privacy settings
            update_mask = st.session_state.users['username'] == user_data['username']
            st.session_state.users.loc[update_mask, 'notifications_enabled'] = notifications
            st.session_state.users.loc[update_mask, 'profile_visibility'] = profile_visibility
            st.session_state.users.loc[update_mask, 'contact_sharing'] = contact_sharing
            st.session_state.users.loc[update_mask, 'activity_visibility'] = activity_visibility
            st.session_state.users.loc[update_mask, 'data_sharing'] = data_sharing

            if user_data['role'] == "Receiver":
                st.session_state.users.loc[update_mask, 'preferred_pantry'] = preferred_pantry

            # Save to local storage
            save_local_data(st.session_state.users, 'users.json')
            st.success("Settings updated successfully!")

# Save chat history to local storage
if st.session_state.chat_history:
    save_local_data(pd.DataFrame(st.session_state.chat_history), 'chat_history.json')

# Save all data to local storage
save_local_data(st.session_state.users, 'users.json')
save_local_data(st.session_state.inventory, 'inventory.json')
save_local_data(st.session_state.pantry_locations, 'pantry_locations.json')
save_local_data(st.session_state.donors, 'donors.json')

with tab8:
    st.subheader("🔧 System Diagnostics")

    # Check if user is admin
    if st.session_state.current_user and st.session_state.current_user.get('role') == 'admin':
        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown("""
            ### System Diagnostic Report
            Generate a comprehensive system status report including:
            - Pantry locations status
            - Inventory levels
            - Critical items
            - System performance metrics
            """)

        with col2:
            if st.button("Generate Report", type="primary"):
                with st.spinner("Generating diagnostic report..."):
                    try:
                        report_generator = DiagnosticReport(
                            st.session_state.pantry_manager,
                            st.session_state.inventory
                        )
                        report_path = report_generator.generate_report()

                        if report_path and report_path.exists():
                            with open(report_path, "rb") as f:
                                st.download_button(
                                    label="📥 Download Report",
                                    data=f.read(),
                                    file_name=report_path.name,
                                    mime="application/pdf"
                                )
                            st.success("Report generated successfully!")
                        else:
                            st.error("Failed to generate report. Please check the logs.")
                    except Exception as e:
                        st.error(f"Error generating report: {e}")
    else:
        st.warning("⚠️ This section is only accessible to system administrators.")
        if not st.session_state.current_user:
            st.info("Please log in with an administrator account to access the diagnostics.")