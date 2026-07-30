// register.js - Logic for registration page

class RegistrationManager {
    constructor() {
        this.video = document.getElementById('cameraPreview');
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.stream = null;
        this.cameraActive = false;
        this.studentData = {};
        this.apiUrl = '/api';
        
        // UI Elements
        this.cameraLoading = document.getElementById('cameraLoading');
        this.captureSection = document.getElementById('captureSection');
        this.loadingSection = document.getElementById('loadingSection');
        this.successSection = document.getElementById('successSection');
        this.errorSection = document.getElementById('errorSection');
        this.manualSection = document.getElementById('manualSection');
        
        // Form elements
        this.nisInput = document.getElementById('nis');
        this.nameInput = document.getElementById('name');
        this.classSelect = document.getElementById('class');
        
        // Error elements
        this.errorTitle = document.getElementById('errorTitle');
        this.errorMessage = document.getElementById('errorMessage');
        
        this.init();
    }
    
    async init() {
        try {
            await this.startCamera();
            this.setupEventListeners();
            this.checkUrlParams();
            this.loadDraftData();
        } catch (error) {
            console.error('Initialization error:', error);
        }
    }
    
    setupEventListeners() {
        // Form validation
        this.nisInput.addEventListener('input', () => this.validateField('nis'));
        this.nameInput.addEventListener('input', () => this.validateField('name'));
        this.classSelect.addEventListener('change', () => this.validateField('class'));
        
        // Auto-save draft
        setInterval(() => this.saveDraft(), 5000);
    }
    
