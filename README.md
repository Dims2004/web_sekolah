# SMART SCHOOL - Sistem E-Absensi Wajah & Jadwal Pelajaran

Sistem absensi sekolah berbasis pengenalan wajah (Flask + MediaPipe) dengan modul jadwal pelajaran dan dashboard admin.

## Menjalankan dengan Docker (disarankan)

Pastikan Docker dan Docker Compose sudah terpasang, lalu dari folder project ini jalankan:

```bash
docker compose up --build
```

Setelah build selesai, buka:

- Website: http://localhost:5000
- Admin panel: http://localhost:5000/admin.html
- Cek API: http://localhost:5000/api/test

Login admin default: `admin` / `admin123` (ganti `ADMIN_USERNAME` dan `ADMIN_PASSWORD` di `backend/app.py` sebelum dipakai secara nyata).

Database SQLite (`students.db`) disimpan di folder `./database` di komputer host, jadi data tidak akan hilang walaupun container dihapus atau dibangun ulang.

Untuk menghentikan:

```bash
docker compose down
```

## Menjalankan tanpa Docker (manual)

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Lalu buka `http://localhost:5000`.

## Struktur Proyek

```
school-attendance/
├── backend/            # Flask API, deteksi & pengenalan wajah, jadwal
├── frontend/           # Halaman web (HTML, CSS, JS, gambar)
├── database/           # File SQLite (dibuat otomatis)
├── docker-compose.yml
└── backend/Dockerfile
```

## Mengganti Foto dan Logo Sponsor di Halaman Utama

Halaman utama (`frontend/index.html`) memiliki:

1. **Hero slider** di bagian atas (3 slide ilustrasi) — bisa diganti dengan foto asli dengan mengubah bagian `style="background:..."` pada tiap `.hero-slide` menjadi `background-image:url('images/nama-file.jpg')`.
2. **Galeri sekolah** (`#tentang`) — 4 slide placeholder ikon, ganti dengan `<img src="images/foto1.jpg">` setelah menaruh foto sekolah di folder `frontend/images/`.
3. **Marquee sponsor** — daftar `sponsors` di bagian `<script>` paling bawah `index.html`, ganti ikon dan nama dengan logo sponsor asli (bisa memakai `<img>` alih-alih ikon FontAwesome).

## Catatan

- Semua endpoint API sekarang memakai path relatif (`/api/...`) sehingga otomatis mengikuti origin tempat web ini dihosting, baik lewat Docker maupun lewat `python app.py` langsung.
- `mediapipe` dan `opencv-python-headless` cukup berat untuk diunduh saat build image pertama kali; proses `docker compose up --build` bisa memakan waktu beberapa menit tergantung koneksi internet.
