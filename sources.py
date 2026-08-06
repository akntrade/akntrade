"""
sources.py
----------
Dis veri kaynaklariyla konusan fonksiyonlar. Her fonksiyon ham API
cevabini olabildigince az islenmis sekilde dondurur; yorumlama/filtre
mantigi filters.py'de.

Kaynaklar (hepsi ucretsiz, key gerektirmiyor - Agustos 2026 itibariyle):
  - GeckoTerminal: yeni pool kesfi        (~30 istek/dk sinir)
  - DexScreener:   fiyat/likidite/hacim    (300 istek/dk sinir)
  - GoPlus:        kontrat guvenlik taramasi
  - Honeypot.is:   alim/satim simulasyonu + honeypot sonucu

NOT: Bu API'lerin ucu her zaman degisebilir. Bot calismazsa once bu
fonksiyonlardaki URL/parametreleri ilgili dokumantasyonla karsilastir:
  https://docs.gopluslabs.io/reference/tokensecurityusingget_1
  https://docs.honeypot.is/ishoneypot
  https://docs.dexscreener.com/api/reference
  https://apiguide.geckoterminal.com/
"""

import logging

import requests

import config

log = logging.getLogger("sources")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "akn-trade-safe-bot/1.0"})

_TIMEOUT = 12


class ApiError(Exception):
    """Beklenmeyen bir API hatasi (429 dahil) icin ortak istisna."""

    def __init__(self, message, status_code=None, rate_limited=False):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limited = rate_limited


