import json
from pathlib import Path

import streamlit as st
from sqlalchemy import select

from modules import auth, automation, notifier, project_editor, rules, settings, ui
from modules.database import Bildirim, Kullanici, TakimEslesmesi, get_session, log_islem, now
from modules.text_utils import fold

u = ui.require_user()
st.title("👤 Profilim")

sekmeler = ["Bilgilerim"]
if u.rol == "ogrenci":
    sekmeler += ["📩 Davetlerim", "📨 Başvurularım", "🤝 Takımım"]
sekmeler += ["🔔 Bildirim kanalları", "🔐 Güvenlik ve KVKK"]
tabs = dict(zip(sekmeler, st.tabs(sekmeler)))

# ---------------------------------------------------------------------------
with tabs["Bilgilerim"]:
    with st.form("profil"):
        c1, c2 = st.columns(2)
        ad = c1.text_input("Ad Soyad", u.ad_soyad)
        c2.text_input("E-posta", u.eposta, disabled=True)
        bolumler = list(dict.fromkeys((settings.get("bolumler") or []) + ([u.bolum] if u.bolum else [])))
        guncel = {}
        if u.rol == "ogrenci":
            c3, c4, c5 = st.columns(3)
            guncel["bolum"] = c3.selectbox("Program / Bölüm", bolumler, index=bolumler.index(u.bolum) if u.bolum in bolumler else 0)
            siniflar = ["1", "2", "Mezuniyet aşaması"]
            guncel["sinif"] = c4.selectbox("Sınıf", siniflar, index=siniflar.index(u.sinif) if u.sinif in siniflar else 0)
            guncel["ogrenim_turu"] = c5.selectbox("Öğrenim türü", rules.OGRENIM_TURLERI,
                                                  index=rules.OGRENIM_TURLERI.index(u.ogrenim_turu) if u.ogrenim_turu in rules.OGRENIM_TURLERI else 0)
            c6, c7, c8 = st.columns(3)
            guncel["ogrenci_no"] = c6.text_input("Öğrenci no", u.ogrenci_no or "")
            guncel["gno"] = c7.number_input("GNO", 0.0, 4.0, float(u.gno or 0), 0.01)
            guncel["telefon"] = c8.text_input("Telefon (isteğe bağlı)", u.telefon or "")
            guncel["davet_almak_istiyor"] = st.toggle("Yetkinliklerime uygun projelerden otomatik takım daveti almak istiyorum",
                                                      value=u.davet_almak_istiyor)
        elif u.rol in ("hoca", "admin"):
            c3, c4 = st.columns(2)
            guncel["unvan"] = c3.text_input("Unvan", u.unvan or "")
            guncel["bolum"] = c4.selectbox("Bölüm", bolumler, index=bolumler.index(u.bolum) if u.bolum in bolumler else 0)
            guncel["yoksis_guncel"] = st.checkbox("YÖKSİS kaydım güncel (2209 danışmanlığı için zorunlu)", value=u.yoksis_guncel)
        else:
            guncel["kurum"] = st.text_input("Firma / Kuruluş", u.kurum or "")
            guncel["telefon"] = st.text_input("Telefon", u.telefon or "")
        katalog = list(dict.fromkeys((settings.get("yetkinlik_katalogu") or []) + list(u.yetkinlikler or [])))
        guncel["yetkinlikler"] = st.multiselect("Yetkinliklerim", katalog, default=u.yetkinlikler or [], accept_new_options=True, placeholder="Seçin veya yazıp Enter ile ekleyin",
                                                help="Projelerle eşleştirme ve takım davetleri bu listeye göre yapılır.")
        guncel["arbis_kaydi"] = st.checkbox("ARBİS kaydım var ve güncel (arbis.tubitak.gov.tr)", value=u.arbis_kaydi)
        if st.form_submit_button("Kaydet", type="primary"):
            with get_session() as s:
                uu = s.get(Kullanici, u.id)
                uu.ad_soyad = ad.strip() or uu.ad_soyad
                for k, v in guncel.items():
                    setattr(uu, k, v)
            ui.flash("Profil güncellendi.")
            st.rerun()
    st.link_button("ARBİS'e git", "https://arbis.tubitak.gov.tr")

