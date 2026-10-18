# Akıllı Proje Kuluçka ve Otomasyon Sistemi

TÜBİTAK 2209-A / 2209-B, bitirme projeleri ve TEKNOFEST için uçtan uca proje kuluçka sistemi.
Öğrenciler yetkinliklerine göre takım kurar ve akademik/sanayi danışmanlarıyla eşleşir. TEKNOFEST
yarışmaları otomatik takip edilir. Danışman tek tıkla onay verdiğinde proje klasörü, şartname ve Word
başvuru taslakları hazırlanır, ekibe rehber ve hatırlatmalar gönderilir.

Program kuruma bağlı değildir. Kurum adı, bölümler, yetkinlik kataloğu, kota ve bütçe kuralları, e-posta
alan adı ve Word şablonları **Yönetim Paneli**'nden değiştirilir. Her kurum kendi kopyasını çalıştırır.

---

## İçindekiler
1. [Özellikler](#özellikler)
2. [Hızlı kurulum](#hızlı-kurulum)
3. [İlk çalıştırma](#ilk-çalıştırma)
4. [Roller ve iş akışı](#roller-ve-iş-akışı)
5. [Otomatik görevler](#otomatik-görevler)
6. [Entegrasyonlar (e-posta, Telegram, Google Drive)](#entegrasyonlar)
7. [Word şablonları](#word-şablonları)
8. [TÜBİTAK kuralları ve güncelleme](#tübitak-kuralları)
9. [Başka kurumlarda kullanım ve sunucu kurulumu](#başka-kurumlarda-kullanım)
10. [Komut satırı](#komut-satırı)
11. [Klasör yapısı](#klasör-yapısı)
12. [Sık karşılaşılan sorunlar](#sık-karşılaşılan-sorunlar)
13. [Bilinen sınırlamalar](#bilinen-sınırlamalar)

---

## Özellikler

### Mimari belgedeki 6 modül

| Modül | Bu programda |
|---|---|
| 1. TEKNOFEST Scraper Botu | `modules/teknofest_scraper.py`. teknofest.org yarışma listesini ve her yarışma sayfasını **haftada bir** tarar. Katılım seviyesini (Ön Lisans / Üniversite), takvimi, son başvuru tarihini, ödülleri, şartname PDF'ini ve resmi rapor şablonlarını çıkarır. Ön lisansa uygun yarışmaların şartnamelerini indirir. Site istekleri engellerse Playwright ile yeniden dener. |
| 2. Ödüllü Projeler Hafızası | Taramada yarışma sayfalarındaki "Dereceler" tabloları arşive eklenir. Kurumda sonuçlanan projeler de **otomatik** eklenir (Kabul, Finalist, Derece). Excel ile toplu yükleme yapılabilir. |
| 3. Akıllı Takım & Yetkinlik Eşleştirici | `Eksik = Aranan − Ekip yetkinlikleri` hesaplanır. Eksik yetkinliğe sahip, uygun öğrencilere **otomatik davet** gönderilir. "plc", "TIA Portal" ve "PLC (Siemens TIA Portal)" aynı yetkinlik sayılır. |
| 4. 2209 → TEKNOFEST Çapraz Eşleştirici | Türkçe'ye uyarlanmış TF-IDF ve kosinüs benzerliğiyle en uygun 2 yarışma **% uyum skoruyla** önerilir. Aynı yöntem benzer (tekrar eden) proje fikirlerini de uyarır. |
| 5. Otonom Belge & Drive İşçisi | "Onayla ve Kur" düğmesiyle şu adımlar çalışır: klasör ve alt klasörler (Drive veya yerel), şartname ve resmi şablonlar, **2209-A/B TYBS hazırlık taslağı**, **TEKNOFEST rapor taslağı**, **Bitirme öneri formu**, **başvuru kontrol listesi**, ekibe "Düzenleyen" yetkisi. |
| 6. Kota, ARBİS ve Takvim Bekçisi | Danışman kotası denetlenir; kota doluysa ilan **Yedek Havuz**'a alınır, yer açılınca otomatik yayınlanır. ARBİS/TYBS/e-imza rehberi gönderilir. Son tarihe **10 ve 3 gün** kala hatırlatma (e-posta, Telegram, uygulama içi) gönderilir. Kurulumdan sonra doldurulmamış taslaklar için haftalık uyarı yapılır. |

### Belgede olmayan, eklenenler
- **TÜBİTAK TYBS ön kontrolü:** Özet 25–450 kelime, bölümler en az 350 karakter, başarı ölçütü toplamı %100, yasak iş adımları, en çok 12 ay süre, en fazla 5 kişilik ekip, bütçe üst limiti, DOI uyarısı, 2209-B'de iki danışmanın farklı kişi olması, açık öğretim ve hazırlık öğrencisi engeli.
- **Tek başvuru kuralı:** Öğrenci bir 2209 ekibine kabul edilince aynı dönemdeki diğer 2209 başvuruları otomatik geri çekilir.
- **Rol bazlı giriş:** Öğrenci, Akademik Danışman, Sanayi Temsilcisi ve Yönetici rolleri vardır. Kayıt, şifre sıfırlama, "beni hatırla" oturumu ve hatalı denemelerde hesap kilidi bulunur.
- **İlk kurulum sihirbazı** ve isteğe bağlı **DEMO verisi** (tek tıkla silinir).
- **Excel ile toplu yükleme:** Öğrenci ve danışman listeleri, ödüllü projeler arşivi ve takvim yüklenebilir. Tüm verilerin Excel raporu indirilebilir.
- **Takvim:** TÜBİTAK 2209-A/B 2026 tarihleri hazır gelir. Son tarihler `.ics` olarak telefona veya Outlook'a eklenebilir. Öğrenciler TEKNOFEST yarışmalarını **takip edip** hatırlatma alabilir.
- **KVKK:** Kayıtta açık rıza istenir. Kullanıcı verilerini JSON olarak indirebilir ve hesabını silebilir (anonimleştirme).
- **Kurum şablonları:** Word şablonları panelden indirilip değiştirilir ve geri yüklenir; yüklenen şablon doğrulanır.
- **Bildirim kutusu:** E-posta veya Telegram kurulmamış olsa da sistem çalışır. Mesajlar uygulama içinde görünür; yönetici giden kutusunu izler.

---

## Hızlı kurulum

Gerekenler: **Python 3.11 veya üstü** (https://www.python.org/downloads/). Windows'ta kurarken
**"Add Python to PATH"** kutusunu işaretleyin.

### Windows (tek tık)
1. Klasörü bilgisayarınıza çıkarın.
2. `baslat_windows.bat` dosyasına çift tıklayın. İlk çalıştırmada gerekli paketler kurulur (birkaç dakika sürer).
3. Tarayıcı `http://localhost:8501` adresinde açılır.

### macOS / Linux
```bash
chmod +x baslat.sh
./baslat.sh
```

### Elle kurulum
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### Docker (sunucu)
```bash
cp .env.example .env        # gerekirse düzenleyin
docker compose up -d        # arayüz: http://SUNUCU:8501
```
Docker kurulumunda arayüz ve zamanlayıcı ayrı konteynerlerde çalışır. Veriler `./data` klasöründe kalır.

---

## İlk çalıştırma

İlk açılışta **Kurulum Sihirbazı** görünür:
1. Birim adı, üniversite adı ve aktif çağrı dönemini girin (ör. `2026`).
2. İsteğe bağlı olarak öğrenci e-posta alan adını yazın (ör. `ogr.universite.edu.tr`). Bu doldurulursa yalnızca bu adreslerle öğrenci kaydı yapılabilir.
3. Yönetici hesabını oluşturun.
4. Denemek için **DEMO verisi** kutusunu işaretleyebilirsiniz. Demo hesapların şifresi `Demo1234`: `hoca@demo.local`, `sanayi@demo.local`, `ayse@demo.local`, `zeynep@demo.local` …
   Gerçek kullanıma geçerken **Yönetim Paneli → Yedek & Veri → Demo verisini sil** ile temizleyin.

Kurulum sihirbazı 61 TEKNOFEST yarışmasını (adlar ve bağlantılar) ve TÜBİTAK 2209-A/B 2026 son tarihlerini
otomatik ekler. TEKNOFEST tarihleri, ödülleri ve şartnameleri **ilk taramada** dolar. İlk taramayı hemen
yapmak için: **TEKNOFEST Yarışmaları → Taramayı şimdi çalıştır**.

---

## Roller ve iş akışı

```
Danışman / Sanayi ilan açar ──► Kota kontrolü ──► Açık  (kota doluysa → Yedek Havuz)
        │                          │
        │                          └─► TEKNOFEST çapraz eşleştirme (% uyum) + benzer proje uyarısı
        ▼
Öğrenci başvurur (yetkinlik uyumu %)  ◄── Sistem eksik yetkinlik için uygun öğrencilere davet gönderir
        ▼
Danışman kabul eder ──► Ekip tamamlanır ──► İçerik (TYBS bölümleri) birlikte doldurulur ──► Ön kontrol
        ▼
"Onayla ve Kur" ──► Klasör + şartname + Word taslakları + paylaşım + ARBİS/TYBS rehberi + son tarihler
        ▼
Başvuru yapıldı ──► Sonuç (Kabul / Finalist / Derece) ──► Ödüllü Projeler Arşivi'ne otomatik eklenir
```

| Rol | Neler yapar |
|---|---|
| **Öğrenci** | Profilinde yetkinlik, GNO ve ARBİS durumunu tutar. Kendisine uygun ilanları görür, başvurur, davetleri yanıtlar. Takım belgelerini indirir, düzenleyip geri yükler. İçeriği ekipçe düzenler. TEKNOFEST yarışmalarını takip eder. |
| **Akademik Danışman** | İlan açar, kotasını görür. Başvuruları kabul veya ret eder, yürütücüyü belirler, aday önerilerine davet gönderir. İçeriği düzenler, ön kontrolü görür. **Onayla ve Kur**'u çalıştırır, sonuç girer. |
| **Sanayi Temsilcisi** | 2209-B ilanı açar (akademik danışman seçer). Projeyi izler ve içeriği düzenler. Kabul ve onay kararlarını akademik danışman verir. |
| **Yönetici** | Tüm ayarları, kullanıcıları, entegrasyonları, takvimi, şablonları, kayıtları ve yedekleri yönetir. |

---

## Otomatik görevler

| Görev | Zaman |
|---|---|
| TEKNOFEST taraması | Haftada bir (varsayılan Pazartesi 03:00, panelden değiştirilir) |
| Son tarih hatırlatmaları | Her gün 09:00 ve uygulama her açıldığında (aynı hatırlatma ikinci kez gitmez) |
| Boş taslak kontrolü | Her gün 10:00. Kurulumdan 7 gün sonra `[DOLDURULACAK]` alanı kalan ekiplere haftalık uyarı gider. |
| Süresi dolan davetler | Her gün 08:00 (varsayılan 14 gün) |
| Telegram hesap eşleştirme | 2 dakikada bir (Telegram açıksa) |

Zamanlayıcı varsayılan olarak uygulamanın içinde çalışır; ayrı bir şey başlatmanıza gerek yoktur.
Görevlerin çalışması için uygulamanın açık kalması gerekir. Durumu **Yönetim Paneli**'nin üstünde görürsünüz
(🟢 / 🔴). Sunucuda arayüz ve zamanlayıcıyı ayırmak için `.env` içinde `KULUCKA_ZAMANLAYICI=harici` yazın
ve ayrıca `python worker.py` çalıştırın.

---

## Entegrasyonlar

Hiçbiri zorunlu değildir. Kurulmadıklarında bildirimler uygulama içinde görünür ve belgeler sunucudaki
`data/projeler/` klasörüne yazılır. Ekip belgeleri arayüzden indirir.

### E-posta (SMTP)
**Yönetim Paneli → Entegrasyonlar → E-posta**
- Kurum e-posta sunucusu: Bilgi işlem biriminden SMTP sunucusu, port ve kullanıcı bilgilerini alın.
- Gmail: Sunucu `smtp.gmail.com`, port `587`, güvenlik STARTTLS. Hesapta 2 adımlı doğrulamayı açıp bir **uygulama şifresi** oluşturun ve onu kullanın.
- Outlook / Microsoft 365: Sunucu `smtp.office365.com`, port `587`, güvenlik STARTTLS.
- Şifreyi veritabanına yazmak istemezseniz `.env` dosyasına `SMTP_SIFRE=...` ekleyin.
- Kaydettikten sonra **Test e-postası gönder** ile deneyin.

### Telegram
1. Telegram'da **@BotFather**'a `/newbot` yazıp bot oluşturun ve verilen token'ı kopyalayın.
2. Panelde token'ı ve bot kullanıcı adını girip Telegram'ı açın.
3. Kullanıcılar **Profilim → Bildirim kanalları**'ndaki koda göre bota `/start TG-XXXXXX` yazar; hesap otomatik bağlanır.

### Google Drive
**Seçenek A: Hizmet hesabı (Google Workspace for Education için önerilir)**
1. https://console.cloud.google.com adresinde bir proje açın ve **Google Drive API**'yi etkinleştirin.
2. *IAM ve Yönetici → Hizmet Hesapları*'ndan bir hizmet hesabı oluşturun ve **JSON anahtarı** indirin.
3. Drive'da bir **Paylaşılan Drive** (Shared Drive) açın. Hizmet hesabının e-postasını *İçerik yöneticisi* olarak ekleyin. Bu Drive'da bir ana klasör oluşturun.
4. Panelde JSON dosyasını yükleyin, ana klasör ID'sini yazın (adres çubuğunda `/folders/` sonrasındaki kısım) ve **Drive bağlantısını test et**'e basın.

> Hizmet hesaplarının kişisel depolama kotası yoktur. Bu yüzden klasör mutlaka bir **Paylaşılan Drive** içinde olmalıdır.

**Seçenek B: Kullanıcı hesabı (OAuth)**
1. Cloud Console'da *OAuth istemci kimliği → Masaüstü uygulaması* oluşturup JSON'u indirin.
2. Panelde "Kullanıcı hesabı (OAuth)" seçip JSON'u yükleyin.
3. Uygulamanın çalıştığı bilgisayarda bir kez `python manage.py drive-yetkilendir` komutunu çalıştırın ve tarayıcıda izin verin.

"Word taslaklarını Google Dokümanlar'a dönüştür" açıkken ekip taslakları tarayıcıda birlikte düzenler.
Boş taslak kontrolü de doğrudan Drive'daki dokümanı okur.

---

## Word şablonları

`templates/` klasöründe 5 varsayılan şablon bulunur:

| Şablon | Kullanım |
|---|---|
| `tubitak_2209a_sablon.docx` | 2209-A **TYBS hazırlık taslağı** (TYBS ekranlarıyla aynı başlıklar, karakter ve kelime sınırları, çalışma takvimi, Gantt, risk ve bütçe tabloları, ön kontrol sonucu) |
| `tubitak_2209b_sablon.docx` | 2209-B taslağı (Yenilikçi Yön, Sanayi Odaklı Çıktılar ve sanayi bilgileri dahil) |
| `teknofest_odr_sablon.docx` | TEKNOFEST Ön Değerlendirme / Proje Detay Raporu taslağı |
| `bitirme_oneri_sablon.docx` | Bitirme projesi öneri formu (imza alanlı) |
| `kontrol_listesi_sablon.docx` | Her onaylı projeye eklenen yapılacaklar ve rehber belgesi |

> **Önemli:** 2026 çağrısından itibaren TÜBİTAK araştırma önerisini **TYBS ekranlarına girilen bilgilerden
> kendisi oluşturur** ve Word dosyası yüklenmez. Bu yüzden 2209 belgesi bir *hazırlık taslağıdır*. Ekip
> içeriği burada birlikte yazar, ardından TYBS'deki ilgili alanlara kopyalar. TEKNOFEST'te ise içerik,
> yarışmanın resmi şablonuna aktarılır (resmi şablon proje klasörüne otomatik indirilir).

Kurum formatını kullanmak için **Yönetim Paneli → Şablonlar**'dan şablonu indirin, Word'de düzenleyin
(`{{ baslik }}`, `{{ ozet }}` gibi yer tutucuları koruyun) ve geri yükleyin. Kullanılabilir değişkenler
aynı ekranda listelenir. Varsayılan şablonları yeniden üretmek için: `python manage.py sablonlar`.

---

## TÜBİTAK kuralları

Varsayılan değerler **2026 yılı 2209-A ve 2209-B çağrı duyurularına** göre ayarlanmıştır:

| Kural | Değer | Panelde değiştirilebilir mi? |
|---|---|---|
| Başvuru ve danışman onayı | 07.10.2026 – 11.11.2026 17:30 | Evet (Takvim) |
| Kurum yetkilisi e-imza | 16.11.2026 – 23.11.2026 | Evet (Takvim) |
| Destek üst limiti | 2209-A: 12.000 TL · 2209-B: 16.000 TL | Evet |
| Proje süresi | En çok 12 ay | Evet |
| Ekip | Yürütücü + en fazla 4 ortak (5 kişi) | Evet |
| Danışman başına proje | Aynı dönemde en fazla 5 | Evet |
| Öğrenci başına başvuru | Dönemde 1 | Kural motorunda |
| Uygun olmayan öğrenciler | Açık öğretim, hazırlık sınıfı | Kural motorunda |

Yeni çağrı açıldığında **Yönetim Paneli → Genel** bölümünden dönemi, limitleri ve takvimi güncelleyin.
Kaynaklar: tubitak.gov.tr 2209-A ve 2209-B program sayfaları, 2026 çağrı duyuruları ve Başvuru İçeriği Bilgi Notları.

---

## Başka kurumlarda kullanım

- **Kurum bilgileri:** Birim ve üniversite adı, bölümler/programlar, yetkinlik kataloğu, KVKK metni ve başvuru rehberi Yönetim Paneli → Genel'den değiştirilir.
- **Kullanıcıları toplu ekleme:** Yönetim Paneli → Kullanıcılar → *Excel ile toplu kullanıcı yükle* (örnek şablon indirilebilir). Her kişiye geçici şifre üretilir ve ilk girişte değiştirmesi istenir.
- **Ağda paylaşım:** Uygulamayı bir sunucuda veya laboratuvar bilgisayarında çalıştırın. Diğerleri `http://BILGISAYAR-IP:8501` adresinden erişir. Yönetim Paneli'nde **Uygulama adresi**ni bu adres yapın; e-postalardaki bağlantılar buraya gider.
- **İnternete açma:** Ters vekil sunucu (nginx, Caddy) ile HTTPS kullanın. Uygulama HTTPS'i algılar ve oturum çerezini *Secure* olarak yazar.
- **PostgreSQL:** `.env` içinde `DATABASE_URL=postgresql+psycopg2://kullanici:sifre@sunucu/vt` yazın ve `pip install psycopg2-binary` çalıştırın.
- **Güncelleme:** Yeni sürüm dosyalarını kopyalayın; `data/` klasörüne dokunmayın. Yeni veritabanı sütunları açılışta otomatik eklenir.

---

## Komut satırı

```bash
python manage.py kurulum               # veritabanı + varsayılan veriler
python manage.py yonetici-ekle         # yönetici hesabı (şifre unutulursa da kullanılır)
python manage.py demo | demo-sil       # demo verisi yükle / sil
python manage.py tara [--limit 5]      # TEKNOFEST taraması
python manage.py hatirlat              # hatırlatmaları şimdi gönder
python manage.py taslak-kontrol        # boş taslak kontrolü
python manage.py sablonlar             # varsayılan Word şablonlarını yeniden üret
python manage.py drive-yetkilendir     # Google Drive OAuth
python manage.py yedekle               # data/yedekler/ altına SQLite yedeği
python -m pytest -q                    # testler
```

---

## Klasör yapısı

```
myo_proje_otomasyonu/
├── app.py                         # Giriş, kurulum sihirbazı, rol bazlı menü
├── worker.py                      # Ayrı süreçte zamanlayıcı (sunucu kurulumu için)
├── manage.py                      # Komut satırı yönetim aracı
├── requirements.txt · .env.example · Dockerfile · docker-compose.yml
├── baslat_windows.bat · baslat.sh # Tek tıkla başlatma
├── sayfalar/                      # Arayüz ekranları (belgedeki pages/ klasörü)
│   ├── 0_Ana_Sayfa.py                     # Özet, son tarihler, bildirimler
│   ├── 1_Proje_Eslestirme_Panosu.py       # İlanlar, başvuru, yeni ilan
│   ├── 2_Teknofest_Kategorileri.py        # Yarışmalar, geri sayım, şartname, eşleştirme aracı
│   ├── 3_Odullu_Projeler_Arsivi.py        # İlham kartları
│   ├── 4_Danisman_Onay_ve_Otomasyon.py    # Kota, başvurular, içerik, ön kontrol, Onayla ve Kur
│   ├── 5_Profilim.py                      # Profil, davetler, takım, bildirim kanalları, KVKK
│   └── 6_Yonetim_Paneli.py                # Ayarlar, kullanıcılar, entegrasyonlar, takvim, şablonlar
├── modules/
│   ├── database.py        # 5 ana tablo + başvuru, davet, takvim, bildirim, ayar, oturum, işlem günlüğü
│   ├── teknofest_scraper.py · matcher.py · doc_generator.py · drive.py · notifier.py
│   ├── automation.py      # İş akışları ve "Onayla ve Kur" zinciri
│   ├── rules.py           # Kota, uygunluk, TÜBİTAK ön kontrolü
│   ├── scheduler.py       # Zamanlanmış görevler
│   └── auth.py · settings.py · importer.py · seed.py · ui.py · project_editor.py · text_utils.py
├── templates/             # Varsayılan Word şablonları
├── tools/build_templates.py
├── tests/                 # Otomatik testler
└── data/                  # (çalışınca oluşur) veritabanı, şartnameler, proje klasörleri, yedekler
```

> Belgedeki `pages/` klasörü burada `sayfalar/` adını taşır. Streamlit `pages/` klasörünü giriş yapılmadan
> da menüde gösterdiği için ad değiştirildi; menü artık kullanıcının rolüne göre oluşur.

---

## Sık karşılaşılan sorunlar

| Sorun | Çözüm |
|---|---|
| `python` bulunamadı | Python'u "Add Python to PATH" seçeneğiyle yeniden kurun. |
| Yönetim Paneli'nde 🔴 zamanlayıcı | Uygulamayı başlatma betiğiyle açın. Harici moddaysanız `python worker.py` çalışıyor olmalı. |
| E-posta gitmiyor | Bildirim & Kayıtlar sekmesindeki **Hata** sütununa bakın. Gmail için normal şifre değil, uygulama şifresi gerekir. |
| TEKNOFEST taraması hata veriyor | İnternet bağlantısını kontrol edin. Site engelliyorsa `pip install playwright && playwright install chromium` ile tarayıcı modunu açın. Site düzeni değiştiyse yarışmalar elle de eklenip düzenlenebilir. |
| Şifremi unuttum (e-posta yok) | Yönetici, Kullanıcılar → Şifre sıfırla'dan geçici şifre üretir. Yönetici şifresi için: `python manage.py yonetici-ekle`. |
| Port 8501 dolu | `streamlit run app.py --server.port 8502` |

---

## Bilinen sınırlamalar
- **TYBS ve TEKNOFEST sistemlerinin dış erişime açık bir arayüzü yoktur.** Bu yüzden son başvuru gönderimi kişinin kendisi tarafından yapılır. Sistem her şeyi gönderime hazır hâle getirir ve takip eder.
- **TEKNOFEST taraması** sayfa düzenine değil metin kalıplarına dayanır, ancak site köklü biçimde değişirse ayrıştırma güncellenmelidir. Tarama sonuçları ve uyarıları Yönetim Paneli'nde görünür. Yarışmalar elle düzenlenebilir.
- **TÜBİTAK kuralları her çağrıda değişebilir.** Yeni çağrı metnini okuyup panelden limitleri ve takvimi güncelleyin.
