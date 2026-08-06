"""
state.py
--------
Botun hafizasi. Tum takip edilen tokenler, gecmis kontrol sonuclari,
gonderilen bildirimler ve rapor sayaclari burada, tek bir JSON dosyasinda
tutulur ve thread-safe okunur/yazilir.

ONEMLI SINIRLAMA (dogrudan Akin'a soylenmeli):
Render gibi ucretsiz platformlarda kalici disk YOKTUR (bu ozellik
ucretli plana ait). Yani servis yeniden baslarsa (redeploy, cokme,
Render'in kendi bakim islemleri vb.) bu dosya SIFIRLANIR - o ana kadar
takip edilen tokenler ve "kac kontrolde yukseliyordu" gecmisi kaybolur.
Bu, "sunucu parasi odemeyecegim" tercihinin dogal bir bedeli.
Kalici saklama istenirse ucretsiz bir Postgres (orn. Supabase/Neon free
tier) baglamak ileride kolay bir yukseltme olur.
"""

import json
import os
import threading
import time

import config

_lock = threading.RLock()


def _empty_counter():
    return {
        "since_ts": None,
        "reviewed": 0,
        "rejected_critical": 0,
        "rejected_liquidity": 0,
        "added_watchlist": 0,
        "passed_strong": 0,
    }


_DEFAULT_STATE = {
    "tokens": {},              # address -> token record (bkz. asagida)
    "stats_6h": _empty_counter(),      # 6 saatlik ozet icin, gonderildikce sifirlanir
    "stats_daily": _empty_counter(),   # gunluk rapor icin, 23:00'da sifirlanir
    "connections": {           # durum raporlarinda gosterilen baglanti durumu
        "rpc": "bilinmiyor",
        "dexscreener": "bilinmiyor",
        "goplus": "bilinmiyor",
        "honeypot_is": "bilinmiyor",
    },
    "last_scan_ts": None,
    "rate_limit_multiplier": {},       # kaynak adi -> mevcut backoff carpani
    "last_6h_summary_ts": None,
    "last_daily_report_date": None,    # "YYYY-MM-DD" (Europe/Istanbul) - ayni gun tekrar gondermemek icin
}


def _now():
    return time.time()


class Store:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with _lock:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    self.data = json.loads(json.dumps(_DEFAULT_STATE))
            else:
                self.data = json.loads(json.dumps(_DEFAULT_STATE))
            # Eski dosyalardan gecis / eksik anahtarlari tamamla
            for key, default_val in _DEFAULT_STATE.items():
                self.data.setdefault(key, default_val)
            if self.data["stats_6h"].get("since_ts") is None:
                self.data["stats_6h"]["since_ts"] = _now()
            if self.data["stats_daily"].get("since_ts") is None:
                self.data["stats_daily"]["since_ts"] = _now()
            self._save()

    def _save(self):
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    # --- token kayitlari -----------------------------------------------
    def get_token(self, address):
        with _lock:
            return self.data["tokens"].get(address.lower())

    def upsert_token(self, address, record):
        with _lock:
            self.data["tokens"][address.lower()] = record
            self._save()

    def all_tokens(self):
        with _lock:
            return dict(self.data["tokens"])

    def remove_token(self, address):
        with _lock:
            self.data["tokens"].pop(address.lower(), None)
            self._save()

    def prune_old_tokens(self, max_age_sec):
        with _lock:
            now = _now()
            to_delete = [
                addr for addr, rec in self.data["tokens"].items()
                if now - rec.get("first_seen_ts", now) > max_age_sec
            ]
            for addr in to_delete:
                del self.data["tokens"][addr]
            if to_delete:
                self._save()
            return len(to_delete)

    # --- sayaclar (hem 6h hem daily ayni anda artar) --------------------
    def bump_stat(self, key, amount=1):
        with _lock:
            self.data["stats_6h"][key] = self.data["stats_6h"].get(key, 0) + amount
            self.data["stats_daily"][key] = self.data["stats_daily"].get(key, 0) + amount
            self._save()

    def reset_stats_6h(self):
        with _lock:
            self.data["stats_6h"] = _empty_counter()
            self.data["stats_6h"]["since_ts"] = _now()
            self.data["last_6h_summary_ts"] = _now()
            self._save()

    def reset_stats_daily(self):
        with _lock:
            self.data["stats_daily"] = _empty_counter()
            self.data["stats_daily"]["since_ts"] = _now()
            self._save()

    def get_stats_6h(self):
        with _lock:
            return dict(self.data["stats_6h"])

    def get_stats_daily(self):
        with _lock:
            return dict(self.data["stats_daily"])

    def get_last_6h_summary_ts(self):
        with _lock:
            return self.data.get("last_6h_summary_ts")

    def get_last_daily_report_date(self):
        with _lock:
            return self.data.get("last_daily_report_date")

    def set_last_daily_report_date(self, date_str):
        with _lock:
            self.data["last_daily_report_date"] = date_str
            self._save()

    # --- baglanti durumu ---------------------------------------------
    def set_connection_status(self, name, status):
        with _lock:
            self.data.setdefault("connections", {})[name] = status
            self._save()

    def get_connections(self):
        with _lock:
            return dict(self.data.get("connections", {}))

    # --- tarama zamani ------------------------------------------------
    def set_last_scan(self):
        with _lock:
            self.data["last_scan_ts"] = _now()
            self._save()

    def get_last_scan(self):
        with _lock:
            return self.data.get("last_scan_ts")

    # --- rate-limit backoff -------------------------------------------
    def get_backoff(self, source):
        with _lock:
            return self.data.get("rate_limit_multiplier", {}).get(source, 1.0)

    def set_backoff(self, source, multiplier):
        with _lock:
            self.data.setdefault("rate_limit_multiplier", {})[source] = multiplier
            self._save()


store = Store(config.STATE_FILE)


def new_token_record(address, symbol, pair_address, created_ts):
    """Yeni tespit edilen bir token icin bos kayit sablonu."""
    return {
        "address": address.lower(),
        "symbol": symbol,
        "pair_address": pair_address,
        "first_seen_ts": _now(),
        "created_ts": created_ts,
        "last_check_ts": 0,
        "next_check_ts": _now(),
        "history": [],          # her kontrolde eklenen ozet (holders, volume, traders, ts)
        "critical_rejected": False,
        "critical_reason": None,
        "watchlist_sent": False,
        "strong_sent": False,
        "last_missing_conditions": [],
        "last_missing_count": None,
    }
