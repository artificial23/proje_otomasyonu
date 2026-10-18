"""Streamlit sayfalarının ortak bileşenleri: oturum, giriş/kayıt, kurulum sihirbazı, kartlar."""
from __future__ import annotations

import datetime as dt
import html

import streamlit as st

from . import auth, config, notifier, rules, settings
from .database import Kullanici, get_session, has_admin, init_db, log_islem, now

ROL_IKON = {"ogrenci": "🎓", "hoca": "👩‍🏫", "sanayi": "🏭", "admin": "🛠️"}
TUR_RENK = {"2209-A": "blue", "2209-B": "violet", "Bitirme": "orange", "TEKNOFEST": "red"}
DURUM_RENK = {"Acik": "green", "Yedek Havuz": "orange", "Dolu": "blue", "Onaylandi": "violet", "Basvuruldu": "blue",
              "Sonuclandi": "gray", "Iptal": "gray", "Taslak": "gray"}

CSS = """
<style>
.block-container {padding-top: 2.2rem; max-width: 1250px;}
.kart-baslik {font-size: 1.05rem; font-weight: 650; line-height: 1.35; margin-bottom: .15rem;}
.soluk {color: rgba(100,110,125,.95); font-size: .86rem;}
.chip {display:inline-block; padding: 1px 9px; margin: 2px 4px 2px 0; border-radius: 999px; font-size: .78rem;
       background: rgba(30,91,184,.08); border: 1px solid rgba(30,91,184,.22);}
.chip.ok {background: rgba(22,163,74,.10); border-color: rgba(22,163,74,.35);}
.chip.eksik {background: rgba(220,38,38,.07); border-color: rgba(220,38,38,.30);}
.sayac {font-weight: 700; font-variant-numeric: tabular-nums;}
[data-testid="stMetricValue"] {font-size: 1.6rem;}
</style>
"""


def sayfa_baslat() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Oturum
# ---------------------------------------------------------------------------
COOKIE = "kulucka_oturum"


def oturum_ac(user_id: int) -> None:
    """Oturumu başlatır; bir sonraki çalıştırmada tarayıcıya 'beni hatırla' çerezi yazılır."""
    st.session_state["uid"] = user_id
    st.session_state["cerez_yaz"] = auth.create_session(user_id)
    st.session_state.pop("cikis", None)


def cerez_isle() -> None:
    """Bekleyen çerez yazma/silme işlemlerini tarayıcıya iletir."""
    secure = "; Secure" if str(getattr(st.context, "url", "") or "").startswith("https") else ""
    if st.session_state.get("cerez_yaz"):
        tok = st.session_state.pop("cerez_yaz")
        st.session_state["oturum_token"] = tok
        st.html(f"<script>document.cookie='{COOKIE}={tok}; path=/; max-age={auth.OTURUM_GUN * 86400}; SameSite=Lax{secure}';</script>",
                unsafe_allow_javascript=True, width="content")
    if st.session_state.get("cerez_sil"):
        st.session_state.pop("cerez_sil")
        st.html(f"<script>document.cookie='{COOKIE}=; path=/; max-age=0; SameSite=Lax{secure}';</script>",
                unsafe_allow_javascript=True, width="content")


def current_user() -> Kullanici | None:
    uid = st.session_state.get("uid")
    if not uid and not st.session_state.get("cikis"):
        tok = st.context.cookies.get(COOKIE) if hasattr(st.context, "cookies") else None
        uid = auth.user_from_session(tok)
        if uid:
            st.session_state["uid"] = uid
            st.session_state["oturum_token"] = tok
    if not uid:
        return None
    with get_session() as s:
        u = s.get(Kullanici, uid)
    if not u or not u.aktif:
        st.session_state.pop("uid", None)
        return None
    return u


def flash(mesaj: str, tur: str = "success") -> None:
    """Bir sonraki çalıştırmada gösterilecek mesaj (st.rerun sonrası kaybolmasın diye)."""
    st.session_state.setdefault("_flash", []).append((tur, mesaj))


def show_flash() -> None:
    for tur, mesaj in st.session_state.pop("_flash", []):
        if tur == "success":
            st.toast(mesaj, icon="✅")
        else:
            getattr(st, tur, st.info)(mesaj)


def require_user(roller: tuple[str, ...] | None = None) -> Kullanici:
    sayfa_baslat()
    show_flash()
    u = current_user()
    if not u:
        st.warning("Bu sayfayı görmek için giriş yapın.")
        st.stop()
    if roller and u.rol not in roller and u.rol != "admin":
        st.error("Bu sayfaya erişim yetkiniz yok.")
        st.stop()
    return u


def logout() -> None:
    auth.end_session(st.session_state.get("oturum_token") or st.context.cookies.get(COOKIE))
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state["cikis"] = True
    st.session_state["cerez_sil"] = True
    st.rerun()


