#include <WiFi.h>
#include <WebServer.h>
#include <HardwareSerial.h>
#include <DFRobotDFPlayerMini.h>
#include <TinyGPS++.h>
#include <esp32cam.h>
#include "esp_camera.h"

// Update WiFi settings
const char* WIFI_SSID = "Test";
const char* WIFI_PASS = "12345678";

// ===== Server Setup =====
WebServer server(80);

// Update DFPlayer pins and variables
HardwareSerial dfSerial(1);  // Use Serial1 
DFRobotDFPlayerMini dfplayer;
bool dfplayer_ready = false;

// ===== GPS (Serial2 - RX only: GPIO15) =====
HardwareSerial gpsSerial(2); // Gunakan Serial2 untuk GPS
TinyGPSPlus gps;
bool gps_ready = false;

// ===== Camera Resolution =====
static auto loRes  = esp32cam::Resolution::find(320, 240);
static auto midRes = esp32cam::Resolution::find(640, 480);
static auto hiRes  = esp32cam::Resolution::find(800, 600);

// Track current resolution
static auto currentRes = midRes;  // Default to mid resolution

// ===== IMPROVED AUDIO MANAGEMENT SYSTEM =====
struct AudioManager {
    // Timing constants - Disesuaikan untuk audio TTS bahasa Indonesia
    static const unsigned long PERSON_DURATION = 6000;      // 6 detik untuk "hati hati ada pejalan kaki di depan kamu"
    static const unsigned long VEHICLE_DURATION = 5500;     // 5.5 detik untuk "pelan pelan disekitarmu ada kendaraan"
    static const unsigned long COMMAND_DELAY = 300;         // Delay antar perintah DFPlayer lebih lama
    static const unsigned long COOLDOWN_SAME_CLASS = 8000;  // 8 detik cooldown untuk kelas yang sama
    static const unsigned long COOLDOWN_DIFFERENT_CLASS = 2000; // 2 detik untuk kelas berbeda
    static const unsigned long PLAYBACK_BUFFER = 500;       // Buffer tambahan untuk memastikan audio tidak terpotong
    
    // State variables
    bool isPlaying = false;
    unsigned long playStartTime = 0;
    unsigned long expectedDuration = 0;
    String currentClass = "";
    String lastPlayedClass = "";
    unsigned long lastPlayTime = 0;
    
    // Queue system
    struct QueueItem {
        String detectionClass;
        unsigned long timestamp;
    };
    
    static const int QUEUE_SIZE = 3;
    QueueItem queue[QUEUE_SIZE];
    int queueHead = 0;
    int queueTail = 0;
    
    // Debug helper
    void debugLog(String message) {
        Serial.print("🔊 [AudioMgr] ");
        Serial.println(message);
    }
    
    // Check if queue is empty
    bool isQueueEmpty() {
        return queueHead == queueTail;
    }
    
    // Check if queue is full
    bool isQueueFull() {
        return ((queueTail + 1) % QUEUE_SIZE) == queueHead;
    }
    
    // Add item to queue
    bool addToQueue(String detectionClass) {
        if (isQueueFull()) {
            debugLog("Queue penuh, menolak: " + detectionClass);
            return false;
        }
        
        queue[queueTail].detectionClass = detectionClass;
        queue[queueTail].timestamp = millis();
        queueTail = (queueTail + 1) % QUEUE_SIZE;
        
        debugLog("Ditambahkan ke queue: " + detectionClass);
        return true;
    }
    
    // Get next item from queue
    QueueItem getFromQueue() {
        if (isQueueEmpty()) {
            return {"", 0};
        }
        
        QueueItem item = queue[queueHead];
        queueHead = (queueHead + 1) % QUEUE_SIZE;
        return item;
    }
    
