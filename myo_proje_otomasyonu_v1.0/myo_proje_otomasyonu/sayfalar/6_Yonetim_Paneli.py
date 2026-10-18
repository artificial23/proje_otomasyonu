import datetime as dt
import io
import shutil
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from modules import (
    auth, automation, config, doc_generator, importer, notifier, scheduler, seed, settings, teknofest_scraper, ui,
)
from modules.database import Bildirim, CagriTakvimi, IslemLog, Kullanici, get_session, log_islem

u = ui.require_user(("admin",))
st.title("🛠️ Yönetim Paneli")

z = scheduler.durum()
if z["calisiyor"]:
    st.caption(f"🟢 Zamanlayıcı çalışıyor (son sinyal {z['son']:%H:%M:%S}). Otomatik görevler: haftalık TEKNOFEST taraması, "
               "günlük hatırlatma, taslak kontrolü.")
else:
    st.warning("🔴 Zamanlayıcıdan sinyal alınamıyor. Otomatik görevler için uygulamayı başlatma betiğiyle çalıştırın "
               "veya ayrı bir terminalde `python worker.py` komutunu çalıştırın.")

t_genel, t_kul, t_ent, t_takvim, t_sablon, t_kayit, t_yedek = st.tabs(
    ["⚙️ Genel", "👥 Kullanıcılar", "🔌 Entegrasyonlar", "📅 Takvim & Görevler", "📄 Şablonlar", "📜 Bildirim & Kayıtlar", "💾 Yedek & Veri"])

