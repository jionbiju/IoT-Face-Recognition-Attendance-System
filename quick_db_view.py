"""
Quick Database View - See key information at a glance
"""
import sqlite3

conn = sqlite3.connect('attendance.db')
c = conn.cursor()

print("=" * 70)
print("QUICK DATABASE VIEW")
print("=" * 70)

# Students
print("\n📚 STUDENTS:")
c.execute("SELECT id, name, roll, class, section FROM students ORDER BY id")
students = c.fetchall()
if students:
    print(f"Total: {len(students)} students\n")
    for sid, name, roll, cls, section in students:
        roll_str = f"Roll: {roll}" if roll else ""
        class_str = f"{cls}-{section}" if cls and section else ""
        print(f"  ID {sid}: {name} {roll_str} {class_str}")
else:
    print("  (No students registered yet)")

# Subjects
print("\n📖 SUBJECTS:")
c.execute("SELECT id, code, name FROM subjects ORDER BY code")
subjects = c.fetchall()
if subjects:
    print(f"Total: {len(subjects)} subjects\n")
    for sid, code, name in subjects:
        print(f"  {code}: {name}")
else:
    print("  (No subjects configured)")

# Attendance (Active only)
print("\n✅ ATTENDANCE (Active Records):")
c.execute("SELECT COUNT(*) FROM attendance WHERE deleted=0")
active_count = c.fetchone()[0]
print(f"Total Active: {active_count} records")

if active_count > 0:
    # Today's attendance
    c.execute("""SELECT COUNT(*) FROM attendance 
                 WHERE deleted=0 AND date(timestamp) = date('now')""")
    today_count = c.fetchone()[0]
    print(f"Today: {today_count} records")
    
    # Recent attendance
    print("\nRecent Attendance (last 5):")
    c.execute("""SELECT a.name, a.subject_code, a.period, 
                        datetime(a.timestamp, 'localtime')
                 FROM attendance a
                 WHERE a.deleted=0
                 ORDER BY a.timestamp DESC LIMIT 5""")
    recent = c.fetchall()
    for name, subject, period, timestamp in recent:
        subject_str = f"{subject} P{period}" if subject else "No subject"
        print(f"  {name} - {subject_str} - {timestamp}")

# Deleted (Unmarked) Attendance
c.execute("SELECT COUNT(*) FROM attendance WHERE deleted=1")
deleted_count = c.fetchone()[0]
if deleted_count > 0:
    print(f"\n🗑️  Unmarked Records: {deleted_count}")

# Timetable
print("\n📅 TIMETABLE:")
c.execute("SELECT COUNT(*) FROM timetable")
timetable_count = c.fetchone()[0]
print(f"Total Entries: {timetable_count}")

if timetable_count > 0:
    # Show Monday's schedule as example
    c.execute("""SELECT t.period, s.code, t.start_time, t.end_time
                 FROM timetable t
                 JOIN subjects s ON t.subject_id = s.id
                 WHERE t.day_of_week = 1
                 ORDER BY t.period""")
    monday = c.fetchall()
    if monday:
        print("\nMonday Schedule:")
        for period, code, start, end in monday:
            print(f"  Period {period}: {code} ({start}-{end})")

# Enrollments
print("\n👥 ENROLLMENTS:")
c.execute("SELECT COUNT(*) FROM student_subjects")
enrollment_count = c.fetchone()[0]
print(f"Total: {enrollment_count} enrollments")

if len(students) > 0 and len(subjects) > 0:
    expected = len(students) * len(subjects)
    print(f"Expected: {expected} (if all students enrolled in all subjects)")
    if enrollment_count == expected:
        print("✓ All students enrolled in all subjects")
    elif enrollment_count < expected:
        print(f"⚠️  Missing {expected - enrollment_count} enrollments")

# Audit Log
print("\n📋 AUDIT LOG:")
c.execute("SELECT COUNT(*) FROM attendance_audit_log")
audit_count = c.fetchone()[0]
print(f"Total Entries: {audit_count}")

if audit_count > 0:
    c.execute("""SELECT action, COUNT(*) FROM attendance_audit_log 
                 GROUP BY action""")
    actions = c.fetchall()
    for action, count in actions:
        print(f"  {action}: {count}")

conn.close()

print("\n" + "=" * 70)
print("For detailed view, run: python view_database.py")
print("=" * 70)
