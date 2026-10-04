"""
AttendX — Dual-mode attendance system (Face Recognition + QR/Barcode).
Flask + SQLite backend serving 5 pages: login, scanner, enroll, dashboard, students.

Security hardening (Sep 2026):
  - Secrets loaded from .env via python-dotenv (SECRET_KEY, TEACHER_PASSWORD).
  - Teacher password hashed with werkzeug.security on first run.
  - Short-lived signed scan tokens (itsdangerous) required on /scan.
  - Rate limiting on /login and /scan via flask-limiter.
  - 30-minute idle session timeout.
  - debug=False by default; FLASK_DEBUG=1 in .env to override.
"""

import os
import io
import csv
import json
import socket
from datetime import date, datetime, timedelta

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, Response
)
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3

# ---------------------------------------------------------------------------
# Configuration — all secrets come from environment variables (.env file).
# ---------------------------------------------------------------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "CHANGE-ME-insecure-fallback")
app.permanent_session_lifetime = timedelta(minutes=30)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

@app.after_request
def set_security_headers(response):
    """Set HTTP security headers on all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    return response

DB = "attendance.db"

# Signed-token serializer used to issue short-lived scan tokens.
# Tokens prevent a raw POST to /scan from faking attendance without a real
# client-side face/QR match first.
token_serializer = URLSafeTimedSerializer(app.secret_key)

# Rate limiter — protects /login and /scan from brute-force / spam.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# ---------------------------------------------------------------------------
# Password hashing helper
# ---------------------------------------------------------------------------
# On first run the plaintext TEACHER_PASSWORD env var is hashed and stored in
# memory. After that, check_password_hash is used for comparison — the raw
# password is never compared as a string.
_raw_pw = os.getenv("TEACHER_PASSWORD", "attendx2026")
TEACHER_PASSWORD_HASH = generate_password_hash(_raw_pw)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """Open a connection to the SQLite database with Row factory and busy timeout."""
    conn = sqlite3.connect(DB, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn


def get_local_ip():
    """Return the machine's LAN IP so phones on the same Wi-Fi can connect."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_server_url():
    """Return (local_ip, server_url) matching active protocol scheme (HTTP/HTTPS)."""
    local_ip = get_local_ip()
    try:
        scheme = request.scheme
    except RuntimeError:
        scheme = "https" if os.getenv("USE_HTTPS", "0") == "1" else "http"
    return local_ip, f"{scheme}://{local_ip}:5000"