# ---------------------------------------------------------------------------
with t_genel:
    with st.form("genel"):
        st.subheader("Kurum")
        c1, c2 = st.columns(2)
        kurum = c1.text_input("Birim adı", settings.get("kurum_adi"))
        uni = c2.text_input("Üniversite adı", settings.get("universite_adi"))
        c3, c4 = st.columns(2)
        url = c3.text_input("Uygulama adresi (e-posta bağlantıları için)", settings.get("uygulama_url"),
                            disabled=settings.env_overridden("uygulama_url"))
        donem = c4.text_input("Aktif çağrı dönemi", settings.get("aktif_donem"))
        bolumler = st.text_area("Bölümler / programlar (her satıra bir tane)", "\n".join(settings.get("bolumler") or []), height=150)

        st.subheader("Kurallar")
        st.caption("Varsayılanlar 2026 TÜBİTAK 2209-A/B çağrı metinlerine göredir; yeni çağrıda değişiklik olursa buradan güncelleyin.")
        r1, r2, r3, r4 = st.columns(4)
        kota = r1.number_input("2209 danışman kotası", 1, 50, settings.get_int("max_kota_2209"))
        kota_b = r2.number_input("Bitirme danışman kotası", 1, 100, settings.get_int("max_kota_bitirme"))
        ekip = r3.number_input("2209 en fazla kişi (yürütücü dahil)", 1, 15, settings.get_int("max_ekip_2209"))
        ekip_b = r4.number_input("Bitirme ekip sınırı", 1, 15, settings.get_int("max_ekip_bitirme"))
        r5, r6, r7, r8 = st.columns(4)
        lim_a = r5.number_input("2209-A bütçe limiti (TL)", 0, 10_000_000, settings.get_int("butce_limit_2209a"), step=500)
        lim_b = r6.number_input("2209-B bütçe limiti (TL)", 0, 10_000_000, settings.get_int("butce_limit_2209b"), step=500)
        sure = r7.number_input("En uzun proje süresi (ay)", 1, 36, settings.get_int("max_sure_ay"))
        gno = r8.number_input("Kurum içi asgari GNO (0 = yok)", 0.0, 4.0, settings.get_float("min_gno"), 0.05)

        st.subheader("Eşleştirme ve bildirim")
        e1, e2, e3, e4 = st.columns(4)
        oto = e1.toggle("Otomatik takım daveti", settings.get_bool("otomatik_davet"))
        aday = e2.number_input("Eksik yetkinlik başına aday", 1, 20, settings.get_int("davet_aday_sayisi"))
        gecer = e3.number_input("Davet geçerlilik (gün)", 1, 90, settings.get_int("davet_gecerlilik_gun"))
        esik = e4.number_input("TEKNOFEST eşleşme eşiği (%)", 0, 100, settings.get_int("teknofest_esik"))
        h1, h2 = st.columns(2)
        hatir = h1.text_input("Hatırlatma günleri (son tarihe kala)", str(settings.get("hatirlatma_gunleri")), help="Ör. 10,3")
        taslak = h2.number_input("Boş taslak uyarısı: kurulumdan kaç gün sonra", 1, 60, settings.get_int("taslak_kontrol_gun"))

        st.subheader("Kayıt")
        k1, k2 = st.columns(2)
        ogr_kayit = k1.toggle("Öğrenciler kendi kaydını oluşturabilir", settings.get_bool("ogrenci_kayit_acik"))
        onay = k2.toggle("Danışman / sanayi hesapları yönetici onayı gerektirir", settings.get_bool("hoca_sanayi_onay_gerekli"))
        alan = st.text_input("Öğrenci e-posta alan adları (virgülle, boş = kısıt yok)", settings.get("izinli_eposta_alanlari"))
        kvkk = st.text_area("KVKK aydınlatma / açık rıza metni", settings.get("kvkk_metni"), height=100)

        st.subheader("Yetkinlik kataloğu")
        katalog = st.text_area("Her satıra bir yetkinlik", "\n".join(settings.get("yetkinlik_katalogu") or []), height=200)
        st.subheader("Başvuru rehberi (onaylanan ekiplere gönderilir, Markdown)")
        rehber = st.text_area("Rehber", settings.get("basvuru_rehberi"), height=260, label_visibility="collapsed")
        if st.form_submit_button("Ayarları kaydet", type="primary"):
            degerler = {
                "kurum_adi": kurum, "universite_adi": uni, "aktif_donem": donem.strip(),
                "bolumler": [x.strip() for x in bolumler.splitlines() if x.strip()],
                "max_kota_2209": int(kota), "max_kota_bitirme": int(kota_b), "max_ekip_2209": int(ekip), "max_ekip_bitirme": int(ekip_b),
                "butce_limit_2209a": int(lim_a), "butce_limit_2209b": int(lim_b), "max_sure_ay": int(sure), "min_gno": float(gno),
                "otomatik_davet": oto, "davet_aday_sayisi": int(aday), "davet_gecerlilik_gun": int(gecer), "teknofest_esik": int(esik),
                "hatirlatma_gunleri": hatir, "taslak_kontrol_gun": int(taslak), "ogrenci_kayit_acik": ogr_kayit,
                "hoca_sanayi_onay_gerekli": onay, "izinli_eposta_alanlari": alan, "kvkk_metni": kvkk,
                "yetkinlik_katalogu": [x.strip() for x in katalog.splitlines() if x.strip()], "basvuru_rehberi": rehber,
            }
            if not settings.env_overridden("uygulama_url"):
                degerler["uygulama_url"] = url
            settings.save_many(degerler)
            log_islem(u.id, "ayar_guncelle", ", ".join(degerler))
            st.success("Ayarlar kaydedildi.")

