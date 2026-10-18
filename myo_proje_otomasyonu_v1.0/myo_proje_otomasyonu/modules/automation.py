"""İş akışları: ilan/kota, başvuru-davet, 'Onayla ve Kur' zinciri, hatırlatmalar.

Arayüz (Streamlit sayfaları) ve zamanlayıcı (worker.py) yalnızca bu modüldeki
fonksiyonları çağırır; böylece aynı mantık hem butonla hem otomatik çalışır.
"""
from __future__ import annotations

import datetime as dt
import logging
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select

from . import config, doc_generator, matcher, notifier, rules, settings
from .database import (
    Basvuru, CagriTakvimi, Davet, Kullanici, OdulluProje, Proje, TakimEslesmesi, TeknofestKategori,
    get_session, log_islem, now,
)
from .text_utils import parse_list, safe_filename

log = logging.getLogger("kulucka.automation")

TUR_KISA = {"2209-A": "A", "2209-B": "B", "Bitirme": "BT", "TEKNOFEST": "TF"}


@dataclass
class Sonuc:
    ok: bool
    mesaj: str
    veri: object | None = None


def _app_url(path_query: str = "") -> str:
    base = str(settings.get("uygulama_url") or "").rstrip("/")
    return f"{base}/{path_query.lstrip('/')}" if base else ""


# ---------------------------------------------------------------------------
# İlan oluşturma ve kota
# ---------------------------------------------------------------------------
def proje_olustur(veri: dict, olusturan: Kullanici) -> Sonuc:
    tur = veri.get("tur", "2209-A")
    danisman_id = veri.get("danisman_id") or (olusturan.id if olusturan.rol == "hoca" else None)
    if not danisman_id:
        return Sonuc(False, "Bir akademik danışman seçilmelidir.")
    if tur == "2209-B" and olusturan.rol == "sanayi":
        veri.setdefault("sanayi_danisman_id", olusturan.id)
        veri.setdefault("sanayi_kurulus", olusturan.kurum)
    if tur == "2209-B" and veri.get("sanayi_danisman_id") and int(veri["sanayi_danisman_id"]) == int(danisman_id):
        return Sonuc(False, "Akademik danışman ve sanayi danışmanı aynı kişi olamaz.")
    donem = str(veri.get("donem") or settings.get("aktif_donem"))
    uygun, sayi, limit = rules.kota_uygun_mu(int(danisman_id), tur, donem)
    durum = "Acik" if uygun else "Yedek Havuz"
    if veri.get("taslak"):
        durum = "Taslak"
    aranan = parse_list(veri.get("aranan_yetkinlikler", []))
    eslesmeler = matcher.teknofest_eslestir(veri.get("baslik", ""), veri.get("ozet", ""), veri.get("anahtar_kelimeler", ""),
                                            aranan, veri.get("yontem", ""))
    sure = min(int(veri.get("sure_ay") or 12), 24)
    with get_session() as s:
        p = Proje(
            baslik=veri["baslik"].strip(), ozet=veri.get("ozet", ""), anahtar_kelimeler=veri.get("anahtar_kelimeler", ""),
            tur=tur, donem=donem, danisman_id=int(danisman_id), sanayi_danisman_id=veri.get("sanayi_danisman_id"),
            olusturan_id=olusturan.id, sanayi_kurulus=veri.get("sanayi_kurulus"), aranan_yetkinlikler=aranan,
            max_ekip=min(int(veri.get("max_ekip") or rules.ekip_limiti(tur)), rules.ekip_limiti(tur)), durum=durum, sure_ay=sure,
            konu_onemi=veri.get("konu_onemi", ""), amac_hedefler=veri.get("amac_hedefler", ""),
            yenilikci_yon=veri.get("yenilikci_yon", ""), yontem=veri.get("yontem", ""),
            arastirma_olanaklari=veri.get("arastirma_olanaklari", ""), yaygin_etki=veri.get("yaygin_etki", ""),
            kaynaklar=veri.get("kaynaklar", ""), etik_kurul_gerekli=bool(veri.get("etik_kurul_gerekli")),
            teknofest_eslesmeler=eslesmeler,
            eslesen_teknofest_kat_id=veri.get("eslesen_teknofest_kat_id") or (eslesmeler[0]["kategori_id"] if eslesmeler else None),
            is_plani=rules.varsayilan_is_plani(sure) if tur != "TEKNOFEST" else [],
            risk_plani=rules.varsayilan_risk_plani(),
            butce=veri.get("butce") or [],
        )
        s.add(p)
        s.flush()
        p.kod = f"{TUR_KISA.get(tur, 'P')}{donem}-{p.id:04d}"
        s.add(TakimEslesmesi(proje_id=p.id))
        pid = p.id
    log_islem(olusturan.id, "proje_olustur", f"{pid} {tur} {durum}")
    with get_session() as s:
        p = s.get(Proje, pid)
        danisman = s.get(Kullanici, int(danisman_id))
    if olusturan.id != danisman.id:
        notifier.notify(danisman, f"Yeni proje ilanında danışman olarak seçildiniz: {p.baslik}",
                        f"{olusturan.ad_soyad} ({olusturan.kurum or olusturan.bolum or '-'}) '{p.baslik}' başlıklı {tur} ilanında "
                        f"sizi akademik danışman olarak belirledi. İlan durumu: {rules.DURUM_ETIKET[p.durum]}.")
    if durum == "Yedek Havuz":
        notifier.notify(danisman, f"Kota dolu: '{p.baslik}' yedek havuza alındı",
                        f"Bu dönem {limit} proje sınırına ulaştınız ({sayi}/{limit}). İlan 'Yedek Dönem Havuzu'na alındı; "
                        "aktif projelerinizden biri iptal edilirse otomatik olarak yayına alınır.")
        return Sonuc(True, f"Danışman kotası dolu ({sayi}/{limit}). İlan yedek havuza alındı.", p)
    return Sonuc(True, "İlan yayınlandı." if durum == "Acik" else "Taslak kaydedildi.", p)


