#!/usr/bin/env python3
"""
First Run Setup Script
Automatically sets up the database and initial configuration
"""

import os
import sqlite3
import json
from datetime import datetime

def create_database():
    """Create and initialize the database with sample data"""
    print("📊 Setting up database...")
    
    # Import the database initialization from app.py
    try:
        from app import init_db
        init_db()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    return True

def create_sample_subjects():
    """Create sample subjects for testing"""
    print("📚 Creating sample subjects...")
    
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # Check if subjects already exist
        c.execute("SELECT COUNT(*) FROM subjects")
        count = c.fetchone()[0]
        
        if count > 0:
            print("ℹ️  Subjects already exist, skipping...")
            conn.close()
            return True
        
        # Sample subjects
        subjects = [
            ('CST362', 'Programming in Python', 'Dr. Smith'),
            ('CST301', 'Data Structures', 'Prof. Johnson'),
            ('CST401', 'Machine Learning', 'Dr. Brown'),
            ('CST302', 'Database Systems', 'Prof. Davis'),
            ('CST403', 'Computer Networks', 'Dr. Wilson')
        ]
        
        for code, name, teacher in subjects:
            c.execute("INSERT INTO subjects (code, name, teacher) VALUES (?, ?, ?)",
                     (code, name, teacher))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Created {len(subjects)} sample subjects")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create subjects: {e}")
        return False

def create_sample_timetable():
    """Create a sample timetable"""
    print("📅 Creating sample timetable...")
    
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # Check if timetable already exists
        c.execute("SELECT COUNT(*) FROM timetable")
        count = c.fetchone()[0]
        
        if count > 0:
            print("ℹ️  Timetable already exists, skipping...")
            conn.close()
            return True
        
        # Get subject IDs
        c.execute("SELECT id FROM subjects ORDER BY id LIMIT 5")
        subject_ids = [row[0] for row in c.fetchall()]
        
        if len(subject_ids) < 5:
            print("⚠️  Not enough subjects for timetable")
            conn.close()
            return True
        
        # Sample timetable (Monday to Friday, 5 periods each)
        timetable = []
        for day in range(1, 6):  # Monday to Friday
            for period in range(1, 6):  # 5 periods
                subject_id = subject_ids[(day + period - 2) % len(subject_ids)]
                start_time = f"{8 + period}:00"
                end_time = f"{9 + period}:00"
                timetable.append((day, period, subject_id, start_time, end_time))
        
        for day, period, subject_id, start_time, end_time in timetable:
            c.execute("""INSERT INTO timetable (day_of_week, period, subject_id, start_time, end_time)
                         VALUES (?, ?, ?, ?, ?)""",
                     (day, period, subject_id, start_time, end_time))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Created timetable with {len(timetable)} entries")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create timetable: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    print("📁 Creating directories...")
    
    directories = ['dataset', 'static/images']
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"✅ Created directory: {directory}")
        except Exception as e:
            print(f"❌ Failed to create {directory}: {e}")
            return False
    
    return True

def create_train_status():
    """Create initial training status file"""
    print("🎯 Creating training status file...")
    
    try:
        status = {
            "running": False,
            "progress": 0,
            "message": "No training yet. Add students to begin."
        }
        
        with open('train_status.json', 'w') as f:
            json.dump(status, f, indent=2)
        
        print("✅ Training status file created")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create training status: {e}")
        return False

def main():
    """Run first-time setup"""
    print("🎓 Smart Attendance System - First Run Setup")
    print("=" * 50)
    
    all_good = True
    
    # Create directories
    if not create_directories():
        all_good = False
    
    # Initialize database
    if not create_database():
        all_good = False
    
    # Create sample subjects
    if not create_sample_subjects():
        all_good = False
    
    # Create sample timetable
    if not create_sample_timetable():
        all_good = False
    
    # Create training status
    if not create_train_status():
        all_good = False
    
    print("\n" + "=" * 50)
    
    if all_good:
        print("🎉 First run setup completed successfully!")
        print("\n✅ Your system is ready to use")
        print("\n📋 What's been set up:")
        print("   • Database with proper schema")
        print("   • 5 sample subjects")
        print("   • Sample weekly timetable")
        print("   • Required directories")
        print("   • Training status tracking")
        print("\n🚀 Next steps:")
        print("   1. Start the application: python app.py")
        print("   2. Open browser: http://localhost:5000")
        print("   3. Add students and start taking attendance!")
        print("\n📖 For detailed instructions, see README.md")
    else:
        print("❌ First run setup encountered some issues")
        print("\n🔧 Please check the errors above and try again")
    
    return all_good

if __name__ == "__main__":
    main()