import io
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import select

from modules import automation, matcher, project_editor, rules, settings, ui
from modules.database import Davet, Kullanici, Proje, TakimEslesmesi, get_session
from modules.text_utils import skill_set

u = ui.require_user(("hoca", "sanayi"))
st.title("🧭 Danışman Onay ve Otomasyon Paneli")
donem = str(settings.get("aktif_donem"))

# ---------------------------------------------------------------------------
# Kota
# ---------------------------------------------------------------------------
if u.rol in ("hoca", "admin"):
    k1, k2, k3 = st.columns(3)
    for col, tur, ad in ((k1, "2209-A", "TÜBİTAK 2209-A/B"), (k2, "Bitirme", "Bitirme")):
        uygun, sayi, limit = rules.kota_uygun_mu(u.id, tur, donem)
        col.metric(f"{ad} kotası ({donem})", f"{sayi}/{limit}", help="Açık, ekibi tamam, onaylı, başvurulmuş ve sonuçlanmış ilanlar sayılır.")
        col.progress(min(1.0, sayi / max(1, limit)))
    with get_session() as s:
        yedek = list(s.scalars(select(Proje).where(Proje.danisman_id == u.id, Proje.durum == "Yedek Havuz")))
    k3.metric("Yedek havuzdaki ilanlarım", len(yedek))

# ---------------------------------------------------------------------------
# Proje listesi
# ---------------------------------------------------------------------------
if u.rol == "admin":
    sadece_benim = st.toggle("Yalnızca danışmanı olduğum projeler", value=False)
    with get_session() as s:
        projeler = list(s.scalars(select(Proje).order_by(Proje.olusturma.desc())))
    if sadece_benim:
        projeler = [p for p in projeler if p.danisman_id == u.id]
else:
    projeler = automation.hoca_projeleri(u.id)

if not projeler:
    st.info("Henüz projeniz yok. **Proje Panosu > Yeni İlan** sekmesinden ilk ilanınızı oluşturun.")
    st.stop()

ozet_rows = []
for p in projeler:
    bas = automation.proje_basvurulari(p.id)
    ozet_rows.append({"Kod": p.kod, "Başlık": p.baslik, "Tür": p.tur, "Durum": rules.DURUM_ETIKET.get(p.durum, p.durum),
                      "Ekip": f"{sum(1 for b, _ in bas if b.durum == 'Kabul')}/{p.max_ekip}",
                      "Bekleyen başvuru": sum(1 for b, _ in bas if b.durum == "Beklemede"), "Sonuç": p.sonuc})
st.dataframe(pd.DataFrame(ozet_rows), hide_index=True, width="stretch", height=min(320, 38 + 35 * len(ozet_rows)))

secili_id = st.session_state.get("danisman_secili")
ids = [p.id for p in projeler]
idx = ids.index(secili_id) if secili_id in ids else 0
p = st.selectbox("Proje seçin", projeler, index=idx, format_func=lambda x: f"{x.kod} · {x.baslik[:90]} ({rules.DURUM_ETIKET.get(x.durum, x.durum)})")
st.session_state["danisman_secili"] = p.id
karar_yetkisi = u.rol == "admin" or p.danisman_id == u.id
icerik_yetkisi = karar_yetkisi or p.sanayi_danisman_id == u.id or p.olusturan_id == u.id

st.markdown(f"{ui.tur_rozet(p.tur)} {ui.durum_rozet(p.durum)} :gray-badge[{p.kod}] :gray-badge[Sonuç: {p.sonuc}]")
if not karar_yetkisi:
    st.caption("Bu projede kabul/ret ve 'Onayla ve Kur' kararlarını akademik danışman verir; siz içeriği düzenleyebilir ve süreci izleyebilirsiniz.")

t_ekip, t_icerik, t_kontrol, t_kur, t_durum = st.tabs(["👥 Başvurular & Ekip", "📝 İçerik (TYBS)", "✅ Ön Kontrol", "⚙️ Onayla ve Kur", "🏁 Durum & Sonuç"])

