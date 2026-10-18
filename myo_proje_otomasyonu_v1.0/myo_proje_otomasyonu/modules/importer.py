"""Excel/CSV içe ve dışa aktarma."""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd
from sqlalchemy import func, select

from . import auth
from .database import (
    Basvuru, Bildirim, CagriTakvimi, Kullanici, OdulluProje, Proje, TakimEslesmesi, TeknofestKategori, get_session,
)
from .text_utils import parse_list

KULLANICI_SUTUNLARI = ["ad_soyad", "eposta", "rol", "bolum", "unvan", "kurum", "ogrenci_no", "sinif", "ogrenim_turu", "gno", "yetkinlikler"]
ARSIV_SUTUNLARI = ["proje_adi", "takim_adi", "yil", "program", "kategori_adi", "derece", "kurum_adi", "proje_ozeti", "kullanilan_teknolojiler", "rapor_url"]
TAKVIM_SUTUNLARI = ["baslik", "program", "baslangic", "bitis", "url", "aciklama", "hedef_rol"]
ROL_ESLEME = {"ogrenci": "ogrenci", "öğrenci": "ogrenci", "hoca": "hoca", "danisman": "hoca", "danışman": "hoca",
              "akademisyen": "hoca", "sanayi": "sanayi", "admin": "admin", "yonetici": "admin", "yönetici": "admin"}


