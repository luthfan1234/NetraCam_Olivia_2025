# Kacamata Tunanetra Tanpa MQTT

Proyek ini adalah implementasi sistem kacamata pintar untuk tunanetra tanpa menggunakan protokol MQTT. Sistem menggunakan ESP32-CAM untuk menangkap gambar, modul GPS (Ublox NEO-6M) untuk pelacakan lokasi, DFPlayer Mini untuk output suara, serta server Flask dengan YOLOv8 untuk deteksi objek dan dashboard web.

## 📋 Fitur

* Deteksi objek (pejalan kaki & kendaraan) menggunakan YOLOv8
* Notifikasi suara via DFPlayer Mini
* Pelacakan lokasi real-time menggunakan GPS Neo-6M
* Dashboard web menampilkan peta lokasi terkini (Leaflet.js)
* Notifikasi deteksi via Telegram Bot
* Komunikasi data menggunakan HTTP 

## 🛠️ Persyaratan

### Hardware

* ESP32-CAM (AI-Thinker)
* Modul GPS Ublox NEO-6M
* DFRobot DFPlayer Mini + speaker kecil
* MicroSD Card (FAT32) untuk menyimpan file audio
* Breadboard & jumper wires
* USB-to-Serial adapter (FTDI) jika ESP32-CAM tidak memiliki onboard USB
* Power supply 5V (power bank atau adaptor USB)

### Software

* **Arduino IDE** (versi terbaru)

  * Board ESP32 via Board Manager: `https://raw.githubusercontent.com/espressif/arduino-esp32`
  * Library:

    * esp\_camera (core ESP32)
    * WiFi.h & HTTPClient.h (core ESP32)
    * DFRobotDFPlayerMini
    * TinyGPSPlus
    * HardwareSerial (core ESP32)
* **Python 3.10+**

  * Virtual environment (opsional)
  * Library pip:

    ```bash
    pip install flask ultralytics opencv-python-headless requests
    ```
* **Code editor**: VS Code (disarankan)

## 📂 Struktur Proyek

```
KACAMATA_TN/
├── arduino/
│   └── kacamata.ino        # Sketch ESP32-CAM
├── audio/
│   ├── 001.mp3             # "Hati-hati, ada pejalan kaki"
│   └── 002.mp3             # "Hati-hati, ada kendaraan"
├── flask_app/
│   ├── app.py              # Server Flask utama
│   ├── yolo_infer.py       # Modul inferensi YOLOv8
│   ├── gps_routes.py       # Blueprint GPS
│   ├── telegram_bot.py     # Helper Telegram Bot
│   ├── templates/
│   │   └── index.html      # Dashboard web
│   └── static/
│       └── style.css       # Styling dashboard
└── README.md               # Dokumentasi proyek
```

## 🚀 Instalasi & Menjalankan

### 1. Persiapan Arduino IDE

1. Buka Arduino IDE
2. Tambahkan URL Board Manager: `https://raw.githubusercontent.com/espressif/arduino-esp32`
3. Install board "AI-Thinker ESP32-CAM"
4. Install library via Library Manager:

   * DFRobotDFPlayerMini
   * TinyGPSPlus

### 2. Konfigurasi Audio

1. Format MicroSD ke FAT32
2. Copy `audio/001.mp3` dan `audio/002.mp3` ke root MicroSD
3. Masukkan ke DFPlayer Mini

### 3. Upload ke ESP32-CAM

1. Buka `arduino/kacamata.ino`
2. Sesuaikan `ssid`, `password`, dan `server` URL (default: `http://192.168.226.250:5000`)
3. Pilih Board & Port, lalu Upload

### 4. Setup Python Server

```bash
cd flask_app
python -m venv venv         # buat virtualenv (opsional)
source venv/bin/activate    # Linux/Mac
venv\Scripts\activate     # Windows
pip install flask ultralytics opencv-python-headless requests
```

### 5. Konfigurasi Telegram

1. Buat Bot via @BotFather → dapatkan `BOT_TOKEN`
2. Chat dengan bot, dapatkan `CHAT_ID`
3. Set `BOT_TOKEN` & `CHAT_ID` di `flask_app/telegram_bot.py`

### 6. Jalankan Flask

```bash
export FLASK_APP=app.py      # Linux/Mac
set FLASK_APP=app.py         # Windows
flask run --host=0.0.0.0 --port=5000
```

### 7. Akses Dashboard

Buka browser → `http://192.168.226.250:5000/`

## 🧪 Pengujian End-to-End

1. Nyalakan ESP32-CAM, tunggu koneksi WiFi
2. Amati Serial Monitor: kirim gambar & GPS
3. Lihat dashboard lokasi & notifikasi Telegram
4. Cek suara DFPlayer saat deteksi objek

