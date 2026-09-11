"""
Lapisan kompatibilitas database.

Kenapa file ini ada:
- Kode lama (app.py, schedule_routes.py, schedule_model.py) ditulis untuk SQLite,
  pakai placeholder "?" dan mengandalkan `cursor.lastrowid`.
- SQLite cocok untuk development lokal, tapi bermasalah untuk hosting produksi:
  cuma boleh ditulis oleh satu proses/thread pada satu waktu, gampang "database
  is locked" begitu ada 2 worker gunicorn, dan filenya hilang setiap kali
  container di-redeploy kalau tidak di-mount sebagai volume persisten.
- PostgreSQL adalah database yang tepat untuk hosting: mendukung banyak koneksi
  bersamaan, punya banyak pilihan hosting gratis (Supabase, Neon, Railway,
  Render) yang datanya persisten dan terpisah dari container aplikasi.

Modul ini membiarkan seluruh query yang sudah ada (gaya SQLite, placeholder "?")
tetap jalan tanpa diubah satu per satu. Set environment variable DATABASE_URL
untuk pindah ke PostgreSQL; kalau tidak diset, aplikasi tetap jalan pakai SQLite
seperti sebelumnya (cocok untuk development di laptop).
"""

import os
import re
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
IS_POSTGRES = DATABASE_URL.startswith('postgres')

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras

# Dipakai hanya kalau DATABASE_URL tidak diset (development lokal / fallback).
DATABASE_DIR = os.path.join(BASE_DIR, '..', 'database')
DATABASE_PATH = os.path.join(DATABASE_DIR, 'students.db')

if not IS_POSTGRES and not os.path.exists(DATABASE_DIR):
    os.makedirs(DATABASE_DIR)

_PLACEHOLDER_RE = re.compile(r'\?')
_INSERT_RE = re.compile(r'^\s*INSERT\b', re.IGNORECASE)


class _CompatCursor:
    """Bungkus cursor asli supaya query lama (placeholder "?", .lastrowid)
    tetap jalan sama persis di PostgreSQL maupun SQLite."""

    def __init__(self, raw_cursor, is_postgres):
        self._cursor = raw_cursor
        self._is_postgres = is_postgres
        self.lastrowid = None

    def execute(self, query, params=()):
        params = params or ()
        if not self._is_postgres:
            self._cursor.execute(query, params)
            self.lastrowid = self._cursor.lastrowid
            return self

        pg_query = _PLACEHOLDER_RE.sub('%s', query)

        # SQLite otomatis punya cursor.lastrowid setelah INSERT. Postgres tidak
        # punya konsep itu, jadi untuk setiap INSERT yang belum punya klausa
        # RETURNING, kita tambahkan "RETURNING id" (semua tabel di app ini
        # memakai "id" sebagai primary key) dan ambil hasilnya sebagai lastrowid.
        if _INSERT_RE.match(pg_query) and 'RETURNING' not in pg_query.upper():
            pg_query = pg_query.rstrip().rstrip(';') + ' RETURNING id'
            self._cursor.execute(pg_query, params)
            row = self._cursor.fetchone()
            self.lastrowid = row[0] if row else None
            return self

        self._cursor.execute(pg_query, params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        return self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)


class _CompatConnection:
    def __init__(self, raw_conn, is_postgres):
        self._conn = raw_conn
        self._is_postgres = is_postgres

    def cursor(self):
        return _CompatCursor(self._conn.cursor(), self._is_postgres)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db_connection(sqlite_path=None):
    """Ganti langsung untuk setiap `sqlite3.connect(...)` yang lama ada di kode.

    Kalau DATABASE_URL diset -> connect ke PostgreSQL.
    Kalau tidak -> connect ke file SQLite seperti sebelumnya (sqlite_path kalau
    diberikan, atau DATABASE_PATH default).
    """
    if IS_POSTGRES:
        raw = psycopg2.connect(DATABASE_URL)
        return _CompatConnection(raw, True)

    raw = sqlite3.connect(sqlite_path or DATABASE_PATH)
    return _CompatConnection(raw, False)


def to_binary(data):
    """Bungkus data bytes (mis. embedding wajah yang di-pickle) supaya aman
    disimpan ke kolom BYTEA di PostgreSQL. Di SQLite, bytes mentah sudah
    langsung diterima kolom BLOB, jadi cukup dikembalikan apa adanya."""
    if IS_POSTGRES and data is not None:
        return psycopg2.Binary(data)
    return data


def year_expr(column):
    """Ekspresi SQL untuk mengambil bagian tahun (YYYY) dari kolom timestamp
    yang disimpan sebagai teks 'YYYY-MM-DD HH:MM:SS'. Beda fungsi antara
    SQLite (strftime) dan PostgreSQL (to_char)."""
    if IS_POSTGRES:
        return f"to_char({column}::timestamp, 'YYYY')"
    return f"strftime('%Y', {column})"