# ---------------------------------------------------------------------------
if u.rol == "ogrenci":
    with tabs["📩 Davetlerim"]:
        acik = st.session_state.get("acik_davet")
        if acik:
            d = automation.davet_token_bul(acik)
            if not d or d.ogrenci_id != u.id:
                st.warning("Bağlantıdaki davet bu hesaba ait değil veya bulunamadı.")
            st.session_state.pop("acik_davet", None)
        davetler = automation.ogrenci_davetleri(u.id)
        if not davetler:
            st.info("Henüz davetiniz yok. Yetkinliklerinizi güncel tutun; eksik yetkinlik arayan projeler sizi otomatik davet eder.")
        for d, p in davetler:
            with st.container(border=True):
                a, c = st.columns([4, 1.4])
                a.markdown(f"{ui.tur_rozet(p.tur)} **{ui.esc(p.baslik)}**  \n"
                           f"<span class='soluk'>Aranan yetkinliğiniz: {ui.esc(', '.join(d.yetkinlikler or []))} · {ui.tarih(d.tarih)}</span>",
                           unsafe_allow_html=True)
                if p.ozet:
                    a.caption(p.ozet[:300] + ("…" if len(p.ozet) > 300 else ""))
                if d.durum == "Gonderildi":
                    if c.button("Kabul et", key=f"dk_{d.id}", type="primary", width="stretch"):
                        res = automation.davet_yanitla(d.id, u, True)
                        ui.flash(res.mesaj, "success" if res.ok else "error")
                        st.rerun()
                    if c.button("Reddet", key=f"dr_{d.id}", width="stretch"):
                        automation.davet_yanitla(d.id, u, False)
                        st.rerun()
                else:
                    c.markdown({"Kabul": ":green-badge[Kabul ettiniz]", "Ret": ":gray-badge[Reddettiniz]",
                                "Suresi Doldu": ":gray-badge[Süresi doldu]"}.get(d.durum, d.durum))

    with tabs["📨 Başvurularım"]:
        kayitlar = automation.ogrenci_projeleri(u.id)
        if not kayitlar:
            st.info("Henüz başvurunuz yok. Proje Panosu'ndan size uygun ilanlara başvurabilirsiniz.")
        for b, p in kayitlar:
            with st.container(border=True):
                a, c = st.columns([4, 1.4])
                a.markdown(f"{ui.tur_rozet(p.tur)} **{ui.esc(p.baslik)}**  \n<span class='soluk'>{ui.tarih(b.tarih)} · Uyum %{b.uyum_skoru:g}</span>",
                           unsafe_allow_html=True)
                renk = {"Beklemede": "orange", "Kabul": "green", "Ret": "gray", "Geri Cekildi": "gray"}.get(b.durum, "gray")
                etiket = {"Geri Cekildi": "Geri çekildi", "Kabul": "Kabul edildi", "Ret": "Olumsuz"}.get(b.durum, b.durum)
                c.markdown(f":{renk}-badge[{etiket}]")
                if b.durum == "Beklemede" and c.button("Geri çek", key=f"gc_{b.id}", width="stretch"):
                    automation.basvuru_geri_cek(b.id, u.id)
                    st.rerun()

    with tabs["🤝 Takımım"]:
        takimlar = [(b, p) for b, p in automation.ogrenci_projeleri(u.id) if b.durum == "Kabul" and p.durum != "Iptal"]
        if not takimlar:
            st.info("Henüz bir proje ekibinde değilsiniz.")
        for b, p in takimlar:
            st.subheader(f"{p.kod} · {p.baslik}")
            st.markdown(f"{ui.tur_rozet(p.tur)} {ui.durum_rozet(p.durum)}")
            ctx = automation.proje_baglami(p.id)
            st.write("**Ekip:** " + ", ".join(x.ad_soyad for x in ctx["ekip"]) +
                     (f" · **Danışman:** {ctx['danisman'].ad_soyad}" if ctx["danisman"] else ""))
            with get_session() as s:
                t = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == p.id))
            if t and t.belgeler:
                if t.drive_klasor_url:
                    st.link_button("📂 Google Drive klasörü", t.drive_klasor_url)
                if t.bos_alan_sayisi:
                    st.warning(f"Taslaklarda {t.bos_alan_sayisi} adet [DOLDURULACAK] alanı var.")
                for i, d in enumerate(t.belgeler):
                    c1, c2, c3 = st.columns([3, 1, 2])
                    c1.write(d["ad"])
                    if d.get("drive_url"):
                        c2.link_button("Aç", d["drive_url"])
                    elif Path(d["yol"]).exists():
                        c2.download_button("İndir", Path(d["yol"]).read_bytes(), file_name=Path(d["yol"]).name, key=f"td_{p.id}_{i}")
                        if d["tur"] != "kontrol":
                            up = c3.file_uploader("Düzenlenmiş hâlini yükle (.docx)", type=["docx"], key=f"tu_{p.id}_{i}")
                            if up is not None and c3.button("Yükle", key=f"tub_{p.id}_{i}"):
                                ui.flash(automation.belge_guncelle(p.id, i, up.getvalue(), u.id).mesaj)
                                st.rerun()
            else:
                st.caption("Danışman 'Onayla ve Kur' dediğinde proje klasörü ve taslaklar burada görünecek.")
            if p.tur in rules.TUBITAK_TURLERI:
                with st.expander("✅ TÜBİTAK ön kontrol"):
                    ui.kontrol_tablosu(automation.on_kontrol(p.id))
            with st.expander("📝 Proje içeriğini ekip olarak düzenle"):
                project_editor.icerik_duzenleyici(p, u.id, duzenleyebilir=p.durum not in ("Sonuclandi", "Iptal"))
            st.divider()

