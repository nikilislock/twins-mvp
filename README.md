# THE TWINS

**Aynı bağlantı haritası. İki ayrı deneyim. Gözlenebilir bir deney.**

The Twins, gerçek FlyWire FAFB v783 bağlantı verisi üzerinde iki özdeş başlangıçlı nöral simülasyonu, eklenmiş öğrenme katmanını ve iki ajan arasındaki küçük bir sembol kanalını inceleyen yerel araştırma uygulamasıdır. Arayüzde gösterilen ölçümler çalışan Python deneyinden gelir. Tarayıcı kendi sonuçlarını üretmez.

## Başlat

Windows'ta **`BASLAT.cmd` dosyasına çift tıkla**. Python 3.11 veya üstü gereklidir; geliştirme ve doğrulama Python 3.12 ile yapıldı. Alternatif:

```powershell
python launch.py
```

İlk çalıştırma ayrı bir `.venv` ortamı hazırlar, sabitlenmiş bağımlılıkları kurar ve yaklaşık 136 MB araştırma verisini indirip SHA-256 doğrulaması yapar. Sonraki çalıştırmalar yerel önbelleği kullanır. Tam beyin verisi yüklenince tarayıcıda **http://127.0.0.1:8765** açılır. Terminal penceresi açık kalmalıdır; `Ctrl+C` uygulamayı durdurur. Bu teslimatta ortam ve veri zaten hazırlanmıştır.

```bash
# Linux / macOS veya tarayıcı açmadan kullanım
python3 launch.py --no-browser
# Alternatif port
python launch.py --port 8766
```

Tam veri için birkaç yüz MB disk, çalışma sırasında yaklaşık 1–2 GB boş RAM ayırmak uygundur; süre işlemciye bağlıdır. CUDA veya GPU gerekmez. Python bağımlılıkları ve veriler hazır olduktan sonra ağ bağlantısı gerekmez.

## Panelde neler var?

- **İki ajan:** aynı topoloji, başlangıç parametreleri ve durum; ayrı deneyimler ve öğrenilen ağırlıklar.
- **Canlı arena:** ajan konumları, hareket izleri, deney evresi ve ayrılma müdahalesi. Beden ve hareket eşlemeleri bu projenin tasarımıdır.
- **Nöral gözlem:** gerçek ağdan örneklenmiş aktivite, açıklama verisi bulunan anatomik referans noktaları ve indeks/FlyWire kimliğiyle tek nöron inceleme.
- **Partner ipucu deneyi:** tanıdık, yeni ve aynı duyusal ipucunu taşıyan kontrol örneklerine tepkiler. Aynı ipucu kontrolü, modelin bireyin özünü değil duyusal örüntüyü ayırt ettiğini görmeyi sağlar.
- **Dört sembollü kanal:** üretilen sembol, alıcının seçimi, iki ajanın gönderici/alıcı politikaları ve başarı oranı. Kanalı karıştırma ve plastisiteyi kapatma müdahaleleri.
- **Nöral müdahale:** ölçülen sensory/Kenyon/descending spike izleri öğrenmeyi ve politikaları etkiler. Ağı susturmak hareketi ve öğrenmeyi durdurur, politika çıktısını şans düzeyine getirir; öğrenilmiş parametreleri silmez.
- **Deney kaydı:** evreler, müdahaleler, olaylar, ölçümler ve örneklenmiş durumlar SQLite'a kaydedilir. Eski oturumlar incelenebilir ve JSON dışa aktarılabilir.

**Başlat** ile varsayılan protokol ilerler. **Duraklat** ve **Tek adım** inceleme içindir. Evre düğmeleri ilgili deneye geçer; önceki eğitim durumunu korur. Yeni tohumla sıfırlama yeni kayıt açar, eski kayıtları silmez. Öğrenmeyi açık/kapalı karşılaştırırken aynı başlangıç tohumu ve aynı protokolü kullan. Evre atlamaları ve müdahaleler kayda girer.

## Bilimsel sınırlar

Gerçek veri, bağlantı topolojisi ve açıklamalardır. **Dinamik model, duyusal giriş eşlemeleri, beden, partner öğrenmesi ve sembol oyunu bu projenin eklediği mekanizmalardır.** Bu uygulama Eon/Shiu modelinin deneysel sonuçlarını yeniden ürettiğini veya biyolojik sosyal davranışı doğruladığını iddia etmez.

Bir connectome, canlının anılarıyla ve bütün biyokimyasıyla kopyası değildir. Özdeş başlangıçlı iki hesaplama durumu oluşturuyoruz; bir sineğin kişiliğini iki kez çoğaltmıyoruz. Eksik mekanizmalar arasında ayrıntılı sinaptik zamanlama ve reseptör biyolojisi, gelişim, hormonlar, gerçek vücut ve çevre dinamikleri bulunur.

Partner tanıma burada duyusal ipucuna öğrenilmiş tepki anlamına gelir. Sembol oyunu tasarlanmış bir ödül altında sınırlı haberleşmedir; doğal dil, öznel anlam, sevgi, özlem, acı veya bilinç kanıtı değildir. Ayrılık evresinin davranış etkileri kodlanmış çevre ve öğrenme kurallarının sonuçlarıdır. Önceki sohbetlerde geçen dramatik yüzdeler veya duygusal anlatımlar veri olarak kullanılmadı.