# ---------------------------------------------------------------------------
# Başvurular & ekip
# ---------------------------------------------------------------------------
with t_ekip:
    basvurular = automation.proje_basvurulari(p.id)
    bekleyen = [(b, o) for b, o in basvurular if b.durum == "Beklemede"]
    ekip = [(b, o) for b, o in basvurular if b.durum == "Kabul"]
    st.subheader(f"Bekleyen başvurular ({len(bekleyen)})")
    if not bekleyen:
        st.caption("Bekleyen başvuru yok.")
    for b, o in bekleyen:
        with st.container(border=True):
            a, c = st.columns([4, 1.4])
            a.markdown(f"**{ui.esc(o.ad_soyad)}** · {ui.esc(o.bolum or '')} · Sınıf {o.sinif or '-'} · GNO {o.gno or '-'} · {o.ogrenim_turu or ''}"
                       + (" :violet-badge[Davetle geldi]" if b.kaynak == "davet" else ""))
            a.markdown(ui.chips(o.yetkinlikler, ok=set(skill_set(p.aranan_yetkinlikler))), unsafe_allow_html=True)
            if b.motivasyon:
                a.caption(f"“{b.motivasyon}”")
            for kk in rules.ogrenci_uygunlugu(o, p):
                (a.error if kk.seviye == "hata" else a.warning)(f"{kk.alan}: {kk.mesaj}")
            c.metric("Uyum", f"%{b.uyum_skoru:g}")
            if karar_yetkisi:
                if c.button("Kabul", key=f"k_{b.id}", type="primary", width="stretch"):
                    res = automation.basvuru_karar(b.id, True, u.id)
                    ui.flash(res.mesaj, "success" if res.ok else "error")
                    st.rerun()
                if c.button("Ret", key=f"r_{b.id}", width="stretch"):
                    automation.basvuru_karar(b.id, False, u.id)
                    st.rerun()

    st.subheader(f"Ekip ({len(ekip)}/{p.max_ekip})")
    with get_session() as s:
        takim = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == p.id))
    if ekip:
        for b, o in ekip:
            with st.container(border=True):
                a, c = st.columns([4, 1.4])
                yurutucu = takim and takim.yurutucu_id == o.id
                a.markdown(f"**{ui.esc(o.ad_soyad)}** {':blue-badge[Yürütücü / Kaptan]' if yurutucu else ''} "
                           f"{':green-badge[ARBİS ✓]' if o.arbis_kaydi else ':orange-badge[ARBİS yok]'}  \n"
                           f"<span class='soluk'>{ui.esc(o.eposta)} · {ui.esc(o.bolum or '')}</span>", unsafe_allow_html=True)
                a.markdown(ui.chips(o.yetkinlikler), unsafe_allow_html=True)
                if karar_yetkisi:
                    if not yurutucu and c.button("Yürütücü yap", key=f"y_{o.id}", width="stretch"):
                        automation.yurutucu_ata(p.id, o.id)
                        st.rerun()
                    if c.button("Ekipten çıkar", key=f"c_{o.id}", width="stretch"):
                        automation.uyeyi_cikar(p.id, o.id, u.id)
                        st.rerun()
    else:
        st.caption("Ekip henüz boş.")

    st.subheader("Yetkinlik kapsamı")
    eksikler = matcher.ekip_eksikleri(p)
    st.markdown(ui.chips(p.aranan_yetkinlikler, ok=set(skill_set(p.aranan_yetkinlikler)) - set(skill_set(eksikler)),
                         eksik=set(skill_set(eksikler))), unsafe_allow_html=True)
    if eksikler:
        st.caption("Kırmızı: ekipte henüz bulunmayan yetkinlikler.")
        adaylar = matcher.aday_bul(p, eksikler, limit=5)
        if adaylar:
            st.dataframe(pd.DataFrame([{"Öğrenci": a.ogrenci.ad_soyad, "Bölüm": a.ogrenci.bolum, "GNO": a.ogrenci.gno,
                                        "Karşıladığı eksik": ", ".join(a.kapsadigi)} for a in adaylar]), hide_index=True, width="stretch")
            if karar_yetkisi and p.durum == "Acik" and st.button("📨 Uygun adaylara otomatik davet gönder", type="primary"):
                n = automation.otomatik_davet(p.id)
                ui.flash(f"{n} öğrenciye davet gönderildi.")
                st.rerun()
        else:
            st.caption("Eksik yetkinliklere sahip, davet edilebilecek öğrenci bulunamadı.")
    else:
        st.success("Ekip tüm aranan yetkinlikleri karşılıyor.")
    with get_session() as s:
        davetler = s.execute(select(Davet, Kullanici).join(Kullanici, Kullanici.id == Davet.ogrenci_id).where(Davet.proje_id == p.id)).all()
    if davetler:
        with st.expander(f"Gönderilen davetler ({len(davetler)})"):
            st.dataframe(pd.DataFrame([{"Öğrenci": o.ad_soyad, "Yetkinlik": ", ".join(d.yetkinlikler or []), "Durum": d.durum,
                                        "Tarih": ui.tarih(d.tarih)} for d, o in davetler]), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# İçerik
# ---------------------------------------------------------------------------
with t_icerik:
    project_editor.icerik_duzenleyici(p, u.id, duzenleyebilir=icerik_yetkisi)

# ---------------------------------------------------------------------------
# Ön kontrol
# ---------------------------------------------------------------------------
with t_kontrol:
    kontroller = automation.on_kontrol(p.id)
    if kontroller:
        h, w, ok = rules.kontrol_ozeti(kontroller)
        m1, m2, m3 = st.columns(3)
        m1.metric("Hata", h)
        m2.metric("Uyarı", w)
        m3.metric("Tamam", ok)
        if h == 0:
            st.success("TYBS kurallarına göre engelleyici hata yok. Başvuru yapılabilir.")
        else:
            st.warning("Hatalar giderilmeden TYBS başvurusu reddedilebilir veya eksik kalır.")
    ui.kontrol_tablosu(kontroller)

# ---------------------------------------------------------------------------
# Onayla ve Kur
# ---------------------------------------------------------------------------
with t_kur:
    b = automation.proje_baglami(p.id)
    takim = b["takim"]
    st.write("Danışman onayıyla şu zincir otomatik çalışır:")
    st.markdown(
        "1. Proje klasörü ve alt klasörler (**Google Drive** açıksa Drive'da, değilse sunucuda) açılır  \n"
        "2. Hedef TEKNOFEST yarışmasının **şartname PDF'i** ve resmi rapor şablonları indirilir  \n"
        "3. **TÜBİTAK 2209 TYBS hazırlık taslağı / Bitirme öneri formu** ve **TEKNOFEST rapor taslağı** Word olarak üretilir  \n"
        "4. Ekip, danışman ve sanayi danışmanına klasörde **Düzenleyen** yetkisi verilir  \n"
        "5. Herkese **ARBİS / TYBS / e-imza rehberi** ve son tarihler e-posta/Telegram ile gönderilir")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ekip", f"{len(b['ekip'])}/{p.max_ekip}")
    c2.metric("TEKNOFEST hedefi", "Var" if b["kategori"] else "Yok", help=b["kategori"].kategori_adi if b["kategori"] else None)
    c3.metric("Depolama", "Google Drive" if settings.get_bool("drive_aktif") else "Yerel klasör")
    c4.metric("Kurulum", takim.onay_durumu if takim else "Bekliyor")
    zorla = st.checkbox("Yapısal uyarılara rağmen devam et", help="Ekip/danışman/kota kontrollerini atlar. Yalnızca gerekirse kullanın.")
    kuruldu = takim and takim.onay_durumu in ("Kuruldu", "Kısmen Kuruldu")
    son = st.session_state.get(f"kurulum_{p.id}")
    if son:
        ok, mesaj, adimlar = son
        with st.container(border=True):
            (st.success if ok and "uyarı" not in mesaj else st.warning if ok else st.error)(mesaj)
            for a in adimlar or []:
                st.markdown({"tamam": "✅", "hata": "⚠️", "atlandi": "➖"}[a["durum"]] + f" **{a['adim']}** — {ui.esc(a['mesaj'])}")
            if st.button("Kapat", key=f"kapat_{p.id}"):
                st.session_state.pop(f"kurulum_{p.id}", None)
                st.rerun()
    if karar_yetkisi:
        if st.button("🔁 Belgeleri yeniden üret ve gönder" if kuruldu else "✅ Onayla ve Kur", type="primary", disabled=not b["ekip"]):
            with st.spinner("Otomasyon zinciri çalışıyor: klasör, şartname, Word taslakları, paylaşım ve bildirimler…"):
                res = automation.onayla_ve_kur(p.id, u.id, zorla=zorla)
            st.session_state[f"kurulum_{p.id}"] = (res.ok, res.mesaj, res.veri if res.ok else None)
            st.rerun()
        if not b["ekip"]:
            st.caption("Kurulum için ekipte en az bir öğrenci olmalı.")

    with get_session() as s:
        takim = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == p.id))
    if takim and takim.belgeler:
        st.subheader("📂 Proje belgeleri")
        if takim.drive_klasor_url:
            st.link_button("Google Drive klasörünü aç", takim.drive_klasor_url)
        if takim.bos_alan_sayisi is not None:
            st.caption(f"Taslaklarda doldurulmayı bekleyen alan: **{takim.bos_alan_sayisi}** [DOLDURULACAK]")
        for i, d in enumerate(takim.belgeler):
            with st.container(border=True):
                a, c = st.columns([3, 2])
                a.markdown(f"**{ui.esc(d['ad'])}**  \n<span class='soluk'>{ui.esc(Path(d['yol']).name)}</span>", unsafe_allow_html=True)
                if d.get("drive_url"):
                    a.link_button("Drive'da aç", d["drive_url"])
                if Path(d["yol"]).exists():
                    c.download_button("⬇️ İndir", Path(d["yol"]).read_bytes(), file_name=Path(d["yol"]).name, key=f"dl_{i}")
                if not d.get("drive_url") and d["tur"] != "kontrol":
                    up = c.file_uploader("Düzenlenmiş hâlini yükle (.docx)", type=["docx"], key=f"up_{p.id}_{i}")
                    if up is not None and c.button("Güncelle", key=f"upb_{i}"):
                        res = automation.belge_guncelle(p.id, i, up.getvalue(), u.id)
                        ui.flash(res.mesaj)
                        st.rerun()
        if takim.yerel_klasor and Path(takim.yerel_klasor).exists():
            buf = io.BytesIO()
            kok = Path(takim.yerel_klasor)
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in kok.rglob("*"):
                    if f.is_file():
                        z.write(f, f.relative_to(kok.parent))
            st.download_button("🗜️ Tüm proje klasörünü indir (.zip)", buf.getvalue(), file_name=f"{kok.name}.zip", mime="application/zip")
    if takim and takim.otomasyon_log:
        with st.expander("Otomasyon günlüğü"):
            st.dataframe(pd.DataFrame(takim.otomasyon_log[::-1]), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Durum & sonuç
# ---------------------------------------------------------------------------
with t_durum:
    if not karar_yetkisi:
        st.info("Durum ve sonuç güncellemelerini akademik danışman yapar.")
    else:
        with get_session() as s:
            takim = s.scalar(select(TakimEslesmesi).where(TakimEslesmesi.proje_id == p.id))
        st.subheader("Süreç")
        if takim:
            arbis = st.toggle("Ekibin ve danışmanın ARBİS kayıtları kontrol edildi", value=bool(takim.arbis_onay))
            if arbis != bool(takim.arbis_onay):
                with get_session() as s:
                    s.get(TakimEslesmesi, takim.id).arbis_onay = arbis
                st.rerun()
        c1, c2, c3 = st.columns(3)
        if p.durum in ("Onaylandi", "Dolu", "Acik") and c1.button("📤 Başvuru yapıldı olarak işaretle", width="stretch"):
            automation.proje_durum_degistir(p.id, "Basvuruldu", u.id)
            st.rerun()
        if p.durum == "Yedek Havuz":
            uygun, sayi, limit = rules.kota_uygun_mu(p.danisman_id, p.tur, p.donem)
            if c2.button("📢 Yayına al", disabled=not uygun, width="stretch", help=None if uygun else f"Kota dolu ({sayi}/{limit})"):
                automation.proje_durum_degistir(p.id, "Acik", u.id)
                st.rerun()
        if p.durum == "Dolu" and len(rules.ekip_uyeleri(p.id)) < p.max_ekip and c2.button("🔓 Yeni başvurulara aç", width="stretch"):
            automation.proje_durum_degistir(p.id, "Acik", u.id)
            st.rerun()
        if p.durum == "Taslak" and c2.button("📢 Yayınla", width="stretch"):
            uygun, _, _ = rules.kota_uygun_mu(p.danisman_id, p.tur, p.donem)
            automation.proje_durum_degistir(p.id, "Acik" if uygun else "Yedek Havuz", u.id)
            st.rerun()
        if p.durum != "Iptal" and c3.button("🗑️ İlanı iptal et", width="stretch"):
            automation.proje_durum_degistir(p.id, "Iptal", u.id)
            st.rerun()

        st.subheader("Sonuç")
        st.caption("Kabul / Finalist / Derece girilen projeler otomatik olarak Ödüllü Projeler Arşivi'ne eklenir.")
        with st.form("sonuc"):
            sonuc = st.selectbox("Sonuç", rules.SONUCLAR, index=rules.SONUCLAR.index(p.sonuc) if p.sonuc in rules.SONUCLAR else 0)
            notu = st.text_input("Açıklama / derece", value=p.sonuc_notu or "", placeholder="ör. TEKNOFEST 2027 Sanayide Robotik — 2.lik")
            if st.form_submit_button("Sonucu kaydet", type="primary"):
                automation.sonuc_guncelle(p.id, sonuc, notu, u.id)
                ui.flash("Sonuç kaydedildi.")
                st.rerun()