# ---------------------------------------------------------------------------
with t_kul:
    with get_session() as s:
        kullanicilar = list(s.scalars(select(Kullanici).order_by(Kullanici.olusturma.desc())))
    bekleyen = [k for k in kullanicilar if not k.aktif and k.sifre_hash and k.son_giris is None and k.rol in ("hoca", "sanayi")]
    if bekleyen:
        st.subheader(f"Onay bekleyen hesaplar ({len(bekleyen)})")
        for k in bekleyen:
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.write(f"**{k.ad_soyad}** · {k.eposta} · {auth.ROLLER.get(k.rol)} · {k.kurum or k.bolum or ''}")
            if c2.button("Onayla", key=f"on_{k.id}", type="primary"):
                with get_session() as s:
                    s.get(Kullanici, k.id).aktif = True
                notifier.notify(k.id, "Hesabınız onaylandı", "Proje Kuluçka sistemine artık giriş yapabilirsiniz.")
                st.rerun()
            if c3.button("Reddet", key=f"red_{k.id}"):
                try:
                    with get_session() as s:
                        s.delete(s.get(Kullanici, k.id))
                except IntegrityError:
                    # Pasife alınmış eski hesaplar da bu listede görünür; ilişkili kayıtları olduğu için silinemez
                    st.error(f"{k.ad_soyad} silinemedi: hesaba bağlı başvuru/bildirim/oturum kayıtları var. Hesap pasif bırakıldı.")
                else:
                    st.rerun()
        st.divider()

    f1, f2 = st.columns([1, 2])
    rol_f = f1.multiselect("Rol", list(auth.ROLLER), format_func=auth.ROLLER.get, placeholder="Tümü")
    ara = f2.text_input("Ara (ad / e-posta)")
    liste = [k for k in kullanicilar if (not rol_f or k.rol in rol_f) and (not ara or ara.lower() in f"{k.ad_soyad} {k.eposta}".lower())]
    df = pd.DataFrame([{"id": k.id, "Ad Soyad": k.ad_soyad, "E-posta": k.eposta, "Rol": k.rol, "Bölüm/Kurum": k.bolum or k.kurum or "",
                        "Aktif": k.aktif, "ARBİS": k.arbis_kaydi, "Yetkinlik": len(k.yetkinlikler or []),
                        "Son giriş": ui.tarih(k.son_giris) if k.son_giris else "—"} for k in liste])
    if not df.empty:
        ed = st.data_editor(df, hide_index=True, width="stretch", disabled=["id", "E-posta", "Yetkinlik", "Son giriş", "ARBİS"],
                            column_config={"Rol": st.column_config.SelectboxColumn("Rol", options=list(auth.ROLLER)),
                                           "Aktif": st.column_config.CheckboxColumn("Aktif")}, key="kul_ed")
        if st.button("Değişiklikleri kaydet"):
            with get_session() as s:
                for r in ed.to_dict("records"):
                    k = s.get(Kullanici, int(r["id"]))
                    if k.id == u.id and (r["Rol"] != "admin" or not r["Aktif"]):
                        continue  # kendini kilitlemeyi önle
                    # Boşaltılan hücreler NOT NULL sütunlara None yazmasın
                    k.ad_soyad, k.rol, k.aktif = r["Ad Soyad"] or k.ad_soyad, r["Rol"] or k.rol, bool(r["Aktif"])
            ui.flash("Kaydedildi.")
            st.rerun()

    c1, c2 = st.columns(2)
    with c1.expander("🔑 Şifre sıfırla"):
        hedef = st.selectbox("Kullanıcı", kullanicilar, format_func=lambda k: f"{k.ad_soyad} ({k.eposta})", key="sifre_hedef")
        if st.button("Geçici şifre oluştur"):
            gecici = auth.random_password()
            auth.set_password(hedef.id, gecici, must_change=True)
            notifier.notify(hedef, "Şifreniz sıfırlandı", f"Geçici şifreniz: {gecici}\nİlk girişte yeni şifre belirlemeniz istenecek.",
                            kanallar=("eposta",))
            st.success(f"Geçici şifre: **{gecici}** (kullanıcıya e-posta ile de gönderildi, e-posta açıksa)")
    with c2.expander("➕ Tek kullanıcı ekle"):
        with st.form("tek_kul", clear_on_submit=True):
            ad = st.text_input("Ad Soyad")
            ep = st.text_input("E-posta")
            rol = st.selectbox("Rol", list(auth.ROLLER), format_func=auth.ROLLER.get)
            bol = st.text_input("Bölüm / Kurum")
            if st.form_submit_button("Ekle"):
                gecici = auth.random_password()
                user, err = auth.register_user(ad_soyad=ad, eposta=ep, sifre=gecici, rol=rol, aktif=True,
                                               bolum=bol if rol != "sanayi" else None, kurum=bol if rol == "sanayi" else None,
                                               sifre_degismeli=True)
                if err:
                    st.error(err)
                else:
                    notifier.notify(user, "Proje Kuluçka hesabınız oluşturuldu",
                                    f"E-posta: {user.eposta}\nGeçici şifre: {gecici}\nİlk girişte şifrenizi değiştirmeniz istenecek.",
                                    kanallar=("eposta",))
                    st.success(f"Eklendi. Geçici şifre: **{gecici}**")
    with st.expander("📥 Excel ile toplu kullanıcı yükle"):
        st.write("Öğrenci ve danışman listelerini tek seferde yükleyin. Her kullanıcıya geçici şifre üretilir; "
                 "e-posta açıksa şifreler otomatik gönderilir, değilse indirilen listeyi paylaşın.")
        st.download_button("Örnek şablon (.xlsx)", importer.ornek_excel("kullanici"), file_name="kullanici_sablonu.xlsx")
        dosya = st.file_uploader("Excel / CSV", type=["xlsx", "csv"], key="kul_up")
        if dosya and st.button("Yükle", type="primary"):
            sonuc, hatalar = importer.kullanicilari_ice_aktar(dosya)
            for h in hatalar:
                st.warning(h)
            if not sonuc.empty:
                with get_session() as s:
                    eklenenler = {k.eposta: k for k in s.scalars(select(Kullanici).where(Kullanici.eposta.in_(list(sonuc["eposta"]))))}
                for r in sonuc.to_dict("records"):
                    k = eklenenler.get(r["eposta"])
                    if k:
                        notifier.notify(k, "Proje Kuluçka hesabınız oluşturuldu",
                                        f"E-posta: {k.eposta}\nGeçici şifre: {r['gecici_sifre']}\nİlk girişte şifrenizi değiştirmeniz istenecek.",
                                        kanallar=("eposta",))
                st.success(f"{len(sonuc)} kullanıcı eklendi.")
                buf = io.BytesIO()
                sonuc.to_excel(buf, index=False)
                st.download_button("Geçici şifre listesini indir", buf.getvalue(), file_name=f"gecici_sifreler_{importer.zaman_damgasi()}.xlsx")

