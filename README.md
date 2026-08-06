# SAFE Filtre Botu (Izleme Listesi + Guclu Filtre)

BSC (varsayilan) uzerinde yeni tokenleri tarayan, iki kademeli bir
Telegram bildirim botu:

- 🟡 **Izleme Listesi** - erken/gevsek esikler (sohbette verdigin degerler)
- 🟢 **Guclu Filtre** - katı SAFE esikleri (yukledigin belgeden)

---

## 1) ONCE OKU: Neyi varsaydim, neyi tahmin ettim

Bu botu **kanit temelli** kurmaya calistim ama bazi noktalarda elimde
kesin veri yoktu. Guvenmeden once bunlari gozden gecir:

| Konu | Ne yaptim | Neden |
|---|---|---|
| Zincir | Varsayilan **BSC** | Honeypot.is + GoPlus + "vergi/mint/blacklist" kaliplarindan BSC'ye isaret ettigini varsaydim. `config.py` icinde `CHAIN` degiskeniyle degistirilebilir. |
| Guclu Filtre esikleri | `config.py` icinde her satirda `[BELGE]` (belgeden birebir) veya `[TAHMIN]` (belgede olmayan, benim ekledigim) etiketi var | Belgen bazi sayilari vermiyordu (min hacim, min alis sayisi). Bunlari tier1'e oranla tahmin ettim - **mutlaka gozden gecir**. |
| Yeni pair kesfi | Ham RPC WebSocket yerine **GeckoTerminal'in `new_pools` endpoint'i** | Ucretsiz hosting'de (Render) surekli acik bir WebSocket/kontrat-event dinleyicisi kurmak kirilgan ve agir. GeckoTerminal ~2-3 saniye gecikmeyle pratikte esdeger sonuc veriyor. |
| "Guvenilir benzersiz trader" | GeckoTerminal'in `buyers`/`sellers` (h1) alanlarinin **buyugu** | Tam "birlesim" (union) sayisi API'de yok; bu bir alt sinir tahminidir, gercek sayi bundan biraz daha yuksek olabilir. |
| "Gercek alis/satis sayisi" | Son 1 saatlik pencere (`transactions.h1`) | Yasam boyu toplam islem sayisi icin ek bir veri kaynagi/sayfalama gerekir; bu ilk surumde eklenmedi. |
| RPC | Sadece **baglanti canliligi** icin kullaniliyor (durum raporunda gorunur) | Asil filtreleme mantigi RPC'ye bagimli degil - bu sayede WebSocket/kontrat-ABI karmasikligi olmadan ucretsiz platformda calisiyor. |
| API alan adlari | Belgelenmis (GoPlus/Honeypot.is/GeckoTerminal) alan adlarini kullandim ve **sahte veriyle test ettim** | Benim ortamimin internet erisimi yok, o yuzden **canli bir API cevabini hic goremedim**. Ilk calistirmada mutlaka 1-2 gercek token adresiyle her `sources.py` fonksiyonunu tek tek deneyip ham JSON'u yazdir, alan adlari tutuyor mu kontrol et. |

Bu bot **yatirim tavsiyesi vermez** ve hicbir kombinasyon "%100 guvenli"
anlamina gelmez - bunu sen de biliyorsun, mesajlarda da acikca yaziyor.

---

## 2) Neden Render (ucretsiz, kart yok)

Fly.io ve Railway artik kredi karti istiyor ve gercek bir "sonsuza kadar
ucretsiz" katmanlari yok (2024'te kaldirildi). **Render** hala kart
istemeyen, gercekten $0 bir "Hobby" katmani sunuyor - tek dezavantaji,
**gelen trafik olmadan 15 dakika sonra uykuya dalmasi**. Bunu asagidaki
"uyanik tutma" adimiyla asiyoruz.

Daha guclu / gercek zamanli bir kurulum istersen (kredi karti gerekir
ama hicbir zaman ucret yazilmaz - sadece dogrulama icin), **Oracle
Cloud Always Free** bir ARM VM (4 OCPU / 24GB RAM'e kadar, suresiz
ucretsiz) alternatif olarak dosyanin sonunda anlatiliyor.

### Adimlar

1. **Telegram botu olustur:** Telegram'da `@BotFather`'a yaz, `/newbot`
   de, adini sec. Sana bir **token** verecek - bunu sakla.
2. **Chat ID'ni ogren:** Botuna Telegram'dan `/start` yaz. Sonra
   tarayicida ac (TOKEN yerine kendi tokenini yaz):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Donen JSON'da `"chat":{"id": 123456789}` gorunecek - o sayi senin
   `TELEGRAM_CHAT_ID`'in.
3. **Render'a git** (render.com), GitHub hesabinla giris yap (kart
   istemez). Bu kodu kendi GitHub reponuza yukle (private repo olabilir).
