# AKN Trades — #TradeÖğreniyorum Telegram Bildirim Sistemi (Ücretsiz)

Bu sistem X API kullanmaz, hiçbir ücret gerektirmez. Günde 3 kez (10:00,
15:00, 19:30) Telegram üzerinden sana sıradaki tweeti mesaj olarak gönderir.
Sen mesajı görürsün, kopyalayıp X'e kendi elinle yapıştırıp paylaşırsın.

## Neden bu şekilde tamamen ücretsiz?

- X API'ye hiç dokunmuyoruz, dolayısıyla o tarafta hiçbir ücret yok.
- Telegram Bot API tamamen ücretsizdir, hiçbir kota/ödeme sınırı yoktur.
- Zamanlama için **GitHub Actions** kullanıyoruz — GitHub'ın herkese açık
  sunduğu, private repo'larda bile ayda 2000 dakikaya kadar ücretsiz olan
  zamanlanmış görev servisi. Bu üç günlük mesaj için gereken süre (saniyeler
  seviyesinde) bu kotanın çok altında kalır. Kendi bilgisayarını veya bir
  sunucuyu sürekli açık tutmana gerek kalmaz.

## Dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `tweets.csv` | 100 tweet + durumu (pending/sent), gönderim zamanı |
| `send_to_telegram.py` | Sıradaki bekleyen tweeti Telegram'a gönderen script |
| `requirements_telegram.txt` | Gerekli Python kütüphaneleri |
| `.env.telegram.example` | Telegram bot bilgilerin için şablon |
| `.github_workflows_telegram_tweet.yml` | GitHub Actions zamanlama dosyası (bkz. aşağıda nereye koyacağın) |
| `crontab_telegram.txt` | İstersen kendi sunucunda/bilgisayarında cron ile çalıştırmak için alternatif |

`tweets.csv` sütunları aynı kaldı, sadece anlamları hafif değişti:
- `status`: `pending` (henüz gönderilmedi) veya `sent` (Telegram'a gönderildi — X'e senin elinle paylaşman gerekiyor)
- `posted_at`: Telegram'a gönderilme zamanı (UTC)
- `posted_tweet_id`: Bu sistemde kullanılmıyor, boş kalır

## Kurulum Adımların

### 1) Telegram bot oluştur

1. Telegram'da **@BotFather** hesabını bul, `/newbot` yaz.
2. Bot için bir isim ve kullanıcı adı belirle (örn. `AKNTradesBot`).
3. BotFather sana bir **token** verecek (örn. `123456:ABC-...`), bunu not al.
4. Kendi Telegram hesabından bu yeni bota gidip `/start` yaz (bot seninle
   konuşabilsin diye bu şart).

### 2) Kendi chat ID'ini öğren

Tarayıcıdan şu adrese git (TOKEN yerine kendi token'ını yaz):

```
https://api.telegram.org/botTOKEN/getUpdates
```

`/start` yazdıktan sonra buraya girersen dönen JSON içinde
`"chat":{"id":123456789,...}` şeklinde bir sayı göreceksin. Bu senin
`chat_id`'in.

### 3) Bir GitHub reposu oluştur

1. GitHub'da yeni bir **private** repo aç (örn. `akn-trades-bot`).
2. Bu klasördeki dosyaları (`tweets.csv`, `send_to_telegram.py`,
   `requirements_telegram.txt`) repoya yükle.
3. `.github_workflows_telegram_tweet.yml` dosyasını repo içinde
   **`.github/workflows/telegram_tweet.yml`** yoluna koy (klasör adı nokta
   ile başlıyor, GitHub Actions bu yolu arıyor).

### 4) Bot bilgilerini GitHub'a güvenli şekilde ekle

Repo → **Settings → Secrets and variables → Actions → New repository secret**
1. `TELEGRAM_BOT_TOKEN` adıyla bot token'ını ekle.
2. `TELEGRAM_CHAT_ID` adıyla chat ID'ini ekle.

Bu bilgiler repo koduna hiç yazılmaz, sadece GitHub'ın güvenli secret
deposunda tutulur.

### 5) Test et

Repo → **Actions** sekmesi → workflow'u seç → **Run workflow** butonuyla
elle bir kere çalıştır. Telegram'a mesaj gelip gelmediğini kontrol et,
`tweets.csv` içindeki ilgili satırın `status` = `sent` olduğunu gör.

### 6) Otomatik çalışmaya bırak

Bir şey yapmana gerek yok — workflow dosyasındaki zamanlama (`cron:`
satırları) her gün otomatik olarak 10:00, 15:00 ve 19:30'da (Türkiye saati)
çalışır ve Telegram'a mesaj atar.

## Alternatif: Kendi bilgisayarında/sunucunda cron

GitHub Actions yerine kendi cihazını kullanmak istersen `crontab_telegram.txt`
içindeki satırları `crontab -e` ile ekleyebilirsin. Tek fark: bu durumda
cihazın o saatlerde açık olması gerekir. GitHub Actions bu yüzden daha
pratik — hiçbir cihazı açık tutmana gerek kalmıyor.

## Senin yapman gerekenler (özet)

1. @BotFather ile bot oluştur, token'ı al.
2. `/start` yaz, `getUpdates` ile chat_id'ini öğren.
3. GitHub'da private repo aç, dosyaları yükle, workflow dosyasını doğru
   klasöre (`.github/workflows/`) koy.
4. İki secret'ı (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) ekle.
5. Actions sekmesinden elle bir test çalıştırması yap.
6. Telegram'dan gelen mesajları görünce kopyala, X'e yapıştır, paylaş.

## Tekrar gönderim koruması nasıl çalışıyor?

- Script her çalıştığında yalnızca bir `pending` satır bulur, gönderir,
  hemen `sent` olarak işaretler ve güncellenmiş `tweets.csv`'yi GitHub
  Actions otomatik olarak repoya geri commit'ler (workflow'un son adımı).
- Böylece bir sonraki çalıştırma, önceki tweetin artık `sent` olduğunu
  görür ve bir sonraki `pending` tweete geçer — aynı tweet iki kez
  gönderilmez.
- 100 tweet bittiğinde bot sana "kuyrukta bekleyen tweet kalmadı" diye
  ayrı bir Telegram mesajı gönderir.
