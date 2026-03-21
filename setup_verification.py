#!/usr/bin/env python3
"""
Setup Verification Script
Run this after cloning to ensure everything is working correctly
"""

import sys
import os
import subprocess
import importlib

def check_python_version():
    """Check if Python version is 3.8+"""
    print("🐍 Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} - Need Python 3.8+")
        return False

def check_dependencies():
    """Check if all required packages are installed"""
    print("\n📦 Checking dependencies...")
    
    required_packages = [
        'flask',
        'cv2',
        'numpy',
        'sklearn',
        'tensorflow',
        'torch',
        'facenet_pytorch',
        'openpyxl',
        'requests',
        'PIL'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == 'cv2':
                importlib.import_module('cv2')
            elif package == 'PIL':
                importlib.import_module('PIL')
            else:
                importlib.import_module(package)
            print(f"✅ {package} - OK")
        except ImportError:
            print(f"❌ {package} - Missing")
            missing_packages.append(package)
    
    return len(missing_packages) == 0, missing_packages

def check_project_files():
    """Check if all required project files exist"""
    print("\n📁 Checking project files...")
    
    required_files = [
        'app.py',
        'face_model.py',
        'facenet_model.py',
        'liveness_detection.py',
        'model.py',
        'requirements.txt',
        'README.md',
        'templates/index.html',
        'templates/mark_attendance.html',
        'templates/add_student.html',
        'static/css/style.css',
        'static/js/camera_mark.js'
    ]
    
    missing_files = []
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} - OK")
        else:
            print(f"❌ {file_path} - Missing")
            missing_files.append(file_path)
    
    return len(missing_files) == 0, missing_files

def check_directories():
    """Check if required directories exist or can be created"""
    print("\n📂 Checking directories...")
    
    required_dirs = [
        'static',
        'templates',
        'static/css',
        'static/js'
    ]
    
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✅ {dir_path}/ - OK")
        else:
            print(f"❌ {dir_path}/ - Missing")
            return False
    
    # Check if we can create runtime directories
    runtime_dirs = ['dataset']
    
    for dir_path in runtime_dirs:
        try:
            os.makedirs(dir_path, exist_ok=True)
            print(f"✅ {dir_path}/ - Created")
        except Exception as e:
            print(f"❌ {dir_path}/ - Cannot create: {e}")
            return False
    
    return True

def test_imports():
    """Test critical imports"""
    print("\n🔍 Testing critical imports...")
    
    try:
        import app
        print("✅ app.py - Import OK")
    except Exception as e:
        print(f"❌ app.py - Import failed: {e}")
        return False
    
    try:
        import facenet_model
        print("✅ facenet_model.py - Import OK")
    except Exception as e:
        print(f"❌ facenet_model.py - Import failed: {e}")
        return False
    
    try:
        import facenet_model
        print("✅ facenet_model.py - Import OK")
    except Exception as e:
        print(f"❌ facenet_model.py - Import failed: {e}")
        return False
    
    try:
        import liveness_detection
        print("✅ liveness_detection.py - Import OK")
    except Exception as e:
        print(f"❌ liveness_detection.py - Import failed: {e}")
        return False
    
    return True

def check_camera_access():
    """Test camera access"""
    print("\n📷 Testing camera access...")
    
    try:
        import cv2
        
        # Try to access camera 0
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                print("✅ Camera access - OK")
                return True
            else:
                print("⚠️  Camera detected but no frame captured")
                return True  # Still OK, might be permission issue
        else:
            print("⚠️  No camera detected (this is OK if using DroidCam)")
            return True  # Not critical for setup
    except Exception as e:
        print(f"⚠️  Camera test failed: {e}")
        return True  # Not critical for setup

def main():
    """Run all verification checks"""
    print("🚀 Smart Attendance System - Setup Verification")
    print("=" * 50)
    
    all_good = True
    
    # Check Python version
    if not check_python_version():
        all_good = False
    
    # Check dependencies
    deps_ok, missing_deps = check_dependencies()
    if not deps_ok:
        all_good = False
        print(f"\n❌ Missing packages: {', '.join(missing_deps)}")
        print("💡 Run: pip install -r requirements.txt")
    
    # Check project files
    files_ok, missing_files = check_project_files()
    if not files_ok:
        all_good = False
        print(f"\n❌ Missing files: {', '.join(missing_files)}")
    
    # Check directories
    if not check_directories():
        all_good = False
    
    # Test imports
    if not test_imports():
        all_good = False
    
    # Test camera (optional)
    check_camera_access()
    
    # Final result
    print("\n" + "=" * 50)
    if all_good:
        print("🎉 Setup verification PASSED!")
        print("\n✅ Your system is ready to run the Smart Attendance System")
        print("\n🚀 To start the application:")
        print("   python app.py")
        print("\n🌐 Then open: http://localhost:5000")
        print("\n📖 For detailed instructions, see README.md")
    else:
        print("❌ Setup verification FAILED!")
        print("\n🔧 Please fix the issues above and run this script again")
        print("\n💡 Common solutions:")
        print("   • Install missing packages: pip install -r requirements.txt")
        print("   • Ensure you're in the project directory")
        print("   • Check Python version: python --version")
        print("   • Create virtual environment: python -m venv venv")
    
    return all_good

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)