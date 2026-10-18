"""Uçtan uca testler: python -m pytest -q"""
import datetime as dt
import io
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from conftest import FIXTURES
from modules import (
    auth, automation, config, doc_generator, importer, matcher, notifier, rules, settings, teknofest_scraper, text_utils,
)
from modules.database import (
    Basvuru, Bildirim, CagriTakvimi, Davet, Kullanici, OdulluProje, Proje, TakimEslesmesi, TeknofestKategori, get_session,
)

_sayac = [0]


def kisi(rol="ogrenci", yetkinlikler=(), **kw):
    _sayac[0] += 1
    user, err = auth.register_user(ad_soyad=kw.pop("ad", f"Test {rol} {_sayac[0]}"), eposta=f"{rol}{_sayac[0]}@test.edu.tr",
                                   sifre="Sifre1234", rol=rol, aktif=True, kvkk_onay=True, yetkinlikler=list(yetkinlikler),
                                   ogrenim_turu=kw.pop("ogrenim_turu", "Örgün Öğretim" if rol == "ogrenci" else None), **kw)
    assert err is None, err
    return user


OZET = ("Bu projede küçük ölçekli üretim hatlarında hatalı ürünlerin ayıklanması için PLC kontrollü bir konveyör üzerinde kamera "
        "tabanlı görüntü işleme sistemi geliştirilecek ve prototip atölyede test edilecektir.")


# ---------------------------------------------------------------------------
def test_metin_ve_yetkinlik():
    assert text_utils.skill_key("PLC (Siemens TIA Portal)") == text_utils.skill_key("tia portal") == "plc"
    assert text_utils.skill_key("Yapay Zeka / Makine Öğrenmesi") == text_utils.skill_key("makine öğrenmesi")
    assert text_utils.slugify("Sıfır Atık & Döngüsel Ekonomi Yarışması") == "sifir-atik-dongusel-ekonomi-yarismasi"
    assert "otono" in text_utils.tokenize("Otonom İnsansız Kara Aracı ve")
    a = matcher.yetkinlik_analizi(["PLC", "SolidWorks", "Python"], ["plc (siemens tia portal)"], ["Python"])
    assert a.uyum_yuzde == 33.3 and a.eksik == ["SolidWorks"] and a.ogrencinin_katkisi == ["PLC"]


def test_kimlik_dogrulama_ve_oturum():
    u = kisi()
    assert auth.authenticate(u.eposta, "Sifre1234").id == u.id
    assert auth.authenticate(u.eposta, "yanlis") is None
    assert auth.password_problem("kisa") and auth.password_problem("sadeceharf") and not auth.password_problem("Abc12345")
    _, err = auth.register_user(ad_soyad="x", eposta=u.eposta, sifre="Sifre1234", rol="ogrenci")
    assert "zaten" in err
    settings.save("izinli_eposta_alanlari", "ogr.ornek.edu.tr")
    _, err = auth.register_user(ad_soyad="x", eposta="a@gmail.com", sifre="Sifre1234", rol="ogrenci")
    assert err and "alan adı" in err
    ok, err = auth.register_user(ad_soyad="x", eposta="b@ogr.ornek.edu.tr", sifre="Sifre1234", rol="ogrenci")
    assert err is None
    settings.save("izinli_eposta_alanlari", "")
    tok = auth.create_session(u.id)
    assert auth.user_from_session(tok) == u.id
    auth.end_session(tok)
    assert auth.user_from_session(tok) is None
    usr, kod = auth.start_reset(u.eposta)
    assert auth.finish_reset(u.eposta, "000000" if kod != "000000" else "111111", "YeniSifre1") is not None
    assert auth.finish_reset(u.eposta, kod, "YeniSifre1") is None
    assert auth.authenticate(u.eposta, "YeniSifre1")


