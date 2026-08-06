"""
filters.py
----------
Karar mantiginin tamami burada:
  1) check_critical_risks()  -> her iki tier icin de gecerli, elemeyen kirmizi cizgiler
  2) evaluate_tier1()        -> Izleme Listesi esikleri  [SOHBET]
  3) evaluate_tier2()        -> Guclu Filtre esikleri     [BELGE]/[TAHMIN]
  4) rising_trend()          -> "en az 2 kontrol arasinda olumlu ilerleme" kontrolu

Bu dosya sadece HAZIR (normalize edilmis) bir "snapshot" sozlugu ile
calisir; GoPlus/Honeypot.is/GeckoTerminal'in ham JSON alan adlariyla
UGRASMAZ (bu is sources.py -> normalize_* fonksiyonlarinda yapiliyor).
Boylece bir API alan adi degisirse tek bir yerde (sources.py) duzeltme
yeterli olur.
"""

import config


# ---------------------------------------------------------------------------
# 1) KRITIK RISK ELEME (her iki tier icin ortak, terminal red)
# ---------------------------------------------------------------------------
def check_critical_risks(snap):
    """
    snap: sources.build_snapshot() ciktisidir (asagida sablonu var).
    Donen deger: (rejected: bool, reasons: list[str])
    """
    reasons = []

    if snap.get("is_honeypot") is True:
        reasons.append("Honeypot tespit edildi")

    if snap.get("simulation_success") is False:
        reasons.append("Satis simulasyonu basarisiz / dogrulanamadi")
    if snap.get("sells_h1") == 0 and snap.get("age_sec", 0) > 20 * 60:
        # Token 20 dakikadan eskiyse ve hic gercek satis yoksa suphelidir.
        reasons.append("Hic gercek satis islemi yok")

    if snap.get("is_blacklisted") is True:
        reasons.append("Blacklist fonksiyonu var")

    if snap.get("is_whitelisted") is True:
        reasons.append("Whitelist ile satis kisitlamasi var")

    if snap.get("transfer_pausable") is True or snap.get("trading_cooldown") is True:
        reasons.append("Trading/transfer durdurma yetkisi var")

    if snap.get("owner_change_balance") is True:
        reasons.append("Owner kullanici bakiyesini degistirebiliyor")

    if snap.get("is_mintable") is True:
        reasons.append("Mint yetkisi var (sinirsiz/tehlikeli olabilir)")

    if snap.get("custom_per_wallet_tax") is True:
        reasons.append("Kisiye ozel vergi koyabilme yetkisi var")

    sell_tax = snap.get("sell_tax")
    if sell_tax is None:
        reasons.append("Satis vergisi bilinmiyor")
    elif sell_tax > config.EXCESSIVE_TAX_RATIO:
        reasons.append(f"Asiri satis vergisi (%{sell_tax * 100:.0f})")

    if snap.get("goplus_says_honeypot") is not None and snap.get("is_honeypot") is not None:
        if snap["goplus_says_honeypot"] != snap["is_honeypot"]:
            reasons.append("GoPlus ve Honeypot.is sonuclari celisiyor")

    return (len(reasons) > 0), reasons


# ---------------------------------------------------------------------------
# Ortak esik kontrol yardimcisi
# ---------------------------------------------------------------------------
def _check(label, value, required, comparator, unit=""):
    """
    Tek bir esigi kontrol eder, (gecti_mi, aciklama_metni) dondurur.
    comparator: "min" -> value >= required, "max" -> value <= required
    """
    if value is None:
        return False, f"{label}: veri yok (gereken {'>=' if comparator=='min' else '<='} {required}{unit})"
    if comparator == "min":
        ok = value >= required
    else:
        ok = value <= required
    if ok:
        return True, f"{label}: {value}{unit} (OK)"
    return False, f"{label}: {value}{unit} -> gereken {'>=' if comparator=='min' else '<='} {required}{unit}"


def _tier_result(checks):
    passed_all = all(c[0] for c in checks)
    missing = [c[1] for c in checks if not c[0]]
    details = [c[1] for c in checks]
    return passed_all, missing, details


