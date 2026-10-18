"""TEKNOFEST yarışma kazıyıcı ve ödüllü proje arşiv yükleyici.

Çalışma mantığı
---------------
1. teknofest.org/tr/yarismalar/ sayfasındaki tüm yarışma bağlantılarını toplar.
2. Her yarışma sayfasını açar; "Yarışma Hakkında" bölümünden katılım seviyesini
   (Ön Lisans / Üniversite / Lise ...), takvim tablosundan son başvuru tarihini,
   ödül tablosunu, şartname PDF'ini ve resmi rapor şablonlarını çıkarır.
3. "<Yarışma> <Yıl> Dereceler" tablolarını Ödüllü Projeler arşivine aktarır.
4. Ön lisansa uygun yarışmaların şartname PDF'lerini data/sartnameler/ altına indirir.

Sayfa düzeni değişse bile çalışabilmesi için ayrıştırma, HTML sınıflarına değil
metin kalıplarına dayanır. Site, istekleri engellerse (403) ve Playwright kuruluysa
tarayıcı ile yeniden denenir.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import time
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString
from sqlalchemy import select

from . import config, settings
from .database import OdulluProje, TeknofestKategori, get_session, log_islem, now
from .text_utils import fold, slugify

log = logging.getLogger("kulucka.scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 KuluckaBot/1.0 (egitim amacli)"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5",
}

AYLAR = {"ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7,
         "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12}
_DATE_NUM = re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})")
_DATE_TXT = re.compile(r"(\d{1,2})\s+(ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik)\s+(20\d{2})")
_LINK_RE = re.compile(r"^/(?:tr|en)/yarismalar/([a-z0-9][a-z0-9\-]*)/?$")


class ScraperError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _fetch_playwright(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ScraperError("Site isteği engelledi ve Playwright kurulu değil.") from exc
    with sync_playwright() as p:  # pragma: no cover - ağ gerektirir
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]})
        page.goto(url, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()
        return html


def fetch(url: str, session: requests.Session | None = None, retries: int = 2) -> str:
    sess = session or requests.Session()
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = sess.get(url, headers=HEADERS, timeout=30)
            if r.status_code in (403, 429, 503):
                raise ScraperError(f"HTTP {r.status_code}")
            r.raise_for_status()
            # charset bildirilmeyen text/html yanıtlarında requests ISO-8859-1 varsayar; Türkçe karakterler bozulmasın
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = "utf-8"
            return r.text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(2 * (attempt + 1))
    try:
        return _fetch_playwright(url)
    except ScraperError:
        raise ScraperError(f"{url} alınamadı: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Ayrıştırma
# ---------------------------------------------------------------------------
def parse_listing(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"])
        parsed = urlparse(full)
        if "teknofest.org" not in parsed.netloc and parsed.netloc:
            continue
        m = _LINK_RE.match(parsed.path)
        if not m:
            continue
        slug = m.group(1)
        name = a.get_text(" ", strip=True)
        if not name or len(name) < 4 or fold(name) in ("detay", "detaylar", "incele", "basvur", "basvuru tamamlandi"):
            name = found.get(slug, {}).get("ad") or ""
        url = f"{parsed.scheme or 'https'}://{parsed.netloc or 'www.teknofest.org'}/tr/yarismalar/{slug}/"
        entry = found.setdefault(slug, {"slug": slug, "url": url, "ad": ""})
        if name and (not entry["ad"] or len(name) < len(entry["ad"]) and "yarisma" in fold(name)):
            entry["ad"] = re.sub(r"\s*(Başvuru Tamamlandı|Başvur|Detaylar?)\s*$", "", name).strip()
    return list(found.values())


def _parse_date(text: str) -> dt.date | None:
    t = fold(text)
    m = _DATE_NUM.search(t)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    m = _DATE_TXT.search(t)
    if m:
        try:
            return dt.date(int(m.group(3)), AYLAR[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    return None


def detect_levels(text: str) -> tuple[list[str], bool | None]:
    t = fold(text)
    levels = []
    if re.search(r"\bon\s?lisans", t):
        levels.append("Ön Lisans")
    if re.search(r"\blisans\b|\blisans ogrenci", t):
        levels.append("Lisans")
    if "lisansustu" in t or "yuksek lisans" in t or "doktora" in t:
        levels.append("Lisansüstü")
    if "universite" in t:
        levels.append("Üniversite")
    if re.search(r"\blise\b|\bliseler", t):
        levels.append("Lise")
    if "ortaokul" in t:
        levels.append("Ortaokul")
    if "ilkokul" in t:
        levels.append("İlkokul")
    if "mezun" in t:
        levels.append("Mezun")
    if "Ön Lisans" in levels or "Üniversite" in levels:
        uygun: bool | None = True
    elif levels and set(levels) <= {"Lise", "Ortaokul", "İlkokul", "Lisansüstü"}:
        uygun = False
    else:
        uygun = None
    return levels, uygun


def _flatten_tables(soup: BeautifulSoup) -> None:
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        tr.replace_with(NavigableString("\n" + " | ".join(cells) + "\n"))


def _section(lines: list[str], start_pat: str, stop_pats: list[str], max_lines: int = 80) -> list[str]:
    out, inside = [], False
    for ln in lines:
        f = fold(ln)
        if not inside and re.search(start_pat, f):
            inside = True
            continue
        if inside:
            if any(re.search(p, f) for p in stop_pats):
                break
            out.append(ln)
            if len(out) >= max_lines:
                break
    return out


def parse_detail(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        title = (og.get("content") if og else "") or (soup.title.get_text(strip=True) if soup.title else "")
    # "Ad | TEKNOFEST" / "Ad - TEKNOFEST" son eki atılır; "TÜBA-TEKNOFEST ..." gibi adlar korunur
    title = re.sub(r"\s*(?:\||\s[\-–])\s*TEKNOFEST.*$", "", title).strip()

    # Bağlantılar (düzleştirmeden önce)
    pdfs, sablonlar = [], []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"].strip())
        text = a.get_text(" ", strip=True)
        low = href.lower().split("?")[0]
        if low.endswith(".pdf"):
            pdfs.append({"ad": text, "url": href})
        elif low.endswith((".docx", ".doc", ".pptx", ".xlsx")):
            sablonlar.append({"ad": text or href.rsplit("/", 1)[-1], "url": href})

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "svg", "form"]):
        tag.decompose()
    _flatten_tables(soup)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").splitlines()]
    lines = [ln for ln in lines if ln]

    hakkinda = _section(lines, r"yarisma hakkinda|hakkinda$", [r"yarisma takvimi", r"oduller?$", r"\boduller\b", r"rapor sablon"], 60)
    aciklama = " ".join(hakkinda)[:4000]
    levels, uygun = detect_levels(aciklama or " ".join(lines[:200]))

    # Takvim
    takvim, son_basvuru, sezon = [], None, None
    for ln in lines:
        m = re.search(r"yarisma takvimi\s*(20\d{2})", fold(ln))
        if m:
            sezon = m.group(1)
            break
    for ln in lines:
        if "|" not in ln and ":" not in ln:
            continue
        d = _parse_date(ln)
        if not d:
            continue
        label = re.split(r"\s*[|:]\s*", ln)[0].strip()
        if not label or _parse_date(label):
            continue
        if re.search(r"derece|takim adi", fold(label)):
            continue
        takvim.append({"asama": label[:200], "tarih": d.isoformat()})
        if son_basvuru is None and "son basvuru" in fold(label):
            son_basvuru = d
    # Ödüller
    oduller = []
    odul_bolumu = _section(lines, r"\boduller?\b", [r"dereceler?$", r"\bdereceleri?\b", r"rapor sablon", r"yarisma dokuman"], 30)
    for ln in odul_bolumu or lines:
        m = re.search(r"([\d]{1,3}(?:[.\s]\d{3})+|\d{4,})\s*(?:TL|₺)", ln)
        if not m:
            continue
        derece = re.split(r"\s*[|:]\s*", ln)[0].strip()
        if derece and len(derece) < 60:
            oduller.append({"derece": derece, "tutar": m.group(1).replace(" ", ".") + " TL"})
    odul_ozet = " / ".join(f"{o['derece']}: {o['tutar']}" for o in oduller[:4])

    # Takım büyüklüğü
    takim_min = takim_max = None
    m = re.search(r"(\d{1,2})\s*(?:ile|-|–)\s*(\d{1,2})\s*(?:kisi|uye|ogrenci)", fold(aciklama))
    if m:
        takim_min, takim_max = int(m.group(1)), int(m.group(2))

    # Şartname
    sartname = None
    for p in pdfs:
        f = fold(p["ad"] + " " + p["url"])
        if "sartname" in f and not re.search(r"\bek\b|ek teknik|ek_", f):
            sartname = p["url"]
            break
    if not sartname:
        for p in pdfs:
            if "sartname" in fold(p["ad"] + " " + p["url"]):
                sartname = p["url"]
                break

    # Dereceler (arşiv)
    dereceler = []
    i = 0
    while i < len(lines):
        f = fold(lines[i])
        m = re.search(r"(20\d{2})\s+dereceler?i?\b", f)
        if m and "|" not in lines[i]:
            yil = int(m.group(1))
            kategori = re.sub(r"\s*20\d{2}\s+Dereceler?i?\s*$", "", lines[i], flags=re.I).strip() or title
            header: list[str] = []
            j = i + 1
            while j < len(lines) and "|" in lines[j]:
                cells = [c.strip() for c in lines[j].split("|")]
                fc = [fold(c) for c in cells]
                if fc and fc[0] in ("derece", "sira", "sıra") or "takim adi" in fc:
                    header = fc
                else:
                    row = {"yil": yil, "kategori_adi": kategori, "derece": cells[0], "takim_adi": cells[1] if len(cells) > 1 else "",
                           "kurum_adi": "", "proje_adi": ""}
                    for idx, h in enumerate(header):
                        if idx >= len(cells):
                            break
                        if "kurum" in h or "universite" in h or "okul" in h:
                            row["kurum_adi"] = cells[idx]
                        elif "proje" in h:
                            row["proje_adi"] = cells[idx]
                        elif "takim" in h:
                            row["takim_adi"] = cells[idx]
                    if row["derece"] and row["takim_adi"]:
                        dereceler.append(row)
                j += 1
            i = j
            continue
        i += 1

    return {
        "kategori_adi": title,
        "aciklama": aciklama,
        "katilim_seviyesi": ", ".join(levels),
        "onlisans_uygun": uygun,
        "takvim": takvim,
        "son_basvuru_tarihi": son_basvuru,
        "oduller": oduller,
        "odul_miktari": odul_ozet,
        "sartname_pdf_url": sartname,
        "rapor_sablonlari": sablonlar,
        "takim_min": takim_min,
        "takim_max": takim_max,
        "sezon": sezon,
        "dereceler": dereceler,
    }


# ---------------------------------------------------------------------------
# Dosya indirme
# ---------------------------------------------------------------------------
def download_file(url: str, dest_dir, filename: str | None = None, session: requests.Session | None = None) -> str:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = filename or unquote(url.split("?")[0].rsplit("/", 1)[-1]) or "dosya.pdf"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .") or "dosya.pdf"  # Windows'ta geçersiz karakterler
    dest = dest_dir / name
    sess = session or requests.Session()
    r = sess.get(url, headers=HEADERS, timeout=60, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(65536):
            fh.write(chunk)
    return str(dest)


def sartname_indir(kategori: TeknofestKategori, session: requests.Session | None = None, force: bool = False) -> str | None:
    if not kategori.sartname_pdf_url:
        return None
    dest = config.SARTNAME_DIR / f"{kategori.slug}.pdf"
    if dest.exists() and not force and kategori.sartname_yerel_yol == str(dest):
        return str(dest)
    path = download_file(kategori.sartname_pdf_url, config.SARTNAME_DIR, f"{kategori.slug}.pdf", session)
    with get_session() as s:
        k = s.get(TeknofestKategori, kategori.id)
        k.sartname_yerel_yol = path
    return path


# ---------------------------------------------------------------------------
# Veritabanına kaydetme
# ---------------------------------------------------------------------------
def save_category(data: dict, slug: str, url: str, kaynak: str = "scraper") -> tuple[TeknofestKategori, bool]:
    with get_session() as s:
        k = s.scalar(select(TeknofestKategori).where(TeknofestKategori.slug == slug))
        yeni = k is None
        if yeni:
            k = TeknofestKategori(slug=slug, kategori_adi=data.get("kategori_adi") or slug, anahtar_kelimeler="")
            s.add(k)
        for field_name in ("kategori_adi", "aciklama", "katilim_seviyesi", "takvim", "son_basvuru_tarihi", "oduller",
                           "odul_miktari", "sartname_pdf_url", "rapor_sablonlari", "takim_min", "takim_max", "sezon"):
            val = data.get(field_name)
            if val in (None, "", []):
                continue
            if field_name == "sartname_pdf_url" and val != k.sartname_pdf_url:
                k.sartname_yerel_yol = None
            setattr(k, field_name, val)
        if data.get("onlisans_uygun") is not None or k.onlisans_uygun is None:
            k.onlisans_uygun = data.get("onlisans_uygun", k.onlisans_uygun)
        k.url = url
        k.aktif = True
        k.kaynak = kaynak
        k.son_guncelleme = now()
        s.flush()
        return k, yeni


def save_dereceler(rows: list[dict], kategori_id: int | None) -> int:
    added = 0
    with get_session() as s:
        for r in rows:
            exists = s.scalar(select(OdulluProje.id).where(
                OdulluProje.kategori_adi == r["kategori_adi"], OdulluProje.yil == r["yil"],
                OdulluProje.derece == r["derece"], OdulluProje.takim_adi == r["takim_adi"]))
            if exists:
                continue
            s.add(OdulluProje(
                proje_adi=r.get("proje_adi") or "", takim_adi=r["takim_adi"], yil=r["yil"], kategori_id=kategori_id,
                kategori_adi=r["kategori_adi"], program="TEKNOFEST", derece=r["derece"], kurum_adi=r.get("kurum_adi") or "",
                kaynak="teknofest.org",
            ))
            added += 1
    return added


def run_scrape(progress: Callable[[float, str], None] | None = None, limit: int | None = None,
               indir_sartname: bool = True) -> dict:
    """Tam tarama. Özet sözlüğü döndürür ve ayarlara kaydeder."""
    progress = progress or (lambda *_: None)
    list_url = str(settings.get("teknofest_liste_url"))
    delay = settings.get_float("teknofest_tarama_gecikme")
    sess = requests.Session()
    ozet = {"tarih": now().isoformat(sep=" "), "bulunan": 0, "yeni": 0, "guncellenen": 0, "onlisans_uygun": 0,
            "sartname": 0, "arsiv": 0, "hatalar": []}
    progress(0.02, "Yarışma listesi alınıyor…")
    try:
        listing = parse_listing(fetch(list_url, sess), list_url)
    except Exception as exc:  # noqa: BLE001
        ozet["hatalar"].append(f"Liste sayfası: {exc}")
        settings.save("son_tarama", ozet["tarih"])
        settings.save("son_tarama_ozet", ozet)
        log_islem(None, "teknofest_tarama_hata", str(exc))
        return ozet
    if limit:
        listing = listing[:limit]
    ozet["bulunan"] = len(listing)
    seen = set()
    for idx, item in enumerate(listing, start=1):
        progress(0.05 + 0.9 * idx / max(1, len(listing)), f"{idx}/{len(listing)} · {item['ad'] or item['slug']}")
        seen.add(item["slug"])  # listede var: sayfası geçici olarak alınamasa da pasife çekilmesin
        try:
            data = parse_detail(fetch(item["url"], sess), item["url"])
            if not data.get("kategori_adi"):
                data["kategori_adi"] = item["ad"] or item["slug"]
            kat, yeni = save_category(data, item["slug"], item["url"])
            ozet["yeni" if yeni else "guncellenen"] += 1
            if kat.onlisans_uygun:
                ozet["onlisans_uygun"] += 1
                if indir_sartname and kat.sartname_pdf_url:
                    try:
                        sartname_indir(kat, sess)
                        ozet["sartname"] += 1
                    except Exception as exc:  # noqa: BLE001
                        ozet["hatalar"].append(f"{kat.kategori_adi} şartname: {exc}")
            if data.get("dereceler"):
                ozet["arsiv"] += save_dereceler(data["dereceler"], kat.id)
        except Exception as exc:  # noqa: BLE001
            ozet["hatalar"].append(f"{item['slug']}: {exc}")
        time.sleep(delay)
    if seen and not limit:
        with get_session() as s:
            for k in s.scalars(select(TeknofestKategori).where(TeknofestKategori.kaynak == "scraper")):
                if k.slug not in seen:
                    k.aktif = False
    settings.save("son_tarama", ozet["tarih"])
    settings.save("son_tarama_ozet", ozet)
    log_islem(None, "teknofest_tarama", f"{ozet['bulunan']} yarışma, {ozet['yeni']} yeni, {len(ozet['hatalar'])} hata")
    progress(1.0, "Tamamlandı")
    return ozet


def slug_from_name(name: str) -> str:
    return slugify(name)
