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
BOT_TOKEN = '7718703590:AAGcUryDq5evkLJ6dLiGfMiobACKMPO1csE'  # Ganti dengan token bot Anda
CHAT_ID = '1193580325'  # Ganti dengan chat ID tujuan
BASE_URL = f'https://api.telegram.org/bot{BOT_TOKEN}'

# Interval default
DEFAULT_INTERVAL = 120  # 2 menit (120 detik)
current_interval = DEFAULT_INTERVAL

# Tambahkan variabel untuk interval deteksi
last_detection_sent = 0
DETECTION_INTERVAL = 120  # 2 menit antara setiap notifikasi deteksi

# Tambahkan variabel untuk melacak waktu terakhir pengiriman lokasi
last_location_sent = 0

# Pengaturan untuk mengizinkan pengiriman GPS default
ALLOW_DEFAULT_GPS = True  # Set True untuk selalu mengirim notifikasi terlepas dari status GPS

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
    
    # Set last_location_sent at the beginning to prevent concurrent sends
    last_location_sent = current_time
    
    # Cek apakah koordinat default (misalnya dari UNS)
    is_default_gps = lat == -7.5594794 and lon == 110.856853464304
    
    # Jika koordinat default dan pengaturan tidak mengizinkan pengiriman default, skip
    if is_default_gps and not ALLOW_DEFAULT_GPS:
        logger.info("⚠️ Koordinat default terdeteksi, update dilewati")
        return False
        
    try:
        # Format timestamp untuk lebih mudah dibaca
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        
        # Tentukan status GPS
        gps_status = "📍 GPS Valid" if not is_default_gps else "⚠️ GPS Belum Fix (Lokasi Default)"
        
        # Buat pesan teks informasi
        location_text = f"""🔍 <b>NETRACAM UPDATE</b>

📅 <b>Waktu:</b> {timestamp}
{gps_status}
🌐 <b>Koordinat:</b> {lat:.6f}, {lon:.6f}
📡 <b>Interval:</b> {current_interval} detik

{'🏢 Menggunakan koordinat Universitas Sebelas Maret' if is_default_gps else '✅ Lokasi real-time dari GPS'}"""

        # Kirim pesan teks terlebih dahulu
        text_url = f'{BASE_URL}/sendMessage'
        text_data = {
            'chat_id': CHAT_ID,
            'text': location_text,
            'parse_mode': 'HTML'
        }
        
        text_response = requests.post(text_url, data=text_data)
        if not text_response.ok:
            logger.error(f"❌ Failed to send text message: {text_response.text}")
        else:
            logger.info("✅ Text message sent")
        
        # Kirim lokasi (tanpa teks tambahan)
        location_url = f'{BASE_URL}/sendLocation'
        location_data = {
            'chat_id': CHAT_ID,
            'latitude': lat,
            'longitude': lon
        }
        
        # Kirim lokasi ke Telegram
        location_response = requests.post(location_url, data=location_data)
        if not location_response.ok:
            logger.error(f"❌ Failed to send location: {location_response.text}")
            return False
            
        logger.info(f"✅ Location sent: {lat}, {lon}")

        # Kirim gambar jika tersedia
        if image_url:
            try:
                # Add cache-busting parameter to URL
                cache_buster = int(time.time())
                if '?' in image_url:
                    img_url_with_cache = f"{image_url}&_cb={cache_buster}"
                else:
                    img_url_with_cache = f"{image_url}?_cb={cache_buster}"
                
                # Log the URL we're fetching from
                logger.info(f"📸 Fetching image from: {img_url_with_cache}")
                
                # Add headers to avoid caching issues
                headers = {
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
                
                # Fetch the image with longer timeout
                img_response = requests.get(img_url_with_cache, timeout=10, headers=headers)
                
                # Log response details
                logger.info(f"📊 Image response status: {img_response.status_code}, size: {len(img_response.content) if img_response.ok else 0} bytes")
                
                if img_response.status_code == 200 and len(img_response.content) > 1000:
                    # Create BytesIO object
                    image_bytes = BytesIO(img_response.content)
                    
                    files = {
                        'photo': ('snapshot.jpg', image_bytes, 'image/jpeg')
                    }
                    photo_url = f"{BASE_URL}/sendPhoto"
                    
                    # Caption dengan informasi detail
                    photo_caption = f"📷 Live Camera Feed\n🕐 {timestamp}\n📍 {gps_status.replace('📍 ', '').replace('⚠️ ', '')}"
                    
                    photo_data = {
                        'chat_id': CHAT_ID,
                        'caption': photo_caption
                    }
                    
                    # Send photo to Telegram
                    photo_response = requests.post(photo_url, data=photo_data, files=files, timeout=15)
                    
                    if not photo_response.ok:
                        logger.error(f"❌ Failed to send photo")
                    else:
                        logger.info("✅ Photo sent successfully")
                else:
                    logger.error(f"❌ Invalid image from ESP32")
            except Exception as e:
                logger.error(f"❌ Error getting or sending image: {str(e)}")
                
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send Telegram update: {str(e)}")
        # We don't reset last_location_sent on error to prevent constant retries
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
        
        logger.info(f"✅ Interval diperbarui: {new_interval} detik")
        return True
    except ValueError:
        logger.error("❌ Interval tidak valid")
        return False

def set_default_gps_sending(allow):
    """Mengatur apakah akan mengirim koordinat default atau tidak."""
    global ALLOW_DEFAULT_GPS
    ALLOW_DEFAULT_GPS = bool(allow)
    logger.info(f"✅ Allow default GPS sending set to: {ALLOW_DEFAULT_GPS}")
    return True

def get_current_interval():
    """Dapatkan interval saat ini."""
    return current_interval

def update_intervals(location_interval, detection_interval, allow_default=True):
    """Update kedua interval sekaligus."""
    global current_interval, DETECTION_INTERVAL, last_location_sent, last_detection_sent, ALLOW_DEFAULT_GPS
    
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
        
        # Update pengaturan GPS default
        ALLOW_DEFAULT_GPS = bool(allow_default)
        
        # Reset last_location_sent agar interval baru berlaku segera
        last_location_sent = 0
        last_detection_sent = 0
        
        logger.info(f"✅ Intervals updated - Location: {location_interval}s, Detection: {detection_interval}s, Allow Default GPS: {ALLOW_DEFAULT_GPS}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to update intervals: {str(e)}")
        return False

# Force kirim notifikasi segera
def force_send_now():
    """Force sending notification immediately by resetting timers."""
    global last_location_sent, last_detection_sent
    last_location_sent = 0
    last_detection_sent = 0
    logger.info("✅ Timers reset. Next notification will be sent immediately.")
    return True
