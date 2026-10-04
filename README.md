# AttendX

A attendance system I built for my class that works in two ways — either scan a student's barcode/QR ID or just look at the camera and it marks you present automatically using face recognition.

I got tired of the manual register process so I just made this. It runs locally on a laptop, works on mobile too if you're on the same Wi-Fi.

---

## What it does

- Face recognition — students enroll once via webcam, after that just look at the camera and done
- Barcode / QR scanning — works with any student ID card that has a barcode
- Teacher login with a dashboard to see who came, filter by date, download CSV
- Student list page showing who's enrolled and who isn't
- Runs over HTTPS if you need camera access on phones (just toggle it in .env)

---

## Tech used

- Python / Flask for the backend
- SQLite for storing attendance and student data (no setup needed, just a file)
- face-api.js for the face recognition stuff (runs entirely in the browser, no server-side ML)
- Vanilla HTML/CSS/JS for the frontend

---

## How to run it

Clone it and set up a virtual env first:

```bash
git clone https://github.com/0x-dks/AttendX.git
cd AttendX

python -m venv .venv
.venv\Scripts\activate        # on Windows
# source .venv/bin/activate   # on Mac/Linux
```

Install the dependencies:

```bash
pip install flask python-dotenv werkzeug itsdangerous flask-limiter
```

Copy the example env file and edit it:

```bash
cp .env.example .env
```

Open `.env` and change at least these two:

```
SECRET_KEY=some-long-random-string
TEACHER_PASSWORD=whatever-you-want
```

To generate a proper secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then just run it:

```bash
python app.py
```

Go to `http://localhost:5000` and log in.

---

## Using it on a phone

Set `USE_HTTPS=1` in your `.env`. The app will print the LAN IP when it starts — open that on your phone's browser and it should work. You'll get a certificate warning since it's self-signed, just accept it.

---

## Project structure

```
AttendX/
├── app.py                  # everything backend lives here
├── check_enroll.py         # quick script to check who's enrolled
├── .env.example            # copy this to .env
├── static/
│   ├── style.css
│   ├── js/
│   │   └── face-api.min.js
│   └── models/             # face-api model weights (don't touch these)
└── templates/
    ├── login.html
    ├── scanner.html        # the main page for marking attendance
    ├── enroll.html         # for registering a student's face
    ├── dashboard.html      # attendance records
    └── students.html       # full class list
```

---

## A few things to know

- The `.env` file is gitignored — don't commit it, it has your password in it
- `attendance.db` is also gitignored — it's just a local SQLite file that gets created on first run
- The face recognition runs fully client-side in the browser using face-api.js, so no face data ever leaves the machine
- There's rate limiting on the login and scan endpoints so it won't get spammed

---

Built this for my Data Science batch. Might clean it up more later.