# Panduan Menjalankan Sistem Kacamata Tunanetra

Dokumen ini berisi panduan lengkap untuk menjalankan sistem kacamata tunanetra dengan deteksi objek, GPS tracking, dan notifikasi Telegram.

## 📋 Prasyarat Sistem

Sebelum menjalankan, pastikan Anda memiliki:

- Python 3.8 atau lebih baru
- Arduino IDE (untuk ESP32-CAM)
- Perangkat ESP32-CAM dengan sensor kamera
- Modul GPS Neo-6M
- DFPlayer Mini dan speaker
- MicroSD card berisi file audio
- Koneksi internet

## 🛠️ Instalasi dan Konfigurasi

### 1. Setup Hardware

1. **Rangkai ESP32-CAM** dengan:
   - GPS Neo-6M: TX → GPIO13, RX → GPIO12, VCC → 3.3V, GND → GND
   - DFPlayer Mini: RX → GPIO14, TX → GPIO15, VCC → 5V, GND → GND
   - Pastikan MicroSD dengan file audio sudah terpasang di DFPlayer

2. **Persiapkan Arduino:**
   - Buka sketch `arduino/kacamata.ino` di Arduino IDE
   - Sesuaikan kredensial WiFi dan IP server Flask
   - Upload ke ESP32-CAM menggunakan FTDI adapter

### 2. Setup Software Server (Flask)

1. **Instalasi dependensi Python:**
   ```bash
   # Buat virtual environment (opsional tetapi disarankan)
   python -m venv venv
   
   # Aktifkan virtual environment
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   
   # Install packages yang diperlukan
   pip install flask flask-login flask-sqlalchemy flask-wtf ultralytics opencv-python requests
   ```

2. **Konfigurasi Telegram:**
   - Edit file `flask_app/telegram_bot.py`
   - Ganti `BOT_TOKEN` dan `CHAT_ID` dengan nilai yang sesuai

3. **Inisialisasi Database:**
   ```bash
   cd flask_app
   python -c "from app import app; from models import db; app.app_context().push(); db.create_all()"
   ```

## 🚀 Menjalankan Sistem

### 1. Jalankan Server Flask

```bash
cd flask_app
python app.py
```

Server akan berjalan di `http://localhost:5000` atau sesuai IP yang dikonfigurasi.

### 2. Login ke Dashboard

- Buka browser dan kunjungi URL server
- Login dengan kredensial default:
  - Username: `admin`
  - Password: `admin123`

### 3. Nyalakan ESP32-CAM

- Pastikan ESP32-CAM terhubung ke power
- Tunggu hingga terhubung ke WiFi (LED indikator akan menyala)
- ESP32-CAM akan mulai mengirim data ke server Flask

### 4. Menggunakan Dashboard

Dashboard terdiri dari beberapa halaman:

- **Pemantauan Lokasi**: Tampilan peta dan kamera real-time
- **Pengaturan**: Konfigurasi kamera dan interval notifikasi Telegram
- **Riwayat Aktivitas**: Log aktivitas dan statistik perangkat

## 🔍 Pemecahan Masalah

### Masalah Koneksi ESP32-CAM

- Pastikan kredensial WiFi benar
- Periksa IP server Flask di kode ESP32-CAM
- Restart ESP32-CAM dengan menekan tombol reset

### Server Flask Tidak Responsif

- Pastikan semua dependensi terinstal: `pip install -r requirements.txt`
- Periksa log error di terminal server
- Pastikan port 5000 tidak digunakan aplikasi lain

### Notifikasi Telegram Tidak Berfungsi

- Verifikasi `BOT_TOKEN` dan `CHAT_ID` di `telegram_bot.py`
- Pastikan bot Telegram sudah diaktifkan (chat `/start`)
- Periksa koneksi internet server

### Deteksi Objek Tidak Berjalan

- Pastikan model YOLOv8 (`best.pt`) berada di lokasi yang benar
- Periksa permisi akses file model
- Perbarui library ultralytics: `pip install --upgrade ultralytics`

## 📊 Memonitor Kinerja

- Statistik kinerja dapat dilihat di halaman Riwayat Aktivitas
- Log perangkat tersedia di terminal server Flask
- Serial monitor ESP32-CAM (jika terhubung) menampilkan status koneksi

---

Dikembangkan oleh Tim Doa Ibu (NetraCam) - Universitas Sebelas Maret

Ghaitsa Aulia Sakinah Wijaya (V8223011)
Muhammad Fadhli Nur Luthfan (V3423055)
Nayla Asri Yusviputri Ashani (V8223021)
Nurfadila Cahyani (V8223023)

