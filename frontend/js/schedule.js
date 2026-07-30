// schedule.js - Main logic for schedule page

class ScheduleManager {
    constructor() {
        this.currentFilter = 'all';
        this.currentClass = '';
        this.apiUrl = '/api';
        this.scheduleData = null;
        this.allClasses = [];
        
        // Initialize when DOM is ready
        this.init();
    }
    
    async init() {
        console.log('ScheduleManager initializing...');
        
        // Load the full list of classes first (includes classes with no schedule yet)
        await this.loadClassList();

        // Load schedule data from API
        await this.loadScheduleFromAPI();
        
        // Setup UI
        this.setupEventListeners();
        this.updateDateTime();
        this.loadSchedule();
        this.updateStats();
        
        // Start time update interval
        setInterval(() => this.updateDateTime(), 1000);
    }

    // Ambil semua nama kelas yang terdaftar (termasuk yang belum ada jadwalnya)
    async loadClassList() {
        try {
            const response = await fetch(`${this.apiUrl}/schedule/classes`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && Array.isArray(data.classes)) {
                    this.allClasses = data.classes;
                }
            }
        } catch (error) {
            console.error('Error loading class list:', error);
        }
    }
    
    async loadScheduleFromAPI() {
        try {
            // Show loading state
            const container = document.getElementById('scheduleContainer');
            if (container) {
                container.innerHTML = `
                    <div class="text-center py-12">
                        <div class="loading-spinner mx-auto mb-4"></div>
                        <p class="text-gray-500">Memuat jadwal dari server...</p>
                    </div>
                `;
            }
            
            // Try to load from API first - perbaiki endpoint
            const response = await fetch(`${this.apiUrl}/schedule/list`);
            
            if (response.ok) {
                const data = await response.json();
                console.log('API Response:', data);
                
                if (data.success && data.schedule) {
                    // Terima data apa adanya dari server, walaupun kosong ({})
                    // supaya tidak diam-diam diganti data dummy saat memang belum ada jadwal.
                    this.scheduleData = data.schedule;
                    console.log('Loaded schedule from API:', this.scheduleData);
                    this.updateClassFilter();
                    return;
                }
            }
            
            // Hanya jatuh ke localStorage/dummy kalau API benar-benar tidak bisa dihubungi
            const savedData = localStorage.getItem('scheduleData');
            if (savedData) {
                this.scheduleData = JSON.parse(savedData);
                console.log('Loaded schedule from localStorage');
            } else {
                // Fallback to dummy data
                this.scheduleData = this.getDummyData();
                console.log('Using dummy schedule data');
                
                // Save dummy data to localStorage as backup
                localStorage.setItem('scheduleData', JSON.stringify(this.scheduleData));
            }
            this.updateClassFilter();
            
        } catch (error) {
            console.error('Error loading from API:', error);
            
            // Try localStorage if API fails
            const savedData = localStorage.getItem('scheduleData');
            if (savedData) {
                this.scheduleData = JSON.parse(savedData);
                console.log('Loaded schedule from localStorage after API failure');
            } else {
                // Fallback to dummy data
                this.scheduleData = this.getDummyData();
                console.log('Using dummy schedule data');
                localStorage.setItem('scheduleData', JSON.stringify(this.scheduleData));
            }
            this.updateClassFilter();
        }
    }
    
    // Method untuk update class filter, gabungan dari daftar kelas resmi
    // (termasuk yang belum ada jadwalnya) + kelas yang muncul di data jadwal
    updateClassFilter() {
        const classFilter = document.getElementById('classFilter');
        if (!classFilter) return;

        const classesFromSchedule = this.scheduleData ? Object.keys(this.scheduleData) : [];
        const combined = Array.from(new Set([...this.allClasses, ...classesFromSchedule])).sort();

        classFilter.innerHTML = '';

        if (combined.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'Belum ada kelas';
            classFilter.appendChild(option);
            return;
        }

        combined.forEach(className => {
            const option = document.createElement('option');
            option.value = className;
            option.textContent = className;
            classFilter.appendChild(option);
        });

        // Pertahankan kelas yang sedang dipilih kalau masih ada, kalau tidak pilih yang pertama
        if (!this.currentClass || !combined.includes(this.currentClass)) {
            this.currentClass = combined[0];
        }
        classFilter.value = this.currentClass;
    }
    
    // Method untuk refresh data dari API
    async refreshData() {
        try {
            await this.loadClassList();
            const response = await fetch(`${this.apiUrl}/schedule/list`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.schedule) {
                    this.scheduleData = data.schedule;
                    
                    // Save to localStorage
                    localStorage.setItem('scheduleData', JSON.stringify(this.scheduleData));
                    
                    // Update UI
                    this.updateClassFilter();
                    this.loadSchedule();
                    this.updateStats();
                    
                    this.showNotification('Data jadwal berhasil diperbarui', 'success');
                }
            } else {
                this.showNotification('Gagal memperbarui data', 'error');
            }
        } catch (error) {
            console.error('Error refreshing data:', error);
            this.showNotification('Gagal terhubung ke server', 'error');
        }
    }
    
    // Method untuk menambah jadwal baru (akan dipanggil dari admin panel)
    async addNewSchedule(scheduleData) {
        try {
            const response = await fetch(`${this.apiUrl}/schedule/add`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('adminToken')
                },
                body: JSON.stringify(scheduleData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Refresh data setelah menambah
                await this.refreshData();
                return { success: true, message: 'Jadwal berhasil ditambahkan' };
            } else {
                return { success: false, message: result.error || 'Gagal menambah jadwal' };
            }
        } catch (error) {
            console.error('Error adding schedule:', error);
            return { success: false, message: 'Gagal terhubung ke server' };
        }
    }
    
    // Method untuk menghapus jadwal
    async deleteSchedule(scheduleId) {
        try {
            const response = await fetch(`${this.apiUrl}/schedule/delete/${scheduleId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': 'Bearer ' + localStorage.getItem('adminToken')
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                await this.refreshData();
                return { success: true, message: 'Jadwal berhasil dihapus' };
            } else {
                return { success: false, message: result.error || 'Gagal menghapus jadwal' };
            }
        } catch (error) {
            console.error('Error deleting schedule:', error);
            return { success: false, message: 'Gagal terhubung ke server' };
        }
    }
    
    getDummyData() {
        return {
            '10 IPA 1': {
                senin: [
                    { time: '07:00 - 08:30', subject: 'Matematika', teacher: 'Bu Siti', room: 'R.101', color: 'blue' },
                    { time: '08:30 - 10:00', subject: 'Bahasa Indonesia', teacher: 'Pak Budi', room: 'R.102', color: 'green' },
                    { time: '10:15 - 11:45', subject: 'Bahasa Inggris', teacher: 'Bu Ani', room: 'R.103', color: 'purple' },
                    { time: '12:30 - 14:00', subject: 'Fisika', teacher: 'Pak Joko', room: 'Lab Fisika', color: 'yellow' }
                ],
                selasa: [
                    { time: '07:00 - 08:30', subject: 'Kimia', teacher: 'Bu Rina', room: 'Lab Kimia', color: 'red' },
                    { time: '08:30 - 10:00', subject: 'Biologi', teacher: 'Pak Ahmad', room: 'Lab Biologi', color: 'teal' },
                    { time: '10:15 - 11:45', subject: 'Matematika', teacher: 'Bu Siti', room: 'R.101', color: 'blue' },
                    { time: '12:30 - 14:00', subject: 'Olahraga', teacher: 'Pak Yoga', room: 'Lapangan', color: 'indigo' }
                ],
                rabu: [
                    { time: '07:00 - 08:30', subject: 'Sejarah', teacher: 'Bu Dewi', room: 'R.104', color: 'pink' },
                    { time: '08:30 - 10:00', subject: 'Geografi', teacher: 'Pak Eko', room: 'R.105', color: 'orange' },
                    { time: '10:15 - 11:45', subject: 'Ekonomi', teacher: 'Bu Fitri', room: 'R.106', color: 'cyan' },
                    { time: '12:30 - 14:00', subject: 'Sosiologi', teacher: 'Pak Hendra', room: 'R.107', color: 'lime' }
                ],
                kamis: [
                    { time: '07:00 - 08:30', subject: 'Agama', teacher: 'Bu Hj. Aminah', room: 'Musholla', color: 'teal' },
                    { time: '08:30 - 10:00', subject: 'PKN', teacher: 'Pak Gatot', room: 'R.108', color: 'brown' },
                    { time: '10:15 - 11:45', subject: 'Seni Budaya', teacher: 'Bu Indah', room: 'Studio', color: 'pink' },
                    { time: '12:30 - 14:00', subject: 'Prakarya', teacher: 'Pak Kurnia', room: 'Bengkel', color: 'amber' }
                ],
                jumat: [
                    { time: '07:00 - 08:30', subject: 'Matematika', teacher: 'Bu Siti', room: 'R.101', color: 'blue' },
                    { time: '08:30 - 09:45', subject: 'Bahasa Inggris', teacher: 'Bu Ani', room: 'R.103', color: 'purple' },
                    { time: '10:00 - 11:15', subject: 'BK', teacher: 'Bu Lestari', room: 'R.109', color: 'gray' }
                ],
                sabtu: [
                    { time: '07:00 - 08:30', subject: 'Ekstrakurikuler', teacher: 'Pembina', room: 'Lapangan', color: 'orange' },
                    { time: '08:30 - 10:00', subject: 'Ekstrakurikuler', teacher: 'Pembina', room: 'Aula', color: 'orange' }
                ]
            },
            '11 IPA 1': {
                senin: [
                    { time: '07:00 - 08:30', subject: 'Matematika Lanjut', teacher: 'Pak Dedi', room: 'R.201', color: 'blue' },
                    { time: '08:30 - 10:00', subject: 'Fisika', teacher: 'Bu Maya', room: 'Lab Fisika', color: 'yellow' },
                    { time: '10:15 - 11:45', subject: 'Kimia', teacher: 'Bu Rina', room: 'Lab Kimia', color: 'red' },
                    { time: '12:30 - 14:00', subject: 'Biologi', teacher: 'Pak Ahmad', room: 'Lab Biologi', color: 'teal' }
                ],
                selasa: [
                    { time: '07:00 - 08:30', subject: 'Bahasa Indonesia', teacher: 'Pak Budi', room: 'R.202', color: 'green' },
                    { time: '08:30 - 10:00', subject: 'Bahasa Inggris', teacher: 'Bu Ani', room: 'R.203', color: 'purple' },
                    { time: '10:15 - 11:45', subject: 'Matematika', teacher: 'Pak Dedi', room: 'R.201', color: 'blue' }
                ],
                rabu: [
                    { time: '07:00 - 08:30', subject: 'Sejarah', teacher: 'Bu Dewi', room: 'R.204', color: 'pink' },
                    { time: '08:30 - 10:00', subject: 'Geografi', teacher: 'Pak Eko', room: 'R.205', color: 'orange' },
                    { time: '10:15 - 11:45', subject: 'Ekonomi', teacher: 'Bu Fitri', room: 'R.206', color: 'cyan' }
                ]
            },
            '12 IPA 1': {
                senin: [
                    { time: '07:00 - 08:30', subject: 'Matematika', teacher: 'Bu Siti', room: 'R.301', color: 'blue' },
                    { time: '08:30 - 10:00', subject: 'Fisika', teacher: 'Pak Joko', room: 'Lab Fisika', color: 'yellow' },
                    { time: '10:15 - 11:45', subject: 'Kimia', teacher: 'Bu Rina', room: 'Lab Kimia', color: 'red' }
                ],
                selasa: [
                    { time: '07:00 - 08:30', subject: 'Biologi', teacher: 'Pak Ahmad', room: 'Lab Biologi', color: 'teal' },
                    { time: '08:30 - 10:00', subject: 'Bahasa Inggris', teacher: 'Bu Ani', room: 'R.302', color: 'purple' }
                ]
            }
        };
    }
    
    setupEventListeners() {
        // Class filter change
        const classFilter = document.getElementById('classFilter');
        if (classFilter) {
            classFilter.addEventListener('change', (e) => {
                this.currentClass = e.target.value;
                this.loadSchedule();
                this.updateStats();
            });
        }
        
        // Search functionality
        const searchInput = document.getElementById('searchSchedule');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchSchedule(e.target.value);
            });
        }
        
        // Refresh button (if exists)
        const refreshBtn = document.getElementById('refreshSchedule');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.refreshData();
            });
        }
    }
    
    updateDateTime() {
        const now = new Date();
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        const dateElement = document.getElementById('currentDate');
        if (dateElement) {
            dateElement.textContent = now.toLocaleDateString('id-ID', options);
        }
    }
    
    updateStats() {
        if (!this.scheduleData) return;
        
        const subjects = new Set();
        const teachers = new Set();
        let totalHours = 0;

        Object.values(this.scheduleData).forEach(classSchedule => {
            Object.values(classSchedule).forEach(daySchedule => {
                daySchedule.forEach(item => {
                    subjects.add(item.subject);
                    teachers.add(item.teacher);
                    totalHours += 1.5;
                });
            });
        });

        // Update DOM elements
        const totalSubjectsEl = document.getElementById('totalSubjects');
        const totalTeachersEl = document.getElementById('totalTeachers');
        const todayClassesEl = document.getElementById('todayClasses');
        const totalHoursEl = document.getElementById('totalHours');
        
        if (totalSubjectsEl) totalSubjectsEl.textContent = subjects.size;
        if (totalTeachersEl) totalTeachersEl.textContent = teachers.size;
        
        const today = this.getTodayDay();
        const todayClasses = this.scheduleData[this.currentClass]?.[today]?.length || 0;
        if (todayClassesEl) todayClassesEl.textContent = todayClasses;
        if (totalHoursEl) totalHoursEl.textContent = totalHours;
    }
    
    getTodayDay() {
        const days = ['minggu', 'senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu'];
        return days[new Date().getDay()];
    }
    
    loadSchedule() {
        const container = document.getElementById('scheduleContainer');
        if (!container || !this.scheduleData) return;
        
        const classSchedule = this.scheduleData[this.currentClass];
        
        if (!classSchedule) {
            container.innerHTML = this.getEmptyStateHTML('Belum ada jadwal untuk kelas ini. Silakan hubungi admin untuk menambah jadwal.');
            return;
        }

        let html = '';
        const days = ['senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu'];
        let hasContent = false;
        
        days.forEach(day => {
            const daySchedule = classSchedule[day] || [];
            
            if (this.currentFilter !== 'all' && this.currentFilter !== day) {
                return;
            }
            
            if (daySchedule.length > 0) {
                hasContent = true;
                html += this.getDaySectionHTML(day, daySchedule);
            }
        });
        
        if (!hasContent) {
            container.innerHTML = this.getEmptyStateHTML('Tidak ada jadwal untuk filter yang dipilih');
        } else {
            container.innerHTML = html;
        }
    }
    
    getDaySectionHTML(day, daySchedule) {
        return `
            <div class="bg-white rounded-xl shadow overflow-hidden">
                <div class="bg-gradient-to-r from-purple-600 to-indigo-600 px-6 py-4">
                    <h3 class="text-xl font-bold text-white capitalize flex items-center">
                        <i class="fas fa-calendar-day mr-3"></i>
                        ${day}
                    </h3>
                </div>
                <div class="p-6">
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        ${daySchedule.map(item => this.getScheduleCardHTML(item)).join('')}
                    </div>
                </div>
            </div>
        `;
    }
    
    getScheduleCardHTML(item) {
        const colorClasses = {
            blue: 'border-blue-200 bg-blue-50',
            green: 'border-green-200 bg-green-50',
            purple: 'border-purple-200 bg-purple-50',
            yellow: 'border-yellow-200 bg-yellow-50',
            red: 'border-red-200 bg-red-50',
            teal: 'border-teal-200 bg-teal-50',
            pink: 'border-pink-200 bg-pink-50',
            indigo: 'border-indigo-200 bg-indigo-50',
            orange: 'border-orange-200 bg-orange-50',
            cyan: 'border-cyan-200 bg-cyan-50',
            lime: 'border-lime-200 bg-lime-50',
            brown: 'border-brown-200 bg-brown-50',
            amber: 'border-amber-200 bg-amber-50',
            gray: 'border-gray-200 bg-gray-50'
        };
        
        return `
            <div class="schedule-card border-2 ${colorClasses[item.color] || 'border-gray-200 bg-gray-50'} rounded-xl p-4">
                <div class="flex justify-between items-start mb-3">
                    <span class="time-badge">${item.time}</span>
                    <span class="room-badge">
                        <i class="fas fa-map-marker-alt mr-1"></i>${item.room}
                    </span>
                </div>
                <h4 class="font-bold text-gray-800 mb-2 text-lg">${item.subject}</h4>
                <div class="teacher-info">
                    <div class="teacher-avatar">
                        <i class="fas fa-chalkboard-teacher text-xs"></i>
                    </div>
                    <span class="text-sm text-gray-600">${item.teacher}</span>
                </div>
            </div>
        `;
    }
    
    getEmptyStateHTML(message = 'Belum ada jadwal untuk kelas ini') {
        return `
            <div class="text-center py-12 bg-white rounded-xl shadow">
                <i class="fas fa-calendar-times text-4xl text-gray-400 mb-4"></i>
                <p class="text-gray-500">${message}</p>
                <button onclick="scheduleManager.refreshData()" class="mt-4 bg-purple-600 hover:bg-purple-700 text-white px-6 py-2 rounded-lg">
                    <i class="fas fa-sync-alt mr-2"></i>Refresh Data
                </button>
            </div>
        `;
    }
    
    filterDay(day) {
        this.currentFilter = day;
        this.setActiveTab(day);
        this.loadSchedule();
    }
    
    setActiveTab(day) {
        const tabs = ['all', 'senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu'];
        tabs.forEach(tab => {
            const element = document.getElementById(`tab-${tab}`);
            if (element) {
                if (tab === day) {
                    element.classList.remove('bg-gray-100', 'text-gray-700');
                    element.classList.add('bg-purple-600', 'text-white');
                } else {
                    element.classList.remove('bg-purple-600', 'text-white');
                    element.classList.add('bg-gray-100', 'text-gray-700');
                }
            }
        });
    }
    
    searchSchedule(query) {
        if (!query.trim()) {
            this.loadSchedule();
            return;
        }
        
        const container = document.getElementById('scheduleContainer');
        const classSchedule = this.scheduleData[this.currentClass];
        if (!classSchedule) return;
        
        const results = [];
        const days = ['senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu'];
        
        days.forEach(day => {
            const daySchedule = classSchedule[day] || [];
            daySchedule.forEach(item => {
                if (item.subject.toLowerCase().includes(query.toLowerCase()) ||
                    item.teacher.toLowerCase().includes(query.toLowerCase())) {
                    results.push({ ...item, day });
                }
            });
        });
        
        if (results.length === 0) {
            container.innerHTML = this.getEmptyStateHTML('Tidak ada hasil pencarian');
            return;
        }
        
        let html = '';
        const groupedByDay = {};
        results.forEach(item => {
            if (!groupedByDay[item.day]) groupedByDay[item.day] = [];
            groupedByDay[item.day].push(item);
        });
        
        Object.keys(groupedByDay).forEach(day => {
            html += this.getDaySectionHTML(day, groupedByDay[day]);
        });
        
        container.innerHTML = html;
    }
    
    async printSchedule(type) {
        const className = this.currentClass;
        const classSchedule = this.scheduleData[className];
        
        if (!classSchedule) {
            alert('Tidak ada jadwal untuk kelas ini');
            return;
        }
        
        const printContent = this.generatePrintContent(type, className, classSchedule);
        const printWindow = window.open('', '_blank');
        printWindow.document.write(printContent);
        printWindow.document.close();
        setTimeout(() => printWindow.print(), 500);
    }
    
    generatePrintContent(type, className, classSchedule) {
        const today = this.getTodayDay();
        const days = type === 'today' ? [today] : ['senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu'];
        
        let content = `
            <!DOCTYPE html>
            <html>
            <head>
                <title>Jadwal Pelajaran - ${className}</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; }
                    .print-header { text-align: center; margin-bottom: 30px; }
                    .print-day { margin-bottom: 30px; }
                    .print-day h2 { color: #8b5cf6; border-bottom: 2px solid #8b5cf6; padding-bottom: 10px; }
                    .print-table { width: 100%; border-collapse: collapse; }
                    .print-table th { background: #f3f4f6; padding: 10px; text-align: left; }
                    .print-table td { padding: 10px; border-bottom: 1px solid #e5e7eb; }
                    .print-footer { margin-top: 40px; text-align: center; color: #6b7280; font-size: 12px; }
                </style>
            </head>
            <body>
                <div class="print-header">
                    <h1>🎓 SMART SCHOOL</h1>
                    <h2>Jadwal Pelajaran</h2>
                    <p>Kelas: ${className}</p>
                    <p>Semester Genap 2024/2025</p>
                </div>
        `;
        
        days.forEach(day => {
            const daySchedule = classSchedule[day] || [];
            if (daySchedule.length > 0) {
                content += `
                    <div class="print-day">
                        <h2 class="capitalize">${day}</h2>
                        <table class="print-table">
                            <thead>
                                <tr>
                                    <th>Waktu</th>
                                    <th>Mata Pelajaran</th>
                                    <th>Guru</th>
                                    <th>Ruangan</th>
                                </tr>
                            </thead>
                            <tbody>
                `;
                
                daySchedule.forEach(item => {
                    content += `
                        <tr>
                            <td>${item.time}</td>
                            <td>${item.subject}</td>
                            <td>${item.teacher}</td>
                            <td>${item.room}</td>
                        </tr>
                    `;
                });
                
                content += `
                            </tbody>
                        </table>
                    </div>
                `;
            }
        });
        
        content += `
                <div class="print-footer">
                    <p>Dicetak pada: ${new Date().toLocaleString('id-ID')}</p>
                    <p>© 2026 SMART SCHOOL - Sistem Informasi Akademik</p>
                </div>
            </body>
            </html>
        `;
        
        return content;
    }
    
    async exportToCSV() {
        const className = this.currentClass;
        const classSchedule = this.scheduleData[className];
        
        if (!classSchedule) {
            alert('Tidak ada jadwal untuk kelas ini');
            return;
        }
        
        let csvContent = "Hari,Waktu,Mata Pelajaran,Guru,Ruangan\n";
        const days = ['senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu'];
        
        days.forEach(day => {
            const daySchedule = classSchedule[day] || [];
            daySchedule.forEach(item => {
                // Escape commas in text
                const subject = item.subject.replace(/,/g, ' ');
                const teacher = item.teacher.replace(/,/g, ' ');
                const room = item.room.replace(/,/g, ' ');
                csvContent += `${day},${item.time},${subject},${teacher},${room}\n`;
            });
        });
        
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `jadwal_${className}_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }
    
    addSchedule() {
        // Redirect ke halaman admin schedule jika user adalah admin
        const adminToken = localStorage.getItem('adminToken');
        if (adminToken) {
            window.open('admin-schedule.html', '_blank');
        } else {
            alert('Fitur ini hanya untuk admin. Silakan login sebagai admin terlebih dahulu.');
            window.location.href = 'admin.html';
        }
    }
    
    // Helper method untuk menampilkan notifikasi
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 transform transition-all duration-300 
            ${type === 'success' ? 'bg-green-100 text-green-800 border-l-4 border-green-500' :
              type === 'error' ? 'bg-red-100 text-red-800 border-l-4 border-red-500' :
              'bg-blue-100 text-blue-800 border-l-4 border-blue-500'}`;
        
        const icon = type === 'success' ? 'fa-check-circle' :
                    type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle';
        
        notification.innerHTML = `
            <div class="flex items-center">
                <i class="fas ${icon} mr-3 text-xl"></i>
                <span>${message}</span>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transform = 'translateY(-20px)';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
}

// Initialize when page loads
let scheduleManager;
document.addEventListener('DOMContentLoaded', () => {
    scheduleManager = new ScheduleManager();
    window.scheduleManager = scheduleManager; // Make global for onclick handlers
});