def test_kota_yedek_havuz_ve_terfi():
    hoca = kisi("hoca")
    limit = settings.get_int("max_kota_2209")
    projeler = []
    for i in range(limit):
        r = automation.proje_olustur({"baslik": f"Kota projesi {i}", "tur": "2209-A", "ozet": OZET, "aranan_yetkinlikler": ["PLC"]}, hoca)
        assert r.ok and r.veri.durum == "Acik"
        projeler.append(r.veri)
    r = automation.proje_olustur({"baslik": "Fazla proje", "tur": "2209-B", "ozet": OZET, "aranan_yetkinlikler": ["PLC"],
                                  "sanayi_kurulus": "Firma"}, hoca)
    assert r.veri.durum == "Yedek Havuz"
    # Bitirme kotası ayrı sayılır
    r2 = automation.proje_olustur({"baslik": "Bitirme", "tur": "Bitirme", "ozet": OZET, "aranan_yetkinlikler": ["PLC"]}, hoca)
    assert r2.veri.durum == "Acik"
    automation.proje_durum_degistir(projeler[0].id, "Iptal")
    with get_session() as s:
        assert s.get(Proje, r.veri.id).durum == "Acik"


def test_2209b_ayni_danisman_engeli():
    hoca = kisi("hoca")
    r = automation.proje_olustur({"baslik": "B", "tur": "2209-B", "ozet": OZET, "aranan_yetkinlikler": ["PLC"],
                                  "danisman_id": hoca.id, "sanayi_danisman_id": hoca.id}, hoca)
    assert not r.ok


