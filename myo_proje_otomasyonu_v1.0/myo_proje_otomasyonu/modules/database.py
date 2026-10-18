"""Veritabanı katmanı: tablolar, oturum yönetimi ve basit otomatik göç.

SQLite (varsayılan) ve PostgreSQL ile çalışır. PostgreSQL için
`DATABASE_URL=postgresql+psycopg2://kullanici:sifre@sunucu/vt` tanımlamak yeterlidir.
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine, event, func, inspect, select, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from . import config


def now() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# TABLO 1: kullanicilar
# ---------------------------------------------------------------------------
class Kullanici(Base):
    __tablename__ = "kullanicilar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ad_soyad: Mapped[str] = mapped_column(String(150))
    eposta: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    sifre_hash: Mapped[str] = mapped_column(String(300), default="")
    rol: Mapped[str] = mapped_column(String(20), index=True)  # admin / hoca / ogrenci / sanayi
    bolum: Mapped[str | None] = mapped_column(String(150), nullable=True)
    unvan: Mapped[str | None] = mapped_column(String(80), nullable=True)        # hoca için
    kurum: Mapped[str | None] = mapped_column(String(200), nullable=True)       # sanayi için firma
    ogrenci_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sinif: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ogrenim_turu: Mapped[str | None] = mapped_column(String(40), nullable=True)  # Örgün/İÖ/Açık Öğretim/Hazırlık
    gno: Mapped[float | None] = mapped_column(Float, nullable=True)
    yetkinlikler: Mapped[list] = mapped_column(JSON, default=list)
    telefon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telegram_kod: Mapped[str | None] = mapped_column(String(20), nullable=True)
    arbis_kaydi: Mapped[bool] = mapped_column(Boolean, default=False)
    yoksis_guncel: Mapped[bool] = mapped_column(Boolean, default=False)       # danışman için
    davet_almak_istiyor: Mapped[bool] = mapped_column(Boolean, default=True)
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    kvkk_onay: Mapped[bool] = mapped_column(Boolean, default=False)
    kvkk_tarih: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    sifre_sifirlama_kod: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sifre_sifirlama_son: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    sifre_degismeli: Mapped[bool] = mapped_column(Boolean, default=False)
    basarisiz_deneme: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    kilit_bitis: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    takip_edilen_kategoriler: Mapped[list] = mapped_column(JSON, default=list)
    olusturma: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    son_giris: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# TABLO 2: projeler (2209-A / 2209-B / Bitirme / Serbest TEKNOFEST)
# ---------------------------------------------------------------------------
class Proje(Base):
    __tablename__ = "projeler"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kod: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    baslik: Mapped[str] = mapped_column(String(300))
    ozet: Mapped[str] = mapped_column(Text, default="")
    anahtar_kelimeler: Mapped[str] = mapped_column(String(400), default="")
    tur: Mapped[str] = mapped_column(String(20), index=True)
    donem: Mapped[str] = mapped_column(String(20), default="")
    danisman_id: Mapped[int | None] = mapped_column(ForeignKey("kullanicilar.id"), nullable=True)
    sanayi_danisman_id: Mapped[int | None] = mapped_column(ForeignKey("kullanicilar.id"), nullable=True)
    olusturan_id: Mapped[int | None] = mapped_column(ForeignKey("kullanicilar.id"), nullable=True)
    sanayi_kurulus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    aranan_yetkinlikler: Mapped[list] = mapped_column(JSON, default=list)
    max_ekip: Mapped[int] = mapped_column(Integer, default=5)
    durum: Mapped[str] = mapped_column(String(30), default="Acik", index=True)
    sure_ay: Mapped[int] = mapped_column(Integer, default=12)
    # TYBS bölümleri
    konu_onemi: Mapped[str] = mapped_column(Text, default="")      # 2209-A 1.1
    amac_hedefler: Mapped[str] = mapped_column(Text, default="")   # 2209-A 1.2 / 2209-B 1.1
    yenilikci_yon: Mapped[str] = mapped_column(Text, default="")   # 2209-B 1.2
    yontem: Mapped[str] = mapped_column(Text, default="")
    arastirma_olanaklari: Mapped[str] = mapped_column(Text, default="")
    yaygin_etki: Mapped[str] = mapped_column(Text, default="")
    diger_konular: Mapped[str] = mapped_column(Text, default="")
    kaynaklar: Mapped[str] = mapped_column(Text, default="")
    is_plani: Mapped[list] = mapped_column(JSON, default=list)
    risk_plani: Mapped[list] = mapped_column(JSON, default=list)
    butce: Mapped[list] = mapped_column(JSON, default=list)
    etik_kurul_gerekli: Mapped[bool] = mapped_column(Boolean, default=False)
    teknofest_eslesmeler: Mapped[list] = mapped_column(JSON, default=list)
    eslesen_teknofest_kat_id: Mapped[int | None] = mapped_column(
        ForeignKey("teknofest_kategoriler.id"), nullable=True
    )
    sonuc: Mapped[str] = mapped_column(String(30), default="Beklemede")
    sonuc_notu: Mapped[str | None] = mapped_column(Text, nullable=True)
    olusturma: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    guncelleme: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------------------------------------------------------------------
# TABLO 3: teknofest_kategoriler (scraper çıktısı)
# ---------------------------------------------------------------------------
class TeknofestKategori(Base):
    __tablename__ = "teknofest_kategoriler"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kategori_adi: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    katilim_seviyesi: Mapped[str] = mapped_column(String(300), default="")
    onlisans_uygun: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None: bilinmiyor
    son_basvuru_tarihi: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    takvim: Mapped[list] = mapped_column(JSON, default=list)
    odul_miktari: Mapped[str] = mapped_column(String(300), default="")
    oduller: Mapped[list] = mapped_column(JSON, default=list)
    sartname_pdf_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    sartname_yerel_yol: Mapped[str | None] = mapped_column(String(800), nullable=True)
    rapor_sablonlari: Mapped[list] = mapped_column(JSON, default=list)
    aciklama: Mapped[str] = mapped_column(Text, default="")
    anahtar_kelimeler: Mapped[str] = mapped_column(Text, default="")
    takim_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    takim_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sezon: Mapped[str | None] = mapped_column(String(10), nullable=True)
    aktif: Mapped[bool] = mapped_column(Boolean, default=True)
    kaynak: Mapped[str] = mapped_column(String(30), default="manuel")
    son_guncelleme: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------------------
# TABLO 4: odullu_projeler (ilham arşivi)
# ---------------------------------------------------------------------------
class OdulluProje(Base):
    __tablename__ = "odullu_projeler"
    __table_args__ = (UniqueConstraint("kategori_adi", "yil", "derece", "takim_adi", name="uq_odul"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proje_adi: Mapped[str] = mapped_column(String(300), default="")
    takim_adi: Mapped[str] = mapped_column(String(200), default="")
    yil: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kategori_id: Mapped[int | None] = mapped_column(ForeignKey("teknofest_kategoriler.id"), nullable=True)
    kategori_adi: Mapped[str] = mapped_column(String(300), default="")
    program: Mapped[str] = mapped_column(String(30), default="TEKNOFEST")  # TEKNOFEST / 2209-A / 2209-B / Bitirme
    derece: Mapped[str] = mapped_column(String(100), default="")
    kurum_adi: Mapped[str] = mapped_column(String(300), default="")
    proje_ozeti: Mapped[str] = mapped_column(Text, default="")
    kullanilan_teknolojiler: Mapped[list] = mapped_column(JSON, default=list)
    rapor_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    kaynak: Mapped[str] = mapped_column(String(40), default="manuel")
    kaynak_proje_id: Mapped[int | None] = mapped_column(ForeignKey("projeler.id"), nullable=True)
    olusturma: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------------------
# TABLO 5: takim_eslesmeleri (otomasyon çıktıları)
# ---------------------------------------------------------------------------
class TakimEslesmesi(Base):
    __tablename__ = "takim_eslesmeleri"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proje_id: Mapped[int] = mapped_column(ForeignKey("projeler.id"), unique=True)
    ogrenci_id_listesi: Mapped[list] = mapped_column(JSON, default=list)
    yurutucu_id: Mapped[int | None] = mapped_column(ForeignKey("kullanicilar.id"), nullable=True)
    onay_durumu: Mapped[str] = mapped_column(String(30), default="Bekliyor")
    onay_tarihi: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    drive_klasor_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    drive_klasor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    yerel_klasor: Mapped[str | None] = mapped_column(String(800), nullable=True)
    tubitak_docx_yolu: Mapped[str | None] = mapped_column(String(800), nullable=True)
    teknofest_odr_yolu: Mapped[str | None] = mapped_column(String(800), nullable=True)
    belgeler: Mapped[list] = mapped_column(JSON, default=list)  # [{ad, yol, drive_id, drive_url}]
    arbis_onay: Mapped[bool] = mapped_column(Boolean, default=False)
    otomasyon_log: Mapped[list] = mapped_column(JSON, default=list)
    son_taslak_kontrol: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    bos_alan_sayisi: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ---------------------------------------------------------------------------
# Ek tablolar (belgede olmayan ama sistemin çalışması için gerekli)
# ---------------------------------------------------------------------------
class Basvuru(Base):
    """Öğrencinin bir projeye başvurusu (veya kabul edilmiş daveti)."""

    __tablename__ = "basvurular"
    __table_args__ = (UniqueConstraint("proje_id", "ogrenci_id", name="uq_basvuru"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proje_id: Mapped[int] = mapped_column(ForeignKey("projeler.id"), index=True)
    ogrenci_id: Mapped[int] = mapped_column(ForeignKey("kullanicilar.id"), index=True)
    motivasyon: Mapped[str] = mapped_column(Text, default="")
    durum: Mapped[str] = mapped_column(String(20), default="Beklemede")  # Beklemede/Kabul/Ret/Geri Cekildi
    uyum_skoru: Mapped[float] = mapped_column(Float, default=0.0)
    eksik_yetkinlikler: Mapped[list] = mapped_column(JSON, default=list)
    kaynak: Mapped[str] = mapped_column(String(20), default="basvuru")  # basvuru / davet
    tarih: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    karar_tarihi: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Davet(Base):
    __tablename__ = "davetler"
    __table_args__ = (UniqueConstraint("proje_id", "ogrenci_id", name="uq_davet"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proje_id: Mapped[int] = mapped_column(ForeignKey("projeler.id"), index=True)
    ogrenci_id: Mapped[int] = mapped_column(ForeignKey("kullanicilar.id"), index=True)
    yetkinlikler: Mapped[list] = mapped_column(JSON, default=list)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    durum: Mapped[str] = mapped_column(String(20), default="Gonderildi")  # Gonderildi/Kabul/Ret/Suresi Doldu
    tarih: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    yanit_tarihi: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class CagriTakvimi(Base):
    __tablename__ = "cagri_takvimi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    baslik: Mapped[str] = mapped_column(String(300))
    program: Mapped[str] = mapped_column(String(30))  # 2209-A / 2209-B / TEKNOFEST / Bitirme / Diğer
    baslangic: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    bitis: Mapped[dt.datetime] = mapped_column(DateTime)
    aciklama: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hedef_rol: Mapped[str] = mapped_column(String(40), default="ilgili")  # ilgili / tum_ogrenciler / hocalar
    kaynak: Mapped[str] = mapped_column(String(30), default="manuel")


class Bildirim(Base):
    __tablename__ = "bildirimler"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kullanici_id: Mapped[int | None] = mapped_column(ForeignKey("kullanicilar.id"), index=True, nullable=True)
    kanal: Mapped[str] = mapped_column(String(20))  # uygulama / eposta / telegram
    konu: Mapped[str] = mapped_column(String(300))
    icerik: Mapped[str] = mapped_column(Text)
    durum: Mapped[str] = mapped_column(String(20), default="Bekliyor")  # Gonderildi / Simule / Hata / Bekliyor
    hata: Mapped[str | None] = mapped_column(Text, nullable=True)
    anahtar: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    okundu: Mapped[bool] = mapped_column(Boolean, default=False)
    olusturma: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    gonderim: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Ayar(Base):
    __tablename__ = "ayarlar"

    anahtar: Mapped[str] = mapped_column(String(100), primary_key=True)
    deger: Mapped[str | None] = mapped_column(Text, nullable=True)


class Oturum(Base):
    """'Beni hatırla' oturumları: tarayıcı çerezindeki belirtecin özeti saklanır."""

    __tablename__ = "oturumlar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    kullanici_id: Mapped[int] = mapped_column(ForeignKey("kullanicilar.id"), index=True)
    olusturma: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    son_kullanma: Mapped[dt.datetime] = mapped_column(DateTime)


class IslemLog(Base):
    __tablename__ = "islem_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kullanici_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    islem: Mapped[str] = mapped_column(String(100))
    detay: Mapped[str] = mapped_column(Text, default="")
    tarih: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------------------
# Motor ve oturum
# ---------------------------------------------------------------------------
_connect_args = {"check_same_thread": False, "timeout": 30} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

if config.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - bağlantı ayarı
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _auto_migrate() -> None:
    """Yeni sürümlerde eklenen sütunları mevcut tabloya ekler (basit göç)."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                col_type = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {col_type}'))


_initialized = False


def init_db() -> None:
    global _initialized
    if _initialized:
        return
    Base.metadata.create_all(engine)
    _auto_migrate()
    _initialized = True


def log_islem(kullanici_id: int | None, islem: str, detay: str = "") -> None:
    with get_session() as s:
        s.add(IslemLog(kullanici_id=kullanici_id, islem=islem, detay=detay[:4000]))


def has_admin() -> bool:
    with get_session() as s:
        return s.scalar(select(func.count()).select_from(Kullanici).where(Kullanici.rol == "admin")) > 0


def get_user(user_id: int | None) -> Kullanici | None:
    if not user_id:
        return None
    with get_session() as s:
        return s.get(Kullanici, user_id)


def users_by_ids(ids: list[int]) -> dict[int, Kullanici]:
    if not ids:
        return {}
    with get_session() as s:
        return {u.id: u for u in s.scalars(select(Kullanici).where(Kullanici.id.in_(ids)))}
