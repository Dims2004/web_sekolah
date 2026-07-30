@echo off
echo ========================================
echo  School Attendance System - Windows
echo ========================================

echo.
echo Step 1: Checking Python installation...
python --version
if errorlevel 1 (
    echo Error: Python not found!
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

echo.
echo Step 2: Creating necessary directories...
if not exist database mkdir database
if not exist frontend\css mkdir frontend\css
if not exist frontend\js mkdir frontend\js

echo.
echo Step 3: Installing/upgrading pip...
python -m pip install --upgrade pip

echo.
echo Step 4: Installing dependencies...
cd backend
pip install Flask==2.3.3 Flask-CORS==4.0.0 numpy==1.24.3 opencv-python==4.8.1.78 Pillow==10.0.0 mediapipe==0.10.7

echo.
echo Step 5: Starting server...
echo Server will run on: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.
python app.py

pause