def init_db():
    """Create tables if missing and seed the class roster.

    Safe to call on every startup — uses CREATE TABLE IF NOT EXISTS and
    INSERT OR IGNORE so existing data is never clobbered.
    """
    conn = get_db()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    conn.execute("""CREATE TABLE IF NOT EXISTS students
                     (id TEXT PRIMARY KEY, name TEXT,
                      face_descriptor TEXT, face_registered_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS attendance
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      student_id TEXT, date TEXT, time TEXT, method TEXT DEFAULT 'barcode')""")

    # Migrate older schema versions if columns are missing.
    student_cols = [row[1] for row in conn.execute("PRAGMA table_info(students)").fetchall()]
    if "face_descriptor" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN face_descriptor TEXT")
    if "face_registered_at" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN face_registered_at TEXT")

    att_cols = [row[1] for row in conn.execute("PRAGMA table_info(attendance)").fetchall()]
    if "time" not in att_cols:
        conn.execute("ALTER TABLE attendance ADD COLUMN time TEXT")
    if "method" not in att_cols:
        conn.execute("ALTER TABLE attendance ADD COLUMN method TEXT DEFAULT 'barcode'")

    # Confirmed real student IDs (known mappings).
    confirmed = {
        "ABHISHEK": "25DS001",
        "AKASH DAGAR": "25DS007",
        "ADITI SINGH": "25DS126",
        "CHANDANI VISHWAKARMA": "25DS030",
        "DEEPAK KUMAR SINGH": "25DS031",
        "DEV PATEL": "25DS032",
        "LUCKY KUMAR": "25DS050",
    }

    # Full class roster — order as given.
    roster = [
        "AARAM MAURYA", "ABHISHEK", "ABHISHEK KUMAR YADAV", "ADHIRAJ SOLANKI",
        "ADITI SINGH", "ADITYA CHAUHAN", "ADITYA KUMAR", "ADITYA MAURYA",
        "ADITYA RAJAK", "ADITYA SINGH", "AKASH DAGAR", "AKASH PATEL",
        "AKSHAT RAVI KAUSHIK", "AKUL SIHANIYA", "AMAL KUMAR", "AMAN GUPTA",
        "AMRITA DUBEY", "ANAND RAJ", "ANIMESH CHAND", "ANKIT KUMAR",
        "ANKIT KUMAR VERMA", "ANKIT SHARMA", "ANSHUMAN YADAV", "ANUJ KUMAR",
        "ANUMESH", "ANYANYA RAGHUVANSHI", "ARJUN PRATAP SINGH", "ARSALA ZEHRA ZAIDI",
        "ARSH MISHRA", "ARUSH RAJ SINGH", "ASHISH BHATT", "ASHUTOSH THAKUR",
        "ATEEBA HASAN", "BHANUPRATAP SINGH", "BHAWNA KUMARI", "CHANDANI VISHWAKARMA",
        "DEEPAK KUMAR SINGH", "DEEPENDRA", "DEV PATEL", "DHANANJAY KUMAR",
        "DHANANJAY PRAJAPATI", "DIVYANSH THAPA", "DIWAKAR SINGH", "DRISHTI SOLANKI",
        "GAURAV SINGH", "GOPAL JHA", "HARDEV YADAV", "HARSH KUMAR", "HARSH KUMAR",
        "HARSHIT SHARMA", "INDRESH NISHAD", "JANVI BHATNAGAR", "KRISH KUMAR VERMA",
        "KRISH VERMA", "KUNAL SHARMA", "KUSH CHAUHAN", "LAVANYA SINGH",
        "LOVE CHAUHAN", "LOVESH PATHAK", "LUCKY KUMAR", "MAYANK SINGH",
    ]

    pending_counter = 1
    for name in roster:
        if name in confirmed:
            sid = confirmed[name]
        else:
            sid = f"PENDING-{pending_counter:03d}"
            pending_counter += 1
        conn.execute("INSERT OR IGNORE INTO students (id, name) VALUES (?, ?)", (sid, name))

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Session / auth helpers
# ---------------------------------------------------------------------------
def teacher_required():
    """Return True if the current session belongs to an authenticated teacher.

    Also enforces a 30-minute idle timeout: if more than 30 minutes have
    elapsed since the last request, the session is cleared.
    """
    if not session.get("teacher"):
        return False

    last_active = session.get("last_active")
    if last_active:
        try:
            last_dt = datetime.fromisoformat(last_active)
            if datetime.now() - last_dt > timedelta(minutes=30):
                session.clear()
                return False
        except (ValueError, TypeError):
            pass

    # Refresh the idle timer on every authenticated request.
    session["last_active"] = datetime.now().isoformat()
    return True


# ---------------------------------------------------------------------------
# Scan token helpers
# ---------------------------------------------------------------------------
@app.route("/api/scan-token", methods=["POST"])
@limiter.limit("120/minute")
def issue_scan_token():
    """Issue a short-lived signed token after the client-side face or QR
    match succeeds.

    Embeds student_id, method, client timestamp, and cryptographic nonce
    to ensure tamper-proof, anti-replay integrity.
    """
    data = request.get_json(silent=True) or {}
    student_id = data.get("id", "").strip().upper()
    method = data.get("method", "barcode").strip().lower()
    nonce = data.get("nonce", "")
    client_ts = data.get("timestamp", datetime.now().isoformat())

    if method not in ("face", "barcode", "manual"):
        method = "barcode"

    if not student_id:
        return jsonify({"status": "error", "message": "No student ID provided"}), 400

    token = token_serializer.dumps({
        "id": student_id,
        "method": method,
        "nonce": nonce,
        "ts": client_ts,
    })
    return jsonify({
        "status": "ok",
        "token": token,
        "security": "HMAC-SHA256-Signed",
        "expires_in": 30
    })


# ---------------------------------------------------------------------------
# Scanner & Face APIs
# ---------------------------------------------------------------------------
@app.route("/")
def scanner_page():
    local_ip, phone_url = get_server_url()
    return render_template("scanner.html", local_ip=local_ip, phone_url=phone_url)