def proje_guncelle(proje_id: int, alanlar: dict, kullanici_id: int | None = None, eslesme_yenile: bool = False) -> Proje:
    with get_session() as s:
        p = s.get(Proje, proje_id)
        for k, v in alanlar.items():
            setattr(p, k, v)
        if eslesme_yenile:
            p.teknofest_eslesmeler = matcher.teknofest_eslestir(p.baslik, p.ozet, p.anahtar_kelimeler, p.aranan_yetkinlikler, p.yontem)
            if not p.eslesen_teknofest_kat_id and p.teknofest_eslesmeler:
                p.eslesen_teknofest_kat_id = p.teknofest_eslesmeler[0]["kategori_id"]
    log_islem(kullanici_id, "proje_guncelle", f"{proje_id}: {', '.join(alanlar)}")
    with get_session() as s:
        return s.get(Proje, proje_id)


def yedek_havuz_terfi(hoca_id: int) -> int:
    """Kota boşaldığında yedek havuzdaki en eski ilanları yayına alır."""
    terfi = 0
    with get_session() as s:
        bekleyenler = list(s.scalars(select(Proje).where(Proje.danisman_id == hoca_id, Proje.durum == "Yedek Havuz").order_by(Proje.olusturma)))
    for p in bekleyenler:
        uygun, _, _ = rules.kota_uygun_mu(hoca_id, p.tur, p.donem)
        if not uygun:
            continue
        with get_session() as s:
            s.get(Proje, p.id).durum = "Acik"
        terfi += 1
        notifier.notify(hoca_id, f"Yedek havuzdaki ilan yayına alındı: {p.baslik}", "Kotanızda yer açıldığı için ilan otomatik olarak yayına alındı.")
    return terfi


def proje_durum_degistir(proje_id: int, durum: str, kullanici_id: int | None = None) -> None:
    with get_session() as s:
        p = s.get(Proje, proje_id)
        p.durum = durum
        hoca_id = p.danisman_id
    log_islem(kullanici_id, "proje_durum", f"{proje_id} -> {durum}")
    if durum in ("Iptal", "Taslak") and hoca_id:
        yedek_havuz_terfi(hoca_id)


def sonuc_guncelle(proje_id: int, sonuc: str, notu: str = "", kullanici_id: int | None = None) -> None:
    """Sonuç girildiğinde başarılı projeler otomatik olarak Ödüllü Arşiv'e aktarılır (geri besleme)."""
    with get_session() as s:
        p = s.get(Proje, proje_id)
        p.sonuc, p.sonuc_notu = sonuc, notu
        if sonuc != "Beklemede":
            p.durum = "Sonuclandi"
        if sonuc in ("Kabul", "Finalist", "Derece"):
            var = s.scalar(select(OdulluProje.id).where(OdulluProje.kaynak_proje_id == p.id))
            kat = s.get(TeknofestKategori, p.eslesen_teknofest_kat_id) if p.eslesen_teknofest_kat_id else None
            if var:
                mevcut = s.get(OdulluProje, var)
                mevcut.derece = {"Kabul": "Destek Kazandı"}.get(sonuc, notu or sonuc)
            if not var:
                uyeler = rules.ekip_uyeleri(p.id)
                tekno = []
                for u in s.scalars(select(Kullanici).where(Kullanici.id.in_(uyeler or [0]))):
                    tekno.extend(u.yetkinlikler or [])
                program = "TEKNOFEST" if p.tur == "TEKNOFEST" or sonuc in ("Finalist", "Derece") else p.tur
                s.add(OdulluProje(
                    proje_adi=p.baslik, takim_adi=p.kod or "", yil=int(str(p.donem)[:4]) if str(p.donem)[:4].isdigit() else dt.date.today().year,
                    kategori_id=kat.id if kat and program == "TEKNOFEST" else None,
                    kategori_adi=(kat.kategori_adi if kat and program == "TEKNOFEST" else f"TÜBİTAK {p.tur}" if p.tur in rules.TUBITAK_TURLERI else p.tur),
                    program=program, derece={"Kabul": "Destek Kazandı"}.get(sonuc, notu or sonuc), kurum_adi=str(settings.get("kurum_adi")),
                    proje_ozeti=p.ozet, kullanilan_teknolojiler=sorted(set(tekno))[:15], kaynak="Kurum içi (otomatik)", kaynak_proje_id=p.id,
                ))
        hoca_id = p.danisman_id
    log_islem(kullanici_id, "proje_sonuc", f"{proje_id} -> {sonuc}")
    if hoca_id:
        yedek_havuz_terfi(hoca_id)