# ---------------------------------------------------------------------------
with tabs["🔔 Bildirim kanalları"]:
    st.write(f"E-posta: **{u.eposta}** " + ("✅ (sistem e-postası açık)" if notifier.smtp_hazir() else "— sistem e-postası henüz yapılandırılmadı, bildirimler yalnızca uygulama içinde görünür."))
    st.subheader("Telegram")
    if not notifier.telegram_hazir():
        st.caption("Telegram botu yönetici tarafından henüz etkinleştirilmedi.")
    elif u.telegram_chat_id:
        st.success("Telegram hesabınız bağlı.")
        if st.button("Bağlantıyı kaldır"):
            with get_session() as s:
                s.get(Kullanici, u.id).telegram_chat_id = None
            st.rerun()
    else:
        kod = u.telegram_kod
        if not kod:
            kod = auth.telegram_code()
            with get_session() as s:
                s.get(Kullanici, u.id).telegram_kod = kod
        bot = str(settings.get("telegram_bot_adi") or "").lstrip("@")
        st.markdown(f"1. Telegram'da **@{bot or 'kurum_botu'}** botunu açın\n2. Bota şu mesajı gönderin: `/start {kod}`\n3. Aşağıdaki düğmeye basın")
        if bot:
            st.link_button("Botu aç", f"https://t.me/{bot}?start={kod}")
        if st.button("Bağlantıyı kontrol et"):
            try:
                notifier.telegram_sync()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Telegram'a ulaşılamadı: {exc}")
            st.rerun()

# ---------------------------------------------------------------------------
with tabs["🔐 Güvenlik ve KVKK"]:
    with st.form("sifre"):
        eski = st.text_input("Mevcut şifre", type="password")
        y1 = st.text_input("Yeni şifre", type="password")
        y2 = st.text_input("Yeni şifre (tekrar)", type="password")
        if st.form_submit_button("Şifreyi değiştir"):
            if not auth.verify_password(eski, u.sifre_hash):
                st.error("Mevcut şifre hatalı.")
            elif y1 != y2:
                st.error("Yeni şifreler eşleşmiyor.")
            elif auth.password_problem(y1):
                st.error(auth.password_problem(y1))
            else:
                auth.set_password(u.id, y1)
                st.success("Şifre değiştirildi.")
    st.subheader("Kişisel verilerim")
    st.caption(f"KVKK onayı: {ui.tarih(u.kvkk_tarih) if u.kvkk_tarih else '—'}")
    with get_session() as s:
        uu = s.get(Kullanici, u.id)
        veri = {c.name: getattr(uu, c.name) for c in Kullanici.__table__.columns if c.name not in ("sifre_hash", "sifre_sifirlama_kod")}
        veri["bildirimler"] = [{"konu": b.konu, "tarih": str(b.olusturma), "kanal": b.kanal}
                               for b in s.scalars(select(Bildirim).where(Bildirim.kullanici_id == u.id))]
    st.download_button("Verilerimi indir (JSON)", json.dumps(veri, ensure_ascii=False, indent=2, default=str),
                       file_name="kisisel_verilerim.json", mime="application/json")
    if u.rol != "admin":
        with st.expander("Hesabımı sil"):
            st.write("Hesabınız kapatılır; ad, e-posta ve iletişim bilgileriniz anonimleştirilir. Tamamlanmış proje kayıtlarındaki "
                     "ekip bilgisi 'Silinmiş kullanıcı' olarak görünür.")
            onay = st.text_input("Onaylamak için SİL yazın")
            if st.button("Hesabımı kalıcı olarak sil", type="primary", disabled=fold(onay.strip()) != "sil"):
                with get_session() as s:
                    uu = s.get(Kullanici, u.id)
                    uu.ad_soyad, uu.eposta = "Silinmiş kullanıcı", f"silindi-{uu.id}@silindi.local"
                    uu.telefon = uu.ogrenci_no = uu.telegram_chat_id = None
                    uu.aktif, uu.davet_almak_istiyor = False, False
                    uu.sifre_hash = ""
                log_islem(u.id, "hesap_silme", str(now()))
                ui.logout()
