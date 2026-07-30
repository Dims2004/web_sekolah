import os
import sys
import subprocess

def setup_project():
    print("=" * 50)
    print("🎓 School Attendance System Setup")
    print("=" * 50)
    
    # Create necessary directories
    directories = [
        'backend',
        'frontend',
        'frontend/css',
        'frontend/js',
        'database'
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✅ Created directory: {directory}")
        else:
            print(f"📁 Directory exists: {directory}")
    
    # Create requirements.txt
    requirements = """Flask==2.3.3
Flask-CORS==4.0.0
numpy==1.24.3
opencv-python==4.8.1.78
Pillow==10.0.0
mediapipe==0.10.7
"""
    
    with open('backend/requirements.txt', 'w') as f:
        f.write(requirements)
    print("✅ Created requirements.txt")
    
    # Create basic frontend files if they don't exist
    frontend_files = {
        'frontend/index.html': '''<!DOCTYPE html>
<html>
<head>
    <title>Sistem Absensi Sekolah</title>
</head>
<body>
    <h1>Sistem Absensi Sekolah</h1>
    <p>Frontend akan diisi nanti. Pastikan backend berjalan di http://localhost:5000</p>
    <a href="http://localhost:5000">Klik di sini untuk ke API</a>
</body>
</html>'''
    }
    
    for file_path, content in frontend_files.items():
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Created {file_path}")
    
    print("\n" + "=" * 50)
    print("📋 Setup Instructions:")
    print("=" * 50)
    print("1. Install dependencies:")
    print("   cd backend")
    print("   pip install -r requirements.txt")
    print("\n2. Run the server:")
    print("   python app.py")
    print("\n3. Open browser and go to:")
    print("   http://localhost:5000 (for API)")
    print("   or open frontend/index.html")
    print("\n4. For frontend development:")
    print("   Use Live Server extension in VS Code")
    print("=" * 50)

if __name__ == '__main__':
    setup_project()