4. Render'da **New > Web Service** sec, reponu bagla.
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4`
   - Plan: **Free**
   - `--workers 1` sart: birden fazla worker acilirsa her biri kendi
     tarama thread'ini baslatir ve ayni bildirimi birden fazla kez
     gonderirsin. Tek worker + birden fazla thread (webhook istekleri
     icin) yeterli.
5. **Environment** sekmesinde `.env.example`'daki degiskenleri tek tek
   gir (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CHAIN=bsc`).
6. Deploy bittikten sonra Render sana bir URL verecek
   (orn. `https://safe-bot-xxxx.onrender.com`). Bunu `PUBLIC_BASE_URL`
   olarak Environment'a ekle ve **tekrar deploy et** (webhook sadece
   acilista kuruluyor).
7. **Uyanik tutma (ONEMLI):** Render'in ucretsiz servisi 15 dakika
   istek gelmezse uyur; uyurken arka plandaki tarama da durur. Bunu
   engellemek icin ucretsiz bir "uptime ping" servisi kullan:
   - cron-job.org veya UptimeRobot.com - ikisi de ucretsiz.
   - Hedef URL: `https://<render-url>/health`
   - Siklik: her **10 dakikada bir**.
   - Bu sayede servis pratikte hep uyanik kalir.

### Ilk test

Deploy sonrasi tarayicidan `https://<render-url>/health` ac -
`{"status": "ok", ...}` gormelisin. Telegram'dan botuna `/watchlist`
yaz - "Izleme Listesi'nde su an bir token yok." donmeli (henuz
baslangic). Loglari Render dashboard'undan izleyebilirsin.

---

## 3) Sinirlamalar (durustce)

- **Kalici disk yok:** Render'in ucretsiz katmaninda servis yeniden
  baslarsa (redeploy, cokme) takip edilen tokenler ve "yukseliyor mu"
  gecmisi **sifirlanir**. Ucretsiz kalmak istiyorsan bunun bedeli bu.
  Ileride ucretsiz bir Postgres (Supabase/Neon free tier) baglanip
  kalicilik eklenebilir.
- **Gercek zamanlilik:** GeckoTerminal verisi ~2-3 saniye gecikmeli ve
  kendi cache'i 1 dakika - saniyeler mertebesinde "ilk giren" olmayi
  garanti etmez. Bu, ham RPC WebSocket'e kiyasla bilincli bir taviz.
- **API'ler degisebilir:** GoPlus/Honeypot.is/GeckoTerminal ucretsiz ve
  belgelenmemis sekilde degisebilir. Bot calismazsa once
  `sources.py` basindaki dokumantasyon linklerini kontrol et.
- **Rate limit:** Kodda otomatik yavaslama var ama GeckoTerminal'in
  ucretsiz siniri (~30 istek/dk, bazen daha az) cok fazla token
  takip edilirse zorlanabilir.

---

## 4) Alternatif: Oracle Cloud Always Free (daha guclu, kart gerekli ama ucretsiz)

Eger Render'in uyku/cold-start davranisindan rahatsiz olursan, Oracle
Cloud'un **Always Free** katmani gercek, suresiz ucretsiz bir Linux VM
verir (kimlik dogrulama icin kredi karti ister ama yukseltmedikce
ASLA ucret yazmaz):

1. oracle.com/cloud/free adresinden hesap ac (telefon + kart dogrulama).
2. Bir "VM.Standard.A1.Flex" (ARM, 1-4 OCPU/24GB'a kadar) veya bulunamazsa
   "VM.Standard.E2.1.Micro" instance olustur, Ubuntu sec.
3. SSH ile baglan, Python3 + pip kur, bu klasoru yukle,
   `pip install -r requirements.txt`, sonra `systemd` ile
   `gunicorn app:app --bind 0.0.0.0:8000` servisini surekli calisacak
   sekilde ayarla (boot'ta otomatik baslar).
4. Bu durumda ayrica bir "uyanik tutma" pingine gerek yok - VM zaten
   7/24 calisir, ve WebSocket/gercek-zamanli genisletmeler icin de
   daha uygun bir zemindir.

Bazi bolgelerde ARM kapasitesi gecici olarak dolabiliyor - o durumda
birkac kez farkli saatte tekrar denemek genelde cozuyor.

---

## Dosya yapisi

```
config.py     - tum esik degerleri (etiketli: [SOHBET]/[BELGE]/[TAHMIN])
state.py      - JSON dosyasi tabanli hafiza (thread-safe)
sources.py    - GoPlus / Honeypot.is / GeckoTerminal / DexScreener / RPC cagrilari
filters.py    - risk eleme + tier1/tier2 karar mantigi
notifier.py   - Telegram mesaj gonderme ve metin sablonlari
scanner.py    - ana dongu, zamanlama, rapor
app.py        - Flask giris noktasi (health + webhook + arka plan thread baslatma)
```