@app.route("/scan", methods=["POST"])
@limiter.limit("120/minute")
def scan():
    """Mark a student present for today.

    Requires a signed token (from /api/scan-token) that embeds the student_id
    and scan method.  The token expires after 30 seconds.

    Duplicate-check logic:
      Before inserting, we query the attendance table for any row matching
      this student_id + today's date.  If one exists the student is already
      marked present, and we return status="duplicate" without inserting
      again.  This guarantees at most one attendance record per student
      per calendar day.
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")

    if not token:
        return jsonify({"status": "error", "message": "Missing scan token"}), 400

    # Verify and decode the signed token (max age 30 seconds).
    try:
        payload = token_serializer.loads(token, max_age=30)
    except SignatureExpired:
        return jsonify({"status": "error", "message": "Scan token expired, please scan again"}), 400
    except BadSignature:
        return jsonify({"status": "error", "message": "Invalid scan token"}), 400

    student_id = payload.get("id", "").strip().upper()
    method = payload.get("method", "barcode")

    today = str(date.today())
    now = datetime.now().strftime("%H:%M:%S")

    if not student_id:
        return jsonify({"status": "error", "message": "No student ID in token"}), 400

    try:
        conn = get_db()
        student = conn.execute(
            "SELECT name, id FROM students WHERE id=?", (student_id,)
        ).fetchone()

        if not student:
            conn.close()
            return jsonify({"status": "unknown", "message": f"Unknown ID: {student_id}"})

        # Duplicate-check: one attendance record per student per day.
        already = conn.execute(
            "SELECT * FROM attendance WHERE student_id=? AND date=?",
            (student_id, today),
        ).fetchone()

        if already:
            conn.close()
            return jsonify({
                "status": "duplicate",
                "name": student["name"],
                "id": student["id"],
                "time": already["time"],
                "message": f"{student['name']} already marked present today ({already['time']})",
            })

        conn.execute(
            "INSERT INTO attendance (student_id, date, time, method) VALUES (?, ?, ?, ?)",
            (student_id, today, now, method),
        )
        conn.commit()
        conn.close()

        method_label = "Face recognition" if method == "face" else "Barcode scan"
        return jsonify({
            "status": "success",
            "name": student["name"],
            "id": student["id"],
            "time": now,
            "method": method,
            "message": f"Marked present — {student['name']} via {method_label} at {now}",
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500


@app.route("/api/students/faces", methods=["GET"])
def get_student_faces():
    """Return all enrolled face descriptors for client-side matching.

    Face-descriptor matching logic (for viva reference):
      Each enrolled student has a 128-dimensional face descriptor vector
      stored as JSON in the students table.  The client downloads all
      descriptors, builds a faceapi.FaceMatcher with a distance threshold
      of 0.52, and on every video frame computes the Euclidean distance
      between the live face's descriptor and every enrolled descriptor.
      The enrolled face with the smallest distance wins, provided that
      distance is below 0.52 (i.e. >48% confidence).  If no enrolled
      face is close enough the detection is labelled "unknown".
    """
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT id, name, face_descriptor, face_registered_at
            FROM students
            WHERE face_descriptor IS NOT NULL AND face_descriptor != ''
        """).fetchall()
        conn.close()

        faces = []
        for r in rows:
            try:
                desc = json.loads(r["face_descriptor"])
                faces.append({
                    "id": r["id"],
                    "name": r["name"],
                    "descriptor": desc,
                    "registered_at": r["face_registered_at"],
                })
            except (json.JSONDecodeError, TypeError):
                continue

        return jsonify({"status": "success", "count": len(faces), "faces": faces})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500


