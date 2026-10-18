"""Uygulama genelinde kullanılan yollar ve ortam değişkenleri.

Gizli bilgiler (SMTP şifresi, Telegram token vb.) isteğe bağlı olarak `.env`
dosyasından veya ortam değişkenlerinden okunabilir. Ortam değişkeni varsa
veritabanındaki ayarın önüne geçer.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("KULUCKA_VERI_DIZINI", BASE_DIR / "data"))
TEMPLATE_DIR = BASE_DIR / "templates"
CUSTOM_TEMPLATE_DIR = DATA_DIR / "sablonlar"          # kurumun yüklediği şablonlar
SARTNAME_DIR = DATA_DIR / "sartnameler"
PROJECT_DIR = DATA_DIR / "projeler"                   # yerel proje klasörleri
BACKUP_DIR = DATA_DIR / "yedekler"
SECRETS_DIR = DATA_DIR / "gizli"                      # Google kimlik dosyaları

APP_VERSION = "1.0.0"
APP_NAME = "Akıllı Proje Kuluçka ve Otomasyon Sistemi"


def _load_dotenv() -> None:
    """Basit .env okuyucu (python-dotenv bağımlılığı olmadan)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    ham = env_path.read_bytes()
    try:
        metin = ham.decode("utf-8-sig")  # Windows Not Defteri BOM ekleyebilir
    except UnicodeDecodeError:
        metin = ham.decode("cp1254", errors="replace")  # ANSI (Türkçe Windows) ile kaydedilmiş dosya
    for line in metin.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'myo_otomasyon.db').as_posix()}"
)

# "gomulu": zamanlayıcı Streamlit süreci içinde çalışır (tek komutla kurulum)
# "harici": zamanlayıcı ayrı `python worker.py` süreciyle çalışır (sunucu kurulumu)
SCHEDULER_MODE = os.environ.get("KULUCKA_ZAMANLAYICI", "gomulu").lower()


def ensure_dirs() -> None:
    for d in (DATA_DIR, CUSTOM_TEMPLATE_DIR, SARTNAME_DIR, PROJECT_DIR, BACKUP_DIR, SECRETS_DIR):
        d.mkdir(parents=True, exist_ok=True)


ensure_dirs()
