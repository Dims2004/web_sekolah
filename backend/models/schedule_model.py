import sqlite3
import json
from datetime import datetime
import os

class ScheduleModel:
    def __init__(self, db_path):
        """Initialize schedule model with database path"""
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Create schedule tables if not exists"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Schedule table
            c.execute('''CREATE TABLE IF NOT EXISTS schedules
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          class_name TEXT NOT NULL,
                          day TEXT NOT NULL,
                          time TEXT NOT NULL,
                          subject TEXT NOT NULL,
                          teacher TEXT NOT NULL,
                          room TEXT NOT NULL,
                          color TEXT DEFAULT 'blue',
                          created_by TEXT DEFAULT 'admin',
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            # Teachers table
            c.execute('''CREATE TABLE IF NOT EXISTS teachers
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          name TEXT NOT NULL,
                          subject TEXT NOT NULL,
                          nip TEXT UNIQUE,
                          phone TEXT,
                          email TEXT,
                          username TEXT UNIQUE,
                          password TEXT,
                          homeroom_class TEXT,
                          token TEXT,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

            # Migrasi ringan untuk database lama, dibungkus try/except karena bisa
            # dijalankan bersamaan oleh beberapa worker gunicorn saat startup.
            for col_def in [
                ("username", "TEXT"),
                ("password", "TEXT"),
                ("homeroom_class", "TEXT"),
                ("token", "TEXT"),
            ]:
                try:
                    c.execute("PRAGMA table_info(teachers)")
                    existing_cols = [col[1] for col in c.fetchall()]
                    if col_def[0] not in existing_cols:
                        c.execute(f"ALTER TABLE teachers ADD COLUMN {col_def[0]} {col_def[1]}")
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e).lower():
                        raise
            
            # Rooms table
            c.execute('''CREATE TABLE IF NOT EXISTS rooms
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          name TEXT NOT NULL,
                          building TEXT,
                          capacity INTEGER,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

            # Classes table
            c.execute('''CREATE TABLE IF NOT EXISTS classes
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          name TEXT UNIQUE NOT NULL,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            conn.commit()
            conn.close()
            print("✅ Schedule tables initialized")
        except Exception as e:
            print(f"❌ Error initializing schedule tables: {e}")
    
    def add_schedule(self, data):
        """Add new schedule entry"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('''INSERT INTO schedules 
                         (class_name, day, time, subject, teacher, room, color, created_by)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (data['class_name'], data['day'], data['time'], 
                       data['subject'], data['teacher'], data['room'], 
                       data.get('color', 'blue'), data.get('created_by', 'admin')))
            
            schedule_id = c.lastrowid
            conn.commit()
            conn.close()
            
            return schedule_id, None
        except Exception as e:
            return None, str(e)
    
    def get_schedules(self, class_name=None, day=None):
        """Get schedules with optional filters"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            query = "SELECT * FROM schedules WHERE 1=1"
            params = []
            
            if class_name:
                query += " AND class_name = ?"
                params.append(class_name)
            
            if day and day != 'all':
                query += " AND day = ?"
                params.append(day)
            
            query += " ORDER BY class_name, day, time"
            
            c.execute(query, params)
            schedules = c.fetchall()
            conn.close()
            
            # Format schedules
            formatted = {}
            for s in schedules:
                class_name = s[1]
                day = s[2]
                
                if class_name not in formatted:
                    formatted[class_name] = {}
                
                if day not in formatted[class_name]:
                    formatted[class_name][day] = []
                
                formatted[class_name][day].append({
                    'id': s[0],
                    'time': s[3],
                    'subject': s[4],
                    'teacher': s[5],
                    'room': s[6],
                    'color': s[7]
                })
            
            return formatted, None
        except Exception as e:
            return None, str(e)
    
    def update_schedule(self, schedule_id, data):
        """Update existing schedule"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('''UPDATE schedules 
                         SET class_name=?, day=?, time=?, subject=?, teacher=?, room=?, color=?, updated_at=CURRENT_TIMESTAMP
                         WHERE id=?''',
                      (data['class_name'], data['day'], data['time'], 
                       data['subject'], data['teacher'], data['room'], 
                       data.get('color', 'blue'), schedule_id))
            
            conn.commit()
            conn.close()
            return True, None
        except Exception as e:
            return False, str(e)
    
    def delete_schedule(self, schedule_id):
        """Delete schedule"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
            conn.commit()
            conn.close()
            return True, None
        except Exception as e:
            return False, str(e)
    
    def add_teacher(self, data):
        """Add new teacher"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('''INSERT INTO teachers (name, subject, nip, phone, email, username, password, homeroom_class)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (data['name'], data['subject'], data.get('nip'), 
                       data.get('phone'), data.get('email'),
                       data.get('username'), data.get('password'), data.get('homeroom_class')))
            
            teacher_id = c.lastrowid
            conn.commit()
            conn.close()
            return teacher_id, None
        except Exception as e:
            return None, str(e)
    
    def get_teachers(self):
        """Get all teachers (password excluded from listing)"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT id, name, subject, nip, username, homeroom_class FROM teachers ORDER BY name")
            teachers = c.fetchall()
            conn.close()
            
            return [{'id': t[0], 'name': t[1], 'subject': t[2], 'nip': t[3],
                     'username': t[4], 'homeroom_class': t[5]} for t in teachers], None
        except Exception as e:
            return None, str(e)

    def get_teacher_by_username(self, username):
        """Get one teacher (with password/token) by username, used for login"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''SELECT id, name, subject, username, password, homeroom_class
                         FROM teachers WHERE username = ?''', (username,))
            row = c.fetchone()
            conn.close()
            if not row:
                return None, None
            return {'id': row[0], 'name': row[1], 'subject': row[2], 'username': row[3],
                    'password': row[4], 'homeroom_class': row[5]}, None
        except Exception as e:
            return None, str(e)

    def get_teacher_by_token(self, token):
        """Get one teacher by their session token, used to authorize teacher-only actions"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''SELECT id, name, subject, username, homeroom_class
                         FROM teachers WHERE token = ?''', (token,))
            row = c.fetchone()
            conn.close()
            if not row:
                return None
            return {'id': row[0], 'name': row[1], 'subject': row[2], 'username': row[3], 'homeroom_class': row[4]}
        except Exception as e:
            return None

    def set_teacher_token(self, teacher_id, token):
        """Store a fresh session token for a teacher after successful login"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("UPDATE teachers SET token = ? WHERE id = ?", (token, teacher_id))
            conn.commit()
            conn.close()
            return True, None
        except Exception as e:
            return False, str(e)

    def update_teacher(self, teacher_id, data):
        """Update a teacher's data. Password only changed if a new one is provided."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            if data.get('password'):
                c.execute('''UPDATE teachers SET name=?, subject=?, nip=?, username=?, password=?, homeroom_class=?
                             WHERE id=?''',
                          (data['name'], data['subject'], data.get('nip'), data.get('username'),
                           data.get('password'), data.get('homeroom_class'), teacher_id))
            else:
                c.execute('''UPDATE teachers SET name=?, subject=?, nip=?, username=?, homeroom_class=?
                             WHERE id=?''',
                          (data['name'], data['subject'], data.get('nip'), data.get('username'),
                           data.get('homeroom_class'), teacher_id))
            conn.commit()
            conn.close()
            return True, None
        except Exception as e:
            return False, str(e)

    def delete_teacher(self, teacher_id):
        """Delete a teacher"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
            conn.commit()
            conn.close()
            return True, None
        except Exception as e:
            return False, str(e)
    
    def add_room(self, data):
        """Add new room"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('''INSERT INTO rooms (name, building, capacity)
                         VALUES (?, ?, ?)''',
                      (data['name'], data.get('building'), data.get('capacity')))
            
            room_id = c.lastrowid
            conn.commit()
            conn.close()
            return room_id, None
        except Exception as e:
            return None, str(e)
    
    def get_rooms(self):
        """Get all rooms"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT id, name, building, capacity FROM rooms ORDER BY name")
            rooms = c.fetchall()
            conn.close()
            
            return [{'id': r[0], 'name': r[1], 'building': r[2], 'capacity': r[3]} for r in rooms], None
        except Exception as e:
            return None, str(e)
    
    def add_class(self, name):
        """Add a new class name"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO classes (name) VALUES (?)", (name,))
            class_id = c.lastrowid
            conn.commit()
            conn.close()
            return class_id, None
        except Exception as e:
            return None, str(e)

    def get_classes(self):
        """Get all class names (from the classes table, plus any class names
        already used in schedules so nothing already in use gets hidden)"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''SELECT name FROM classes
                         UNION
                         SELECT DISTINCT class_name FROM schedules
                         ORDER BY 1''')
            classes = c.fetchall()
            conn.close()
            
            return [c[0] for c in classes], None
        except Exception as e:
            return None, str(e)