# ---------------------------------------------------------------------------
# Başvuru ve davet
# ---------------------------------------------------------------------------
def basvuru_yap(ogrenci: Kullanici, proje_id: int, motivasyon: str = "", kaynak: str = "basvuru") -> Sonuc:
    with get_session() as s:
        p = s.get(Proje, proje_id)
        mevcut = s.scalar(select(Basvuru).where(Basvuru.proje_id == proje_id, Basvuru.ogrenci_id == ogrenci.id))
    if p.durum not in ("Acik",):
        return Sonuc(False, "Bu ilan şu an başvuruya açık değil.")
    if mevcut and mevcut.durum in ("Beklemede", "Kabul"):
        return Sonuc(False, "Bu projeye zaten başvurdunuz.")
    engeller = [k for k in rules.ogrenci_uygunlugu(ogrenci, p) if k.seviye == "hata"]
    if engeller:
        return Sonuc(False, " ".join(k.mesaj for k in engeller))
    analiz = matcher.yetkinlik_analizi(p.aranan_yetkinlikler, ogrenci.yetkinlikler, matcher.ekip_yetkinlikleri(p.id))
    with get_session() as s:
        if mevcut:
            b = s.get(Basvuru, mevcut.id)
            b.durum, b.motivasyon, b.tarih, b.kaynak = "Beklemede", motivasyon, now(), kaynak
        else:
            b = Basvuru(proje_id=proje_id, ogrenci_id=ogrenci.id, motivasyon=motivasyon, kaynak=kaynak)
            s.add(b)
        b.uyum_skoru = analiz.uyum_yuzde
        b.eksik_yetkinlikler = analiz.eksik
    log_islem(ogrenci.id, "basvuru", f"proje {proje_id}")
    eksik_txt = ", ".join(analiz.eksik) if analiz.eksik else "yok"
    notifier.notify(p.danisman_id, f"Yeni başvuru: {p.baslik}",
                    f"{ogrenci.ad_soyad} ({ogrenci.bolum or '-'}, GNO {ogrenci.gno or '-'}) projenize "
                    f"{'davetinizi kabul ederek ' if kaynak == 'davet' else ''}başvurdu.\n"
                    f"Yetkinlik uyumu: %{analiz.uyum_yuzde:g}. Başvurudan sonra ekipte kalacak eksik yetkinlikler: {eksik_txt}.\n"
                    "Danışman Onay ekranından kabul veya ret verebilirsiniz.")
    return Sonuc(True, f"Başvurunuz alındı. Yetkinlik uyumunuz %{analiz.uyum_yuzde:g}.", analiz)


def basvuru_geri_cek(basvuru_id: int, ogrenci_id: int) -> Sonuc:
    with get_session() as s:
        b = s.get(Basvuru, basvuru_id)
        if not b or b.ogrenci_id != ogrenci_id:
            return Sonuc(False, "Başvuru bulunamadı.")
        if b.durum == "Kabul":
            return Sonuc(False, "Kabul edilmiş başvuru için danışmanınızla görüşün.")
        b.durum = "Geri Cekildi"
    return Sonuc(True, "Başvuru geri çekildi.")


def _takim_senkron(proje_id: int) -> None:
    uyeler = rules.ekip_uyeleri(proje_id)
    with get_session() as s:
        t = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == proje_id))
        if t is None:
            t = TakimEslesmesi(proje_id=proje_id)
            s.add(t)
        t.ogrenci_id_listesi = uyeler
        if t.yurutucu_id not in uyeler:
            t.yurutucu_id = uyeler[0] if uyeler else None
        p = s.get(Proje, proje_id)
        if p.durum in ("Acik", "Dolu"):
            p.durum = "Dolu" if len(uyeler) >= p.max_ekip else "Acik"


def basvuru_karar(basvuru_id: int, kabul: bool, karar_veren_id: int, otomatik_davet_calistir: bool = True) -> Sonuc:
    with get_session() as s:
        b = s.get(Basvuru, basvuru_id)
        p = s.get(Proje, b.proje_id)
        ogr = s.get(Kullanici, b.ogrenci_id)
    if kabul:
        engeller = [k for k in rules.ogrenci_uygunlugu(ogr, p) if k.seviye == "hata"]
        if engeller:
            return Sonuc(False, " ".join(k.mesaj for k in engeller))
    with get_session() as s:
        b = s.get(Basvuru, basvuru_id)
        b.durum = "Kabul" if kabul else "Ret"
        b.karar_tarihi = now()
        if kabul and p.tur in rules.TUBITAK_TURLERI:
            # Tek başvuru kuralı: aynı dönemdeki diğer bekleyen 2209 başvuruları geri çekilir
            for diger in s.scalars(select(Basvuru).join(Proje, Proje.id == Basvuru.proje_id).where(
                    Basvuru.ogrenci_id == ogr.id, Basvuru.id != b.id, Basvuru.durum == "Beklemede",
                    Proje.tur.in_(rules.TUBITAK_TURLERI), Proje.donem == p.donem)):
                diger.durum = "Geri Cekildi"
    _takim_senkron(p.id)
    log_islem(karar_veren_id, "basvuru_karar", f"{basvuru_id} {'kabul' if kabul else 'ret'}")
    if kabul:
        notifier.notify(ogr, f"🎉 Ekibe kabul edildiniz: {p.baslik}",
                        f"Danışman, '{p.baslik}' projesine başvurunuzu kabul etti. Takım tamamlandığında danışman onayıyla "
                        "proje klasörü ve başvuru taslakları otomatik hazırlanacak.")
        davet_sayisi = otomatik_davet(p.id) if otomatik_davet_calistir and settings.get_bool("otomatik_davet") else 0
        ek = f" Eksik yetkinlikler için {davet_sayisi} öğrenciye otomatik davet gönderildi." if davet_sayisi else ""
        return Sonuc(True, f"{ogr.ad_soyad} ekibe eklendi.{ek}")
    notifier.notify(ogr, f"Başvuru sonucu: {p.baslik}",
                    f"'{p.baslik}' projesine başvurunuz bu kez olumlu sonuçlanmadı. Proje Panosu'nda size uygun diğer ilanları inceleyebilirsiniz.")
    return Sonuc(True, "Başvuru reddedildi.")


