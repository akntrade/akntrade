"""
config.py
---------
Tum ayarlar ve esik degerler burada. Kod icinde baska hicbir yerde
"sihirli sayi" olmamali - hepsi buradan okunur.

ONEMLI - ESIK DEGERLERININ KAYNAGI:
Her esigin yanindaki etikete dikkat et:
  [SOHBET]  -> Akin'in daha once bu sohbette birebir yazdigi deger (Izleme Listesi / tier 1)
  [BELGE]   -> Akin'in yukledigi belgeden birebir alinan deger (Guclu Filtre / tier 2)
  [TAHMIN]  -> Belgede olmayan ama tier 2'yi tamamlamak icin makul bir
               mantikla EKLEDIGIM deger. Bunlar kesin degil, sen kontrol et.

[TAHMIN] etiketli degerleri mutlaka gozden gecir. Bot bu sayilarla calisir
ama bunlar "Akin'in yazdigi katı SAFE kriterleri" degil, benim tahminim.
"""

import os

# ---------------------------------------------------------------------------
# Telegram / genel ayarlar
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
PORT = int(os.environ.get("PORT", "10000"))

# Zincir ayari. GoPlus chain_id, GeckoTerminal network id, DexScreener chainId
# uclu hepsi farkli isimlendirme kullaniyor, o yuzden ucunu de burada esliyoruz.
CHAIN = os.environ.get("CHAIN", "bsc")  # "bsc" = Binance Smart Chain (varsayilan)

CHAIN_MAP = {
    "bsc": {"goplus_id": "56", "gecko_network": "bsc", "dexscreener_id": "bsc"},
    "eth": {"goplus_id": "1", "gecko_network": "eth", "dexscreener_id": "ethereum"},
    "base": {"goplus_id": "8453", "gecko_network": "base", "dexscreener_id": "base"},
}

TIMEZONE = "Europe/Istanbul"

# ---------------------------------------------------------------------------
# Tarama sikligi  [SOHBET] - Akin'in verdigi cetvel
# ---------------------------------------------------------------------------
NEW_TOKEN_SCAN_INTERVAL_SEC = 45          # yeni token/pool taramasi
EARLY_CHECK_INTERVAL_SEC = 60             # ilk 15 dakika
AGE_15_60_MIN_INTERVAL_SEC = 120          # 15-60 dakika
AGE_1_4_H_INTERVAL_SEC = 300              # 1-4 saat
AGE_4_6_H_INTERVAL_SEC = 600              # 4-6 saat
MAX_TRACK_AGE_SEC = 6 * 3600              # 6 saatten sonra takipten dusur

# API'ye yaklasilinca aralik kac katina cikarilsin
RATE_LIMIT_BACKOFF_MULTIPLIER = 2.0
RATE_LIMIT_BACKOFF_MAX_MULTIPLIER = 8.0

# Ayni token icin ayni kaynaga gereksiz tekrar cagri yapmamak icin
# minimum bekleme (cache TTL), check araligiyla ayni tutuluyor.
CACHE_MIN_TTL_SEC = 30

# ---------------------------------------------------------------------------
# TIER 1 - IZLEME LISTESI (erken/gevsek)  [SOHBET]
# ---------------------------------------------------------------------------
T1_MIN_AGE_SEC = 5 * 60
T1_MAX_AGE_SEC = 4 * 3600
T1_MIN_LIQUIDITY_USD = 20_000
T1_MIN_HOLDERS = 40
T1_MIN_TRUSTED_TRADERS = 20
T1_MIN_REAL_BUYS = 15
T1_MIN_REAL_SELLS = 5
T1_MIN_VOLUME_1H_USD = 7_500
T1_MIN_LIQ_MCAP_RATIO = 0.10       # likidite/piyasa degeri >= %10
T1_MAX_TOP_WALLET_RATIO = 0.08     # en buyuk normal cuzdan <= %8
T1_MAX_TOP10_WALLET_RATIO = 0.35   # ilk 10 normal cuzdan toplami <= %35
T1_MAX_TAX_RATIO = 0.05            # alis/satis vergisi <= %5
T1_MIN_POSITIVE_CHECKS = 2         # en az 2 kontrol arasinda yukselis sart

