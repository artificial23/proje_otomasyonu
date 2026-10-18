"""Bildirim katmanı: uygulama içi kutu, e-posta (SMTP) ve Telegram.

E-posta veya Telegram yapılandırılmamışsa mesajlar silinmez; "Simule" durumuyla
bildirim kutusuna yazılır. Böylece sistem kurulumdan hemen sonra çalışır ve
yönetici hangi mesajların gideceğini Yönetim Paneli'nden görebilir.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import requests
from sqlalchemy import select

from . import settings
from .database import Bildirim, Kullanici, get_session, now

log = logging.getLogger("kulucka.notifier")


def _already_sent(anahtar: str | None, kullanici_id: int | None) -> bool:
    if not anahtar:
        return False
    with get_session() as s:
        return s.scalar(select(Bildirim.id).where(Bildirim.anahtar == anahtar, Bildirim.kullanici_id == kullanici_id).limit(1)) is not None


def smtp_hazir() -> bool:
    return settings.get_bool("eposta_aktif") and bool(settings.get("smtp_sunucu")) and bool(settings.get("smtp_gonderen") or settings.get("smtp_kullanici"))


def telegram_hazir() -> bool:
    return settings.get_bool("telegram_aktif") and bool(settings.get("telegram_token"))


def send_email(to: str, subject: str, body: str, attachments: list[str] | None = None) -> None:
    host = str(settings.get("smtp_sunucu"))
    port = settings.get_int("smtp_port")
    user = str(settings.get("smtp_kullanici") or "")
    pw = str(settings.get("smtp_sifre") or "")
    sender = str(settings.get("smtp_gonderen") or user)
    mode = str(settings.get("smtp_guvenlik") or "STARTTLS").upper()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((str(settings.get("kurum_adi"))[:60] + " Proje Sistemi", sender))
    msg["To"] = to
    msg.set_content(body)
    for path in attachments or []:
        from pathlib import Path
        p = Path(path)
        if p.exists():
            msg.add_attachment(p.read_bytes(), maintype="application", subtype="octet-stream", filename=p.name)
    ctx = ssl.create_default_context()
    if mode == "SSL":
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as srv:
            if user:
                srv.login(user, pw)
            srv.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as srv:
            if mode == "STARTTLS":
                srv.starttls(context=ctx)
            if user:
                srv.login(user, pw)
            srv.send_message(msg)


def send_telegram(chat_id: str, text: str) -> None:
    token = str(settings.get("telegram_token"))
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}, timeout=20)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or f"HTTP {r.status_code}")


def notify(user: Kullanici | int, konu: str, icerik: str, anahtar: str | None = None,
           kanallar: tuple[str, ...] = ("uygulama", "eposta", "telegram"), ekler: list[str] | None = None) -> bool:
    """Kullanıcıya bildirim gönderir. `anahtar` verilirse aynı bildirim ikinci kez gönderilmez."""
    if isinstance(user, int):
        with get_session() as s:
            user = s.get(Kullanici, user)
    if user is None:
        return False
    if _already_sent(anahtar, user.id):
        return False
    url = str(settings.get("uygulama_url") or "").rstrip("/")
    full = icerik + (f"\n\nSisteme git: {url}" if url and url not in icerik else "")
    rows: list[Bildirim] = []
    if "uygulama" in kanallar:
        rows.append(Bildirim(kullanici_id=user.id, kanal="uygulama", konu=konu, icerik=icerik, durum="Gonderildi",
                             anahtar=anahtar, gonderim=now()))
    if "eposta" in kanallar and user.eposta:
        b = Bildirim(kullanici_id=user.id, kanal="eposta", konu=konu, icerik=full, anahtar=anahtar, okundu=True)
        if smtp_hazir():
            try:
                send_email(user.eposta, konu, full, ekler)
                b.durum, b.gonderim = "Gonderildi", now()
            except Exception as exc:  # noqa: BLE001
                b.durum, b.hata = "Hata", str(exc)[:500]
                log.warning("E-posta gönderilemedi (%s): %s", user.eposta, exc)
        else:
            b.durum = "Simule"
        rows.append(b)
    if "telegram" in kanallar and user.telegram_chat_id and telegram_hazir():
        b = Bildirim(kullanici_id=user.id, kanal="telegram", konu=konu, icerik=full, anahtar=anahtar, okundu=True)
        try:
            send_telegram(user.telegram_chat_id, f"📌 {konu}\n\n{full}")
            b.durum, b.gonderim = "Gonderildi", now()
        except Exception as exc:  # noqa: BLE001
            b.durum, b.hata = "Hata", str(exc)[:500]
        rows.append(b)
    with get_session() as s:
        s.add_all(rows)
    return True


def notify_many(users, konu: str, icerik: str, anahtar_prefix: str | None = None, **kw) -> int:
    n = 0
    for u in users:
        uid = u if isinstance(u, int) else u.id
        if notify(u, konu, icerik, anahtar=f"{anahtar_prefix}:{uid}" if anahtar_prefix else None, **kw):
            n += 1
    return n


def okunmamis_sayisi(user_id: int) -> int:
    with get_session() as s:
        return len(list(s.scalars(select(Bildirim.id).where(
            Bildirim.kullanici_id == user_id, Bildirim.kanal == "uygulama", Bildirim.okundu.is_(False)))))


def telegram_sync() -> int:
    """Bot'a '/start TG-XXXXXX' yazan kullanıcıların sohbet kimliklerini eşler."""
    if not telegram_hazir():
        return 0
    token = str(settings.get("telegram_token"))
    offset = settings.get_int("telegram_son_update") + 1
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=20)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description"))
    linked = 0
    last = offset - 1
    for upd in data.get("result", []):
        last = max(last, upd.get("update_id", 0))
        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip().upper()
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        code = next((p for p in text.replace("/START", " ").split() if p.startswith("TG-")), None)
        if not code or not chat_id:
            continue
        name = None
        with get_session() as s:
            u = s.scalar(select(Kullanici).where(Kullanici.telegram_kod == code))
            if u:
                u.telegram_chat_id = chat_id
                linked += 1
                name = u.ad_soyad
        try:
            send_telegram(chat_id, f"✅ Merhaba {name}, hesabınız bağlandı. Proje bildirimleri buraya gelecek." if name else
                          "Kod bulunamadı. Profil sayfanızdaki kodu kontrol edin.")
        except Exception:  # noqa: BLE001
            pass
    settings.save("telegram_son_update", last)
    return linked