# ---------------------------------------------------------------------------
# Gömülü zamanlayıcı
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _embedded_scheduler():
    from . import scheduler
    return scheduler.start_background()


def start_embedded_scheduler() -> None:
    if config.SCHEDULER_MODE == "gomulu":
        try:
            _embedded_scheduler()
        except Exception as exc:  # noqa: BLE001
            st.sidebar.caption(f"Zamanlayıcı başlatılamadı: {exc}")


# ---------------------------------------------------------------------------
# Kurulum sihirbazı (ilk çalıştırma)
# ---------------------------------------------------------------------------
def setup_wizard() -> None:
    sayfa_baslat()
    st.title("🚀 İlk Kurulum")
    st.write("Sistemi kurumunuz için hazırlayalım. Bu bilgiler daha sonra **Yönetim Paneli**'nden değiştirilebilir.")
    with st.form("kurulum"):
        st.subheader("Kurum")
        c1, c2 = st.columns(2)
        kurum = c1.text_input("Birim adı", value=settings.DEFAULTS["kurum_adi"], help="Ör. Teknik Bilimler Meslek Yüksekokulu")
        uni = c2.text_input("Üniversite adı", placeholder="Ör. Manisa Celal Bayar Üniversitesi")
        c3, c4 = st.columns(2)
        donem = c3.text_input("Aktif çağrı dönemi", value=str(dt.date.today().year))
        alan = c4.text_input("Öğrenci e-posta alan adı (isteğe bağlı)", placeholder="ogr.universite.edu.tr",
                             help="Doldurulursa yalnızca bu alan adındaki e-postalar öğrenci olarak kayıt olabilir.")
        url = st.text_input("Uygulamanın erişim adresi", value="http://localhost:8501",
                            help="E-postalardaki bağlantılar bu adrese yönlenir. Sunucuya kurduğunuzda güncelleyin.")
        st.subheader("Yönetici hesabı")
        c5, c6 = st.columns(2)
        ad = c5.text_input("Ad Soyad")
        eposta = c6.text_input("E-posta")
        c7, c8 = st.columns(2)
        sifre = c7.text_input("Şifre", type="password", help="En az 8 karakter, harf ve rakam")
        sifre2 = c8.text_input("Şifre (tekrar)", type="password")
        demo = st.checkbox("Denemek için DEMO verisi yükle (örnek öğrenci, danışman ve projeler — sonradan silinebilir)")
        ok = st.form_submit_button("Kurulumu Tamamla", type="primary")
    if ok:
        if not ad or not eposta or not sifre:
            st.error("Yönetici ad, e-posta ve şifre zorunludur.")
            return
        if sifre != sifre2:
            st.error("Şifreler eşleşmiyor.")
            return
        settings.save_many({"kurum_adi": kurum, "universite_adi": uni, "aktif_donem": donem, "izinli_eposta_alanlari": alan,
                            "uygulama_url": url})
        user, err = auth.register_user(ad_soyad=ad, eposta=eposta, sifre=sifre, rol="admin", kvkk_onay=True, aktif=True)
        if err:
            st.error(err)
            return
        from . import seed
        seed.seed_defaults()
        if demo:
            seed.seed_demo()
        oturum_ac(user.id)
        st.success("Kurulum tamamlandı!")
        st.rerun()


# ---------------------------------------------------------------------------
# Giriş / Kayıt / Şifre sıfırlama
# ---------------------------------------------------------------------------
def login_screen() -> None:
    sayfa_baslat()
    kurum = settings.get("kurum_adi")
    uni = settings.get("universite_adi")
    st.markdown(f"<div class='soluk'>{html.escape(str(uni or ''))}</div>", unsafe_allow_html=True)
    st.title(f"🎓 {kurum}")
    st.markdown("#### Akıllı Proje Kuluçka ve Otomasyon Sistemi")
    st.caption("TÜBİTAK 2209-A / 2209-B · Bitirme Projeleri · TEKNOFEST")
    if st.query_params.get("davet"):
        st.info("Bir takım davetiniz var. Görmek için giriş yapın veya kayıt olun.")
        st.session_state["bekleyen_davet"] = st.query_params.get("davet")

    sekmeler = ["Giriş", "Kayıt Ol", "Şifremi Unuttum"]
    t1, t2, t3 = st.tabs(sekmeler)
    with t1:
        with st.form("giris"):
            eposta = st.text_input("E-posta")
            sifre = st.text_input("Şifre", type="password")
            ok = st.form_submit_button("Giriş Yap", type="primary")
        if ok:
            try:
                u = auth.authenticate(eposta, sifre)
            except auth.HesapKilitli as exc:
                st.error(str(exc))
                return
            if not u:
                st.error("E-posta veya şifre hatalı.")
            elif not u.aktif:
                st.warning("Hesabınız yönetici onayı bekliyor.")
            else:
                oturum_ac(u.id)
                st.rerun()
        st.caption("Hesabınızı yönetici oluşturduysa size verilen geçici şifreyle girin; ilk girişte şifrenizi değiştirmeniz istenir.")
    with t2:
        kayit_formu()
    with t3:
        sifre_sifirlama()