    // Check if we can play a sound (cooldown logic) - FIXED
    bool canPlay(String detectionClass) {
        unsigned long currentTime = millis();
        
        if (isPlaying) {
            debugLog("Sedang memutar, menolak: " + detectionClass);
            return false;
        }
        
        // First time playing, no cooldown
        if (lastPlayTime == 0) {
            debugLog("First time playing, no cooldown applied");
            return true;
        }
        
        // Check cooldown with fixed logic
        if (lastPlayedClass == detectionClass) {
            unsigned long elapsed = currentTime - lastPlayTime;
            if (elapsed < COOLDOWN_SAME_CLASS) {
                unsigned long remaining = COOLDOWN_SAME_CLASS - elapsed;
                debugLog("Cooldown aktif untuk " + detectionClass + ", sisa: " + String(remaining/1000) + "s");
                return false;
            }
            
            // Cooldown expired, can play
            debugLog("Cooldown untuk " + detectionClass + " sudah habis, boleh play");
            return true;
        } else {
            unsigned long elapsed = currentTime - lastPlayTime;
            if (elapsed < COOLDOWN_DIFFERENT_CLASS) {
                unsigned long remaining = COOLDOWN_DIFFERENT_CLASS - elapsed;
                debugLog("Cooldown antar-kelas aktif, sisa: " + String(remaining/1000) + "s");
                return false;
            }
            
            // Different class cooldown expired, can play
            debugLog("Cooldown antar kelas sudah habis, boleh play");
            return true;
        }
    }
    
    // Start playing a sound
    bool startPlaying(String detectionClass) {
        if (!dfplayer_ready) {
            debugLog("DFPlayer tidak siap");
            return false;
        }

        // Hentikan audio yang sedang berjalan dengan cara yang lebih gentle
        if (isPlaying) {
            dfplayer.stop();
            delay(COMMAND_DELAY);
            debugLog("Menghentikan audio sebelumnya");
        }
        
        // Reset DFPlayer untuk memastikan state yang bersih
        dfplayer.reset();
        delay(500);  // Tunggu reset selesai
        
        // Set volume optimal untuk TTS Indonesia
        dfplayer.volume(28);
        delay(COMMAND_DELAY);
        
        // Konfigurasikan equalizer untuk suara yang lebih jelas
        dfplayer.EQ(DFPLAYER_EQ_NORMAL);
        delay(COMMAND_DELAY);
        
        // Play appropriate file dengan timing yang disesuaikan
        if (detectionClass == "orang") {
            dfplayer.play(1);
            expectedDuration = PERSON_DURATION;
            debugLog("🎵 MEMUTAR: 'Hati-hati ada pejalan kaki di depan kamu' (001.mp3)");
        } else if (detectionClass == "kendaraan") {
            dfplayer.play(2);
            expectedDuration = VEHICLE_DURATION;
            debugLog("🎵 MEMUTAR: 'Pelan-pelan disekitarmu ada kendaraan' (002.mp3)");
        } else {
            debugLog("Kelas deteksi tidak dikenal: " + detectionClass);
            return false;
        }
        
        // Update state
        isPlaying = true;
        playStartTime = millis();
        currentClass = detectionClass;
        lastPlayedClass = detectionClass;
        lastPlayTime = millis();
        
        debugLog("Audio dimulai pada: " + String(playStartTime) + ", durasi: " + String(expectedDuration/1000) + "s");
        return true;
    }
    
    // Check if current playback is finished
    void updatePlaybackStatus() {
        if (!isPlaying) return;
        
        unsigned long currentTime = millis();
        unsigned long totalDuration = expectedDuration + PLAYBACK_BUFFER;
        
        if (currentTime - playStartTime >= totalDuration) {
            // Pastikan audio benar-benar selesai dengan grace period
            dfplayer.stop();
            delay(100);
            
            debugLog("✅ SELESAI: " + currentClass + " (durasi: " + String(totalDuration/1000) + "s)");
            
            isPlaying = false;
            currentClass = "";
        } else {
            // Tampilkan progress setiap 2 detik
            static unsigned long lastProgressUpdate = 0;
            if (currentTime - lastProgressUpdate > 2000) {
                unsigned long remaining = totalDuration - (currentTime - playStartTime);
                debugLog("🎵 SEDANG PUTAR: " + currentClass + ", sisa: " + String(remaining/1000) + "s");
                lastProgressUpdate = currentTime;
            }
        }
    }
    