def otomatik_davet(proje_id: int) -> int:
    with get_session() as s:
        p = s.get(Proje, proje_id)
    if p.durum not in ("Acik",):
        return 0
    eksikler = matcher.ekip_eksikleri(p)
    if not eksikler:
        return 0
    uye_sayisi = len(rules.ekip_uyeleri(p.id))
    with get_session() as s:
        bekleyen = len(list(s.scalars(select(Davet.id).where(Davet.proje_id == p.id, Davet.durum == "Gonderildi"))))
    bos = max(0, p.max_ekip - uye_sayisi)
    kontenjan = max(0, bos * 2 - bekleyen)
    adaylar = matcher.aday_bul(p, eksikler)[:kontenjan]
    gonderilen = 0
    for a in adaylar:
        token = secrets.token_urlsafe(16)
        with get_session() as s:
            s.add(Davet(proje_id=p.id, ogrenci_id=a.ogrenci.id, yetkinlikler=a.kapsadigi, token=token))
        link = _app_url(f"?davet={token}")
        notifier.notify(a.ogrenci, f"Takım daveti: {p.baslik}",
                        f"Merhaba {a.ogrenci.ad_soyad},\n\n'{p.baslik}' ({p.tur}) projesinin ekibinde şu yetkinliklere ihtiyaç var: "
                        f"{', '.join(a.kapsadigi)}. Profilinizde bu yetkinlikler bulunduğu için sistem sizi önerdi.\n\n"
                        f"Daveti Profilim > Davetlerim bölümünden kabul veya ret edebilirsiniz."
                        + (f"\nDoğrudan bağlantı: {link}" if link else "")
                        + f"\n\nDavet {settings.get_int('davet_gecerlilik_gun')} gün geçerlidir.")
        gonderilen += 1
    if gonderilen:
        log_islem(None, "otomatik_davet", f"proje {p.id}: {gonderilen} davet")
    return gonderilen


def davet_yanitla(davet_id: int, ogrenci: Kullanici, kabul: bool) -> Sonuc:
    with get_session() as s:
        d = s.get(Davet, davet_id)
        if not d or d.ogrenci_id != ogrenci.id:
            return Sonuc(False, "Davet bulunamadı.")
        if d.durum != "Gonderildi":
            return Sonuc(False, "Bu davet artık geçerli değil.")
        if d.tarih < now() - dt.timedelta(days=settings.get_int("davet_gecerlilik_gun")):
            d.durum = "Suresi Doldu"
            return Sonuc(False, "Bu davetin süresi dolmuş.")
        proje_id = d.proje_id
    if kabul:
        res = basvuru_yap(ogrenci, proje_id, "Sistem davetini kabul etti.", kaynak="davet")
        if not res.ok:
            return res
    with get_session() as s:
        d = s.get(Davet, davet_id)
        d.durum, d.yanit_tarihi = ("Kabul" if kabul else "Ret"), now()
    return Sonuc(True, "Davet kabul edildi; danışman onayı bekleniyor." if kabul else "Davet reddedildi.")


def davet_token_bul(token: str) -> Davet | None:
    with get_session() as s:
        return s.scalar(select(Davet).where(Davet.token == token))


def davet_suresi_kontrol() -> int:
    sinir = now() - dt.timedelta(days=settings.get_int("davet_gecerlilik_gun"))
    with get_session() as s:
        eski = list(s.scalars(select(Davet).where(Davet.durum == "Gonderildi", Davet.tarih < sinir)))
        for d in eski:
            d.durum = "Suresi Doldu"
    return len(eski)


def yurutucu_ata(proje_id: int, ogrenci_id: int) -> None:
    with get_session() as s:
        t = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == proje_id))
        t.yurutucu_id = ogrenci_id


def uyeyi_cikar(proje_id: int, ogrenci_id: int, kullanici_id: int) -> None:
    with get_session() as s:
        b = s.scalar(select(Basvuru).where(Basvuru.proje_id == proje_id, Basvuru.ogrenci_id == ogrenci_id))
        if b:
            b.durum = "Geri Cekildi"
    _takim_senkron(proje_id)
    log_islem(kullanici_id, "uye_cikar", f"{proje_id}/{ogrenci_id}")


# ---------------------------------------------------------------------------
# Son tarihler
# ---------------------------------------------------------------------------
def yaklasan_son_tarihler(gun: int = 120, sadece_onlisans: bool = True) -> list[dict]:
    bugun = dt.date.today()
    sinir = bugun + dt.timedelta(days=gun)
    out = []
    with get_session() as s:
        for c in s.scalars(select(CagriTakvimi)):
            d = c.bitis.date()
            if bugun <= d <= sinir:
                out.append({"tur": "cagri", "id": c.id, "baslik": c.baslik, "program": c.program, "tarih": c.bitis,
                            "kalan": (d - bugun).days, "url": c.url, "hedef_rol": c.hedef_rol})
        q = select(TeknofestKategori).where(TeknofestKategori.aktif.is_(True), TeknofestKategori.son_basvuru_tarihi.is_not(None))
        for k in s.scalars(q):
            if sadece_onlisans and k.onlisans_uygun is False:
                continue
            if bugun <= k.son_basvuru_tarihi <= sinir:
                out.append({"tur": "teknofest", "id": k.id, "baslik": f"TEKNOFEST · {k.kategori_adi} son başvuru",
                            "program": "TEKNOFEST", "tarih": dt.datetime.combine(k.son_basvuru_tarihi, dt.time(23, 59)),
                            "kalan": (k.son_basvuru_tarihi - bugun).days, "url": k.url, "hedef_rol": "ilgili"})
    return sorted(out, key=lambda x: x["tarih"])


def _ilgili_kisiler(program: str, donem: str) -> set[int]:
    turler = rules.TUBITAK_TURLERI if program in ("2209", "2209-A/B") else {program}
    ids: set[int] = set()
    with get_session() as s:
        projeler = list(s.scalars(select(Proje).where(Proje.tur.in_(turler), Proje.donem == donem,
                                                      Proje.durum.in_(["Acik", "Dolu", "Onaylandi", "Basvuruldu"]))))
    for p in projeler:
        ids.update(rules.ekip_uyeleri(p.id))
        for x in (p.danisman_id, p.sanayi_danisman_id):
            if x:
                ids.add(x)
    return ids