def kayit_formu() -> None:
    roller = []
    if settings.get_bool("ogrenci_kayit_acik"):
        roller.append("Öğrenci")
    roller += ["Akademik Danışman", "Sanayi Temsilcisi"]
    rol_label = st.radio("Hesap türü", roller, horizontal=True)
    rol = {"Öğrenci": "ogrenci", "Akademik Danışman": "hoca", "Sanayi Temsilcisi": "sanayi"}[rol_label]
    onay_gerekli = rol != "ogrenci" and settings.get_bool("hoca_sanayi_onay_gerekli")
    if onay_gerekli:
        st.caption("Danışman ve sanayi hesapları yönetici onayından sonra aktif olur.")
    alanlar = settings.get("izinli_eposta_alanlari")
    if rol == "ogrenci" and alanlar:
        st.caption(f"Öğrenci kaydı için kurum e-postası gerekli: {alanlar}")
    with st.form("kayit"):
        c1, c2 = st.columns(2)
        ad = c1.text_input("Ad Soyad")
        eposta = c2.text_input("E-posta")
        c3, c4 = st.columns(2)
        sifre = c3.text_input("Şifre", type="password", help="En az 8 karakter, harf ve rakam")
        sifre2 = c4.text_input("Şifre (tekrar)", type="password")
        bolumler = settings.get("bolumler") or []
        extra = {}
        if rol == "ogrenci":
            c5, c6, c7 = st.columns(3)
            extra["bolum"] = c5.selectbox("Program / Bölüm", bolumler)
            extra["sinif"] = c6.selectbox("Sınıf", ["1", "2", "Mezuniyet aşaması"])
            extra["ogrenim_turu"] = c7.selectbox("Öğrenim türü", rules.OGRENIM_TURLERI)
            c8, c9 = st.columns(2)
            extra["ogrenci_no"] = c8.text_input("Öğrenci no")
            extra["gno"] = c9.number_input("GNO (4'lük)", 0.0, 4.0, 0.0, 0.01)
        elif rol == "hoca":
            c5, c6 = st.columns(2)
            extra["unvan"] = c5.selectbox("Unvan", ["Öğr. Gör.", "Öğr. Gör. Dr.", "Arş. Gör.", "Arş. Gör. Dr.", "Dr. Öğr. Üyesi", "Doç. Dr.", "Prof. Dr."])
            extra["bolum"] = c6.selectbox("Bölüm", bolumler)
        else:
            extra["kurum"] = st.text_input("Firma / Kuruluş adı")
        katalog = settings.get("yetkinlik_katalogu") or []
        extra["yetkinlikler"] = st.multiselect("Yetkinlikler", katalog, accept_new_options=True, placeholder="Seçin veya yazıp Enter ile ekleyin",
                                               help="Listede yoksa yazıp Enter'a basarak ekleyebilirsiniz.")
        st.markdown(f"<div class='soluk'>{html.escape(str(settings.get('kvkk_metni')))}</div>", unsafe_allow_html=True)
        kvkk = st.checkbox("Aydınlatma metnini okudum, onaylıyorum.")
        ok = st.form_submit_button("Kayıt Ol", type="primary")
    if ok:
        if not kvkk:
            st.error("Devam etmek için KVKK onayı gerekli.")
            return
        if sifre != sifre2:
            st.error("Şifreler eşleşmiyor.")
            return
        if not ad.strip():
            st.error("Ad Soyad zorunludur.")
            return
        user, err = auth.register_user(ad_soyad=ad.strip(), eposta=eposta, sifre=sifre, rol=rol, kvkk_onay=True,
                                       aktif=not onay_gerekli, **extra)
        if err:
            st.error(err)
            return
        if onay_gerekli:
            with get_session() as s:
                from sqlalchemy import select
                adminler = list(s.scalars(select(Kullanici).where(Kullanici.rol == "admin")))
            for a in adminler:
                notifier.notify(a, f"Onay bekleyen hesap: {user.ad_soyad}",
                                f"{user.ad_soyad} ({user.eposta}) {auth.ROLLER[rol]} olarak kayıt oldu. Yönetim Paneli > Kullanıcılar'dan onaylayın.")
            st.success("Kaydınız alındı. Yönetici onayından sonra giriş yapabilirsiniz.")
        else:
            oturum_ac(user.id)
            st.success("Kayıt başarılı!")
            st.rerun()


