"""Kuruma özel ayarlar.

Ayarlar `ayarlar` tablosunda JSON olarak saklanır ve Yönetim Paneli'nden
değiştirilebilir. Aynı isimde bir ortam değişkeni (büyük harfle, ör.
SMTP_SIFRE) tanımlanmışsa veritabanındaki değerin önüne geçer; böylece
şifreler veritabanına yazılmadan da kullanılabilir.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .database import Ayar, get_session

VARSAYILAN_YETKINLIKLER = [
    "SolidWorks", "AutoCAD", "Fusion 360", "CATIA", "Teknik Resim", "3D Yazıcı / Hızlı Prototipleme",
    "CNC Programlama", "Kaynak Teknolojisi", "Malzeme Bilgisi", "Pnömatik / Hidrolik",
    "PLC (Siemens TIA Portal)", "SCADA / HMI", "Endüstriyel Otomasyon", "Mekatronik", "Robotik (ROS)",
    "Python", "C / C++", "Java", "Web Geliştirme", "Mobil Uygulama", "Veritabanı / SQL",
    "Yapay Zeka / Makine Öğrenmesi", "Görüntü İşleme (OpenCV)", "Veri Analizi",
    "Arduino", "Raspberry Pi", "Gömülü Sistemler (STM32/ESP32)", "IoT", "Elektronik Devre Tasarımı",
    "PCB Tasarımı (KiCad/Altium)", "Motor Sürücü / Güç Elektroniği", "Batarya / BMS",
    "Elektrik Tesisatı", "Yenilenebilir Enerji / Güneş", "MATLAB / Simulink",
    "İklimlendirme / Soğutma", "Otomotiv / Elektrikli Araç", "İnsansız Hava Aracı (İHA)",
    "Haberleşme / RF", "Ağ Teknolojileri", "Siber Güvenlik", "Biyomedikal Cihaz",
    "Gıda Teknolojisi", "Tarım Teknolojileri", "Kalite Kontrol", "İş Sağlığı ve Güvenliği",
    "Proje Yönetimi", "Rapor Yazımı / Sunum", "Grafik Tasarım", "Video / Görsel İçerik",
]

VARSAYILAN_REHBER = """### TÜBİTAK 2209-A / 2209-B başvuru adımları

1. **ARBİS kaydı (öğrenci ve danışman):** https://arbis.tubitak.gov.tr adresinden kayıt olun veya
   bilgilerinizi güncelleyin. Proje yürütücüsü, tüm proje ortakları ve danışmanın ARBİS kaydı güncel olmalıdır.
2. **Danışmanın YÖKSİS kaydı:** Akademik danışmanın YÖK kaydı güncel olmalıdır.
3. **TYBS başvurusu:** Başvuru https://tybs.tubitak.gov.tr üzerinden proje yürütücüsü öğrenci tarafından yapılır.
   Araştırma önerisi, TYBS ekranlarına girilen bilgilerden otomatik oluşturulur; ayrıca Word dosyası yüklenmez.
   Size gönderilen **TYBS Hazırlık Taslağı**ndaki bölümleri ekip olarak doldurup ilgili ekranlara aktarın.
4. **Danışman onayı:** Başvuru gönderildikten sonra danışman TYBS üzerinden onay verir.
5. **Kurum yetkilisi e-imzası:** Kurum onayı https://eimza.tubitak.gov.tr üzerinden verilir.
6. **Sonuç ve belgeler:** Sonuçlar ve etik kurul belgeleri https://e-bideb.tubitak.gov.tr üzerinden takip edilir.

> Açık öğretim ve hazırlık sınıfı öğrencileri yürütücü veya ortak olamaz. Bir projede yürütücü dışında
> en fazla 4 ortak bulunabilir. Aynı dönemde birden fazla başvuru yapılamaz.

### TEKNOFEST başvuru adımları

1. Yarışmanın sayfasındaki şartnameyi ekipçe okuyun (sistem şartnameyi proje klasörünüze indirir).
2. Takım kaptanı, yarışma sayfasındaki **Başvur** bağlantısından takım başvurusunu oluşturur, üyeler ve
   danışman sisteme davet edilir.
