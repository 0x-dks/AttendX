# AttendX 🎓

> **Dual-mode smart attendance system** — mark attendance via **Face Recognition** or **QR/Barcode scanning**, built with Flask + SQLite.

---

## ✨ Features

- 🤖 **Face Recognition** — enrolls students via webcam and identifies them in real-time using [face-api.js](https://github.com/justadudewhohacks/face-api.js)
- 📷 **QR / Barcode Scanning** — instant attendance via student ID barcodes
- 🔐 **Teacher Login** — password-protected dashboard with 30-minute idle session timeout
- 📊 **Dashboard** — view today's attendance, filter by date, export to CSV
- 👥 **Student Management** — full class roster with enrollment status
- 🔒 **Security hardened** — signed scan tokens, rate limiting, HTTP security headers, hashed passwords

---

## 🖥️ Pages

| Route | Description |
|---|---|
| `/` | Login page (teacher authentication) |
| `/scanner` | Dual-mode scanner (Face / QR-Barcode) |
| `/enroll` | Enroll a student's face via webcam |
| `/dashboard` | Attendance records + CSV export |
| `/students` | Full student roster & face enrollment status |

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/0x-dks/AttendX.git
cd AttendX
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install flask python-dotenv werkzeug itsdangerous flask-limiter
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set your values:

```env
SECRET_KEY=your-random-secret-key-here
TEACHER_PASSWORD=your-secure-password
FLASK_DEBUG=0
USE_HTTPS=0
```

> 💡 Generate a secure key with:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

### 5. Run the app

```bash
python app.py
```

Open your browser at **http://localhost:5000**

---

## 📱 Mobile / LAN Access

Set `USE_HTTPS=1` in `.env` to enable ad-hoc SSL — required for camera access on mobile browsers over Wi-Fi. The terminal will display your LAN IP on startup.

---

## 📁 Project Structure

```
AttendX/
├── app.py                  # Main Flask application
├── check_enroll.py         # Utility to check enrollment status
├── .env.example            # Environment variable template
├── .gitignore
├── static/
│   ├── style.css           # Global styles
│   ├── js/
│   │   └── face-api.min.js # Face recognition library
│   └── models/             # Pre-trained face-api.js model weights
│       ├── ssd_mobilenetv1_model-*
│       ├── face_landmark_68_model-*
│       ├── face_recognition_model-*
│       └── tiny_face_detector_model-*
└── templates/
    ├── login.html
    ├── scanner.html
    ├── enroll.html
    ├── dashboard.html
    └── students.html
```

---

## 🔒 Security Notes

- **Never commit `.env`** — it's in `.gitignore` by default
- `TEACHER_PASSWORD` is hashed with `werkzeug.security` on first run
- Scan endpoints are protected by short-lived signed tokens (`itsdangerous`)
- Rate limiting is applied on `/login` and `/scan` to prevent brute-force
- `attendance.db` is local-only and excluded from version control

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · Flask · SQLite |
| Auth & Security | Werkzeug · itsdangerous · flask-limiter |
| Face Recognition | face-api.js (client-side, browser) |
| Frontend | HTML · Vanilla CSS · JavaScript |

---

## 📄 License

This project is for educational use. Feel free to fork and adapt.

---

<p align="center">Made with ❤️ by <a href="https://github.com/0x-dks">DKS</a></p>