def hatirlatmalari_gonder(bugun: dt.date | None = None) -> int:
    """Son tarihe 10 ve 3 gün (ayarlanabilir) kala ilgili kişilere bir kez hatırlatma gönderir."""
    bugun = bugun or dt.date.today()
    gunler = settings.hatirlatma_gunleri()
    donem = str(settings.get("aktif_donem"))
    gonderilen = 0
    for item in yaklasan_son_tarihler(gun=max(gunler) + 1, sadece_onlisans=False):
        kalan = (item["tarih"].date() - bugun).days
        uygun = [g for g in gunler if 0 <= kalan <= g]
        if not uygun:
            continue
        esik = min(uygun)
        alicilar: set[int] = set()
        if item["tur"] == "cagri":
            hedef = item.get("hedef_rol") or "ilgili"
            with get_session() as s:
                if hedef == "tum_ogrenciler":
                    alicilar = set(s.scalars(select(Kullanici.id).where(Kullanici.rol == "ogrenci", Kullanici.aktif.is_(True))))
                elif hedef == "hocalar":
                    alicilar = set(s.scalars(select(Kullanici.id).where(Kullanici.rol == "hoca", Kullanici.aktif.is_(True))))
                elif hedef == "herkes":
                    alicilar = set(s.scalars(select(Kullanici.id).where(Kullanici.aktif.is_(True))))
            if hedef == "ilgili":
                alicilar = _ilgili_kisiler(item["program"], donem)
        else:
            with get_session() as s:
                for p in s.scalars(select(Proje).where(Proje.eslesen_teknofest_kat_id == item["id"], Proje.durum.notin_(["Iptal", "Sonuclandi"]))):
                    alicilar.update(rules.ekip_uyeleri(p.id))
                    if p.danisman_id:
                        alicilar.add(p.danisman_id)
                for u in s.scalars(select(Kullanici).where(Kullanici.aktif.is_(True))):
                    if item["id"] in (u.takip_edilen_kategoriler or []):
                        alicilar.add(u.id)
        if not alicilar:
            continue
        tarih_txt = item["tarih"].strftime("%d.%m.%Y %H:%M")
        konu = f"⏰ {kalan} gün kaldı: {item['baslik']}" if kalan else f"⏰ BUGÜN son gün: {item['baslik']}"
        icerik = (f"{item['baslik']} için son tarih: {tarih_txt} ({kalan} gün kaldı).\n"
                  + (f"Ayrıntılar: {item['url']}\n" if item.get("url") else "")
                  + "Eksik belge veya onay adımlarınızı Proje Kuluçka sisteminden kontrol edin.")
        # Anahtar son tarihi de içerir: aynı kayıt/yarışma sonraki dönem yeni tarihle güncellendiğinde yine hatırlatılır
        anahtar = f"hatirlatma:{item['tur']}:{item['id']}:{item['tarih']:%Y%m%d}:{esik}"
        for uid in alicilar:
            if notifier.notify(uid, konu, icerik, anahtar=anahtar):
                gonderilen += 1
    if gonderilen:
        log_islem(None, "hatirlatma", f"{gonderilen} bildirim")
    return gonderilen


def ics_olustur(items: list[dict]) -> str:
    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Proje Kuluçka//TR", "CALSCALE:GREGORIAN"]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for it in items:
        d = it["tarih"]
        lines += [
            "BEGIN:VEVENT", f"UID:{it['tur']}-{it['id']}@proje-kulucka", f"DTSTAMP:{stamp}",
            f"DTSTART:{d.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{(d + dt.timedelta(minutes=30)).strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{esc(it['baslik'])}", f"DESCRIPTION:{esc(it.get('url') or '')}",
            "BEGIN:VALARM", "TRIGGER:-P3D", "ACTION:DISPLAY", f"DESCRIPTION:{esc(it['baslik'])}", "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


# ---------------------------------------------------------------------------
# 'Onayla ve Kur' otonom zinciri
# ---------------------------------------------------------------------------
def proje_baglami(proje_id: int) -> dict:
    with get_session() as s:
        p = s.get(Proje, proje_id)
        t = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == proje_id))
        uyeler = rules.ekip_uyeleri(proje_id)
        ekip_map = {u.id: u for u in s.scalars(select(Kullanici).where(Kullanici.id.in_(uyeler or [0])))}
        ekip = [ekip_map[i] for i in uyeler if i in ekip_map]
        danisman = s.get(Kullanici, p.danisman_id) if p.danisman_id else None
        sanayi = s.get(Kullanici, p.sanayi_danisman_id) if p.sanayi_danisman_id else None
        kategori = s.get(TeknofestKategori, p.eslesen_teknofest_kat_id) if p.eslesen_teknofest_kat_id else None
    if t and t.yurutucu_id in uyeler:
        ekip.sort(key=lambda u: 0 if u.id == t.yurutucu_id else 1)
    skor = None
    if kategori:
        skor = next((e["skor"] for e in (p.teknofest_eslesmeler or []) if e.get("kategori_id") == kategori.id), None)
    return {"proje": p, "takim": t, "ekip": ekip, "danisman": danisman, "sanayi": sanayi, "kategori": kategori, "skor": skor}


def on_kontrol(proje_id: int) -> list[rules.Kontrol]:
    b = proje_baglami(proje_id)
    if b["proje"].tur not in rules.TUBITAK_TURLERI:
        return []
    return rules.tubitak_on_kontrol(b["proje"], b["ekip"], b["danisman"], b["sanayi"])


def _ilgili_takvim(p: Proje, kategori: TeknofestKategori | None) -> list[dict]:
    items = []
    for it in yaklasan_son_tarihler(gun=365, sadece_onlisans=False):
        if it["tur"] == "cagri" and (it["program"] == p.tur or (it["program"] in ("2209", "2209-A/B") and p.tur in rules.TUBITAK_TURLERI)):
            items.append(it)
        elif it["tur"] == "teknofest" and kategori and it["id"] == kategori.id:
            items.append(it)
    if kategori:
        for row in kategori.takvim or []:
            try:
                d = dt.date.fromisoformat(row["tarih"])
            except (KeyError, ValueError):
                continue
            if d >= dt.date.today():
                items.append({"baslik": f"TEKNOFEST · {row.get('asama', '')}", "tarih": dt.datetime.combine(d, dt.time(17, 0)),
                              "kalan": (d - dt.date.today()).days})
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["tarih"]):
        key = (it["baslik"], it["tarih"].date())
        if key in seen:
            continue
        seen.add(key)
        out.append({"tarih": it["tarih"].strftime("%d.%m.%Y"), "baslik": it["baslik"], "kalan": f"{it['kalan']} gün"})
    return out[:12]


