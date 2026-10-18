"""Türkçe metin yardımcıları: normalizasyon, durak kelimeler, kök bulma, slug."""
from __future__ import annotations

import re
import unicodedata

_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_TR_ASCII = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})

STOPWORDS = set(
    """
    acaba ama ancak artık aslında az bana bazen bazı bazıları belki ben beni benim beş bile bir birkaç birçok
    biri birisi birşey biz bize bizi bizim bu buna bunda bundan bunu bunun burada böyle böylece çok çünkü da daha
    de defa değil diye dolayı dolayısıyla eğer en fakat gibi göre hala hangi hatta hem hep hepsi her herhangi
    hiç için ile ilgili ise işte itibaren kadar karşın kendi kendine kez ki kim kimse mı mi mu mü nasıl ne neden
    nerede nereye niçin niye o olan olarak oldu olduğu olduğunu olmak olmayan olmuş olsa olup onlar onları onların
    onu onun orada öyle oysa pek rağmen sadece sanki şey şu şuna şunda şundan şunu tarafından tüm üzere var vardır
    ve veya ya yani yine yoksa zaten ayrıca sonra önce içinde üzerinde arasında yapılan yapılacak yapmak sağlamak
    amacıyla kapsamında projede proje projesi projenin çalışma çalışmada sistem sistemi sisteminin yöntem
    olacak olacaktır edilecek edilmesi yapılması bulunan farklı yeni temel genel kullanılarak kullanılan
    """.split()
)


def tr_lower(text: str) -> str:
    return (text or "").translate(_TR_LOWER).lower()


def fold(text: str) -> str:
    """Küçük harfe çevirip Türkçe karakterleri ASCII karşılıklarına indirger."""
    t = tr_lower(text).translate(_TR_ASCII)
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if not unicodedata.combining(ch))


_STOP_FOLDED = {fold(w) for w in STOPWORDS}
_TOKEN_RE = re.compile(r"[a-z0-9\+#]+")


def tokenize(text: str, stem_len: int = 5) -> list[str]:
    """Türkçe için etkili olduğu bilinen 'ilk 5 harf' (F5) kök yaklaşımıyla belirteçler."""
    tokens = []
    for tok in _TOKEN_RE.findall(fold(text)):
        if len(tok) < 2 or tok in _STOP_FOLDED or tok.isdigit():
            continue
        tokens.append(tok[:stem_len] if len(tok) > stem_len else tok)
    return tokens


def slugify(text: str) -> str:
    s = fold(text)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "kayit"


def safe_filename(text: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\- ]+", "", fold(text)).strip().replace(" ", "_")
    return (s[:max_len].rstrip("_")) or "proje"


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


# ---------------------------------------------------------------------------
# Yetkinlik eşleştirme
# ---------------------------------------------------------------------------
_SKILL_ALIASES = {
    "solid works": "solidworks",
    "tia portal": "plc",
    "siemens plc": "plc",
    "siemens tia portal": "plc",
    "s7": "plc",
    "c++": "c",
    "cpp": "c",
    "opencv": "goruntu isleme",
    "makine ogrenmesi": "yapay zeka",
    "ml": "yapay zeka",
    "derin ogrenme": "yapay zeka",
    "ros": "robotik",
    "esp32": "gomulu sistemler",
    "stm32": "gomulu sistemler",
    "kicad": "pcb tasarimi",
    "altium": "pcb tasarimi",
    "3d baski": "3d yazici",
    "simulink": "matlab",
    "hmi": "scada",
    "hidrolik": "pnomatik",
    "bms": "batarya",
    "guc elektronigi": "motor surucu",
    "iha": "insansiz hava araci",
    "drone": "insansiz hava araci",
}


def skill_key(skill: str) -> str:
    """Yetkinlik adını karşılaştırma anahtarına çevirir.

    Büyük/küçük harf, Türkçe karakter ve parantez içi açıklamalar yok sayılır;
    "Yapay Zeka / Makine Öğrenmesi" gibi bileşik adlarda ilk parça esas alınır.
    Böylece "plc", "PLC (Siemens TIA Portal)" ve "TIA Portal" aynı yetkinlik sayılır.
    """
    s = fold(skill)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _SKILL_ALIASES.get(s, s)
    s = s.split(" / ")[0].strip()
    return _SKILL_ALIASES.get(s, s)


def skill_set(skills) -> dict[str, str]:
    """{anahtar: görünen_ad} sözlüğü döndürür."""
    out: dict[str, str] = {}
    for sk in skills or []:
        if not sk:
            continue
        out.setdefault(skill_key(str(sk)), str(sk).strip())
    return out


def parse_list(text: str) -> list[str]:
    if isinstance(text, list):
        return [str(x).strip() for x in text if str(x).strip()]
    parts = re.split(r"[,;\n]", text or "")
    return [p.strip() for p in parts if p.strip()]
