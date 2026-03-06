"""
FaceNet-based Face Recognition
Uses pre-trained InceptionResnetV1 model trained on VGGFace2
Much better than MobileNetV2 for face recognition!
"""
import os
import cv2
import numpy as np
import pickle
import json
from datetime import datetime
import threading
import time
from sklearn.metrics.pairwise import cosine_similarity
import warnings
warnings.filterwarnings('ignore')

# Import FaceNet
from facenet_pytorch import MTCNN, InceptionResnetV1
import torch
from PIL import Image

# Paths
MODEL_PATH = "face_encodings.pkl"
TRAIN_STATUS_FILE = "train_status.json"

class FaceNetRecognizer:
    def __init__(self):
        print("Initializing FaceNet Face Recognition System...")
        
        # Set device
        self.device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        print(f"  Using device: {self.device}")
        
        # Initialize MTCNN for face detection
        self.mtcnn = MTCNN(
            image_size=160,
            margin=20,
            min_face_size=20,
            thresholds=[0.6, 0.7, 0.7],
            factor=0.709,
            post_process=True,
            device=self.device,
            keep_all=False  # Only detect the most prominent face
        )
        
        # Initialize InceptionResnetV1 with pre-trained weights
        self.facenet = InceptionResnetV1(
            pretrained='vggface2',  # Pre-trained on VGGFace2 dataset
            classify=False,  # We want embeddings, not classification
            device=self.device
        ).eval()
        
        print("✓ FaceNet Model loaded (Pre-trained on VGGFace2)")
        print("  - Model: InceptionResnetV1")
        print("  - Training: 3.3M faces, 9,131 identities")
        print("  - Embedding size: 512 dimensions")
        
        # Face database
        self.face_database = {}
        self.student_names = {}
        
        # Auto-training settings
        self.auto_train_enabled = True
        self.min_faces_for_training = 3
        self.training_lock = threading.Lock()
        
        # Load existing data
        self.load_database()
        
        print("✓ FaceNet Face Recognition System Ready!")
    
    def detect_faces(self, image):
        """Detect faces using MTCNN"""
        try:
            # Convert BGR to RGB
            if len(image.shape) == 3 and image.shape[2] == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image
            
            # Convert to PIL Image
            pil_image = Image.fromarray(image_rgb)
            
            # Detect faces
            boxes, probs = self.mtcnn.detect(pil_image)
            
            if boxes is None:
                return np.array([])
            
            # Convert to (x, y, w, h) format
            faces = []
            for box in boxes:
                x1, y1, x2, y2 = box
                x, y = int(x1), int(y1)
                w, h = int(x2 - x1), int(y2 - y1)
                faces.append([x, y, w, h])
            
            return np.array(faces)
            
        except Exception as e:
            print(f"Face detection error: {e}")
            return np.array([])
    
    def extract_face_encoding(self, image_input):
        """Extract face encoding using FaceNet"""
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
            
            # Convert BGR to RGB
            if len(image.shape) == 3 and image.shape[2] == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image
            
            # Convert to PIL Image
            pil_image = Image.fromarray(image_rgb)
            
            # Detect and align face
            face_tensor = self.mtcnn(pil_image)
            
            if face_tensor is None:
                return None
            
            # Move to device
            face_tensor = face_tensor.unsqueeze(0).to(self.device)
            
            # Extract embedding
            with torch.no_grad():
                embedding = self.facenet(face_tensor)
            
            # Convert to numpy
            embedding = embedding.cpu().numpy()[0]
            
            return embedding
            
        except Exception as e:
            print(f"Error extracting face encoding: {e}")
            return None
    
    def add_face_encoding(self, student_id, encoding, student_name=None):
        """Add face encoding to database"""
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
                
                # Keep only high-quality encodings
                threshold = max(0.85, np.percentile(similarities, 20))
                
                good_encodings = []
                for i, sim in enumerate(similarities):
                    if sim >= threshold:
                        good_encodings.append(encodings[i])
                
                # Ensure we keep at least 5 encodings
                if len(good_encodings) >= 5:
                    self.face_database[student_id] = good_encodings
                    self.save_database()
                    print(f"✓ Auto-training complete for student {student_id}: {len(good_encodings)} encodings")
                
            except Exception as e:
                print(f"Auto-training error for student {student_id}: {e}")
    
    def predict_face(self, encoding):
        """Predict student ID from face encoding"""
        if encoding is None or not self.face_database:
            return None, 0.0, False
        
        # Calculate similarities with all students
        student_scores = {}
        
        for student_id, stored_encodings in self.face_database.items():
            if not stored_encodings:
                continue
            
            # Calculate similarities
            similarities = []
            for stored_encoding in stored_encodings:
                similarity = cosine_similarity([encoding], [stored_encoding])[0][0]
                similarities.append(similarity)
            
            # Use multiple metrics
            max_sim = max(similarities)
            avg_sim = np.mean(similarities)
            top3_avg = np.mean(sorted(similarities, reverse=True)[:min(3, len(similarities))])
            
            # Weighted score
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
        
        # FaceNet threshold (more accurate, can use higher threshold)
        if len(self.face_database) == 1:
            threshold = 0.70
            is_match = best_max >= threshold
        else:
            # Adaptive threshold with better discrimination
            base_threshold = 0.88  # Increased from 0.85 for better accuracy
            
            if len(sorted_students) > 1:
                second_best_score = sorted_students[1][1]['score']
                separation = best_score - second_best_score
                
                # Require good separation
                if separation > 0.20:
                    threshold = 0.85
                elif separation > 0.15:
                    threshold = 0.88
                else:
                    threshold = 0.92  # Very strict if faces are similar
            else:
                threshold = base_threshold
            
            is_match = best_max >= threshold
        
        return best_student_id, best_max, is_match
    
    def train_from_dataset(self, dataset_dir, progress_callback=None):
        """Train from dataset directory"""
        if progress_callback:
            progress_callback(0, "Starting training with FaceNet...")
        
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
                
                # Process images
                image_files = [f for f in os.listdir(folder_path) 
                              if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                
                encodings = []
                
                for img_file in image_files:
                    img_path = os.path.join(folder_path, img_file)
                    encoding = self.extract_face_encoding(img_path)
                    
                    if encoding is not None:
                        encodings.append(encoding)
                    
                    time.sleep(0.01)  # Small delay
                
                # Store encodings
                if encodings:
                    self.face_database[student_id] = encodings
                    total_processed += len(encodings)
                    
                    # Auto-optimize
                    self.auto_train_student(student_id)
                
            except ValueError:
                continue
        
        if progress_callback:
            progress_callback(95, "Saving model...")
        
        # Save the database
        self.save_database()
        
        if progress_callback:
            progress_callback(100, f"Training complete! Processed {len(self.face_database)} students with {total_processed} samples.")
        
        return len(self.face_database) > 0
    
    def save_database(self):
        """Save face database"""
        try:
            database_data = {
                'face_database': {k: [enc.tolist() for enc in v] for k, v in self.face_database.items()},
                'student_names': self.student_names,
                'timestamp': datetime.now().isoformat(),
                'version': '3.0',
                'model': 'FaceNet-VGGFace2'
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
                    face_db = data['face_database']
                    self.face_database = {k: [np.array(enc) for enc in v] for k, v in face_db.items()}
                    self.student_names = data.get('student_names', {})
                    model_type = data.get('model', 'Unknown')
                    print(f"✓ Loaded {len(self.face_database)} students from database ({model_type})")
                else:
                    print("Old database format detected, will retrain automatically")
                    self.face_database = {}
                    self.student_names = {}
                    
            except Exception as e:
                print(f"Error loading database: {e}")
                self.face_database = {}
                self.student_names = {}


# Global instance
face_recognizer = FaceNetRecognizer()

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