def onayla_ve_kur(proje_id: int, kullanici_id: int | None = None, zorla: bool = False) -> Sonuc:
    """Danışman onayıyla tetiklenen zincir.

    1) Kontroller  2) Proje klasörü (Drive/yerel) + alt klasörler  3) Şartname ve resmi rapor şablonlarını indir
    4) Word taslaklarını üret  5) Drive'a yükle ve ekip/danışmana 'Düzenleyen' yetkisi ver  6) Rehber ve bildirim gönder
    """
    adimlar: list[dict] = []

    def kaydet(adim: str, durum: str, mesaj: str = "") -> None:
        adimlar.append({"adim": adim, "durum": durum, "mesaj": mesaj, "zaman": now().strftime("%d.%m.%Y %H:%M:%S")})

    b = proje_baglami(proje_id)
    p, ekip, danisman, sanayi, kategori = b["proje"], b["ekip"], b["danisman"], b["sanayi"], b["kategori"]
    t = b["takim"]

    # 1) Kontroller
    if not ekip:
        return Sonuc(False, "Ekipte en az bir öğrenci olmalı.")
    if not danisman:
        return Sonuc(False, "Projeye danışman atanmamış.")
    kontroller = rules.tubitak_on_kontrol(p, ekip, danisman, sanayi) if p.tur in rules.TUBITAK_TURLERI else []
    yapisal = [k for k in kontroller if k.seviye == "hata" and k.alan in ("Ekip", "Danışman", "Sanayi danışmanı", "Proje süresi")]
    if yapisal and not zorla:
        return Sonuc(False, "Kurulum durduruldu: " + " ".join(k.mesaj for k in yapisal))
    if p.tur in rules.TUBITAK_TURLERI:
        uygun, sayi, limit = rules.kota_uygun_mu(danisman.id, p.tur, p.donem, haric_proje_id=p.id)
        if not uygun and not zorla:
            return Sonuc(False, f"Danışman kotası dolu ({sayi}/{limit}).")
    h, u, _ = rules.kontrol_ozeti(kontroller)
    kaydet("Ön kontrol", "tamam", f"{h} hata, {u} uyarı (içerik hataları taslakta [DOLDURULACAK] olarak işaretlendi)" if kontroller else "Uygulanmadı")

    # 2) Klasörler
    klasor_adi = f"{p.kod}_{safe_filename(p.baslik, 40)}"
    yerel = config.PROJECT_DIR / klasor_adi
    alt = {"tubitak": "01_TUBITAK_2209", "bitirme": "01_Bitirme", "teknofest": "02_TEKNOFEST", "sartname": "03_Sartname", "notlar": "04_Toplanti_Notlari"}
    secilen_alt = ["notlar"]
    if p.tur in rules.TUBITAK_TURLERI:
        secilen_alt.insert(0, "tubitak")
    if p.tur == "Bitirme":
        secilen_alt.insert(0, "bitirme")
    if kategori:
        secilen_alt += ["teknofest", "sartname"]
    for a in secilen_alt:
        (yerel / alt[a]).mkdir(parents=True, exist_ok=True)
    kaydet("Yerel proje klasörü", "tamam", str(yerel))

    storage = None
    drive_ids: dict[str, str] = {}
    drive_url = None
    if settings.get_bool("drive_aktif"):
        try:
            from .drive import GoogleDriveStorage
            storage = GoogleDriveStorage()
            if t and t.drive_klasor_id and not zorla:
                ana = {"id": t.drive_klasor_id, "url": t.drive_klasor_url}
            else:
                ana = storage.create_folder(klasor_adi)
            drive_url = ana["url"]
            drive_ids["ana"] = ana["id"]
            for a in secilen_alt:
                drive_ids[a] = storage.create_folder(alt[a], ana["id"])["id"]
            kaydet("Google Drive klasörü", "tamam", drive_url or ana["id"])
        except Exception as exc:  # noqa: BLE001
            storage = None
            kaydet("Google Drive klasörü", "hata", f"{exc} — yerel klasörle devam edildi.")
    else:
        kaydet("Google Drive klasörü", "atlandi", "Drive entegrasyonu kapalı; yerel klasör kullanıldı.")

    # 3) Şartname ve resmi şablonlar
    ek_dosyalar: list[tuple[str, str]] = []  # (alt_klasor, yol)
    if kategori:
        from . import teknofest_scraper
        try:
            yol = kategori.sartname_yerel_yol if kategori.sartname_yerel_yol and Path(kategori.sartname_yerel_yol).exists() else None
            if not yol and kategori.sartname_pdf_url:
                yol = teknofest_scraper.sartname_indir(kategori)
            if yol:
                hedef = yerel / alt["sartname"] / f"Sartname_{safe_filename(kategori.kategori_adi, 50)}.pdf"
                shutil.copy2(yol, hedef)
                ek_dosyalar.append(("sartname", str(hedef)))
                kaydet("Şartname PDF", "tamam", hedef.name)
            else:
                kaydet("Şartname PDF", "atlandi", "Yarışma için şartname bağlantısı henüz yok (tarama sonrası eklenecek).")
        except Exception as exc:  # noqa: BLE001
            kaydet("Şartname PDF", "hata", str(exc))
        for s in (kategori.rapor_sablonlari or [])[:5]:
            try:
                yol = teknofest_scraper.download_file(s["url"], yerel / alt["teknofest"])
                ek_dosyalar.append(("teknofest", yol))
                kaydet("Resmi rapor şablonu", "tamam", Path(yol).name)
            except Exception as exc:  # noqa: BLE001
                kaydet("Resmi rapor şablonu", "hata", f"{s.get('ad')}: {exc}")

    # 4) Word taslakları
    takvim = _ilgili_takvim(p, kategori)
    ctx = doc_generator.build_context(p, ekip, danisman, sanayi, t.yurutucu_id if t else None, kategori, b["skor"],
                                      klasor_url=drive_url or str(yerel), kontroller=kontroller, takvim=takvim)
    belgeler: list[dict] = []
    tubitak_yol = odr_yol = None
    try:
        if p.tur in rules.TUBITAK_TURLERI:
            tubitak_yol = doc_generator.render(p.tur, ctx, yerel / alt["tubitak"], doc_generator.dosya_adi(p, f"TUBITAK_{p.tur}_TYBS_Taslak"))
            belgeler.append({"ad": f"TÜBİTAK {p.tur} TYBS Hazırlık Taslağı", "tur": "tubitak", "yol": tubitak_yol, "alt": "tubitak"})
        if p.tur == "Bitirme":
            yol = doc_generator.render("Bitirme", ctx, yerel / alt["bitirme"], doc_generator.dosya_adi(p, "Bitirme_Oneri"))
            belgeler.append({"ad": "Bitirme Projesi Öneri Formu", "tur": "bitirme", "yol": yol, "alt": "bitirme"})
            tubitak_yol = yol
        if kategori:
            odr_yol = doc_generator.render("TEKNOFEST", ctx, yerel / alt["teknofest"], doc_generator.dosya_adi(p, "TEKNOFEST_ODR_Taslak"))
            belgeler.append({"ad": f"TEKNOFEST Rapor Taslağı ({kategori.kategori_adi})", "tur": "teknofest", "yol": odr_yol, "alt": "teknofest"})
        kontrol_yol = doc_generator.render("KONTROL", ctx, yerel, f"00_Basvuru_Kontrol_Listesi_{p.kod}.docx")
        belgeler.append({"ad": "Başvuru Kontrol Listesi ve Rehber", "tur": "kontrol", "yol": kontrol_yol, "alt": None})
        kaydet("Word taslakları", "tamam", ", ".join(Path(x["yol"]).name for x in belgeler))
    except Exception as exc:  # noqa: BLE001
        kaydet("Word taslakları", "hata", str(exc))
        log.exception("Belge üretimi başarısız")

    # 5) Drive'a yükleme ve paylaşım
    if storage:
        convert = settings.get_bool("drive_docs_donustur")
        for d in belgeler:
            try:
                parent = drive_ids.get(d["alt"] or "ana", drive_ids["ana"])
                up = storage.upload(d["yol"], parent, convert=convert and d["tur"] != "kontrol")
                d["drive_id"], d["drive_url"] = up["id"], up["url"]
            except Exception as exc:  # noqa: BLE001
                kaydet("Drive yükleme", "hata", f"{Path(d['yol']).name}: {exc}")
        for alt_ad, yol in ek_dosyalar:
            try:
                storage.upload(yol, drive_ids.get(alt_ad, drive_ids["ana"]))
            except Exception as exc:  # noqa: BLE001
                kaydet("Drive yükleme", "hata", f"{Path(yol).name}: {exc}")
        kaydet("Drive yükleme", "tamam", f"{len(belgeler) + len(ek_dosyalar)} dosya")
        paylasilan = 0
        for kisi in [danisman, sanayi, *ekip]:
            if not kisi or not kisi.eposta:
                continue
            try:
                storage.share(drive_ids["ana"], kisi.eposta, "writer")
                paylasilan += 1
            except Exception as exc:  # noqa: BLE001
                kaydet("Drive paylaşımı", "hata", f"{kisi.eposta}: {exc}")
        kaydet("Drive paylaşımı", "tamam", f"{paylasilan} kişiye 'Düzenleyen' yetkisi verildi")

    # 6) Kayıt ve bildirim
    with get_session() as s:
        t = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == proje_id))
        if t is None:
            t = TakimEslesmesi(proje_id=proje_id)
            s.add(t)
        t.ogrenci_id_listesi = [u.id for u in ekip]
        t.yurutucu_id = t.yurutucu_id or ekip[0].id
        hatali = any(a["durum"] == "hata" for a in adimlar if a["adim"] in ("Word taslakları",))
        t.onay_durumu = "Kısmen Kuruldu" if hatali else "Kuruldu"
        t.onay_tarihi = now()
        t.yerel_klasor = str(yerel)
        if drive_url:
            t.drive_klasor_url = drive_url
            t.drive_klasor_id = drive_ids.get("ana")
        t.tubitak_docx_yolu = tubitak_yol
        t.teknofest_odr_yolu = odr_yol
        t.belgeler = belgeler
        t.bos_alan_sayisi = sum(doc_generator.bos_alan_say(_belge_metni(d)) for d in belgeler if d["tur"] != "kontrol")
        pp = s.get(Proje, proje_id)
        if pp.durum in ("Acik", "Dolu", "Taslak"):
            pp.durum = "Onaylandi"

    rehber = str(settings.get("basvuru_rehberi") or "")
    belge_listesi = "\n".join(f"• {d['ad']}" + (f": {d['drive_url']}" if d.get("drive_url") else "") for d in belgeler)
    takvim_txt = "\n".join(f"• {x['tarih']} — {x['baslik']} ({x['kalan']})" for x in takvim[:6]) or "• Kayıtlı son tarih yok"
    icerik = (f"'{p.baslik}' ({p.tur}) projesi danışman tarafından onaylandı ve çalışma alanınız hazırlandı.\n\n"
              f"Proje klasörü: {drive_url or 'Sistemdeki proje sayfasından indirebilirsiniz.'}\n\nOluşturulan belgeler:\n{belge_listesi}\n\n"
              f"Yaklaşan son tarihler:\n{takvim_txt}\n\n"
              f"Taslaklarda [DOLDURULACAK] ile işaretli alanları ekip olarak tamamlayın.\n\n{rehber}")
    ekler = [d["yol"] for d in belgeler] if not drive_url else None
    alicilar = [x for x in [danisman, sanayi, *ekip] if x]
    for kisi in alicilar:
        notifier.notify(kisi, f"✅ Proje onaylandı ve kuruldu: {p.baslik}", icerik, anahtar=f"kurulum:{p.id}:{now():%Y%m%d%H%M}", ekler=ekler)
    kaydet("Bildirim ve ARBİS/TYBS rehberi", "tamam", f"{len(alicilar)} kişiye gönderildi")

    with get_session() as s:
        t = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == proje_id))
        t.otomasyon_log = (t.otomasyon_log or []) + adimlar
    log_islem(kullanici_id, "onayla_ve_kur", f"proje {proje_id}")
    hata_sayisi = sum(1 for a in adimlar if a["durum"] == "hata")
    return Sonuc(True, "Kurulum tamamlandı." if not hata_sayisi else f"Kurulum tamamlandı, {hata_sayisi} adımda uyarı var.", adimlar)


