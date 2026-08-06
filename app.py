"""
app.py
------
Uygulamanin giris noktasi. Iki isi var:

  1) Kucuk bir Flask web sunucusu:
     - GET /health   -> Render'i (ve UptimeRobot/cron-job.org gibi bir
                          disaridan "ping" servisini) uyanik tutmak icin.
     - POST /telegram-webhook -> /watchlist, /near, /summary komutlarini
                          isler.
     Render'in ucretsiz Web Service'i calisabilmek icin bir HTTP port'u
     dinlemeni istiyor - bu Flask uygulamasi o sarti karsiliyor.

  2) Arka planda surekli calisan tarayici thread'i (scanner.py).

Yerelde denemek icin:  python app.py
Render'da (gunicorn ile onerilir): gunicorn app:app
"""

import logging

from flask import Flask, request, jsonify

import config
import notifier
import scanner
import state
import safe_runtime_patch

safe_runtime_patch.apply()

log = logging.getLogger("app")

app = Flask(__name__)

_AUTHORIZED_CHAT_ID = str(config.TELEGRAM_CHAT_ID) if config.TELEGRAM_CHAT_ID else None


@app.get("/health")
@app.get("/")
def health():
    return jsonify({
        "status": "ok",
        "chain": config.CHAIN,
        "tracked_tokens": len(state.store.all_tokens()),
        "last_scan_ts": state.store.get_last_scan(),
    })


@app.post("/telegram-webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}
    text = (message.get("text") or "").strip()
    chat_id = str((message.get("chat") or {}).get("id", ""))

    if not text or not chat_id:
        return jsonify({"ok": True})

    if _AUTHORIZED_CHAT_ID and chat_id != _AUTHORIZED_CHAT_ID:
        log.warning("Yetkisiz chat_id'den komut denemesi: %s", chat_id)
        return jsonify({"ok": True})

    command = text.split()[0].lower()

    if command == "/watchlist":
        reply = notifier.format_watchlist_command(state.store.all_tokens())
    elif command == "/near":
        reply = _handle_near_command()
    elif command == "/summary":
        reply = notifier.format_status_summary(
            state.store.get_stats_6h(), state.store.get_connections(), state.store.get_last_scan()
        )
    elif command == "/start":
        reply = ("Merhaba! Bu bot BSC uzerinde yeni tokenleri tariyor.\n\n"
                 "Komutlar:\n"
                 "/watchlist - Izleme Listesi'ndeki tokenler\n"
                 "/near - Guclu Filtre'ye en yakin 5 token\n"
                 "/summary - Son 6 saatlik ozeti hemen gonder")
    else:
        reply = None

    if reply:
        notifier.send_message(reply, chat_id=chat_id)

    return jsonify({"ok": True})


def _handle_near_command():
    import filters
    import sources as _sources

    candidates = []
    for rec in state.store.all_tokens().values():
        if rec.get("critical_rejected") or rec.get("strong_sent"):
            continue
        missing_count = rec.get("last_missing_count")
        if missing_count is None:
            continue
        candidates.append((rec, rec.get("last_missing_conditions", []), missing_count))

    candidates.sort(key=lambda x: x[2])
    return notifier.format_near_command(candidates)


def _setup_webhook_if_configured():
    base_url = config.__dict__.get("PUBLIC_BASE_URL")  # bkz. .env.example
    import os
    base_url = os.environ.get("PUBLIC_BASE_URL")
    if base_url and config.TELEGRAM_BOT_TOKEN:
        webhook_url = base_url.rstrip("/") + "/telegram-webhook"
        try:
            result = notifier.set_webhook(webhook_url)
            log.info("Telegram webhook ayarlandi: %s -> %s", webhook_url, result)
        except Exception:  # noqa: BLE001
            log.exception("Webhook ayarlanamadi - PUBLIC_BASE_URL dogru mu kontrol et")


# Modul yuklenirken (hem "python app.py" hem "gunicorn app:app" icin) baslat
_setup_webhook_if_configured()
scanner.start_background_thread()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
