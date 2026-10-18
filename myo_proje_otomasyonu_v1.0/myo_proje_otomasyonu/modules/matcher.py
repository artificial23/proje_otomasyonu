"""Eşleştirme motoru.

* Yetkinlik kesişimi: Eksik = Aranan − (Ekip ∪ Başvuran) yetkinlikleri
* 2209 → TEKNOFEST çapraz eşleştirme: TF-IDF + kosinüs benzerliği
* Benzer proje uyarısı: aynı yöntemle mevcut projelerle karşılaştırma
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from . import settings
from .database import Basvuru, Davet, Kullanici, Proje, TeknofestKategori, get_session
from .rules import TUBITAK_TURLERI, ogrencinin_aktif_2209_projesi, ekip_uyeleri
from .text_utils import skill_key, skill_set, tokenize

try:  # scikit-learn yoksa saf Python yedeği kullanılır
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN = True
except Exception:  # pragma: no cover
    _SKLEARN = False


# ---------------------------------------------------------------------------
# Yetkinlik kesişimi
# ---------------------------------------------------------------------------
@dataclass
class YetkinlikSonucu:
    uyum_yuzde: float
    karsilanan: list[str]
    eksik: list[str]
    ogrencinin_katkisi: list[str] = field(default_factory=list)


def yetkinlik_analizi(aranan: list[str], ogrenci_yetkinlikleri: list[str], ekip_yetkinlikleri: list[str] | None = None) -> YetkinlikSonucu:
    aranan_map = skill_set(aranan)
    ogr = set(skill_set(ogrenci_yetkinlikleri))
    ekip = set(skill_set(ekip_yetkinlikleri or []))
    if not aranan_map:
        return YetkinlikSonucu(100.0, [], [], [])
    karsilanan_ogr = [aranan_map[k] for k in aranan_map if k in ogr]
    eksik = [aranan_map[k] for k in aranan_map if k not in ogr and k not in ekip]
    katkı = [aranan_map[k] for k in aranan_map if k in ogr and k not in ekip]
    uyum = 100.0 * len(karsilanan_ogr) / len(aranan_map)
    return YetkinlikSonucu(round(uyum, 1), karsilanan_ogr, eksik, katkı)


def ekip_yetkinlikleri(proje_id: int) -> list[str]:
    uyeler = ekip_uyeleri(proje_id)
    if not uyeler:
        return []
    with get_session() as s:
        out: list[str] = []
        for u in s.scalars(select(Kullanici).where(Kullanici.id.in_(uyeler))):
            out.extend(u.yetkinlikler or [])
        return out


def ekip_eksikleri(proje: Proje) -> list[str]:
    ekip = set(skill_set(ekip_yetkinlikleri(proje.id)))
    aranan = skill_set(proje.aranan_yetkinlikler)
    return [ad for k, ad in aranan.items() if k not in ekip]


@dataclass
class Aday:
    ogrenci: Kullanici
    kapsadigi: list[str]
    puan: float


def aday_bul(proje: Proje, eksikler: list[str], limit: int | None = None) -> list[Aday]:
    """Eksik yetkinliklere sahip, davet edilebilir öğrencileri sıralar."""
    if not eksikler:
        return []
    limit = limit or settings.get_int("davet_aday_sayisi")
    eksik_keys = {skill_key(e): e for e in eksikler}
    uyeler = set(ekip_uyeleri(proje.id))
    with get_session() as s:
        davetliler = set(s.scalars(select(Davet.ogrenci_id).where(Davet.proje_id == proje.id)))
        basvuranlar = set(s.scalars(select(Basvuru.ogrenci_id).where(Basvuru.proje_id == proje.id)))
        ogrenciler = list(s.scalars(select(Kullanici).where(
            Kullanici.rol == "ogrenci", Kullanici.aktif.is_(True), Kullanici.davet_almak_istiyor.is_(True))))
    adaylar: list[Aday] = []
    for o in ogrenciler:
        if o.id in uyeler or o.id in davetliler or o.id in basvuranlar:
            continue
        if proje.tur in TUBITAK_TURLERI:
            if (o.ogrenim_turu or "") in {"Açık Öğretim", "Hazırlık Sınıfı"}:
                continue
            if ogrencinin_aktif_2209_projesi(o.id, proje.donem):
                continue
        min_gno = settings.get_float("min_gno")
        if min_gno and (o.gno or 0) < min_gno:
            continue
        sahip = set(skill_set(o.yetkinlikler))
        kapsadigi = [ad for k, ad in eksik_keys.items() if k in sahip]
        if not kapsadigi:
            continue
        puan = len(kapsadigi) * 10 + (o.gno or 0)
        adaylar.append(Aday(o, kapsadigi, puan))
    adaylar.sort(key=lambda a: a.puan, reverse=True)
    # Her eksik yetkinlik için en fazla `limit` aday
    secilen: list[Aday] = []
    sayac = {e: 0 for e in eksikler}
    for a in adaylar:
        if any(sayac[e] < limit for e in a.kapsadigi):
            secilen.append(a)
            for e in a.kapsadigi:
                sayac[e] += 1
    return secilen


# ---------------------------------------------------------------------------
# TF-IDF benzerliği
# ---------------------------------------------------------------------------
def _analyzer(text: str) -> list[str]:
    toks = tokenize(text)
    # iki kelimelik öbekler de eklenir (ör. "insan kara")
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]


def _similarities(query: str, docs: list[str]) -> list[float]:
    if not docs or not query.strip():
        return [0.0] * len(docs)
    if _SKLEARN:
        vec = TfidfVectorizer(analyzer=_analyzer, sublinear_tf=True)
        try:
            matrix = vec.fit_transform(docs + [query])
        except ValueError:  # boş sözlük
            return [0.0] * len(docs)
        sims = cosine_similarity(matrix[-1], matrix[:-1])[0]
        return [float(x) for x in sims]
    # --- saf Python yedeği ---
    import math
    from collections import Counter
    corpus = [Counter(_analyzer(d)) for d in docs + [query]]
    df = Counter(t for c in corpus for t in c)
    n = len(corpus)

    def vec(c):
        return {t: (1 + math.log(f)) * (math.log((1 + n) / (1 + df[t])) + 1) for t, f in c.items()}

    vecs = [vec(c) for c in corpus]
    q = vecs[-1]
    qn = math.sqrt(sum(v * v for v in q.values())) or 1
    out = []
    for d in vecs[:-1]:
        dn = math.sqrt(sum(v * v for v in d.values())) or 1
        out.append(sum(q.get(t, 0) * v for t, v in d.items()) / (qn * dn))
    return out


def kategori_metni(k: TeknofestKategori) -> str:
    # Kategori adı ve anahtar kelimeler daha belirleyici olduğu için ağırlıklandırılır
    return " ".join([k.kategori_adi] * 2 + [k.anahtar_kelimeler or ""] * 2 + [(k.aciklama or "")[:3000]])


def proje_metni(baslik: str, ozet: str, anahtar: str = "", yetkinlikler: list[str] | None = None, yontem: str = "") -> str:
    return " ".join([baslik or ""] * 2 + [anahtar or ""] * 2 + [ozet or "", yontem or "", " ".join(yetkinlikler or [])])


def teknofest_eslestir(baslik: str, ozet: str, anahtar: str = "", yetkinlikler: list[str] | None = None,
                       yontem: str = "", top_n: int = 2, sadece_uygun: bool = True) -> list[dict]:
    """En uygun TEKNOFEST kategorilerini % uyum skoruyla döndürür."""
    with get_session() as s:
        q = select(TeknofestKategori).where(TeknofestKategori.aktif.is_(True))
        kategoriler = list(s.scalars(q))
    if sadece_uygun:
        kategoriler = [k for k in kategoriler if k.onlisans_uygun is not False]
    if not kategoriler:
        return []
    sims = _similarities(proje_metni(baslik, ozet, anahtar, yetkinlikler, yontem), [kategori_metni(k) for k in kategoriler])
    ranked = sorted(zip(kategoriler, sims), key=lambda x: x[1], reverse=True)
    esik = settings.get_float("teknofest_esik") / 100.0
    out = []
    for k, sim in ranked[:top_n]:
        if sim < esik:
            continue
        out.append({"kategori_id": k.id, "kategori_adi": k.kategori_adi, "skor": round(sim * 100, 1)})
    return out


def benzer_projeler(baslik: str, ozet: str, haric_id: int | None = None, esik: float = 0.35, top_n: int = 3) -> list[dict]:
    """Aynı fikrin daha önce girilip girilmediğini kontrol eder."""
    with get_session() as s:
        projeler = [p for p in s.scalars(select(Proje).where(Proje.durum != "Iptal")) if p.id != haric_id]
    if not projeler:
        return []
    sims = _similarities(proje_metni(baslik, ozet), [proje_metni(p.baslik, p.ozet) for p in projeler])
    ranked = sorted(zip(projeler, sims), key=lambda x: x[1], reverse=True)
    return [{"proje_id": p.id, "baslik": p.baslik, "tur": p.tur, "donem": p.donem, "skor": round(sim * 100, 1)}
            for p, sim in ranked[:top_n] if sim >= esik]


def ogrenciye_uygun_projeler(ogrenci: Kullanici, projeler: list[Proje]) -> dict[int, float]:
    """Proje panosunda 'size uygunluk' sıralaması için yetkinlik uyum yüzdeleri."""
    return {p.id: yetkinlik_analizi(p.aranan_yetkinlikler, ogrenci.yetkinlikler).uyum_yuzde for p in projeler}