def _belge_metni(d: dict) -> str:
    try:
        if d.get("drive_id") and settings.get_bool("drive_aktif"):
            from .drive import GoogleDriveStorage
            return GoogleDriveStorage().export_text(d["drive_id"])
        from .drive import docx_text
        return docx_text(d["yol"])
    except Exception:  # noqa: BLE001
        return ""


def belge_guncelle(proje_id: int, belge_index: int, yuklenen: bytes, kullanici_id: int) -> Sonuc:
    """Ekibin düzenlediği taslağı (yerel modda) sisteme geri yükler."""
    with get_session() as s:
        t = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == proje_id))
        belgeler = list(t.belgeler or [])
        if belge_index >= len(belgeler):
            return Sonuc(False, "Belge bulunamadı.")
        yol = Path(belgeler[belge_index]["yol"])
        yedek = yol.with_name(yol.stem + f"_onceki_{now():%Y%m%d%H%M}.docx")
        if yol.exists():
            shutil.copy2(yol, yedek)
        yol.write_bytes(yuklenen)
        t.bos_alan_sayisi = sum(doc_generator.bos_alan_say(_belge_metni(d)) for d in belgeler if d["tur"] != "kontrol")
        kalan = t.bos_alan_sayisi
    log_islem(kullanici_id, "belge_guncelle", f"{proje_id}/{belge_index}")
    return Sonuc(True, f"Belge güncellendi. Kalan boş alan: {kalan}.")


