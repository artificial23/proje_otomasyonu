"""Kural motoru: danışman kotası, öğrenci uygunluğu ve TÜBİTAK ön kontrolü.

Varsayılan kurallar 2026 yılı 2209-A / 2209-B çağrı metinlerine göre ayarlanmıştır
(proje süresi en çok 12 ay, yürütücü + en fazla 4 ortak, danışman başına aynı dönemde
en fazla 5 proje, öğrenci başına dönemde tek başvuru). Kurum, değerleri Yönetim
Paneli'nden güncelleyebilir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, select

from . import settings
from .database import Basvuru, Kullanici, Proje, get_session
from .text_utils import fold, word_count

TURLER = ["2209-A", "2209-B", "Bitirme", "TEKNOFEST"]
TUBITAK_TURLERI = {"2209-A", "2209-B"}
DURUMLAR = ["Taslak", "Acik", "Yedek Havuz", "Dolu", "Onaylandi", "Basvuruldu", "Sonuclandi", "Iptal"]
DURUM_ETIKET = {
    "Taslak": "Taslak", "Acik": "Açık", "Yedek Havuz": "Yedek Havuz", "Dolu": "Ekip Tamam",
    "Onaylandi": "Onaylandı / Kuruldu", "Basvuruldu": "Başvuru Yapıldı", "Sonuclandi": "Sonuçlandı", "Iptal": "İptal",
}
KOTA_DURUMLARI = {"Acik", "Dolu", "Onaylandi", "Basvuruldu", "Sonuclandi"}
SONUCLAR = ["Beklemede", "Kabul", "Ret", "Finalist", "Derece"]
OGRENIM_TURLERI = ["Örgün Öğretim", "İkinci Öğretim", "Uzaktan Öğretim", "Açık Öğretim", "Hazırlık Sınıfı"]
TUBITAK_UYGUN_DEGIL = {"Açık Öğretim", "Hazırlık Sınıfı"}
YASAK_IS_ADIMLARI = ["literatur", "rapor yaz", "raporlama", "yayginlastir", "malzeme alim", "malzeme temin",
                     "satin alma", "satin alim", "sonuclarin paylas"]


@dataclass
class Kontrol:
    seviye: str  # "hata" / "uyari" / "tamam"
    alan: str
    mesaj: str


# ---------------------------------------------------------------------------
# Kota
# ---------------------------------------------------------------------------
def kota_limiti(tur: str) -> int:
    if tur in TUBITAK_TURLERI:
        return settings.get_int("max_kota_2209")
    if tur == "Bitirme":
        return settings.get_int("max_kota_bitirme")
    return 999


def ekip_limiti(tur: str) -> int:
    if tur in TUBITAK_TURLERI:
        return settings.get_int("max_ekip_2209")
    if tur == "Bitirme":
        return settings.get_int("max_ekip_bitirme")
    return settings.get_int("max_ekip_teknofest")


def kota_grubu(tur: str) -> set[str]:
    return TUBITAK_TURLERI if tur in TUBITAK_TURLERI else {tur}


def aktif_danismanlik_sayisi(hoca_id: int, tur: str, donem: str | None = None, haric_proje_id: int | None = None) -> int:
    donem = donem or str(settings.get("aktif_donem"))
    with get_session() as s:
        q = select(func.count()).select_from(Proje).where(
            Proje.danisman_id == hoca_id,
            Proje.tur.in_(kota_grubu(tur)),
            Proje.donem == donem,
            Proje.durum.in_(KOTA_DURUMLARI),
        )
        if haric_proje_id:
            q = q.where(Proje.id != haric_proje_id)
        return s.scalar(q) or 0


def kota_uygun_mu(hoca_id: int, tur: str, donem: str | None = None, haric_proje_id: int | None = None) -> tuple[bool, int, int]:
    limit = kota_limiti(tur)
    sayi = aktif_danismanlik_sayisi(hoca_id, tur, donem, haric_proje_id)
    return sayi < limit, sayi, limit


# ---------------------------------------------------------------------------
# Ekip ve öğrenci uygunluğu
# ---------------------------------------------------------------------------
def ekip_uyeleri(proje_id: int) -> list[int]:
    with get_session() as s:
        return list(s.scalars(
            select(Basvuru.ogrenci_id).where(Basvuru.proje_id == proje_id, Basvuru.durum == "Kabul").order_by(Basvuru.karar_tarihi, Basvuru.id)
        ))


def ogrencinin_aktif_2209_projesi(ogrenci_id: int, donem: str, haric_proje_id: int | None = None) -> Proje | None:
    with get_session() as s:
        q = (
            select(Proje)
            .join(Basvuru, Basvuru.proje_id == Proje.id)
            .where(
                Basvuru.ogrenci_id == ogrenci_id,
                Basvuru.durum == "Kabul",
                Proje.tur.in_(TUBITAK_TURLERI),
                Proje.donem == donem,
                Proje.durum != "Iptal",
            )
        )
        if haric_proje_id:
            q = q.where(Proje.id != haric_proje_id)
        return s.scalars(q).first()


def ogrenci_uygunlugu(ogrenci: Kullanici, proje: Proje) -> list[Kontrol]:
    """Öğrencinin projeye katılabilmesi için engel (hata) ve uyarıları döndürür."""
    out: list[Kontrol] = []
    if proje.tur in TUBITAK_TURLERI:
        if (ogrenci.ogrenim_turu or "") in TUBITAK_UYGUN_DEGIL:
            out.append(Kontrol("hata", "Öğrenim türü", f"{ogrenci.ogrenim_turu} öğrencileri TÜBİTAK 2209 projelerinde yer alamaz."))
        diger = ogrencinin_aktif_2209_projesi(ogrenci.id, proje.donem, haric_proje_id=proje.id)
        if diger:
            out.append(Kontrol("hata", "Tek başvuru kuralı", f"Bu dönem zaten '{diger.baslik}' projesinin ekibindesiniz. Aynı dönemde birden fazla 2209 başvurusu yapılamaz."))
        if not ogrenci.arbis_kaydi:
            out.append(Kontrol("uyari", "ARBİS", "ARBİS kaydınız işaretli değil. Başvurudan önce arbis.tubitak.gov.tr üzerinden kayıt olun."))
    min_gno = settings.get_float("min_gno")
    if min_gno > 0 and (ogrenci.gno or 0) < min_gno:
        out.append(Kontrol("hata", "GNO", f"Kurum kuralına göre en az {min_gno:.2f} GNO gerekiyor."))
    uyeler = ekip_uyeleri(proje.id)
    if ogrenci.id not in uyeler and len(uyeler) >= (proje.max_ekip or ekip_limiti(proje.tur)):
        out.append(Kontrol("hata", "Ekip", "Proje ekibi dolu."))
    return out


# ---------------------------------------------------------------------------
# Varsayılan çalışma takvimi ve risk tablosu
# ---------------------------------------------------------------------------
_VARSAYILAN_IS_PAKETLERI = [
    ("Gereksinim analizi ve sistem tasarımı",
     "Tasarım dokümanı, CAD modelleri ve devre/yazılım mimarisinin %100 tamamlanması", 25),
    ("Prototip üretimi ve yazılım geliştirme",
     "Prototipin tüm alt sistemleriyle birlikte çalışır hâle gelmesi", 35),
    ("Test, doğrulama ve iyileştirme",
     "Belirlenen performans ölçütlerinin en az %80'inin sağlanması", 25),
    ("Saha / uygulama denemesi ve performans ölçümü",
     "Gerçek koşullarda en az 3 deneme ve ölçüm sonuçlarının raporlanabilir hâle gelmesi", 15),
]

_VARSAYILAN_RISKLER = [
    ("Tasarım gereksinimlerinin süreç içinde değişmesi", "Modüler tasarım yapılır; alternatif yapılandırma önceden hazırlanır."),
    ("Malzeme tedarikinde gecikme veya fiyat artışı", "Muadil bileşen listesi ve alternatif tedarikçi belirlenir; kritik parçalar erkenden sipariş edilir."),
    ("Prototipin hedef performansı sağlayamaması", "Parametre optimizasyonu ve alternatif yöntem/algoritma denenir; ana amaçtan sapılmaz."),
    ("Saha denemesine erişim sorunu", "Doğrulama laboratuvar ortamında benzetimle yapılır, saha denemesi sonraki uygun tarihe alınır."),
]


def varsayilan_is_plani(sure_ay: int, ekip_adlari: list[str] | None = None) -> list[dict]:
    n = max(1, min(int(sure_ay or 12), 24))
    sinirlar = [0, 0.25, 0.6, 0.85, 1.0]
    ekip_adlari = ekip_adlari or []
    plan = []
    for i, (ad, olcut, katki) in enumerate(_VARSAYILAN_IS_PAKETLERI):
        bas = int(sinirlar[i] * n) + 1
        bit = max(bas, round(sinirlar[i + 1] * n))
        sorumlu = ekip_adlari[i % len(ekip_adlari)] if ekip_adlari else "Proje ekibi"
        plan.append({"is_paketi": ad, "sorumlu": sorumlu, "baslangic_ay": bas, "bitis_ay": min(bit, n),
                     "basari_olcutu": olcut, "katki_yuzde": katki})
    return plan


def varsayilan_risk_plani() -> list[dict]:
    return [{"is_paketi_no": i + 1, "risk": r, "b_plani": b} for i, (r, b) in enumerate(_VARSAYILAN_RISKLER)]


# ---------------------------------------------------------------------------
# TÜBİTAK TYBS ön kontrolü
# ---------------------------------------------------------------------------
def _min_char(out: list[Kontrol], alan: str, metin: str, minimum: int = 350) -> None:
    n = len((metin or "").strip())
    if n == 0:
        out.append(Kontrol("hata", alan, f"Boş. TYBS'de en az {minimum} karakter gerekiyor."))
    elif n < minimum:
        out.append(Kontrol("hata", alan, f"{n} karakter; en az {minimum} karakter olmalı."))
    else:
        out.append(Kontrol("tamam", alan, f"{n} karakter."))


def tubitak_on_kontrol(proje: Proje, ekip: list[Kullanici], danisman: Kullanici | None,
                       sanayi_danismani: Kullanici | None = None) -> list[Kontrol]:
    out: list[Kontrol] = []
    tur = proje.tur

    # Özet
    wc = word_count(proje.ozet)
    if 25 <= wc <= 450:
        out.append(Kontrol("tamam", "Özet", f"{wc} kelime (25–450 aralığında)."))
    else:
        out.append(Kontrol("hata", "Özet", f"{wc} kelime; özet 25–450 kelime olmalı."))

    if tur == "2209-A":
        _min_char(out, "1.1 Konunun Önemi ve Bilimsel Niteliği", proje.konu_onemi)
        _min_char(out, "1.2 Amaç ve Hedefler", proje.amac_hedefler)
    else:
        _min_char(out, "1.1 Amaç ve Hedefler", proje.amac_hedefler)
        _min_char(out, "1.2 Yenilikçi Yönü ve Teknolojik Değeri", proje.yenilikci_yon)
    _min_char(out, "2. Yöntem", proje.yontem)

    # Süre ve çalışma takvimi
    max_sure = settings.get_int("max_sure_ay")
    if (proje.sure_ay or 0) > max_sure:
        out.append(Kontrol("hata", "Proje süresi", f"{proje.sure_ay} ay; en çok {max_sure} ay olabilir."))
    plan = proje.is_plani or []
    if not plan:
        out.append(Kontrol("hata", "3.1 Çalışma Takvimi", "En az bir iş adımı gerekli."))
    else:
        toplam = sum(float(p.get("katki_yuzde") or 0) for p in plan)
        if abs(toplam - 100) > 0.01:
            out.append(Kontrol("hata", "3.1 Başarı ölçütü toplamı", f"Başarı ölçütü katkılarının toplamı %{toplam:g}; %100 olmalı."))
        else:
            out.append(Kontrol("tamam", "3.1 Başarı ölçütü toplamı", "%100."))
        for p in plan:
            ad = fold(str(p.get("is_paketi", "")))
            if any(y in ad for y in YASAK_IS_ADIMLARI):
                out.append(Kontrol("hata", "3.1 İş adımı", f"'{p.get('is_paketi')}' ayrı iş adımı olarak yazılamaz (literatür taraması, rapor yazımı, yaygınlaştırma, malzeme alımı)."))
            try:
                if int(p.get("bitis_ay") or 0) > (proje.sure_ay or 12):
                    out.append(Kontrol("hata", "3.1 İş adımı süresi", f"'{p.get('is_paketi')}' proje süresini aşıyor."))
            except (TypeError, ValueError):
                pass
            if not re.search(r"\d", str(p.get("basari_olcutu", ""))):
                out.append(Kontrol("uyari", "3.1 Başarı ölçütü", f"'{p.get('is_paketi')}' için ölçülebilir (sayısal) bir başarı ölçütü yazın."))
    if not proje.risk_plani:
        out.append(Kontrol("hata", "3.2 Risk Yönetimi", "Risk ve B planı tablosu boş."))
    if len((proje.arastirma_olanaklari or "").strip()) < 50:
        out.append(Kontrol("uyari", "3.3 Araştırma Olanakları", "Kullanılacak laboratuvar/atölye/ekipmanları yazın."))
    if len((proje.yaygin_etki or "").strip()) < 100:
        out.append(Kontrol("uyari", "4. Yaygın Etki", "Beklenen çıktıları ölçülebilir hedeflerle yazın."))

    # Kaynaklar
    kaynaklar = [k for k in (proje.kaynaklar or "").splitlines() if k.strip()]
    if not kaynaklar:
        out.append(Kontrol("uyari", "Kaynaklar", "Kaynak listesi boş."))
    else:
        doisiz = [k for k in kaynaklar if "doi" not in k.lower() and "10." not in k]
        if doisiz:
            out.append(Kontrol("uyari", "Kaynaklar", f"{len(doisiz)} kaynakta DOI görünmüyor. DOI'si olan kaynaklarda DOI yazmak zorunludur."))

    # Bütçe
    limit = settings.get_int("butce_limit_2209a" if tur == "2209-A" else "butce_limit_2209b")
    toplam_butce = sum(float(b.get("tutar") or 0) for b in (proje.butce or []))
    if toplam_butce > limit:
        out.append(Kontrol("hata", "Bütçe", f"Toplam {toplam_butce:,.0f} TL; üst limit {limit:,.0f} TL."))
    elif toplam_butce == 0:
        out.append(Kontrol("uyari", "Bütçe", "Bütçe kalemi girilmemiş."))
    else:
        out.append(Kontrol("tamam", "Bütçe", f"{toplam_butce:,.0f} TL / {limit:,.0f} TL."))

    # Ekip
    ekip_max = settings.get_int("max_ekip_2209")
    if not ekip:
        out.append(Kontrol("hata", "Ekip", "Ekipte en az bir öğrenci (proje yürütücüsü) olmalı."))
    elif len(ekip) > ekip_max:
        out.append(Kontrol("hata", "Ekip", f"{len(ekip)} kişi; yürütücü dahil en fazla {ekip_max} kişi olabilir."))
    for u in ekip:
        if (u.ogrenim_turu or "") in TUBITAK_UYGUN_DEGIL:
            out.append(Kontrol("hata", "Ekip", f"{u.ad_soyad}: {u.ogrenim_turu} öğrencisi yer alamaz."))
        if not u.arbis_kaydi:
            out.append(Kontrol("uyari", "ARBİS", f"{u.ad_soyad} ARBİS kaydını onaylamadı."))

    # Danışmanlar
    if not danisman:
        out.append(Kontrol("hata", "Danışman", "Akademik danışman atanmamış."))
    else:
        if not danisman.yoksis_guncel:
            out.append(Kontrol("uyari", "Danışman", "Danışmanın YÖKSİS kaydının güncel olduğu onaylanmadı."))
        if not danisman.arbis_kaydi:
            out.append(Kontrol("uyari", "Danışman", "Danışmanın ARBİS kaydı onaylanmadı."))
    if tur == "2209-B":
        if not sanayi_danismani and not proje.sanayi_kurulus:
            out.append(Kontrol("hata", "Sanayi danışmanı", "2209-B projelerinde sanayi danışmanı zorunludur."))
        if sanayi_danismani and danisman and sanayi_danismani.id == danisman.id:
            out.append(Kontrol("hata", "Sanayi danışmanı", "Akademik danışman ve sanayi danışmanı aynı kişi olamaz."))
    if proje.etik_kurul_gerekli:
        out.append(Kontrol("uyari", "Etik kurul", "Etik kurul onayı/muafiyet belgesi bilimsel değerlendirme sonrası e-BİDEB'e yüklenmelidir."))
    return out


def kontrol_ozeti(kontroller: list[Kontrol]) -> tuple[int, int, int]:
    h = sum(1 for k in kontroller if k.seviye == "hata")
    u = sum(1 for k in kontroller if k.seviye == "uyari")
    t = sum(1 for k in kontroller if k.seviye == "tamam")
    return h, u, t
