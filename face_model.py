import os
import cv2
import numpy as np
import pickle
import json
from datetime import datetime
import threading
import time
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense, Lambda
from tensorflow.keras.applications import MobileNetV2
import warnings
warnings.filterwarnings('ignore')

# Import camera configuration
try:
    from camera_config import CameraManager
    CAMERA_MANAGER = CameraManager()
except ImportError:
    CAMERA_MANAGER = None
    print("⚠ Camera configuration not available, using default camera")

# Paths
MODEL_PATH = "face_encodings.pkl"
TRAIN_STATUS_FILE = "train_status.json"

class AdvancedFaceRecognizer:
    def __init__(self):
        print("Initializing Advanced Face Recognition System...")
        
        # Initialize face detector (MTCNN-like using OpenCV DNN)
        self.setup_face_detector()
        
        # Initialize face recognition model (MobileNet-based)
        self.setup_face_recognition_model()
        
        # Face database
        self.face_database = {}
        self.student_names = {}
        
        # Auto-training settings
        self.auto_train_enabled = True
        self.min_faces_for_training = 3
        self.training_lock = threading.Lock()
        
        # Load existing data
        self.load_database()
        
        print("✓ Advanced Face Recognition System Ready!")
    
    def setup_face_detector(self):
        """Setup high-accuracy face detector using OpenCV DNN"""
        try:
            # Download and load DNN face detector
            model_file = "opencv_face_detector_uint8.pb"
            config_file = "opencv_face_detector.pbtxt"
            
            if not os.path.exists(model_file):
                print("Downloading DNN face detector...")
                import urllib.request
                urllib.request.urlretrieve(
                    "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/opencv_face_detector_uint8.pb",
                    model_file
                )
                urllib.request.urlretrieve(
                    "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/opencv_face_detector.pbtxt",
                    config_file
                )
            
            self.face_net = cv2.dnn.readNetFromTensorflow(model_file, config_file)
            self.use_dnn_detector = True
            print("✓ DNN Face Detector loaded")
            
        except Exception as e:
            print(f"DNN detector failed, using Haar cascade: {e}")
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            self.use_dnn_detector = False
    
    def setup_face_recognition_model(self):
        """Setup MobileNetV2 for face recognition (pre-trained on ImageNet)"""
        try:
            # Use MobileNetV2 with ImageNet pre-training
            # Even though trained on objects, transfer learning works well for faces
            input_shape = (160, 160, 3)
            
            base_model = MobileNetV2(
                input_shape=input_shape,
                include_top=False,
                weights='imagenet',  # Pre-trained weights are crucial
                pooling='avg'
            )
            
            # Add custom layers for face recognition
            x = base_model.output
            x = Dense(512, activation='relu', name='feature_dense')(x)
            x = Lambda(lambda x: tf.nn.l2_normalize(x, axis=1), name='l2_normalize')(x)
            
            self.face_model = Model(inputs=base_model.input, outputs=x)
            self.input_size = (160, 160)
            
            # Freeze base model layers
            for layer in base_model.layers:
                layer.trainable = False
            
            print("✓ MobileNetV2 Face Recognition Model loaded (ImageNet pre-trained)")
            
        except Exception as e:
            print(f"Error loading MobileNetV2: {e}")
            self.setup_simple_cnn_model()
    
    def setup_simple_cnn_model(self):
        """Fallback simple CNN model"""
        from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dropout
        
        input_size = (160, 160, 3)
        
        model = tf.keras.Sequential([
            Conv2D(32, (3, 3), activation='relu', input_shape=input_size),
            MaxPooling2D(2, 2),
            Conv2D(64, (3, 3), activation='relu'),
            MaxPooling2D(2, 2),
            Conv2D(128, (3, 3), activation='relu'),
            MaxPooling2D(2, 2),
            Flatten(),
            Dense(512, activation='relu'),
            Dropout(0.5),
            Dense(256, activation='relu'),
            Lambda(lambda x: tf.nn.l2_normalize(x, axis=1))
        ])
        
        self.face_model = model
        self.input_size = (160, 160)
        print("✓ Simple CNN Face Model loaded")
    
    def detect_faces(self, image):
        """Detect faces using DNN or Haar cascade"""
        if self.use_dnn_detector:
            return self.detect_faces_dnn(image)
        else:
            return self.detect_faces_haar(image)
    
    def detect_faces_dnn(self, image):
        """Detect faces using DNN"""
        h, w = image.shape[:2]
        
        # Create blob from image
        blob = cv2.dnn.blobFromImage(image, 1.0, (300, 300), [104, 117, 123])
        self.face_net.setInput(blob)
        detections = self.face_net.forward()
        
        faces = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > 0.5:  # Confidence threshold
                x1 = int(detections[0, 0, i, 3] * w)
                y1 = int(detections[0, 0, i, 4] * h)
                x2 = int(detections[0, 0, i, 5] * w)
                y2 = int(detections[0, 0, i, 6] * h)
                
                # Convert to (x, y, w, h) format
                faces.append([x1, y1, x2-x1, y2-y1])
        
        return np.array(faces)
    
    def detect_faces_haar(self, image):
        """Detect faces using Haar cascade"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(40, 40),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        return faces
    
    def preprocess_face(self, image, bbox):
        """Extract and preprocess face from bounding box"""
        x, y, w, h = bbox
        
        # Add padding
        padding = 20
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(image.shape[1], x + w + padding)
        y2 = min(image.shape[0], y + h + padding)
        
        # Extract face
        face = image[y1:y2, x1:x2]
        
        if face.size == 0:
            return None
        
        # Resize to model input size (112x112 for MobileFaceNet, 160x160 for fallback)
        target_size = getattr(self, 'input_size', (112, 112))
        face = cv2.resize(face, target_size)
        
        # Normalize to [0, 1]
        face = face.astype(np.float32) / 255.0
        
        # Ensure RGB format
        if len(face.shape) == 3 and face.shape[2] == 3:
            face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        
        return face
    
    def extract_face_encoding(self, image_input):
        """Extract face encoding from image with optimizations"""
        try:
            # Handle different input types
            if isinstance(image_input, str):
                image = cv2.imread(image_input)
            else:
                image_input.seek(0)
                img_array = np.frombuffer(image_input.read(), np.uint8)
                image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            
            if image is None:
                return None
            
            # Resize image for faster processing if too large
            height, width = image.shape[:2]
            if width > 640:
                scale = 640 / width
                new_width = 640
                new_height = int(height * scale)
                image = cv2.resize(image, (new_width, new_height))
            
            # Detect faces
            faces = self.detect_faces(image)
            
            if len(faces) == 0:
                return None
            
            # Get the largest face
            largest_face = max(faces, key=lambda x: x[2] * x[3])
            
            # Preprocess face
            face = self.preprocess_face(image, largest_face)
            
            if face is None:
                return None
            
            # Extract encoding using the model (with batch processing for efficiency)
            face_batch = np.expand_dims(face, axis=0)
            
            # Use predict with verbose=0 for faster inference
            with tf.device('/CPU:0'):  # Force CPU for consistency
                encoding = self.face_model.predict(face_batch, verbose=0)[0]
            
            return encoding
            
        except Exception as e:
            print(f"Error extracting face encoding: {e}")
            return None
    
    def add_face_encoding(self, student_id, encoding, student_name=None):
        """Add face encoding to database with automatic training"""
        if encoding is None:
            return False
        
        # Store student name
        if student_name:
            self.student_names[student_id] = student_name
        
        # Add encoding to database
        if student_id not in self.face_database:
            self.face_database[student_id] = []
        
        self.face_database[student_id].append(encoding)
        
        # Auto-save
        self.save_database()
        
        # Check if we should auto-train
        if (self.auto_train_enabled and 
            len(self.face_database[student_id]) >= self.min_faces_for_training):
            
            # Start background training
            threading.Thread(
                target=self.auto_train_student,
                args=(student_id,),
                daemon=True
            ).start()
        
        return True
    
    def auto_train_student(self, student_id):
        """Automatically optimize encodings for a student"""
        with self.training_lock:
            try:
                encodings = self.face_database.get(student_id, [])
                if len(encodings) < 3:
                    return
                
                print(f"Auto-training student {student_id}...")
                
                # Calculate mean encoding (centroid)
                encodings_array = np.array(encodings)
                mean_encoding = np.mean(encodings_array, axis=0)
                
                # Calculate similarities to mean
                similarities = []
                for enc in encodings:
                    sim = cosine_similarity([enc], [mean_encoding])[0][0]
                    similarities.append(sim)
                
                # Keep only high-quality encodings (above median similarity)
                median_sim = np.median(similarities)
                threshold = max(0.8, median_sim)  # At least 80% similarity
                
                good_encodings = []
                for i, sim in enumerate(similarities):
                    if sim >= threshold:
                        good_encodings.append(encodings[i])
                
                # Update database with optimized encodings
                if len(good_encodings) >= 2:
                    self.face_database[student_id] = good_encodings
                    self.save_database()
                    print(f"✓ Auto-training complete for student {student_id}: {len(good_encodings)} high-quality encodings")
                
            except Exception as e:
                print(f"Auto-training error for student {student_id}: {e}")
    
    def predict_face(self, encoding):
        """Predict student ID from face encoding with improved discrimination"""
        if encoding is None or not self.face_database:
            return None, 0.0, False
        
        # Calculate similarities with all students
        student_scores = {}
        
        for student_id, stored_encodings in self.face_database.items():
            if not stored_encodings:
                continue
            
            # Calculate similarities with all encodings for this student
            similarities = []
            for stored_encoding in stored_encodings:
                similarity = cosine_similarity([encoding], [stored_encoding])[0][0]
                similarities.append(similarity)
            
            # Use multiple metrics for better discrimination
            max_sim = max(similarities)
            avg_sim = np.mean(similarities)
            top3_avg = np.mean(sorted(similarities, reverse=True)[:min(3, len(similarities))])
            
            # Weighted score: prioritize max but consider average
            score = 0.6 * max_sim + 0.3 * top3_avg + 0.1 * avg_sim
            
            student_scores[student_id] = {
                'max': max_sim,
                'avg': avg_sim,
                'top3': top3_avg,
                'score': score
            }
        
        # Find best match
        best_student_id = max(student_scores.keys(), key=lambda k: student_scores[k]['score'])
        best_score = student_scores[best_student_id]['score']
        best_max = student_scores[best_student_id]['max']
        
        # Calculate second best for discrimination
        sorted_students = sorted(student_scores.items(), key=lambda x: x[1]['score'], reverse=True)
        
        # Dynamic threshold based on discrimination
        if len(self.face_database) == 1:
            threshold = 0.65  # More lenient for single student
            is_match = best_max >= threshold
        else:
            # Use adaptive threshold
            base_threshold = 0.78  # Increased from 0.75
            
            # If there's a clear winner (good separation), be more lenient
            if len(sorted_students) > 1:
                second_best_score = sorted_students[1][1]['score']
                separation = best_score - second_best_score
                
                # If separation is large (>0.15), we can be more confident
                if separation > 0.15:
                    threshold = 0.75
                elif separation > 0.10:
                    threshold = 0.77
                else:
                    threshold = base_threshold
            else:
                threshold = base_threshold
            
            is_match = best_max >= threshold
        
        return best_student_id, best_max, is_match
    
    def train_from_dataset(self, dataset_dir, progress_callback=None):
        """Train from dataset directory with progress tracking"""
        if progress_callback:
            progress_callback(0, "Starting training...")
        
        # Clear existing database
        self.face_database = {}
        self.student_names = {}
        
        # Get student folders
        student_folders = [f for f in os.listdir(dataset_dir) 
                          if os.path.isdir(os.path.join(dataset_dir, f))]
        
        total_folders = len(student_folders)
        total_processed = 0
        
        for idx, folder_name in enumerate(student_folders):
            try:
                student_id = int(folder_name)
                folder_path = os.path.join(dataset_dir, folder_name)
                
                if progress_callback:
                    progress = int((idx / total_folders) * 90)
                    progress_callback(progress, f"Processing student {student_id}...")
                
                # Process images in batches for better performance
                image_files = [f for f in os.listdir(folder_path) 
                              if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                encodings = []
                batch_size = 5
                
                for i in range(0, len(image_files), batch_size):
                    batch_files = image_files[i:i+batch_size]
                    
                    for img_file in batch_files:
                        img_path = os.path.join(folder_path, img_file)
                        encoding = self.extract_face_encoding(img_path)
                        
                        if encoding is not None:
                            encodings.append(encoding)
                    
                    # Small delay to prevent system overload
                    time.sleep(0.01)
                
                # Store encodings for this student
                if encodings:
                    self.face_database[student_id] = encodings
                    total_processed += len(encodings)
                    
                    # Auto-optimize encodings
                    self.auto_train_student(student_id)
                
            except ValueError:
                continue
        
        if progress_callback:
            progress_callback(95, "Saving model...")
        
        # Save the database
        self.save_database()
        
        if progress_callback:
            progress_callback(100, f"Training complete! Processed {len(self.face_database)} students with {total_processed} face samples.")
        
        return len(self.face_database) > 0
    
    def save_database(self):
        """Save face database"""
        try:
            database_data = {
                'face_database': {k: [enc.tolist() for enc in v] for k, v in self.face_database.items()},
                'student_names': self.student_names,
                'timestamp': datetime.now().isoformat(),
                'version': '2.0'
            }
            
            with open(MODEL_PATH, 'wb') as f:
                pickle.dump(database_data, f)
                
        except Exception as e:
            print(f"Error saving database: {e}")
    
    def load_database(self):
        """Load face database"""
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, 'rb') as f:
                    data = pickle.load(f)
                
                if isinstance(data, dict) and 'face_database' in data:
                    # New format
                    face_db = data['face_database']
                    self.face_database = {k: [np.array(enc) for enc in v] for k, v in face_db.items()}
                    self.student_names = data.get('student_names', {})
                    print(f"✓ Loaded {len(self.face_database)} students from database")
                else:
                    # Old format - clear and retrain
                    print("Old database format detected, will retrain automatically")
                    self.face_database = {}
                    self.student_names = {}
                    
            except Exception as e:
                print(f"Error loading database: {e}")
                self.face_database = {}
                self.student_names = {}

# Global instance
face_recognizer = AdvancedFaceRecognizer()

# API functions for compatibility
def extract_embedding_for_image(image_stream):
    """Extract face embedding from image stream"""
    return face_recognizer.extract_face_encoding(image_stream)

def add_face_to_database(student_id, face_encoding):
    """Add face encoding to database"""
    return face_recognizer.add_face_encoding(student_id, face_encoding)

def load_model_if_exists():
    """Load existing model"""
    return face_recognizer.face_database

def predict_with_model(face_database, embedding):
    """Predict using the model"""
    return face_recognizer.predict_face(embedding)

def save_face_database(face_database):
    """Save face database"""
    face_recognizer.face_database = face_database
    face_recognizer.save_database()

def auto_train_from_dataset(dataset_dir):
    """Auto train from dataset directory"""
    def dummy_callback(progress, message):
        print(f"Progress: {progress}% - {message}")
    
    return face_recognizer.train_from_dataset(dataset_dir, dummy_callback)

def train_model_background(dataset_dir, progress_callback):
    """Train model in background with progress callback"""
    try:
        success = face_recognizer.train_from_dataset(dataset_dir, progress_callback)
        if success:
            progress_callback(100, "Training completed successfully!")
        else:
            progress_callback(100, "Training failed - no valid face data found")
    except Exception as e:
        progress_callback(100, f"Training failed: {str(e)}")

# For backward compatibility
MODEL_PATH = MODEL_PATH