3. Ön Değerlendirme / Proje Detay Raporu, yarışmanın resmi rapor şablonuna aktarılarak süresi içinde yüklenir.
"""

DEFAULTS: dict[str, Any] = {
    # Kurum
    "kurum_adi": "Teknik Bilimler Meslek Yüksekokulu",
    "universite_adi": "",
    "uygulama_url": "http://localhost:8501",
    "bolumler": [
        "Bilgisayar Programcılığı", "Elektrik", "Elektronik Teknolojisi", "Makine", "Mekatronik",
        "Otomotiv Teknolojisi", "İklimlendirme ve Soğutma Teknolojisi", "Kontrol ve Otomasyon Teknolojisi",
        "Elektrikli Cihaz Teknolojisi", "Biyomedikal Cihaz Teknolojisi", "Diğer",
    ],
    "yetkinlik_katalogu": VARSAYILAN_YETKINLIKLER,
    # Kayıt
    "ogrenci_kayit_acik": True,
    "hoca_sanayi_onay_gerekli": True,
    "izinli_eposta_alanlari": "",
    "kvkk_metni": (
        "Bu sistemde paylaştığım ad-soyad, e-posta, bölüm, not ortalaması ve yetkinlik bilgilerimin; proje "
        "ekibi kurulması, danışman eşleştirmesi, başvuru belgelerinin hazırlanması ve tarafıma bilgilendirme "
        "yapılması amacıyla kurum içinde işlenmesine 6698 sayılı KVKK kapsamında onay veriyorum."
    ),
    # Dönem ve kurallar
    "aktif_donem": "2026",
    "max_kota_2209": 5,
    "max_kota_bitirme": 10,
    "max_ekip_2209": 5,
    "max_ekip_bitirme": 4,
    "max_ekip_teknofest": 15,
    "min_gno": 0.0,
    "butce_limit_2209a": 12000,
    "butce_limit_2209b": 16000,
    "max_sure_ay": 12,
    # Eşleştirme
    "otomatik_davet": True,
    "davet_aday_sayisi": 3,
    "davet_gecerlilik_gun": 14,
    "teknofest_esik": 5,  # yüzde
    # Hatırlatma
    "hatirlatma_gunleri": "10,3",
    "taslak_kontrol_gun": 7,
    # TEKNOFEST tarayıcı
    "teknofest_liste_url": "https://www.teknofest.org/tr/yarismalar/",
    "teknofest_tarama_gunu": "mon",
    "teknofest_tarama_saati": 3,
    "teknofest_tarama_gecikme": 1.5,
    "son_tarama": "",
    "son_tarama_ozet": "",
    # E-posta
    "eposta_aktif": False,
    "smtp_sunucu": "",
    "smtp_port": 587,
    "smtp_kullanici": "",
    "smtp_sifre": "",
    "smtp_gonderen": "",
    "smtp_guvenlik": "STARTTLS",  # STARTTLS / SSL / YOK
    # Telegram
    "telegram_aktif": False,
    "telegram_token": "",
    "telegram_bot_adi": "",
    "telegram_son_update": 0,
    # Google Drive
    "drive_aktif": False,
    "drive_mod": "service_account",  # service_account / oauth
    "drive_kimlik_dosyasi": "",
    "drive_ana_klasor_id": "",
    "drive_docs_donustur": True,
    "drive_paylasim_bildirimi": True,
    # Rehber
    "basvuru_rehberi": VARSAYILAN_REHBER,
    # Sistem
    "zamanlayici_kalp": "",
}

_ENV_KEYS = {
    "smtp_sifre": "SMTP_SIFRE",
    "smtp_kullanici": "SMTP_KULLANICI",
    "smtp_sunucu": "SMTP_SUNUCU",
    "telegram_token": "TELEGRAM_TOKEN",
    "drive_kimlik_dosyasi": "DRIVE_KIMLIK_DOSYASI",
    "uygulama_url": "UYGULAMA_URL",
}


def get(key: str, default: Any = None) -> Any:
    env_name = _ENV_KEYS.get(key)
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    with get_session() as s:
        row = s.get(Ayar, key)
    if row is not None and row.deger is not None:
        try:
            return json.loads(row.deger)
        except (json.JSONDecodeError, TypeError):
            return row.deger
    if default is not None:
        return default
    return DEFAULTS.get(key)


def save(key: str, value: Any) -> None:
    with get_session() as s:
        row = s.get(Ayar, key)
        payload = json.dumps(value, ensure_ascii=False)
        if row is None:
            s.add(Ayar(anahtar=key, deger=payload))
        else:
            row.deger = payload


def save_many(values: dict[str, Any]) -> None:
    for k, v in values.items():
        save(k, v)


def get_int(key: str) -> int:
    try:
        return int(float(get(key)))
    except (TypeError, ValueError):
        return int(DEFAULTS.get(key) or 0)


def get_float(key: str) -> float:
    try:
        return float(get(key))
    except (TypeError, ValueError):
        return float(DEFAULTS.get(key) or 0)


def get_bool(key: str) -> bool:
    v = get(key)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "evet", "yes", "on")
    return bool(v)


def hatirlatma_gunleri() -> list[int]:
    raw = str(get("hatirlatma_gunleri") or "10,3")
    out = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return sorted(set(out), reverse=True) or [10, 3]


def env_overridden(key: str) -> bool:
    env_name = _ENV_KEYS.get(key)
    return bool(env_name and os.environ.get(env_name))