def test_basvuru_davet_ve_kurulum_zinciri():
    hoca = kisi("hoca", ["PLC"], unvan="Öğr. Gör.", yoksis_guncel=True, arbis_kaydi=True)
    a = kisi(yetkinlikler=["PLC (Siemens TIA Portal)"], arbis_kaydi=True)
    b = kisi(yetkinlikler=["Görüntü İşleme (OpenCV)", "Python"])
    acik_ogr = kisi(yetkinlikler=["SolidWorks"], ogrenim_turu="Açık Öğretim")
    c = kisi(yetkinlikler=["SolidWorks"])
    r = automation.proje_olustur({"baslik": "PLC kontrollü konveyörde görüntü işleme ile hatalı ürün ayıklama", "tur": "2209-A",
                                  "ozet": OZET, "anahtar_kelimeler": "PLC, görüntü işleme, konveyör, kalite kontrol",
                                  "aranan_yetkinlikler": ["PLC (Siemens TIA Portal)", "Görüntü İşleme (OpenCV)", "SolidWorks"]}, hoca)
    p = r.veri
    assert p.kod.startswith("A")
    assert p.teknofest_eslesmeler and p.teknofest_eslesmeler[0]["kategori_adi"] == "Sanayide Robotik Uygulamalar Yarışması"
    assert p.is_plani and sum(x["katki_yuzde"] for x in p.is_plani) == 100

    res = automation.basvuru_yap(a, p.id, "İsterim")
    assert res.ok
    assert not automation.basvuru_yap(a, p.id).ok  # tekrar başvuru
    with get_session() as s:
        ba = s.scalar(select(Basvuru).where(Basvuru.proje_id == p.id, Basvuru.ogrenci_id == a.id))
    res = automation.basvuru_karar(ba.id, True, hoca.id)
    assert res.ok and "davet" in res.mesaj
    with get_session() as s:
        davetler = list(s.scalars(select(Davet).where(Davet.proje_id == p.id)))
    davetli = {d.ogrenci_id for d in davetler}
    assert b.id in davetli and c.id in davetli and acik_ogr.id not in davetli  # açık öğretim davet edilmez

    # Açık öğretim öğrencisi 2209'a başvuramaz
    assert not automation.basvuru_yap(acik_ogr, p.id).ok

    d_b = next(d for d in davetler if d.ogrenci_id == b.id)
    assert automation.davet_yanitla(d_b.id, b, True).ok
    with get_session() as s:
        bb = s.scalar(select(Basvuru).where(Basvuru.proje_id == p.id, Basvuru.ogrenci_id == b.id))
    assert bb.kaynak == "davet" and bb.durum == "Beklemede"
    assert automation.basvuru_karar(bb.id, True, hoca.id).ok
    assert rules.ekip_uyeleri(p.id) == [a.id, b.id]

    # Tek başvuru kuralı: a başka bir 2209 projesine kabul edilemez
    hoca2 = kisi("hoca")
    p2 = automation.proje_olustur({"baslik": "Başka", "tur": "2209-A", "ozet": OZET, "aranan_yetkinlikler": ["PLC"]}, hoca2).veri
    assert not automation.basvuru_yap(a, p2.id).ok

    # Ön kontrol: boş bölümler hata verir
    kontroller = automation.on_kontrol(p.id)
    alanlar = {k.alan for k in kontroller if k.seviye == "hata"}
    assert "2. Yöntem" in alanlar

    # İçerik doldurulunca hatalar azalır
    uzun = "Bu bölüm ölçülebilir hedefler içerir. " * 12
    automation.proje_guncelle(p.id, {"konu_onemi": uzun, "amac_hedefler": uzun, "yontem": uzun,
                                     "butce": [{"kalem": "Kamera", "tur": "Makine-Teçhizat", "adet": 1, "birim_fiyat": 13000, "tutar": 13000}]})
    hatalar = {k.alan: k.mesaj for k in automation.on_kontrol(p.id) if k.seviye == "hata"}
    assert "2. Yöntem" not in hatalar and "Bütçe" in hatalar  # 13.000 > 12.000

    # Yasak iş adımı ve katkı toplamı
    automation.proje_guncelle(p.id, {"is_plani": [{"is_paketi": "Literatür taraması", "baslangic_ay": 1, "bitis_ay": 2,
                                                    "basari_olcutu": "%100", "katki_yuzde": 50}]})
    hatalar = [k.alan for k in automation.on_kontrol(p.id) if k.seviye == "hata"]
    assert "3.1 İş adımı" in hatalar and "3.1 Başarı ölçütü toplamı" in hatalar
    automation.proje_guncelle(p.id, {"is_plani": rules.varsayilan_is_plani(10), "butce": []})

    # Onayla ve Kur
    sonuc = automation.onayla_ve_kur(p.id, hoca.id)
    assert sonuc.ok, sonuc.mesaj
    with get_session() as s:
        t = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == p.id))
        pp = s.get(Proje, p.id)
    assert t.onay_durumu == "Kuruldu" and pp.durum == "Onaylandi"
    turler = {d["tur"] for d in t.belgeler}
    assert {"tubitak", "teknofest", "kontrol"} <= turler
    for d in t.belgeler:
        assert Path(d["yol"]).exists()
    assert t.bos_alan_sayisi and t.bos_alan_sayisi > 0
    from modules.drive import docx_text
    tub = docx_text(t.tubitak_docx_yolu)
    assert "PLC kontrollü konveyörde" in tub and "YÖNTEM" in tub and "[DOLDURULACAK" in tub and "{{" not in tub
    odr = docx_text(t.teknofest_odr_yolu)
    assert "Sanayide Robotik Uygulamalar" in odr
    with get_session() as s:
        bild = list(s.scalars(select(Bildirim).where(Bildirim.kullanici_id == a.id, Bildirim.konu.like("%kuruldu%"))))
    assert bild and any(x.kanal == "eposta" and x.durum == "Simule" for x in bild)

    # Düzenlenmiş belge yükleme boş alan sayısını günceller
    from docx import Document
    doc = Document()
    doc.add_paragraph("Tamamlandı")
    buf = io.BytesIO()
    doc.save(buf)
    i = next(i for i, d in enumerate(t.belgeler) if d["tur"] == "tubitak")
    assert automation.belge_guncelle(p.id, i, buf.getvalue(), hoca.id).ok

    # Sonuç -> arşiv geri beslemesi
    automation.sonuc_guncelle(p.id, "Kabul", "", hoca.id)
    with get_session() as s:
        arsiv = s.scalar(select(OdulluProje).where(OdulluProje.kaynak_proje_id == p.id))
    assert arsiv and arsiv.derece == "Destek Kazandı" and "PLC" in " ".join(arsiv.kullanilan_teknolojiler)


