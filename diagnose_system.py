"""
System Diagnostic Script
Checks database, face recognition model, and file system
"""

import os
import sqlite3
import sys

def check_database():
    """Check database integrity"""
    print("\n" + "="*50)
    print("DATABASE DIAGNOSTICS")
    print("="*50)
    
    db_path = "attendance.db"
    
    if not os.path.exists(db_path):
        print("❌ Database file not found!")
        return False
    
    print(f"✓ Database file exists: {db_path}")
    print(f"  Size: {os.path.getsize(db_path)} bytes")
    
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        c = conn.cursor()
        
        # Check tables
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        print(f"\n✓ Tables found: {len(tables)}")
        for table in tables:
            print(f"  - {table}")
        
        # Check students
        c.execute("SELECT COUNT(*) FROM students")
        student_count = c.fetchone()[0]
        print(f"\n✓ Students: {student_count}")
        
        if student_count > 0:
            c.execute("SELECT id, name FROM students ORDER BY id")
            students = c.fetchall()
            for s in students:
                print(f"  {s[0]}: {s[1]}")
        
        # Check attendance
        c.execute("SELECT COUNT(*) FROM attendance WHERE deleted=0")
        attendance_count = c.fetchone()[0]
        print(f"\n✓ Active attendance records: {attendance_count}")
        
        # Check audit log
        c.execute("SELECT COUNT(*) FROM attendance_audit_log")
        audit_count = c.fetchone()[0]
        print(f"✓ Audit log entries: {audit_count}")
        
        conn.close()
        print("\n✓ Database is healthy!")
        return True
        
    except Exception as e:
        print(f"\n❌ Database error: {e}")
        return False

def check_face_model():
    """Check face recognition model"""
    print("\n" + "="*50)
    print("FACE RECOGNITION MODEL DIAGNOSTICS")
    print("="*50)
    
    model_path = "face_encodings.pkl"
    
    if not os.path.exists(model_path):
        print("⚠ Face recognition model not found (will be created on first training)")
        return True
    
    print(f"✓ Model file exists: {model_path}")
    print(f"  Size: {os.path.getsize(model_path)} bytes")
    
    try:
        import pickle
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
        
        if isinstance(data, dict) and 'face_database' in data:
            face_db = data['face_database']
            print(f"\n✓ Students in model: {len(face_db)}")
            
            for student_id, encodings in face_db.items():
                student_name = data.get('student_names', {}).get(student_id, 'Unknown')
                print(f"  Student {student_id} ({student_name}): {len(encodings)} encodings")
            
            print("\n✓ Face recognition model is healthy!")
            return True
        else:
            print("⚠ Model format is old or invalid")
            return False
            
    except Exception as e:
        print(f"\n❌ Model error: {e}")
        return False

def check_dataset():
    """Check dataset folder"""
    print("\n" + "="*50)
    print("DATASET DIAGNOSTICS")
    print("="*50)
    
    dataset_dir = "dataset"
    
    if not os.path.exists(dataset_dir):
        print("⚠ Dataset folder not found (will be created when adding students)")
        return True
    
    print(f"✓ Dataset folder exists: {dataset_dir}")
    
    student_folders = [f for f in os.listdir(dataset_dir) 
                      if os.path.isdir(os.path.join(dataset_dir, f))]
    
    print(f"\n✓ Student folders: {len(student_folders)}")
    
    for folder in sorted(student_folders, key=lambda x: int(x) if x.isdigit() else 0):
        folder_path = os.path.join(dataset_dir, folder)
        images = [f for f in os.listdir(folder_path) 
                 if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        print(f"  Student {folder}: {len(images)} images")
    
    print("\n✓ Dataset is healthy!")
    return True

def check_dependencies():
    """Check required dependencies"""
    print("\n" + "="*50)
    print("DEPENDENCIES CHECK")
    print("="*50)
    
    required = [
        'flask',
        'cv2',
        'numpy',
        'tensorflow',
        'sklearn',
        'pandas'
    ]
    
    all_ok = True
    for module in required:
        try:
            if module == 'cv2':
                import cv2
                print(f"✓ opencv-python: {cv2.__version__}")
            elif module == 'tensorflow':
                import tensorflow as tf
                print(f"✓ tensorflow: {tf.__version__}")
            elif module == 'sklearn':
                import sklearn
                print(f"✓ scikit-learn: {sklearn.__version__}")
            else:
                mod = __import__(module)
                version = getattr(mod, '__version__', 'unknown')
                print(f"✓ {module}: {version}")
        except ImportError:
            print(f"❌ {module}: NOT INSTALLED")
            all_ok = False
    
    if all_ok:
        print("\n✓ All dependencies installed!")
    else:
        print("\n❌ Some dependencies missing!")
    
    return all_ok

def check_file_permissions():
    """Check file permissions"""
    print("\n" + "="*50)
    print("FILE PERMISSIONS CHECK")
    print("="*50)
    
    files_to_check = [
        'attendance.db',
        'face_encodings.pkl',
        'dataset'
    ]
    
    all_ok = True
    for file_path in files_to_check:
        if os.path.exists(file_path):
            readable = os.access(file_path, os.R_OK)
            writable = os.access(file_path, os.W_OK)
            
            status = "✓" if (readable and writable) else "❌"
            print(f"{status} {file_path}: R={readable}, W={writable}")
            
            if not (readable and writable):
                all_ok = False
        else:
            print(f"⚠ {file_path}: Does not exist")
    
    if all_ok:
        print("\n✓ File permissions OK!")
    else:
        print("\n❌ Some permission issues found!")
    
    return all_ok

def main():
    """Run all diagnostics"""
    print("\n" + "="*50)
    print("ATTENDANCE SYSTEM DIAGNOSTICS")
    print("="*50)
    
    results = {
        'database': check_database(),
        'face_model': check_face_model(),
        'dataset': check_dataset(),
        'dependencies': check_dependencies(),
        'permissions': check_file_permissions()
    }
    
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    
    for check, status in results.items():
        symbol = "✓" if status else "❌"
        print(f"{symbol} {check.upper()}: {'OK' if status else 'ISSUES FOUND'}")
    
    all_ok = all(results.values())
    
    if all_ok:
        print("\n✅ System is healthy and ready to use!")
        return 0
    else:
        print("\n⚠️ Some issues found. Please review the diagnostics above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