# ---------------------------------------------------------------------------
with t_ent:
    st.subheader("📧 E-posta (SMTP)")
    st.caption("Kurum e-posta sunucusu veya Gmail/Outlook uygulama şifresiyle çalışır. Şifreyi veritabanına yazmak istemezseniz "
               "`.env` dosyasında SMTP_SIFRE tanımlayın.")
    with st.form("smtp"):
        aktif = st.toggle("E-posta gönderimi açık", settings.get_bool("eposta_aktif"))
        c1, c2, c3 = st.columns([3, 1, 1.4])
        host = c1.text_input("SMTP sunucusu", settings.get("smtp_sunucu"), placeholder="smtp.gmail.com", disabled=settings.env_overridden("smtp_sunucu"))
        port = c2.number_input("Port", 1, 65535, settings.get_int("smtp_port"))
        guv = c3.selectbox("Güvenlik", ["STARTTLS", "SSL", "YOK"], index=["STARTTLS", "SSL", "YOK"].index(str(settings.get("smtp_guvenlik") or "STARTTLS")))
        c4, c5, c6 = st.columns(3)
        kul = c4.text_input("Kullanıcı adı", settings.get("smtp_kullanici"), disabled=settings.env_overridden("smtp_kullanici"))
        sif = c5.text_input("Şifre / uygulama şifresi", type="password", placeholder="değiştirmek için yazın",
                            disabled=settings.env_overridden("smtp_sifre"))
        gon = c6.text_input("Gönderen adresi", settings.get("smtp_gonderen"))
        if st.form_submit_button("Kaydet"):
            vals = {"eposta_aktif": aktif, "smtp_port": int(port), "smtp_guvenlik": guv, "smtp_gonderen": gon}
            if not settings.env_overridden("smtp_sunucu"):
                vals["smtp_sunucu"] = host
            if not settings.env_overridden("smtp_kullanici"):
                vals["smtp_kullanici"] = kul
            if sif and not settings.env_overridden("smtp_sifre"):
                vals["smtp_sifre"] = sif
            settings.save_many(vals)
            st.success("Kaydedildi.")
    test_adr = st.text_input("Test e-postası gönderilecek adres", u.eposta)
    if st.button("Test e-postası gönder"):
        try:
            notifier.send_email(test_adr, "Proje Kuluçka test e-postası", "E-posta ayarlarınız çalışıyor. ✅")
            st.success("Gönderildi.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Gönderilemedi: {exc}")

    st.divider()
    st.subheader("💬 Telegram botu")
    st.caption("Telegram'da @BotFather ile bir bot oluşturun, token'ı buraya girin. Kullanıcılar Profilim > Bildirim kanalları "
               "bölümündeki kodla hesaplarını bağlar.")
    with st.form("tg"):
        tg_aktif = st.toggle("Telegram bildirimleri açık", settings.get_bool("telegram_aktif"))
        c1, c2 = st.columns(2)
        tok = c1.text_input("Bot token", type="password", placeholder="değiştirmek için yazın", disabled=settings.env_overridden("telegram_token"))
        bot = c2.text_input("Bot kullanıcı adı", settings.get("telegram_bot_adi"), placeholder="@kurum_proje_bot")
        if st.form_submit_button("Kaydet"):
            vals = {"telegram_aktif": tg_aktif, "telegram_bot_adi": bot.lstrip("@")}
            if tok and not settings.env_overridden("telegram_token"):
                vals["telegram_token"] = tok
            settings.save_many(vals)
            st.success("Kaydedildi.")
    if st.button("Bağlantı eşleştirmesini şimdi çalıştır"):
        try:
            st.success(f"{notifier.telegram_sync()} kullanıcı bağlandı.")
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    st.divider()
    st.subheader("📁 Google Drive")
    st.markdown(
        "- **Hizmet hesabı (önerilen, Google Workspace):** Google Cloud Console'da Drive API'yi açın, bir hizmet hesabı ve JSON anahtarı "
        "oluşturun. Bir **Paylaşılan Drive** açıp hizmet hesabının e-postasını *İçerik yöneticisi* olarak ekleyin ve o Drive'daki "
        "ana klasörün ID'sini aşağıya yazın. (Hizmet hesaplarının kişisel depolama kotası yoktur.)\n"
        "- **Kullanıcı hesabı (OAuth):** OAuth istemci JSON'unu yükleyin ve sunucuda bir kez "
        "`python manage.py drive-yetkilendir` komutunu çalıştırın.")
    with st.form("drive"):
        d_aktif = st.toggle("Google Drive entegrasyonu açık", settings.get_bool("drive_aktif"))
        mod = st.radio("Bağlantı türü", ["service_account", "oauth"], horizontal=True,
                       index=0 if settings.get("drive_mod") != "oauth" else 1,
                       format_func={"service_account": "Hizmet hesabı", "oauth": "Kullanıcı hesabı (OAuth)"}.get)
        kok = st.text_input("Ana klasör ID'si", settings.get("drive_ana_klasor_id"), help="Klasör adresindeki /folders/ sonrasındaki kısım")
        donustur = st.toggle("Word taslaklarını Google Dokümanlar'a dönüştür (ortak düzenleme için)", settings.get_bool("drive_docs_donustur"))
        bildir = st.toggle("Paylaşımda Google'ın bildirim e-postası gönderilsin", settings.get_bool("drive_paylasim_bildirimi"))
        jf = st.file_uploader("Kimlik JSON dosyası (hizmet hesabı anahtarı veya OAuth istemcisi)", type=["json"])
        if st.form_submit_button("Kaydet"):
            vals = {"drive_aktif": d_aktif, "drive_mod": mod, "drive_ana_klasor_id": kok.strip(), "drive_docs_donustur": donustur,
                    "drive_paylasim_bildirimi": bildir}
            if jf is not None:
                hedef = config.SECRETS_DIR / ("drive_service_account.json" if mod == "service_account" else "drive_oauth_client.json")
                hedef.write_bytes(jf.getvalue())
                if mod == "service_account":
                    vals["drive_kimlik_dosyasi"] = str(hedef)
            settings.save_many(vals)
            st.success("Kaydedildi.")
    if st.button("Drive bağlantısını test et"):
        try:
            from modules import drive
            st.success(f"Bağlantı başarılı: {drive.test_connection()}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Bağlantı kurulamadı: {exc}")

