"""
notifier.py
-----------
Telegram'a mesaj gonderme ve mesaj metinlerini olusturma.
Buyuk kutuphane (python-telegram-bot) yerine ham Bot API cagrisi
kullaniliyor - daha az bagimlilik, daha az hata noktasi.
"""

import logging
import time

import requests

import config

log = logging.getLogger("notifier")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _url(method):
    return _TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)


def send_message(text, chat_id=None):
    chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not config.TELEGRAM_BOT_TOKEN or not chat_id:
        log.warning("TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamis, mesaj gonderilemedi")
        return False
    try:
        resp = requests.post(
            _url("sendMessage"),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=10,
        )
        if resp.status_code != 200:
            log.error("Telegram gonderim hatasi: %s %s", resp.status_code, resp.text[:300])
            return False
        return True
    except requests.RequestException as exc:
        log.error("Telegram baglanti hatasi: %s", exc)
        return False


def set_webhook(webhook_url):
    resp = requests.post(_url("setWebhook"), json={"url": webhook_url}, timeout=10)
    return resp.json()


def _explorer_link(chain_key, token_address):
    bases = {
        "bsc": "https://bscscan.com/token/",
        "eth": "https://etherscan.io/token/",
        "base": "https://basescan.org/token/",
    }
    return bases.get(chain_key, "https://bscscan.com/token/") + token_address


def _dexscreener_link(chain_key, pool_address):
    ids = config.CHAIN_MAP[chain_key]["dexscreener_id"]
    return f"https://dexscreener.com/{ids}/{pool_address}"


def _fmt_usd(v):
    if v is None:
        return "?"
    return f"${v:,.0f}"


def _fmt_pct(v):
    if v is None:
        return "?"
    return f"%{v * 100:.1f}"


def format_watchlist_alert(chain_key, snap, missing_tier2, symbol=None):
    name = symbol or snap["token_address"][:10]
    lines = [
        f"🟡 <b>IZLEME LISTESI</b> - {name}",
        "",
        "<b>Bu bir alim onerisi DEGILDIR.</b> Bu token henuz Guclu Filtre'yi "
        "gecmedi - erken ve daha riskli bir aday olarak izleniyor.",
        "",
        f"Yas: {int(snap['age_sec'] // 60)} dk",
        f"Likidite: {_fmt_usd(snap.get('liquidity_usd'))}",
        f"Holder: {snap.get('holders', '?')}",
        f"Guvenilir trader (tahmini): {snap.get('trusted_traders', '?')}",
        f"Alis/Satis (1s): {snap.get('buys_h1', '?')}/{snap.get('sells_h1', '?')}",
        f"Likidite/MCap: {_fmt_pct(snap.get('liq_mcap_ratio'))}",
        f"En buyuk cuzdan: {_fmt_pct(snap.get('top_wallet_ratio'))}",
        f"Ilk 10 cuzdan: {_fmt_pct(snap.get('top10_wallet_ratio'))}",
        f"Vergi (alis/satis max): {_fmt_pct(snap.get('max_tax'))}",
        "",
        "<b>Guclu Filtre icin eksik sartlar:</b>",
    ]
    for m in missing_tier2:
        lines.append(f"  • {m}")
    lines += [
        "",
        f"Kontrat: <code>{snap['token_address']}</code>",
        f"DexScreener: {_dexscreener_link(chain_key, snap['pool_address'])}",
        f"Explorer: {_explorer_link(chain_key, snap['token_address'])}",
    ]
    return "\n".join(lines)


