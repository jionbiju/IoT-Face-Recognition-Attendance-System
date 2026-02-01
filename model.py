import os
import cv2
import numpy as np
import pickle

MODEL_PATH = "face_encodings.pkl"

def extract_embedding_for_image(stream_or_bytes):
    """Extract face encoding using OpenCV"""
    try:
        data = stream_or_bytes.read()
        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        if len(faces) == 0:
            return None
        
        largest_face = max(faces, key=lambda x: x[2] * x[3])
        x, y, w, h = largest_face
        
        padding = 20
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(gray.shape[1], x + w + padding)
        y2 = min(gray.shape[0], y + h + padding)
        
        face_roi = gray[y1:y2, x1:x2]
        face_roi = cv2.resize(face_roi, (100, 100))
        face_roi = cv2.equalizeHist(face_roi)
        
        # Simple feature extraction
        features = face_roi.flatten().astype(np.float32) / 255.0
        return features
    
    except Exception as e:
        print(f"Error: {e}")
        return None

def load_model_if_exists():
    """Load face database"""
    if not os.path.exists(MODEL_PATH):
        return {}
    try:
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except:
        return {}

def save_face_database(face_database):
    """Save face database"""
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(face_database, f)

def add_face_to_database(student_id, face_encoding):
    """Add face to database"""
    face_database = load_model_if_exists()
    
    if student_id not in face_database:
        face_database[student_id] = []
    
    face_database[student_id].append(face_encoding)
    
    if len(face_database[student_id]) > 10:
        face_database[student_id] = face_database[student_id][-10:]
    
    save_face_database(face_database)
    print(f"Added encoding for student {student_id}")

def predict_with_model(face_database, test_encoding):
    """Predict student from face encoding"""
    if not face_database:
        return None, 0.0, False
    
    best_match_id = None
    best_similarity = -1.0
    
    for student_id, encodings in face_database.items():
        for encoding in encodings:
            # Calculate cosine similarity
            dot_product = np.dot(test_encoding, encoding)
            norm1 = np.linalg.norm(test_encoding)
            norm2 = np.linalg.norm(encoding)
            
            if norm1 > 0 and norm2 > 0:
                similarity = dot_product / (norm1 * norm2)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_id = student_id
    
    # Determine if it's a match
    is_match = best_similarity > 0.85  # High threshold for accuracy
    confidence = best_similarity
    
    return best_match_id, confidence, is_match

def auto_train_from_dataset(dataset_dir):
    """Auto-train from dataset"""
    face_database = {}
    
    if not os.path.exists(dataset_dir):
        return face_database
    
    student_dirs = [d for d in os.listdir(dataset_dir) if os.path.isdir(os.path.join(dataset_dir, d))]
    
    for sid in student_dirs:
        folder = os.path.join(dataset_dir, sid)
        files = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        
        student_encodings = []
        for fn in files:
            path = os.path.join(folder, fn)
            
            with open(path, 'rb') as f:
                encoding = extract_embedding_for_image(f)
                if encoding is not None:
                    student_encodings.append(encoding)
        
        if student_encodings:
            face_database[int(sid)] = student_encodings
            print(f"Loaded {len(student_encodings)} encodings for student {sid}")
    
    if face_database:
        save_face_database(face_database)
        print(f"Auto-training complete: {len(face_database)} students")
    
    return face_database

def train_model_background(dataset_dir, progress_callback=None):
    """Train model in background"""
    try:
        if progress_callback:
            progress_callback(10, "Starting training...")
        
        face_database = auto_train_from_dataset(dataset_dir)
        
        if progress_callback:
            if face_database:
                total_encodings = sum(len(encodings) for encodings in face_database.values())
                progress_callback(100, f"Complete: {len(face_database)} students, {total_encodings} encodings")
            else:
                progress_callback(0, "No training data found")
    
    except Exception as e:
        if progress_callback:
            progress_callback(0, f"Training failed: {str(e)}")