def taslak_kontrolu() -> int:
    """Kurulumdan N gün sonra hâlâ [DOLDURULACAK] alanı kalan taslaklar için haftalık uyarı."""
    gun = settings.get_int("taslak_kontrol_gun")
    sinir = now() - dt.timedelta(days=gun)
    hafta = dt.date.today().isocalendar()
    anahtar_ek = f"{hafta[0]}-{hafta[1]}"
    gonderilen = 0
    with get_session() as s:
        takimlar = list(s.scalars(select(TakimEslesmesi).where(
            TakimEslesmesi.onay_durumu.in_(["Kuruldu", "Kısmen Kuruldu"]), TakimEslesmesi.onay_tarihi < sinir)))
    for t in takimlar:
        with get_session() as s:
            p = s.get(Proje, t.proje_id)
        if p.durum not in ("Onaylandi",):
            continue
        toplam = sum(doc_generator.bos_alan_say(_belge_metni(d)) for d in (t.belgeler or []) if d.get("tur") != "kontrol")
        with get_session() as s:
            tt = s.get(TakimEslesmesi, t.id)
            tt.bos_alan_sayisi = toplam
            tt.son_taslak_kontrol = now()
        if toplam <= 0:
            continue
        alicilar = list(t.ogrenci_id_listesi or []) + ([p.danisman_id] if p.danisman_id else [])
        for uid in alicilar:
            if notifier.notify(uid, f"📝 Taslakta {toplam} boş alan var: {p.baslik}",
                               f"'{p.baslik}' projesinin başvuru taslaklarında hâlâ {toplam} adet [DOLDURULACAK] alanı bulunuyor. "
                               "Son tarihten önce ekipçe tamamlayın.", anahtar=f"taslak:{p.id}:{anahtar_ek}"):
                gonderilen += 1
    return gonderilen


# ---------------------------------------------------------------------------
# Yardımcı sorgular (arayüz için)
# ---------------------------------------------------------------------------
def hoca_projeleri(hoca_id: int) -> list[Proje]:
    with get_session() as s:
        return list(s.scalars(select(Proje).where(or_(Proje.danisman_id == hoca_id, Proje.sanayi_danisman_id == hoca_id,
                                                      Proje.olusturan_id == hoca_id)).order_by(Proje.olusturma.desc())))


def proje_basvurulari(proje_id: int) -> list[tuple[Basvuru, Kullanici]]:
    with get_session() as s:
        rows = s.execute(select(Basvuru, Kullanici).join(Kullanici, Kullanici.id == Basvuru.ogrenci_id)
                         .where(Basvuru.proje_id == proje_id).order_by(Basvuru.tarih)).all()
        return [(b, u) for b, u in rows]


def ogrenci_projeleri(ogrenci_id: int) -> list[tuple[Basvuru, Proje]]:
    with get_session() as s:
        rows = s.execute(select(Basvuru, Proje).join(Proje, Proje.id == Basvuru.proje_id)
                         .where(Basvuru.ogrenci_id == ogrenci_id).order_by(Basvuru.tarih.desc())).all()
        return [(b, p) for b, p in rows]


def ogrenci_davetleri(ogrenci_id: int) -> list[tuple[Davet, Proje]]:
    with get_session() as s:
        rows = s.execute(select(Davet, Proje).join(Proje, Proje.id == Davet.proje_id)
                         .where(Davet.ogrenci_id == ogrenci_id).order_by(Davet.tarih.desc())).all()
        return [(d, p) for d, p in rows]
