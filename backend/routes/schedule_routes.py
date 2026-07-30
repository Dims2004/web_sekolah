from flask import Blueprint, request, jsonify
from models.schedule_model import ScheduleModel
import os
import sqlite3
import secrets
from datetime import datetime, timedelta

# Get database path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, '..', 'database', 'students.db')

# Initialize schedule model
schedule_model = ScheduleModel(DATABASE_PATH)

# Create blueprint
schedule_bp = Blueprint('schedule', __name__, url_prefix='/api/schedule')

# Admin authentication decorator (simplified)
def admin_required(f):
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != 'Bearer admin_token_secure_123':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


@schedule_bp.route('/teachers/login', methods=['POST'])
def teacher_login():
    """Login untuk guru (wali kelas)."""
    try:
        data = request.json or {}
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '').strip()

        if not username or not password:
            return jsonify({'success': False, 'error': 'Username dan password wajib diisi'}), 400

        teacher, error = schedule_model.get_teacher_by_username(username)
        if error or not teacher or not teacher.get('password') or teacher['password'] != password:
            return jsonify({'success': False, 'error': 'Username atau password salah'}), 401

        token = secrets.token_hex(24)
        schedule_model.set_teacher_token(teacher['id'], token)

        return jsonify({
            'success': True,
            'message': 'Login berhasil',
            'token': token,
            'teacher': {
                'id': teacher['id'],
                'name': teacher['name'],
                'subject': teacher['subject'],
                'username': teacher['username'],
                'homeroom_class': teacher['homeroom_class']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/teachers/me/students', methods=['GET'])
def teacher_me_students():
    """Daftar siswa di kelas perwalian guru yang sedang login (dicek lewat token)."""
    try:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header else ''
        teacher = schedule_model.get_teacher_by_token(token)
        if not teacher:
            return jsonify({'success': False, 'error': 'Sesi tidak valid, silakan login ulang'}), 401

        if not teacher.get('homeroom_class'):
            return jsonify({'success': True, 'students': [], 'homeroom_class': None, 'teacher': teacher})

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT id, nis, name, class, registration_date,
                     (face_embedding IS NOT NULL) as has_photo
                     FROM students WHERE class = ? ORDER BY name''', (teacher['homeroom_class'],))
        rows = c.fetchall()
        conn.close()

        students = [{'id': r[0], 'nis': r[1], 'name': r[2], 'class': r[3],
                     'registration_date': r[4], 'has_photo': bool(r[5])} for r in rows]
        return jsonify({'success': True, 'students': students, 'homeroom_class': teacher['homeroom_class'], 'teacher': teacher})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/teachers/me/schedule', methods=['GET'])
def teacher_me_schedule():
    """Jadwal mengajar guru yang sedang login, di SEMUA kelas yang dia ajar
    (bukan cuma kelas perwalian)."""
    try:
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '') if auth_header else ''
        teacher = schedule_model.get_teacher_by_token(token)
        if not teacher:
            return jsonify({'success': False, 'error': 'Sesi tidak valid, silakan login ulang'}), 401

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''SELECT id, class_name, day, time, subject, room, color
                     FROM schedules WHERE teacher = ? ORDER BY day, time''', (teacher['name'],))
        rows = c.fetchall()
        conn.close()

        schedule_list = [{'id': r[0], 'class_name': r[1], 'day': r[2], 'time': r[3],
                           'subject': r[4], 'room': r[5], 'color': r[6]} for r in rows]
        return jsonify({'success': True, 'schedule': schedule_list, 'teacher_name': teacher['name']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_current_teacher():
    """Ambil data guru dari token Authorization header. Return None kalau tidak valid."""
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '') if auth_header else ''
    return schedule_model.get_teacher_by_token(token)


def _teacher_teaches_class(teacher_name, class_name):
    """Cek apakah guru ini mengajar mata pelajaran di kelas tersebut (lewat jadwal),
    tanpa memandang hari. Dipakai untuk keperluan umum selain approval izin/sakit."""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM schedules WHERE teacher = ? AND class_name = ?", (teacher_name, class_name))
    count = c.fetchone()[0]
    conn.close()
    return count > 0


_INDONESIAN_DAY_NAMES = ['senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu', 'minggu']


def _day_name_from_date(date_str):
    """Ubah tanggal (YYYY-MM-DD) jadi nama hari dalam Bahasa Indonesia huruf kecil,
    supaya bisa dicocokkan dengan kolom `day` di tabel schedules."""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return _INDONESIAN_DAY_NAMES[dt.weekday()]
    except (ValueError, TypeError):
        return None


def _teacher_teaches_class_on_date(teacher_name, class_name, leave_date):
    """Cek apakah guru ini punya jadwal mengajar di kelas tersebut TEPAT pada hari
    yang sesuai dengan leave_date. Inilah yang menentukan hak setuju/tolak surat
    izin/sakit — dipegang guru mapel yang mengajar pada hari & jam itu, bukan
    otomatis wali kelas atau guru lain yang kebetulan mengajar kelas yang sama
    di hari lain."""
    day_name = _day_name_from_date(leave_date)
    if not day_name:
        return False
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM schedules WHERE teacher = ? AND class_name = ? AND day = ?",
              (teacher_name, class_name, day_name))
    count = c.fetchone()[0]
    conn.close()
    return count > 0


@schedule_bp.route('/teachers/me/classes', methods=['GET'])
def teacher_me_classes():
    """Daftar kelas yang diajar guru yang sedang login (dari jadwal mata pelajaran,
    BUKAN cuma kelas perwalian)."""
    try:
        teacher = _get_current_teacher()
        if not teacher:
            return jsonify({'success': False, 'error': 'Sesi tidak valid, silakan login ulang'}), 401

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT class_name FROM schedules WHERE teacher = ? ORDER BY class_name", (teacher['name'],))
        classes = [r[0] for r in c.fetchall()]
        conn.close()

        return jsonify({'success': True, 'classes': classes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/teachers/me/class-roster', methods=['GET'])
def teacher_class_roster():
    """Daftar siswa di kelas yang diajar guru + rekap status (Hadir/Telat/Alfa/Sakit/Izin)
    bulan berjalan (atau bulan tertentu lewat ?month=YYYY-MM)."""
    try:
        teacher = _get_current_teacher()
        if not teacher:
            return jsonify({'success': False, 'error': 'Sesi tidak valid, silakan login ulang'}), 401

        class_name = (request.args.get('class') or '').strip()
        if not class_name:
            return jsonify({'success': False, 'error': 'Parameter kelas wajib diisi'}), 400

        if not _teacher_teaches_class(teacher['name'], class_name):
            return jsonify({'success': False, 'error': 'Anda tidak mengajar di kelas ini'}), 403

        month_param = (request.args.get('month') or '').strip()
        today = datetime.now()
        if month_param:
            year, month = [int(x) for x in month_param.split('-')]
        else:
            year, month = today.year, today.month

        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year, 12, 31)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)
        end_day = min(last_day, today) if (year, month) == (today.year, today.month) else last_day

        # Kumpulkan tanggal hari kerja dalam rentang bulan tsb
        school_days = []
        d = first_day
        while d <= end_day:
            if d.weekday() < 5:
                school_days.append(d.strftime('%Y-%m-%d'))
            d += timedelta(days=1)

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT nis, name, registration_date FROM students WHERE class = ? ORDER BY name", (class_name,))
        students = c.fetchall()

        roster = []
        for nis, name, registration_date in students:
            # Siswa baru tidak boleh dihitung Alfa untuk hari-hari sebelum dia terdaftar
            reg_date_str = (registration_date or '')[:10]
            effective_days = [d for d in school_days if not reg_date_str or d >= reg_date_str]

            c.execute('''SELECT DATE(timestamp), status FROM attendance WHERE nis = ? AND DATE(timestamp) BETWEEN ? AND ?''',
                      (nis, first_day.strftime('%Y-%m-%d'), end_day.strftime('%Y-%m-%d')))
            att_map = {row[0]: (row[1] or 'hadir') for row in c.fetchall()}

            c.execute('''SELECT att_date, status FROM attendance_overrides WHERE nis = ? AND att_date BETWEEN ? AND ?''',
                      (nis, first_day.strftime('%Y-%m-%d'), end_day.strftime('%Y-%m-%d')))
            override_map = {row[0]: row[1] for row in c.fetchall()}

            counts = {'hadir': 0, 'telat': 0, 'alfa': 0, 'sakit': 0, 'izin': 0}
            for day in effective_days:
                status = override_map.get(day) or att_map.get(day) or 'alfa'
                if status not in counts:
                    status = 'alfa'
                counts[status] += 1

            roster.append({
                'nis': nis, 'name': name,
                'hadir': counts['hadir'], 'telat': counts['telat'],
                'alfa': counts['alfa'], 'sakit': counts['sakit'], 'izin': counts['izin']
            })

        conn.close()
        return jsonify({
            'success': True, 'roster': roster, 'class': class_name,
            'period': first_day.strftime('%Y-%m'), 'school_days_count': len(school_days)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/teachers/me/leave-requests', methods=['GET'])
def teacher_leave_requests():
    """Daftar pengajuan izin/sakit yang berhak disetujui/ditolak guru ini, yaitu
    pengajuan di kelas & hari yang sama persis dengan jadwal mengajarnya (bukan
    semua kelas yang pernah dia ajar di hari lain, dan bukan hak wali kelas)."""
    try:
        teacher = _get_current_teacher()
        if not teacher:
            return jsonify({'success': False, 'error': 'Sesi tidak valid, silakan login ulang'}), 401

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT class_name, day FROM schedules WHERE teacher = ?", (teacher['name'],))
        taught_class_days = set(c.fetchall())

        if not taught_class_days:
            conn.close()
            return jsonify({'success': True, 'requests': []})

        taught_classes = list(set(class_name for class_name, _ in taught_class_days))
        placeholders = ','.join('?' * len(taught_classes))
        c.execute(f'''SELECT id, nis, student_name, class, leave_type, leave_date, reason, status, created_at,
                     (doctor_note IS NOT NULL AND doctor_note != '') as has_doctor_note
                     FROM leave_requests WHERE class IN ({placeholders}) ORDER BY created_at DESC''', taught_classes)
        rows = c.fetchall()
        conn.close()

        requests_list = [{
            'id': r[0], 'nis': r[1], 'student_name': r[2], 'class': r[3], 'leave_type': r[4],
            'leave_date': r[5], 'reason': r[6] or '', 'status': r[7], 'created_at': r[8],
            'has_doctor_note': bool(r[9])
        } for r in rows if (r[3], _day_name_from_date(r[5])) in taught_class_days]
        return jsonify({'success': True, 'requests': requests_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/leave-requests/<int:request_id>/review', methods=['PUT'])
def review_leave_request(request_id):
    """Guru menyetujui/menolak pengajuan izin. Kalau disetujui, otomatis dicatat
    sebagai status Sakit/Izin di rekap absensi tanggal tersebut."""
    try:
        teacher = _get_current_teacher()
        if not teacher:
            return jsonify({'success': False, 'error': 'Sesi tidak valid, silakan login ulang'}), 401

        data = request.json or {}
        action = (data.get('action') or '').strip().lower()
        if action not in ('approve', 'reject'):
            return jsonify({'success': False, 'error': 'Aksi tidak valid'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT nis, class, leave_type, leave_date FROM leave_requests WHERE id = ?", (request_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Pengajuan tidak ditemukan'}), 404

        nis, class_name, leave_type, leave_date = row
        if not _teacher_teaches_class_on_date(teacher['name'], class_name, leave_date):
            conn.close()
            return jsonify({'success': False, 'error': 'Anda tidak mengajar di kelas ini pada hari sesuai tanggal pengajuan'}), 403

        new_status = 'disetujui' if action == 'approve' else 'ditolak'
        c.execute('''UPDATE leave_requests SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?''',
                  (new_status, teacher['name'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), request_id))

        if action == 'approve':
            c.execute('''INSERT INTO attendance_overrides (nis, att_date, status, note, updated_by, updated_at)
                         VALUES (?, ?, ?, ?, ?, ?)
                         ON CONFLICT(nis, att_date) DO UPDATE SET status=excluded.status, note=excluded.note,
                             updated_by=excluded.updated_by, updated_at=excluded.updated_at''',
                      (nis, leave_date, leave_type, 'Disetujui dari pengajuan izin', teacher['name'],
                       datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Pengajuan berhasil di-{"setujui" if action == "approve" else "tolak"}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/attendance/override', methods=['PUT'])
def set_attendance_override():
    """Guru mengoreksi/menambahkan status kehadiran manual (Hadir/Telat/Alfa/Sakit/Izin)
    untuk seorang siswa di kelas yang dia ajar, pada tanggal tertentu."""
    try:
        teacher = _get_current_teacher()
        if not teacher:
            return jsonify({'success': False, 'error': 'Sesi tidak valid, silakan login ulang'}), 401

        data = request.json or {}
        nis = (data.get('nis') or '').strip()
        att_date = (data.get('date') or '').strip()
        status = (data.get('status') or '').strip().lower()
        note = (data.get('note') or '').strip()

        if status not in ('hadir', 'telat', 'alfa', 'sakit', 'izin'):
            return jsonify({'success': False, 'error': 'Status tidak valid'}), 400
        if not nis or not att_date:
            return jsonify({'success': False, 'error': 'NIS dan tanggal wajib diisi'}), 400

        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT class FROM students WHERE nis = ?", (nis,))
        student = c.fetchone()
        if not student:
            conn.close()
            return jsonify({'success': False, 'error': 'Siswa tidak ditemukan'}), 404

        if not _teacher_teaches_class(teacher['name'], student[0]):
            conn.close()
            return jsonify({'success': False, 'error': 'Anda tidak mengajar di kelas siswa ini'}), 403

        c.execute('''INSERT INTO attendance_overrides (nis, att_date, status, note, updated_by, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?)
                     ON CONFLICT(nis, att_date) DO UPDATE SET status=excluded.status, note=excluded.note,
                         updated_by=excluded.updated_by, updated_at=excluded.updated_at''',
                  (nis, att_date, status, note, teacher['name'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Status kehadiran berhasil diperbarui'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/list', methods=['GET'])
def get_schedules():
    """Get all schedules (public)"""
    try:
        class_name = request.args.get('class')
        day = request.args.get('day', 'all')
        
        schedules, error = schedule_model.get_schedules(class_name, day)
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'schedule': schedules
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/add', methods=['POST'])
@admin_required
def add_schedule():
    """Add new schedule (admin only)"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['class_name', 'day', 'time', 'subject', 'teacher', 'room']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Validate day
        valid_days = ['senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu']
        if data['day'] not in valid_days:
            return jsonify({'success': False, 'error': 'Invalid day'}), 400
        
        schedule_id, error = schedule_model.add_schedule(data)
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'message': 'Schedule added successfully',
            'schedule_id': schedule_id
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/update/<int:schedule_id>', methods=['PUT'])
@admin_required
def update_schedule(schedule_id):
    """Update schedule (admin only)"""
    try:
        data = request.json
        success, error = schedule_model.update_schedule(schedule_id, data)
        
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'message': 'Schedule updated successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/delete/<int:schedule_id>', methods=['DELETE'])
@admin_required
def delete_schedule(schedule_id):
    """Delete schedule (admin only)"""
    try:
        success, error = schedule_model.delete_schedule(schedule_id)
        
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'message': 'Schedule deleted successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/teachers', methods=['GET'])
def get_teachers():
    """Get all teachers"""
    try:
        teachers, error = schedule_model.get_teachers()
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'teachers': teachers
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/teachers/add', methods=['POST'])
@admin_required
def add_teacher():
    """Add new teacher (admin only)"""
    try:
        data = request.json
        teacher_id, error = schedule_model.add_teacher(data)
        
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'message': 'Teacher added successfully',
            'teacher_id': teacher_id
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/teachers/<int:teacher_id>', methods=['PUT'])
@admin_required
def update_teacher(teacher_id):
    """Update teacher (admin only)"""
    try:
        data = request.json
        success, error = schedule_model.update_teacher(teacher_id, data)
        if error:
            return jsonify({'success': False, 'error': error}), 500

        return jsonify({'success': True, 'message': 'Data guru berhasil diperbarui'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/teachers/<int:teacher_id>', methods=['DELETE'])
@admin_required
def delete_teacher(teacher_id):
    """Delete teacher (admin only)"""
    try:
        success, error = schedule_model.delete_teacher(teacher_id)
        if error:
            return jsonify({'success': False, 'error': error}), 500

        return jsonify({'success': True, 'message': 'Teacher deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/rooms', methods=['GET'])
def get_rooms():
    """Get all rooms"""
    try:
        rooms, error = schedule_model.get_rooms()
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'rooms': rooms
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/rooms/add', methods=['POST'])
@admin_required
def add_room():
    """Add new room (admin only)"""
    try:
        data = request.json
        room_id, error = schedule_model.add_room(data)
        
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'message': 'Room added successfully',
            'room_id': room_id
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/classes', methods=['GET'])
def get_classes():
    """Get all classes"""
    try:
        classes, error = schedule_model.get_classes()
        if error:
            return jsonify({'success': False, 'error': error}), 500
        
        return jsonify({
            'success': True,
            'classes': classes
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/classes/add', methods=['POST'])
@admin_required
def add_class():
    """Add new class (admin only)"""
    try:
        data = request.json
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Nama kelas wajib diisi'}), 400

        class_id, error = schedule_model.add_class(name)
        if error:
            return jsonify({'success': False, 'error': error}), 500

        return jsonify({
            'success': True,
            'message': 'Kelas berhasil ditambahkan',
            'class_id': class_id
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500