def ornek_excel(tur: str) -> bytes:
    if tur == "kullanici":
        df = pd.DataFrame([
            {"ad_soyad": "Ad Soyad", "eposta": "ogrenci@kurum.edu.tr", "rol": "ogrenci", "bolum": "Mekatronik", "unvan": "",
             "kurum": "", "ogrenci_no": "2025123456", "sinif": "1", "ogrenim_turu": "Örgün Öğretim", "gno": 3.1,
             "yetkinlikler": "SolidWorks, Arduino, Python"},
            {"ad_soyad": "Öğr. Gör. Ad Soyad", "eposta": "hoca@kurum.edu.tr", "rol": "hoca", "bolum": "Elektrik", "unvan": "Öğr. Gör.",
             "kurum": "", "ogrenci_no": "", "sinif": "", "ogrenim_turu": "", "gno": "", "yetkinlikler": "PLC, SCADA"},
        ], columns=KULLANICI_SUTUNLARI)
    elif tur == "arsiv":
        df = pd.DataFrame([{"proje_adi": "Proje adı", "takim_adi": "Takım", "yil": 2025, "program": "TEKNOFEST",
                            "kategori_adi": "Sanayide Robotik Uygulamalar Yarışması", "derece": "Finalist", "kurum_adi": "Kurum",
                            "proje_ozeti": "Kısa özet", "kullanilan_teknolojiler": "PLC, ROS", "rapor_url": ""}], columns=ARSIV_SUTUNLARI)
    else:
        df = pd.DataFrame([{"baslik": "Bitirme projesi öneri formu teslimi", "program": "Bitirme", "baslangic": "2026-10-01 09:00",
                            "bitis": "2026-11-30 17:00", "url": "", "aciklama": "", "hedef_rol": "tum_ogrenciler"}], columns=TAKVIM_SUTUNLARI)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def _read(upload) -> pd.DataFrame:
    name = getattr(upload, "name", "") or ""
    # dtype=str: boş hücre içeren sayısal sütunlarda "2025123456.0" gibi değerler oluşmasın
    if name.lower().endswith(".csv"):
        # Windows Excel'in CSV çıktısı: UTF-8 (BOM'lu) veya Windows-1254, ayraç çoğunlukla ';'
        ham = upload.getvalue() if hasattr(upload, "getvalue") else upload.read()
        try:
            metin = ham.decode("utf-8-sig")
        except UnicodeDecodeError:
            metin = ham.decode("cp1254", errors="replace")
        ilk = metin.split("\n", 1)[0]
        df = pd.read_csv(io.StringIO(metin), sep=";" if ilk.count(";") > ilk.count(",") else ",", dtype=str)
    else:
        df = pd.read_excel(upload, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.fillna("")


def _tarih(deger):
    """ISO (YYYY-AA-GG) metinleri gün-önce yorumlanıp ay/gün yer değiştirmesin."""
    metin = str(deger).strip()
    return pd.to_datetime(deger, dayfirst=not metin[:4].isdigit())


def kullanicilari_ice_aktar(upload) -> tuple[pd.DataFrame, list[str]]:
    """Kullanıcıları ekler. Oluşturulan geçici şifreleri tablo olarak döndürür."""
    df = _read(upload)
    sonuc, hatalar = [], []
    for i, row in df.iterrows():
        eposta = auth.normalize_email(str(row.get("eposta", "")))
        if not eposta:
            continue
        rol = ROL_ESLEME.get(str(row.get("rol", "ogrenci")).strip().lower(), "ogrenci")
        sifre = auth.random_password()
        gno = row.get("gno")
        try:
            gno = float(str(gno).replace(",", ".")) if str(gno).strip() else None
        except ValueError:
            gno = None
        if gno is not None and not 0 <= gno <= 4:
            hatalar.append(f"Satır {i + 2}: GNO 4'lük sistemde olmalı ({gno:g}), boş bırakıldı.")
            gno = None
        with get_session() as s:
            if s.scalar(select(Kullanici.id).where(func.lower(Kullanici.eposta) == eposta)):
                hatalar.append(f"Satır {i + 2}: {eposta} zaten kayıtlı, atlandı.")
                continue
            s.add(Kullanici(
                ad_soyad=str(row.get("ad_soyad", "")).strip() or eposta, eposta=eposta, rol=rol,
                bolum=str(row.get("bolum", "")) or None, unvan=str(row.get("unvan", "")) or None, kurum=str(row.get("kurum", "")) or None,
                ogrenci_no=str(row.get("ogrenci_no", "")) or None, sinif=str(row.get("sinif", "")) or None,
                ogrenim_turu=str(row.get("ogrenim_turu", "")) or None, gno=gno,
                yetkinlikler=parse_list(str(row.get("yetkinlikler", ""))), sifre_hash=auth.hash_password(sifre),
                sifre_degismeli=True, aktif=True, kvkk_onay=False,
            ))
        sonuc.append({"ad_soyad": row.get("ad_soyad", ""), "eposta": eposta, "rol": rol, "gecici_sifre": sifre})
    return pd.DataFrame(sonuc), hatalar


def arsivi_ice_aktar(upload) -> tuple[int, list[str]]:
    df = _read(upload)
    eklenen, hatalar = 0, []
    with get_session() as s:
        kategoriler = {k.kategori_adi.lower(): k.id for k in s.scalars(select(TeknofestKategori))}
        for i, row in df.iterrows():
            if not str(row.get("proje_adi", "")).strip() and not str(row.get("takim_adi", "")).strip():
                continue
            try:
                yil = int(float(row.get("yil"))) if str(row.get("yil", "")).strip() else None
            except ValueError:
                yil = None
                hatalar.append(f"Satır {i + 2}: yıl okunamadı.")
            kat_adi = str(row.get("kategori_adi", ""))
            if s.scalar(select(OdulluProje.id).where(
                    OdulluProje.kategori_adi == kat_adi, OdulluProje.yil == yil,
                    OdulluProje.derece == str(row.get("derece", "")), OdulluProje.takim_adi == str(row.get("takim_adi", "")))):
                hatalar.append(f"Satır {i + 2}: arşivde zaten var, atlandı.")
                continue
            s.add(OdulluProje(
                proje_adi=str(row.get("proje_adi", "")), takim_adi=str(row.get("takim_adi", "")), yil=yil,
                program=str(row.get("program", "") or "TEKNOFEST"), kategori_adi=kat_adi, kategori_id=kategoriler.get(kat_adi.lower()),
                derece=str(row.get("derece", "")), kurum_adi=str(row.get("kurum_adi", "")), proje_ozeti=str(row.get("proje_ozeti", "")),
                kullanilan_teknolojiler=parse_list(str(row.get("kullanilan_teknolojiler", ""))),
                rapor_url=str(row.get("rapor_url", "")) or None, kaynak="Excel",
            ))
            eklenen += 1
    return eklenen, hatalar


def takvimi_ice_aktar(upload) -> tuple[int, list[str]]:
    df = _read(upload)
    eklenen, hatalar = 0, []
    with get_session() as s:
        for i, row in df.iterrows():
            try:
                bitis = _tarih(row.get("bitis"))
                if pd.isna(bitis):
                    raise ValueError("boş tarih")
                bitis = bitis.to_pydatetime()
            except Exception:  # noqa: BLE001
                hatalar.append(f"Satır {i + 2}: bitiş tarihi okunamadı.")
                continue
            bas = None
            if str(row.get("baslangic", "")).strip():
                try:
                    bas = _tarih(row.get("baslangic"))
                    bas = None if pd.isna(bas) else bas.to_pydatetime()
                except Exception:  # noqa: BLE001
                    bas = None
            s.add(CagriTakvimi(baslik=str(row.get("baslik", "Son tarih")), program=str(row.get("program", "Diğer")),
                               baslangic=bas, bitis=bitis, url=str(row.get("url", "")) or None, aciklama=str(row.get("aciklama", "")),
                               hedef_rol=str(row.get("hedef_rol", "") or "ilgili"), kaynak="Excel"))
            eklenen += 1
    return eklenen, hatalar


def tum_veriyi_disa_aktar() -> bytes:
    """Kurum raporu: tüm ana tablolar tek Excel dosyasında (şifre özetleri hariç)."""
    buf = io.BytesIO()
    with get_session() as s, pd.ExcelWriter(buf, engine="openpyxl") as xw:
        def dump(model, sheet, drop=()):
            rows = []
            for obj in s.scalars(select(model)):
                d = {c.name: getattr(obj, c.name) for c in model.__table__.columns if c.name not in drop}
                for k, v in d.items():
                    if isinstance(v, (list, dict)):
                        d[k] = ", ".join(map(str, v)) if isinstance(v, list) and all(not isinstance(x, dict) for x in v) else str(v)
                rows.append(d)
            pd.DataFrame(rows).to_excel(xw, sheet_name=sheet, index=False)

        dump(Kullanici, "Kullanicilar", drop=("sifre_hash", "sifre_sifirlama_kod", "telegram_kod"))
        dump(Proje, "Projeler")
        dump(Basvuru, "Basvurular")
        dump(TakimEslesmesi, "Takimlar")
        dump(TeknofestKategori, "TEKNOFEST")
        dump(OdulluProje, "Odullu_Arsiv")
        dump(CagriTakvimi, "Cagri_Takvimi")
        dump(Bildirim, "Bildirimler", drop=("icerik",))  # içerik geçici şifre / sıfırlama kodu barındırabilir
    return buf.getvalue()


def zaman_damgasi() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M")
