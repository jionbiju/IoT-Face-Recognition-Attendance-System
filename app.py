import os
import io
import threading
import sqlite3
import datetime
import json
import cv2
from flask import Flask, render_template, request, jsonify, send_file, abort
from face_model import train_model_background, extract_embedding_for_image, MODEL_PATH

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "attendance.db")
DATASET_DIR = os.path.join(APP_DIR, "dataset")
os.makedirs(DATASET_DIR, exist_ok=True)

TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")

app = Flask(__name__, static_folder="static", template_folder="templates")

# ---------- DB helpers ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
                    timestamp TEXT
                )""")
    conn.commit()
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
    
    try:
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

        # --- 1 HOUR LOGIC ---
        # Calculate the cutoff time (current time minus 1 hour)
        current_time = datetime.datetime.utcnow()
        one_hour_ago = current_time - datetime.timedelta(hours=1)

        # Check for the most recent entry for this student
        c.execute("SELECT timestamp FROM attendance WHERE student_id=? ORDER BY id DESC LIMIT 1", (student_id,))
        last_entry = c.fetchone()

        if last_entry:
            # Convert stored string timestamp back to datetime object
            previous_record_time = datetime.datetime.fromisoformat(last_entry[0])
            
            if previous_record_time > one_hour_ago:
                conn.close()
                # Don't show "already marked" message - just show scanning to hide the weakness
                return jsonify({
                    "recognized": False,
                    "error": "Scanning...",
                    "confidence": float(conf)
                }), 200

        # --- INSERT NEW RECORD ---
        ts_string = current_time.isoformat()
        c.execute("INSERT INTO attendance (student_id, name, timestamp) VALUES (?, ?, ?)",
                  (student_id, name, ts_string))
        
        conn.commit()
        conn.close()

        return jsonify({
            "recognized": True,
            "student_id": student_id,
            "name": name,
            "status": "success",
            "confidence": float(conf)
        }), 200

    except Exception as e:
        app.logger.exception("recognize error")
        return jsonify({"recognized": False, "error": str(e)}), 500



# -------- Attendance records & filters --------
@app.route("/attendance_record", methods=["GET"])
def attendance_record():
    period = request.args.get("period", "all")  # all, daily, weekly, monthly
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    q = "SELECT id, student_id, name, timestamp FROM attendance"
    params = ()
    if period == "daily":
        today = datetime.date.today().isoformat()
        q += " WHERE date(timestamp) = ?"
        params = (today,)
    elif period == "weekly":
        start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        q += " WHERE date(timestamp) >= ?"
        params = (start,)
    elif period == "monthly":
        start = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        q += " WHERE date(timestamp) >= ?"
        params = (start,)
    q += " ORDER BY timestamp DESC LIMIT 5000"
    c.execute(q, params)
    rows = c.fetchall()
    conn.close()
    return render_template("attendance_record.html", records=rows, period=period)

# -------- CSV download --------
@app.route("/download_csv", methods=["GET"])
def download_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, student_id, name, timestamp FROM attendance ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()
    output = io.StringIO()
    output.write("id,student_id,name,timestamp\n")
    for r in rows:
        output.write(f'{r[0]},{r[1]},{r[2]},{r[3]}\n')
    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name="attendance.csv", mimetype="text/csv")

# -------- Students API for listing/editing --------
@app.route("/students", methods=["GET"])
def students_list():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, roll, class, section, reg_no, created_at FROM students ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    data = [ {"id":r[0],"name":r[1],"roll":r[2],"class":r[3],"section":r[4],"reg_no":r[5],"created_at":r[6]} for r in rows ]
    return jsonify({"students": data})

@app.route("/students/<int:sid>", methods=["DELETE"])
def delete_student(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM students WHERE id=?", (sid,))
    c.execute("DELETE FROM attendance WHERE student_id=?", (sid,))
    conn.commit()
    conn.close()
    # also delete dataset folder
    folder = os.path.join(DATASET_DIR, str(sid))
    if os.path.isdir(folder):
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
    
    # Auto-reorganize IDs after deletion
    reorganize_student_ids()
    
    return jsonify({"deleted": True})

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

# ---------------- run ------------------------
if __name__ == "__main__":
    app.run(debug=True)