    async startCamera() {
        this.cameraLoading.classList.remove('hidden');
        
        try {
            // Check browser support
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('Browser tidak mendukung akses kamera');
            }
            
            // Get camera stream
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user'
                },
                audio: false
            });
            
            this.video.srcObject = this.stream;
            this.cameraActive = true;
            
            // Wait for video to be ready
            await new Promise((resolve) => {
                this.video.onloadedmetadata = () => {
                    this.video.play();
                    resolve();
                };
            });
            
            // Hide manual section, show capture section if form is valid
            this.manualSection.classList.add('hidden');
            this.checkFormAndShowCapture();
            
            console.log('Camera started successfully');
            
        } catch (error) {
            console.error('Camera error:', error);
            this.cameraActive = false;
            
            // Show manual options
            this.manualSection.classList.remove('hidden');
            
            // Handle specific errors
            if (error.name === 'NotAllowedError') {
                this.showError(
                    'Izin Ditolak',
                    'Akses kamera ditolak. Silakan berikan izin kamera atau gunakan data dummy untuk testing.'
                );
            } else if (error.name === 'NotFoundError') {
                this.showError(
                    'Kamera Tidak Ditemukan',
                    'Tidak ada kamera yang terdeteksi. Gunakan data dummy untuk testing.'
                );
            } else {
                this.showError('Kamera Error', error.message || 'Tidak dapat mengakses kamera');
            }
            
        } finally {
            this.cameraLoading.classList.add('hidden');
        }
    }
    
    validateField(fieldName) {
        const field = this[`${fieldName}Input`];
        const value = field.value.trim();
        let isValid = true;
        let errorMessage = '';
        
        // Remove existing error styling
        field.classList.remove('border-red-500', 'border-green-500');
        
        switch(fieldName) {
            case 'nis':
                if (!value) {
                    isValid = false;
                    errorMessage = 'NIS harus diisi';
                } else if (value.length < 3) {
                    isValid = false;
                    errorMessage = 'NIS minimal 3 karakter';
                } else if (!/^\d+$/.test(value)) {
                    isValid = false;
                    errorMessage = 'NIS harus berupa angka';
                }
                break;
                
            case 'name':
                if (!value) {
                    isValid = false;
                    errorMessage = 'Nama harus diisi';
                } else if (value.length < 3) {
                    isValid = false;
                    errorMessage = 'Nama minimal 3 karakter';
                }
                break;
                
            case 'class':
                if (!value) {
                    isValid = false;
                    errorMessage = 'Kelas harus dipilih';
                }
                break;
        }
        
        // Show validation feedback
        if (value) {
            field.classList.add(isValid ? 'border-green-500' : 'border-red-500');
        }
        
        // Show/hide error message
        const errorEl = document.getElementById(`${fieldName}Error`);
        if (errorEl) {
            if (!isValid && value) {
                errorEl.textContent = errorMessage;
                errorEl.classList.remove('hidden');
            } else {
                errorEl.classList.add('hidden');
            }
        }
        
        return isValid;
    }
    
    validateForm() {
        const isNisValid = this.validateField('nis');
        const isNameValid = this.validateField('name');
        const isClassValid = this.validateField('class');
        
        return isNisValid && isNameValid && isClassValid;
    }
    
    checkFormAndShowCapture() {
        if (this.validateForm() && this.cameraActive) {
            this.captureSection.classList.remove('hidden');
        } else {
            this.captureSection.classList.add('hidden');
        }
    }
    
    prepareRegistration() {
        if (!this.validateForm()) {
            this.showToast('Mohon lengkapi formulir dengan benar', 'error');
            return false;
        }
        
        this.studentData = {
            nis: this.nisInput.value.trim(),
            name: this.nameInput.value.trim(),
            class: this.classSelect.value
        };
        
        return true;
    }
    
    async captureFace() {
        if (!this.prepareRegistration()) return;
        
        // Validate video
        if (!this.video || this.video.readyState !== 4) {
            this.showError('Video Error', 'Video belum siap. Tunggu sebentar lalu coba lagi.');
            return;
        }
        
        try {
            // Capture frame
            this.canvas.width = this.video.videoWidth || 640;
            this.canvas.height = this.video.videoHeight || 480;
            this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
            
            // Get image as base64
            const imageData = this.canvas.toDataURL('image/jpeg', 0.8);
            
            // Check image quality (optional)
            const quality = await this.checkImageQuality(imageData);
            if (quality && !quality.overall_ok) {
                const confirm = window.confirm(
                    'Kualitas gambar kurang baik. Tetap lanjutkan pendaftaran?'
                );
                if (!confirm) return;
            }
            
            // Stop camera
            this.stopCamera();
            
            // Show loading
            this.captureSection.classList.add('hidden');
            this.loadingSection.classList.remove('hidden');
            
            // Register to server
            await this.registerStudent(imageData);
            
        } catch (error) {
            console.error('Capture error:', error);
            this.handleRegistrationError(error);
        }
    }
    
    async registerStudent(imageData) {
        try {
            const response = await fetch(`${this.apiUrl}/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    nis: this.studentData.nis,
                    name: this.studentData.name,
                    class: this.studentData.class,
                    face_image: imageData
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            
            if (result.success) {
                this.handleRegistrationSuccess(result);
            } else {
                throw new Error(result.error || 'Registrasi gagal');
            }
            
        } catch (error) {
            console.error('Registration error:', error);
            
            // Try dummy registration if server is unavailable
            if (error.message.includes('Failed to fetch') || 
                error.message.includes('NetworkError')) {
                
                const useDummy = confirm(
                    'Gagal terhubung ke server. Apakah Anda ingin menggunakan data dummy untuk testing?'
                );
                
                if (useDummy) {
                    this.useDummyRegistration();
                } else {
                    this.handleRegistrationError(error);
                }
            } else {
                this.handleRegistrationError(error);
            }
        }
    }
    
    handleRegistrationSuccess(result) {
        // Clear draft
        this.clearDraft();
        
        // Notify parent window if opened from dashboard
        if (window.opener) {
            window.opener.postMessage({ 
                type: 'studentRegistered',
                data: this.studentData 
            }, '*');
        }
        
        // Save to localStorage
        this.saveToLocalStorage();
        
        // Show success
        this.loadingSection.classList.add('hidden');
        this.successSection.classList.remove('hidden');
        
        // Show success message
        this.showToast('Pendaftaran berhasil!', 'success');
        
        // Play success sound
        this.playSound('success');
    }
    
    handleRegistrationError(error) {
        this.loadingSection.classList.add('hidden');
        this.showError('Pendaftaran Gagal', error.message);
        this.playSound('error');
    }
    
    useDummyRegistration() {
        if (!this.prepareRegistration()) return;
        
        // Stop camera if active
        this.stopCamera();
        
        // Hide all sections
        this.captureSection.classList.add('hidden');
        this.loadingSection.classList.add('hidden');
        this.errorSection.classList.add('hidden');
        this.manualSection.classList.add('hidden');
        
        // Save to localStorage
        this.saveToLocalStorage(true);
        
        // Show success
        this.successSection.classList.remove('hidden');
        
        // Show message
        this.showToast('Pendaftaran dummy berhasil!', 'success');
    }
    
    saveToLocalStorage(isDummy = false) {
        try {
            // Get existing students
            let students = [];
            const saved = localStorage.getItem('registeredStudents');
            if (saved) {
                students = JSON.parse(saved);
            }
            
            // Add new student
            students.push({
                ...this.studentData,
                registration_date: new Date().toISOString(),
                id: Date.now(),
                isDummy: isDummy
            });
            
            // Save
            localStorage.setItem('registeredStudents', JSON.stringify(students));
            
            console.log('Student saved to localStorage');
            
        } catch (error) {
            console.error('Error saving to localStorage:', error);
        }
    }
    
    async checkImageQuality(imageData) {
        try {
            const response = await fetch(`${this.apiUrl}/check_face`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ face_image: imageData })
            });
            
            const result = await response.json();
            return result;
            
        } catch (error) {
            console.error('Error checking image quality:', error);
            return null;
        }
    }
    
    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.cameraActive = false;
        }
    }
    
    showError(title, message) {
        this.errorTitle.textContent = title;
        this.errorMessage.textContent = message;
        this.errorSection.classList.remove('hidden');
        this.captureSection.classList.add('hidden');
        this.loadingSection.classList.add('hidden');
        this.successSection.classList.add('hidden');
    }
    
    retryRegistration() {
        this.errorSection.classList.add('hidden');
        this.captureSection.classList.remove('hidden');
        
        // Restart camera if needed
        if (!this.cameraActive) {
            this.startCamera();
        }
    }
    
    registerAnother() {
        // Reset form
        this.nisInput.value = '';
        this.nameInput.value = '';
        this.classSelect.value = '';
        
        // Hide success section
        this.successSection.classList.add('hidden');
        
        // Clear student data
        this.studentData = {};
        
        // Restart camera
        this.startCamera();
        
        // Clear validation styling
        [this.nisInput, this.nameInput, this.classSelect].forEach(field => {
            field.classList.remove('border-green-500', 'border-red-500');
        });
    }
    
    saveDraft() {
        if (this.nisInput.value || this.nameInput.value || this.classSelect.value) {
            const draft = {
                nis: this.nisInput.value,
                name: this.nameInput.value,
                class: this.classSelect.value,
                timestamp: Date.now()
            };
            localStorage.setItem('registrationDraft', JSON.stringify(draft));
        }
    }
    
    loadDraftData() {
        try {
            const draft = localStorage.getItem('registrationDraft');
            if (draft) {
                const data = JSON.parse(draft);
                // Check if draft is less than 1 hour old
                if (Date.now() - data.timestamp < 3600000) {
                    this.nisInput.value = data.nis || '';
                    this.nameInput.value = data.name || '';
                    if (data.class) {
                        this.classSelect.value = data.class;
                    }
                    
                    // Show restore message
                    this.showToast('Data draft dipulihkan', 'info');
                } else {
                    localStorage.removeItem('registrationDraft');
                }
            }
        } catch (error) {
            console.error('Error loading draft:', error);
        }
    }
    
    clearDraft() {
        localStorage.removeItem('registrationDraft');
    }
    
    checkUrlParams() {
        const urlParams = new URLSearchParams(window.location.search);
        
        // Auto-fill from URL if provided
        if (urlParams.has('nis')) {
            this.nisInput.value = urlParams.get('nis');
        }
        if (urlParams.has('name')) {
            this.nameInput.value = urlParams.get('name');
        }
        if (urlParams.has('class')) {
            this.classSelect.value = urlParams.get('class');
        }
    }
    
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 transform transition-all duration-300 
                          ${type === 'success' ? 'bg-green-100 text-green-800 border-l-4 border-green-500' :
                            type === 'error' ? 'bg-red-100 text-red-800 border-l-4 border-red-500' :
                            type === 'warning' ? 'bg-yellow-100 text-yellow-800 border-l-4 border-yellow-500' :
                            'bg-blue-100 text-blue-800 border-l-4 border-blue-500'}`;
        
        const icon = type === 'success' ? 'fa-check-circle' :
                    type === 'error' ? 'fa-exclamation-circle' :
                    type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle';
        
        toast.innerHTML = `
            <div class="flex items-center">
                <i class="fas ${icon} mr-3 text-xl"></i>
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-gray-500 hover:text-gray-700">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-20px)';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }
    
    playSound(type) {
        // Optional: Add sound effects
        console.log(`Playing ${type} sound`);
    }
    
    cleanup() {
        this.stopCamera();
        this.successSection.classList.add('hidden');
        this.errorSection.classList.add('hidden');
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.registrationManager = new RegistrationManager();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.registrationManager) {
        window.registrationManager.cleanup();
    }
});