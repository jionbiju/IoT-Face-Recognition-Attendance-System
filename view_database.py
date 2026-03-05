"""
Database Viewer - View all tables and data in attendance.db
"""
import sqlite3
import sys

DB_PATH = "attendance.db"

def view_database():
    """View all tables and their data"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        print("=" * 80)
        print("DATABASE VIEWER - attendance.db")
        print("=" * 80)
        
        # Get all tables
        c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in c.fetchall()]
        
        print(f"\n📊 Found {len(tables)} tables:")
        for i, table in enumerate(tables, 1):
            print(f"  {i}. {table}")
        
        # Show each table
        for table in tables:
            print("\n" + "=" * 80)
            print(f"TABLE: {table}")
            print("=" * 80)
            
            # Get column info
            c.execute(f"PRAGMA table_info({table})")
            columns = c.fetchall()
            
            print("\nColumns:")
            for col in columns:
                col_id, name, type_, notnull, default, pk = col
                pk_str = " (PRIMARY KEY)" if pk else ""
                notnull_str = " NOT NULL" if notnull else ""
                print(f"  - {name}: {type_}{pk_str}{notnull_str}")
            
            # Get row count
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]
            print(f"\nTotal Rows: {count}")
            
            # Show sample data (first 5 rows)
            if count > 0:
                c.execute(f"SELECT * FROM {table} LIMIT 5")
                rows = c.fetchall()
                
                print("\nSample Data (first 5 rows):")
                col_names = [col[1] for col in columns]
                
                # Print header
                header = " | ".join(col_names)
                print("-" * len(header))
                print(header)
                print("-" * len(header))
                
                # Print rows
                for row in rows:
                    row_str = " | ".join(str(val)[:30] if val is not None else "NULL" for val in row)
                    print(row_str)
                
                if count > 5:
                    print(f"... and {count - 5} more rows")
            else:
                print("\n(No data in this table)")
        
        conn.close()
        
        print("\n" + "=" * 80)
        print("END OF DATABASE")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

def view_specific_table(table_name):
    """View specific table with all data"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not c.fetchone():
            print(f"❌ Table '{table_name}' not found!")
            conn.close()
            return
        
        print("=" * 80)
        print(f"TABLE: {table_name}")
        print("=" * 80)
        
        # Get column info
        c.execute(f"PRAGMA table_info({table_name})")
        columns = c.fetchall()
        col_names = [col[1] for col in columns]
        
        print("\nColumns:")
        for col in columns:
            col_id, name, type_, notnull, default, pk = col
            pk_str = " (PRIMARY KEY)" if pk else ""
            notnull_str = " NOT NULL" if notnull else ""
            print(f"  - {name}: {type_}{pk_str}{notnull_str}")
        
        # Get all data
        c.execute(f"SELECT * FROM {table_name}")
        rows = c.fetchall()
        
        print(f"\nTotal Rows: {len(rows)}")
        
        if rows:
            print("\nAll Data:")
            # Print header
            header = " | ".join(col_names)
            print("-" * len(header))
            print(header)
            print("-" * len(header))
            
            # Print all rows
            for row in rows:
                row_str = " | ".join(str(val)[:50] if val is not None else "NULL" for val in row)
                print(row_str)
        else:
            print("\n(No data in this table)")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

def show_menu():
    """Show interactive menu"""
    print("\n" + "=" * 80)
    print("DATABASE VIEWER MENU")
    print("=" * 80)
    print("\nOptions:")
    print("  1. View all tables (summary)")
    print("  2. View specific table (detailed)")
    print("  3. View students table")
    print("  4. View attendance table")
    print("  5. View subjects table")
    print("  6. View timetable table")
    print("  7. Exit")
    print("\n" + "=" * 80)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line argument provided
        table_name = sys.argv[1]
        view_specific_table(table_name)
    else:
        # Interactive menu
        while True:
            show_menu()
            choice = input("\nEnter your choice (1-7): ").strip()
            
            if choice == "1":
                view_database()
            elif choice == "2":
                table_name = input("Enter table name: ").strip()
                view_specific_table(table_name)
            elif choice == "3":
                view_specific_table("students")
            elif choice == "4":
                view_specific_table("attendance")
            elif choice == "5":
                view_specific_table("subjects")
            elif choice == "6":
                view_specific_table("timetable")
            elif choice == "7":
                print("\n👋 Goodbye!")
                break
            else:
                print("\n❌ Invalid choice! Please enter 1-7")
            
            input("\nPress Enter to continue...")
