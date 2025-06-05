from flask import Blueprint, jsonify, request, current_app
import requests
from datetime import datetime
import time

gps_bp = Blueprint('gps', __name__)

# Default coordinates (UNS Solo)
DEFAULT_LAT = -7.5594794
DEFAULT_LON = 110.856853464304

# Cache GPS data to prevent too frequent requests
last_gps_update = 0
cached_gps_data = {'lat': DEFAULT_LAT, 'lon': DEFAULT_LON, 'timestamp': 0}
GPS_CACHE_DURATION = 2  # seconds

# ESP32 IP configuration - must match app.py
ESP_IP = "192.168.255.173"  # Update to match app.py
GPS_ENDPOINT = f"http://{ESP_IP}/gps"

# Function to get latest valid GPS coordinates
def latest_gps():
    global last_gps_update, cached_gps_data
    
    current_time = time.time()
    
    # Return cached data if recent enough
    if current_time - last_gps_update < GPS_CACHE_DURATION:
        return cached_gps_data['lat'], cached_gps_data['lon']
    
    try:
        # Query ESP32 for GPS data
        print(f"📍 Fetching GPS data from: {GPS_ENDPOINT}")  # Add debug output
        response = requests.get(GPS_ENDPOINT, timeout=5)  # Increase timeout
        
        if response.ok:
            data = response.text
            print(f"📍 GPS response: {data}")  # Add debug output
            
            # Check if response is GPS_NOT_FIX
            if data == "GPS_NOT_FIX":
                print(f"⚠️ GPS reports no fix")
                return cached_gps_data['lat'], cached_gps_data['lon']
                
            # Check if the response contains comma (lat,lon format)
            if ',' in data:
                coords = data.split(',')
                if len(coords) == 2:
                    try:
                        lat = float(coords[0].strip())
                        lon = float(coords[1].strip())
                        
                        # Indonesia-specific reasonable bounds check
                        if (-11 <= lat <= 6) and (95 <= lon <= 141) and (lat != 0 and lon != 0):
                            # If coordinates are valid and different from previous, log it
                            if (abs(lat - cached_gps_data['lat']) > 0.0001 or 
                                abs(lon - cached_gps_data['lon']) > 0.0001):
                                
                                # New valid location found, try to log activity
                                try:
                                    with current_app.app_context():
                                        from app import log_activity
                                        log_activity('GPS Updated', f'New coordinates: {lat}, {lon}', 'gps')
                                except Exception as e:
                                    print(f"Could not log GPS activity: {e}")
                                
                                print(f"✅ Valid GPS data received: {lat}, {lon}")
                            
                            # Update cache with new coordinates
                            cached_gps_data = {
                                'lat': lat,
                                'lon': lon,
                                'timestamp': current_time
                            }
                            last_gps_update = current_time
                            return lat, lon  # Return the valid coordinates immediately
                    except Exception as e:
                        print(f"❌ Error parsing GPS data: {e}")
            
        else:
            # If failed to get response, use cache or default
            print(f"⚠️ Failed to get GPS data: {response.status_code}")
            
    except Exception as e:
        # If error occurs, use cache or default
        print(f"❌ GPS error: {e}")
    
    # Return the current cached data
    return cached_gps_data['lat'], cached_gps_data['lon']

@gps_bp.route('/gps')
def get_gps():
    lat, lon = latest_gps()
    
    # Check if the coordinates are exactly the default values (UNS coordinates)
    is_default = (lat == DEFAULT_LAT and lon == DEFAULT_LON)
    
    # Format coordinates to 6 decimal places for consistency
    return jsonify({
        'lat': round(lat, 6), 
        'lon': round(lon, 6),
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'is_default': is_default,
        'valid': not is_default,
        'status': 'GPS belum fix (menggunakan lokasi default)' if is_default else 'GPS valid'
    })

@gps_bp.route('/track')
def track():
    """Return a GeoJSON of the recent track"""
    # Function for a future feature to return track history
    return jsonify({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[110.829, -7.556]]  # Default position as placeholder
        }
    })
