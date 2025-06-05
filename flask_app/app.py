from flask import Flask, render_template, request, jsonify, session, Response, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from models import db, User, ActivityLog
from auth import auth_bp
from yolo_infer import fetch_frame, detect_from_frame, get_gps_coordinates
from datetime import timedelta, datetime
import json
import requests
import threading

# YOLO + Kamera
import cv2
import time

# Telegram
from telegram_bot import (
    send_location_and_image, 
    update_interval,
    update_intervals,
    get_current_interval,
    force_send_now,
    set_default_gps_sending
)

# Global variables
ESP_IP = "192.168.255.173"  # Update to match gps_routes.py
last_status_check = datetime.now()
cached_status = None
STATUS_CACHE_DURATION = timedelta(minutes=2)
CONF_THRESHOLD = 0.5  # Default confidence threshold for detections
DEFAULT_LAT = -7.5594794
DEFAULT_LON = 110.856853464304

app = Flask(__name__)
app.config.update({
    'SECRET_KEY': 'ganti-dengan-rahasia-anda',  # Pastikan secret key yang kuat
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///../instance/kacamata.db',
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'PERMANENT_SESSION_LIFETIME': timedelta(minutes=30),
    'SESSION_COOKIE_SECURE': True,
    'SESSION_COOKIE_HTTPONLY': True,
    'SESSION_COOKIE_SAMESITE': 'Lax',
    'WTF_CSRF_ENABLED': True,  # Enable CSRF protection
    'WTF_CSRF_SECRET_KEY': 'csrf-key-yang-sangat-rahasia'  # Set CSRF secret key
})

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)
csrf = CSRFProtect()
csrf.init_app(app)  # Initialize CSRF protection setelah app dibuat

@login_manager.user_loader
def load_user(user_id):
    # Update to use Session.get() instead of Query.get()
    return db.session.get(User, int(user_id))

app.register_blueprint(auth_bp, url_prefix='/auth')

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='super-admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

@app.before_request
def before_request():
    if current_user.is_authenticated:
        session['last_active'] = datetime.utcnow()
    else:
        session.clear()

@app.route('/api/settings/connection', methods=['POST'])
@login_required
def update_connection_settings():
    try:
        update_interval = request.form.get('update_interval', type=int)
        if not 1 <= update_interval <= 60:
            return jsonify({'error': 'Invalid update interval'}), 400
        return jsonify({'message': 'Settings updated successfully'})
    except Exception as e:
        app.logger.error(f'Failed to update connection settings: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/settings/video', methods=['POST'])
@login_required
def update_video_settings():
    try:
        quality = request.form.get('quality', type=int)
        fps = request.form.get('fps', type=int)
        if quality not in [360, 480, 720]:
            return jsonify({'error': 'Invalid quality setting'}), 400
        if fps not in [15, 24, 30]:
            return jsonify({'error': 'Invalid fps setting'}), 400
        return jsonify({'message': 'Settings updated successfully'})
    except Exception as e:
        app.logger.error(f'Failed to update video settings: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/')
@login_required
def dashboard():
    lat = -7.556
    lon = 110.829
    return render_template('index.html', lat=lat, lon=lon)

@app.route('/history')
@login_required
def history():
    return render_template('history.html')

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

# ===== STREAM ROUTE =====
@app.route('/video_feed')
@login_required
def video_feed():
    def gen():
        retries = 0
        max_retries = 3
        
        while True:
            try:
                if retries >= max_retries:
                    print("⚠️ Maximum retries reached, waiting 5 seconds...")
                    time.sleep(5)
                    retries = 0
                    
                frame = fetch_frame()
                if frame is None:
                    retries += 1
                    time.sleep(1)
                    continue
                    
                # Pass app instance to detect_from_frame
                frame_with_detections = detect_from_frame(frame, app)
                retries = 0
                
                _, buffer = cv2.imencode('.jpg', frame_with_detections)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            except Exception as e:
                print(f"❌ Error in video feed: {str(e)}")
                retries += 1
                time.sleep(1)
    
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ===== END STREAM =====

@app.route('/gps')
def get_gps():
    lat, lon = get_gps_coordinates()
    
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

def periodic_telegram_update():
    while True:
        try:
            # Use the new GPS integration
            lat, lon = get_gps_coordinates()
            
            # Get image from ESP32 with cache-busting
            timestamp = int(time.time())
            image_url = f"http://{ESP_IP}/cam-hi.jpg?t={timestamp}"
            
            # Send location and image
            success = send_location_and_image(lat, lon, image_url)
            
            if success:
                print(f"✅ Telegram update sent at {datetime.now().strftime('%H:%M:%S')}")
                try:
                    with app.app_context():
                        log_activity('Lokasi Dikirim', f'Koordinat: {lat:.6f}, {lon:.6f}', 'telegram')
                except Exception as e:
                    print(f"❌ Error logging activity: {e}")
            else:
                # Show interval info
                interval = get_current_interval()
                print(f"⏳ Telegram update scheduled every {interval}s - Will send next update when interval elapses")
                
        except Exception as e:
            print(f"❌ Error in periodic Telegram update: {e}")
            
        # Sleep for 30 seconds before checking again
        time.sleep(30)