def format_strong_alert(chain_key, snap, symbol=None):
    name = symbol or snap["token_address"][:10]
    lines = [
        f"🟢 <b>GUCLU FILTREYI GECTI</b> - {name}",
        "",
        "Katı SAFE kriterlerinin tamamini karsiladi. Bu yine de bir yatirim "
        "tavsiyesi degildir - kendi arastirmani yap.",
        "",
        f"Yas: {int(snap['age_sec'] // 60)} dk",
        f"Likidite: {_fmt_usd(snap.get('liquidity_usd'))}",
        f"Holder: {snap.get('holders', '?')}",
        f"Guvenilir trader (tahmini): {snap.get('trusted_traders', '?')}",
        f"Alis/Satis (1s): {snap.get('buys_h1', '?')}/{snap.get('sells_h1', '?')}",
        f"Likidite/MCap: {_fmt_pct(snap.get('liq_mcap_ratio'))}",
        f"En buyuk cuzdan: {_fmt_pct(snap.get('top_wallet_ratio'))}",
        f"Ilk 10 cuzdan: {_fmt_pct(snap.get('top10_wallet_ratio'))}",
        f"Vergi (alis/satis max): {_fmt_pct(snap.get('max_tax'))}",
        "",
        f"Kontrat: <code>{snap['token_address']}</code>",
        f"DexScreener: {_dexscreener_link(chain_key, snap['pool_address'])}",
        f"Explorer: {_explorer_link(chain_key, snap['token_address'])}",
    ]
    return "\n".join(lines)


def format_status_summary(stats, connections, last_scan_ts):
    since = stats.get("since_ts")
    since_str = time.strftime("%H:%M", time.localtime(since)) if since else "?"
    last_scan_str = time.strftime("%H:%M:%S", time.localtime(last_scan_ts)) if last_scan_ts else "hic"
    lines = [
        "📊 <b>6 saatlik ozet</b>",
        f"({since_str} - simdi)",
        "",
        f"Son tarama: {last_scan_str}",
        f"Incelenen token: {stats.get('reviewed', 0)}",
        f"Kritik risk nedeniyle elenen: {stats.get('rejected_critical', 0)}",
        f"Dusuk likidite nedeniyle elenen: {stats.get('rejected_liquidity', 0)}",
        f"Izleme Listesi'ne alinan: {stats.get('added_watchlist', 0)}",
        f"Guclu Filtre'yi gecen: {stats.get('passed_strong', 0)}",
        "",
        "Baglanti durumu:",
        f"  RPC: {connections.get('rpc', '?')}",
        f"  DexScreener: {connections.get('dexscreener', '?')}",
        f"  GoPlus: {connections.get('goplus', '?')}",
        f"  Honeypot.is: {connections.get('honeypot_is', '?')}",
    ]
    return "\n".join(lines)


def format_daily_report(stats, connections, last_scan_ts):
    lines = format_status_summary(stats, connections, last_scan_ts).split("\n")
    lines[0] = "🗓 <b>Gunluk rapor (23:00 Europe/Istanbul)</b>"
    return "\n".join(lines)


def format_watchlist_command(tracked_tokens):
    watchlisted = [t for t in tracked_tokens.values() if t.get("watchlist_sent")]
    if not watchlisted:
        return "Izleme Listesi'nde su an bir token yok."
    lines = ["🟡 <b>Izleme Listesi</b>", ""]
    for t in watchlisted[:25]:
        age_min = int((time.time() - t.get("first_seen_ts", time.time())) // 60)
        lines.append(f"• {t.get('symbol', t['address'][:10])} - {age_min} dk - <code>{t['address']}</code>")
    return "\n".join(lines)


def format_near_command(candidates):
    """
    candidates: [(token_record, missing_list, missing_count), ...] - en yakin 5.
    """
    if not candidates:
        return "Guclu Filtre'ye yakin bir token yok."
    lines = ["🎯 <b>Guclu Filtre'ye en yakin 5 token</b>", ""]
    for rec, missing, _ in candidates[:5]:
        lines.append(f"<b>{rec.get('symbol', rec['address'][:10])}</b> - <code>{rec['address']}</code>")
        if missing:
            for m in missing:
                lines.append(f"  • {m}")
        else:
            lines.append("  • (bir sonraki kontrolde gecebilir)")
        lines.append("")
    return "\n".join(lines).strip()
