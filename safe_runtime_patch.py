"""Runtime fixes for public API limits and very new Honeypot pairs."""

import logging
import threading
import time

import sources

log = logging.getLogger("runtime_patch")

_GOPLUS_MIN_INTERVAL_SEC = 4.0
_goplus_lock = threading.Lock()
_last_goplus_call = 0.0
_applied = False


def apply():
    global _applied
    if _applied:
        return
    _applied = True

    original_goplus = sources.get_goplus_security
    original_honeypot = sources.get_honeypot_check

    def throttled_goplus(chain_key, token_address):
        global _last_goplus_call

        with _goplus_lock:
            elapsed = time.monotonic() - _last_goplus_call
            wait_for = _GOPLUS_MIN_INTERVAL_SEC - elapsed

            if wait_for > 0:
                time.sleep(wait_for)

            try:
                return original_goplus(chain_key, token_address)
            finally:
                _last_goplus_call = time.monotonic()

    def tolerant_honeypot(chain_key, token_address, pair_address=None):
        try:
            return original_honeypot(chain_key, token_address, pair_address)

        except sources.ApiError as exc:
            if exc.status_code != 404:
                raise

            if pair_address:
                log.info(
                    "Honeypot pair henuz indekslenmemis, pair olmadan tekrar deneniyor: %s",
                    token_address,
                )

                try:
                    return original_honeypot(chain_key, token_address, None)

                except sources.ApiError as retry_exc:
                    if retry_exc.status_code != 404:
                        raise

            log.info(
                "Honeypot verisi henuz yok, sonraki kontrolde tekrar denenecek: %s",
                token_address,
            )
            return None

    sources.get_goplus_security = throttled_goplus
    sources.get_honeypot_check = tolerant_honeypot

    log.info("API rate-limit ve yeni pair yamalari etkinlestirildi")
