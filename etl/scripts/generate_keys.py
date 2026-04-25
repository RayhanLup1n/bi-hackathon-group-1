#!/usr/bin/env python3
"""
Helper: generate Fernet key dan Secret key untuk Airflow.
Jalankan sekali saat setup awal, lalu copy hasilnya ke file .env
"""
from cryptography.fernet import Fernet
import secrets

fernet_key = Fernet.generate_key().decode()
secret_key = secrets.token_hex(32)

print("=" * 60)
print("Copy nilai berikut ke file .env Anda:")
print("=" * 60)
print(f"AIRFLOW__CORE__FERNET_KEY={fernet_key}")
print(f"AIRFLOW__WEBSERVER__SECRET_KEY={secret_key}")
print("=" * 60)