Nöral milisaniye ile deney adımı ayrı ölçeklerdir. Hız düğmesi bilgisayarın işleme temposunu değiştirir; biyolojik gerçek zaman iddiası taşımaz. Nöral görselleştirme bütün nöronların aynı anda çizimi değildir; örnek büyüklüğü panelde belirtilir. Anatomik noktalar kaynakta verilen referans konumlarıdır, nöronun tam geometrisi değildir.

Ayrıntılar: [Yöntem](docs/METHODS.md), [Kaynaklar, sabit sürümler ve lisanslar](docs/SOURCES.md), [Doğrulama](docs/VALIDATION.md).

## Kaynak ve lisans

Yerelde yüklenen Eon 2025 dışa aktarımında **138.639 nöron** ve **15.091.983 sıfır olmayan, yönlü ağırlıklı bağlantı** bulunur. Bağlantı sayısı sinapsların toplam sayısı değildir; farklı filtre ve dışa aktarımlar farklı sayılar verir. Grafın kimliği ve dosya sağlama toplamları sonuçlarla kaydedilir.

Projenin yeni yazılmış kodu MIT lisanslıdır. Eon `fly-brain` deposunun kökü GPL-2.0 lisanslıdır; buradan çalıştırılabilir kod kopyalanmadı. Veri için MIT/GPL yazılım lisansları geçerli varsayılmaz: FlyWire'ın kamusal veri açıklaması **CC BY-NC 4.0** koşullarını belirtir. Veri indirilen önbellekte tutulur ve Git deposuna eklenmez. Ticari kullanım için veri koşullarını ayrıca değerlendir.

Birincil kaynaklar: [Eon Fly Brain](https://github.com/eonsystemspbc/fly-brain), [FlyWire açıklamaları](https://github.com/flyconnectome/flywire_annotations), [FlyWire veri politikası](https://home.flywire.ai/guidelines), [Dorkenwald ve ark., Nature 2024](https://doi.org/10.1038/s41586-024-07558-y), [Shiu ve ark., Nature 2024](https://doi.org/10.1038/s41586-024-07763-9).

## Geliştirme ve test

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.lock
python scripts/fetch_data.py
python -m pytest -q
python -m twins
```

Testler küçük, açıkça işaretlenmiş sentetik grafiklerle temel mekanizmaları ve küçük gerçek biçimli dosyalarla veri yüklemeyi sınar; veri indirmeyi gerektirmez. Gerçek tam grafik üzerinde yerel çalıştırma ayrı doğrulanmıştır. Tam dosyalar yoksa üretim sunucusu açıklayıcı hatayla durur, sessizce sentetik demoya geçmez.

```bash
# Üç tohum, dört kontrol koşulu; küçük sentetik test ağı
python scripts/benchmark.py
# Tam gerçek ağ, bütün protokol, kalıcı kayıt ve sayısal rapor
python scripts/validate_full.py
```

`Yöntem & kaynak` penceresinden bütün nöronların o anki durumunu `.npz` olarak
indirebilirsin. Bu bir inceleme çıktısıdır, yeniden başlatılabilen checkpoint
değildir. Arşiv oynatma, beş adım aralıkla ve müdahalelerde kaydedilmiş görünür
durumları kullanır; her nöronun her milisaniyesini kaydetmez. Tek nöron
denetleyicisi canlı duruma aittir ve arşiv görüntülenirken kapatılır.

`twins/connectome.py`: veri ve provenans; `twins/engine.py`: nöral çekirdek ve deneyler; `twins/server.py`: yerel API; `twins/storage.py`: kayıt; `twins/static/`: arayüz.

Sunucu yalnızca `127.0.0.1` üzerinde dinler. Ajanların dosya sistemi, terminal, kamera, cihaz veya dış servis aracı yoktur. Kaydedilen dosyalar uygulamanın deney verileridir. Tarayıcıdan dış kaynağa veri gönderilmez. Bu yapı dış internete açılmış çok kullanıcılı bir servis değildir.

## GitHub'a daha sonra yükleme

Bu aşamada kullanıcının tercihiyle GitHub'a yükleme yapılmadı. Kod, testler ve dokümantasyon yüklemeye hazırdır; veri önbelleği, ortam ve yerel oturumlar `.gitignore` kapsamındadır.

```bash
# GitHub CLI ile kendi hesabında oturum açtıktan sonra:
gh auth login
gh repo create the-twins --private --source=. --remote=origin --push
```

`gh` yoksa GitHub'da boş bir depo oluştur ve verdiği uzak depo adresini kullan:

```bash
git remote add origin https://github.com/KULLANICI/the-twins.git
git push -u origin main
```

Yerel başlangıç commit'i, Git kimliği bulunmadığında kişisel kimlik uydurmamak için proje katkıcı adıyla oluşturulmuş olabilir. Kendi sonraki commit'lerin için `git config user.name` ve `git config user.email` değerlerini ayarla.
