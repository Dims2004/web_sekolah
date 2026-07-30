import os
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import sqlite3
import cv2
import numpy as np
import mediapipe as mp
import pickle
from datetime import datetime, timedelta
from routes.schedule_routes import schedule_bp, _teacher_teaches_class_on_date
import base64
import json
import platform
import sys

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

IS_PYTHONANYWHERE = 'PYTHONANYWHERE_DOMAIN' in os.environ

if IS_PYTHONANYWHERE:
    DEBUG = False
    print("✅ Running in PythonAnywhere production mode")
else:
    DEBUG = True
    print("✅ Running in local development mode")

app.register_blueprint(schedule_bp)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if IS_PYTHONANYWHERE:
    DATABASE_DIR = os.path.join(BASE_DIR, 'database')
else:
    DATABASE_DIR = os.path.join(BASE_DIR, '..', 'database')

DATABASE_PATH = os.path.join(DATABASE_DIR, 'students.db')

if not os.path.exists(DATABASE_DIR):
    os.makedirs(DATABASE_DIR)
    print(f"✅ Created database directory: {DATABASE_DIR}")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
ADMIN_TOKEN = "admin_token_secure_123"
PAYMENT_AMOUNT = 100000

def admin_required(f):
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != f'Bearer {ADMIN_TOKEN}':
            return jsonify({'success': False, 'error': 'Unauthorized. Silakan login sebagai admin/guru.'}), 401
        return f(*args, **kwargs)
    return decorated_function