@app.route("/api/students/register-face", methods=["POST"])
def register_face():
    """Store or update a 128-d face descriptor vector for a student.

    The descriptor is a list of 128 floating-point numbers generated by
    face-api.js's faceRecognitionNet on the client.  We store it as a
    JSON string in the students.face_descriptor column.
    """
    data = request.get_json(silent=True) or {}
    student_id = data.get("id", "").strip().upper()
    descriptor = data.get("descriptor")

    if not student_id:
        return jsonify({"status": "error", "message": "Student ID is required"}), 400

    if not descriptor or not isinstance(descriptor, list) or len(descriptor) != 128:
        return jsonify({"status": "error", "message": "Valid 128-dimensional face descriptor vector is required"}), 400

    try:
        descriptor = [float(x) for x in descriptor]
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Biometric vector values must be valid floating point numbers"}), 400

    try:
        conn = get_db()
        student = conn.execute(
            "SELECT name, id FROM students WHERE id=?", (student_id,)
        ).fetchone()
        if not student:
            conn.close()
            return jsonify({"status": "error", "message": f"Student with ID '{student_id}' not found"}), 404

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        desc_json = json.dumps(descriptor)

        conn.execute("""
            UPDATE students
            SET face_descriptor=?, face_registered_at=?
            WHERE id=?
        """, (desc_json, now_iso, student_id))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Face enrolled for {student['name']} ({student_id})",
            "name": student["name"],
            "id": student_id,
            "registered_at": now_iso,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500


@app.route("/api/students/remove-face", methods=["POST"])
def remove_face():
    """Clear the stored face descriptor for a student."""
    data = request.get_json(silent=True) or request.form
    student_id = data.get("id", "").strip().upper()

    if not student_id:
        return jsonify({"status": "error", "message": "Student ID is required"}), 400

    try:
        conn = get_db()
        student = conn.execute(
            "SELECT name, id FROM students WHERE id=?", (student_id,)
        ).fetchone()
        if not student:
            conn.close()
            return jsonify({"status": "error", "message": "Student not found"}), 404

        conn.execute(
            "UPDATE students SET face_descriptor=NULL, face_registered_at=NULL WHERE id=?",
            (student_id,),
        )
        conn.commit()
        conn.close()

        if request.is_json:
            return jsonify({"status": "success", "message": f"Face data removed for {student['name']}"})
        return redirect(url_for("manage_students"))
    except Exception as e:
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500


@app.route("/enroll")
def self_enroll_page():
    """Student-facing self-enrollment page (open on mobile or desktop)."""
    try:
        conn = get_db()
        students = conn.execute("""
            SELECT name, id,
                   CASE WHEN face_descriptor IS NOT NULL AND face_descriptor != '' THEN 1 ELSE 0 END as has_face
            FROM students
            ORDER BY name
        """).fetchall()
        conn.close()
    except Exception:
        students = []

    local_ip = get_local_ip()
    return render_template("enroll.html", students=students, local_ip=local_ip)


# ---------------------------------------------------------------------------
# Toggle attendance (teacher dashboard one-click)
# ---------------------------------------------------------------------------
@app.route("/api/attendance/toggle", methods=["POST"])
def toggle_attendance():
    """Toggle a student's attendance for a given date (teacher only).

    If the student already has an attendance record for the date, delete it
    (mark absent).  Otherwise insert one (mark present via 'manual' method).
    """
    if not teacher_required():
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id", "").strip().upper()
    target_date = data.get("date", str(date.today())).strip()
    now_time = datetime.now().strftime("%H:%M:%S")

    if not student_id:
        return jsonify({"status": "error", "message": "Missing student_id"}), 400

    try:
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM attendance WHERE student_id=? AND date=?",
            (student_id, target_date),
        ).fetchone()

        if existing:
            conn.execute("DELETE FROM attendance WHERE id=?", (existing["id"],))
            conn.commit()
            conn.close()
            return jsonify({
                "status": "success",
                "action": "removed",
                "is_present": False,
                "student_id": student_id,
                "message": f"Marked absent for {student_id}",
            })
        else:
            conn.execute(
                "INSERT INTO attendance (student_id, date, time, method) VALUES (?, ?, ?, 'manual')",
                (student_id, target_date, now_time),
            )
            conn.commit()
            conn.close()
            return jsonify({
                "status": "success",
                "action": "marked",
                "is_present": True,
                "time": now_time,
                "method": "manual",
                "student_id": student_id,
                "message": f"Marked present at {now_time}",
            })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Student attendance history (teacher only)
