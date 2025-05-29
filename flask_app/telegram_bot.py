import requests
import logging
from datetime import datetime
from io import BytesIO
import time
import threading  # Import threading module

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Konfigurasi Bot
BOT_TOKEN = ''  # Ganti dengan token bot Anda
CHAT_ID = ''  # Ganti dengan chat ID tujuan
BASE_URL = f'https://api.telegram.org/bot{BOT_TOKEN}'

# Interval default
DEFAULT_INTERVAL = 300  # 5 menit (300 detik)
current_interval = DEFAULT_INTERVAL

# Tambahkan variabel untuk interval deteksi
last_detection_sent = 0
DETECTION_INTERVAL = 120  # 2 menit antara setiap notifikasi deteksi

# Tambahkan variabel untuk melacak waktu terakhir pengiriman lokasi
last_location_sent = 0

def send_telegram_alert(message, force=False):
    global last_detection_sent
    current_time = time.time()
    
    # Check interval kecuali jika force=True
    if not force and (current_time - last_detection_sent < DETECTION_INTERVAL):
        logger.info(f"⏳ Waiting for detection interval ({DETECTION_INTERVAL}s)")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': CHAT_ID, 
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, data=data)
        if response.ok:
            last_detection_sent = current_time
            logger.info(f"✅ Alert sent: {message}")
            return True
        else:
            logger.error(f"❌ Failed to send alert: {response.text}")
    except Exception as e:
        logger.error(f"❌ Telegram error: {e}")
    return False

def send_location_and_image(lat, lon, image_url=None):
    """Kirim lokasi dan gambar ke Telegram."""
    global last_location_sent
    current_time = time.time()
    
    # Periksa apakah sudah waktunya untuk mengirim update lokasi
    time_since_last = current_time - last_location_sent
    if time_since_last < current_interval:
        logger.info(f"⏳ Menunggu interval ({current_interval}s), sisa: {int(current_interval - time_since_last)}s")
        return False
        
    try:
        # Kirim lokasi
        location_url = f'{BASE_URL}/sendLocation'
        location_data = {
            'chat_id': CHAT_ID,
            'latitude': lat,
            'longitude': lon
        }
        location_response = requests.post(location_url, data=location_data)
        
        if not location_response.ok:
            logger.error(f"❌ Failed to send location: {location_response.text}")
            return False
            
        logger.info(f"✅ Location sent: {lat}, {lon}")

        # Kirim gambar jika tersedia
        if image_url:
            try:
                # Gunakan timeout yang lebih lama
                img_response = requests.get(image_url, timeout=10)
                
                if img_response.status_code == 200 and len(img_response.content) > 100:
                    files = {
                        'photo': ('snapshot.jpg', BytesIO(img_response.content), 'image/jpeg')
                    }
                    photo_url = f"{BASE_URL}/sendPhoto"
                    photo_data = {
                        'chat_id': CHAT_ID,
                        'caption': f"📸 Tangkapan Kamera\n📍 Lokasi: {lat}, {lon}\n⏰ Waktu: {time.strftime('%H:%M:%S')}"
                    }
                    photo_response = requests.post(photo_url, data=photo_data, files=files)
                    
                    if not photo_response.ok:
                        logger.error(f"❌ Failed to send photo: {photo_response.text}")
                        # Tetap return True karena lokasi berhasil dikirim
                    else:
                        logger.info("✅ Photo sent successfully")
                else:
                    logger.error(f"❌ Failed to get image from ESP32: Status {img_response.status_code}, Size: {len(img_response.content) if img_response.ok else 0} bytes")
            except Exception as e:
                logger.error(f"❌ Error getting or sending image: {str(e)}")
                # Tetap return True karena lokasi berhasil dikirim
                
        # Update waktu terakhir kirim lokasi
        last_location_sent = current_time
        logger.info(f"✅ Update sent at {time.strftime('%H:%M:%S')}. Next update in {current_interval} seconds.")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send Telegram update: {str(e)}")
        return False

def update_interval(new_interval):
    """Update interval pengiriman notifikasi."""
    global current_interval, last_location_sent
    try:
        new_interval = int(new_interval)
        if new_interval < 60:  # Minimal 1 menit
            new_interval = 60
        current_interval = new_interval
        
        # Reset last_location_sent agar interval baru berlaku segera
        last_location_sent = 0
        
        logger.info(f"Interval diperbarui: {new_interval} detik")
        return True
    except ValueError:
        logger.error("Interval tidak valid")
        return False

def get_current_interval():
    """Dapatkan interval saat ini."""
    return current_interval

def update_intervals(location_interval, detection_interval):
    """Update kedua interval sekaligus."""
    global current_interval, DETECTION_INTERVAL, last_location_sent
    
    try:
        # Validasi interval lokasi
        location_interval = int(location_interval)
        if location_interval < 60:  # Minimal 1 menit
            location_interval = 60
            
        # Validasi interval deteksi
        detection_interval = int(detection_interval)
        if detection_interval < 10:  # Minimal 10 detik
            detection_interval = 10
            
        # Update interval
        current_interval = location_interval
        DETECTION_INTERVAL = detection_interval
        
        # Reset last_location_sent agar interval baru berlaku segera
        last_location_sent = 0
        last_detection_sent = 0
        
        logger.info(f"✅ Intervals updated - Location: {location_interval}s, Detection: {detection_interval}s")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update intervals: {str(e)}")
        return False
