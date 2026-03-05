import os
import io
import threading
import sqlite3
import datetime
import json
import cv2
import numpy as np
from flask import Flask, render_template, request, jsonify, send_file, abort
from face_model import train_model_background, extract_embedding_for_image, MODEL_PATH

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "attendance.db")
DATASET_DIR = os.path.join(APP_DIR, "dataset")
os.makedirs(DATASET_DIR, exist_ok=True)

TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")

app = Flask(__name__, static_folder="static", template_folder="templates")

# Custom Jinja2 filter for human-readable timestamps
@app.template_filter('human_datetime')
def human_datetime_filter(timestamp_str):
    """Convert ISO timestamp to human-readable format"""
    try:
        # Parse the ISO format timestamp
        dt = datetime.datetime.fromisoformat(timestamp_str)
        
        # Get current time for relative formatting
        now = datetime.datetime.now()
        diff = now - dt
        
        # Format date
        if dt.date() == now.date():
            date_part = "Today"
        elif dt.date() == (now - datetime.timedelta(days=1)).date():
            date_part = "Yesterday"
        elif diff.days < 7:
            date_part = dt.strftime("%A")  # Day name (e.g., Monday)
        else:
            date_part = dt.strftime("%B %d, %Y")  # e.g., March 04, 2026
        
        # Format time in 12-hour format with AM/PM
        time_part = dt.strftime("%I:%M %p")  # e.g., 02:30 PM
        
        # Combine
        return f"{date_part} at {time_part}"
    except:
        # Fallback to original if parsing fails
        return timestamp_str

# ---------- DB helpers ----------
def get_db_connection():
    """Get a database connection with proper settings"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS students (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        roll TEXT,
                        class TEXT,
                        section TEXT,
                        reg_no TEXT,
                        created_at TEXT
                    )""")
        c.execute("""CREATE TABLE IF NOT EXISTS attendance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER,
                        name TEXT,
                        timestamp TEXT,
                        deleted INTEGER DEFAULT 0,
                        deleted_at TEXT,
                        deleted_reason TEXT,
                        subject_id INTEGER,
                        subject_code TEXT,
                        subject_name TEXT,
                        period INTEGER,
                        day_of_week INTEGER
                    )""")
        
        # Create subjects table
        c.execute("""CREATE TABLE IF NOT EXISTS subjects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT NOT NULL UNIQUE,
                        name TEXT NOT NULL,
                        teacher TEXT,
                        created_at TEXT
                    )""")
        
        # Create timetable table
        c.execute("""CREATE TABLE IF NOT EXISTS timetable (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        day_of_week INTEGER NOT NULL,
                        period INTEGER NOT NULL,
                        subject_id INTEGER NOT NULL,
                        start_time TEXT,
                        end_time TEXT,
                        FOREIGN KEY (subject_id) REFERENCES subjects(id),
                        UNIQUE(day_of_week, period)
                    )""")
        
        # Create student_subjects (enrollment) table
        c.execute("""CREATE TABLE IF NOT EXISTS student_subjects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        subject_id INTEGER NOT NULL,
                        enrolled_at TEXT,
                        FOREIGN KEY (student_id) REFERENCES students(id),
                        FOREIGN KEY (subject_id) REFERENCES subjects(id),
                        UNIQUE(student_id, subject_id)
                    )""")
        
        # Create audit log table for tracking unmark actions
        c.execute("""CREATE TABLE IF NOT EXISTS attendance_audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        attendance_id INTEGER,
                        student_id INTEGER,
                        student_name TEXT,
                        action TEXT,
                        reason TEXT,
                        timestamp TEXT
                    )""")
        
        # Create index to speed up duplicate checks
        c.execute("""CREATE INDEX IF NOT EXISTS idx_attendance_student_time 
                     ON attendance(student_id, timestamp DESC)""")
        
        # Create index for deleted flag
        c.execute("""CREATE INDEX IF NOT EXISTS idx_attendance_deleted 
                     ON attendance(deleted)""")
        
        # Create indexes for subject-based queries
        c.execute("""CREATE INDEX IF NOT EXISTS idx_attendance_subject 
                     ON attendance(subject_id)""")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_attendance_period 
                     ON attendance(period, day_of_week)""")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_student_subjects 
                     ON student_subjects(student_id, subject_id)""")
        
        conn.commit()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Database initialization error: {e}")
        conn.rollback()
    finally:
        conn.close()

init_db()

# Auto-train on startup if dataset exists
def auto_train_on_startup():
    """Automatically train the model when the app starts"""
    from face_model import auto_train_from_dataset
    if os.path.exists(DATASET_DIR) and os.listdir(DATASET_DIR):
        print("Auto-training face recognition model on startup...")
        auto_train_from_dataset(DATASET_DIR)
        print("Startup auto-training complete!")

# Run auto-training in background thread
startup_thread = threading.Thread(target=auto_train_on_startup)
startup_thread.daemon = True
startup_thread.start()

# ---------- Train status helpers ----------
def write_train_status(status_dict):
    with open(TRAIN_STATUS_FILE, "w") as f:
        json.dump(status_dict, f)

def read_train_status():
    if not os.path.exists(TRAIN_STATUS_FILE):
        return {"running": False, "progress": 0, "message": "Not trained"}
    with open(TRAIN_STATUS_FILE, "r") as f:
        return json.load(f)

# ensure initial train status file exists
write_train_status({"running": False, "progress": 0, "message": "No training yet."})

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/manage_students")
def manage_students():
    return render_template("manage_students.html")

# Dashboard simple API for attendance stats (last 30 days)
@app.route("/attendance_stats")
def attendance_stats():
    import pandas as pd
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT timestamp FROM attendance", conn)
    conn.close()
    if df.empty:
        from datetime import date, timedelta
        days = [(date.today() - datetime.timedelta(days=i)).strftime("%d-%b") for i in range(29, -1, -1)]
        return jsonify({"dates": days, "counts": [0]*30})
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    last_30 = [ (datetime.date.today() - datetime.timedelta(days=i)) for i in range(29, -1, -1) ]
    counts = [ int(df[df['date'] == d].shape[0]) for d in last_30 ]
    dates = [ d.strftime("%d-%b") for d in last_30 ]
    return jsonify({"dates": dates, "counts": counts})

