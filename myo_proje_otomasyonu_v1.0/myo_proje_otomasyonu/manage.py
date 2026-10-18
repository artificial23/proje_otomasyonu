"""Komut satırı yönetim aracı.

    python manage.py kurulum                 # veritabanını ve varsayılan verileri hazırlar
    python manage.py yonetici-ekle           # yönetici hesabı oluşturur (etkileşimli)
    python manage.py demo                    # DEMO kullanıcı ve projeleri yükler
    python manage.py demo-sil                # DEMO verilerini siler
    python manage.py tara [--limit N]        # TEKNOFEST taramasını hemen çalıştırır
    python manage.py hatirlat                # son tarih hatırlatmalarını gönderir
    python manage.py taslak-kontrol          # boş taslak kontrolünü çalıştırır
    python manage.py sablonlar               # varsayılan Word şablonlarını yeniden üretir
    python manage.py drive-yetkilendir DOSYA # Google Drive OAuth token'ı alır
    python manage.py yedekle                 # SQLite yedeği alır (data/yedekler)
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import logging
import sys

from modules import automation, config, seed, teknofest_scraper
from modules.database import init_db


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Proje Kuluçka yönetim aracı")
    sub = ap.add_subparsers(dest="komut", required=True)
    sub.add_parser("kurulum")
    sub.add_parser("yonetici-ekle")
    sub.add_parser("demo")
    sub.add_parser("demo-sil")
    t = sub.add_parser("tara")
    t.add_argument("--limit", type=int, default=None)
    sub.add_parser("hatirlat")
    sub.add_parser("taslak-kontrol")
    sub.add_parser("sablonlar")
    d = sub.add_parser("drive-yetkilendir")
    d.add_argument("istemci_json", nargs="?", default=str(config.SECRETS_DIR / "drive_oauth_client.json"))
    sub.add_parser("yedekle")
    args = ap.parse_args(argv)

    init_db()
    if args.komut == "kurulum":
        print("Varsayılan veriler:", seed.seed_defaults())
    elif args.komut == "yonetici-ekle":
        from modules import auth
        ad = input("Ad Soyad: ")
        eposta = input("E-posta: ")
        sifre = getpass.getpass("Şifre: ")
        user, err = auth.register_user(ad_soyad=ad, eposta=eposta, sifre=sifre, rol="admin", aktif=True, kvkk_onay=True)
        print(err or f"Yönetici oluşturuldu: {user.eposta}")
        seed.seed_defaults()
    elif args.komut == "demo":
        seed.seed_defaults()
        print(seed.seed_demo())
    elif args.komut == "demo-sil":
        print(seed.remove_demo())
    elif args.komut == "tara":
        sonuc = teknofest_scraper.run_scrape(progress=lambda x, m: print(f"[{x:4.0%}] {m}"), limit=args.limit)
        print(json.dumps(sonuc, ensure_ascii=False, indent=2, default=str))
    elif args.komut == "hatirlat":
        print("Gönderilen:", automation.hatirlatmalari_gonder())
    elif args.komut == "taslak-kontrol":
        print("Uyarı:", automation.taslak_kontrolu())
    elif args.komut == "sablonlar":
        sys.path.insert(0, str(config.BASE_DIR / "tools"))
        import build_templates
        build_templates.main()
    elif args.komut == "drive-yetkilendir":
        from modules import drive, settings
        print("Token kaydedildi:", drive.oauth_authorize(args.istemci_json))
        settings.save("drive_mod", "oauth")
    elif args.komut == "yedekle":
        import sqlite3
        if not config.DATABASE_URL.startswith("sqlite"):
            print("PostgreSQL için pg_dump kullanın.")
            return 1
        src = sqlite3.connect(config.DATABASE_URL.replace("sqlite:///", ""))
        hedef = config.BACKUP_DIR / f"myo_otomasyon_{dt.datetime.now():%Y%m%d_%H%M}.db"
        dst = sqlite3.connect(hedef)
        src.backup(dst)
        dst.close()
        src.close()
        print("Yedek:", hedef)
    return 0


if __name__ == "__main__":
    sys.exit(main())