    // Process queue and play next sound if possible
    void processQueue() {
        if (isPlaying || isQueueEmpty()) return;
        
        QueueItem nextItem = getFromQueue();
        if (nextItem.detectionClass == "") return;
        
        // Check if item is too old (avoid playing stale detections)
        unsigned long currentTime = millis();
        if (currentTime - nextItem.timestamp > 5000) {  // Increase stale timeout untuk TTS yang lebih panjang
            debugLog("Item queue terlalu lama, dilewati: " + nextItem.detectionClass);
            return;
        }
        
        if (canPlay(nextItem.detectionClass)) {
            startPlaying(nextItem.detectionClass);
        } else {
            debugLog("Tidak bisa memutar dari queue: " + nextItem.detectionClass);
        }
    }
    
    // Handle new detection
    String handleDetection(String detectionClass) {
        debugLog("Deteksi masuk: " + detectionClass);
        
        // Validate detection class
        if (detectionClass != "orang" && detectionClass != "kendaraan") {
            debugLog("Kelas tidak valid: " + detectionClass);
            return "INVALID_CLASS";
        }
        
        // If we can play immediately, do it
        if (canPlay(detectionClass)) {
            if (startPlaying(detectionClass)) {
                return "PLAYING";
            } else {
                return "PLAY_FAILED";
            }
        }
        
        // If we can't play immediately, try to add to queue
        if (addToQueue(detectionClass)) {
            return "QUEUED";
        } else {
            return "QUEUE_FULL";
        }
    }
    
    // Get current status for debugging
    String getStatus() {
        String status = "";
        if (isPlaying) {
            unsigned long elapsed = millis() - playStartTime;
            unsigned long totalDuration = expectedDuration + PLAYBACK_BUFFER;
            unsigned long remaining = (elapsed < totalDuration) ? (totalDuration - elapsed) : 0;
            status += "PLAYING:" + currentClass + ":" + String(remaining/1000) + "s/" + String(totalDuration/1000) + "s";
        } else {
            status += "IDLE";
            if (lastPlayedClass != "") {
                unsigned long timeSinceLastPlay = millis() - lastPlayTime;
                status += ":LAST:" + lastPlayedClass + ":" + String(timeSinceLastPlay/1000) + "s_ago";
            }
        }
        
        if (!isQueueEmpty()) {
            int queueCount = (queueTail - queueHead + QUEUE_SIZE) % QUEUE_SIZE;
            status += ":QUEUE:" + String(queueCount);
        }
        
        return status;
    }
    
    // Add method to clear the queue
    void clearQueue() {
        queueHead = queueTail;  // Reset queue pointers to empty the queue
        debugLog("Queue dibersihkan");
    }
    
    // Reset all audio state
    void resetState() {
        isPlaying = false;
        currentClass = "";
        lastPlayedClass = "";
        lastPlayTime = 0;  // Reset the cooldown timer
        clearQueue();
        debugLog("Audio state reset completely");
    }
};

// Global audio manager instance
AudioManager audioMgr;

// ===== Snapshot Function =====
void serveJpg() {
    static int failCount = 0;
    
    auto frame = esp32cam::capture();
    if (!frame) {
        Serial.println("❌ CAPTURE FAIL");
        failCount++;
        
        if (failCount > 5) {
            Serial.println("⚠️ Too many capture failures, resetting camera...");
            esp_restart();  // Use ESP restart instead of camera deinit
            failCount = 0;
        }
        
        server.send(503, "text/plain", "Capture Failed");
        return;
    }
    
    failCount = 0;  // Reset fail counter on success
    
    // Add debug info
    Serial.printf("📸 CAPTURE OK %dx%d %db\n", frame->getWidth(), frame->getHeight(), (int)frame->size());
    
    // Set CORS headers for browser compatibility
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.sendHeader("Access-Control-Allow-Methods", "GET");
    server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
    
    server.setContentLength(frame->size());
    server.send(200, "image/jpeg");
    WiFiClient client = server.client();
    frame->writeTo(client);
}

