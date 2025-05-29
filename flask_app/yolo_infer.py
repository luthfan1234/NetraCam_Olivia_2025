from ultralytics import YOLO
import cv2
import numpy as np
import requests
import os
from pathlib import Path
import time
from telegram_bot import send_telegram_alert

# Get absolute path to model file
MODEL_PATH = 'D:/KULIAH UNS/OLIVIA/KACAMATA_TN/flask_app/best.pt'

# Verify model exists
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"YOLO model not found at {MODEL_PATH}")

# Inisialisasi model
try:
    model = YOLO(MODEL_PATH)
    print("✅ Model loaded successfully")
    print(f"Model classes: {model.names}")
except Exception as e:
    raise Exception(f"Failed to load YOLO model: {str(e)}")
CONF_THRESHOLD = 0.5
# Update ESP settings to match GPS routes
ESP_IP = "192.168.130.173"
TIMEOUT = 5  # Increased timeout
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # Increased delay between retries

# URL definitions
CAM_URL = f"http://{ESP_IP}/cam-hi.jpg"
PLAY_URL = f"http://{ESP_IP}/play"
GPS_URL = f"http://{ESP_IP}/gps"
DETECT_URL = f"http://{ESP_IP}/detect"

# Update constants
DETECTION_COOLDOWN = 5  # Reduced to 5 seconds
MIN_CONFIDENCE = 0.50   # Increased confidence threshold
MAX_CONSECUTIVE_DETECTIONS = 3  # Limit consecutive detections

# Add detection tracking
consecutive_detections = 0
last_detection_class = None

# Variabel untuk melacak waktu deteksi terakhir
last_detection_time = time.time() - 60  # Init to allow immediate first detection

# Update color mapping for two classes
COLORS = {
    "orang": (0, 255, 0),      # Green for person
    "kendaraan": (0, 0, 255)   # Red for vehicles
}

# Fungsi ambil frame dari ESP32-CAM
def fetch_frame():
    session = requests.Session()
    session.trust_env = False  # Disable proxy settings
    
    for attempt in range(MAX_RETRIES):
        try:
            # Test connection with increased timeout
            test_resp = session.get(f"http://{ESP_IP}", 
                                  timeout=TIMEOUT,
                                  headers={'Connection': 'keep-alive'})
            
            if test_resp.status_code == 200:
                # Get image
                resp = session.get(CAM_URL, 
                                 timeout=TIMEOUT,
                                 headers={'Connection': 'keep-alive'})
                
                if resp.status_code == 200 and len(resp.content) > 100:
                    img_np = np.frombuffer(resp.content, np.uint8)
                    img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
                    if img is not None and img.size > 0:
                        print(f"✅ Frame captured successfully")
                        return img
                else:
                    print(f"⚠️ Invalid response: status={resp.status_code}, size={len(resp.content)}")
            else:
                print(f"⚠️ ESP32 returned status code {test_resp.status_code}")
                
            if attempt < MAX_RETRIES - 1:
                print(f"🔄 Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
                
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                
    return None

# Fungsi deteksi dari gambar (byte array)
def detect_from_image(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return detect_from_frame(image)

# Fungsi utama deteksi dari frame OpenCV
def detect_from_frame(frame, app=None):
    global last_detection_time, last_detection_class, consecutive_detections
    
    try:
        results = model(frame, conf=CONF_THRESHOLD)[0]
        current_time = time.time()
        
        # Process detections
        best_detection = None
        best_confidence = 0
        
        # Always draw boxes for visualization with enhanced visuals
        for det in results.boxes:
            confidence = float(det.conf.item())
            class_id = int(det.cls.item())
            class_name = model.names[class_id]  # This should be either "orang" or "kendaraan"
            
            # Update best detection
            if confidence > best_confidence and confidence >= MIN_CONFIDENCE:
                best_confidence = confidence
                best_detection = det
            
            # Draw enhanced box if confidence meets threshold
            if confidence >= MIN_CONFIDENCE:
                x1, y1, x2, y2 = map(int, det.xyxy[0])
                color = COLORS.get(class_name, (255, 255, 0))  # Yellow for unknown classes
                
                # Draw filled rectangle for label background
                label = f"{class_name} {confidence:.2f}"
                (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(frame, (x1, y1-label_h-10), (x1+label_w, y1), color, -1)
                
                # Draw bounding box with thickness based on confidence
                thickness = max(2, min(4, int(confidence * 4)))
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
                
                # Draw label text in white
                cv2.putText(frame, label, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.6, (255, 255, 255), 2)

        # Handle sound triggers and Telegram alerts for best detection
        if best_detection is not None:
            class_id = int(best_detection.cls.item())
            class_name = model.names[class_id]
            
            # Direct mapping since model already uses "orang" and "kendaraan"
            if class_name in ["orang", "kendaraan"]:
                # Play sound locally via ESP32
                try:
                    detect_url = f"http://{ESP_IP}/detect?class={class_name}"
                    detect_response = requests.get(detect_url, timeout=1)
                    
                    if detect_response.ok:
                        if class_name == last_detection_class:
                            consecutive_detections += 1
                        else:
                            consecutive_detections = 1
                            
                        last_detection_time = current_time
                        last_detection_class = class_name
                        print(f"🔊 Alert played: {class_name} ({best_confidence:.2f})")
                        
                        # Log activity if app context is available
                        if app:
                            with app.app_context():
                                from app import log_activity
                                log_activity(f'Deteksi {class_name}', 
                                           f'Confidence: {best_confidence:.2f}', 
                                           'detection')
                                
                        # Send Telegram notification
                        cooldown_satisfied = current_time - last_detection_time >= DETECTION_COOLDOWN
                        if cooldown_satisfied:
                            message = f"⚠️ <b>DETEKSI {class_name.upper()}</b>\n" \
                                     f"🔍 Kepastian: {best_confidence:.2f}\n" \
                                     f"⏰ Waktu: {time.strftime('%H:%M:%S')}"
                            send_telegram_alert(message)
                        
                except Exception as e:
                    print(f"❌ Failed to send alert: {str(e)}")
        
        return frame

    except Exception as e:
        print(f"❌ YOLO detection error: {str(e)}")
        return frame

# Test function untuk debug model
def test_model():
    print("\n=== Testing YOLO Model ===")
    print(f"Model file: {MODEL_PATH}")
    print(f"Available classes: {list(model.names.values())}")
    print(f"Confidence threshold: {CONF_THRESHOLD}")
    
    frame = fetch_frame()
    if frame is not None:
        print(f"Test frame shape: {frame.shape}")
        try:
            frame_with_detections = detect_from_frame(frame)
            print("✅ Detection test successful")
        except Exception as e:
            print(f"❌ Detection test failed: {str(e)}")
    else:
        print("❌ Could not get test frame")

# Contoh eksekusi
if __name__ == "__main__":
    test_model()