def _get(url, params=None):
    try:
        resp = _SESSION.get(url, params=params, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise ApiError(f"baglanti hatasi: {exc}") from exc

    if resp.status_code == 429:
        raise ApiError("rate limit (429)", status_code=429, rate_limited=True)
    if resp.status_code >= 400:
        raise ApiError(f"HTTP {resp.status_code}: {resp.text[:200]}", status_code=resp.status_code)

    try:
        return resp.json()
    except ValueError as exc:
        raise ApiError(f"gecersiz JSON cevabi: {exc}") from exc


# ---------------------------------------------------------------------------
# GeckoTerminal - yeni pool kesfi
# ---------------------------------------------------------------------------
def get_new_pools(chain_key):
    """
    Bir agdaki en yeni pool'lari dondurur.
    https://api.geckoterminal.com/api/v2/networks/{network}/new_pools
    Not: DexScreener'da tum agi tarayan resmi bir "yeni pair" endpoint'i
    yok; bu yuzden kesif icin GeckoTerminal, zenginlestirme (fiyat/hacim)
    icin DexScreener kullaniliyor.
    """
    network = config.CHAIN_MAP[chain_key]["gecko_network"]
    url = f"https://api.geckoterminal.com/api/v2/networks/{network}/new_pools"
    data = _get(url)
    pools = []
    for item in data.get("data", []):
        attrs = item.get("attributes", {})
        rel = item.get("relationships", {})
        base_token_id = (
            rel.get("base_token", {}).get("data", {}).get("id", "")
        )
        # id formati genelde "bsc_0xADRES"
        token_address = base_token_id.split("_", 1)[-1] if base_token_id else None
        pools.append({
            "pool_address": attrs.get("address"),
            "token_address": token_address,
            "name": attrs.get("name"),
            "created_at": attrs.get("pool_created_at"),
        })
    return pools


# ---------------------------------------------------------------------------
# GeckoTerminal - tek pool detayi (likidite / hacim / alici-satici sayisi)
# ---------------------------------------------------------------------------
def get_pool_detail(chain_key, pool_address):
    """
    https://api.geckoterminal.com/api/v2/networks/{network}/pools/{pool_address}
    Bu endpoint DexScreener'da OLMAYAN "h1 icindeki benzersiz alici/satici
    sayisi" (buyers/sellers) verisini de veriyor - "gercek benzersiz trader"
    kriteri icin bu kullaniliyor.
    """
    network = config.CHAIN_MAP[chain_key]["gecko_network"]
    url = f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{pool_address}"
    data = _get(url)
    attrs = (data.get("data") or {}).get("attributes", {})
    tx_h1 = (attrs.get("transactions") or {}).get("h1", {}) or {}
    vol = attrs.get("volume_usd") or {}
    return {
        "liquidity_usd": _to_float(attrs.get("reserve_in_usd")),
        "market_cap_usd": _to_float(attrs.get("market_cap_usd")) or _to_float(attrs.get("fdv_usd")),
        "volume_h1_usd": _to_float(vol.get("h1")),
        "buys_h1": tx_h1.get("buys"),
        "sells_h1": tx_h1.get("sells"),
        "unique_buyers_h1": tx_h1.get("buyers"),
        "unique_sellers_h1": tx_h1.get("sellers"),
        "pool_created_at": attrs.get("pool_created_at"),
    }


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# RPC - sadece baglanti/canlilik kontrolu icin (durum raporunda gosterilir).
# Kesif ve filtreleme mantigi RPC'ye bagimli DEGIL; bu sayede bot, agir bir
# WebSocket/kontrat-event altyapisi kurmadan ucretsiz bir dyno'da da calisir.
# Gercek zamanliligi artirmak istersen (orn. Oracle Cloud VM'e gectiginde)
# burasi PairCreated event WebSocket dinleyicisine genisletilebilir.
# ---------------------------------------------------------------------------
DEFAULT_RPC_URLS = {
    "bsc": "https://bsc-dataseed.binance.org",
    "eth": "https://eth.llamarpc.com",
    "base": "https://mainnet.base.org",
}


def get_rpc_block_number(chain_key):
    import os as _os
    url = _os.environ.get("RPC_URL") or DEFAULT_RPC_URLS.get(chain_key)
    payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    resp = _SESSION.post(url, json=payload, timeout=_TIMEOUT)
    if resp.status_code >= 400:
        raise ApiError(f"RPC HTTP {resp.status_code}")
    data = resp.json()
    return int(data["result"], 16)


# ---------------------------------------------------------------------------
# DexScreener - fiyat / likidite / hacim / islem sayilari (capraz kontrol)
# ---------------------------------------------------------------------------
def get_pair_data(chain_key, pair_address):
    """
    https://api.dexscreener.com/latest/dex/pairs/{chainId}/{pairAddress}
    """
    chain_id = config.CHAIN_MAP[chain_key]["dexscreener_id"]
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pair_address}"
    data = _get(url)
    pairs = data.get("pairs") or []
    if not pairs:
        return None
    p = pairs[0]
    txns_h1 = p.get("txns", {}).get("h1", {}) or {}
    return {
        "liquidity_usd": (p.get("liquidity") or {}).get("usd"),
        "fdv": p.get("fdv"),
        "market_cap": p.get("marketCap"),
        "volume_h1_usd": (p.get("volume") or {}).get("h1"),
        "buys_h1": txns_h1.get("buys"),
        "sells_h1": txns_h1.get("sells"),
        "price_usd": p.get("priceUsd"),
        "pair_created_at_ms": p.get("pairCreatedAt"),
        "base_token_address": (p.get("baseToken") or {}).get("address"),
        "base_token_symbol": (p.get("baseToken") or {}).get("symbol"),
    }


# ---------------------------------------------------------------------------
# GoPlus - kontrat guvenlik taramasi
# ---------------------------------------------------------------------------
def get_goplus_security(chain_key, token_address):
    """
    https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses=...
    """
    chain_id = config.CHAIN_MAP[chain_key]["goplus_id"]
    url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
    data = _get(url, params={"contract_addresses": token_address})
    result = (data.get("result") or {}).get(token_address.lower())
    return result  # None ise GoPlus bu token'i henuz indexlememis demektir


# ---------------------------------------------------------------------------
# Honeypot.is - alim/satim simulasyonu
# ---------------------------------------------------------------------------
def get_honeypot_check(chain_key, token_address, pair_address=None):
    """
    https://api.honeypot.is/v2/IsHoneypot?address=...&chainID=...&pair=...
    """
    chain_id = config.CHAIN_MAP[chain_key]["goplus_id"]  # GoPlus ile ayni sayisal chain id semasi (56=BSC, 1=ETH...)
    params = {"address": token_address, "chainID": chain_id}
    if pair_address:
        params["pair"] = pair_address
    return _get("https://api.honeypot.is/v2/IsHoneypot", params=params)


# ---------------------------------------------------------------------------
# NORMALIZASYON - ham API cevaplarini filters.py'nin bekledigi sabit
# alan adlarina cevirir. API alan adi degisirse SADECE burasi guncellenir.
# ---------------------------------------------------------------------------