// ===== Camera Handlers =====
void handleJpgLo()  { 
    currentRes = loRes;
    esp32cam::Camera.changeResolution(loRes);  
    serveJpg(); 
}
void handleJpgMid() { 
    currentRes = midRes;
    esp32cam::Camera.changeResolution(midRes); 
    serveJpg(); 
}
void handleJpgHi()  { 
    currentRes = hiRes;
    esp32cam::Camera.changeResolution(hiRes);  
    serveJpg(); 
}

// ===== Root Page =====
void handleRoot() {
  server.send(200, "text/plain", "📷 ESP32-CAM with GPS & DFPlayer ready!");
}

// ===== DFPlayer Play Handler (untuk testing manual) =====
void handlePlay() {
  String f = server.arg("file");
  if (f == "1") {
    String result = audioMgr.handleDetection("orang");
    Serial.println("🔊 Manual play person: " + result);
    server.send(200, "text/plain", "MANUAL_PLAY_PERSON:" + result);
  } else if (f == "2") {
    String result = audioMgr.handleDetection("kendaraan");
    Serial.println("🔊 Manual play vehicle: " + result);
    server.send(200, "text/plain", "MANUAL_PLAY_VEHICLE:" + result);
  } else {
    Serial.println("⚠️  Unknown file request");
    server.send(200, "text/plain", "UNKNOWN_FILE");
  }
}

// ===== GPS Handler =====
void handleGPS() {
  if (gps.location.isValid()) {
    String msg = String(gps.location.lat(), 6) + "," + String(gps.location.lng(), 6);
    server.send(200, "text/plain", msg);
  } else {
    server.send(200, "text/plain", "GPS_NOT_FIX");
  }
}

// ===== IMPROVED Detection Handler =====
void handleDetection() {
    String detection = server.arg("class");
    
    // Handle detection using audio manager
    String result = audioMgr.handleDetection(detection);
    
    // Add CORS headers
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "text/plain", result);
}

void setupWiFi() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  
  Serial.print("📡 Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi Connected");
    Serial.println("📍 IP: " + WiFi.localIP().toString());
    Serial.println("📶 RSSI: " + String(WiFi.RSSI()) + " dBm");
  } else {
    Serial.println("\n❌ WiFi connection failed");
  }
}

void checkWiFiHealth() {
  static unsigned long lastCheck = 0;
  if (millis() - lastCheck > 10000) {  // Check every 10 seconds
    lastCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("⚠️ Network issue detected, reconnecting...");
      WiFi.disconnect();
      delay(1000);
      setupWiFi();
    }
  }
}

void setupDFPlayer() {
    Serial.println("🎵 Initializing DFPlayer for Indonesian TTS...");
    dfSerial.begin(9600, SERIAL_8N1, 13, 12);
    delay(1000);  // Shorter initial delay
    
    // Retry mechanism
    int retries = 0;
    bool connected = false;
    
    while (!connected && retries < 3) {
        if (dfplayer.begin(dfSerial, true)) { // Enable debug info
            connected = true;
            Serial.println("✅ DFPlayer connected!");
        } else {
            retries++;
            Serial.println("⚠️ Retry connecting to DFPlayer... " + String(retries) + "/3");
            delay(500);
        }
    }
    
    if (!connected) {
        Serial.println("❌ DFPlayer failed to initialize");
        return;
    }
    
    // Simplified configuration with minimal delays
    Serial.println("⚙️ Configuring DFPlayer...");
    
    // Set volume 
    dfplayer.volume(25);
    delay(100);
    
    // Skip lengthy reset and other config steps
    
    // Just assume files exist and mark player as ready
    dfplayer_ready = true;
    Serial.println("✅ DFPlayer initialized successfully");
    
    // Force a test play of file 1
    Serial.println("🔈 Testing audio file 3...");
    dfplayer.play(3);
    
    // Success message
    Serial.println("📢 Ready for audio playback");
    Serial.println("- 001.mp3: 'Hati-hati ada pejalan kaki di depan kamu'");
    Serial.println("- 002.mp3: 'Pelan-pelan disekitarmu ada kendaraan'");
}