def test_hatirlatma_bir_kez_gonderilir():
    hoca = kisi("hoca")
    o = kisi(yetkinlikler=["PLC"])
    p = automation.proje_olustur({"baslik": "Hatırlatma testi", "tur": "Bitirme", "ozet": OZET, "aranan_yetkinlikler": ["PLC"]}, hoca).veri
    b = automation.basvuru_yap(o, p.id)
    with get_session() as s:
        ba = s.scalar(select(Basvuru).where(Basvuru.proje_id == p.id))
        s.add(CagriTakvimi(baslik="Bitirme öneri teslimi", program="Bitirme", bitis=dt.datetime.now() + dt.timedelta(days=9, hours=2)))
    automation.basvuru_karar(ba.id, True, hoca.id, otomatik_davet_calistir=False)
    n1 = automation.hatirlatmalari_gonder()
    n2 = automation.hatirlatmalari_gonder()
    assert n1 >= 2 and n2 == 0  # öğrenci + danışman, ikinci çalıştırmada tekrar yok
    # 3 gün kala yeni hatırlatma
    n3 = automation.hatirlatmalari_gonder(bugun=dt.date.today() + dt.timedelta(days=7))
    assert n3 >= 2
    ics = automation.ics_olustur(automation.yaklasan_son_tarihler())
    assert "BEGIN:VEVENT" in ics and "Bitirme" in ics


def test_kazici_ayristirma():
    liste = teknofest_scraper.parse_listing((FIXTURES / "liste.html").read_text(encoding="utf-8"), "https://www.teknofest.org/tr/yarismalar/")
    sluglar = {x["slug"]: x for x in liste}
    assert set(sluglar) == {"sanayide-robotik-uygulamalar-yarismasi", "liseler-arasi-insansiz-hava-araclari-yarismasi", "yeni-test-yarismasi"}
    assert sluglar["sanayide-robotik-uygulamalar-yarismasi"]["ad"] == "Sanayide Robotik Uygulamalar Yarışması"
    d = teknofest_scraper.parse_detail((FIXTURES / "detay.html").read_text(encoding="utf-8"),
                                       "https://www.teknofest.org/tr/yarismalar/sanayide-robotik-uygulamalar-yarismasi/")
    assert d["kategori_adi"] == "Sanayide Robotik Uygulamalar Yarışması"
    assert d["onlisans_uygun"] is True and "Üniversite" in d["katilim_seviyesi"]
    assert d["son_basvuru_tarihi"] == dt.date(2026, 5, 31)
    assert d["sezon"] == "2026" and len(d["takvim"]) == 3
    assert d["sartname_pdf_url"].endswith("2026_SRUY_TR_Hre2P.pdf")
    assert d["rapor_sablonlari"] and d["rapor_sablonlari"][0]["url"].endswith(".docx")
    assert d["odul_miktari"].startswith("Birinci: 250.000 TL")
    assert (d["takim_min"], d["takim_max"]) == (3, 15)
    assert len(d["dereceler"]) == 3
    assert any(r["takim_adi"] == "Batarya" and r["kurum_adi"] == "Örnek Üniversitesi" and r["yil"] == 2024 for r in d["dereceler"])
    kat, yeni = teknofest_scraper.save_category(d, "sanayide-robotik-uygulamalar-yarismasi", "https://x")
    assert not yeni and kat.son_basvuru_tarihi == dt.date(2026, 5, 31)
    with get_session() as s:
        k = s.get(TeknofestKategori, kat.id)
        assert "forklift" in k.anahtar_kelimeler  # seed anahtar kelimeleri korunur
    assert teknofest_scraper.save_dereceler(d["dereceler"], kat.id) == 3
    assert teknofest_scraper.save_dereceler(d["dereceler"], kat.id) == 0
    assert teknofest_scraper.detect_levels("Yarışmaya lise öğrencileri katılabilir")[1] is False
    assert teknofest_scraper.detect_levels("Ön lisans ve lisans öğrencileri")[1] is True


