import streamlit as st
from streamlit_js_eval import streamlit_js_eval
import json
import logging
import os
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def init_google_maps():
    """Initialize Google Maps JavaScript code"""
    try:
        # Try to get API key from secrets or environment variable
        api_key = st.secrets.get("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            st.error("Google Maps API key not found. Please configure it in .streamlit/secrets.toml")
            logger.error("Google Maps API key not configured")
            return False

        logger.info("Starting Google Maps initialization")

        # Inject required CSS
        st.markdown("""
        <style>
        #map {
            height: 400px;
            width: 100%;
            margin: 1rem 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        </style>
        """, unsafe_allow_html=True)

        # Create map container
        st.markdown('<div id="map"></div>', unsafe_allow_html=True)

        # Initialize map with JavaScript
        js_code = f"""
        if (typeof google === 'undefined') {{
            var script = document.createElement('script');
            script.src = 'https://maps.googleapis.com/maps/api/js?key={api_key}&libraries=places,visualization,geometry';
            script.onload = initMap;
            document.head.appendChild(script);
        }} else {{
            initMap();
        }}

        function initMap() {{
            try {{
                window.map = new google.maps.Map(document.getElementById('map'), {{
                    zoom: 13,
                    center: {{ lat: 37.7749, lng: -122.4194 }},
                    mapTypeControl: true,
                    streetViewControl: true,
                    fullscreenControl: true,
                    styles: [
                        {{
                            featureType: "poi",
                            elementType: "labels",
                            stylers: [{{ visibility: "off" }}]
                        }}
                    ]
                }});
                console.log("Map initialized successfully");
            }} catch (error) {{
                console.error("Error initializing map:", error);
                throw error;
            }}
        }}
        """

        # Use streamlit_js_eval to inject and execute the JavaScript
        logger.info("Injecting Google Maps JavaScript code")
        streamlit_js_eval(js_expressions=js_code)
        logger.info("Google Maps JavaScript code injected successfully")
        return True

    except Exception as e:
        logger.error(f"Error initializing Google Maps: {str(e)}", exc_info=True)
        st.error(f"Failed to initialize Google Maps: {str(e)}")
        return False

def add_marker(lat, lng, title, info=None, icon=None):
    """Add a marker to the map"""
    try:
        logger.info(f"Adding marker at {lat}, {lng}")
        marker_js = f"""
        try {{
            if (!window.map) {{
                console.error('Map not initialized');
                return;
            }}
            const marker = new google.maps.Marker({{
                position: {{ lat: {lat}, lng: {lng} }},
                map: window.map,
                title: "{title}",
                {f'icon: "{icon}",' if icon else ''}
                animation: google.maps.Animation.DROP
            }});
        """

        if info:
            info_content = json.dumps(info)
            marker_js += f"""
            const infoWindow = new google.maps.InfoWindow({{
                content: {info_content}
            }});
            marker.addListener("click", () => {{
                infoWindow.open({{
                    anchor: marker,
                    map: window.map
                }});
            }});
            """

        marker_js += "} catch (error) { console.error('Error adding marker:', error); }"
        streamlit_js_eval(js_expressions=marker_js)
        logger.info(f"Marker added successfully at {lat}, {lng}")
        return True
    except Exception as e:
        logger.error(f"Error adding marker: {str(e)}", exc_info=True)
        return False

def center_map(lat, lng, zoom=13):
    """Center the map on specific coordinates"""
    try:
        center_js = f"""
        try {{
            window.map.setCenter({{ lat: {lat}, lng: {lng} }});
            window.map.setZoom({zoom});
        }} catch (error) {{
            console.error('Error centering map:', error);
        }}
        """
        streamlit_js_eval(js_expressions=center_js)
        return True
    except Exception as e:
        logger.error(f"Error centering map: {e}")
        return False

def draw_route(origin_lat, origin_lng, dest_lat, dest_lng):
    """Draw a route between two points"""
    try:
        route_js = f"""
        try {{
            if (!window.directionsService) {{
                window.directionsService = new google.maps.DirectionsService();
            }}
            const directionsRenderer = new google.maps.DirectionsRenderer({{
                map: window.map,
                suppressMarkers: true,
                polylineOptions: {{
                    strokeColor: '#2196F3',
                    strokeWeight: 4
                }}
            }});

            const request = {{
                origin: {{ lat: {origin_lat}, lng: {origin_lng} }},
                destination: {{ lat: {dest_lat}, lng: {dest_lng} }},
                travelMode: google.maps.TravelMode.DRIVING
            }};

            window.directionsService.route(request, (response, status) => {{
                if (status === "OK") {{
                    directionsRenderer.setDirections(response);
                }} else {{
                    console.error('Directions request failed:', status);
                }}
            }});
        }} catch (error) {{
            console.error('Error drawing route:', error);
        }}
        """
        streamlit_js_eval(js_expressions=route_js)
        return True
    except Exception as e:
        logger.error(f"Error drawing route: {e}")
        return False

def clear_routes():
    """Clear all routes from the map"""
    try:
        clear_js = """
        try {
            if (window.map) {
                const directionsRenderer = new google.maps.DirectionsRenderer({
                    map: window.map
                });
                directionsRenderer.setMap(null);
            }
        } catch (error) {
            console.error('Error clearing routes:', error);
        }
        """
        streamlit_js_eval(js_expressions=clear_js)
        return True
    except Exception as e:
        logger.error(f"Error clearing routes: {e}")
        return False

def add_heat_map(locations, weights=None):
    """Add a heat map layer to the map"""
    try:
        locations_str = json.dumps([{"lat": lat, "lng": lng} for lat, lng in locations])
        heat_map_js = f"""
        try {{
            const heatmapData = {locations_str}.map(location => {{
                return new google.maps.LatLng(location.lat, location.lng);
            }});

            const heatmap = new google.maps.visualization.HeatmapLayer({{
                data: heatmapData,
                map: window.map,
                radius: 50,
                opacity: 0.6
            }});
        }} catch (error) {{
            console.error('Error creating heat map:', error);
        }}
        """
        streamlit_js_eval(js_expressions=heat_map_js)
        return True
    except Exception as e:
        logger.error(f"Error adding heat map: {e}")
        return False