void handleStatus() {
    String response = "{";
    response += "\"connected\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false") + ",";  // Fix boolean representation
    response += "\"rssi\":" + String(WiFi.RSSI()) + ",";
    response += "\"gps_valid\":" + String(gps.location.isValid() ? "true" : "false") + ",";  // Fix boolean representation
    response += "\"dfplayer_ready\":" + String(dfplayer_ready ? "true" : "false") + ",";  // Fix boolean representation
    response += "\"audio_status\":\"" + audioMgr.getStatus() + "\",";
    response += "\"last_update\":\"" + String(millis()/1000) + "\"";
    response += "}";
    
    // Add debugging output
    Serial.println("📊 Status request received, sending: " + response);
    
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.sendHeader("Content-Type", "application/json");
    server.send(200, "application/json", response);
}

void handleSettings() {
    String response = "{";
    response += "\"update_interval\":3,";
    response += "\"quality\":" + String(currentRes == hiRes ? 720 : currentRes == midRes ? 480 : 360) + ",";
    response += "\"fps\":30,";
    response += "\"device_id\":\"NETRACAM-01\"";
    response += "}";
    
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.sendHeader("Content-Type", "application/json");
    server.send(200, "application/json", response);
}

void setup() {
  Serial.begin(115200);
  delay(2000);  // Longer initial delay
  Serial.println("\n🚀 Booting ESP32-CAM with DFPlayer & GPS...");

  // DFPlayer initialization
  setupDFPlayer();  // Call the new setup function

  // === Init Camera with balanced quality and performance settings ===
  {
    using namespace esp32cam;
    Config cfg;
    cfg.setPins(pins::AiThinker);
    cfg.setResolution(hiRes);      // Use higher resolution
    cfg.setBufferCount(2);         // Reduced buffer for lower latency
    cfg.setJpeg(80);              // Better JPEG quality (was 60)
    
    bool ok = Camera.begin(cfg);
    if (!ok) {
        Serial.println("❌ Camera initialization failed");
        delay(100);
        ESP.restart();
    }
    
    sensor_t * s = esp_camera_sensor_get();
    if (s) {
        s->set_brightness(s, 1);     // Slightly increased brightness
        s->set_contrast(s, 1);       // Slightly increased contrast
        s->set_saturation(s, 1);     // Slightly increased saturation
        s->set_special_effect(s, 0); // No special effect
        s->set_whitebal(s, 1);       // Enable white balance
        s->set_awb_gain(s, 1);       // Enable AWB gain
        s->set_wb_mode(s, 0);        // Auto WB mode
        s->set_exposure_ctrl(s, 1);   // Enable auto exposure
        s->set_aec2(s, 1);           // Enable AEC DSP
        s->set_ae_level(s, 1);       // Slightly increased AE level
        s->set_gain_ctrl(s, 1);      // Enable auto gain
        s->set_agc_gain(s, 2);       // Moderate gain increase
        s->set_gainceiling(s, (gainceiling_t)3); // Moderate gain ceiling
        s->set_bpc(s, 1);            // Enable defect correction
        s->set_wpc(s, 1);            // Enable white pixel correction
        s->set_raw_gma(s, 1);        // Enable GMA
        s->set_lenc(s, 1);           // Enable lens correction
        s->set_dcw(s, 1);            // Enable DCW
        s->set_colorbar(s, 0);       // Disable colorbar
    }
    
    Serial.println("✅ Camera initialized with balanced quality settings");
  }

  setupWiFi();
  
  // === Init GPS Serial2 ===
  gpsSerial.begin(9600, SERIAL_8N1, 15, -1); // RX = 15 only
  Serial.println("📡 GPS Module initialized.");
  gps_ready = true;

  // === WebServer Routes ===
  server.on("/",           handleRoot);
  server.on("/cam-lo.jpg", handleJpgLo);
  server.on("/cam-mid.jpg",handleJpgMid);
  server.on("/cam-hi.jpg", handleJpgHi);
  server.on("/play",       handlePlay);
  server.on("/gps",        handleGPS);
  server.on("/detect",     handleDetection);  // Route untuk deteksi
  server.on("/status",     handleStatus);     // Route untuk status
  server.on("/settings",   handleSettings);   // Route untuk settings
  server.begin();
  Serial.println("🌐 WebServer started.");
  
  Serial.println("\n=== SYSTEM READY ===");
  Serial.println("Indonesian TTS Audio System:");
  Serial.println("- 001.mp3: 'Hati-hati ada pejalan kaki di depan kamu' (6s)");
  Serial.println("- 002.mp3: 'Pelan-pelan disekitarmu ada kendaraan' (5.5s)");
  Serial.println("\nTest Commands:");
  Serial.println("- Send 'a' via Serial to test person detection");
  Serial.println("- Send 'b' via Serial to test vehicle detection");
  Serial.println("- Send 's' via Serial to check audio status");
  Serial.println("- Send 'r' via Serial to reset audio system");
}