# Bilinen yakma/olu adresler - GoPlus bunlari "is_contract" olarak
# isaretlemeyebilir (kod calistirmiyorlar) ama "normal cuzdan" degildirler.
_BURN_ADDRESSES = {
    "0x000000000000000000000000000000000000dead",
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}


def _pct_to_float(value):
    """GoPlus yuzdeleri genelde '0.0512' gibi 0-1 arasi string olarak doner."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flag(value):
    """GoPlus bool alanlari '1'/'0' string olarak doner."""
    if value is None:
        return None
    return str(value) == "1"


def _normal_wallet_concentration(holders):
    """
    holders: GoPlus'in 'holders' listesi.
    LP/kontrat/yakma adreslerini disarida birakip, kalan en buyuk
    normal cuzdanin ve ilk 10 normal cuzdanin toplam oranini hesaplar.
    Donen degerler 0-1 arasi orandir (yuzde degil).
    """
    if not holders:
        return None, None

    normal = []
    for h in holders:
        addr = (h.get("address") or "").lower()
        if addr in _BURN_ADDRESSES:
            continue
        if _flag(h.get("is_contract")):
            continue
        tag = (h.get("tag") or "").lower()
        if any(k in tag for k in ("pancake", "uniswap", "lp", "router", "locker", "lock")):
            continue
        pct = _pct_to_float(h.get("percent"))
        if pct is not None:
            normal.append(pct)

    if not normal:
        return None, None

    normal.sort(reverse=True)
    top1 = normal[0]
    top10 = sum(normal[:10])
    return top1, top10


def normalize_goplus(raw):
    """
    raw: get_goplus_security() ciktisi (None olabilir - henuz indexlenmemis token).
    Donen sozluk, filters.py'nin bekledigi alan adlariyla.
    GoPlus alan adlari icin bkz: https://docs.gopluslabs.io/reference/tokensecurityusingget_1
    """
    if raw is None:
        return {
            "goplus_available": False,
            "goplus_says_honeypot": None,
            "is_blacklisted": None,
            "is_whitelisted": None,
            "transfer_pausable": None,
            "trading_cooldown": None,
            "owner_change_balance": None,
            "is_mintable": None,
            "custom_per_wallet_tax": None,
            "is_open_source": None,
            "buy_tax": None,
            "sell_tax": None,
            "holders": None,
            "top_wallet_ratio": None,
            "top10_wallet_ratio": None,
        }

    top1, top10 = _normal_wallet_concentration(raw.get("holders"))
    holder_count = raw.get("holder_count")
    try:
        holder_count = int(holder_count) if holder_count is not None else None
    except (TypeError, ValueError):
        holder_count = None

    goplus_honeypot = _flag(raw.get("is_honeypot"))
    if goplus_honeypot is None:
        # Bazi eski/kucuk tokenlerde is_honeypot alani yok; cannot_sell_all
        # ikincil bir gosterge olarak kullanilir.
        goplus_honeypot = _flag(raw.get("cannot_sell_all"))

    return {
        "goplus_available": True,
        "goplus_says_honeypot": goplus_honeypot,
        "is_blacklisted": _flag(raw.get("is_blacklisted")),
        "is_whitelisted": _flag(raw.get("is_whitelisted")),
        "transfer_pausable": _flag(raw.get("transfer_pausable")),
        "trading_cooldown": _flag(raw.get("trading_cooldown")),
        "owner_change_balance": _flag(raw.get("owner_change_balance")),
        "is_mintable": _flag(raw.get("is_mintable")),
        "custom_per_wallet_tax": _flag(raw.get("personal_slippage_modifiable")),
        "is_open_source": _flag(raw.get("is_open_source")),
        "buy_tax": _pct_to_float(raw.get("buy_tax")),
        "sell_tax": _pct_to_float(raw.get("sell_tax")),
        "holders": holder_count,
        "top_wallet_ratio": top1,
        "top10_wallet_ratio": top10,
    }


def normalize_honeypot(raw):
    """
    raw: get_honeypot_check() ciktisi.
    Bkz: https://docs.honeypot.is/ishoneypot
    """
    if raw is None:
        return {"is_honeypot": None, "simulation_success": None,
                "hp_buy_tax": None, "hp_sell_tax": None}

    honeypot_result = raw.get("honeypotResult") or {}
    sim_result = raw.get("simulationResult") or {}
    return {
        "is_honeypot": honeypot_result.get("isHoneypot"),
        "simulation_success": raw.get("simulationSuccess"),
        "hp_buy_tax": _pct_to_float_ratio_from_percent(sim_result.get("buyTax")),
        "hp_sell_tax": _pct_to_float_ratio_from_percent(sim_result.get("sellTax")),
    }


def _pct_to_float_ratio_from_percent(value):
    """Honeypot.is buyTax/sellTax degerlerini 0-100 yuzde olarak doner; 0-1 orana cevirir."""
    if value is None:
        return None
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# TUM KAYNAKLARI BIRLESTIREN ANA FONKSIYON
# ---------------------------------------------------------------------------
def build_snapshot(chain_key, token_address, pool_address, created_ts):
    """
    Bir token icin tum kaynaklari sorgular ve filters.py'nin bekledigi
    tek bir "snapshot" sozlugu olusturur. Herhangi bir kaynak basarisiz
    olursa ApiError firlatir - cagiran taraf (scanner.py) bunu yakalayip
    rate-limit/backoff ve loglama yapar.
    """
    import time as _time

    pool = get_pool_detail(chain_key, pool_address)
    goplus_raw = get_goplus_security(chain_key, token_address)
    goplus = normalize_goplus(goplus_raw)
    hp_raw = get_honeypot_check(chain_key, token_address, pool_address)
    hp = normalize_honeypot(hp_raw)

    age_sec = _time.time() - (created_ts or _time.time())

    liquidity_usd = pool.get("liquidity_usd")
    market_cap_usd = pool.get("market_cap_usd")
    liq_mcap_ratio = None
    if liquidity_usd is not None and market_cap_usd:
        try:
            liq_mcap_ratio = liquidity_usd / market_cap_usd
        except ZeroDivisionError:
            liq_mcap_ratio = None

    buyers = pool.get("unique_buyers_h1")
    sellers = pool.get("unique_sellers_h1")
    trusted_traders = None
    if buyers is not None or sellers is not None:
        trusted_traders = max(buyers or 0, sellers or 0)  # bkz. README: yaklasik/alt sinir tahmini

    # Honeypot.is'in simulasyon vergisi varsa GoPlus'in statik vergisinden
    # daha guvenilir kabul edilir (gercek islemle test edilmis olur).
    sell_tax = hp.get("hp_sell_tax")
    if sell_tax is None:
        sell_tax = goplus.get("sell_tax")
    buy_tax = hp.get("hp_buy_tax")
    if buy_tax is None:
        buy_tax = goplus.get("buy_tax")
    max_tax = None
    if buy_tax is not None or sell_tax is not None:
        max_tax = max(buy_tax or 0, sell_tax or 0)

    is_honeypot = hp.get("is_honeypot")
    if is_honeypot is None:
        is_honeypot = goplus.get("goplus_says_honeypot")

    return {
        "token_address": token_address,
        "pool_address": pool_address,
        "age_sec": age_sec,
        "liquidity_usd": liquidity_usd,
        "market_cap_usd": market_cap_usd,
        "liq_mcap_ratio": liq_mcap_ratio,
        "volume_h1_usd": pool.get("volume_h1_usd"),
        "buys_h1": pool.get("buys_h1"),
        "sells_h1": pool.get("sells_h1"),
        "trusted_traders": trusted_traders,
        "holders": goplus.get("holders"),
        "top_wallet_ratio": goplus.get("top_wallet_ratio"),
        "top10_wallet_ratio": goplus.get("top10_wallet_ratio"),
        "buy_tax": buy_tax,
        "sell_tax": sell_tax,
        "max_tax": max_tax,
        "is_honeypot": is_honeypot,
        "goplus_says_honeypot": goplus.get("goplus_says_honeypot"),
        "simulation_success": hp.get("simulation_success"),
        "is_blacklisted": goplus.get("is_blacklisted"),
        "is_whitelisted": goplus.get("is_whitelisted"),
        "transfer_pausable": goplus.get("transfer_pausable"),
        "trading_cooldown": goplus.get("trading_cooldown"),
        "owner_change_balance": goplus.get("owner_change_balance"),
        "is_mintable": goplus.get("is_mintable"),
        "custom_per_wallet_tax": goplus.get("custom_per_wallet_tax"),
        "is_open_source": goplus.get("is_open_source"),
        "goplus_available": goplus.get("goplus_available"),
    }
