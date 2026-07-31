# -*- coding: utf-8 -*-
"""
send_to_telegram.py
--------------------
tweets.csv icindeki siradaki "pending" tweeti Telegram Bot API uzerinden
sana ozel mesaj olarak gonderir. Sen mesaji goruyorsun, kopyalayip X'e
kendi elinle yapistirip paylasiyorsun. Hicbir X API kullanilmiyor, hicbir
ucret yok.

Kullanim:
    python3 send_to_telegram.py --slot sabah
    python3 send_to_telegram.py --slot ogleden_sonra
    python3 send_to_telegram.py --slot aksam
"""

import csv
import os
import sys
import argparse
import logging
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "tweets.csv")
LOG_PATH = os.path.join(BASE_DIR, "send_log.txt")

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def read_rows():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    return rows, fieldnames


def write_rows(rows, fieldnames):
    tmp_path = CSV_PATH + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, CSV_PATH)  # atomik degistirme


def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    resp = requests.post(url, data=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", default="", help="sabah / ogleden_sonra / aksam (sadece kayit icin)")
    parser.add_argument("--dry-run", action="store_true", help="Gercekten gondermeden sadece secilecek tweeti goster")
    args = parser.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    rows, fieldnames = read_rows()

    target_idx = None
    for idx, row in enumerate(rows):
        if row["status"] == "pending":
            target_idx = idx
            break

    if target_idx is None:
        msg = "Bekleyen tweet kalmadi. Kuyruk bitti, yeni tweet eklenmesi gerekiyor."
        print(msg)
        logging.warning(msg)
        if token and chat_id and not args.dry_run:
            try:
                send_telegram_message(token, chat_id, "AKN Trades botu: kuyrukta bekleyen tweet kalmadi, yeni tweet eklemen gerekiyor.")
            except Exception:
                pass
        sys.exit(0)

    row = rows[target_idx]
    text = row["tweet_text"]

    if args.dry_run:
        print(f"[DRY RUN] #{row['id']} gonderilecekti:\n{text}")
        return

    if not token or not chat_id:
        print("HATA: TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID .env dosyasinda bulunamadi.")
        sys.exit(1)

    full_message = text

    try:
        send_telegram_message(token, chat_id, full_message)
    except Exception as e:
        logging.error(f"Tweet #{row['id']} Telegram'a gonderilirken hata: {e}")
        print(f"HATA: Tweet #{row['id']} gonderilemedi: {e}")
        sys.exit(1)

    row["status"] = "sent"
    row["scheduled_slot"] = args.slot
    row["posted_at"] = datetime.now(timezone.utc).isoformat()
    row["posted_tweet_id"] = ""  # manuel paylasim oldugu icin X tweet ID'si burada tutulmuyor
    rows[target_idx] = row

    write_rows(rows, fieldnames)

    msg = f"Tweet #{row['id']} basariyla Telegram'a gonderildi (slot: {args.slot})"
    print(msg)
    logging.info(msg)


if __name__ == "__main__":
    main()
