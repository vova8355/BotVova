import asyncio
import logging
import random
import json
import os
import sys

import qrcode
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

# ─── Config ───────────────────────────────────────────────────────────────────

CONFIG_FILE = "config.json"

BANNER = r"""
██▒   █▓ ▒█████   ██▒   █▓ ▄▄▄      
▓██░   █▒▒██▒  ██▒▓██░   █▒▒████▄    
 ▓██  █▒░▒██░  ██▒ ▓██  █▒░▒██  ▀█▄  
  ▒██ █░░▒██   ██░  ▒██ █░░░██▄▄▄▄██ 
   ▒▀█░  ░ ████▓▒░   ▒▀█░   ▓█   ▓██▒
   ░ ▐░  ░ ▒░▒░▒░    ░ ▐░   ▒▒   ▓▒█░
   ░ ░░    ░ ▒ ▒░    ░ ░░    ▒   ▒▒ ░
     ░░  ░ ░ ░ ▒       ░░    ░   ▒   
      ░      ░ ░        ░        ░  ░
     ░                 ░
"""

TEMPLATE = {
    "api_id": 0,
    "api_hash": "",
    "session_name": "userbot",
    "trigger": "/vova",
    "target_chats": ["@BabizyanChat"],
    "default_replies": [
        {"text": "привет", "weight": 47.5},
        {"text": "приает", "weight": 47.5},
        {"text": "привет, как дела?", "weight": 5.0}
    ],
    "personal_replies": [
        {
            "user": "@pacput",
            "replies": [
                {"text": "привет Вова", "weight": 70},
                {"text": "привет!!!",   "weight": 30}
            ]
        }
    ]
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        raw = json.dumps(TEMPLATE, ensure_ascii=False, indent=2)
        import re
        raw = re.sub(
            r'("target_chats":\s*)\[\s*([\s\S]*?)\s*\]',
            lambda m: m.group(1) + "[" + ", ".join(v.strip() for v in m.group(2).split(",")) + "]",
            raw
        )
        with open(CONFIG_FILE, "w", encoding="utf-8") as fp:
            fp.write(raw)
        print(f"[!] Файл {CONFIG_FILE} создан. Заполни его и запусти бота снова.")
        print("[!] Инструкция — читай README.txt")
        sys.exit(0)

    with open(CONFIG_FILE, "r", encoding="utf-8") as fp:
        cfg = json.load(fp)

    if not cfg.get("api_id") or cfg.get("api_id") == 0:
        print("[!] Впиши api_id в config.json (цифры без кавычек, с my.telegram.org)")
        sys.exit(1)
    if not cfg.get("api_hash") or cfg.get("api_hash") == "":
        print("[!] Впиши api_hash в config.json (строка в кавычках, с my.telegram.org)")
        sys.exit(1)

    return cfg


cfg = load_config()

API_ID       = int(cfg["api_id"])
API_HASH     = cfg["api_hash"]
SESSION_NAME = cfg.get("session_name", "userbot")
TRIGGER      = cfg["trigger"]

DEFAULT_REPLIES      = cfg["default_replies"]
RAW_TARGET_CHATS     = cfg["target_chats"]
RAW_PERSONAL_REPLIES = cfg.get("personal_replies", [])

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M",
)
logging.getLogger("telethon").setLevel(logging.WARNING)
log = logging.getLogger("userbot")

# ─── Client ───────────────────────────────────────────────────────────────────

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# ─── Resolve usernames → IDs ──────────────────────────────────────────────────

async def resolve_entity_id(value):
    if isinstance(value, int):
        return value
    try:
        entity = await client.get_entity(value)
        return entity.id
    except Exception as e:
        log.warning("Не удалось определить ID для '%s': %s", value, e)
        return None


