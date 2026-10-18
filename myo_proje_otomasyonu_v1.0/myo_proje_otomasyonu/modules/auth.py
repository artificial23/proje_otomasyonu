"""Kimlik doğrulama: şifre özetleme, giriş, kayıt ve şifre sıfırlama."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
import string

from sqlalchemy import func, select

from . import settings
from .database import Kullanici, Oturum, get_session, log_islem, now

_ITER = 200_000
ROLLER = {"ogrenci": "Öğrenci", "hoca": "Akademik Danışman", "sanayi": "Sanayi Temsilcisi", "admin": "Yönetici"}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITER).hex()
    return f"pbkdf2_sha256${_ITER}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters)).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, AttributeError):
        return False


def random_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


def password_problem(password: str) -> str | None:
    if len(password or "") < 8:
        return "Şifre en az 8 karakter olmalı."
    if not re.search(r"\d", password) or not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", password):
        return "Şifre en az bir harf ve bir rakam içermeli."
    return None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def email_allowed(email: str, rol: str) -> bool:
    """Kurum ayarlarında e-posta alan adı kısıtı varsa öğrenciler için uygular."""
    domains = [d.strip().lower().lstrip("@") for d in str(settings.get("izinli_eposta_alanlari") or "").split(",") if d.strip()]
    if not domains or rol != "ogrenci":
        return True
    return any(email.endswith("@" + d) or email.endswith("." + d) for d in domains)


MAX_DENEME = 5
KILIT_DAKIKA = 15


class HesapKilitli(Exception):
    """Çok sayıda hatalı denemeden sonra hesap geçici olarak kilitlenir."""


def _kilit_kontrol(user: Kullanici) -> None:
    if user.kilit_bitis and user.kilit_bitis > now():
        kalan = int((user.kilit_bitis - now()).total_seconds() // 60) + 1
        raise HesapKilitli(f"Çok sayıda hatalı deneme. {kalan} dakika sonra tekrar deneyin.")


def _hatali_deneme(user: Kullanici) -> None:
    user.basarisiz_deneme = (user.basarisiz_deneme or 0) + 1
    if user.basarisiz_deneme >= MAX_DENEME:
        user.kilit_bitis = now() + dt.timedelta(minutes=KILIT_DAKIKA)
        user.basarisiz_deneme = 0


def authenticate(email: str, password: str) -> Kullanici | None:
    """Başarılıysa kullanıcıyı döndürür; hesap kilitliyse HesapKilitli fırlatır."""
    email = normalize_email(email)
    with get_session() as s:
        user = s.scalar(select(Kullanici).where(func.lower(Kullanici.eposta) == email))
        if not user:
            return None
        _kilit_kontrol(user)
        if not verify_password(password, user.sifre_hash):
            _hatali_deneme(user)
            return None
        user.basarisiz_deneme, user.kilit_bitis = 0, None
        user.son_giris = now()
    log_islem(user.id, "giris", email)
    return user


def register_user(**fields) -> tuple[Kullanici | None, str | None]:
    """Yeni kullanıcı oluşturur. (kullanici, hata_mesaji) döndürür."""
    email = normalize_email(fields.get("eposta", ""))
    rol = fields.get("rol", "ogrenci")
    password = fields.pop("sifre", None)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return None, "Geçerli bir e-posta adresi girin."
    if not email_allowed(email, rol):
        return None, "Bu e-posta alan adıyla öğrenci kaydı yapılamıyor. Kurum e-postanızı kullanın."
    if password is not None:
        problem = password_problem(password)
        if problem:
            return None, problem
    with get_session() as s:
        exists = s.scalar(select(Kullanici.id).where(func.lower(Kullanici.eposta) == email))
        if exists:
            return None, "Bu e-posta adresiyle kayıtlı bir hesap zaten var."
        fields["eposta"] = email
        user = Kullanici(**fields)
        user.sifre_hash = hash_password(password) if password else ""
        if fields.get("kvkk_onay"):
            user.kvkk_tarih = now()
        s.add(user)
        s.flush()
        uid = user.id
    log_islem(uid, "kayit", f"{email} ({rol})")
    with get_session() as s:
        return s.get(Kullanici, uid), None


def set_password(user_id: int, password: str, must_change: bool = False) -> None:
    with get_session() as s:
        u = s.get(Kullanici, user_id)
        u.sifre_hash = hash_password(password)
        u.sifre_degismeli = must_change
        u.sifre_sifirlama_kod = None
        u.sifre_sifirlama_son = None
    if must_change:
        end_all_sessions(user_id)


def start_reset(email: str) -> tuple[Kullanici | None, str | None]:
    """6 haneli sıfırlama kodu üretir; kodu (gönderilmek üzere) döndürür."""
    email = normalize_email(email)
    code = "".join(secrets.choice(string.digits) for _ in range(6))
    with get_session() as s:
        user = s.scalar(select(Kullanici).where(func.lower(Kullanici.eposta) == email))
        if not user:
            return None, None
        user.sifre_sifirlama_kod = hash_password(code)
        user.sifre_sifirlama_son = now() + dt.timedelta(minutes=30)
    return user, code


def finish_reset(email: str, code: str, new_password: str) -> str | None:
    problem = password_problem(new_password)
    if problem:
        return problem
    email = normalize_email(email)
    with get_session() as s:
        user = s.scalar(select(Kullanici).where(func.lower(Kullanici.eposta) == email))
        if user:
            try:
                _kilit_kontrol(user)
            except HesapKilitli as exc:
                return str(exc)
        if (
            not user
            or not user.sifre_sifirlama_kod
            or not user.sifre_sifirlama_son
            or user.sifre_sifirlama_son < now()
            or not verify_password(code.strip(), user.sifre_sifirlama_kod)
        ):
            if user:
                _hatali_deneme(user)
                if user.kilit_bitis:  # kilitlenince kod da geçersiz olur
                    user.sifre_sifirlama_kod = None
            return "Kod hatalı veya süresi dolmuş."
        user.basarisiz_deneme, user.kilit_bitis = 0, None
        uid = user.id
    set_password(uid, new_password)
    end_all_sessions(uid)  # sıfırlama sonrası eski 'beni hatırla' oturumları geçersiz olsun
    log_islem(uid, "sifre_sifirlama", email)
    return None


def telegram_code() -> str:
    return "TG-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


# ---------------------------------------------------------------------------
# Kalıcı oturum (çerez)
# ---------------------------------------------------------------------------
OTURUM_GUN = 14


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_session() as s:
        s.add(Oturum(token_hash=_token_hash(token), kullanici_id=user_id, son_kullanma=now() + dt.timedelta(days=OTURUM_GUN)))
        for eski in s.scalars(select(Oturum).where(Oturum.son_kullanma < now())):
            s.delete(eski)
    return token


def user_from_session(token: str | None) -> int | None:
    if not token:
        return None
    with get_session() as s:
        o = s.scalar(select(Oturum).where(Oturum.token_hash == _token_hash(token)))
        if not o or o.son_kullanma < now():
            return None
        return o.kullanici_id


def end_session(token: str | None) -> None:
    if not token:
        return
    with get_session() as s:
        o = s.scalar(select(Oturum).where(Oturum.token_hash == _token_hash(token)))
        if o:
            s.delete(o)


def end_all_sessions(user_id: int) -> None:
    with get_session() as s:
        for o in s.scalars(select(Oturum).where(Oturum.kullanici_id == user_id)):
            s.delete(o)