def get_teacher_by_token(token):
    """Cari data guru dari token sesi mereka (diset saat /api/schedule/teachers/login)."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name, homeroom_class FROM teachers WHERE token = ?", (token,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {'id': row[0], 'name': row[1], 'homeroom_class': row[2]}
    except Exception:
        return None


def admin_or_teacher_required(f):
    """Guard untuk endpoint yang boleh diakses admin ATAU guru (wali kelas).
    Menaruh info pelaku di request.actor supaya handler bisa membatasi
    aksi guru cuma untuk kelas perwaliannya sendiri."""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header else ''

        if token == ADMIN_TOKEN:
            request.actor = {'role': 'admin'}
            return f(*args, **kwargs)

        teacher = get_teacher_by_token(token)
        if teacher:
            request.actor = {'role': 'teacher', 'teacher': teacher}
            return f(*args, **kwargs)

        return jsonify({'success': False, 'error': 'Unauthorized. Silakan login sebagai admin atau guru.'}), 401
    return decorated_function

print("🔄 Initializing MediaPipe...")
mp_face_detection = mp.solutions.face_detection
mp_face_mesh = mp.solutions.face_mesh

def init_db():
    try:
        print(f"🔄 Initializing database at: {DATABASE_PATH}")
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS students
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      nis TEXT UNIQUE NOT NULL,
                      name TEXT NOT NULL,
                      class TEXT NOT NULL,
                      face_embedding BLOB,
                      profile_photo TEXT,
                      registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Migrasi ringan untuk database lama sebelum kolom profile_photo ada
        try:
            c.execute("PRAGMA table_info(students)")
            student_cols = [col[1] for col in c.fetchall()]
            if 'profile_photo' not in student_cols:
                c.execute("ALTER TABLE students ADD COLUMN profile_photo TEXT")
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                raise
        
        c.execute('''CREATE TABLE IF NOT EXISTS attendance
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      student_id INTEGER,
                      nis TEXT,
                      name TEXT,
                      class TEXT,
                      status TEXT DEFAULT 'hadir',
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Migrasi ringan untuk database lama sebelum kolom status ada
        try:
            c.execute("PRAGMA table_info(attendance)")
            att_cols = [col[1] for col in c.fetchall()]
            if 'status' not in att_cols:
                c.execute("ALTER TABLE attendance ADD COLUMN status TEXT DEFAULT 'hadir'")
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                raise

        # Pengajuan izin/sakit dari siswa, perlu disetujui guru yang mengajar kelas itu
        c.execute('''CREATE TABLE IF NOT EXISTS leave_requests
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      nis TEXT NOT NULL,
                      student_name TEXT NOT NULL,
                      class TEXT NOT NULL,
                      leave_type TEXT NOT NULL,
                      leave_date TEXT NOT NULL,
                      reason TEXT,
                      doctor_note TEXT,
                      status TEXT DEFAULT 'pending',
                      reviewed_by TEXT,
                      reviewed_at TIMESTAMP,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Migrasi untuk database lama yang dibuat sebelum kolom doctor_note ada
        try:
            c.execute("PRAGMA table_info(leave_requests)")
            leave_cols = [col[1] for col in c.fetchall()]
            if 'doctor_note' not in leave_cols:
                c.execute("ALTER TABLE leave_requests ADD COLUMN doctor_note TEXT")
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                raise

        # Status absensi manual per siswa per tanggal (Alfa/Sakit/Izin/koreksi guru),
        # menang/dipakai duluan dibanding data dari mesin pengenalan wajah.
        c.execute('''CREATE TABLE IF NOT EXISTS attendance_overrides
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      nis TEXT NOT NULL,
                      att_date TEXT NOT NULL,
                      status TEXT NOT NULL,
                      note TEXT,
                      updated_by TEXT,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      UNIQUE(nis, att_date))''')

        c.execute('''CREATE TABLE IF NOT EXISTS admissions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      registration_no TEXT UNIQUE NOT NULL,
                      full_name TEXT NOT NULL,
                      nik TEXT,
                      birth_place TEXT,
                      birth_date TEXT,
                      gender TEXT,
                      address TEXT,
                      parent_name TEXT,
                      phone TEXT,
                      previous_school TEXT,
                      target_class TEXT,
                      extracurricular TEXT,
                      photo TEXT,
                      payment_amount INTEGER DEFAULT 100000,
                      status TEXT DEFAULT 'pending',
                      status_note TEXT,
                      status_updated_at TIMESTAMP,
                      converted_student_id INTEGER,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        try:
            c.execute("PRAGMA table_info(admissions)")
            adm_cols = [col[1] for col in c.fetchall()]
            if 'converted_student_id' not in adm_cols:
                c.execute("ALTER TABLE admissions ADD COLUMN converted_student_id INTEGER")
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                raise

        # Migrasi ringan untuk database lama sebelum kolom status ada
        for col_name, col_type in [('status', "TEXT DEFAULT 'pending'"), ('status_note', 'TEXT'), ('status_updated_at', 'TIMESTAMP')]:
            try:
                c.execute("PRAGMA table_info(admissions)")
                cols = [col[1] for col in c.fetchall()]
                if col_name not in cols:
                    c.execute(f"ALTER TABLE admissions ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError as e:
                if 'duplicate column' not in str(e).lower():
                    raise

        c.execute('''CREATE TABLE IF NOT EXISTS admission_documents
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      admission_id INTEGER NOT NULL,
                      doc_type TEXT NOT NULL,
                      file_name TEXT,
                      file_data TEXT,
                      uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      UNIQUE(admission_id, doc_type))''')

        c.execute('''CREATE TABLE IF NOT EXISTS school_info
                     (id INTEGER PRIMARY KEY CHECK (id = 1),
                      vision_mission TEXT,
                      facilities TEXT,
                      achievements TEXT,
                      hours_weekday TEXT,
                      hours_friday TEXT,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS extracurriculars
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT NOT NULL,
                      description TEXT,
                      icon TEXT DEFAULT 'fa-star',
                      photo TEXT,
                      contact_name TEXT,
                      contact_phone TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Announcements table (pengumuman/berita, tampil sebagai banner+kartu di dashboard)
        c.execute('''CREATE TABLE IF NOT EXISTS announcements
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      title TEXT NOT NULL,
                      description TEXT,
                      image TEXT,
                      link_url TEXT,
                      audience TEXT DEFAULT 'all',
                      is_pinned INTEGER DEFAULT 0,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Ekskul registrations table (pendaftaran ekstrakurikuler, terpisah dari PPDB)
        c.execute('''CREATE TABLE IF NOT EXISTS ekskul_registrations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      registration_no TEXT UNIQUE,
                      ekskul_name TEXT NOT NULL,
                      full_name TEXT NOT NULL,
                      class TEXT NOT NULL,
                      phone TEXT NOT NULL,
                      note TEXT,
                      contact_name TEXT,
                      contact_phone TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Migrasi ringan untuk database lama yang sudah ada sebelum kolom ini ditambahkan.
        # Dibungkus try/except karena ada 2 worker gunicorn yang bisa menjalankan
        # migrasi ini bersamaan saat startup - kalau salah satu sudah lebih dulu
        # menambahkan kolomnya, worker lain akan dapat error "duplicate column"
        # yang aman untuk diabaikan.
        try:
            c.execute("PRAGMA table_info(extracurriculars)")
            ex_columns = [col[1] for col in c.fetchall()]
            if 'photo' not in ex_columns:
                c.execute("ALTER TABLE extracurriculars ADD COLUMN photo TEXT")
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                raise

        try:
            c.execute("PRAGMA table_info(admissions)")
            ad_columns = [col[1] for col in c.fetchall()]
            if 'extracurricular' not in ad_columns:
                c.execute("ALTER TABLE admissions ADD COLUMN extracurricular TEXT")
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                raise

        for col_name, col_type in [('contact_name', 'TEXT'), ('contact_phone', 'TEXT')]:
            try:
                c.execute("PRAGMA table_info(extracurriculars)")
                cols = [col[1] for col in c.fetchall()]
                if col_name not in cols:
                    c.execute(f"ALTER TABLE extracurriculars ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError as e:
                if 'duplicate column' not in str(e).lower():
                    raise

        for col_name, col_type in [('registration_no', 'TEXT'), ('contact_name', 'TEXT'), ('contact_phone', 'TEXT')]:
            try:
                c.execute("PRAGMA table_info(ekskul_registrations)")
                cols = [col[1] for col in c.fetchall()]
                if col_name not in cols:
                    c.execute(f"ALTER TABLE ekskul_registrations ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError as e:
                if 'duplicate column' not in str(e).lower():
                    raise

        c.execute("SELECT COUNT(*) FROM school_info WHERE id = 1")
        if c.fetchone()[0] == 0:
            c.execute('''INSERT INTO school_info
                         (id, vision_mission, facilities, achievements, hours_weekday, hours_friday)
                         VALUES (1, ?, ?, ?, ?, ?)''', (
                'Mewujudkan sekolah unggul berbasis teknologi yang menghasilkan generasi berkarakter dan berkompetensi global.',
                'Laboratorium Computer Vision\nRuang Kelas Ber-AC\nPerpustakaan Digital\nLapangan Olahraga\nWi-Fi Area Sekolah',
                'Juara 1 Lomba Inovasi Teknologi Pendidikan Tingkat Nasional 2023',
                '07:00 - 15:00',
                '07:00 - 11:30'
            ))
        
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully!")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")

init_db()

class FaceRecognizer:
    def __init__(self):
        print("🔄 Initializing MediaPipe Face Recognizer...")
        self.face_detection = mp_face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.5
        )
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        print("✅ Face Recognizer initialized!")
        
    def get_db_connection(self):
        return sqlite3.connect(DATABASE_PATH)
    
    def extract_face_embedding(self, image):
        try:
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_image)
            
            if not results.multi_face_landmarks:
                return None, "No face detected"
            
            face_landmarks = results.multi_face_landmarks[0]
            landmarks = []
            
            for landmark in face_landmarks.landmark:
                landmarks.extend([landmark.x, landmark.y, landmark.z])
            
            embedding = np.array(landmarks, dtype=np.float32)
            embedding_mean = np.mean(embedding)
            embedding_std = np.std(embedding)
            
            if embedding_std > 0:
                embedding = (embedding - embedding_mean) / embedding_std
            else:
                embedding = embedding - embedding_mean
            
            return embedding, None
            
        except Exception as e:
            print(f"❌ Error extracting face embedding: {e}")
            return None, str(e)
    
    def detect_face(self, image):
        try:
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.face_detection.process(rgb_image)
            
            if not results.detections:
                return None, "No face detected"
            
            detection = results.detections[0]
            bbox = detection.location_data.relative_bounding_box
            
            h, w, _ = image.shape
            x = int(bbox.xmin * w)
            y = int(bbox.ymin * h)
            width = int(bbox.width * w)
            height = int(bbox.height * h)
            
            x = max(0, x)
            y = max(0, y)
            width = min(width, w - x)
            height = min(height, h - y)
            
            return (x, y, width, height), None
            
        except Exception as e:
            print(f"❌ Error detecting face: {e}")
            return None, str(e)
    
    def compare_faces(self, query_embedding, threshold=0.6):
        try:
            conn = self.get_db_connection()
            c = conn.cursor()
            c.execute("SELECT id, nis, name, class, face_embedding FROM students")
            students = c.fetchall()
            conn.close()
            
            best_match = None
            best_score = 0
            
            for student in students:
                student_id, nis, name, student_class, embedding_blob = student
                
                if embedding_blob is None:
                    continue
                
                try:
                    stored_embedding = pickle.loads(embedding_blob)
                    
                    if len(query_embedding) != len(stored_embedding):
                        continue
                    
                    similarity = self.cosine_similarity(query_embedding, stored_embedding)
                    
                    if similarity > best_score and similarity > threshold:
                        best_score = similarity
                        best_match = {
                            'id': student_id,
                            'nis': nis,
                            'name': name,
                            'class': student_class,
                            'confidence': float(similarity)
                        }
                        
                except Exception as e:
                    print(f"❌ Error comparing with student {nis}: {e}")
                    continue
            
            return best_match
            
        except Exception as e:
            print(f"❌ Error in compare_faces: {e}")
            return None
    
    @staticmethod
    def cosine_similarity(vec1, vec2):
        try:
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0
            
            similarity = dot_product / (norm1 * norm2)
            return max(0, min(1, similarity))
        except:
            return 0

face_recognizer = FaceRecognizer()

@app.route('/frontend/<path:path>')
def serve_frontend(path):
    return send_from_directory('../frontend', path)

@app.route('/')
def home():
    return send_from_directory('../frontend', 'index.html')

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """Login untuk admin"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return jsonify({
                'success': True,
                'message': 'Login berhasil',
                'token': ADMIN_TOKEN,
                'user': {
                    'username': username,
                    'role': 'admin'
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Username atau password salah'
            }), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    """Dashboard data untuk admin"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM students")
        total_students = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM attendance")
        total_attendance = c.fetchone()[0]
        
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('''SELECT COUNT(DISTINCT student_id) FROM attendance 
                     WHERE DATE(timestamp) = ?''', (today,))
        today_attendance = c.fetchone()[0]
        
        week_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        c.execute('''SELECT COUNT(DISTINCT student_id) FROM attendance 
                     WHERE DATE(timestamp) >= ?''', (week_start,))
        week_attendance = c.fetchone()[0]
        
        month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        c.execute('''SELECT COUNT(DISTINCT student_id) FROM attendance 
                     WHERE DATE(timestamp) >= ?''', (month_start,))
        month_attendance = c.fetchone()[0]
        
        c.execute('''SELECT a.id, s.nis, s.name, s.class, a.timestamp 
                     FROM attendance a
                     JOIN students s ON a.student_id = s.id
                     ORDER BY a.timestamp DESC LIMIT 10''')
        recent_attendance = c.fetchall()
        
        c.execute('''SELECT s.class, COUNT(DISTINCT s.id) as total_students,
                     COUNT(a.id) as total_attendance
                     FROM students s
                     LEFT JOIN attendance a ON s.id = a.student_id 
                     AND DATE(a.timestamp) = ?
                     GROUP BY s.class''', (today,))
        class_stats = c.fetchall()
        
        c.execute('''SELECT DATE(timestamp) as date, 
                     COUNT(DISTINCT student_id) as attendance_count
                     FROM attendance 
                     WHERE DATE(timestamp) >= ?
                     GROUP BY DATE(timestamp)
                     ORDER BY date DESC''', (week_start,))
        daily_stats = c.fetchall()
        
        conn.close()
        
        recent_list = []
        for att in recent_attendance:
            recent_list.append({
                'id': att[0],
                'nis': att[1],
                'name': att[2],
                'class': att[3],
                'timestamp': att[4]
            })
        
        class_list = []
        for cls in class_stats:
            class_list.append({
                'class': cls[0],
                'total_students': cls[1],
                'today_attendance': cls[2]
            })
        
        daily_list = []
        for daily in daily_stats:
            daily_list.append({
                'date': daily[0],
                'attendance_count': daily[1]
            })
        
        return jsonify({
            'success': True,
            'stats': {
                'total_students': total_students,
                'total_attendance': total_attendance,
                'today_attendance': today_attendance,
                'week_attendance': week_attendance,
                'month_attendance': month_attendance,
                'attendance_rate_today': round((today_attendance / total_students * 100) if total_students > 0 else 0, 1),
                'attendance_rate_week': round((week_attendance / total_students * 100) if total_students > 0 else 0, 1)
            },
            'recent_attendance': recent_list,
            'class_stats': class_list,
            'daily_stats': daily_list,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/students/manage', methods=['GET'])
@admin_required
def admin_manage_students():
    """Get all students for management"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute('''SELECT s.id, s.nis, s.name, s.class, s.registration_date,
                     COUNT(a.id) as attendance_count,
                     MAX(a.timestamp) as last_attendance,
                     (s.face_embedding IS NOT NULL) as has_photo
                     FROM students s
                     LEFT JOIN attendance a ON s.id = a.student_id
                     GROUP BY s.id
                     ORDER BY s.name''')
        students = c.fetchall()
        
        conn.close()
        
        students_list = []
        for student in students:
            students_list.append({
                'id': student[0],
                'nis': student[1],
                'name': student[2],
                'class': student[3],
                'registration_date': student[4],
                'attendance_count': student[5] or 0,
                'has_photo': bool(student[7]),
                'nis_pending': bool(student[1] and student[1].startswith('PPDB-')),
                'last_attendance': student[6] or 'Belum pernah absen'
            })
        
        return jsonify({
            'success': True,
            'students': students_list,
            'total': len(students_list)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/students/<int:student_id>', methods=['PUT'])
@admin_required
def admin_edit_student(student_id):
    """Admin mengedit data siswa (terutama untuk melengkapi NIS setelah
    data otomatis masuk dari persetujuan PPDB)."""
    try:
        data = request.json or {}
        nis = (data.get('nis') or '').strip()
        name = (data.get('name') or '').strip()
        student_class = (data.get('class') or '').strip()

        if not all([nis, name, student_class]):
            return jsonify({'success': False, 'error': 'NIS, nama, dan kelas wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()

        c.execute("SELECT id FROM students WHERE id = ?", (student_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Siswa tidak ditemukan'}), 404

        c.execute("SELECT id FROM students WHERE nis = ? AND id != ?", (nis, student_id))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'NIS sudah dipakai siswa lain'}), 400

        c.execute("UPDATE students SET nis = ?, name = ?, class = ? WHERE id = ?",
                  (nis, name, student_class, student_id))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Data siswa berhasil diperbarui'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/students/<int:student_id>', methods=['DELETE'])
@admin_required
def admin_delete_student(student_id):
    """Delete a student"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
        c.execute("DELETE FROM students WHERE id = ?", (student_id,))
        # Kalau siswa ini berasal dari pendaftaran PPDB yang diterima, lepaskan
        # tautannya supaya kalau admin klik "Terima" lagi, sistem tahu siswanya
        # sudah tidak ada dan otomatis membuatkan data siswa baru.
        c.execute("UPDATE admissions SET converted_student_id = NULL WHERE converted_student_id = ?", (student_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Siswa berhasil dihapus'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/attendance', methods=['GET'])
@admin_required
def admin_attendance_report():
    """Get detailed attendance report"""
    try:
        date_from = request.args.get('from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        date_to = request.args.get('to', datetime.now().strftime('%Y-%m-%d'))
        class_filter = (request.args.get('class') or '').strip()
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        if class_filter:
            c.execute('''SELECT a.id, s.nis, s.name, s.class, a.timestamp
                         FROM attendance a
                         JOIN students s ON a.student_id = s.id
                         WHERE DATE(a.timestamp) BETWEEN ? AND ? AND s.class = ?
                         ORDER BY a.timestamp DESC''', (date_from, date_to, class_filter))
        else:
            c.execute('''SELECT a.id, s.nis, s.name, s.class, a.timestamp
                         FROM attendance a
                         JOIN students s ON a.student_id = s.id
                         WHERE DATE(a.timestamp) BETWEEN ? AND ?
                         ORDER BY a.timestamp DESC''', (date_from, date_to))
        attendance = c.fetchall()
        
        c.execute('''SELECT DATE(timestamp) as date, 
                     COUNT(DISTINCT student_id) as unique_attendance,
                     COUNT(*) as total_records
                     FROM attendance 
                     WHERE DATE(timestamp) BETWEEN ? AND ?
                     GROUP BY DATE(timestamp)
                     ORDER BY date''', (date_from, date_to))
        summary = c.fetchall()
        
        conn.close()
        
        attendance_list = []
        for att in attendance:
            attendance_list.append({
                'id': att[0],
                'nis': att[1],
                'name': att[2],
                'class': att[3],
                'timestamp': att[4]
            })
        
        summary_list = []
        for sum in summary:
            summary_list.append({
                'date': sum[0],
                'unique_attendance': sum[1],
                'total_records': sum[2]
            })
        
        return jsonify({
            'success': True,
            'attendance': attendance_list,
            'summary': summary_list,
            'date_range': {
                'from': date_from,
                'to': date_to
            },
            'total_records': len(attendance_list)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/export/attendance', methods=['GET'])
@admin_required
def export_attendance():
    """Export attendance to CSV"""
    try:
        date_from = request.args.get('from', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        date_to = request.args.get('to', datetime.now().strftime('%Y-%m-%d'))
        class_filter = (request.args.get('class') or '').strip()
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        if class_filter:
            c.execute('''SELECT s.nis, s.name, s.class, a.timestamp
                         FROM attendance a
                         JOIN students s ON a.student_id = s.id
                         WHERE DATE(a.timestamp) BETWEEN ? AND ? AND s.class = ?
                         ORDER BY a.timestamp''', (date_from, date_to, class_filter))
        else:
            c.execute('''SELECT s.nis, s.name, s.class, a.timestamp
                         FROM attendance a
                         JOIN students s ON a.student_id = s.id
                         WHERE DATE(a.timestamp) BETWEEN ? AND ?
                         ORDER BY a.timestamp''', (date_from, date_to))
        records = c.fetchall()
        
        conn.close()
        
        csv_content = "NIS,Nama,Kelas,Waktu Absensi\n"
        for record in records:
            csv_content += f"{record[0]},{record[1]},{record[2]},{record[3]}\n"
        
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename=attendance_{date_from}_to_{date_to}.csv"}
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/system/info', methods=['GET'])
@admin_required
def system_info():
    """Get system information"""
    try:
        info = {
            'python_version': platform.python_version(),
            'system': platform.system(),
            'database_size': os.path.getsize(DATABASE_PATH) if os.path.exists(DATABASE_PATH) else 0,
            'server_uptime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_users': 1,
            'api_version': '1.0.0'
        }
        
        return jsonify({
            'success': True,
            'system_info': info
        })
        
    except Exception as e:
        return jsonify({
            'success': True,
            'system_info': {
                'error': 'Some metrics unavailable',
                'api_version': '1.0.0'
            }
        })

@app.route('/api/admin/test', methods=['GET'])
def admin_test():
    """Test admin API"""
    return jsonify({
        'success': True,
        'message': 'Admin API is working',
        'admin_endpoints': {
            'login': 'POST /api/admin/login',
            'dashboard': 'GET /api/admin/dashboard',
            'students': 'GET /api/admin/students/manage',
            'attendance': 'GET /api/admin/attendance',
            'export': 'GET /api/admin/export/attendance',
            'system': 'GET /api/admin/system/info'
        }
    })

@app.route('/api/admission/submit', methods=['POST'])
def submit_admission():
    """Formulir Pendaftaran Siswa Baru (PPDB) - publik, tanpa login.
    Menyimpan data calon siswa dan mengembalikan nomor pendaftaran
    yang dipakai untuk mencetak bukti pendaftaran (PDF) di sisi klien."""
    try:
        data = request.json or {}

        full_name = (data.get('full_name') or '').strip()
        nik = (data.get('nik') or '').strip()
        birth_place = (data.get('birth_place') or '').strip()
        birth_date = (data.get('birth_date') or '').strip()
        gender = (data.get('gender') or '').strip()
        address = (data.get('address') or '').strip()
        parent_name = (data.get('parent_name') or '').strip()
        phone = (data.get('phone') or '').strip()
        previous_school = (data.get('previous_school') or '').strip()
        target_class = (data.get('target_class') or '').strip()
        extracurricular = (data.get('extracurricular') or '').strip()
        photo = data.get('photo') or ''

        required = [full_name, nik, birth_place, birth_date, gender, address, parent_name, phone, target_class]
        if not all(required):
            return jsonify({'success': False, 'error': 'Mohon lengkapi semua kolom wajib'}), 400

        if len(nik) != 16 or not nik.isdigit():
            return jsonify({'success': False, 'error': 'NIK harus terdiri dari 16 digit angka'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()

        # Cegah pendaftaran ganda dengan NIK yang sama
        c.execute("SELECT registration_no FROM admissions WHERE nik = ?", (nik,))
        existing = c.fetchone()
        if existing:
            conn.close()
            return jsonify({
                'success': False,
                'error': f'NIK ini sudah pernah mendaftar dengan nomor pendaftaran {existing[0]}. Satu NIK hanya boleh mendaftar sekali.'
            }), 400

        today_str = datetime.now().strftime('%Y%m%d')
        c.execute("SELECT COUNT(*) FROM admissions WHERE registration_no LIKE ?", (f'PPDB-{today_str}-%',))
        count_today = c.fetchone()[0] + 1
        registration_no = f'PPDB-{today_str}-{count_today:04d}'

        c.execute('''INSERT INTO admissions
                     (registration_no, full_name, nik, birth_place, birth_date, gender,
                      address, parent_name, phone, previous_school, target_class, extracurricular, photo, payment_amount, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (registration_no, full_name, nik, birth_place, birth_date, gender,
                   address, parent_name, phone, previous_school, target_class, extracurricular, photo, PAYMENT_AMOUNT,
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        conn.commit()
        admission_id = c.lastrowid
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Pendaftaran berhasil disimpan',
            'admission_id': admission_id,
            'registration_no': registration_no,
            'payment_amount': PAYMENT_AMOUNT,
            'submitted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        print(f"❌ Admission submit error: {str(e)}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@app.route('/api/admission/list', methods=['GET'])
@admin_required
def list_admissions():
    """Daftar pendaftar PPDB untuk ditinjau admin/guru."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT id, registration_no, full_name, nik, birth_place, birth_date,
                            gender, address, parent_name, phone, previous_school,
                            target_class, extracurricular, status, status_note, status_updated_at, created_at
                     FROM admissions ORDER BY created_at DESC''')
        rows = c.fetchall()
        conn.close()

        columns = ['id', 'registration_no', 'full_name', 'nik', 'birth_place', 'birth_date',
                   'gender', 'address', 'parent_name', 'phone', 'previous_school',
                   'target_class', 'extracurricular', 'status', 'status_note', 'status_updated_at', 'created_at']
        admissions = [dict(zip(columns, row)) for row in rows]
        for a in admissions:
            if not a.get('status'):
                a['status'] = 'pending'

        return jsonify({'success': True, 'admissions': admissions, 'total': len(admissions)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admission/<int:admission_id>/status', methods=['PUT'])
@admin_required
def update_admission_status(admission_id):
    """Admin/guru menandai pendaftar PPDB sebagai diterima/ditolak/menunggu.
    Kalau diterima, otomatis buat data siswa di Kelola Data Siswa (NIS masih
    kosong/placeholder, admin lengkapi belakangan lewat Edit Siswa)."""
    try:
        data = request.json or {}
        status = (data.get('status') or '').strip().lower()
        note = (data.get('note') or '').strip()

        if status not in ('pending', 'diterima', 'ditolak', 'perlu_lengkapi_berkas'):
            return jsonify({'success': False, 'error': 'Status tidak valid'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT full_name, target_class, converted_student_id FROM admissions WHERE id = ?", (admission_id,))
        admission = c.fetchone()
        if not admission:
            conn.close()
            return jsonify({'success': False, 'error': 'Data pendaftar tidak ditemukan'}), 404

        full_name, target_class, converted_student_id = admission

        c.execute('''UPDATE admissions SET status = ?, status_note = ?, status_updated_at = ? WHERE id = ?''',
                  (status, note, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), admission_id))

        student_created = False
        needs_new_student = False
        if status == 'diterima':
            if not converted_student_id:
                needs_new_student = True
            else:
                c.execute("SELECT id FROM students WHERE id = ?", (converted_student_id,))
                if not c.fetchone():
                    # converted_student_id lama menunjuk ke siswa yang sudah dihapus
                    # dari Kelola Data Siswa -> buat ulang data siswanya
                    needs_new_student = True

        if needs_new_student:
            # NIS sengaja diisi placeholder unik (bukan kosong beneran, karena
            # kolom NIS di tabel students bersifat UNIQUE NOT NULL). Admin akan
            # menggantinya lewat Edit Siswa di Kelola Data Siswa.
            placeholder_nis = f'PPDB-{admission_id:05d}'
            c.execute('''INSERT INTO students (nis, name, class, face_embedding, registration_date)
                         VALUES (?, ?, ?, NULL, ?)''',
                      (placeholder_nis, full_name, target_class or '-', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            new_student_id = c.lastrowid
            c.execute("UPDATE admissions SET converted_student_id = ? WHERE id = ?", (new_student_id, admission_id))
            student_created = True

        conn.commit()
        conn.close()

        message = 'Status pendaftaran berhasil diperbarui'
        if student_created:
            message += '. Data siswa otomatis dibuat di Kelola Data Siswa - lengkapi NIS-nya lewat Edit Siswa.'

        return jsonify({'success': True, 'message': message, 'student_created': student_created})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admission/status', methods=['GET'])
def check_admission_status():
    """Cek status pendaftaran PPDB - publik, dicari lewat nomor pendaftaran atau NIK."""
    try:
        reg_no = (request.args.get('registration_no') or '').strip()
        nik = (request.args.get('nik') or '').strip()

        if not reg_no and not nik:
            return jsonify({'success': False, 'error': 'Nomor pendaftaran atau NIK wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        if reg_no:
            c.execute('''SELECT registration_no, full_name, target_class, status, status_note,
                                status_updated_at, created_at
                         FROM admissions WHERE registration_no = ?''', (reg_no,))
        else:
            c.execute('''SELECT registration_no, full_name, target_class, status, status_note,
                                status_updated_at, created_at
                         FROM admissions WHERE nik = ?''', (nik,))
        row = c.fetchone()
        conn.close()

        if not row:
            return jsonify({'success': False, 'error': 'Data pendaftaran tidak ditemukan. Cek kembali nomor pendaftaran/NIK Anda.'}), 404

        return jsonify({
            'success': True,
            'admission': {
                'registration_no': row[0],
                'full_name': row[1],
                'target_class': row[2],
                'status': row[3] or 'pending',
                'status_note': row[4] or '',
                'status_updated_at': row[5],
                'created_at': row[6]
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


DOC_TYPE_LABELS = {
    'nik': 'Kartu Keluarga / NIK',
    'akta_lahir': 'Akta Kelahiran',
    'bukti_bayar': 'Bukti Pembayaran PPDB',
    'lainnya': 'Berkas Pendukung Lainnya'
}


@app.route('/api/admission/documents', methods=['POST'])
def upload_admission_document():
    """Calon siswa mengunggah satu berkas persyaratan (NIK, akta lahir, bukti bayar,
    dll) - publik, diverifikasi lewat nomor pendaftaran. Upload ulang jenis berkas
    yang sama akan menimpa yang lama."""
    try:
        data = request.json or {}
        reg_no = (data.get('registration_no') or '').strip()
        doc_type = (data.get('doc_type') or '').strip().lower()
        file_name = (data.get('file_name') or '').strip()
        file_data = data.get('file_data') or ''

        if doc_type not in DOC_TYPE_LABELS:
            return jsonify({'success': False, 'error': 'Jenis berkas tidak valid'}), 400
        if not reg_no or not file_data:
            return jsonify({'success': False, 'error': 'Nomor pendaftaran dan file wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM admissions WHERE registration_no = ?", (reg_no,))
        admission = c.fetchone()
        if not admission:
            conn.close()
            return jsonify({'success': False, 'error': 'Nomor pendaftaran tidak ditemukan'}), 404

        admission_id = admission[0]
        c.execute('''INSERT INTO admission_documents (admission_id, doc_type, file_name, file_data, uploaded_at)
                     VALUES (?, ?, ?, ?, ?)
                     ON CONFLICT(admission_id, doc_type) DO UPDATE SET
                         file_name=excluded.file_name, file_data=excluded.file_data, uploaded_at=excluded.uploaded_at''',
                  (admission_id, doc_type, file_name, file_data, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': f'{DOC_TYPE_LABELS[doc_type]} berhasil diunggah'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admission/documents', methods=['GET'])
def get_admission_documents_public():
    """Daftar berkas yang sudah diunggah untuk satu pendaftaran - publik,
    dicari lewat nomor pendaftaran (dipakai halaman Perlengkapan Berkas)."""
    try:
        reg_no = (request.args.get('registration_no') or '').strip()
        if not reg_no:
            return jsonify({'success': False, 'error': 'Nomor pendaftaran wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, full_name FROM admissions WHERE registration_no = ?", (reg_no,))
        admission = c.fetchone()
        if not admission:
            conn.close()
            return jsonify({'success': False, 'error': 'Nomor pendaftaran tidak ditemukan'}), 404

        c.execute('''SELECT doc_type, file_name, uploaded_at FROM admission_documents WHERE admission_id = ?''',
                  (admission[0],))
        rows = c.fetchall()
        conn.close()

        uploaded = {r[0]: {'file_name': r[1], 'uploaded_at': r[2]} for r in rows}
        return jsonify({'success': True, 'full_name': admission[1], 'uploaded': uploaded})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admission/<int:admission_id>/documents', methods=['GET'])
@admin_required
def get_admission_documents_admin(admission_id):
    """Lihat semua berkas satu pendaftar (buat validasi admin)."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT doc_type, file_name, file_data, uploaded_at FROM admission_documents WHERE admission_id = ?''',
                  (admission_id,))
        rows = c.fetchall()
        conn.close()

        docs = [{
            'doc_type': r[0], 'label': DOC_TYPE_LABELS.get(r[0], r[0]),
            'file_name': r[1], 'file_data': r[2], 'uploaded_at': r[3]
        } for r in rows]
        return jsonify({'success': True, 'documents': docs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/admission/stats-yearly', methods=['GET'])
@admin_required
def get_admission_yearly_stats():
    """Rekap jumlah pendaftar PPDB per tahun, plus rincian statusnya."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT strftime('%Y', created_at) as year,
                            COUNT(*) as total,
                            SUM(CASE WHEN status = 'diterima' THEN 1 ELSE 0 END) as accepted,
                            SUM(CASE WHEN status = 'ditolak' THEN 1 ELSE 0 END) as rejected,
                            SUM(CASE WHEN status IS NULL OR status = 'pending' THEN 1 ELSE 0 END) as pending
                     FROM admissions
                     GROUP BY year
                     ORDER BY year DESC''')
        rows = c.fetchall()
        conn.close()

        yearly = [{'year': r[0], 'total': r[1], 'accepted': r[2] or 0, 'rejected': r[3] or 0, 'pending': r[4] or 0} for r in rows]
        return jsonify({'success': True, 'yearly': yearly})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/student/login', methods=['POST'])
def student_login():
    """Portal siswa: masuk dengan NIS saja."""
    try:
        data = request.json or {}
        nis = (data.get('nis') or '').strip()
        if not nis:
            return jsonify({'success': False, 'error': 'NIS wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, nis, name, class, registration_date, profile_photo FROM students WHERE nis = ?", (nis,))
        student = c.fetchone()

        if not student:
            conn.close()
            return jsonify({'success': False, 'error': 'NIS tidak ditemukan. Hubungi admin/guru untuk pendaftaran wajah.'}), 404

        student_id, nis, name, student_class, reg_date, profile_photo = student
        c.execute("SELECT COUNT(*) FROM attendance WHERE student_id = ?", (student_id,))
        attendance_count = c.fetchone()[0]
        conn.close()

        return jsonify({
            'success': True,
            'student': {
                'id': student_id,
                'nis': nis,
                'name': name,
                'class': student_class,
                'registration_date': reg_date,
                'attendance_count': attendance_count,
                'profile_photo': profile_photo or ''
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/student/history', methods=['GET'])
def student_history():
    """Riwayat absensi milik satu siswa, dicari lewat NIS. Status yang ditampilkan
    sudah memperhitungkan koreksi guru (attendance_overrides) - kalau guru
    mengoreksi status di suatu tanggal (misalnya siswa 'colong absen' lewat wajah
    tapi sebenarnya tidak masuk), riwayat siswa ikut berubah sesuai koreksi itu,
    bukan status asli hasil pengenalan wajah."""
    try:
        nis = (request.args.get('nis') or '').strip()
        if not nis:
            return jsonify({'success': False, 'error': 'NIS wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT timestamp, status FROM attendance WHERE nis = ? ORDER BY timestamp DESC LIMIT 60''', (nis,))
        att_rows = c.fetchall()

        c.execute('''SELECT att_date, status FROM attendance_overrides WHERE nis = ? ORDER BY att_date DESC LIMIT 60''', (nis,))
        override_rows = c.fetchall()
        conn.close()

        override_map = {r[0]: r[1] for r in override_rows}
        dates_with_attendance = set()
        history_detail = []
        for ts, status in att_rows:
            date_str = (ts or '')[:10]
            dates_with_attendance.add(date_str)
            history_detail.append({
                'timestamp': ts,
                'status': override_map.get(date_str, status or 'hadir'),
                'corrected': date_str in override_map
            })

        # Koreksi guru yang tidak punya rekaman wajah sama sekali (mis. izin/sakit
        # yang disetujui, atau alfa yang ditandai manual) tetap harus muncul
        for date_str, status in override_map.items():
            if date_str not in dates_with_attendance:
                history_detail.append({'timestamp': date_str + ' 00:00:00', 'status': status, 'corrected': True})

        history_detail.sort(key=lambda r: r['timestamp'], reverse=True)
        history_detail = history_detail[:30]

        return jsonify({
            'success': True,
            'history': [r['timestamp'] for r in history_detail],
            'history_detail': history_detail
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/student/attendance-summary', methods=['GET'])
def student_attendance_summary():
    """Rekap kehadiran bulan berjalan untuk satu siswa: gabungan absensi asli dan
    koreksi guru, dihitung sejak tanggal siswa terdaftar (bukan sejak tanggal 1),
    supaya persentase kehadiran portal siswa selalu sinkron dengan status terbaru."""
    try:
        nis = (request.args.get('nis') or '').strip()
        if not nis:
            return jsonify({'success': False, 'error': 'NIS wajib diisi'}), 400

        month_param = (request.args.get('month') or '').strip()
        today = datetime.now()
        if month_param:
            year, month = [int(x) for x in month_param.split('-')]
        else:
            year, month = today.year, today.month

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT registration_date FROM students WHERE nis = ?", (nis,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'NIS tidak ditemukan'}), 404
        registration_date = (row[0] or '')[:10]

        first_day = datetime(year, month, 1)
        last_day = datetime(year, 12, 31) if month == 12 else datetime(year, month + 1, 1) - timedelta(days=1)
        end_day = min(last_day, today) if (year, month) == (today.year, today.month) else last_day

        school_days = []
        d = first_day
        while d <= end_day:
            if d.weekday() < 5:
                day_str = d.strftime('%Y-%m-%d')
                if not registration_date or day_str >= registration_date:
                    school_days.append(day_str)
            d += timedelta(days=1)

        c.execute('''SELECT DATE(timestamp), status FROM attendance WHERE nis = ? AND DATE(timestamp) BETWEEN ? AND ?''',
                  (nis, first_day.strftime('%Y-%m-%d'), end_day.strftime('%Y-%m-%d')))
        att_map = {r[0]: (r[1] or 'hadir') for r in c.fetchall()}

        c.execute('''SELECT att_date, status FROM attendance_overrides WHERE nis = ? AND att_date BETWEEN ? AND ?''',
                  (nis, first_day.strftime('%Y-%m-%d'), end_day.strftime('%Y-%m-%d')))
        override_map = {r[0]: r[1] for r in c.fetchall()}
        conn.close()

        counts = {'hadir': 0, 'telat': 0, 'alfa': 0, 'sakit': 0, 'izin': 0}
        for day in school_days:
            status = override_map.get(day) or att_map.get(day) or 'alfa'
            if status not in counts:
                status = 'alfa'
            counts[status] += 1

        total_days = len(school_days)
        hadir_efektif = counts['hadir'] + counts['telat']
        percent = round((hadir_efektif / total_days) * 100) if total_days > 0 else 0

        return jsonify({
            'success': True,
            'period': first_day.strftime('%Y-%m'),
            'school_days_count': total_days,
            'percent': percent,
            'counts': counts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/leave-requests', methods=['POST'])
def submit_leave_request():
    """Siswa mengajukan izin/sakit tidak masuk sekolah - publik, diverifikasi lewat NIS."""
    try:
        data = request.json or {}
        nis = (data.get('nis') or '').strip()
        leave_type = (data.get('leave_type') or '').strip().lower()
        leave_date = (data.get('leave_date') or '').strip()
        reason = (data.get('reason') or '').strip()
        doctor_note = (data.get('doctor_note') or '').strip()

        if leave_type not in ('sakit', 'izin'):
            return jsonify({'success': False, 'error': 'Jenis izin tidak valid'}), 400
        if not nis or not leave_date or not reason:
            return jsonify({'success': False, 'error': 'NIS, tanggal, dan alasan wajib diisi'}), 400

        # Surat keterangan dokter wajib untuk pengajuan Sakit, tidak untuk Izin
        if leave_type == 'sakit' and not doctor_note:
            return jsonify({'success': False, 'error': 'Surat keterangan dokter wajib dilampirkan untuk pengajuan Sakit'}), 400

        # Batasi ukuran lampiran (kira-kira 5MB dalam bentuk base64) supaya database tidak membengkak
        if doctor_note and len(doctor_note) > 7_000_000:
            return jsonify({'success': False, 'error': 'Ukuran file surat dokter terlalu besar, maksimal 5MB'}), 400

        # Untuk pengajuan Izin, lampiran tidak dipakai sama sekali walau terlanjur dikirim dari klien
        if leave_type == 'izin':
            doctor_note = ''

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT name, class FROM students WHERE nis = ?", (nis,))
        student = c.fetchone()
        if not student:
            conn.close()
            return jsonify({'success': False, 'error': 'NIS tidak ditemukan'}), 404

        student_name, student_class = student
        c.execute('''INSERT INTO leave_requests (nis, student_name, class, leave_type, leave_date, reason, doctor_note, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (nis, student_name, student_class, leave_type, leave_date, reason, doctor_note or None,
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        request_id = c.lastrowid
        conn.close()

        return jsonify({'success': True, 'message': 'Pengajuan izin berhasil dikirim, menunggu persetujuan guru', 'id': request_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/student/leave-requests', methods=['GET'])
def get_student_leave_requests():
    """Riwayat pengajuan izin milik satu siswa, dicari lewat NIS."""
    try:
        nis = (request.args.get('nis') or '').strip()
        if not nis:
            return jsonify({'success': False, 'error': 'NIS wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT id, leave_type, leave_date, reason, status, reviewed_by, reviewed_at, created_at,
                     (doctor_note IS NOT NULL AND doctor_note != '') as has_doctor_note
                     FROM leave_requests WHERE nis = ? ORDER BY created_at DESC''', (nis,))
        rows = c.fetchall()
        conn.close()

        requests_list = [{
            'id': r[0], 'leave_type': r[1], 'leave_date': r[2], 'reason': r[3],
            'status': r[4], 'reviewed_by': r[5], 'reviewed_at': r[6], 'created_at': r[7],
            'has_doctor_note': bool(r[8])
        } for r in rows]
        return jsonify({'success': True, 'requests': requests_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/leave-requests/<int:request_id>/doctor-note', methods=['GET'])
@admin_or_teacher_required
def get_leave_request_doctor_note(request_id):
    """Ambil lampiran surat keterangan dokter (base64) untuk satu pengajuan sakit,
    dipakai guru/admin saat meninjau pengajuan sebelum menyetujui."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT doctor_note, class, leave_date FROM leave_requests WHERE id = ?", (request_id,))
        row = c.fetchone()
        conn.close()

        if not row or not row[0]:
            return jsonify({'success': False, 'error': 'Lampiran tidak ditemukan'}), 404

        doctor_note, class_name, leave_date = row
        if request.actor['role'] == 'teacher':
            if not _teacher_teaches_class_on_date(request.actor['teacher']['name'], class_name, leave_date):
                return jsonify({'success': False, 'error': 'Anda tidak mengajar di kelas ini pada hari sesuai tanggal pengajuan'}), 403

        return jsonify({'success': True, 'doctor_note': doctor_note})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/student/profile', methods=['PUT'])
def update_student_profile():
    """Siswa memperbarui nama miliknya sendiri (diverifikasi lewat NIS)."""
    try:
        data = request.json or {}
        nis = (data.get('nis') or '').strip()
        name = (data.get('name') or '').strip()

        if not nis or not name:
            return jsonify({'success': False, 'error': 'NIS dan nama wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM students WHERE nis = ?", (nis,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'NIS tidak ditemukan'}), 404

        c.execute("UPDATE students SET name = ? WHERE nis = ?", (name, nis))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Profil berhasil diperbarui'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/student/profile-photo', methods=['PUT'])
def update_student_profile_photo():
    """Siswa mengunggah foto profil (avatar tampilan saja, BUKAN foto pengenalan
    wajah untuk absensi - itu cuma bisa diambil oleh wali kelas lewat Portal Guru)."""
    try:
        data = request.json or {}
        nis = (data.get('nis') or '').strip()
        photo = data.get('photo') or ''

        if not nis or not photo:
            return jsonify({'success': False, 'error': 'NIS dan foto wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM students WHERE nis = ?", (nis,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'NIS tidak ditemukan'}), 404

        c.execute("UPDATE students SET profile_photo = ? WHERE nis = ?", (photo, nis))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Foto profil berhasil diperbarui'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/student/update-photo', methods=['POST'])
def update_student_photo():
    """Siswa memperbarui foto wajah mereka sendiri (diverifikasi lewat NIS)."""
    try:
        data = request.json or {}
        nis = (data.get('nis') or '').strip()
        face_image = data.get('face_image', '')

        if not nis or not face_image:
            return jsonify({'success': False, 'error': 'NIS dan foto wajib diisi'}), 400

        if ',' in face_image:
            face_image = face_image.split(',')[1]

        img_data = base64.b64decode(face_image)
        nparr = np.frombuffer(img_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            return jsonify({'success': False, 'error': 'Gambar tidak valid'}), 400

        bbox, error = face_recognizer.detect_face(image)
        if error:
            return jsonify({'success': False, 'error': f'Wajah tidak terdeteksi: {error}'}), 400

        embedding, error = face_recognizer.extract_face_embedding(image)
        if error:
            return jsonify({'success': False, 'error': f'Gagal mengambil fitur wajah: {error}'}), 400

        conn = face_recognizer.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM students WHERE nis = ?", (nis,))
        student = c.fetchone()
        if not student:
            conn.close()
            return jsonify({'success': False, 'error': 'NIS tidak ditemukan'}), 404

        embedding_blob = pickle.dumps(embedding)
        c.execute("UPDATE students SET face_embedding = ? WHERE nis = ?", (embedding_blob, nis))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Foto wajah berhasil diperbarui'})
    except Exception as e:
        print(f"❌ Update photo error: {str(e)}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@app.route('/api/school-info', methods=['GET'])
def get_school_info():
    """Info sekolah yang ditampilkan di beranda."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT vision_mission, facilities, achievements, hours_weekday, hours_friday, updated_at
                     FROM school_info WHERE id = 1''')
        row = c.fetchone()
        conn.close()

        if not row:
            return jsonify({'success': False, 'error': 'Info sekolah belum tersedia'}), 404

        return jsonify({
            'success': True,
            'school_info': {
                'vision_mission': row[0] or '',
                'facilities': (row[1] or '').split('\n') if row[1] else [],
                'achievements': row[2] or '',
                'hours_weekday': row[3] or '',
                'hours_friday': row[4] or '',
                'updated_at': row[5]
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/school-info', methods=['PUT'])
@admin_required
def update_school_info():
    """Update info sekolah (admin/guru only)."""
    try:
        data = request.json or {}
        vision_mission = data.get('vision_mission', '')
        facilities = data.get('facilities', '')
        if isinstance(facilities, list):
            facilities = '\n'.join(f.strip() for f in facilities if f.strip())
        achievements = data.get('achievements', '')
        hours_weekday = data.get('hours_weekday', '')
        hours_friday = data.get('hours_friday', '')

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''UPDATE school_info
                     SET vision_mission = ?, facilities = ?, achievements = ?,
                         hours_weekday = ?, hours_friday = ?, updated_at = ?
                     WHERE id = 1''',
                  (vision_mission, facilities, achievements, hours_weekday, hours_friday,
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Info sekolah berhasil diperbarui'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extracurriculars', methods=['GET'])
def get_extracurriculars():
    """Daftar ekstrakurikuler untuk ditampilkan di beranda (publik)."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT e.id, e.name, e.description, e.icon, e.photo, e.contact_name, e.contact_phone,
                     (SELECT COUNT(*) FROM ekskul_registrations r WHERE r.ekskul_name = e.name) as member_count
                     FROM extracurriculars e ORDER BY e.name''')
        rows = c.fetchall()
        conn.close()

        extracurriculars = [
            {'id': r[0], 'name': r[1], 'description': r[2] or '', 'icon': r[3] or 'fa-star', 'photo': r[4] or '',
             'contact_name': r[5] or '', 'contact_phone': r[6] or '', 'member_count': r[7] or 0}
            for r in rows
        ]
        return jsonify({'success': True, 'extracurriculars': extracurriculars})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extracurriculars/add', methods=['POST'])
@admin_required
def add_extracurricular():
    """Tambah ekstrakurikuler baru (admin/guru only)."""
    try:
        data = request.json or {}
        name = (data.get('name') or '').strip()
        description = (data.get('description') or '').strip()
        icon = (data.get('icon') or 'fa-star').strip()
        photo = data.get('photo') or ''  # base64 data URL, optional
        contact_name = (data.get('contact_name') or '').strip()
        contact_phone = (data.get('contact_phone') or '').strip()

        if not name:
            return jsonify({'success': False, 'error': 'Nama ekstrakurikuler wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO extracurriculars (name, description, icon, photo, contact_name, contact_phone, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (name, description, icon, photo, contact_name, contact_phone,
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        extracurricular_id = c.lastrowid
        conn.close()

        return jsonify({'success': True, 'message': 'Ekstrakurikuler berhasil ditambahkan', 'id': extracurricular_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extracurriculars/<int:extracurricular_id>', methods=['DELETE'])
@admin_required
def delete_extracurricular(extracurricular_id):
    """Hapus ekstrakurikuler (admin/guru only)."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''DELETE FROM extracurriculars WHERE id = ?''', (extracurricular_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Ekstrakurikuler berhasil dihapus'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    """Daftar pengumuman/berita - publik. Bisa disaring per audiens (all/siswa/guru)."""
    try:
        audience = (request.args.get('audience') or 'all').strip().lower()
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        if audience == 'all':
            c.execute('''SELECT id, title, description, image, link_url, audience, is_pinned, created_at
                         FROM announcements ORDER BY is_pinned DESC, created_at DESC''')
        else:
            c.execute('''SELECT id, title, description, image, link_url, audience, is_pinned, created_at
                         FROM announcements WHERE audience = 'all' OR audience = ?
                         ORDER BY is_pinned DESC, created_at DESC''', (audience,))
        rows = c.fetchall()
        conn.close()

        announcements = [{
            'id': r[0], 'title': r[1], 'description': r[2] or '', 'image': r[3] or '',
            'link_url': r[4] or '', 'audience': r[5] or 'all', 'is_pinned': bool(r[6]), 'created_at': r[7]
        } for r in rows]
        return jsonify({'success': True, 'announcements': announcements})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/announcements/add', methods=['POST'])
@admin_required
def add_announcement():
    """Tambah pengumuman/berita baru (admin/guru only)."""
    try:
        data = request.json or {}
        title = (data.get('title') or '').strip()
        description = (data.get('description') or '').strip()
        image = data.get('image') or ''
        link_url = (data.get('link_url') or '').strip()
        audience = (data.get('audience') or 'all').strip().lower()
        is_pinned = 1 if data.get('is_pinned') else 0

        if not title:
            return jsonify({'success': False, 'error': 'Judul pengumuman wajib diisi'}), 400
        if audience not in ('all', 'siswa', 'guru'):
            audience = 'all'

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO announcements (title, description, image, link_url, audience, is_pinned, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (title, description, image, link_url, audience, is_pinned,
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        announcement_id = c.lastrowid
        conn.close()

        return jsonify({'success': True, 'message': 'Pengumuman berhasil ditambahkan', 'id': announcement_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/announcements/<int:announcement_id>', methods=['DELETE'])
@admin_required
def delete_announcement(announcement_id):
    """Hapus pengumuman (admin/guru only)."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''DELETE FROM announcements WHERE id = ?''', (announcement_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Pengumuman berhasil dihapus'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ekskul/register', methods=['POST'])
def register_ekskul():
    """Pendaftaran ekstrakurikuler - publik, terpisah dari PPDB."""
    try:
        data = request.json or {}
        ekskul_name = (data.get('ekskul_name') or '').strip()
        full_name = (data.get('full_name') or '').strip()
        student_class = (data.get('class') or '').strip()
        phone = (data.get('phone') or '').strip()
        note = (data.get('note') or '').strip()

        if not all([ekskul_name, full_name, student_class, phone]):
            return jsonify({'success': False, 'error': 'Mohon lengkapi semua kolom wajib'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()

        # Ambil info kontak ekskul ini untuk disimpan sebagai snapshot di bukti pendaftaran
        c.execute("SELECT contact_name, contact_phone FROM extracurriculars WHERE name = ?", (ekskul_name,))
        contact_row = c.fetchone()
        contact_name = contact_row[0] if contact_row else ''
        contact_phone = contact_row[1] if contact_row else ''

        today_str = datetime.now().strftime('%Y%m%d')
        c.execute("SELECT COUNT(*) FROM ekskul_registrations WHERE registration_no LIKE ?", (f'EKS-{today_str}-%',))
        count_today = c.fetchone()[0] + 1
        registration_no = f'EKS-{today_str}-{count_today:04d}'

        c.execute('''INSERT INTO ekskul_registrations
                     (registration_no, ekskul_name, full_name, class, phone, note, contact_name, contact_phone, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (registration_no, ekskul_name, full_name, student_class, phone, note, contact_name, contact_phone,
                   datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        registration_id = c.lastrowid
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Pendaftaran ekstrakurikuler {ekskul_name} berhasil dikirim',
            'registration_id': registration_id,
            'registration_no': registration_no,
            'contact_name': contact_name,
            'contact_phone': contact_phone,
            'submitted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        print(f"❌ Ekskul register error: {str(e)}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@app.route('/api/ekskul/registrations', methods=['GET'])
@admin_required
def list_ekskul_registrations():
    """Daftar pendaftar ekstrakurikuler untuk admin/guru."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT id, registration_no, ekskul_name, full_name, class, phone, note, created_at
                     FROM ekskul_registrations ORDER BY created_at DESC''')
        rows = c.fetchall()
        conn.close()

        columns = ['id', 'registration_no', 'ekskul_name', 'full_name', 'class', 'phone', 'note', 'created_at']
        registrations = [dict(zip(columns, row)) for row in rows]

        return jsonify({'success': True, 'registrations': registrations, 'total': len(registrations)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/students/check-nis', methods=['GET'])
@admin_or_teacher_required
def check_nis():
    """Cek apakah NIS sudah dipakai siswa lain. Dipakai di modal Tambah Siswa
    Baru supaya guru langsung tahu kalau NIS yang diketik sudah terdaftar,
    sebelum sempat mengisi form dan mengambil foto."""
    try:
        nis = (request.args.get('nis') or '').strip()
        if not nis:
            return jsonify({'success': False, 'error': 'NIS wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT name, class FROM students WHERE nis = ?", (nis,))
        row = c.fetchone()
        conn.close()

        if row:
            return jsonify({'success': True, 'exists': True, 'name': row[0], 'class': row[1]})
        return jsonify({'success': True, 'exists': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/register', methods=['POST'])
@admin_or_teacher_required
def register_student():
    try:
        data = request.json
        nis = data.get('nis', '').strip()
        name = data.get('name', '').strip()
        student_class = data.get('class', '').strip()
        face_image = data.get('face_image', '')
        
        if not all([nis, name, student_class, face_image]):
            return jsonify({'error': 'All fields are required'}), 400

        # Guru hanya boleh mendaftarkan siswa untuk kelas perwaliannya sendiri
        if request.actor['role'] == 'teacher':
            homeroom = request.actor['teacher'].get('homeroom_class')
            if not homeroom:
                return jsonify({'error': 'Anda belum ditetapkan sebagai wali kelas. Hubungi admin.'}), 403
            if student_class != homeroom:
                return jsonify({'error': f'Anda hanya bisa mendaftarkan siswa untuk kelas perwalian Anda ({homeroom})'}), 403
        
        if ',' in face_image:
            face_image = face_image.split(',')[1]
        
        img_data = base64.b64decode(face_image)
        nparr = np.frombuffer(img_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({'error': 'Invalid image'}), 400
        
        bbox, error = face_recognizer.detect_face(image)
        if error:
            return jsonify({'error': f'Face detection failed: {error}'}), 400
        
        embedding, error = face_recognizer.extract_face_embedding(image)
        if error:
            return jsonify({'error': f'Face feature extraction failed: {error}'}), 400
        
        conn = face_recognizer.get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT id FROM students WHERE nis = ?", (nis,))
        if c.fetchone():
            conn.close()
            return jsonify({'error': 'NIS already registered'}), 400
        
        embedding_blob = pickle.dumps(embedding)
        c.execute('''INSERT INTO students (nis, name, class, face_embedding, registration_date)
                     VALUES (?, ?, ?, ?, ?)''',
                  (nis, name, student_class, embedding_blob, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        student_id = c.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'student_id': student_id
        })
        
    except Exception as e:
        print(f"❌ Registration error: {str(e)}")
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/recognize', methods=['POST'])
def recognize_face():
    try:
        if datetime.now().weekday() >= 5:
            return jsonify({
                'success': False,
                'error': 'Absensi hanya bisa dilakukan pada hari kerja (Senin - Jumat)'
            }), 403

        data = request.json
        face_image = data.get('face_image', '')
        
        if not face_image:
            return jsonify({'error': 'No image provided'}), 400
        
        if ',' in face_image:
            face_image = face_image.split(',')[1]
        
        img_data = base64.b64decode(face_image)
        nparr = np.frombuffer(img_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({'error': 'Invalid image data'}), 400
        
        bbox, error = face_recognizer.detect_face(image)
        if error:
            return jsonify({'error': error}), 400
        
        embedding, error = face_recognizer.extract_face_embedding(image)
        if error:
            return jsonify({'error': error}), 400
        
        match = face_recognizer.compare_faces(embedding, threshold=0.5)
        
        if match:
            today = datetime.now().strftime('%Y-%m-%d')
            conn = face_recognizer.get_db_connection()
            c = conn.cursor()

            c.execute('''SELECT COUNT(*) FROM attendance
                         WHERE student_id = ? AND DATE(timestamp) = ?''', (match['id'], today))
            already_attended = c.fetchone()[0] > 0

            if already_attended:
                conn.close()
                return jsonify({
                    'success': False,
                    'already_attended': True,
                    'student': match,
                    'error': f"{match['name']} sudah melakukan absensi hari ini"
                }), 409

            now = datetime.now()
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            cutoff = now.replace(hour=7, minute=0, second=0, microsecond=0)
            att_status = 'telat' if now > cutoff else 'hadir'

            c.execute('''INSERT INTO attendance (student_id, nis, name, class, status, timestamp)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (match['id'], match['nis'], match['name'], match['class'], att_status, timestamp))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'student': match,
                'attendance_time': timestamp,
                'status': att_status
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Face not recognized'
            }), 404
            
    except Exception as e:
        print(f"❌ Recognition error: {str(e)}")
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/students', methods=['GET'])
def get_students():
    try:
        conn = face_recognizer.get_db_connection()
        c = conn.cursor()
        
        c.execute('''SELECT id, nis, name, class, registration_date FROM students ORDER BY name''')
        students = c.fetchall()
        
        students_list = []
        for student in students:
            student_id, nis, name, student_class, reg_date = student
            
            c.execute('SELECT COUNT(*) FROM attendance WHERE student_id = ?', (student_id,))
            attendance_count = c.fetchone()[0]
            
            students_list.append({
                'id': student_id,
                'nis': nis,
                'name': name,
                'class': student_class,
                'registration_date': reg_date,
                'attendance_count': attendance_count
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'students': students_list,
            'total': len(students_list)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        conn = face_recognizer.get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM students")
        total_students = c.fetchone()[0]
        
        today = datetime.now().strftime('%Y-%m-%d')
        c.execute('SELECT COUNT(DISTINCT student_id) FROM attendance WHERE DATE(timestamp) = ?', (today,))
        today_attendance = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM attendance")
        total_attendance = c.fetchone()[0]
        
        conn.close()
        
        attendance_rate = (today_attendance / total_students * 100) if total_students > 0 else 0
        
        return jsonify({
            'success': True,
            'total_students': total_students,
            'today_attendance': today_attendance,
            'total_attendance': total_attendance,
            'attendance_rate': round(attendance_rate, 1)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check_face', methods=['POST'])
def check_face():
    try:
        data = request.json
        face_image = data.get('face_image', '')
        
        if not face_image:
            return jsonify({'error': 'No image provided'}), 400
        
        if ',' in face_image:
            face_image = face_image.split(',')[1]
        
        img_data = base64.b64decode(face_image)
        nparr = np.frombuffer(img_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return jsonify({'error': 'Invalid image data'}), 400
        
        bbox, error = face_recognizer.detect_face(image)
        
        if error:
            return jsonify({
                'face_detected': False,
                'message': error
            })
        
        return jsonify({
            'face_detected': True,
            'bbox': bbox,
            'message': 'Face detected'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test', methods=['GET'])
def test():
    db_exists = os.path.exists(DATABASE_PATH)
    return jsonify({
        'status': 'online',
        'message': 'Server is running',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'server_port': 5000,
        'database_exists': db_exists,
        'environment': 'pythonanywhere' if IS_PYTHONANYWHERE else 'local',
        'endpoints': {
            'register': 'POST /api/register',
            'recognize': 'POST /api/recognize',
            'students': 'GET /api/students',
            'stats': 'GET /api/stats',
            'check_face': 'POST /api/check_face',
            'admin_test': 'GET /api/admin/test'
        }
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Starting School Attendance System")
    print("=" * 60)
    print(f"📁 Database path: {DATABASE_PATH}")
    print(f"📊 Database exists: {os.path.exists(DATABASE_PATH)}")
    print(f"👤 Admin credentials: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print(f"🌍 Environment: {'PythonAnywhere' if IS_PYTHONANYWHERE else 'Local'}")
    print("=" * 60)
    
    if IS_PYTHONANYWHERE:
        print("📌 Running on PythonAnywhere - use WSGI configuration")
    else:
        print("📌 IMPORTANT LINKS:")
        print("  • Frontend: http://localhost:5000/")
        print("  • Admin Panel: http://localhost:5000/admin.html")
        print("  • API Test: http://localhost:5000/api/test")
        print("=" * 60)
        app.run(debug=True, port=5000, host='0.0.0.0')