# ---------------------------------------------------------------------------
# TIER 2 - GUCLU FILTRE (katı SAFE)   [BELGE] + [TAHMIN]
# ---------------------------------------------------------------------------
T2_MIN_AGE_SEC = 30 * 60                  # [BELGE] "en az 15-30 dakika" -> ust sinir (30 dk) kullanildi
T2_MAX_AGE_SEC = MAX_TRACK_AGE_SEC         # [TAHMIN] belgede ust sinir yok, takip ufkuyla sinirlandirildi (6s)
T2_MIN_LIQUIDITY_USD = 50_000              # [BELGE] "en az 50.000, tercihen 100.000+"
T2_STRONG_LIQUIDITY_USD = 100_000          # [BELGE] bonus/guclu isaret, sart degil
T2_MIN_HOLDERS = 100                       # [BELGE]
T2_MIN_TRUSTED_TRADERS = 50                # [BELGE] "gercek trader en az 50"
T2_MIN_REAL_SELLS = 20                     # [BELGE] "en az 20-30 farkli satis" -> alt sinir
T2_STRONG_REAL_SELLS = 30                  # [BELGE] bonus/guclu isaret
T2_MIN_REAL_BUYS = 40                      # [TAHMIN] belgede yok; tier1'in ~2.5x'i olarak tahmin edildi
T2_MAX_TOP_WALLET_RATIO = 0.05             # [BELGE] "arzin %5'inden azi"
T2_MAX_TOP10_WALLET_RATIO = 0.25           # [BELGE] "%20-25'ten az" -> siki uc (25) kullanildi
T2_MIN_LIQ_MCAP_RATIO = 0.15               # [BELGE] "tercihen en az %15-20" -> alt sinir
T2_STRONG_LIQ_MCAP_RATIO = 0.20            # [BELGE] bonus/guclu isaret
T2_MAX_TAX_RATIO = 0.05                    # [BELGE] "tercihen %0-5"
T2_MIN_VOLUME_1H_USD = 20_000              # [TAHMIN] belgede rakam yok; olcek tier1'e gore buyutuldu
T2_MIN_POSITIVE_CHECKS = 2                 # [SOHBET] tier1 ile ayni mantik tier2'ye de uygulandi

# ---------------------------------------------------------------------------
# ORTAK RISK ELEME LISTESI (her iki tier icin de gecerli, terminal red)
# [SOHBET] - kritik risk listesi
# ---------------------------------------------------------------------------
# Bu kontrollerden biri bile "evet/riskli" cikarsa token IZLEME LISTESI'ne
# dahi giremez. Bu kontrol filters.py -> check_critical_risks() icinde yapilir.
CRITICAL_RISK_FIELDS = [
    "honeypot",
    "unverified_or_no_real_sells",
    "blacklist",
    "whitelist_sell_restriction",
    "trading_or_transfer_pause",
    "owner_can_change_balance",
    "dangerous_or_unlimited_mint",
    "custom_per_wallet_tax",
    "excessive_or_unknown_sell_tax",
    "zero_real_sells",
    "goplus_honeypot_conflict",
]

# "Asiri/bilinmeyen satis vergisi" icin sinir - bu kritik risk kontrolunde
# kullanilir (tier esiklerinden BAGIMSIZ, cok daha yuksek bir kirmizi cizgi).
# [TAHMIN] belgede net sayi yok, "cok yuksek" ifadesi sayisallastirildi.
EXCESSIVE_TAX_RATIO = 0.20  # %20 uzeri satis vergisi = otomatik red

# ---------------------------------------------------------------------------
# Rapor zamanlamasi  [SOHBET]
# ---------------------------------------------------------------------------
STATUS_SUMMARY_INTERVAL_SEC = 6 * 3600
DAILY_REPORT_HOUR = 23  # Europe/Istanbul, 23:00

# ---------------------------------------------------------------------------
# Dosya yollari
# ---------------------------------------------------------------------------
STATE_FILE = os.environ.get("STATE_FILE", "data/state.json")
LOG_FILE = os.environ.get("LOG_FILE", "data/bot.log")