# ---------------------------------------------------------------------------
with t_takvim:
    st.subheader("Çağrı ve son tarih takvimi")
    st.caption("TÜBİTAK, bitirme ve kurum içi son tarihler. 'Hedef' sütunu kimlerin hatırlatma alacağını belirler: "
               "ilgili = o programdaki proje ekipleri ve danışmanları.")
    with get_session() as s:
        cagrilar = list(s.scalars(select(CagriTakvimi).order_by(CagriTakvimi.bitis)))
    cdf = pd.DataFrame([{"id": c.id, "baslik": c.baslik, "program": c.program, "baslangic": c.baslangic, "bitis": c.bitis,
                         "hedef_rol": c.hedef_rol, "url": c.url or "", "sil": False} for c in cagrilar],
                       columns=["id", "baslik", "program", "baslangic", "bitis", "hedef_rol", "url", "sil"])
    ced = st.data_editor(cdf, num_rows="dynamic", hide_index=True, width="stretch", key="cagri_ed",
                         column_config={
                             "id": None,
                             "baslik": st.column_config.TextColumn("Başlık", width="large", required=True),
                             "program": st.column_config.SelectboxColumn("Program", options=["2209-A/B", "2209-A", "2209-B", "Bitirme", "TEKNOFEST", "Diğer"], required=True),
                             "baslangic": st.column_config.DatetimeColumn("Başlangıç", format="DD.MM.YYYY HH:mm"),
                             "bitis": st.column_config.DatetimeColumn("Son tarih", format="DD.MM.YYYY HH:mm", required=True),
                             "hedef_rol": st.column_config.SelectboxColumn("Hedef", options=["ilgili", "tum_ogrenciler", "hocalar", "herkes"]),
                             "url": st.column_config.LinkColumn("Bağlantı"),
                             "sil": st.column_config.CheckboxColumn("Sil"),
                         })
    if st.button("Takvimi kaydet", type="primary"):
        with get_session() as s:
            mevcut = {c.id: c for c in s.scalars(select(CagriTakvimi))}
            for r in ced.to_dict("records"):
                if not r.get("baslik") or pd.isna(r.get("bitis")):
                    continue
                cid = r.get("id")
                if cid is not None and not pd.isna(cid) and int(cid) in mevcut:
                    c = mevcut[int(cid)]
                    if r.get("sil"):
                        s.delete(c)
                        continue
                else:
                    if r.get("sil"):
                        continue
                    c = CagriTakvimi(kaynak="manuel")
                    s.add(c)
                c.baslik, c.program = r["baslik"], r.get("program") or "Diğer"
                c.baslangic = None if pd.isna(r.get("baslangic")) else pd.Timestamp(r["baslangic"]).to_pydatetime()
                c.bitis = pd.Timestamp(r["bitis"]).to_pydatetime()
                c.hedef_rol = r.get("hedef_rol") or "ilgili"
                c.url = r.get("url") or None
        ui.flash("Takvim kaydedildi.")
        st.rerun()
    with st.expander("📥 Excel ile takvim yükle"):
        st.download_button("Örnek şablon", importer.ornek_excel("takvim"), file_name="takvim_sablonu.xlsx")
        tf = st.file_uploader("Excel / CSV", type=["xlsx", "csv"], key="takvim_up")
        if tf and st.button("Takvimi yükle"):
            n, hatalar = importer.takvimi_ice_aktar(tf)
            st.success(f"{n} kayıt eklendi.")
            for h in hatalar:
                st.warning(h)

    st.subheader("TEKNOFEST tarayıcı")
    with st.form("tarama"):
        c1, c2, c3 = st.columns(3)
        gunler = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        gun_ad = dict(zip(gunler, ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]))
        gun = c1.selectbox("Haftalık tarama günü", gunler, index=gunler.index(settings.get("teknofest_tarama_gunu") or "mon"), format_func=gun_ad.get)
        saat = c2.number_input("Saat", 0, 23, settings.get_int("teknofest_tarama_saati"))
        gecikme = c3.number_input("İstekler arası bekleme (sn)", 0.0, 10.0, settings.get_float("teknofest_tarama_gecikme"), 0.5)
        liste_url = st.text_input("Yarışma listesi adresi", settings.get("teknofest_liste_url"))
        if st.form_submit_button("Kaydet"):
            settings.save_many({"teknofest_tarama_gunu": gun, "teknofest_tarama_saati": int(saat), "teknofest_tarama_gecikme": float(gecikme),
                                "teknofest_liste_url": liste_url})
            st.success("Kaydedildi. Zamanlama değişikliği uygulama/worker yeniden başlatıldığında geçerli olur.")
    ozet = settings.get("son_tarama_ozet")
    if ozet:
        st.caption(f"Son tarama: {ozet.get('tarih')} · {ozet.get('bulunan')} yarışma · {len(ozet.get('hatalar', []))} uyarı")
        if ozet.get("hatalar"):
            with st.expander("Tarama uyarıları"):
                for h in ozet["hatalar"]:
                    st.write("- " + h)

    st.subheader("Görevleri elle çalıştır")
    g1, g2, g3, g4 = st.columns(4)
    if g1.button("🛰️ TEKNOFEST tara", width="stretch"):
        bar = st.progress(0.0)
        o = teknofest_scraper.run_scrape(progress=lambda x, m: bar.progress(min(1.0, x), m))
        st.success(f"{o['bulunan']} yarışma, {len(o['hatalar'])} uyarı")
    if g2.button("⏰ Hatırlatmaları gönder", width="stretch"):
        st.success(f"{automation.hatirlatmalari_gonder()} bildirim gönderildi (daha önce gönderilenler tekrarlanmaz).")
    if g3.button("📝 Taslak kontrolü", width="stretch"):
        st.success(f"{automation.taslak_kontrolu()} uyarı gönderildi.")
    if g4.button("⌛ Davet süreleri", width="stretch"):
        st.success(f"{automation.davet_suresi_kontrol()} davetin süresi doldu.")

