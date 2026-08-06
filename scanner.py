"""
scanner.py
----------
Botun kalbi. Tek bir arka plan thread'inde sonsuz donguyle calisir:

  1) Yeni token/pool kesfi (GeckoTerminal new_pools)          - NEW_TOKEN_SCAN_INTERVAL_SEC
  2) Takip edilen her token icin, yasina gore siradaki kontrol - AGE_*_INTERVAL_SEC
  3) 6 saatlik ozet ve gunluk (23:00 Istanbul) rapor gonderimi
  4) API rate-limit'e yaklasinca otomatik yavaslama

Tasarim notu: dogruluk > hiz. Bir token'in kontrolu basarisiz olursa
(API hatasi/rate-limit) o token'i "kaybetmiyoruz" - bir sonraki turda
tekrar denenir, sadece o turun sayaclarina yansimaz.
"""

import logging
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import config
import filters
import notifier
import sources
import state

log = logging.getLogger("scanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

_TZ = ZoneInfo(config.TIMEZONE)

_next_new_token_scan_ts = 0
_next_conn_check_ts = 0


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------
def _parse_iso_ts(iso_str):
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _interval_for_age(age_sec):
    c = config
    if age_sec <= 15 * 60:
        return c.EARLY_CHECK_INTERVAL_SEC
    if age_sec <= 60 * 60:
        return c.AGE_15_60_MIN_INTERVAL_SEC
    if age_sec <= 4 * 3600:
        return c.AGE_1_4_H_INTERVAL_SEC
    return c.AGE_4_6_H_INTERVAL_SEC


def _apply_backoff(source, base_interval):
    mult = state.store.get_backoff(source)
    return base_interval * mult


def _bump_backoff(source):
    cur = state.store.get_backoff(source)
    new = min(cur * config.RATE_LIMIT_BACKOFF_MULTIPLIER, config.RATE_LIMIT_BACKOFF_MAX_MULTIPLIER)
    state.store.set_backoff(source, new)
    log.warning("Rate limit yaklasti (%s), aralik carpani %.1f -> %.1f", source, cur, new)


def _relax_backoff(source):
    cur = state.store.get_backoff(source)
    if cur > 1.0:
        state.store.set_backoff(source, max(1.0, cur / config.RATE_LIMIT_BACKOFF_MULTIPLIER))


# ---------------------------------------------------------------------------
# 1) Kesif
# ---------------------------------------------------------------------------
def discover_new_tokens():
    try:
        pools = sources.get_new_pools(config.CHAIN)
        _relax_backoff("geckoterminal")
    except sources.ApiError as exc:
        if exc.rate_limited:
            _bump_backoff("geckoterminal")
        log.error("Yeni pool taramasi basarisiz: %s", exc)
        return

    for p in pools:
        token_addr = p.get("token_address")
        pool_addr = p.get("pool_address")
        if not token_addr or not pool_addr:
            continue
        if state.store.get_token(token_addr):
            continue  # zaten takipte
        created_ts = _parse_iso_ts(p.get("created_at")) or time.time()
        rec = state.new_token_record(token_addr, p.get("name"), pool_addr, created_ts)
        state.store.upsert_token(token_addr, rec)
        log.info("Yeni token takibe alindi: %s (%s)", p.get("name"), token_addr)


# ---------------------------------------------------------------------------
# 2) Tek token kontrolu
# ---------------------------------------------------------------------------
def check_token(rec):
    address = rec["address"]
    try:
        snap = sources.build_snapshot(config.CHAIN, address, rec["pair_address"], rec["created_ts"])
        _relax_backoff("goplus")
        _relax_backoff("honeypot_is")
        _relax_backoff("geckoterminal")
    except sources.ApiError as exc:
        if exc.rate_limited:
            _bump_backoff("goplus")
        log.warning("Kontrol basarisiz (%s): %s", address, exc)
        # next_check_ts'i kisa bir sure sonraya ertele, token'i kaybetme
        rec["next_check_ts"] = time.time() + 30
        state.store.upsert_token(address, rec)
        return

    state.store.bump_stat("reviewed")

    rejected, reasons = filters.check_critical_risks(snap)
    if rejected:
        rec["critical_rejected"] = True
        rec["critical_reason"] = "; ".join(reasons)
        state.store.upsert_token(address, rec)
        state.store.bump_stat("rejected_critical")
        log.info("Kritik risk nedeniyle elendi: %s -> %s", address, rec["critical_reason"])
        return

    if snap.get("liquidity_usd") is not None and snap["liquidity_usd"] < config.T1_MIN_LIQUIDITY_USD:
        state.store.bump_stat("rejected_liquidity")

    # Gecmise bu kontrolun ozetini ekle (trend kontrolu icin)
    rec["history"].append({
        "ts": time.time(),
        "holders": snap.get("holders"),
        "volume_h1_usd": snap.get("volume_h1_usd"),
        "trusted_traders": snap.get("trusted_traders"),
    })
    rec["history"] = rec["history"][-10:]  # son 10 kontrolle sinirla

    is_rising, rising_reason = filters.rising_trend(rec["history"], config.T1_MIN_POSITIVE_CHECKS)

    t1_passed, t1_missing, _ = filters.evaluate_tier1(snap)
    t2_passed, t2_missing, _ = filters.evaluate_tier2(snap)

    rec["last_missing_conditions"] = t2_missing
    rec["last_missing_count"] = len(t2_missing)

    if t1_passed and is_rising and not rec["watchlist_sent"]:
        text = notifier.format_watchlist_alert(config.CHAIN, snap, t2_missing, symbol=rec.get("symbol"))
        notifier.send_message(text)
        rec["watchlist_sent"] = True
        state.store.bump_stat("added_watchlist")
        log.info("Izleme Listesi bildirimi gonderildi: %s", address)

    if t2_passed and is_rising and not rec["strong_sent"]:
        text = notifier.format_strong_alert(config.CHAIN, snap, symbol=rec.get("symbol"))
        notifier.send_message(text)
        rec["strong_sent"] = True
        state.store.bump_stat("passed_strong")
        log.info("Guclu Filtre bildirimi gonderildi: %s", address)

    rec["last_check_ts"] = time.time()
    rec["next_check_ts"] = time.time() + _apply_backoff("goplus", _interval_for_age(snap["age_sec"]))
    state.store.upsert_token(address, rec)


# ---------------------------------------------------------------------------
# 3) Baglanti durumu (rapor icin)
# ---------------------------------------------------------------------------
_WELL_KNOWN = {
    "bsc": {"token": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
            "pair": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16"},  # WBNB/BUSD PancakeSwap
}


def check_connections():
    # RPC
    try:
        sources.get_rpc_block_number(config.CHAIN)
        state.store.set_connection_status("rpc", "OK")
    except Exception as exc:  # noqa: BLE001 - durum raporu icin genis yakalama kasitli
        state.store.set_connection_status("rpc", f"HATA: {exc}")

    # DexScreener (capraz kontrol amacli, bilinen bir pair ile)
    wk = _WELL_KNOWN.get(config.CHAIN)
    try:
        if wk:
            sources.get_pair_data(config.CHAIN, wk["pair"])
        state.store.set_connection_status("dexscreener", "OK")
    except Exception as exc:  # noqa: BLE001
        state.store.set_connection_status("dexscreener", f"HATA: {exc}")

    # GoPlus
    try:
        if wk:
            sources.get_goplus_security(config.CHAIN, wk["token"])
        state.store.set_connection_status("goplus", "OK")
    except Exception as exc:  # noqa: BLE001
        state.store.set_connection_status("goplus", f"HATA: {exc}")

    # Honeypot.is
    try:
        if wk:
            sources.get_honeypot_check(config.CHAIN, wk["token"])
        state.store.set_connection_status("honeypot_is", "OK")
    except Exception as exc:  # noqa: BLE001
        state.store.set_connection_status("honeypot_is", f"HATA: {exc}")


# ---------------------------------------------------------------------------
# 4) Rapor zamanlamasi
# ---------------------------------------------------------------------------
def maybe_send_periodic_reports():
    now = time.time()
    last_6h = state.store.get_last_6h_summary_ts()
    if last_6h is None or now - last_6h >= config.STATUS_SUMMARY_INTERVAL_SEC:
        stats = state.store.get_stats_6h()
        conns = state.store.get_connections()
        text = notifier.format_status_summary(stats, conns, state.store.get_last_scan())
        notifier.send_message(text)
        state.store.reset_stats_6h()

    now_istanbul = datetime.now(_TZ)
    today_str = now_istanbul.strftime("%Y-%m-%d")
    if now_istanbul.hour == config.DAILY_REPORT_HOUR and state.store.get_last_daily_report_date() != today_str:
        stats = state.store.get_stats_daily()
        conns = state.store.get_connections()
        text = notifier.format_daily_report(stats, conns, state.store.get_last_scan())
        notifier.send_message(text)
        state.store.reset_stats_daily()
        state.store.set_last_daily_report_date(today_str)


# ---------------------------------------------------------------------------
# Ana dongu
# ---------------------------------------------------------------------------
def run_forever():
    global _next_new_token_scan_ts, _next_conn_check_ts
    log.info("Tarayici baslatildi. Zincir: %s", config.CHAIN)

    while True:
        now = time.time()
        try:
            if now >= _next_new_token_scan_ts:
                discover_new_tokens()
                state.store.set_last_scan()
                _next_new_token_scan_ts = now + _apply_backoff(
                    "geckoterminal", config.NEW_TOKEN_SCAN_INTERVAL_SEC
                )

            if now >= _next_conn_check_ts:
                check_connections()
                _next_conn_check_ts = now + 300  # 5 dakikada bir baglanti kontrolu

            due = [
                rec for rec in state.store.all_tokens().values()
                if not rec.get("critical_rejected") and now >= rec.get("next_check_ts", 0)
            ]
            for rec in due:
                check_token(rec)

            removed = state.store.prune_old_tokens(config.MAX_TRACK_AGE_SEC)
            if removed:
                log.info("%d token takip ufkunun disina cikti, birakildi", removed)

            maybe_send_periodic_reports()
        except Exception:  # noqa: BLE001 - ana dongu asla tamamen durmamali
            log.exception("Ana dongude beklenmeyen hata, devam ediliyor")

        time.sleep(15)


def start_background_thread():
    t = threading.Thread(target=run_forever, name="scanner", daemon=True)
    t.start()
    return t