async def resolve_all():
    global TARGET_CHATS, PERSONAL_REPLIES

    log.info("Загрузка чатов и пользователей...")

    resolved_chats = []
    for entry in RAW_TARGET_CHATS:
        eid = await resolve_entity_id(entry)
        if eid is not None:
            resolved_chats.append(eid)
            if str(entry) != str(eid):
                log.info("  Чат '%s' → %s", entry, eid)
    TARGET_CHATS = resolved_chats

    resolved_personal = {}
    for item in RAW_PERSONAL_REPLIES:
        raw = item.get("user") or item.get("user_id")
        if raw is None:
            log.warning("В personal_replies пропущено поле 'user': %s", item)
            continue
        uid = await resolve_entity_id(raw)
        if uid is not None:
            resolved_personal[str(uid)] = item["replies"]
            if str(raw) != str(uid):
                log.info("  Пользователь '%s' → %s", raw, uid)
    PERSONAL_REPLIES = resolved_personal

    log.info("Чаты: %s", TARGET_CHATS)
    log.info("Персональных правил: %d", len(PERSONAL_REPLIES))

# ─── Helpers ──────────────────────────────────────────────────────────────────

def weighted_choice(replies: list) -> str:
    texts   = [r["text"]   for r in replies]
    weights = [r["weight"] for r in replies]
    return random.choices(texts, weights=weights, k=1)[0]

# ─── Event handler ────────────────────────────────────────────────────────────

async def handler(event):
    if (event.raw_text or "").strip() != TRIGGER:
        return

    sender_id = str(event.sender_id)

    if sender_id in PERSONAL_REPLIES:
        reply_text = weighted_choice(PERSONAL_REPLIES[sender_id])
    else:
        reply_text = weighted_choice(DEFAULT_REPLIES)

    await event.reply(reply_text)
    log.info("Ответил в чате %s пользователю %s: %s",
             event.chat_id, event.sender_id, reply_text)

# ─── Auth ─────────────────────────────────────────────────────────────────────

async def login_with_qr():
    while True:
        qr_login = await client.qr_login()
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_login.url)
        qr.make()
        qr.print_ascii(invert=True)
        print("Отсканируй QR в Telegram: Настройки → Устройства → Привязать устройство\n")
        try:
            await qr_login.wait(timeout=60)
            return
        except SessionPasswordNeededError:
            pwd = input("Пароль двухфакторной аутентификации: ")
            await client.sign_in(password=pwd)
            return
        except asyncio.TimeoutError:
            log.info("QR истёк, генерирую новый...")


async def login_with_code():
    from telethon.errors import (
        PhoneNumberInvalidError, FloodWaitError,
        PhoneCodeInvalidError, PhoneCodeExpiredError,
    )

    phone = input("Номер телефона (с кодом страны, напр. +79001234567): ").strip()
    phone = phone.replace(" ", "").replace("-", "")

    try:
        await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        print("[!] Неверный номер. Формат: +79001234567")
        return await login_with_code()
    except FloodWaitError as e:
        print(f"[!] Telegram просит подождать {e.seconds} секунд. Попробуй позже.")
        sys.exit(1)

    code = input("Код из Telegram (только цифры): ").strip()
    try:
        await client.sign_in(phone, code)
    except PhoneCodeInvalidError:
        print("[!] Неверный код. Попробуй ещё раз.")
        return await login_with_code()
    except PhoneCodeExpiredError:
        print("[!] Код истёк. Запрашиваю новый...")
        return await login_with_code()
    except SessionPasswordNeededError:
        pwd = input("Пароль двухфакторной аутентификации: ")
        await client.sign_in(password=pwd)


async def choose_login():
    print("\nВыбери способ входа:")
    print("  1 — QR-код")
    print("  2 — Код в Telegram/SMS")
    choice = input("Твой выбор [1/2]: ").strip()
    if choice == "1":
        await login_with_qr()
    elif choice == "2":
        await login_with_code()
    else:
        print("Некорректный выбор, попробуй снова.")
        await choose_login()

# ─── Entry point ──────────────────────────────────────────────────────────────

async def main():
    print(BANNER) 
    log.info("Подключение к Telegram...")
    await client.connect()

    if not await client.is_user_authorized():
        await choose_login()

    await resolve_all()

    client.add_event_handler(handler, events.NewMessage(chats=TARGET_CHATS))

    log.info("Бот запущен. Триггер '%s'", TRIGGER)
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