# ---------------------------------------------------------------------------
with t_sablon:
    st.write("Sistem varsayılan Word şablonlarıyla gelir. Kurumunuzun formatını kullanmak için şablonu indirip Word'de düzenleyin "
             "ve `{{ degisken }}` yer tutucularını koruyarak geri yükleyin.")
    for tur, ad in doc_generator.SABLONLAR.items():
        yol = doc_generator.template_path(tur)
        ozel = yol.parent == config.CUSTOM_TEMPLATE_DIR
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1.3, 2])
            c1.markdown(f"**{tur}** · `{ad}` " + (":violet-badge[Kurum şablonu]" if ozel else ":gray-badge[Varsayılan]"))
            c2.download_button("İndir", yol.read_bytes(), file_name=ad, key=f"sd_{tur}")
            up = c3.file_uploader("Yeni şablon", type=["docx"], key=f"su_{tur}", label_visibility="collapsed")
            if up is not None and c3.button("Yükle", key=f"sub_{tur}"):
                gecici = config.CUSTOM_TEMPLATE_DIR / f"_test_{ad}"
                gecici.write_bytes(up.getvalue())
                ok, bilgi = doc_generator.validate_template(str(gecici))
                if ok:
                    shutil.move(gecici, config.CUSTOM_TEMPLATE_DIR / ad)
                    ui.flash("Şablon yüklendi." + (f" Kullanılan değişkenler: {bilgi}" if bilgi else ""))
                    st.rerun()
                else:
                    gecici.unlink(missing_ok=True)
                    st.error(f"Şablon işlenemedi: {bilgi}")
            if ozel and c1.button("Varsayılana dön", key=f"sr_{tur}"):
                (config.CUSTOM_TEMPLATE_DIR / ad).unlink(missing_ok=True)
                st.rerun()
    with st.expander("Kullanılabilir değişkenler"):
        for grup, degiskenler in doc_generator.SABLON_DEGISKENLERI.items():
            st.markdown(f"**{grup}:** `{degiskenler}`")
        st.markdown("Tablo satırı döngüsü örneği: bir satıra `{%tr for r in is_plani %}`, sonraki satıra `{{ r.is_paketi }}` … , "
                    "en alta `{%tr endfor %}` yazın.")