void loop() {
    // === Serial Commands for Testing ===
    if (Serial.available()) {
        char input = Serial.read();
        if (input == 'a') {
            // Play person warning directly through DFPlayer
            if (dfplayer_ready) {
                dfplayer.stop();  // Stop any current playback
                delay(100);
                dfplayer.volume(28);  // Set optimal volume
                delay(100);
                dfplayer.play(1);  // Play person warning
                Serial.println("🔊 Playing person warning via serial command");
                delay(500);  // Short delay to ensure playback starts
            } else {
                Serial.println("❌ DFPlayer not ready");
            }
        }
        else if (input == 'b') {
            // Play vehicle warning directly through DFPlayer
            if (dfplayer_ready) {
                dfplayer.stop();  // Stop any current playback
                delay(100);
                dfplayer.volume(28);  // Set optimal volume
                delay(100);
                dfplayer.play(2);  // Play vehicle warning
                Serial.println("🔊 Playing vehicle warning via serial command");
                delay(500);  // Short delay to ensure playback starts
            } else {
                Serial.println("❌ DFPlayer not ready");
            }
        }
        else if (input == 's') {
            Serial.println("📊 Status Audio: " + audioMgr.getStatus());
            Serial.println("🎵 DFPlayer Ready: " + String(dfplayer_ready));
        }
        else if (input == 'r') {
            Serial.println("🔄 Resetting audio system...");
            audioMgr.resetState();  // Use the new resetState method
            dfplayer.stop();
            delay(500);
            dfplayer.reset();
            delay(2000);
            dfplayer.volume(28);
            Serial.println("✅ Audio system reset completed");
        }
        else if (input == 'q') {
            // Add a command to clear just the queue
            audioMgr.clearQueue();
            Serial.println("🧹 Queue cleared");
        }
    }

    // === Process more server requests per loop to avoid backlog ===
    for (int i = 0; i < 3; i++) {
        server.handleClient();
        delay(5);  // Small delay between handling requests
    }
    
    // === Audio Management ===
    audioMgr.updatePlaybackStatus();  // Check if current sound finished
    audioMgr.processQueue();          // Process queued detections
    
    // === Handle server requests ===
    server.handleClient();
    
    // === Handle GPS data ===
    while (gpsSerial.available()) {
        gps.encode(gpsSerial.read());
    }

    if (gps.location.isUpdated()) {
        Serial.print("📍 GPS: ");
        Serial.print(gps.location.lat(), 6);
        Serial.print(", ");
        Serial.println(gps.location.lng(), 6);
    }
    
    // === WiFi Health Check ===
    checkWiFiHealth();
    
    delay(50);  // Slightly longer delay untuk stability dengan audio yang lebih panjang
}