def sifre_sifirlama() -> None:
    if not notifier.smtp_hazir():
        st.info("E-posta gönderimi yapılandırılmadığı için şifre sıfırlama kodu gönderilemiyor. "
                "Lütfen sistem yöneticisinden şifrenizi sıfırlamasını isteyin.")
        return
    with st.form("sifre_kod"):
        eposta = st.text_input("Kayıtlı e-posta")
        ok = st.form_submit_button("Kod Gönder")
    if ok:
        user, code = auth.start_reset(eposta)
        if user:
            notifier.notify(user, "Şifre sıfırlama kodu", f"Şifre sıfırlama kodunuz: {code}\nKod 30 dakika geçerlidir.",
                            kanallar=("eposta",))
        st.success("E-posta kayıtlıysa sıfırlama kodu gönderildi.")
        st.session_state["reset_email"] = eposta
    if st.session_state.get("reset_email"):
        with st.form("sifre_yeni"):
            kod = st.text_input("E-postadaki 6 haneli kod")
            yeni = st.text_input("Yeni şifre", type="password")
            ok2 = st.form_submit_button("Şifreyi Değiştir", type="primary")
        if ok2:
            err = auth.finish_reset(st.session_state["reset_email"], kod, yeni)
            if err:
                st.error(err)
            else:
                st.success("Şifreniz değiştirildi. Giriş sekmesinden giriş yapabilirsiniz.")
                st.session_state.pop("reset_email", None)


def zorunlu_sifre_degistir(u: Kullanici) -> None:
    sayfa_baslat()
    st.title("🔐 Yeni şifre belirleyin")
    st.write("Hesabınız yönetici tarafından oluşturuldu veya şifreniz sıfırlandı. Devam etmek için yeni bir şifre belirleyin.")
    with st.form("zorunlu_sifre"):
        y1 = st.text_input("Yeni şifre", type="password")
        y2 = st.text_input("Yeni şifre (tekrar)", type="password")
        kvkk = True
        if not u.kvkk_onay:
            st.markdown(f"<div class='soluk'>{html.escape(str(settings.get('kvkk_metni')))}</div>", unsafe_allow_html=True)
            kvkk = st.checkbox("Aydınlatma metnini okudum, onaylıyorum.")
        ok = st.form_submit_button("Kaydet", type="primary")
    if ok:
        problem = auth.password_problem(y1)
        if problem:
            st.error(problem)
        elif y1 != y2:
            st.error("Şifreler eşleşmiyor.")
        elif not kvkk:
            st.error("KVKK onayı gerekli.")
        else:
            auth.set_password(u.id, y1)
            with get_session() as s:
                uu = s.get(Kullanici, u.id)
                if not uu.kvkk_onay:
                    uu.kvkk_onay, uu.kvkk_tarih = True, now()
            log_islem(u.id, "sifre_belirle")
            st.rerun()


# ---------------------------------------------------------------------------
# Görsel yardımcılar
# ---------------------------------------------------------------------------
def esc(x) -> str:
    return html.escape(str(x or ""))


def tur_rozet(tur: str) -> str:
    return f":{TUR_RENK.get(tur, 'gray')}-badge[{tur}]"


def durum_rozet(durum: str) -> str:
    return f":{DURUM_RENK.get(durum, 'gray')}-badge[{rules.DURUM_ETIKET.get(durum, durum)}]"


def kalan_rozet(gun: int | None) -> str:
    if gun is None:
        return ":gray-badge[Tarih bekleniyor]"
    if gun < 0:
        return ":gray-badge[Süresi doldu]"
    if gun == 0:
        return ":red-badge[BUGÜN son gün]"
    renk = "red" if gun <= 3 else "orange" if gun <= 10 else "green"
    return f":{renk}-badge[{gun} gün kaldı]"


def chips(items, ok: set[str] | None = None, eksik: set[str] | None = None) -> str:
    from .text_utils import skill_key
    out = []
    for it in items or []:
        cls = "chip"
        k = skill_key(it)
        if ok is not None and k in ok:
            cls += " ok"
        elif eksik is not None and k in eksik:
            cls += " eksik"
        out.append(f"<span class='{cls}'>{esc(it)}</span>")
    return "".join(out)


def tarih(d) -> str:
    if not d:
        return "—"
    if isinstance(d, dt.datetime):
        return d.strftime("%d.%m.%Y %H:%M")
    return d.strftime("%d.%m.%Y")


def kontrol_tablosu(kontroller) -> None:
    import pandas as pd
    if not kontroller:
        st.info("Bu proje türü için TÜBİTAK ön kontrolü uygulanmaz.")
        return
    ikon = {"hata": "❌ Hata", "uyari": "⚠️ Uyarı", "tamam": "✅ Tamam"}
    df = pd.DataFrame([{"Durum": ikon[k.seviye], "Alan": k.alan, "Açıklama": k.mesaj} for k in kontroller])
    st.dataframe(df, hide_index=True, width="stretch")