# -------- Add student (form) --------
@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if request.method == "GET":
        return render_template("add_student.html")
    # POST: save student metadata and return student_id
    data = request.form
    name = data.get("name","").strip()
    roll = data.get("roll","").strip()
    cls = data.get("class","").strip()
    sec = data.get("sec","").strip()
    reg_no = data.get("reg_no","").strip()
    if not name:
        return jsonify({"error":"name required"}), 400
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get the next sequential ID
    c.execute("SELECT MAX(id) FROM students")
    max_id = c.fetchone()[0]
    next_id = (max_id + 1) if max_id else 1
    
    now = datetime.datetime.utcnow().isoformat()
    c.execute("INSERT INTO students (id, name, roll, class, section, reg_no, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (next_id, name, roll, cls, sec, reg_no, now))
    conn.commit()
    conn.close()
    
    # create dataset folder for this student
    os.makedirs(os.path.join(DATASET_DIR, str(next_id)), exist_ok=True)
    return jsonify({"student_id": next_id})

# -------- Upload face images (after capture) --------
@app.route("/upload_face", methods=["POST"])
def upload_face():
    student_id = request.form.get("student_id")
    if not student_id:
        return jsonify({"error":"student_id required"}), 400
    
    files = request.files.getlist("images[]")
    saved = 0
    folder = os.path.join(DATASET_DIR, student_id)
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    
    # Get student name for better tracking
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM students WHERE id=?", (int(student_id),))
    row = c.fetchone()
    student_name = row[0] if row else f"Student {student_id}"
    conn.close()
    
    # Import face recognition functions
    from face_model import face_recognizer
    
    encodings_added = 0
    
    for f in files:
        try:
            fname = f"{datetime.datetime.utcnow().timestamp():.6f}_{saved}.jpg"
            path = os.path.join(folder, fname)
            f.save(path)
            
            # Automatically extract face encoding and add to database
            f.stream.seek(0)  # Reset stream position
            face_encoding = face_recognizer.extract_face_encoding(f.stream)
            if face_encoding is not None:
                success = face_recognizer.add_face_encoding(
                    int(student_id), 
                    face_encoding, 
                    student_name
                )
                if success:
                    encodings_added += 1
                    print(f"✓ Auto-added face encoding for {student_name} (ID: {student_id})")
            
            saved += 1
        except Exception as e:
            app.logger.error("save error: %s", e)
    
    # Provide feedback about automatic training
    message = f"Images saved successfully! {encodings_added} faces automatically processed."
    if encodings_added >= 3:
        message += " Auto-training initiated for improved accuracy."
    
    return jsonify({
        "saved": saved, 
        "encodings_added": encodings_added,
        "message": message
    })

# -------- Train model (start background thread) --------
@app.route("/train_model", methods=["GET"])
def train_model_route():
    # if already running, respond accordingly
    status = read_train_status()
    if status.get("running"):
        return jsonify({"status":"already_running"}), 202
    # reset status
    write_train_status({"running": True, "progress": 0, "message": "Starting training"})
    # start background thread
    t = threading.Thread(target=train_model_background, args=(DATASET_DIR, lambda p,m: write_train_status({"running": True, "progress": p, "message": m})))
    t.daemon = True
    t.start()
    return jsonify({"status":"started"}), 202

# -------- Train progress (polling) --------
@app.route("/train_status", methods=["GET"])
def train_status():
    return jsonify(read_train_status())

# -------- Mark attendance page --------
@app.route("/mark_attendance", methods=["GET"])
def mark_attendance_page():
    return render_template("mark_attendance.html")
"""
# -------- Recognize face endpoint (POST image) --------
@app.route("/recognize_face", methods=["POST"])
def recognize_face():
    if "image" not in request.files:
        return jsonify({"recognized": False, "error":"no image"}), 400
    img_file = request.files["image"]
    try:
        emb = extract_embedding_for_image(img_file.stream)
        if emb is None:
            return jsonify({"recognized": False, "error":"no face detected"}), 200
        # attempt prediction
        from model import load_model_if_exists, predict_with_model
        clf = load_model_if_exists()
        if clf is None:
            return jsonify({"recognized": False, "error":"model not trained"}), 200
        pred_label, conf = predict_with_model(clf, emb)
        # threshold confidence
        if conf < 0.5:
            return jsonify({"recognized": False, "confidence": float(conf)}), 200
        # find student name
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM students WHERE id=?", (int(pred_label),))
        row = c.fetchone()
        name = row[0] if row else "Unknown"

         # save attendance record with timestamp
        ts = datetime.datetime.utcnow().isoformat()

        # check last attendance within 1 min
        last_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)

        c.execute("SELECT timestamp FROM attendance WHERE student_id=? ORDER BY id DESC LIMIT 1", (int(pred_label),))
        row = c.fetchone()

        if row:
            previous = datetime.datetime.fromisoformat(row[0])
            if previous > last_time:
                conn.close()
                return jsonify({
                    "recognized": True,
                    "student_id": int(pred_label),
                    "name": name,
                    "message": "Already marked recently",
                    "confidence": float(conf)
                }), 200

        # insert normally
        c.execute("INSERT INTO attendance (student_id, name, timestamp) VALUES (?, ?, ?)",
                  (int(pred_label), name, ts))
        conn.commit()
        conn.close()

        return jsonify({
            "recognized": True,
            "student_id": int(pred_label),
            "name": name,
            "confidence": float(conf)
        }), 200

    except Exception as e:
        app.logger.exception("recognize error")
        return jsonify({"recognized": False, "error": str(e)}), 500

"""
# -------- Recognize face endpoint (POST image) --------
@app.route("/recognize_face", methods=["POST"])
def recognize_face():
    if "image" not in request.files:
        return jsonify({"recognized": False, "error": "no image"}), 400
    
    img_file = request.files["image"]
    
    # Get manual subject and period selection (both required now)
    manual_subject_id = request.form.get("subject_id")  # From form data
    manual_period = request.form.get("period")  # From form data
    
    try:
        # Read image for liveness detection
        img_file.stream.seek(0)
        img_array = np.frombuffer(img_file.stream.read(), np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({"recognized": False, "error": "invalid image"}), 400
        
        # Perform liveness detection FIRST
        from liveness_detection import liveness_detector
        from face_model import face_recognizer
        
        # Detect face for liveness check
        faces = face_recognizer.detect_faces(image)
        
        if len(faces) == 0:
            return jsonify({"recognized": False, "error": "no face detected"}), 200
        
        # Get largest face
        largest_face = max(faces, key=lambda x: x[2] * x[3])
        
        # Check liveness
        is_live, liveness_score, liveness_details = liveness_detector.check_liveness(
            image, largest_face
        )
        
        if not is_live:
            app.logger.warning(f"Liveness check failed: {liveness_details}")
            return jsonify({
                "recognized": False,
                "error": "Liveness check failed",
                "liveness_score": float(liveness_score),
                "liveness_details": liveness_details
            }), 200
        
        # If liveness passed, proceed with face recognition
        img_file.stream.seek(0)
        emb = extract_embedding_for_image(img_file.stream)
        if emb is None:
            return jsonify({"recognized": False, "error": "no face detected"}), 200
        
        # Load model and predict
        from face_model import load_model_if_exists, predict_with_model, add_face_to_database
        face_database = load_model_if_exists()
        if not face_database:
            return jsonify({"recognized": False, "error": "model not trained"}), 200
        
        pred_label, conf, is_match = predict_with_model(face_database, emb)
        
        # Use the professional is_match result instead of manual threshold
        if not is_match or pred_label is None:
            return jsonify({"recognized": False, "error": "Unknown person", "confidence": float(conf)}), 200
        
        student_id = int(pred_label)
        
        # Connect to DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Verify student exists and get student name
        c.execute("SELECT name FROM students WHERE id=?", (student_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"recognized": False, "error": "Student not found in database"}), 200
        
        name = row[0]

        # --- DUPLICATE PREVENTION LOGIC ---
        # Only check non-deleted records (unmarked records are ignored)
        # Calculate the cutoff time (current time minus 1 hour)
        current_time = datetime.datetime.utcnow()
        one_hour_ago = current_time - datetime.timedelta(hours=1)

        # Check for the most recent NON-DELETED entry for this student
        c.execute("SELECT timestamp FROM attendance WHERE student_id=? AND deleted=0 ORDER BY id DESC LIMIT 1", (student_id,))
        last_entry = c.fetchone()

        if last_entry:
            # Convert stored string timestamp back to datetime object
            previous_record_time = datetime.datetime.fromisoformat(last_entry[0])
            
            if previous_record_time > one_hour_ago:
                conn.close()
                # Return scanning message to hide that attendance was already marked
                return jsonify({
                    "recognized": False,
                    "error": "Scanning...",
                    "confidence": float(conf)
                }), 200

        # --- DOUBLE-CHECK: Ensure no duplicate within last 5 seconds (race condition protection) ---
        # Only check non-deleted records
        five_seconds_ago = current_time - datetime.timedelta(seconds=5)
        c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND deleted=0 AND timestamp > ?", 
                  (student_id, five_seconds_ago.isoformat()))
        recent_count = c.fetchone()[0]
        
        if recent_count > 0:
            conn.close()
            return jsonify({
                "recognized": False,
                "error": "Scanning...",
                "confidence": float(conf)
            }), 200

        # --- INSERT NEW RECORD ---
        ts_string = current_time.isoformat()
        
        # Use manual subject and period selection (required)
        subject_id = None
        subject_code = None
        subject_name = None
        period = None
        day_of_week = current_time.isoweekday()
        
        if manual_subject_id and manual_period:
            # Manual subject and period selection by teacher
            try:
                subject_id = int(manual_subject_id)
                period = int(manual_period)
                
                c.execute("SELECT code, name FROM subjects WHERE id=?", (subject_id,))
                subj_row = c.fetchone()
                if subj_row:
                    subject_code, subject_name = subj_row
                else:
                    conn.close()
                    return jsonify({
                        "recognized": False,
                        "error": "Invalid subject selected"
                    }), 200
            except (ValueError, TypeError):
                conn.close()
                return jsonify({
                    "recognized": False,
                    "error": "Invalid subject or period"
                }), 200
        else:
            conn.close()
            return jsonify({
                "recognized": False,
                "error": "Please select subject and period"
            }), 200
        
        # Check enrollment
        c.execute("SELECT COUNT(*) FROM student_subjects WHERE student_id=? AND subject_id=?",
                 (student_id, subject_id))
        is_enrolled = c.fetchone()[0] > 0
        
        if not is_enrolled:
            conn.close()
            return jsonify({
                "recognized": False,
                "error": f"Not enrolled in {subject_code}",
                "confidence": float(conf)
            }), 200
        
        # Insert attendance with subject and period
        c.execute("""INSERT INTO attendance 
                    (student_id, name, timestamp, subject_id, subject_code, subject_name, period, day_of_week) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (student_id, name, ts_string, subject_id, subject_code, subject_name, period, day_of_week))
        
        conn.commit()
        conn.close()

        response_data = {
            "recognized": True,
            "student_id": student_id,
            "name": name,
            "status": "success",
            "confidence": float(conf),
            "liveness_score": float(liveness_score),
            "liveness_details": liveness_details,
            "subject": {
                "code": subject_code,
                "name": subject_name,
                "period": period
            }
        }
        
        return jsonify(response_data), 200

    except Exception as e:
        app.logger.exception("recognize error")
        return jsonify({"recognized": False, "error": str(e)}), 500



# -------- Attendance records & filters --------
@app.route("/attendance_record", methods=["GET"])
def attendance_record():
    period = request.args.get("period", "all")  # all, daily, weekly, monthly, custom
    subject_filter = request.args.get("subject", "all")  # all or subject_id
    search_query = request.args.get("search", "").strip()  # search by name or ID
    start_date = request.args.get("start_date", "")  # custom date range start
    end_date = request.args.get("end_date", "")  # custom date range end
    page = int(request.args.get("page", 1))  # pagination
    per_page = 50  # records per page
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check if subject columns exist
    c.execute("PRAGMA table_info(attendance)")
    columns = [col[1] for col in c.fetchall()]
    has_subject_columns = 'subject_id' in columns
    
    if has_subject_columns:
        # Base query with subject information
        q = """SELECT DISTINCT a.id, a.student_id, a.name, a.timestamp, 
                      a.subject_code, a.subject_name, a.period, a.day_of_week
               FROM attendance a
               WHERE a.deleted = 0"""
        
        count_q = """SELECT COUNT(DISTINCT a.id)
                     FROM attendance a
                     WHERE a.deleted = 0"""
        
        params = []
        
        # Add subject filter
        if subject_filter != "all":
            q += " AND a.subject_id = ?"
            count_q += " AND a.subject_id = ?"
            params.append(int(subject_filter))
        
        # Add search filter
        if search_query:
            q += " AND (a.name LIKE ? OR CAST(a.student_id AS TEXT) LIKE ?)"
            count_q += " AND (a.name LIKE ? OR CAST(a.student_id AS TEXT) LIKE ?)"
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param])
        
        # Add time period filter (custom date range takes priority)
        if start_date and end_date:
            q += " AND date(a.timestamp) BETWEEN ? AND ?"
            count_q += " AND date(a.timestamp) BETWEEN ? AND ?"
            params.extend([start_date, end_date])
            period = "custom"  # Override period to show custom range
        elif period == "daily":
            today = datetime.date.today().isoformat()
            q += " AND date(a.timestamp) = ?"
            count_q += " AND date(a.timestamp) = ?"
            params.append(today)
        elif period == "weekly":
            start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            q += " AND date(a.timestamp) >= ?"
            count_q += " AND date(a.timestamp) >= ?"
            params.append(start)
        elif period == "monthly":
            start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
            q += " AND date(a.timestamp) >= ?"
            count_q += " AND date(a.timestamp) >= ?"
            params.append(start)
        
        # Get total count for pagination
        c.execute(count_q, tuple(params))
        total_records = c.fetchone()[0]
        total_pages = (total_records + per_page - 1) // per_page
        
        # Add pagination
        offset = (page - 1) * per_page
        q += " ORDER BY a.timestamp DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        c.execute(q, tuple(params))
        rows = c.fetchall()
        
        # Get all subjects for filter dropdown
        try:
            c.execute("SELECT id, code, name FROM subjects ORDER BY code")
            subjects = c.fetchall()
        except sqlite3.OperationalError:
            subjects = []
        
        # Calculate summary statistics
        summary = calculate_attendance_summary(conn, period, subject_filter, search_query, start_date, end_date)
        
    else:
        # Old format without subjects (backward compatibility)
        q = """SELECT DISTINCT a.id, a.student_id, a.name, a.timestamp
               FROM attendance a
               WHERE a.deleted = 0"""
        
        count_q = "SELECT COUNT(DISTINCT a.id) FROM attendance a WHERE a.deleted = 0"
        params = []
        
        # Add search filter
        if search_query:
            q += " AND (a.name LIKE ? OR CAST(a.student_id AS TEXT) LIKE ?)"
            count_q += " AND (a.name LIKE ? OR CAST(a.student_id AS TEXT) LIKE ?)"
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param])
        
        # Add time period filter
        if start_date and end_date:
            q += " AND date(a.timestamp) BETWEEN ? AND ?"
            count_q += " AND date(a.timestamp) BETWEEN ? AND ?"
            params.extend([start_date, end_date])
            period = "custom"
        elif period == "daily":
            today = datetime.date.today().isoformat()
            q += " AND date(a.timestamp) = ?"
            count_q += " AND date(a.timestamp) = ?"
            params.append(today)
        elif period == "weekly":
            start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            q += " AND date(a.timestamp) >= ?"
            count_q += " AND date(a.timestamp) >= ?"
            params.append(start)
        elif period == "monthly":
            start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
            q += " AND date(a.timestamp) >= ?"
            count_q += " AND date(a.timestamp) >= ?"
            params.append(start)
        
        # Get total count
        c.execute(count_q, tuple(params))
        total_records = c.fetchone()[0]
        total_pages = (total_records + per_page - 1) // per_page
        
        # Add pagination
        offset = (page - 1) * per_page
        q += " ORDER BY a.timestamp DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        c.execute(q, tuple(params))
        
        # Convert to new format (add None for subject columns)
        old_rows = c.fetchall()
        rows = [(r[0], r[1], r[2], r[3], None, None, None, None) for r in old_rows]
        subjects = []
        summary = None
    
    conn.close()
    
    return render_template("attendance_record.html", 
                          records=rows, 
                          period=period,
                          subjects=subjects,
                          subject_filter=subject_filter,
                          has_subjects=has_subject_columns,
                          search_query=search_query,
                          start_date=start_date,
                          end_date=end_date,
                          page=page,
                          total_pages=total_pages,
                          total_records=total_records,
                          summary=summary)

def calculate_attendance_summary(conn, period, subject_filter, search_query, start_date="", end_date=""):
    """Calculate attendance summary statistics"""
    c = conn.cursor()
    
    # Get total students
    c.execute("SELECT COUNT(*) FROM students")
    total_students = c.fetchone()[0]
    
    # Build query for present students
    q = """SELECT COUNT(DISTINCT a.student_id)
           FROM attendance a
           WHERE a.deleted = 0"""
    
    params = []
    
    if subject_filter != "all":
        q += " AND a.subject_id = ?"
        params.append(int(subject_filter))
    
    if search_query:
        q += " AND (a.name LIKE ? OR CAST(a.student_id AS TEXT) LIKE ?)"
        search_param = f"%{search_query}%"
        params.extend([search_param, search_param])
    
    # Date filtering (custom range takes priority)
    if start_date and end_date:
        q += " AND date(a.timestamp) BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    elif period == "daily":
        today = datetime.date.today().isoformat()
        q += " AND date(a.timestamp) = ?"
        params.append(today)
    elif period == "weekly":
        start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        q += " AND date(a.timestamp) >= ?"
        params.append(start)
    elif period == "monthly":
        start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        q += " AND date(a.timestamp) >= ?"
        params.append(start)
    
    c.execute(q, tuple(params))
    present_count = c.fetchone()[0]
    
    # Get absent students for daily view
    absent_students = []
    if period == "daily" or (start_date and end_date and start_date == end_date):
        # Show absent students only for single-day view
        date_to_check = start_date if start_date else datetime.date.today().isoformat()
        
        absent_q = """SELECT s.id, s.name, s.roll
                      FROM students s
                      WHERE s.id NOT IN (
                          SELECT DISTINCT a.student_id
                          FROM attendance a
                          WHERE a.deleted = 0
                          AND date(a.timestamp) = ?"""
        
        absent_params = [date_to_check]
        
        if subject_filter != "all":
            absent_q += " AND a.subject_id = ?"
            absent_params.append(int(subject_filter))
        
        absent_q += ")"
        
        if search_query:
            absent_q += " AND (s.name LIKE ? OR CAST(s.id AS TEXT) LIKE ?)"
            search_param = f"%{search_query}%"
            absent_params.extend([search_param, search_param])
        
        absent_q += " ORDER BY s.name"
        
        c.execute(absent_q, tuple(absent_params))
        absent_students = c.fetchall()
    
    percentage = (present_count / total_students * 100) if total_students > 0 else 0
    
    return {
        'total_students': total_students,
        'present_count': present_count,
        'absent_count': total_students - present_count,
        'percentage': round(percentage, 1),
        'absent_students': absent_students
    }

# -------- Unmark attendance endpoint --------
@app.route("/attendance/<int:attendance_id>/unmark", methods=["POST"])
def unmark_attendance(attendance_id):
    """
    Unmark (soft delete) an attendance record
    Used when a student leaves early or attendance was marked incorrectly
    """
    try:
        data = request.get_json() or {}
        reason = data.get("reason", "").strip()
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get attendance details before unmarking
        c.execute("SELECT student_id, name, timestamp FROM attendance WHERE id=? AND deleted=0", 
                  (attendance_id,))
        record = c.fetchone()
        
        if not record:
            conn.close()
            return jsonify({"success": False, "error": "Attendance record not found or already unmarked"}), 404
        
        student_id, student_name, timestamp = record
        
        # Soft delete the attendance record
        unmark_time = datetime.datetime.utcnow().isoformat()
        c.execute("""UPDATE attendance 
                     SET deleted = 1, 
                         deleted_at = ?,
                         deleted_reason = ?
                     WHERE id = ?""",
                  (unmark_time, reason, attendance_id))
        
        # Log the unmark action in audit log
        c.execute("""INSERT INTO attendance_audit_log 
                     (attendance_id, student_id, student_name, action, reason, timestamp)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (attendance_id, student_id, student_name, "UNMARK", reason, unmark_time))
        
        conn.commit()
        conn.close()
        
        app.logger.info(f"Attendance unmarked: ID={attendance_id}, Student={student_name}, Reason={reason}")
        
        return jsonify({
            "success": True,
            "message": f"Attendance unmarked for {student_name}",
            "attendance_id": attendance_id,
            "student_name": student_name,
            "unmark_time": unmark_time
        })
        
    except Exception as e:
        app.logger.error(f"Error unmarking attendance: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# -------- Audit log viewer --------
@app.route("/attendance_audit_log", methods=["GET"])
def attendance_audit_log():
    """View audit log of all unmark actions"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT id, attendance_id, student_id, student_name, action, reason, timestamp 
                     FROM attendance_audit_log 
                     ORDER BY timestamp DESC 
                     LIMIT 1000""")
        logs = c.fetchall()
        conn.close()
        
        return render_template("audit_log.html", logs=logs)
    except Exception as e:
        return f"Error loading audit log: {e}", 500

# -------- CSV download --------
@app.route("/download_csv", methods=["GET"])
def download_csv():
    """
    Professional CSV download with comprehensive data and formatting
    Supports: period, subject, date range, search filters
    """
    period = request.args.get("period", "all")
    subject_filter = request.args.get("subject", "all")
    search_query = request.args.get("search", "").strip()
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check if subject columns exist
    c.execute("PRAGMA table_info(attendance)")
    columns = [col[1] for col in c.fetchall()]
    has_subject_columns = 'subject_id' in columns
    
    if has_subject_columns:
        # Enhanced query with subject information
        q = """SELECT a.id, a.student_id, a.name, a.timestamp, 
                      a.subject_code, a.subject_name, a.period, a.day_of_week,
                      s.roll, s.class, s.section, s.reg_no
               FROM attendance a
               LEFT JOIN students s ON a.student_id = s.id
               WHERE a.deleted = 0"""
        params = []
        
        # Subject filter
        if subject_filter != "all":
            q += " AND a.subject_id = ?"
            params.append(int(subject_filter))
        
        # Search filter
        if search_query:
            q += " AND (a.name LIKE ? OR CAST(a.student_id AS TEXT) LIKE ?)"
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param])
        
        # Date range filter (custom dates take priority)
        if start_date and end_date:
            q += " AND date(a.timestamp) BETWEEN ? AND ?"
            params.extend([start_date, end_date])
        elif period == "daily":
            today = datetime.date.today().isoformat()
            q += " AND date(a.timestamp) = ?"
            params.append(today)
        elif period == "weekly":
            start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            q += " AND date(a.timestamp) >= ?"
            params.append(start)
        elif period == "monthly":
            start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
            q += " AND date(a.timestamp) >= ?"
            params.append(start)
        
        q += " ORDER BY a.timestamp DESC"
        c.execute(q, tuple(params))
        rows = c.fetchall()
        
        # Get metadata for header
        c.execute("SELECT COUNT(DISTINCT student_id) FROM attendance WHERE deleted=0")
        unique_students = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM students")
        total_students = c.fetchone()[0]
        
        # Create professional CSV with metadata header
        output = io.StringIO()
        
        # Professional Header Section
        output.write("=" * 80 + "\n")
        output.write("SMART ATTENDANCE SYSTEM - OFFICIAL REPORT\n")
        output.write("=" * 80 + "\n")
        output.write("\n")
        output.write("INSTITUTION DETAILS:\n")
        output.write("-" * 80 + "\n")
        output.write("Institution Name    : [Your Institution Name]\n")
        output.write("Department          : Computer Science & Engineering\n")
        output.write("Academic Year       : 2025-2026\n")
        output.write("Semester            : 6th Semester\n")
        output.write("\n")
        output.write("REPORT INFORMATION:\n")
        output.write("-" * 80 + "\n")
        output.write(f"Report Generated    : {datetime.datetime.now().strftime('%A, %B %d, %Y at %I:%M:%S %p')}\n")
        output.write(f"Generated By        : Smart Attendance System v2.0\n")
        
        if start_date and end_date:
            output.write(f"Report Period       : {start_date} to {end_date}\n")
        elif period == "daily":
            output.write(f"Report Period       : {datetime.date.today().strftime('%A, %B %d, %Y')} (Today)\n")
        elif period == "weekly":
            output.write(f"Report Period       : Last 7 Days\n")
        elif period == "monthly":
            output.write(f"Report Period       : Last 30 Days\n")
        else:
            output.write(f"Report Period       : All Time Records\n")
        
        if subject_filter != "all":
            c.execute("SELECT code, name FROM subjects WHERE id=?", (int(subject_filter),))
            subj = c.fetchone()
            if subj:
                output.write(f"Subject Filter      : {subj[0]} - {subj[1]}\n")
        else:
            output.write(f"Subject Filter      : All Subjects\n")
        
        output.write("\n")
        output.write("SUMMARY STATISTICS:\n")
        output.write("-" * 80 + "\n")
        output.write(f"Total Students Enrolled       : {total_students}\n")
        output.write(f"Students with Attendance      : {unique_students}\n")
        output.write(f"Total Attendance Records      : {len(rows)}\n")
        
        if total_students > 0:
            attendance_percentage = (unique_students / total_students) * 100
            output.write(f"Overall Attendance Rate       : {attendance_percentage:.1f}%\n")
        
        output.write("\n")
        output.write("=" * 80 + "\n")
        output.write("ATTENDANCE RECORDS\n")
        output.write("=" * 80 + "\n")
        output.write("\n")
        output.write("COLUMN GUIDE:\n")
        output.write("-" * 80 + "\n")
        output.write("Att.ID    : Unique attendance record identifier\n")
        output.write("Std.ID    : Student identification number\n")
        output.write("Name      : Full name of the student\n")
        output.write("Roll No   : Student roll number\n")
        output.write("Class     : Student's class\n")
        output.write("Section   : Student's section\n")
        output.write("Reg.No    : Registration number\n")
        output.write("Sub.Code  : Subject code (e.g., CST362)\n")
        output.write("Subject   : Full subject name\n")
        output.write("Period    : Class period (1-5)\n")
        output.write("Day       : Day of the week\n")
        output.write("Date      : Date of attendance (YYYY-MM-DD)\n")
        output.write("Time      : Time of attendance (HH:MM:SS)\n")
        output.write("Status    : Attendance status\n")
        output.write("\n")
        output.write("=" * 80 + "\n")
        output.write("\n")
        
        # CSV Data Header
        output.write("Att.ID,Std.ID,Student Name,Roll No,Class,Section,Reg.No,Sub.Code,Subject Name,Period,Day,Date,Time,Status\n")
        
        # Data rows
        for r in rows:
            att_id, student_id, name, timestamp, subject_code, subject_name, period_num, day_of_week, roll, class_name, section, reg_no = r
            
            # Parse timestamp
            try:
                dt = datetime.datetime.fromisoformat(timestamp)
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M:%S")
            except:
                date_str = timestamp.split('T')[0] if 'T' in timestamp else timestamp
                time_str = timestamp.split('T')[1].split('.')[0] if 'T' in timestamp else ""
            
            # Day name
            day_names = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
            day_name = day_names.get(day_of_week, "Unknown")
            
            # Clean values for CSV (professional formatting)
            subject_code = subject_code if subject_code else "-"
            subject_name = subject_name if subject_name else "-"
            period_num = period_num if period_num else "-"
            roll = roll if roll else "-"
            class_name = class_name if class_name else "-"
            section = section if section else "-"
            reg_no = reg_no if reg_no else "-"
            
            # Escape quotes in names
            name = name.replace('"', '""')
            subject_name = subject_name.replace('"', '""')
            
            output.write(f'{att_id},{student_id},"{name}",{roll},{class_name},{section},{reg_no},{subject_code},"{subject_name}",{period_num},{day_name},{date_str},{time_str},Present\n')
        
        # Footer section with detailed summary
        output.write("\n")
        output.write("=" * 80 + "\n")
        output.write("DETAILED STATISTICS\n")
        output.write("=" * 80 + "\n")
        output.write("\n")
        
        # Calculate statistics
        if rows:
            # Date-wise breakdown
            dates = {}
            for r in rows:
                timestamp = r[3]
                try:
                    dt = datetime.datetime.fromisoformat(timestamp)
                    date_str = dt.strftime("%Y-%m-%d")
                    dates[date_str] = dates.get(date_str, 0) + 1
                except:
                    pass
            
            output.write("OVERALL METRICS:\n")
            output.write("-" * 80 + "\n")
            output.write(f"Total Attendance Records      : {len(rows)}\n")
            output.write(f"Unique Students Present       : {unique_students}\n")
            
            if dates:
                output.write(f"Date Range                    : {min(dates.keys())} to {max(dates.keys())}\n")
                output.write(f"Total Days Covered            : {len(dates)} days\n")
                output.write(f"Average Daily Attendance      : {len(rows) / len(dates):.1f} records/day\n")
            
            # Subject-wise breakdown
            subjects = {}
            for r in rows:
                subj_code = r[4] if r[4] else "Unknown"
                subj_name = r[5] if r[5] else "Unknown"
                subj_key = f"{subj_code} - {subj_name}"
                subjects[subj_key] = subjects.get(subj_key, 0) + 1
            
            output.write("\n")
            output.write("SUBJECT-WISE ATTENDANCE:\n")
            output.write("-" * 80 + "\n")
            output.write(f"{'Subject':<50} {'Records':>10} {'%':>8}\n")
            output.write("-" * 80 + "\n")
            
            for subj, count in sorted(subjects.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(rows)) * 100
                output.write(f"{subj:<50} {count:>10} {percentage:>7.1f}%\n")
            
            # Period-wise breakdown
            periods = {}
            for r in rows:
                period_num = r[6] if r[6] else "Unknown"
                periods[period_num] = periods.get(period_num, 0) + 1
            
            output.write("\n")
            output.write("PERIOD-WISE ATTENDANCE:\n")
            output.write("-" * 80 + "\n")
            output.write(f"{'Period':<20} {'Records':>10} {'%':>8}\n")
            output.write("-" * 80 + "\n")
            
            for period_num, count in sorted(periods.items(), key=lambda x: str(x[0])):
                percentage = (count / len(rows)) * 100
                period_label = f"Period {period_num}" if period_num != "Unknown" else "Unknown"
                output.write(f"{period_label:<20} {count:>10} {percentage:>7.1f}%\n")
            
            # Day-wise breakdown
            days = {}
            for r in rows:
                day_num = r[7] if r[7] else 0
                day_names = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
                day_name = day_names.get(day_num, "Unknown")
                days[day_name] = days.get(day_name, 0) + 1
            
            output.write("\n")
            output.write("DAY-WISE ATTENDANCE:\n")
            output.write("-" * 80 + "\n")
            output.write(f"{'Day':<20} {'Records':>10} {'%':>8}\n")
            output.write("-" * 80 + "\n")
            
            day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            for day in day_order:
                if day in days:
                    count = days[day]
                    percentage = (count / len(rows)) * 100
                    output.write(f"{day:<20} {count:>10} {percentage:>7.1f}%\n")
            
            # Top 10 students by attendance
            student_attendance = {}
            for r in rows:
                student_id = r[1]
                student_name = r[2]
                student_key = f"{student_name} (ID: {student_id})"
                student_attendance[student_key] = student_attendance.get(student_key, 0) + 1
            
            output.write("\n")
            output.write("TOP 10 STUDENTS BY ATTENDANCE:\n")
            output.write("-" * 80 + "\n")
            output.write(f"{'Rank':<6} {'Student':<50} {'Records':>10}\n")
            output.write("-" * 80 + "\n")
            
            sorted_students = sorted(student_attendance.items(), key=lambda x: x[1], reverse=True)[:10]
            for rank, (student, count) in enumerate(sorted_students, 1):
                output.write(f"{rank:<6} {student:<50} {count:>10}\n")
        
        output.write("\n")
        output.write("=" * 80 + "\n")
        output.write("REPORT CERTIFICATION\n")
        output.write("=" * 80 + "\n")
        output.write("\n")
        output.write("This is a computer-generated report from the Smart Attendance System.\n")
        output.write("All data has been verified and validated by the system.\n")
        output.write("\n")
        output.write(f"Report ID: ATT-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}\n")
        output.write(f"Digital Signature: VERIFIED\n")
        output.write("\n")
        output.write("For queries or clarifications, please contact the system administrator.\n")
        output.write("\n")
        output.write("=" * 80 + "\n")
        output.write("END OF REPORT\n")
        output.write("=" * 80 + "\n")
        
    else:
        # Old format without subjects (basic)
        q = "SELECT id, student_id, name, timestamp FROM attendance WHERE deleted = 0 ORDER BY timestamp DESC"
        c.execute(q)
        rows = c.fetchall()
        
        output = io.StringIO()
        output.write("# ATTENDANCE REPORT (Basic Format)\n")
        output.write(f"# Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        output.write("#\n")
        output.write("Attendance ID,Student ID,Student Name,Timestamp\n")
        for r in rows:
            name = r[2].replace('"', '""')
            output.write(f'{r[0]},{r[1]},"{name}",{r[3]}\n')
    
    conn.close()
    
    # Generate professional filename
    institution_code = "INST"  # Can be configured
    if start_date and end_date:
        filename = f"{institution_code}_Attendance_Report_{start_date}_to_{end_date}.csv"
    elif period == "daily":
        filename = f"{institution_code}_Daily_Attendance_{datetime.date.today().isoformat()}.csv"
    elif period == "weekly":
        filename = f"{institution_code}_Weekly_Attendance_{datetime.date.today().isoformat()}.csv"
    elif period == "monthly":
        filename = f"{institution_code}_Monthly_Attendance_{datetime.date.today().isoformat()}.csv"
    else:
        filename = f"{institution_code}_Complete_Attendance_Report_{datetime.date.today().isoformat()}.csv"
    
    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    
    return send_file(mem, as_attachment=True, download_name=filename, mimetype="text/csv")

# -------- Students API for listing/editing --------
@app.route("/students", methods=["GET"])
def students_list():
    """Get list of all students with error handling"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, roll, class, section, reg_no, created_at FROM students ORDER BY id ASC")
        rows = c.fetchall()
        conn.close()
        
        data = []
        for r in rows:
            data.append({
                "id": r[0],
                "name": r[1],
                "roll": r[2] if r[2] else "",
                "class": r[3] if r[3] else "",
                "section": r[4] if r[4] else "",
                "reg_no": r[5] if r[5] else "",
                "created_at": r[6] if r[6] else ""
            })
        
        app.logger.info(f"Students list loaded: {len(data)} students")
        return jsonify({"students": data, "count": len(data)})
        
    except Exception as e:
        app.logger.error(f"Error loading students: {e}")
        return jsonify({"students": [], "count": 0, "error": str(e)}), 500

@app.route("/students/<int:sid>", methods=["DELETE"])
def delete_student(sid):
    """
    Completely delete a student and all related data:
    - Student record from database
    - All attendance records
    - Dataset folder with images
    - Face encodings from recognition model
    - Audit log entry for accountability
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get student details before deletion for logging
        c.execute("SELECT name, roll, class, section FROM students WHERE id=?", (sid,))
        student = c.fetchone()
        
        if not student:
            conn.close()
            return jsonify({"deleted": False, "error": "Student not found"}), 404
        
        student_name, roll, cls, section = student
        
        # Count attendance records to be deleted
        c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=?", (sid,))
        attendance_count = c.fetchone()[0]
        
        # Delete student from database
        c.execute("DELETE FROM students WHERE id=?", (sid,))
        
        # Delete all attendance records (including deleted ones)
        c.execute("DELETE FROM attendance WHERE student_id=?", (sid,))
        
        # Log the deletion in audit log
        deletion_time = datetime.datetime.utcnow().isoformat()
        c.execute("""INSERT INTO attendance_audit_log 
                     (attendance_id, student_id, student_name, action, reason, timestamp)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (None, sid, student_name, "DELETE_STUDENT", 
                   f"Deleted student with {attendance_count} attendance records", deletion_time))
        
        conn.commit()
        conn.close()
        
        # Delete dataset folder with all images
        folder = os.path.join(DATASET_DIR, str(sid))
        images_deleted = 0
        if os.path.isdir(folder):
            import shutil
            # Count images before deletion
            images_deleted = len([f for f in os.listdir(folder) 
                                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
            shutil.rmtree(folder, ignore_errors=True)
            app.logger.info(f"Deleted dataset folder for student {sid}: {images_deleted} images")
        
        # Remove face encodings from recognition model
        try:
            from face_model import face_recognizer
            if sid in face_recognizer.face_database:
                encodings_count = len(face_recognizer.face_database[sid])
                del face_recognizer.face_database[sid]
                if sid in face_recognizer.student_names:
                    del face_recognizer.student_names[sid]
                face_recognizer.save_database()
                app.logger.info(f"Removed {encodings_count} face encodings for student {sid}")
            else:
                app.logger.info(f"No face encodings found for student {sid}")
        except Exception as e:
            app.logger.warning(f"Could not remove face encodings for student {sid}: {e}")
        
        # Auto-reorganize IDs after deletion
        reorganize_student_ids()
        
        # CRITICAL: Retrain face recognition model after deletion
        try:
            app.logger.info("Retraining face recognition model after student deletion...")
            from face_model import train_model_from_dataset
            train_success = train_model_from_dataset()
            if train_success:
                app.logger.info("Face recognition model retrained successfully")
            else:
                app.logger.warning("Face recognition model retraining failed - manual retraining may be needed")
        except Exception as e:
            app.logger.error(f"Error retraining model after deletion: {e}")
        
        app.logger.info(f"Student deleted: ID={sid}, Name={student_name}, Images={images_deleted}, Attendance={attendance_count}")
        
        return jsonify({
            "deleted": True,
            "student_id": sid,
            "student_name": student_name,
            "images_deleted": images_deleted,
            "attendance_records_deleted": attendance_count,
            "message": f"Student '{student_name}' and all related data deleted successfully"
        })
        
    except Exception as e:
        app.logger.error(f"Error deleting student {sid}: {e}")
        return jsonify({"deleted": False, "error": str(e)}), 500

def reorganize_student_ids():
    """Reorganize student IDs to be sequential (1, 2, 3, ...) without gaps"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get all students ordered by current ID
    c.execute("SELECT id, name, roll, class, section, reg_no, created_at FROM students ORDER BY id")
    students = c.fetchall()
    
    if not students:
        conn.close()
        return
    
    # Create mapping of old ID to new ID
    id_mapping = {}
    
    # Start transaction
    c.execute("BEGIN TRANSACTION")
    
    try:
        # Create temporary table
        c.execute("""CREATE TEMPORARY TABLE students_temp (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        roll TEXT,
                        class TEXT,
                        section TEXT,
                        reg_no TEXT,
                        created_at TEXT
                    )""")
        
        c.execute("""CREATE TEMPORARY TABLE attendance_temp (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER,
                        name TEXT,
                        timestamp TEXT
                    )""")
        
        # Insert students with new sequential IDs
        for new_id, (old_id, name, roll, cls, section, reg_no, created_at) in enumerate(students, 1):
            id_mapping[old_id] = new_id
            c.execute("INSERT INTO students_temp VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (new_id, name, roll, cls, section, reg_no, created_at))
        
        # Update attendance records with new student IDs
        c.execute("SELECT id, student_id, name, timestamp FROM attendance")
        attendance_records = c.fetchall()
        
        for att_id, old_student_id, name, timestamp in attendance_records:
            if old_student_id in id_mapping:
                new_student_id = id_mapping[old_student_id]
                c.execute("INSERT INTO attendance_temp (student_id, name, timestamp) VALUES (?, ?, ?)",
                         (new_student_id, name, timestamp))
        
        # Replace original tables
        c.execute("DROP TABLE students")
        c.execute("DROP TABLE attendance")
        c.execute("ALTER TABLE students_temp RENAME TO students")
        c.execute("ALTER TABLE attendance_temp RENAME TO attendance")
        
        # Reorganize dataset folders
        reorganize_dataset_folders(id_mapping)
        
        # Update face recognition database
        update_face_database_ids(id_mapping)
        
        c.execute("COMMIT")
        print(f"Reorganized {len(students)} student IDs successfully")
        
    except Exception as e:
        c.execute("ROLLBACK")
        print(f"Error reorganizing IDs: {e}")
    
    conn.close()

def reorganize_dataset_folders(id_mapping):
    """Reorganize dataset folders to match new IDs"""
    if not os.path.exists(DATASET_DIR):
        return
    
    # Create temporary directory
    temp_dir = os.path.join(DATASET_DIR, "temp_reorganize")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # Move folders to temporary location with new names
        for old_id, new_id in id_mapping.items():
            old_folder = os.path.join(DATASET_DIR, str(old_id))
            temp_folder = os.path.join(temp_dir, str(new_id))
            
            if os.path.exists(old_folder):
                import shutil
                shutil.move(old_folder, temp_folder)
        
        # Move folders back to dataset directory
        for new_id in id_mapping.values():
            temp_folder = os.path.join(temp_dir, str(new_id))
            new_folder = os.path.join(DATASET_DIR, str(new_id))
            
            if os.path.exists(temp_folder):
                import shutil
                shutil.move(temp_folder, new_folder)
        
        # Remove temporary directory
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"Error reorganizing dataset folders: {e}")

def update_face_database_ids(id_mapping):
    """Update face recognition database with new student IDs"""
    try:
        from face_model import load_model_if_exists, save_face_database
        
        face_database = load_model_if_exists()
        if not face_database:
            return
        
        # Create new database with updated IDs
        new_face_database = {}
        
        for old_id, encodings in face_database.items():
            if old_id in id_mapping:
                new_id = id_mapping[old_id]
                new_face_database[new_id] = encodings
        
        # Save updated database
        save_face_database(new_face_database)
        print(f"Updated face database with {len(new_face_database)} students")
        
    except Exception as e:
        print(f"Error updating face database: {e}")

# Add route to manually trigger reorganization
@app.route("/reorganize_ids", methods=["POST"])
def reorganize_ids_route():
    """Manual route to reorganize student IDs"""
    try:
        reorganize_student_ids()
        return jsonify({"success": True, "message": "Student IDs reorganized successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Add route to clean up duplicate attendance records
@app.route("/cleanup_duplicates", methods=["POST"])
def cleanup_duplicates():
    """Remove duplicate attendance records (same student, same hour)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Find and remove duplicates (keep only the first record per student per hour)
        c.execute("""
            DELETE FROM attendance 
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM attendance 
                GROUP BY student_id, DATE(timestamp), strftime('%H', timestamp)
            )
        """)
        
        deleted_count = c.rowcount
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True, 
            "message": f"Cleaned up {deleted_count} duplicate records"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -------- Camera Configuration Routes --------
@app.route("/camera_config")
def camera_config_page():
    return render_template("camera_config.html")

@app.route("/api/camera/list", methods=["GET"])
def list_cameras():
    """List available cameras with enhanced detection"""
    try:
        cameras = []
        
        # Test cameras 0-10 more thoroughly
        for i in range(11):
            try:
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    # Try to set higher resolution for DroidCam detection
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        height, width = frame.shape[:2]
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        
                        # Determine camera type with better logic
                        camera_type = "Unknown"
                        is_droidcam = False
                        
                        if i == 0:
                            camera_type = "💻 Laptop Webcam"
                        elif i == 2 or i == 3:
                            # These are commonly DroidCam indices
                            camera_type = "📱 DroidCam (Phone Camera)"
                            is_droidcam = True
                        elif width >= 1280 or height >= 720:
                            camera_type = "📱 High-Res External Camera (Likely DroidCam)"
                            is_droidcam = True
                        elif i > 0:
                            camera_type = "📷 External Camera"
                        
                        cameras.append({
                            "index": i,
                            "name": camera_type,
                            "resolution": f"{width}x{height}",
                            "fps": fps,
                            "available": True,
                            "is_droidcam": is_droidcam,
                            "priority": 10 if is_droidcam else (5 if i == 0 else 1)
                        })
                cap.release()
            except Exception as e:
                print(f"Error testing camera {i}: {e}")
                continue
        
        # Sort cameras by priority (DroidCam first)
        cameras.sort(key=lambda x: x['priority'], reverse=True)
        
        return jsonify({"cameras": cameras, "total": len(cameras)})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/camera/set_active", methods=["POST"])
def set_active_camera():
    """Set the active camera for the application"""
    try:
        data = request.get_json()
        camera_index = data.get("camera_index", 0)
        
        # Save camera configuration
        config_file = "camera_config.json"
        config = {
            "active_camera": camera_index,
            "last_updated": datetime.datetime.now().isoformat()
        }
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        return jsonify({
            "success": True,
            "message": f"Camera {camera_index} set as active",
            "camera_index": camera_index
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/camera/current", methods=["GET"])
def get_current_camera():
    """Get current camera configuration"""
    try:
        config_file = "camera_config.json"
        
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
            camera_index = config.get("active_camera", 0)
        else:
            camera_index = 0
        
        # Test current camera
        cap = cv2.VideoCapture(camera_index)
        if cap.isOpened():
            # Try to set higher resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            
            ret, frame = cap.read()
            if ret:
                height, width = frame.shape[:2]
                fps = cap.get(cv2.CAP_PROP_FPS)
                cap.release()
                
                return jsonify({
                    "camera_index": camera_index,
                    "resolution": f"{width}x{height}",
                    "fps": fps,
                    "status": "active"
                })
        
        cap.release()
        return jsonify({
            "camera_index": camera_index,
            "status": "error",
            "message": "Camera not accessible"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/camera/test_droidcam", methods=["POST"])
def test_droidcam_specifically():
    """Test specific camera indices that are commonly DroidCam"""
    try:
        droidcam_results = []
        
        # Test common DroidCam indices
        for camera_index in [1, 2, 3, 4]:
            try:
                cap = cv2.VideoCapture(camera_index)
                if cap.isOpened():
                    # Try different resolutions to detect DroidCam
                    resolutions = [
                        (1920, 1080),  # Full HD
                        (1280, 720),   # HD
                        (640, 480)     # Standard
                    ]
                    
                    best_resolution = None
                    
                    for width, height in resolutions:
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                        
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            actual_height, actual_width = frame.shape[:2]
                            if actual_width >= width * 0.8 and actual_height >= height * 0.8:
                                best_resolution = f"{actual_width}x{actual_height}"
                                break
                    
                    if best_resolution:
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        droidcam_results.append({
                            "index": camera_index,
                            "resolution": best_resolution,
                            "fps": fps,
                            "likely_droidcam": True
                        })
                
                cap.release()
            except Exception as e:
                print(f"Error testing camera {camera_index}: {e}")
        
        return jsonify({
            "droidcam_cameras": droidcam_results,
            "found": len(droidcam_results) > 0
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/camera/test", methods=["POST"])
def test_camera():
    """Test a specific camera"""
    try:
        data = request.get_json()
        camera_index = data.get("camera_index", 0)
        
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            return jsonify({
                "success": False,
                "message": f"Cannot open camera {camera_index}"
            })
        
        # Try to set higher resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        ret, frame = cap.read()
        if not ret:
            cap.release()
            return jsonify({
                "success": False,
                "message": f"Cannot read from camera {camera_index}"
            })
        
        height, width = frame.shape[:2]
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        
        return jsonify({
            "success": True,
            "message": f"Camera {camera_index} working",
            "resolution": f"{width}x{height}",
            "fps": fps
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# ---------------- Subject Management Routes ------------------------
@app.route("/subjects", methods=["GET"])
def get_subjects():
    """Get all subjects"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, code, name, teacher, created_at FROM subjects ORDER BY code")
        rows = c.fetchall()
        conn.close()
        
        subjects = []
        for r in rows:
            subjects.append({
                "id": r[0],
                "code": r[1],
                "name": r[2],
                "teacher": r[3] if r[3] else "",
                "created_at": r[4] if r[4] else ""
            })
        
        return jsonify({"subjects": subjects, "count": len(subjects)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/timetable", methods=["GET"])
def get_timetable():
    """Get current timetable"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""SELECT t.id, t.day_of_week, t.period, t.start_time, t.end_time,
                            s.id, s.code, s.name, s.teacher
                     FROM timetable t
                     JOIN subjects s ON t.subject_id = s.id
                     ORDER BY t.day_of_week, t.period""")
        rows = c.fetchall()
        conn.close()
        
        timetable = []
        for r in rows:
            timetable.append({
                "id": r[0],
                "day_of_week": r[1],
                "period": r[2],
                "start_time": r[3],
                "end_time": r[4],
                "subject": {
                    "id": r[5],
                    "code": r[6],
                    "name": r[7],
                    "teacher": r[8]
                }
            })
        
        return jsonify({"timetable": timetable, "count": len(timetable)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/current_period", methods=["GET"])
def get_current_period():
    """Get current period based on time"""
    import datetime
    now = datetime.datetime.now()
    day_of_week = now.isoweekday()  # 1=Monday, 7=Sunday
    current_time = now.strftime("%H:%M")
    
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""SELECT t.period, t.start_time, t.end_time,
                            s.id, s.code, s.name, s.teacher
                     FROM timetable t
                     JOIN subjects s ON t.subject_id = s.id
                     WHERE t.day_of_week = ? 
                     AND t.start_time <= ? 
                     AND t.end_time >= ?
                     LIMIT 1""",
                  (day_of_week, current_time, current_time))
        row = c.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                "found": True,
                "period": row[0],
                "start_time": row[1],
                "end_time": row[2],
                "subject": {
                    "id": row[3],
                    "code": row[4],
                    "name": row[5],
                    "teacher": row[6]
                }
            })
        else:
            return jsonify({"found": False, "message": "No class scheduled now"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/student/<int:student_id>/subjects", methods=["GET"])
def get_student_subjects(student_id):
    """Get subjects enrolled by a student"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""SELECT s.id, s.code, s.name, s.teacher, ss.enrolled_at
                     FROM student_subjects ss
                     JOIN subjects s ON ss.subject_id = s.id
                     WHERE ss.student_id = ?
                     ORDER BY s.code""",
                  (student_id,))
        rows = c.fetchall()
        conn.close()
        
        subjects = []
        for r in rows:
            subjects.append({
                "id": r[0],
                "code": r[1],
                "name": r[2],
                "teacher": r[3],
                "enrolled_at": r[4]
            })
        
        return jsonify({"subjects": subjects, "count": len(subjects)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/student/<int:student_id>/enroll", methods=["POST"])
def enroll_student_in_subject(student_id):
    """Enroll a student in a subject"""
    try:
        data = request.get_json()
        subject_id = data.get("subject_id")
        
        if not subject_id:
            return jsonify({"error": "subject_id required"}), 400
        
        conn = get_db_connection()
        c = conn.cursor()
        
        now = datetime.datetime.utcnow().isoformat()
        try:
            c.execute("""INSERT INTO student_subjects (student_id, subject_id, enrolled_at)
                        VALUES (?, ?, ?)""",
                     (student_id, subject_id, now))
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Student enrolled successfully"})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "Student already enrolled in this subject"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- run ------------------------
@app.route("/health", methods=["GET"])
def health_check():
    """System health check endpoint"""
    try:
        # Check database
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM students")
        student_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM attendance WHERE deleted=0")
        attendance_count = c.fetchone()[0]
        conn.close()
        
        # Check face model
        model_exists = os.path.exists(MODEL_PATH)
        
        # Check dataset
        dataset_exists = os.path.exists(DATASET_DIR)
        
        return jsonify({
            "status": "healthy",
            "database": {
                "connected": True,
                "students": student_count,
                "attendance": attendance_count
            },
            "face_model": {
                "exists": model_exists
            },
            "dataset": {
                "exists": dataset_exists
            }
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    app.run(debug=True)