@app.route('/api/telegram-settings', methods=['POST'])
@login_required
def update_telegram_settings():
    try:
        data = request.get_json()
        interval = int(data.get('interval', 120))  # Default to 2 minutes
        allow_default_gps = data.get('allow_default_gps', True)
        
        # Update settings
        set_default_gps_sending(allow_default_gps)
        update_interval(interval)
        
        # Log the activity
        log_activity('Pengaturan Telegram', 
                    f'Interval: {interval}s, Allow Default GPS: {allow_default_gps}', 
                    'settings')
        
        return jsonify({'message': 'Settings updated successfully'})
    except Exception as e:
        print(f"Error updating telegram settings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/force-send', methods=['POST'])
@login_required
def force_telegram_send():
    try:
        # Force sending the notification immediately
        force_send_now()
        
        # Manually trigger a notification right now with current data
        lat, lon = get_gps_coordinates()
        
        # Get the latest high-quality image with cache busting
        timestamp = int(time.time())
        image_url = f"http://{ESP_IP}/cam-hi.jpg?t={timestamp}"
        
        print(f"Forcing telegram notification with image URL: {image_url}")
        
        # Check if using default GPS coordinates
        is_default = (lat == DEFAULT_LAT and lon == DEFAULT_LON)
        status = "Default Location (GPS belum fix)" if is_default else "Valid Location"
        
        # Create a thread to send the notification without blocking the response
        send_thread = threading.Thread(
            target=send_location_and_image,
            args=(lat, lon, image_url),
            daemon=True
        )
        send_thread.start()
        
        # Log activity
        log_activity('Telegram Notification', f'Manual send triggered: {lat:.6f}, {lon:.6f} ({status})', 'telegram')
        
        return jsonify({
            'message': 'Notification dengan teks, lokasi, dan gambar sedang dikirim',
            'coordinates': f'{lat:.6f}, {lon:.6f}',
            'status': status,
            'image_url': image_url,
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'includes': 'Text message + Location + Live camera image'
        })
    except Exception as e:
        print(f"Error forcing telegram send: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/device-status')
def device_status():
    global last_status_check, cached_status
    current_time = datetime.now()
    
    # Only request fresh data if cache is expired
    if cached_status is None or (current_time - last_status_check) > STATUS_CACHE_DURATION:
        try:
            # Get WiFi and system status from ESP32
            print(f"Fetching device status from http://{ESP_IP}/status")  # Add debug output
            wifi_response = requests.get(f"http://{ESP_IP}/status", timeout=5)  # Increase timeout
            if wifi_response.status_code == 200:
                esp_status = wifi_response.json()
                
                # Get GPS data
                lat, lon = latest_gps()
                has_gps = lat != -7.5594794 or lon != 110.856853464304
                
                # Update status data
                status_data = {
                    "wifi_status": "Connected" if esp_status.get('connected', False) else "Disconnected",
                    "rssi": esp_status.get('rssi', 0),
                    "gps_status": "Valid" if has_gps else "No Fix",
                    "last_sync": current_time.strftime("%H:%M:%S"),
                    "last_update": int(current_time.timestamp())
                }
                
                # Cache the new status
                cached_status = status_data
                last_status_check = current_time
                
                # Log status update for activity history
                log_activity('Device Status', f"WiFi: {status_data['wifi_status']}, GPS: {status_data['gps_status']}", 'system')
                
                print(f"Device status updated successfully: {status_data}")  # Add debug output
                return jsonify(status_data)
            else:
                print(f"Error response from ESP32: {wifi_response.status_code}")  # Add debug output
                
        except Exception as e:
            print(f"Error getting device status: {str(e)}")
            
    # If we get here, either there was an error or we're using cache
    if cached_status:
        return jsonify(cached_status)
        
    # Return default status if no cache available
    default_status = {
        "wifi_status": "Unknown",
        "rssi": 0,
        "gps_status": "Unknown",
        "last_sync": "Never",
        "last_update": int(current_time.timestamp())
    }
    
    return jsonify(default_status)

@app.route('/api/current-settings')
@login_required
def get_current_settings():
    try:
        response = requests.get(f"http://{ESP_IP}/settings", timeout=3)
        if response.status_code == 200:
            return jsonify(response.json())
    except Exception as e:
        print(f"Error getting settings: {e}")
    
    # Default settings if failed
    return jsonify({
        'update_interval': 3,
        'quality': 480,
        'fps': 30,
        'device_id': 'NETRACAM-01'
    })

def log_activity(title, details, type='info'):
    """Log an activity to the database for history tracking"""
    try:
        # Create a new activity log entry
        activity = ActivityLog(title=title, details=details, type=type)
        db.session.add(activity)
        db.session.commit()
        print(f"✅ Activity logged: {title} ({type})")
    except Exception as e:
        print(f"❌ Error logging activity: {e}")
        db.session.rollback()

@app.route('/api/activity-log')
@login_required
def get_activity_log():
    try:
        # Get filter parameter (today, week, month)
        time_filter = request.args.get('filter', 'today')
        
        # Calculate date range
        now = datetime.utcnow()
        if time_filter == 'week':
            since = now - timedelta(days=7)
        elif time_filter == 'month':
            since = now - timedelta(days=30)
        else:  # today
            since = now - timedelta(days=1)
            
        # Query activities
        activities = ActivityLog.query\
            .filter(ActivityLog.timestamp >= since)\
            .order_by(ActivityLog.timestamp.desc())\
            .limit(50)\
            .all()
            
        return jsonify([activity.to_dict() for activity in activities])
    except Exception as e:
        print(f"Error getting activity log: {e}")
        return jsonify([])

# Add start time tracking
app.start_time = datetime.now()

@app.route('/api/device-stats')
@login_required
def get_device_stats():
    try:
        # Get current device status
        status_response = requests.get(f"http://{request.host_url.rstrip('/')}/api/device-status", timeout=3)
        status = status_response.json() if status_response.ok else {}
        
        # Calculate uptime
        uptime = datetime.now() - app.start_time
        uptime_str = str(timedelta(seconds=int(uptime.total_seconds())))
        
        # Get detection count for last 24 hours
        detection_count = ActivityLog.query\
            .filter(ActivityLog.type == 'detection')\
            .filter(ActivityLog.timestamp >= datetime.now() - timedelta(days=1))\
            .count()
        
        # Get GPS update count
        gps_updates = ActivityLog.query\
            .filter(ActivityLog.type == 'gps')\
            .filter(ActivityLog.timestamp >= datetime.now() - timedelta(days=1))\
            .count()
            
        return jsonify({
            'uptime': uptime_str,
            'wifi_strength': f"{status.get('rssi', '--')} dBm",
            'gps_updates': f"{gps_updates} updates/24h",
            'detection_count': detection_count
        })
    except Exception as e:
        print(f"Error getting device stats: {e}")
        return jsonify({
            'uptime': '--',
            'wifi_strength': '--',
            'gps_updates': '--',
            'detection_count': 0
        })

@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    return jsonify({
        'camera': {
            'quality': 480,
            'fps': 30
        },
        'detection': {
            'confidence': 0.5,
            'alert_person': True,
            'alert_vehicle': True
        },
        'notifications': {
            'interval': 300,
            'detect': True,
            'location': True,
            'status': True
        }
    })

@app.route('/api/settings/camera', methods=['POST'])
@login_required
def update_camera_settings():
    try:
        quality = request.form.get('quality', type=int)
        fps = request.form.get('fps', type=int)
        
        # Update ESP32 camera settings
        response = requests.get(f"http://{ESP_IP}/cam-{'hi' if quality == 720 else 'mid' if quality == 480 else 'lo'}.jpg")
        
        if response.status_code == 200:
            log_activity('Camera Settings Updated', f'Quality: {quality}p, FPS: {fps}', 'settings')
            return jsonify({'message': 'Settings updated successfully'})
            
        return jsonify({'error': 'Failed to update camera'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings/detection', methods=['POST'])
@login_required
def update_detection_settings():
    try:
        confidence = float(request.form.get('confidence', type=int)) / 100
        alert_person = request.form.get('alert_person') == 'true'
        alert_vehicle = request.form.get('alert_vehicle') == 'true'
        
        # Update YOLO settings
        global CONF_THRESHOLD
        CONF_THRESHOLD = confidence
        
        log_activity('Detection Settings Updated', 
                    f'Confidence: {confidence}, Person: {alert_person}, Vehicle: {alert_vehicle}', 
                    'settings')
        return jsonify({'message': 'Detection settings updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings/notification', methods=['POST'])
@login_required
def update_notification_settings():
    try:
        telegram_interval = int(request.form.get('telegram_interval', 300))
        detection_interval = int(request.form.get('detection_interval', 60))
        
        print(f"Updating notification settings - Telegram: {telegram_interval}s, Detection: {detection_interval}s")
        
        # Update telegram intervals menggunakan fungsi dari telegram_bot.py
        if update_intervals(telegram_interval, detection_interval):
            log_activity('Pengaturan Notifikasi', 
                        f'Lokasi: {telegram_interval}s, Deteksi: {detection_interval}s', 
                        'settings')
            return jsonify({'message': 'Pengaturan berhasil diperbarui'})
        
        return jsonify({'error': 'Gagal memperbarui interval'}), 400
    except Exception as e:
        print(f"Error updating notification settings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/telegram-interval', methods=['POST'])
@login_required
def update_telegram_interval():
    try:
        data = request.get_json()
        interval = int(data.get('interval'))
        update_interval(interval)
        return jsonify({'message': 'Settings updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Start the Telegram update thread
update_thread = threading.Thread(target=periodic_telegram_update, daemon=True)
update_thread.start()

if __name__ == '__main__':
    app.run(debug=True)
