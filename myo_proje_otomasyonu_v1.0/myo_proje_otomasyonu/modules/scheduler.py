"""Zamanlanmış görevler (APScheduler).

Görevler
--------
* teknofest_tarama   : haftada bir (varsayılan Pazartesi 03:00) teknofest.org taraması
* hatirlatmalar      : her gün 09:00 son tarih hatırlatmaları (10 ve 3 gün kala)
* taslak_kontrolu    : her gün 10:00 boş taslak kontrolü
* davet_suresi       : her gün 08:00 süresi dolan davetleri kapatır
* telegram_baglanti  : 2 dakikada bir Telegram bot eşleştirmesi (Telegram açıksa)
* kalp_atisi         : her dakika; Yönetim Paneli zamanlayıcının çalıştığını buradan görür
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import automation, notifier, settings, teknofest_scraper
from .database import init_db, log_islem, now  # noqa: F401

log = logging.getLogger("kulucka.scheduler")


def _guvenli(ad: str, fn):
    def wrapper():
        try:
            sonuc = fn()
            log.info("%s tamamlandı: %s", ad, sonuc)
        except Exception as exc:  # noqa: BLE001
            log.exception("%s hata verdi", ad)
            log_islem(None, f"zamanlayici_hata:{ad}", str(exc))
    wrapper.__name__ = wrapper.__qualname__ = ad
    return wrapper


def _simdi():
    import datetime as dt
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo(os.environ.get("KULUCKA_SAAT_DILIMI", "Europe/Istanbul")))


def _kalp() -> None:
    settings.save("zamanlayici_kalp", {"zaman": now().isoformat(sep=" "), "pid": os.getpid()})


def _telegram() -> None:
    if notifier.telegram_hazir():
        notifier.telegram_sync()


def gorevleri_ekle(sched) -> None:
    gun = str(settings.get("teknofest_tarama_gunu") or "mon")
    saat = settings.get_int("teknofest_tarama_saati")
    sched.add_job(_guvenli("teknofest_tarama", teknofest_scraper.run_scrape), CronTrigger(day_of_week=gun, hour=saat, minute=0),
                  id="teknofest_tarama", replace_existing=True, misfire_grace_time=6 * 3600, coalesce=True)
    sched.add_job(_guvenli("hatirlatmalar", automation.hatirlatmalari_gonder), CronTrigger(hour=9, minute=0),
                  id="hatirlatmalar", replace_existing=True, misfire_grace_time=12 * 3600, coalesce=True)
    sched.add_job(_guvenli("taslak_kontrolu", automation.taslak_kontrolu), CronTrigger(hour=10, minute=0),
                  id="taslak_kontrolu", replace_existing=True, misfire_grace_time=12 * 3600, coalesce=True)
    sched.add_job(_guvenli("davet_suresi", automation.davet_suresi_kontrol), CronTrigger(hour=8, minute=0),
                  id="davet_suresi", replace_existing=True, misfire_grace_time=12 * 3600, coalesce=True)
    sched.add_job(_guvenli("telegram_baglanti", _telegram), IntervalTrigger(minutes=2), id="telegram_baglanti", replace_existing=True)
    sched.add_job(_kalp, IntervalTrigger(minutes=1), id="kalp_atisi", replace_existing=True, next_run_time=_simdi())
    # Uygulama kapalıyken kaçırılan hatırlatmalar için açılışta bir kez çalıştır
    sched.add_job(_guvenli("hatirlatmalar_acilis", automation.hatirlatmalari_gonder), id="hatirlatmalar_acilis",
                  replace_existing=True, next_run_time=_simdi(), misfire_grace_time=3600)


def start_background() -> BackgroundScheduler:
    init_db()
    sched = BackgroundScheduler(timezone=os.environ.get("KULUCKA_SAAT_DILIMI", "Europe/Istanbul"))
    gorevleri_ekle(sched)
    sched.start()
    log.info("Gömülü zamanlayıcı başlatıldı")
    return sched


def run_blocking() -> None:
    init_db()
    sched = BlockingScheduler(timezone=os.environ.get("KULUCKA_SAAT_DILIMI", "Europe/Istanbul"))
    gorevleri_ekle(sched)
    log.info("Zamanlayıcı çalışıyor (Ctrl+C ile durdurun)")
    sched.start()


def durum() -> dict:
    """Yönetim paneli için: zamanlayıcı son kalp atışı."""
    import datetime as dt
    kalp = settings.get("zamanlayici_kalp") or {}
    if isinstance(kalp, dict) and kalp.get("zaman"):
        t = dt.datetime.fromisoformat(kalp["zaman"])
        fark = (now() - t).total_seconds()
        return {"calisiyor": fark < 180, "son": t, "pid": kalp.get("pid")}
    return {"calisiyor": False, "son": None, "pid": None}
