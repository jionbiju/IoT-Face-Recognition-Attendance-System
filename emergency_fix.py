"""
EMERGENCY FIX: Retrain face recognition model
Run this immediately after deleting a student
"""
import os
import sys
import sqlite3
import shutil

print("=" * 70)
print("EMERGENCY FIX - RETRAINING FACE RECOGNITION MODEL")
print("=" * 70)

# Step 1: Check database
print("\n[1/5] Checking database...")
try:
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute("SELECT id, name FROM students ORDER BY id")
    students = c.fetchall()
    conn.close()
    
    valid_student_ids = [str(sid) for sid, name in students]
    
    print(f"   ✓ Found {len(students)} students in database:")
    for sid, name in students:
        print(f"      ID {sid}: {name}")
except Exception as e:
    print(f"   ❌ Database error: {e}")
    sys.exit(1)

# Step 2: Check and clean dataset folders
print("\n[2/5] Checking and cleaning dataset folders...")
dataset_folders = []
orphaned_folders = []

if os.path.exists("dataset"):
    for folder in os.listdir("dataset"):
        folder_path = os.path.join("dataset", folder)
        if os.path.isdir(folder_path):
            image_count = len([f for f in os.listdir(folder_path) 
                             if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
            
            if folder in valid_student_ids:
                dataset_folders.append((folder, image_count))
                print(f"   ✓ Folder {folder}: {image_count} images (valid)")
            else:
                orphaned_folders.append((folder, image_count))
                print(f"   ⚠️  Folder {folder}: {image_count} images (ORPHANED - will be deleted)")
else:
    print("   ❌ Dataset folder not found!")
    sys.exit(1)

# Delete orphaned folders
if orphaned_folders:
    print("\n   Deleting orphaned folders...")
    for folder, count in orphaned_folders:
        folder_path = os.path.join("dataset", folder)
        try:
            shutil.rmtree(folder_path)
            print(f"      ✓ Deleted folder {folder} ({count} images)")
        except Exception as e:
            print(f"      ❌ Failed to delete folder {folder}: {e}")

if len(dataset_folders) == 0:
    print("\n   ⚠️  No valid dataset folders found!")
    print("   Clearing old model files...")
    for file in ["model.pkl", "face_encodings.pkl"]:
        if os.path.exists(file):
            os.remove(file)
            print(f"      ✓ Removed {file}")
    print("\n✅ System cleared. You can now register students.")
    sys.exit(0)

# Step 3: Remove old model files
print("\n[3/5] Removing old model files...")
for file in ["model.pkl", "face_encodings.pkl"]:
    if os.path.exists(file):
        os.remove(file)
        print(f"   ✓ Removed {file}")
    else:
        print(f"   - {file} not found (OK)")

# Step 4: Retrain model
print("\n[4/5] Retraining face recognition model...")
print("   This may take 30-60 seconds...")

try:
    from face_model import auto_train_from_dataset
    
    success = auto_train_from_dataset("dataset")
    
    if success:
        print("   ✓ Model training completed!")
    else:
        print("   ❌ Training failed!")
        sys.exit(1)
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 5: Verify model
print("\n[5/5] Verifying model...")
try:
    from face_model import load_model_if_exists
    
    face_db = load_model_if_exists()
    if face_db:
        print(f"   ✓ Model loaded successfully with {len(face_db)} students")
        for student_id in face_db.keys():
            print(f"      - Student ID {student_id}: {len(face_db[student_id])} face encodings")
    else:
        print("   ❌ Model verification failed!")
        sys.exit(1)
        
except Exception as e:
    print(f"   ❌ Verification error: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ SUCCESS! SYSTEM FIXED")
print("=" * 70)
print("\nYour system is now ready:")
print("  ✓ Orphaned dataset folders removed")
print("  ✓ Face recognition model retrained")
print("  ✓ All students synced with database")
print("  ✓ You can now mark attendance")
print("  ✓ You can register new students")
print("\n💡 TIP: From now on, the system will auto-retrain when you delete students")
sys.exit(0)