# ---------------------------------------------------------------------------
with t_kayit:
    st.subheader("Giden bildirimler")
    with get_session() as s:
        rows = s.execute(select(Bildirim, Kullanici).join(Kullanici, Kullanici.id == Bildirim.kullanici_id, isouter=True)
                         .where(Bildirim.kanal != "uygulama").order_by(Bildirim.olusturma.desc()).limit(500)).all()
    durum_f = st.multiselect("Durum", ["Gonderildi", "Simule", "Hata"], placeholder="Tümü")
    bdf = pd.DataFrame([{"Tarih": ui.tarih(b.olusturma), "Kanal": b.kanal, "Alıcı": k.eposta if k else "", "Konu": b.konu,
                         "Durum": b.durum, "Hata": b.hata or ""} for b, k in rows if not durum_f or b.durum in durum_f])
    st.caption("'Simule' = e-posta/Telegram kapalıyken oluşan mesaj; alıcı yine de uygulama içinde görür.")
    st.dataframe(bdf, hide_index=True, width="stretch", height=320)
    st.subheader("İşlem günlüğü")
    with get_session() as s:
        logs = list(s.scalars(select(IslemLog).order_by(IslemLog.tarih.desc()).limit(500)))
    st.dataframe(pd.DataFrame([{"Tarih": ui.tarih(l.tarih), "Kullanıcı": l.kullanici_id, "İşlem": l.islem, "Ayrıntı": l.detay} for l in logs]),
                 hide_index=True, width="stretch", height=320)

