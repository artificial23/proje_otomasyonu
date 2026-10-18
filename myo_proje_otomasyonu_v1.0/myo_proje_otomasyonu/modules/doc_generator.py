"""docxtpl ile Word (.docx) taslak üretimi."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from docxtpl import DocxTemplate

from . import config, rules, settings
from .database import Kullanici, Proje, TeknofestKategori
from .text_utils import safe_filename, word_count

BOS = "[DOLDURULACAK"

SABLONLAR = {
    "2209-A": "tubitak_2209a_sablon.docx",
    "2209-B": "tubitak_2209b_sablon.docx",
    "Bitirme": "bitirme_oneri_sablon.docx",
    "TEKNOFEST": "teknofest_odr_sablon.docx",
    "KONTROL": "kontrol_listesi_sablon.docx",
}

SABLON_DEGISKENLERI = {
    "Genel": "kurum_adi, universite_adi, donem, tarih, proje_kodu, baslik, tur, bolum, sure_ay, anahtar_kelimeler, "
             "danisman, danisman_eposta, sanayi_danismani, sanayi_kurulus, yurutucu, ortaklar, klasor_url, etik_kurul",
    "Metin bölümleri": "ozet, ozet_kelime, konu_onemi, amac_hedefler, yenilikci_yon, yontem, arastirma_olanaklari, "
                       "yaygin_etki, diger_konular, kaynaklar, problem, cozum, uygulanabilirlik, hedef_kitle",
    "TEKNOFEST": "yarisma_adi, yarisma_url, son_basvuru, katilim_seviyesi, sezon, takim_adi, uyum_skoru, teknofest_onerisi",
    "Bütçe": "butce_toplam, butce_limit, butce (liste: kalem, tur, adet, birim, tutar, gerekce)",
    "Tablolar (satır döngüsü)": "is_plani (no, is_paketi, sorumlu, aylar, basari_olcutu, katki), katki_toplam, "
                                "gantt (no, a1…a12), risk_plani (no, risk, b_plani), ekip (ad, rol, bolum, yetkinlik, arbis), "
                                "kontroller (durum, alan, mesaj), takvim (tarih, baslik, kalan), adimlar (kutu, adim, sorumlu), "
                                "rehber_satirlari",
}


def template_path(kind: str) -> Path:
    name = SABLONLAR[kind]
    custom = config.CUSTOM_TEMPLATE_DIR / name
    return custom if custom.exists() else config.TEMPLATE_DIR / name


def _fill(value: str | None, label: str, min_chars: int = 0) -> str:
    v = (value or "").strip()
    if not v:
        return f"[DOLDURULACAK: {label}]"
    if min_chars and len(v) < min_chars:
        return v + f"\n[DOLDURULACAK: {label} — şu an {len(v)} karakter, en az {min_chars} olmalı]"
    return v


def _tl(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_context(proje: Proje, ekip: list[Kullanici], danisman: Kullanici | None,
                  sanayi: Kullanici | None = None, yurutucu_id: int | None = None,
                  kategori: TeknofestKategori | None = None, uyum_skoru: float | None = None,
                  klasor_url: str = "", kontroller: list | None = None, takvim: list[dict] | None = None) -> dict:
    tarih = dt.date.today().strftime("%d.%m.%Y")
    yurutucu = next((u for u in ekip if u.id == yurutucu_id), ekip[0] if ekip else None)
    ortaklar = [u for u in ekip if not yurutucu or u.id != yurutucu.id]
    is_plani = proje.is_plani or rules.varsayilan_is_plani(proje.sure_ay, [u.ad_soyad for u in ekip])
    risk_plani = proje.risk_plani or rules.varsayilan_risk_plani()
    butce_rows, toplam = [], 0.0
    for b in proje.butce or []:
        tutar = float(b.get("tutar") or 0)
        toplam += tutar
        butce_rows.append({"kalem": b.get("kalem", ""), "tur": b.get("tur", ""), "adet": b.get("adet", ""),
                           "birim": _tl(float(b.get("birim_fiyat") or 0)) if b.get("birim_fiyat") else "",
                           "tutar": _tl(tutar), "gerekce": b.get("gerekce", "")})
    if not butce_rows:
        butce_rows = [{"kalem": "[DOLDURULACAK: bütçe kalemleri]", "tur": "", "adet": "", "birim": "", "tutar": "", "gerekce": ""}]
    limit_key = "butce_limit_2209b" if proje.tur == "2209-B" else "butce_limit_2209a"

    def ad(u: Kullanici | None, unvan: bool = False) -> str:
        if not u:
            return "[DOLDURULACAK]"
        if unvan and u.unvan and not u.ad_soyad.startswith(u.unvan):
            return f"{u.unvan} {u.ad_soyad}"
        return u.ad_soyad

    ekip_rows = []
    for u in ekip:
        rol = "Proje Yürütücüsü" if yurutucu and u.id == yurutucu.id else "Proje Ortağı"
        if proje.tur not in rules.TUBITAK_TURLERI:
            rol = "Takım Kaptanı" if yurutucu and u.id == yurutucu.id else "Üye"
        ekip_rows.append({"ad": u.ad_soyad, "rol": rol, "bolum": u.bolum or "", "yetkinlik": ", ".join(u.yetkinlikler or []),
                          "arbis": "✓" if u.arbis_kaydi else "—"})
    if danisman:
        ekip_rows.append({"ad": ad(danisman, True), "rol": "Akademik Danışman", "bolum": danisman.bolum or "",
                          "yetkinlik": ", ".join(danisman.yetkinlikler or []), "arbis": "✓" if danisman.arbis_kaydi else "—"})
    if sanayi:
        ekip_rows.append({"ad": sanayi.ad_soyad, "rol": "Sanayi Danışmanı", "bolum": sanayi.kurum or "",
                          "yetkinlik": ", ".join(sanayi.yetkinlikler or []), "arbis": "✓" if sanayi.arbis_kaydi else "—"})

    plan_rows, gantt = [], []
    for i, p in enumerate(is_plani, start=1):
        bas, bit = int(p.get("baslangic_ay") or 1), int(p.get("bitis_ay") or 1)
        sorumlu = str(p.get("sorumlu") or "")
        if sorumlu in ("", "Proje ekibi") and ekip:
            sorumlu = ekip[(i - 1) % len(ekip)].ad_soyad  # iş-zaman çizelgesi sorumlularını ekibe dağıt
        plan_rows.append({"no": i, "is_paketi": p.get("is_paketi", ""), "sorumlu": sorumlu,
                          "aylar": f"{bas}–{bit}" if bit != bas else str(bas), "basari_olcutu": p.get("basari_olcutu", ""),
                          "katki": f"%{float(p.get('katki_yuzde') or 0):g}"})
        g = {"no": i}
        for m in range(1, 13):
            g[f"a{m}"] = "■" if bas <= m <= bit else ""
        gantt.append(g)
    katki_toplam = sum(float(p.get("katki_yuzde") or 0) for p in is_plani)

    eslesmeler = proje.teknofest_eslesmeler or []
    tf_onerisi = "; ".join(f"{e['kategori_adi']} (%{e['skor']})" for e in eslesmeler) or "Uygun kategori bulunamadı"

    kontrol_rows = [{"durum": {"hata": "HATA", "uyari": "UYARI", "tamam": "TAMAM"}[k.seviye], "alan": k.alan, "mesaj": k.mesaj}
                    for k in (kontroller or [])] or [{"durum": "—", "alan": "—", "mesaj": "Bu proje türü için TÜBİTAK ön kontrolü uygulanmaz."}]

    rehber = [ln.replace("**", "").replace("### ", "").replace("> ", "").strip() for ln in str(settings.get("basvuru_rehberi") or "").splitlines()]
    rehber = [ln for ln in rehber if ln]

    adimlar = []
    if proje.tur in rules.TUBITAK_TURLERI:
        adimlar = [
            ("Tüm ekip ve danışman ARBİS kaydını güncelledi (arbis.tubitak.gov.tr)", "Tüm ekip"),
            ("Danışmanın YÖKSİS kaydı güncel", ad(danisman)),
            ("TYBS Hazırlık Taslağındaki tüm [DOLDURULACAK] alanları tamamlandı", "Tüm ekip"),
            ("Otomatik ön kontroldeki HATA satırları giderildi", ad(yurutucu)),
            ("Başvuru TYBS'den gönderildi (tybs.tubitak.gov.tr)", ad(yurutucu)),
            ("Danışman TYBS üzerinden onay verdi", ad(danisman)),
            ("Kurum yetkilisi e-imzası takip edildi (eimza.tubitak.gov.tr)", ad(danisman)),
        ]
        if proje.tur == "2209-B":
            adimlar.append(("Destek kararı sonrası sanayi onay yazısı hazırlanacak", ad(sanayi) if sanayi else (proje.sanayi_kurulus or "Sanayi danışmanı")))
        if proje.etik_kurul_gerekli:
            adimlar.append(("Etik kurul onayı / muafiyet belgesi alındı", ad(danisman)))
    if kategori:
        adimlar += [
            (f"TEKNOFEST şartnamesi ekipçe okundu ({kategori.kategori_adi})", "Tüm ekip"),
            ("TEKNOFEST takım başvurusu yapıldı, üyeler ve danışman eklendi", ad(yurutucu)),
            ("Ön Değerlendirme / Proje Detay Raporu resmi şablona aktarıldı ve yüklendi", ad(yurutucu)),
        ]
    if proje.tur == "Bitirme":
        adimlar += [("Öneri formu danışmanla gözden geçirildi", "Tüm ekip"), ("Öneri formu imzalanıp bölüme teslim edildi", ad(yurutucu))]

    problem = proje.konu_onemi if proje.tur != "2209-B" else proje.amac_hedefler
    return {
        "kurum_adi": settings.get("kurum_adi") or "",
        "universite_adi": settings.get("universite_adi") or "",
        "donem": proje.donem or settings.get("aktif_donem"),
        "tarih": tarih,
        "proje_kodu": proje.kod or f"P{proje.id}",
        "baslik": proje.baslik,
        "tur": proje.tur,
        "bolum": (danisman.bolum if danisman else "") or "",
        "sure_ay": proje.sure_ay,
        "anahtar_kelimeler": _fill(proje.anahtar_kelimeler, "3–5 anahtar kelime"),
        "danisman": ad(danisman, True),
        "danisman_eposta": danisman.eposta if danisman else "",
        "sanayi_danismani": ad(sanayi) if sanayi else (_fill("", "sanayi danışmanı adı") if proje.tur == "2209-B" else "—"),
        "sanayi_kurulus": proje.sanayi_kurulus or (sanayi.kurum if sanayi else "") or ("[DOLDURULACAK: sanayi kuruluşu]" if proje.tur == "2209-B" else "—"),
        "yurutucu": ad(yurutucu) if yurutucu else "[DOLDURULACAK: proje yürütücüsü]",
        "ortaklar": ", ".join(u.ad_soyad for u in ortaklar) or "—",
        "klasor_url": klasor_url or "—",
        "etik_kurul": "Gerekli (bilimsel değerlendirme sonrası belge yüklenecek)" if proje.etik_kurul_gerekli else "Gerekli değil",
        "ozet": _fill(proje.ozet, "Özet (25–450 kelime)"),
        "ozet_kelime": word_count(proje.ozet),
        "konu_onemi": _fill(proje.konu_onemi, "Konunun önemi ve bilimsel niteliği", 350),
        "amac_hedefler": _fill(proje.amac_hedefler, "Amaç ve hedefler", 350),
        "yenilikci_yon": _fill(proje.yenilikci_yon, "Yenilikçi yönü ve teknolojik değeri", 350 if proje.tur == "2209-B" else 0),
        "yontem": _fill(proje.yontem, "Yöntem", 350),
        "arastirma_olanaklari": _fill(proje.arastirma_olanaklari, "Kullanılacak laboratuvar, atölye ve ekipmanlar"),
        "yaygin_etki": _fill(proje.yaygin_etki, "Beklenen çıktılar ve yaygın etki"),
        "diger_konular": (proje.diger_konular or "").strip() or "—",
        "kaynaklar": _fill(proje.kaynaklar, "Kaynaklar (DOI'si olanlarda DOI zorunlu)"),
        "problem": _fill(problem, "Çözülmek istenen problem"),
        "cozum": _fill(proje.amac_hedefler, "Önerilen çözüm"),
        "uygulanabilirlik": _fill("", "Uygulanabilirlik ve ticarileşme potansiyeli"),
        "hedef_kitle": _fill("", "Projenin hedef kitlesi"),
        "yarisma_adi": kategori.kategori_adi if kategori else "[DOLDURULACAK: yarışma]",
        "yarisma_url": (kategori.url or "") if kategori else "",
        "son_basvuru": kategori.son_basvuru_tarihi.strftime("%d.%m.%Y") if kategori and kategori.son_basvuru_tarihi else "Yarışma sayfasından kontrol edin",
        "katilim_seviyesi": (kategori.katilim_seviyesi if kategori else "") or "—",
        "sezon": (kategori.sezon if kategori and kategori.sezon else str(dt.date.today().year + (1 if dt.date.today().month >= 9 else 0))),
        "takim_adi": _fill("", "takım adı"),
        "uyum_skoru": f"{uyum_skoru:g}" if uyum_skoru is not None else "—",
        "teknofest_onerisi": tf_onerisi,
        "butce": butce_rows,
        "butce_toplam": _tl(toplam),
        "butce_limit": _tl(settings.get_float(limit_key)),
        "is_plani": plan_rows,
        "katki_toplam": f"%{katki_toplam:g}",
        "gantt": gantt,
        "risk_plani": [{"no": r.get("is_paketi_no", ""), "risk": r.get("risk", ""), "b_plani": r.get("b_plani", "")} for r in risk_plani],
        "ekip": ekip_rows,
        "kontroller": kontrol_rows,
        "takvim": takvim or [{"tarih": "—", "baslik": "Kayıtlı son tarih yok", "kalan": ""}],
        "adimlar": [{"kutu": "☐", "adim": a, "sorumlu": s} for a, s in adimlar] or [{"kutu": "☐", "adim": "Danışmanla ilk toplantı", "sorumlu": "Tüm ekip"}],
        "rehber_satirlari": rehber,
    }


def render(kind: str, context: dict, out_dir: Path, filename: str) -> str:
    tpl = DocxTemplate(str(template_path(kind)))
    tpl.render(context, autoescape=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    tpl.save(str(path))
    return str(path)


def dosya_adi(proje: Proje, ek: str) -> str:
    return f"{proje.kod or 'P' + str(proje.id)}_{ek}_{safe_filename(proje.baslik, 40)}.docx"


def bos_alan_say(text: str) -> int:
    return text.count(BOS)


def validate_template(path: str) -> tuple[bool, str]:
    """Yüklenen özel şablonun örnek bağlamla işlenebildiğini kontrol eder."""
    try:
        tpl = DocxTemplate(path)
        missing = tpl.get_undeclared_template_variables()
        return True, ", ".join(sorted(missing)) if missing else ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