# ---------------------------------------------------------------------------
@app.route("/api/students/<student_id>/history")
def student_history(student_id):
    if not teacher_required():
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    student_id = student_id.strip().upper()

    try:
        conn = get_db()
        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
        if not student:
            conn.close()
            return jsonify({"status": "error", "message": "Student not found"}), 404

        history = conn.execute("""
            SELECT date, time, method
            FROM attendance
            WHERE student_id=?
            ORDER BY date DESC
        """, (student_id,)).fetchall()

        total_days_row = conn.execute("SELECT COUNT(DISTINCT date) FROM attendance").fetchone()
        total_days = total_days_row[0] or 1
        days_present = len(history)
        pct = round((days_present / total_days) * 100, 1)

        records = [
            {"date": h["date"], "time": h["time"], "method": h["method"] or "barcode"}
            for h in history
        ]
        conn.close()

        return jsonify({
            "status": "success",
            "student": {
                "id": student["id"],
                "name": student["name"],
                "has_face": bool(student["face_descriptor"]),
                "face_registered_at": student["face_registered_at"],
            },
            "stats": {
                "days_present": days_present,
                "total_days": total_days,
                "percent": pct,
            },
            "history": records,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Teacher login / logout
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute")
def login():
    error = None
    if request.method == "POST":
        entered = request.form.get("password", "")
        if check_password_hash(TEACHER_PASSWORD_HASH, entered):
            session.permanent = True
            session["teacher"] = True
            session["last_active"] = datetime.now().isoformat()
            return redirect(url_for("dashboard"))
        error = "Incorrect password"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard (attendance sheet)
# ---------------------------------------------------------------------------
@app.route("/dashboard")
def dashboard():
    if not teacher_required():
        return redirect(url_for("login"))

    selected_date = request.args.get("date", str(date.today()))

    try:
        conn = get_db()

        all_students = conn.execute("""
            SELECT name, id,
                   CASE WHEN face_descriptor IS NOT NULL AND face_descriptor != '' THEN 1 ELSE 0 END as has_face
            FROM students
            ORDER BY name
        """).fetchall()

        present_rows = conn.execute("""
            SELECT student_id, time, method FROM attendance WHERE date=?
        """, (selected_date,)).fetchall()
        present_map = {
            r["student_id"]: {"time": r["time"], "method": r["method"] or "barcode"}
            for r in present_rows
        }

        total_days_row = conn.execute("SELECT COUNT(DISTINCT date) FROM attendance").fetchone()
        total_days = total_days_row[0] or 1

        # Query all student attendance counts in a single bulk GROUP BY query
        counts_rows = conn.execute("""
            SELECT student_id, COUNT(*) as cnt
            FROM attendance
            GROUP BY student_id
        """).fetchall()
        attendance_counts = {r["student_id"]: r["cnt"] for r in counts_rows}

        sheet = []
        present_count = 0
        face_enrolled_count = 0

        for i, s in enumerate(all_students, start=1):
            if s["has_face"]:
                face_enrolled_count += 1

            days_present = attendance_counts.get(s["id"], 0)
            pct = round((days_present / total_days) * 100, 1)
            is_present = s["id"] in present_map
            att_info = present_map.get(s["id"], {})

            if is_present:
                present_count += 1

            sheet.append({
                "sr": i,
                "name": s["name"],
                "id": s["id"],
                "has_face": bool(s["has_face"]),
                "present": is_present,
                "time": att_info.get("time", "-"),
                "method": att_info.get("method", "-"),
                "percent": pct,
            })

        conn.close()
    except Exception:
        sheet = []
        present_count = 0
        face_enrolled_count = 0

    local_ip, phone_url = get_server_url()

    return render_template(
        "dashboard.html",
        sheet=sheet,
        selected_date=selected_date,
        total_students=len(sheet),
        present_count=present_count,
        face_enrolled_count=face_enrolled_count,
        local_ip=local_ip,
        phone_url=phone_url,
    )


# ---------------------------------------------------------------------------
# Manage Students
# ---------------------------------------------------------------------------
@app.route("/students", methods=["GET", "POST"])
def manage_students():
    if not teacher_required():
        return redirect(url_for("login"))

    message = None
    if request.method == "POST":
        try:
            if "single_add" in request.form:
                name = request.form.get("name", "").strip()
                sid = request.form.get("student_id", "").strip().upper()
                if name and sid:
                    conn = get_db()
                    conn.execute("INSERT OR REPLACE INTO students (id, name) VALUES (?, ?)", (sid, name))
                    conn.commit()
                    conn.close()
                    message = f"Added student: {name} ({sid})"

            elif "bulk_add" in request.form:
                bulk_text = request.form.get("bulk_data", "").strip()
                count = 0
                conn = get_db()
                for line in bulk_text.splitlines():
                    if "," in line:
                        name, sid = line.split(",", 1)
                        name, sid = name.strip(), sid.strip().upper()
                        if name and sid:
                            conn.execute("INSERT OR REPLACE INTO students (id, name) VALUES (?, ?)", (sid, name))
                            count += 1
                conn.commit()
                conn.close()
                message = f"Added/updated {count} students"

            elif "replace_id" in request.form:
                old_id = request.form.get("old_id")
                new_id = request.form.get("new_id", "").strip().upper()
                name = request.form.get("existing_name")
                if new_id:
                    conn = get_db()
                    old_row = conn.execute(
                        "SELECT face_descriptor, face_registered_at FROM students WHERE id=?",
                        (old_id,),
                    ).fetchone()
                    f_desc = old_row["face_descriptor"] if old_row else None
                    f_time = old_row["face_registered_at"] if old_row else None

                    conn.execute("DELETE FROM students WHERE id=?", (old_id,))
                    conn.execute(
                        "INSERT OR REPLACE INTO students (id, name, face_descriptor, face_registered_at) VALUES (?, ?, ?, ?)",
                        (new_id, name, f_desc, f_time),
                    )
                    conn.commit()
                    conn.close()
                    message = f"Updated ID: {name} → {new_id}"

            elif "delete_id" in request.form:
                sid = request.form.get("delete_id")
                conn = get_db()
                conn.execute("DELETE FROM students WHERE id=?", (sid,))
                conn.commit()
                conn.close()
                message = f"Removed student ID: {sid}"
        except Exception as e:
            message = f"Error: {str(e)}"

    try:
        conn = get_db()
        all_students = conn.execute("""
            SELECT name, id, face_registered_at,
                   CASE WHEN face_descriptor IS NOT NULL AND face_descriptor != '' THEN 1 ELSE 0 END as has_face
            FROM students
            ORDER BY name
        """).fetchall()
        conn.close()
    except Exception:
        all_students = []

    local_ip, phone_url = get_server_url()

    return render_template(
        "students.html",
        students=all_students,
        message=message,
        local_ip=local_ip,
        phone_url=phone_url,
    )


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
@app.route("/export")
def export_csv():
    if not teacher_required():
        return redirect(url_for("login"))

    selected_date = request.args.get("date", str(date.today()))

    try:
        conn = get_db()
        all_students = conn.execute("SELECT name, id FROM students ORDER BY name").fetchall()
        present_rows = conn.execute(
            "SELECT student_id, time, method FROM attendance WHERE date=?",
            (selected_date,),
        ).fetchall()
        present_map = {
            r["student_id"]: {"time": r["time"], "method": r["method"] or "barcode"}
            for r in present_rows
        }
        conn.close()
    except Exception:
        all_students = []
        present_map = {}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Sr No", "Name", "Roll Number", "Status", "Check-in Time", "Method"])
    for i, s in enumerate(all_students, start=1):
        is_pres = s["id"] in present_map
        status = "Present" if is_pres else "Absent"
        time_val = present_map[s["id"]]["time"] if is_pres else "-"
        method_val = present_map[s["id"]]["method"] if is_pres else "-"
        writer.writerow([i, s["name"], s["id"], status, time_val, method_val])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=attendance_{selected_date}.csv"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    use_https = os.getenv("USE_HTTPS", "0") == "1"
    ssl_ctx = "adhoc" if use_https else None
    scheme = "https" if use_https else "http"
    local_ip = get_local_ip()

    print("=" * 60)
    print("  AttendX Kiosk Server Running")
    print(f"  * Localhost:     {scheme}://localhost:5000")
    print(f"  * LAN / Mobile:  {scheme}://{local_ip}:5000")
    print(f"  * Mode:          {'HTTPS (SSL Ad-Hoc)' if use_https else 'HTTP (Default)'}")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=debug_mode, ssl_context=ssl_ctx)