# ---------------------------------------------------------------------------
# 2) TIER 1 - IZLEME LISTESI  [SOHBET]
# ---------------------------------------------------------------------------
def evaluate_tier1(snap):
    c = config
    checks = [
        _check("Yas", snap.get("age_sec"), c.T1_MIN_AGE_SEC, "min", " sn"),
        _check("Yas ust sinir", snap.get("age_sec"), c.T1_MAX_AGE_SEC, "max", " sn"),
        _check("Likidite", snap.get("liquidity_usd"), c.T1_MIN_LIQUIDITY_USD, "min", " USD"),
        _check("Holder", snap.get("holders"), c.T1_MIN_HOLDERS, "min"),
        _check("Guvenilir trader", snap.get("trusted_traders"), c.T1_MIN_TRUSTED_TRADERS, "min"),
        _check("Gercek alis", snap.get("buys_h1"), c.T1_MIN_REAL_BUYS, "min"),
        _check("Gercek satis", snap.get("sells_h1"), c.T1_MIN_REAL_SELLS, "min"),
        _check("Hacim (1s)", snap.get("volume_h1_usd"), c.T1_MIN_VOLUME_1H_USD, "min", " USD"),
        _check("Likidite/MCap", snap.get("liq_mcap_ratio"), c.T1_MIN_LIQ_MCAP_RATIO, "min"),
        _check("En buyuk cuzdan", snap.get("top_wallet_ratio"), c.T1_MAX_TOP_WALLET_RATIO, "max"),
        _check("Ilk 10 cuzdan", snap.get("top10_wallet_ratio"), c.T1_MAX_TOP10_WALLET_RATIO, "max"),
        _check("Vergi", snap.get("max_tax"), c.T1_MAX_TAX_RATIO, "max"),
    ]
    passed, missing, details = _tier_result(checks)
    return passed, missing, details


# ---------------------------------------------------------------------------
# 3) TIER 2 - GUCLU FILTRE  [BELGE] / [TAHMIN]
# ---------------------------------------------------------------------------
def evaluate_tier2(snap):
    c = config
    checks = [
        _check("Yas", snap.get("age_sec"), c.T2_MIN_AGE_SEC, "min", " sn"),
        _check("Yas ust sinir", snap.get("age_sec"), c.T2_MAX_AGE_SEC, "max", " sn"),
        _check("Likidite", snap.get("liquidity_usd"), c.T2_MIN_LIQUIDITY_USD, "min", " USD"),
        _check("Holder", snap.get("holders"), c.T2_MIN_HOLDERS, "min"),
        _check("Guvenilir trader", snap.get("trusted_traders"), c.T2_MIN_TRUSTED_TRADERS, "min"),
        _check("Gercek alis", snap.get("buys_h1"), c.T2_MIN_REAL_BUYS, "min"),
        _check("Gercek satis", snap.get("sells_h1"), c.T2_MIN_REAL_SELLS, "min"),
        _check("Hacim (1s)", snap.get("volume_h1_usd"), c.T2_MIN_VOLUME_1H_USD, "min", " USD"),
        _check("Likidite/MCap", snap.get("liq_mcap_ratio"), c.T2_MIN_LIQ_MCAP_RATIO, "min"),
        _check("En buyuk cuzdan", snap.get("top_wallet_ratio"), c.T2_MAX_TOP_WALLET_RATIO, "max"),
        _check("Ilk 10 cuzdan", snap.get("top10_wallet_ratio"), c.T2_MAX_TOP10_WALLET_RATIO, "max"),
        _check("Vergi", snap.get("max_tax"), c.T2_MAX_TAX_RATIO, "max"),
    ]
    passed, missing, details = _tier_result(checks)
    return passed, missing, details


# ---------------------------------------------------------------------------
# 4) YUKSELIS TRENDI - "en az iki kontrol arasinda olumlu ilerleme"
# ---------------------------------------------------------------------------
def rising_trend(history, min_positive_checks=2):
    """
    history: state.py'de token kaydinin "history" listesi.
    Her eleman: {"ts":, "holders":, "volume_h1_usd":, "trusted_traders":}
    En az `min_positive_checks` adet ardisik kontrolde holder/hacim/trader
    ucunun de gerilemedigi ve en az birinin gercekten arttigi kontrol edilir.
    """
    if len(history) < min_positive_checks:
        return False, "yeterli gecmis kontrol yok (en az 2 kontrol gerekli)"

    recent = history[-min_positive_checks:]
    for prev, curr in zip(recent, recent[1:]):
        keys = ["holders", "volume_h1_usd", "trusted_traders"]
        vals_prev = [prev.get(k) for k in keys]
        vals_curr = [curr.get(k) for k in keys]
        if any(v is None for v in vals_prev + vals_curr):
            return False, "gecmis veride eksik alan var"
        not_decreasing = all(c >= p for c, p in zip(vals_curr, vals_prev))
        any_increase = any(c > p for c, p in zip(vals_curr, vals_prev))
        if not (not_decreasing and any_increase):
            return False, "holder/hacim/trader arasinda gerileme veya durgunluk var"
    return True, "yukselis trendi dogrulandi"
