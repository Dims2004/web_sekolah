// attendance.js - Logic for attendance page

class AttendanceManager {
    constructor() {
        this.video = document.getElementById('attendanceCamera');
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.stream = null;
        this.isRecognizing = false;
        this.recognitionInterval = null;
        this.faceCount = 0;
        this.recognitionCount = 0;
        this.attendanceRecords = [];
        this.recognitionDelay = 2000; // 2 seconds between recognitions
        this.apiUrl = '/api';
        
        // UI Elements
        this.statusIndicator = document.getElementById('statusIndicator');
        this.detectedFacesEl = document.getElementById('detectedFaces');
        this.recognizedFacesEl = document.getElementById('recognizedFaces');
        this.attendanceCountEl = document.getElementById('attendanceCount');
        this.recognitionResultEl = document.getElementById('recognitionResult');
        this.recentAttendanceEl = document.getElementById('recentAttendance');
        this.startBtn = document.getElementById('startBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.detectionFrame = document.getElementById('detectionFrame');
        this.confirmationModal = document.getElementById('confirmationModal');
        
        this.init();
    }
    
    async init() {
        try {
            await this.startCamera();
            this.setupEventListeners();
            this.updateDateTime();
            setInterval(() => this.updateDateTime(), 1000);
            await this.loadStats();
            await this.loadRecentAttendance();
        } catch (error) {
            this.showError('Initialization Error', error.message);
        }
    }
    
    setupEventListeners() {
        this.startBtn.addEventListener('click', () => this.startRecognition());
        this.stopBtn.addEventListener('click', () => this.stopRecognition());
        
        // Handle modal close
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.confirmationModal) {
                this.closeModal();
            }
        });
    }
    
    async startCamera() {
        try {
            // Check if browser supports getUserMedia
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('Browser tidak mendukung akses kamera');
            }
            
            // Get camera stream
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user',
                    frameRate: { ideal: 30 }
                },
                audio: false
            });
            
            this.video.srcObject = this.stream;
            
            // Wait for video to be ready
            await new Promise((resolve) => {
                this.video.onloadedmetadata = () => {
                    this.video.play();
                    resolve();
                };
            });
            
            console.log('Camera started successfully');
            this.updateStatus('ready', 'Kamera siap');
            
        } catch (error) {
            console.error('Camera error:', error);
            this.updateStatus('error', 'Gagal mengakses kamera');
            
            let errorMessage = 'Tidak dapat mengakses kamera. ';
            if (error.name === 'NotAllowedError') {
                errorMessage += 'Mohon izinkan akses kamera.';
            } else if (error.name === 'NotFoundError') {
                errorMessage += 'Kamera tidak ditemukan.';
            } else {
                errorMessage += error.message;
            }
            
            this.showToast(errorMessage, 'error');
        }
    }
    
    updateStatus(status, message) {
        if (!this.statusIndicator) return;
        
        const statusMap = {
            'ready': { color: 'bg-green-500', text: 'text-green-600', icon: 'fa-check-circle' },
            'recognizing': { color: 'bg-blue-500 animate-pulse', text: 'text-blue-600', icon: 'fa-spinner fa-spin' },
            'error': { color: 'bg-red-500', text: 'text-red-600', icon: 'fa-exclamation-circle' },
            'waiting': { color: 'bg-yellow-500', text: 'text-gray-600', icon: 'fa-clock' }
        };
        
        const config = statusMap[status] || statusMap.waiting;
        
        this.statusIndicator.innerHTML = `
            <span class="w-3 h-3 rounded-full ${config.color} mr-2"></span>
            <span class="${config.text} font-medium flex items-center">
                <i class="fas ${config.icon} mr-2"></i>${message}
            </span>
        `;
    }
    
    async startRecognition() {
        if (!this.video.srcObject) {
            this.showToast('Kamera belum siap', 'warning');
            return;
        }
        
        this.isRecognizing = true;
        this.startBtn.classList.add('hidden');
        this.stopBtn.classList.remove('hidden');
        
        this.updateStatus('recognizing', 'Mengenali wajah...');
        
        // Show detection frame
        this.detectionFrame.classList.remove('border-dashed');
        this.detectionFrame.classList.add('border-green-500', 'border-2', 'animate-pulse');
        
        // Start recognition loop
        this.recognitionInterval = setInterval(() => {
            this.captureAndRecognize();
        }, this.recognitionDelay);
    }
    
    stopRecognition() {
        this.isRecognizing = false;
        clearInterval(this.recognitionInterval);
        
        this.startBtn.classList.remove('hidden');
        this.stopBtn.classList.add('hidden');
        
        this.updateStatus('ready', 'Menunggu...');
        
        // Reset detection frame
        this.detectionFrame.classList.add('border-dashed');
        this.detectionFrame.classList.remove('border-green-500', 'border-2', 'animate-pulse');
    }
    
    async captureAndRecognize() {
        if (!this.isRecognizing) return;
        
        try {
            // Capture frame from video
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
            this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
            
            // Get image as base64
            const imageData = this.canvas.toDataURL('image/jpeg', 0.8);
            
            // Send to server for recognition
            const response = await fetch(`${this.apiUrl}/recognize`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ face_image: imageData })
            });
            
            const result = await response.json();
            
            // Update face count
            this.faceCount++;
            this.detectedFacesEl.textContent = this.faceCount;
            
            if (result.success) {
                this.handleSuccessfulRecognition(result);
            } else {
                this.handleFailedRecognition(result);
            }
            
        } catch (error) {
            console.error('Recognition error:', error);
            this.showToast('Gagal terhubung ke server', 'error');
        }
    }
    
    handleSuccessfulRecognition(result) {
        // Update counts
        this.recognitionCount++;
        this.recognizedFacesEl.textContent = this.recognitionCount;
        
        // Update attendance count
        const currentCount = parseInt(this.attendanceCountEl.textContent) || 0;
        this.attendanceCountEl.textContent = currentCount + 1;
        
        // Show result
        const student = result.student;
        const confidence = (student.confidence * 100).toFixed(1);
        
        this.recognitionResultEl.innerHTML = `
            <div class="text-center animate-fade-in">
                <div class="inline-flex items-center justify-center w-20 h-20 bg-green-100 rounded-full mb-4">
                    <i class="fas fa-user-check text-3xl text-green-600"></i>
                </div>
                <h3 class="text-xl font-bold text-gray-800 mb-2">${student.name}</h3>
                <p class="text-gray-600 mb-1">${student.class}</p>
                <p class="text-sm text-gray-500 mb-3">NIS: ${student.nis}</p>
                <div class="flex items-center justify-center mb-4">
                    <span class="text-xs font-semibold inline-block py-1 px-2 rounded-full bg-green-100 text-green-800">
                        <i class="fas fa-check-circle mr-1"></i>Akurasi: ${confidence}%
                    </span>
                </div>
                <div class="text-sm text-gray-500">
                    <i class="fas fa-clock mr-1"></i>${new Date(result.attendance_time).toLocaleTimeString('id-ID')}
                </div>
            </div>
        `;
        
        // Add to recent attendance
        this.addToRecentAttendance({
            name: student.name,
            nis: student.nis,
            time: new Date(result.attendance_time).toLocaleTimeString('id-ID')
        });
        
        // Show confirmation modal
        this.showConfirmationModal(student, result.attendance_time);
        
        // Play success sound (optional)
        this.playSound('success');
        
        // Stop recognition temporarily
        this.stopRecognition();
        
        // Restart after delay
        setTimeout(() => {
            if (this.video.srcObject) {
                this.startRecognition();
            }
        }, 3000);
    }
    
    handleFailedRecognition(result) {
        this.recognitionResultEl.innerHTML = `
            <div class="text-center animate-fade-in">
                <div class="inline-flex items-center justify-center w-20 h-20 bg-yellow-100 rounded-full mb-4">
                    <i class="fas fa-user-times text-3xl text-yellow-600"></i>
                </div>
                <h3 class="text-xl font-bold text-gray-800 mb-2">Wajah Tidak Dikenali</h3>
                <p class="text-gray-600 mb-4">Pastikan Anda sudah terdaftar di sistem</p>
                <a href="register.html" class="text-blue-600 hover:text-blue-800 text-sm inline-flex items-center">
                    <i class="fas fa-user-plus mr-2"></i>Daftar sekarang
                </a>
            </div>
        `;
        
        // Play error sound (optional)
        this.playSound('error');
    }
    
    addToRecentAttendance(record) {
        this.attendanceRecords.unshift(record);
        
        // Keep only last 10 records
        if (this.attendanceRecords.length > 10) {
            this.attendanceRecords.pop();
        }
        
        this.renderRecentAttendance();
    }
    
    renderRecentAttendance() {
        if (this.attendanceRecords.length === 0) {
            this.recentAttendanceEl.innerHTML = `
                <div class="text-center py-8 text-gray-400">
                    <i class="fas fa-history text-3xl mb-2"></i>
                    <p>Belum ada data absensi</p>
                </div>
            `;
            return;
        }
        
        this.recentAttendanceEl.innerHTML = this.attendanceRecords
            .map(record => `
                <div class="flex items-center justify-between bg-gray-50 p-3 rounded-lg hover:bg-gray-100 transition animate-fade-in">
                    <div>
                        <div class="font-medium text-gray-800">${record.name}</div>
                        <div class="text-sm text-gray-500">NIS: ${record.nis}</div>
                    </div>
                    <div class="text-sm font-medium text-green-600">
                        <i class="fas fa-clock mr-1"></i>${record.time}
                    </div>
                </div>
            `).join('');
    }
    
    showConfirmationModal(student, attendanceTime) {
        if (!this.confirmationModal) return;
        
        const studentDetails = document.getElementById('studentDetails');
        const dateTime = new Date(attendanceTime);
        
        studentDetails.innerHTML = `
            <div class="space-y-4">
                <div class="flex items-center">
                    <div class="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mr-4">
                        <i class="fas fa-id-card text-blue-600"></i>
                    </div>
                    <div>
                        <div class="text-sm text-gray-500">NIS</div>
                        <div class="font-semibold text-gray-800">${student.nis}</div>
                    </div>
                </div>
                <div class="flex items-center">
                    <div class="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mr-4">
                        <i class="fas fa-user text-green-600"></i>
                    </div>
                    <div>
                        <div class="text-sm text-gray-500">Nama</div>
                        <div class="font-semibold text-gray-800">${student.name}</div>
                    </div>
                </div>
                <div class="flex items-center">
                    <div class="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mr-4">
                        <i class="fas fa-graduation-cap text-purple-600"></i>
                    </div>
                    <div>
                        <div class="text-sm text-gray-500">Kelas</div>
                        <div class="font-semibold text-gray-800">${student.class}</div>
                    </div>
                </div>
                <div class="border-t border-gray-200 pt-4">
                    <div class="flex justify-between">
                        <span class="text-gray-600">Waktu</span>
                        <span class="font-semibold text-green-600">
                            ${dateTime.toLocaleTimeString('id-ID')}
                        </span>
                    </div>
                    <div class="text-sm text-gray-500 mt-1">
                        ${dateTime.toLocaleDateString('id-ID', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                    </div>
                </div>
            </div>
        `;
        
        this.confirmationModal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }
    
    closeModal() {
        if (this.confirmationModal) {
            this.confirmationModal.classList.add('hidden');
            document.body.style.overflow = 'auto';
        }
    }
    
    async loadStats() {
        try {
            const response = await fetch(`${this.apiUrl}/stats`);
            const data = await response.json();
            
            if (data.success) {
                this.attendanceCountEl.textContent = data.today_attendance || 0;
            }
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }
    
    async loadRecentAttendance() {
        try {
            const response = await fetch(`${this.apiUrl}/admin/attendance?days=1`);
            const data = await response.json();
            
            if (data.success && data.attendance) {
                this.attendanceRecords = data.attendance.slice(0, 10).map(record => ({
                    name: record.name,
                    nis: record.nis,
                    time: new Date(record.timestamp).toLocaleTimeString('id-ID')
                }));
                this.renderRecentAttendance();
            }
        } catch (error) {
            console.error('Error loading recent attendance:', error);
        }
    }
    
    updateDateTime() {
        const now = new Date();
        document.getElementById('currentTime').textContent = now.toLocaleTimeString('id-ID');
        document.getElementById('currentDate').textContent = now.toLocaleDateString('id-ID', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    }
    
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 transform transition-all duration-300 
                          ${type === 'success' ? 'bg-green-100 text-green-800 border-l-4 border-green-500' :
                            type === 'error' ? 'bg-red-100 text-red-800 border-l-4 border-red-500' :
                            'bg-blue-100 text-blue-800 border-l-4 border-blue-500'}`;
        
        const icon = type === 'success' ? 'fa-check-circle' :
                    type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle';
        
        toast.innerHTML = `
            <div class="flex items-center">
                <i class="fas ${icon} mr-3 text-xl"></i>
                <span>${message}</span>
            </div>
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-20px)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
    
    playSound(type) {
        // Optional: Add sound effects
        // You can implement this with Web Audio API or simple beep
        console.log(`Playing ${type} sound`);
    }
    
    async switchCamera() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoDevices = devices.filter(d => d.kind === 'videoinput');
            
            if (videoDevices.length < 2) {
                this.showToast('Hanya satu kamera yang tersedia', 'info');
                return;
            }
            
            // Get current device ID
            const currentTrack = this.stream.getVideoTracks()[0];
            const currentSettings = currentTrack.getSettings();
            const currentDeviceId = currentSettings.deviceId;
            
            // Find next camera
            const currentIndex = videoDevices.findIndex(d => d.deviceId === currentDeviceId);
            const nextIndex = (currentIndex + 1) % videoDevices.length;
            const nextDeviceId = videoDevices[nextIndex].deviceId;
            
            // Stop current stream
            this.stream.getTracks().forEach(track => track.stop());
            
            // Get new stream
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    deviceId: { exact: nextDeviceId },
                    width: { ideal: 640 },
                    height: { ideal: 480 }
                }
            });
            
            this.video.srcObject = this.stream;
            
            this.showToast('Kamera berhasil diganti', 'success');
            
        } catch (error) {
            console.error('Error switching camera:', error);
            this.showToast('Gagal mengganti kamera', 'error');
        }
    }
    
    cleanup() {
        this.stopRecognition();
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
        }
        this.confirmationModal.classList.add('hidden');
        document.body.style.overflow = 'auto';
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.attendanceManager = new AttendanceManager();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.attendanceManager) {
        window.attendanceManager.cleanup();
    }
});