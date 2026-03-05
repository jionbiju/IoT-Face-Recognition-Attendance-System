"""
Pre-Presentation System Check
Comprehensive validation before registering 60 students
"""
import os
import sqlite3
import sys

print("=" * 70)
print("PRE-PRESENTATION SYSTEM CHECK")
print("=" * 70)

issues = []
warnings = []
passed = []

# 1. Check Database Structure
print("\n[1/10] Checking Database Structure...")
try:
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    # Check required tables
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in c.fetchall()]
    
    required_tables = ['students', 'attendance', 'subjects', 'timetable', 
                      'student_subjects', 'attendance_audit_log']
    
    for table in required_tables:
        if table in tables:
            passed.append(f"✓ Table '{table}' exists")
        else:
            issues.append(f"✗ Missing table: {table}")
    
    # Check attendance table has deleted column
    c.execute("PRAGMA table_info(attendance)")
    columns = [col[1] for col in c.fetchall()]
    
    required_columns = ['id', 'student_id', 'name', 'timestamp', 'deleted', 
                       'subject_id', 'subject_code', 'subject_name', 'period']
    
    for col in required_columns:
        if col in columns:
            passed.append(f"✓ Column 'attendance.{col}' exists")
        else:
            issues.append(f"✗ Missing column: attendance.{col}")
    
    conn.close()
    
except Exception as e:
    issues.append(f"✗ Database error: {e}")

# 2. Check Subjects Configuration
print("\n[2/10] Checking Subjects Configuration...")
try:
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM subjects")
    subject_count = c.fetchone()[0]
    
    if subject_count == 8:
        passed.append(f"✓ All 8 subjects configured")
        c.execute("SELECT code, name FROM subjects ORDER BY code")
        for code, name in c.fetchall():
            passed.append(f"  - {code}: {name}")
    elif subject_count == 0:
        issues.append("✗ No subjects configured! Run update_subjects.py")
    else:
        warnings.append(f"⚠ Expected 8 subjects, found {subject_count}")
    
    conn.close()
    
except Exception as e:
    issues.append(f"✗ Subjects check error: {e}")

# 3. Check Timetable Configuration
print("\n[3/10] Checking Timetable Configuration...")
try:
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM timetable")
    timetable_count = c.fetchone()[0]
    
    if timetable_count >= 30:
        passed.append(f"✓ Timetable configured ({timetable_count} entries)")
    elif timetable_count == 0:
        issues.append("✗ No timetable configured! Run update_subjects.py")
    else:
        warnings.append(f"⚠ Expected ~30 timetable entries, found {timetable_count}")
    
    conn.close()
    
except Exception as e:
    issues.append(f"✗ Timetable check error: {e}")

# 4. Check Face Recognition Model
print("\n[4/10] Checking Face Recognition Model...")

if os.path.exists('face_encodings.pkl'):
    passed.append("✓ face_encodings.pkl exists")
    try:
        import pickle
        with open('face_encodings.pkl', 'rb') as f:
            face_db = pickle.load(f)
        passed.append(f"✓ Model loaded: {len(face_db)} students")
    except Exception as e:
        issues.append(f"✗ Model corrupted: {e}")
else:
    warnings.append("⚠ face_encodings.pkl not found (will be created on first registration)")

# 5. Check Dataset Directory
print("\n[5/10] Checking Dataset Directory...")

if os.path.exists('dataset'):
    passed.append("✓ Dataset directory exists")
    
    folders = [f for f in os.listdir('dataset') if os.path.isdir(os.path.join('dataset', f))]
    if len(folders) > 0:
        passed.append(f"✓ {len(folders)} student folders in dataset")
    else:
        warnings.append("⚠ No student folders yet (normal before registration)")
else:
    issues.append("✗ Dataset directory missing!")

# 6. Check Required Python Packages
print("\n[6/10] Checking Required Python Packages...")

required_packages = [
    ('flask', 'flask'),
    ('cv2', 'opencv-python'),
    ('numpy', 'numpy'),
    ('tensorflow', 'tensorflow'),
    ('sklearn', 'scikit-learn'),
    ('PIL', 'pillow')
]

for import_name, package_name in required_packages:
    try:
        __import__(import_name)
        passed.append(f"✓ {package_name} installed")
    except ImportError:
        issues.append(f"✗ Missing package: {package_name} (pip install {package_name})")

# 7. Check Critical Files
print("\n[7/10] Checking Critical Files...")

critical_files = [
    'app.py',
    'face_model.py',
    'liveness_detection.py',
    'templates/index.html',
    'templates/add_student.html',
    'templates/mark_attendance.html',
    'templates/attendance_record.html',
    'static/js/camera_add_student.js',
    'static/js/camera_mark.js',
    'static/css/style.css'
]

for file in critical_files:
    if os.path.exists(file):
        passed.append(f"✓ {file}")
    else:
        issues.append(f"✗ Missing file: {file}")

# 8. Check Database Capacity
print("\n[8/10] Checking Database Capacity...")

try:
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM students")
    current_students = c.fetchone()[0]
    
    passed.append(f"✓ Current students: {current_students}")
    
    if current_students + 60 <= 100:
        passed.append(f"✓ Capacity OK for 60 more students (total: {current_students + 60})")
    else:
        warnings.append(f"⚠ Will have {current_students + 60} students (consider performance)")
    
    conn.close()
    
except Exception as e:
    issues.append(f"✗ Database capacity check error: {e}")

# 9. Check Disk Space
print("\n[9/10] Checking Disk Space...")

try:
    import shutil
    total, used, free = shutil.disk_usage(".")
    free_gb = free // (2**30)
    
    if free_gb >= 5:
        passed.append(f"✓ Disk space: {free_gb} GB free")
    elif free_gb >= 2:
        warnings.append(f"⚠ Low disk space: {free_gb} GB free")
    else:
        issues.append(f"✗ Critical: Only {free_gb} GB free!")
    
except Exception as e:
    warnings.append(f"⚠ Could not check disk space: {e}")

# 10. Check Emergency Recovery Tools
print("\n[10/10] Checking Emergency Recovery Tools...")

recovery_tools = [
    'emergency_fix.py',
    'diagnose_system.py',
    'update_subjects.py'
]

for tool in recovery_tools:
    if os.path.exists(tool):
        passed.append(f"✓ {tool}")
    else:
        warnings.append(f"⚠ Missing recovery tool: {tool}")

# Print Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"\n✓ PASSED: {len(passed)} checks")
print(f"⚠ WARNINGS: {len(warnings)} items")
print(f"✗ ISSUES: {len(issues)} critical problems")

if issues:
    print("\n" + "!" * 70)
    print("CRITICAL ISSUES FOUND:")
    print("!" * 70)
    for issue in issues:
        print(issue)
    print("\n⚠️  FIX THESE BEFORE FRIDAY!")
    sys.exit(1)

if warnings:
    print("\n" + "-" * 70)
    print("WARNINGS:")
    print("-" * 70)
    for warning in warnings:
        print(warning)
    print("\n💡 Review these but not critical")

print("\n" + "=" * 70)
if not issues:
    print("✅ SYSTEM READY FOR PRESENTATION!")
    print("=" * 70)
    print("\nNext Steps:")
    print("1. Friday: Register 60 students")
    print("2. Test face recognition with a few students")
    print("3. Tuesday: Final presentation")
    print("\n💡 Keep emergency_fix.py handy just in case!")
else:
    print("❌ SYSTEM NOT READY - FIX ISSUES ABOVE")
    print("=" * 70)

sys.exit(0 if not issues else 1)
