from flask import Blueprint, jsonify, request
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
ESP_IP = "192.168.175.173"
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
        response = requests.get(GPS_ENDPOINT, timeout=3)
        
        if response.ok:
            data = response.json()
            
            # Check if GPS has valid data (some reasonable bounds)
            lat = float(data.get('lat', DEFAULT_LAT))
            lon = float(data.get('lon', DEFAULT_LON))
            
            # Only update cache if values are reasonable and not defaults from ESP32
            # Indonesia-specific reasonable bounds check
            if (-11 <= lat <= 6) and (95 <= lon <= 141) and (lat != 0 and lon != 0):
                cached_gps_data = {
                    'lat': lat,
                    'lon': lon,
                    'timestamp': current_time
                }
                last_gps_update = current_time
                print(f"✅ Valid GPS data received: {lat}, {lon}")
            else:
                # Jika koordinat tidak valid, gunakan cache terakhir yang valid
                # atau nilai default jika tidak ada cache valid
                print(f"⚠️ Invalid GPS coordinates: {lat}, {lon} - Using last valid or default")
        else:
            # Jika gagal mendapatkan respons, gunakan cache terakhir atau default
            print(f"⚠️ Failed to get GPS data: {response.status_code}")
            
    except Exception as e:
        # Jika terjadi error, gunakan cache terakhir atau default
        print(f"❌ GPS error: {e}")
    
    # Return the current cached data (either updated or the last valid one)
    # Jika tidak ada data GPS yang valid, ini akan mengembalikan koordinat default
    return cached_gps_data['lat'], cached_gps_data['lon']

@gps_bp.route('/gps')
def get_gps():
    lat, lon = latest_gps()
    return jsonify({
        'lat': lat, 
        'lon': lon,
        'timestamp': datetime.now().strftime('%H:%M:%S')
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