def test_belge_sablonlari_ozel_karakter():
    hoca = kisi("hoca")
    p = automation.proje_olustur({"baslik": "R&D <test> \"tırnak\"", "tur": "2209-B", "ozet": "satır1\nsatır2 & özel",
                                  "aranan_yetkinlikler": ["X"], "sanayi_kurulus": "A&B Ltd."}, hoca).veri
    ctx = doc_generator.build_context(p, [], hoca)
    for tur in ("2209-A", "2209-B", "Bitirme", "TEKNOFEST", "KONTROL"):
        out = doc_generator.render(tur, ctx, config.DATA_DIR / "test_belgeler", f"{tur}.docx")
        from modules.drive import docx_text
        txt = docx_text(out)
        assert "{{" not in txt and "{%" not in txt
    assert "R&D <test>" in docx_text(out)


def test_excel_ice_aktarma():
    ornek = importer.ornek_excel("kullanici")
    df = pd.read_excel(io.BytesIO(ornek))
    df["eposta"] = ["ice1@test.edu.tr", "ice2@test.edu.tr"]
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    buf.name = "k.xlsx"
    sonuc, hatalar = importer.kullanicilari_ice_aktar(buf)
    assert len(sonuc) == 2 and not hatalar
    u = auth.authenticate("ice1@test.edu.tr", sonuc.iloc[0]["gecici_sifre"])
    assert u and u.sifre_degismeli and u.yetkinlikler == ["SolidWorks", "Arduino", "Python"]
    rapor = importer.tum_veriyi_disa_aktar()
    xl = pd.ExcelFile(io.BytesIO(rapor))
    assert "Projeler" in xl.sheet_names and "sifre_hash" not in pd.read_excel(xl, "Kullanicilar").columns


def test_bildirim_tekillestirme():
    u = kisi()
    assert notifier.notify(u, "Konu", "İçerik", anahtar="tek")
    assert not notifier.notify(u, "Konu", "İçerik", anahtar="tek")
    assert notifier.okunmamis_sayisi(u.id) == 1


def test_hatali_giris_kilidi():
    import pytest
    u = kisi()
    for _ in range(auth.MAX_DENEME):
        assert auth.authenticate(u.eposta, "yanlis1234") is None
    with pytest.raises(auth.HesapKilitli):
        auth.authenticate(u.eposta, "Sifre1234")  # doğru şifre de kilit süresince reddedilir
    with get_session() as s:
        s.get(Kullanici, u.id).kilit_bitis = None
    assert auth.authenticate(u.eposta, "Sifre1234").id == u.id


def test_davet_suresi_yanitta_kontrol_edilir():
    hoca = kisi("hoca")
    o = kisi(yetkinlikler=["Python"])
    p = automation.proje_olustur({"baslik": "Süre testi", "tur": "Bitirme", "ozet": OZET, "aranan_yetkinlikler": ["Python"]}, hoca).veri
    with get_session() as s:
        d = Davet(proje_id=p.id, ogrenci_id=o.id, yetkinlikler=["Python"], token="eski-davet-token",
                  tarih=dt.datetime.now() - dt.timedelta(days=60))
        s.add(d)
        s.flush()
        did = d.id
    assert not automation.davet_yanitla(did, o, True).ok