# ---------------------------------------------------------------------------
with t_yedek:
    st.subheader("Yedekleme")
    if config.DATABASE_URL.startswith("sqlite"):
        db_yolu = Path(config.DATABASE_URL.replace("sqlite:///", ""))
        if st.button("Veritabanı yedeği oluştur"):
            import sqlite3
            hedef = config.BACKUP_DIR / f"myo_otomasyon_{dt.datetime.now():%Y%m%d_%H%M}.db"
            src = sqlite3.connect(db_yolu)
            dst = sqlite3.connect(hedef)
            src.backup(dst)
            dst.close()
            src.close()
            st.session_state["son_yedek"] = str(hedef)
            st.success(f"Yedek oluşturuldu: {hedef.name}")
        if st.session_state.get("son_yedek") and Path(st.session_state["son_yedek"]).exists():
            p = Path(st.session_state["son_yedek"])
            st.download_button("Yedeği indir", p.read_bytes(), file_name=p.name)
    else:
        st.caption("PostgreSQL kullanıyorsunuz; yedekleme için pg_dump kullanın.")
    st.download_button("📊 Tüm verileri Excel olarak indir (rapor)", importer.tum_veriyi_disa_aktar(),
                       file_name=f"proje_kulucka_rapor_{importer.zaman_damgasi()}.xlsx")

    st.subheader("Demo verisi")
    c1, c2 = st.columns(2)
    if c1.button("Demo verisi yükle"):
        r = seed.seed_demo()
        st.success(f"Demo kullanıcılar hazır (şifre: {r['sifre']}). Ör. ayse@demo.local, hoca@demo.local")
    if c2.button("Demo verisini sil", type="primary"):
        r = seed.remove_demo()
        ui.flash(f"{r['kullanici']} demo kullanıcı ve {r['proje']} demo proje silindi.")
        st.rerun()
