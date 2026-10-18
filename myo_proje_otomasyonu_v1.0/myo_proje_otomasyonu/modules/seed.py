"""İlk kurulum verileri ve isteğe bağlı demo verisi.

* TEKNOFEST yarışma listesi: teknofest.org/tr/yarismalar sayfasındaki yarışma adları ve
  bağlantıları (Ekim 2026). Tarih, ödül ve şartname bilgileri ilk taramada doldurulur.
  Anahtar kelimeler, çapraz eşleştirmenin tarama öncesinde de çalışabilmesi için eklenmiştir.
* TÜBİTAK 2209-A/B 2026 çağrı tarihleri (tubitak.gov.tr, Ekim 2026).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from .database import CagriTakvimi, OdulluProje, TeknofestKategori, get_session
from .text_utils import slugify

TF = "https://www.teknofest.org/tr/yarismalar/"

# (ad, anahtar kelimeler, ön lisans uygunluğu: True/False/None=tarama bekleniyor)
TEKNOFEST_YARISMALARI: list[tuple[str, str, bool | None]] = [
    ("5G & Yapay Zeka ile Akıllı Yol Güvenliği Yarışması", "5G haberleşme yapay zeka trafik yol güvenliği akıllı ulaşım kamera görüntü işleme sensör kaza tespiti", None),
    ("Biyoteknoloji İnovasyon Yarışması", "biyoteknoloji biyoloji genetik mikroorganizma biyomalzeme laboratuvar sağlık gıda", None),
    ("Blokzincir Yarışması", "blokzincir blockchain akıllı sözleşme dağıtık defter yazılım güvenlik web", None),
    ("Çip Tasarım Yarışması", "çip tasarımı entegre devre VLSI FPGA Verilog VHDL RISC-V işlemci sayısal elektronik", None),
    ("Dikey İnişli Roket Yarışması", "roket dikey iniş itki vektör kontrol aviyonik gömülü sistem motor", None),
    ("E-Ticaret Yarışması", "e-ticaret web mobil uygulama dijital pazarlama girişim yazılım", None),
    ("Yapay Zeka Destekli Lojistik Anahat Optimizasyonu Yarışması", "lojistik rota optimizasyon yapay zeka algoritma tedarik zinciri veri analizi", None),
    ("Finansal Teknolojiler Yarışması", "fintek finans ödeme sistemleri yazılım mobil bankacılık veri analizi", None),
    ("Hareketli Uydu Terminali Yarışması", "uydu haberleşme anten RF terminal mobil platform sinyal takip elektronik", None),
    ("Havacılıkta Yapay Zeka Yarışması", "havacılık yapay zeka görüntü işleme nesne tespiti derin öğrenme veri seti", None),
    ("Çelikkubbe Hava Savunma Sistemleri Yarışması", "hava savunma hedef tespit takip radar kamera görüntü işleme otonom gömülü", None),
    ("Hyperloop Geliştirme Yarışması", "hyperloop manyetik levitasyon kapsül ulaşım motor kontrol mekanik tasarım", None),
    ("İnsansız Deniz Aracı Yarışması", "insansız deniz aracı otonom tekne navigasyon GPS sensör motor kontrol gömülü sistem", None),
    ("İnsansız Kara Aracı Yarışması", "insansız kara aracı otonom robot navigasyon lidar kamera motor sürücü ROS gömülü sistem", None),
    ("İnsansız Su Altı Sistemleri Yarışması", "su altı aracı ROV otonom sızdırmazlık itici motor kamera görüntü işleme", None),
    ("İnsansız Su Altı Sistemleri Yıldızlar Yarışması", "su altı aracı ROV itici motor kamera", None),
    ("Jet Motor Tasarım Yarışması", "jet motoru türbin tasarım termodinamik akışkanlar mekanik CAD imalat", None),
    ("Kuantum Teknolojileri Yarışması", "kuantum hesaplama algoritma fizik yazılım şifreleme", None),
    ("Liseler Arası İnsansız Hava Araçları Yarışması", "lise İHA", False),
    ("Lise Öğrencileri İklim Değişikliği Araştırma Projeleri Yarışması", "lise iklim", False),
    ("Lise Öğrencileri Kutup Araştırma Projeleri Yarışması", "lise kutup", False),
    ("Model Uydu Yarışması", "model uydu yer istasyonu telemetri gömülü sistem sensör paraşüt haberleşme", None),
    ("Nükleer Enerji Teknolojileri Tasarım Yarışması", "nükleer enerji reaktör tasarım simülasyon", None),
    ("Onkolojide 3T Yarışması", "onkoloji kanser sağlık tıbbi cihaz teşhis tedavi biyomedikal", None),
    ("Pardus Hata Yakalama ve Öneri Yarışması", "Pardus Linux açık kaynak yazılım hata tespiti test işletim sistemi", None),
    ("Robotaksi-Binek Otonom Araç Yarışması", "otonom araç sürücüsüz şerit takibi görüntü işleme lidar elektrikli araç ROS", None),
    ("Roket Yarışması", "roket aviyonik kurtarma paraşüt itki yapısal tasarım uçuş bilgisayarı telemetri", None),
    ("Sağlıkta Yapay Zeka Yarışması", "sağlık yapay zeka tıbbi görüntü derin öğrenme teşhis veri seti", None),
    ("Sanayide Robotik Uygulamalar Yarışması", "sanayi robotik endüstriyel otomasyon PLC fabrika üretim hattı konveyör kalite kontrol akıllı fabrika endüstri 4.0 otonom mobil robot forklift lojistik QR kod okuma çizgi izleme haritalama", None),
    ("Sürü İHA Yarışması", "sürü İHA drone otonom uçuş koordinasyon yazılım haberleşme", None),
    ("Savaşan İHA Yıldızlar Yarışması", "İHA otonom uçuş görüntü işleme", None),
    ("Savaşan İHA Yarışması", "savaşan İHA otonom uçuş sabit kanat görüntü işleme hedef kilitlenme otopilot telemetri", None),
    ("Savaşan İHA Avcı Drone Yarışması", "avcı drone multikopter hedef takip görüntü işleme otonom", None),
    ("Su Altı Roket Yarışması", "su altı roket itki hidrodinamik tasarım", None),
    ("Tarım Teknolojileri Yarışması", "tarım teknolojileri akıllı tarım sensör sulama IoT ürün verim toprak sera", None),
    ("TEKNOFEST Drone Şampiyonası", "drone yarışı FPV pilotaj multikopter", None),
    ("TEKNOFEST Mimari ve Görsel Tasarım Yarışması", "mimari tasarım görsel tasarım yapı modelleme", None),
    ("TEKNOFEST Robolig Yarışması", "robot lig mobil robot otonom gömülü", None),
    ("World Drone Cup", "drone yarışı FPV", None),
    ("İnsanlık Yararına Teknolojiler Yarışması - İlkokul Seviyesi", "ilkokul", False),
    ("İnsanlık Yararına Teknolojiler Yarışması - Ortaokul Seviyesi", "ortaokul", False),
    ("İnsanlık Yararına Teknolojiler Yarışması - Lise Seviyesi", "lise", False),
    ("Uluslararası Elektrikli Araç Yarışları", "elektrikli araç batarya BMS motor sürücü şasi verimlilik enerji yönetimi hidromobil", None),
    ("Uluslararası İnsansız Hava Aracı Yarışması", "İHA otonom uçuş uluslararası", None),
    ("Üniversite Öğrencileri Araştırma Proje Yarışmaları", "araştırma projesi üniversite öğrencileri bilimsel araştırma TÜBİTAK 2209 yenilikçi proje", True),
    ("Yapay Zeka Dil Ajanları Yarışması", "yapay zeka dil modeli ajan doğal dil işleme Türkçe", None),
    ("Yapay Zeka Destekli Havayolu Optimizasyonu Yarışması", "havayolu optimizasyon yapay zeka planlama", None),
    ("TÜBA-TEKNOFEST Doktora Bilim Ödülleri", "doktora", False),
    ("Sıfır Atık & Döngüsel Ekonomi Yarışması", "sıfır atık geri dönüşüm döngüsel ekonomi çevre sürdürülebilirlik", None),
    ("TEKNOFEST Yapay Zeka Film Yarışması", "yapay zeka film video üretimi", None),
    ("TEKNOFEST Mesleki Yetenek Yarışması", "mesleki yetenek meslek yüksekokulu beceri teknik uygulama kaynak CNC elektrik tesisat mekatronik", None),
    ("NSOSYAL İnovasyon Yarışması", "sosyal medya inovasyon yazılım", None),
    ("HackMasters Güneydoğu", "hackathon yazılım siber güvenlik", None),
    ("İleri Otonom Sistemler Tasarım ve Operasyon Yarışması", "otonom sistemler tasarım operasyon robot İHA kara aracı", None),
    ("Mavi Vatan Resim Yarışması", "resim sanat deniz", None),
    ("KÜRE TEKNOFEST Güneydoğu Madde Yazım Yarışması", "ansiklopedi madde yazımı içerik", None),
    ("Bağımlılıklarla Mücadelede Teknolojik Uygulamalar Yarışması", "bağımlılık sağlık mobil uygulama farkındalık yazılım", None),
    ("FPV Drone İzleme (Tracking) Yarışması", "FPV drone takip görüntü işleme", None),
    ("KÜRE TEKNOFEST Mavi Vatan Madde Yazım Yarışması", "ansiklopedi madde yazımı içerik deniz", None),
    ("Elektronik Harp Yarışması", "elektronik harp RF sinyal radar haberleşme SDR", None),
    ("Maden Teknolojileri Yarışması", "maden teknolojileri madencilik sensör otomasyon güvenlik", None),
]

CAGRILAR_2026 = [
    {"baslik": "TÜBİTAK 2209-A/B 2026 — Başvuru ve danışman onayı son günü (17:30)", "program": "2209-A/B",
     "baslangic": dt.datetime(2026, 10, 7, 9, 0), "bitis": dt.datetime(2026, 11, 11, 17, 30),
     "url": "https://tybs.tubitak.gov.tr", "aciklama": "Başvurular TYBS üzerinden yapılır; danışman onayı da bu tarihe kadar verilmelidir."},
    {"baslik": "TÜBİTAK 2209-A/B 2026 — Kurum yetkilisi e-imza son günü", "program": "2209-A/B",
     "baslangic": dt.datetime(2026, 11, 16, 9, 0), "bitis": dt.datetime(2026, 11, 23, 17, 30),
     "url": "https://eimza.tubitak.gov.tr", "aciklama": "Kurum yetkilisi e-imzası atılmayan başvurular geçersiz sayılır."},
]


def seed_defaults() -> dict:
    out = {"teknofest": 0, "cagri": 0}
    with get_session() as s:
        if s.scalar(select(func.count()).select_from(TeknofestKategori)) == 0:
            for ad, kelimeler, uygun in TEKNOFEST_YARISMALARI:
                slug = slugify(ad)
                s.add(TeknofestKategori(kategori_adi=ad, slug=slug, url=TF + slug + "/", anahtar_kelimeler=kelimeler,
                                        onlisans_uygun=uygun, kaynak="seed",
                                        katilim_seviyesi="" if uygun is None else ("Üniversite" if uygun else "Ön lisans dışı")))
                out["teknofest"] += 1
        if s.scalar(select(func.count()).select_from(CagriTakvimi)) == 0:
            for c in CAGRILAR_2026:
                s.add(CagriTakvimi(kaynak="seed", hedef_rol="ilgili", **c))
                out["cagri"] += 1
    return out


def seed_demo() -> dict:
    """Arayüzü denemek için açıkça 'DEMO' etiketli örnek kullanıcılar ve projeler."""
    from . import automation, auth
    from .database import Kullanici

    sifre = "Demo1234"
    kisiler = [
        dict(ad_soyad="Demo Danışman", eposta="hoca@demo.local", rol="hoca", unvan="Dr. Öğr. Üyesi",
             bolum="Mekatronik", yetkinlikler=["PLC (Siemens TIA Portal)", "Robotik (ROS)", "MATLAB / Simulink"], arbis_kaydi=True, yoksis_guncel=True),
        dict(ad_soyad="Demo Danışman 2", eposta="hoca2@demo.local", rol="hoca", unvan="Öğr. Gör.",
             bolum="Elektronik Teknolojisi", yetkinlikler=["Gömülü Sistemler (STM32/ESP32)", "PCB Tasarımı (KiCad/Altium)"], arbis_kaydi=True, yoksis_guncel=True),
        dict(ad_soyad="Demo Sanayi Temsilcisi", eposta="sanayi@demo.local", rol="sanayi", kurum="Demo Otomasyon A.Ş.",
             yetkinlikler=["Endüstriyel Otomasyon", "SCADA / HMI"]),
        dict(ad_soyad="Demo Öğrenci Ayşe", eposta="ayse@demo.local", rol="ogrenci", bolum="Mekatronik", sinif="2", gno=3.21,
             ogrenim_turu="Örgün Öğretim", yetkinlikler=["SolidWorks", "Arduino", "3D Yazıcı / Hızlı Prototipleme"], arbis_kaydi=True),
        dict(ad_soyad="Demo Öğrenci Mehmet", eposta="mehmet@demo.local", rol="ogrenci", bolum="Kontrol ve Otomasyon Teknolojisi", sinif="2",
             gno=2.95, ogrenim_turu="Örgün Öğretim", yetkinlikler=["PLC (Siemens TIA Portal)", "Pnömatik / Hidrolik", "SCADA / HMI"]),
        dict(ad_soyad="Demo Öğrenci Zeynep", eposta="zeynep@demo.local", rol="ogrenci", bolum="Bilgisayar Programcılığı", sinif="2",
             gno=3.48, ogrenim_turu="Örgün Öğretim", yetkinlikler=["Python", "Görüntü İşleme (OpenCV)", "Yapay Zeka / Makine Öğrenmesi"]),
        dict(ad_soyad="Demo Öğrenci Can", eposta="can@demo.local", rol="ogrenci", bolum="Elektronik Teknolojisi", sinif="1",
             gno=2.70, ogrenim_turu="İkinci Öğretim", yetkinlikler=["Elektronik Devre Tasarımı", "Gömülü Sistemler (STM32/ESP32)", "Python"]),
        dict(ad_soyad="Demo Öğrenci Elif", eposta="elif@demo.local", rol="ogrenci", bolum="Makine", sinif="2", gno=3.05,
             ogrenim_turu="Örgün Öğretim", yetkinlikler=["AutoCAD", "CNC Programlama", "SolidWorks"]),
    ]
    users = {}
    with get_session() as s:
        for k in kisiler:
            u = s.scalar(select(Kullanici).where(Kullanici.eposta == k["eposta"]))
            if not u:
                u = Kullanici(**k, sifre_hash=auth.hash_password(sifre), kvkk_onay=True, aktif=True)
                s.add(u)
                s.flush()
            users[k["eposta"].split("@")[0]] = u.id
    from .database import Proje
    with get_session() as s:
        var = s.scalar(select(func.count()).select_from(Proje))
    if var:
        return {"kullanici": len(users), "proje": 0, "sifre": sifre}
    with get_session() as s:
        hoca = s.get(Kullanici, users["hoca"])
        sanayi = s.get(Kullanici, users["sanayi"])
    r1 = automation.proje_olustur({
        "baslik": "PLC kontrollü otonom konveyör hattında görüntü işleme ile hatalı ürün ayıklama",
        "tur": "2209-A",
        "ozet": ("Bu projede küçük ölçekli üretim hatlarında hatalı ürünlerin insan gözüyle ayıklanmasından kaynaklanan "
                 "zaman kaybını azaltmak amacıyla PLC kontrollü bir konveyör üzerinde kamera tabanlı görüntü işleme sistemi "
                 "geliştirilecektir. Ürün görüntüleri OpenCV ile işlenecek, hatalı ürünler pnömatik itici ile hattan ayrılacaktır. "
                 "Prototip MYO atölyesinde kurulacak ve doğruluk, hız ve maliyet ölçütleriyle değerlendirilecektir."),
        "anahtar_kelimeler": "PLC, görüntü işleme, konveyör, kalite kontrol, otomasyon",
        "aranan_yetkinlikler": ["PLC (Siemens TIA Portal)", "Görüntü İşleme (OpenCV)", "SolidWorks", "Pnömatik / Hidrolik"],
        "sure_ay": 10,
        "butce": [{"kalem": "Endüstriyel kamera", "tur": "Makine-Teçhizat", "adet": 1, "birim_fiyat": 4500, "tutar": 4500, "gerekce": "Ürün görüntüsü alımı"},
                  {"kalem": "Pnömatik silindir ve valf", "tur": "Sarf Malzeme", "adet": 2, "birim_fiyat": 1250, "tutar": 2500, "gerekce": "Ayıklama mekanizması"}],
    }, hoca)
    automation.proje_olustur({
        "baslik": "Sera ortamı için IoT tabanlı akıllı sulama ve iklim izleme sistemi",
        "tur": "2209-B", "sanayi_danisman_id": sanayi.id, "sanayi_kurulus": sanayi.kurum, "danisman_id": hoca.id,
        "ozet": "Seralarda toprak nemi, sıcaklık ve nem verilerini ESP32 tabanlı sensör düğümleriyle toplayıp bulut panelinde izleyen ve sulamayı otomatik yöneten sistem.",
        "anahtar_kelimeler": "IoT, akıllı tarım, sulama, sensör, ESP32",
        "aranan_yetkinlikler": ["Gömülü Sistemler (STM32/ESP32)", "IoT", "Web Geliştirme", "Elektronik Devre Tasarımı"],
    }, sanayi)
    automation.proje_olustur({
        "baslik": "Otonom mobil robot ile atölye içi malzeme taşıma",
        "tur": "Bitirme", "danisman_id": users["hoca2"],
        "ozet": "Çizgi izleme ve QR kod okuma ile atölye istasyonları arasında malzeme taşıyan, engel algılayınca güvenli duran mobil robot.",
        "anahtar_kelimeler": "mobil robot, otonom, QR kod, çizgi izleme",
        "aranan_yetkinlikler": ["Arduino", "SolidWorks", "Python"],
    }, _get_user(users["hoca2"]))
    # Demo ekip: Ayşe ve Mehmet ilk projeye kabul
    p1 = r1.veri
    for key in ("ayse", "mehmet"):
        res = automation.basvuru_yap(_get_user(users[key]), p1.id, "Demo başvuru")
        if res.ok:
            with get_session() as s:
                from .database import Basvuru
                b = s.scalar(select(Basvuru).where(Basvuru.proje_id == p1.id, Basvuru.ogrenci_id == users[key]))
            automation.basvuru_karar(b.id, True, users["hoca"], otomatik_davet_calistir=(key == "mehmet"))
    with get_session() as s:
        for row in [
            dict(proje_adi="DEMO — Atölye için düşük maliyetli CNC lazer kesici", takim_adi="Demo Takım A", yil=2025, program="2209-A",
                 kategori_adi="TÜBİTAK 2209-A", derece="Destek Kazandı", kurum_adi="Demo MYO",
                 proje_ozeti="Örnek kayıt (gerçek değildir): Arduino ve GRBL ile çalışan, atölye eğitimleri için düşük maliyetli lazer kesici.",
                 kullanilan_teknolojiler=["Arduino", "SolidWorks", "CNC Programlama"], kaynak="DEMO"),
            dict(proje_adi="DEMO — Güneş takip sistemli şarj istasyonu", takim_adi="Demo Takım B", yil=2024, program="Bitirme",
                 kategori_adi="Bitirme", derece="Bölüm Birincisi", kurum_adi="Demo MYO",
                 proje_ozeti="Örnek kayıt (gerçek değildir): Çift eksenli güneş takip sistemiyle verimi artırılmış kampüs şarj istasyonu.",
                 kullanilan_teknolojiler=["Yenilenebilir Enerji / Güneş", "Elektronik Devre Tasarımı"], kaynak="DEMO"),
        ]:
            s.add(OdulluProje(**row))
    return {"kullanici": len(users), "proje": 3, "sifre": sifre}


def _get_user(uid: int):
    from .database import Kullanici
    with get_session() as s:
        return s.get(Kullanici, uid)


def remove_demo() -> dict:
    """@demo.local kullanıcılarını, onların projelerini ve DEMO arşiv kayıtlarını siler."""
    import shutil

    from . import config
    from .database import Basvuru, Bildirim, Davet, Kullanici, Oturum, Proje, TakimEslesmesi

    with get_session() as s:
        demo_ids = list(s.scalars(select(Kullanici.id).where(Kullanici.eposta.like("%@demo.local"))))
        if not demo_ids:
            n_arsiv = 0
            for o in s.scalars(select(OdulluProje).where(OdulluProje.kaynak == "DEMO")):
                s.delete(o)
                n_arsiv += 1
            return {"kullanici": 0, "proje": 0, "arsiv": n_arsiv}
        projeler = list(s.scalars(select(Proje).where(
            (Proje.danisman_id.in_(demo_ids)) | (Proje.olusturan_id.in_(demo_ids)) | (Proje.sanayi_danisman_id.in_(demo_ids)))))
        pids = [p.id for p in projeler]
        kodlar = [p.kod for p in projeler if p.kod]
        for model, col in ((Basvuru, Basvuru.proje_id), (Davet, Davet.proje_id), (TakimEslesmesi, TakimEslesmesi.proje_id)):
            for row in s.scalars(select(model).where(col.in_(pids or [0]))):
                s.delete(row)
        for model, col in ((Basvuru, Basvuru.ogrenci_id), (Davet, Davet.ogrenci_id), (Bildirim, Bildirim.kullanici_id),
                           (Oturum, Oturum.kullanici_id)):
            for row in s.scalars(select(model).where(col.in_(demo_ids))):
                s.delete(row)
        for o in s.scalars(select(OdulluProje).where((OdulluProje.kaynak == "DEMO") | (OdulluProje.kaynak_proje_id.in_(pids or [0])))):
            s.delete(o)
        s.flush()
        for p in projeler:
            s.delete(p)
        s.flush()
        for uid in demo_ids:
            s.delete(s.get(Kullanici, uid))
    for kod in kodlar:
        for klasor in config.PROJECT_DIR.glob(f"{kod}_*"):
            shutil.rmtree(klasor, ignore_errors=True)
    return {"kullanici": len(demo_ids), "proje": len(pids)}
