"""Заявки из чатов Telegram. Запускается на ПК Hazzer раз в час (Планировщик заданий Windows).

Почему на ПК, а не в GitHub: вход в аккаунт с сервера в другой стране для Telegram подозрителен,
а с домашнего компьютера это просто ещё одно устройство владельца с его обычного IP.

Что делает (и ничего больше):
  - читает новые сообщения только из чатов в папке Telegram «Заказы» (папку собираешь сам);
  - ничего не пишет, ни во что не вступает, ничего не ищет и не отмечает прочитанным;
  - подходящие заявки отбирает теми же фильтрами, что и поиск по каналам (leads/finder.py),
    и присылает в бот заявок.

Запуск: python chats.py          — проверка (по расписанию)
        python chats.py --login  — первый вход в аккаунт (номер и код из Telegram)
Настройки в .env рядом: API_ID, API_HASH (my.telegram.org), LEADS_BOT_TOKEN (бот заявок).
"""
import asyncio
import importlib.util
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
LIB = HERE / "lib"
STATE_FILE = HERE / "state.json"
LOG_FILE = HERE / "log.txt"
FOLDER = "Заказы"
RAW = "https://raw.githubusercontent.com/hazzi228/shorts-autopilot/main/leads/"
MSK = timezone(timedelta(hours=3))
PER_CHAT = 40          # не больше сообщений из одного чата за проверку
PAUSE = 3              # секунд между чатами: обычный темп человека, а не робота
FIRST_RUN = timedelta(hours=12)


def log(msg):
    line = f"{datetime.now(MSK):%Y-%m-%d %H:%M} {re.sub(r'bot[0-9]+:[\w-]+', 'bot***', str(msg))}"
    print(line, flush=True)
    old = LOG_FILE.read_text(encoding="utf-8").splitlines()[-500:] if LOG_FILE.exists() else []
    LOG_FILE.write_text("\n".join(old + [line]) + "\n", encoding="utf-8")


def env():
    out = {}
    for line in (HERE / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def load_finder():
    """Свежие фильтры и тексты откликов из GitHub, чтобы ПК не отставал от поиска по каналам."""
    LIB.mkdir(exist_ok=True)
    for name in ("finder.py", "sources.json"):
        try:
            r = requests.get(RAW + name, timeout=20)
            r.raise_for_status()
            (LIB / name).write_bytes(r.content)
        except requests.RequestException as e:
            if not (LIB / name).exists():
                raise SystemExit(f"Нет интернета или GitHub недоступен: {e}")
    spec = importlib.util.spec_from_file_location("finder", LIB / "finder.py")
    finder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finder)
    finder.LOG_FILE = LOG_FILE  # пропуски фейков пишем в свой журнал на ПК
    return finder


def client(cfg):
    from telethon import TelegramClient
    return TelegramClient(str(HERE / "hazzer"), int(cfg["API_ID"]), cfg["API_HASH"],
                          device_model="Hazzer PC", system_version="Windows 10", app_version="1.0",
                          flood_sleep_threshold=120)


def title_text(t):
    return getattr(t, "text", t) or ""


async def folder_peers(tg):
    from telethon.tl.functions.messages import GetDialogFiltersRequest
    res = await tg(GetDialogFiltersRequest())
    filters = getattr(res, "filters", res)
    for f in filters:
        if title_text(getattr(f, "title", "")).strip().lower() == FOLDER.lower():
            return list(getattr(f, "include_peers", [])) + list(getattr(f, "pinned_peers", []))
    return None


def fake_sender(finder, user):
    """Почему автор сообщения не подходит. В чате автор известен точно, проверяем его самого."""
    if user is None:
        return "автор скрыт"
    if getattr(user, "bot", False):
        return "автор — бот"
    if getattr(user, "scam", False) or getattr(user, "fake", False):
        return "Telegram пометил автора как мошенника"
    if getattr(user, "deleted", False):
        return "аккаунт удалён"
    name = " ".join(x for x in (user.first_name, user.last_name) if x)
    nick = (user.username or "").lower()
    if nick and finder.LATIN_FULL_NAME.match(name):
        handle = re.sub(r"[^a-z]", "", nick)
        parts = [p.lower() for p in name.split()]
        if not any(p[i:i + 3] in handle for p in parts for i in range(len(p) - 2)):
            return f"имя «{name}» не связано с ником @{nick}: похоже на фейк"
    return None


async def run(cfg, finder):
    from telethon.tl.types import Channel, Chat, User
    hour = datetime.now(MSK).hour
    if not 8 <= hour <= 23 and "--now" not in sys.argv:
        return
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    last = state.setdefault("last", {})
    prints = dict.fromkeys(state.get("prints", []))
    token = re.sub(r'[\s"]', "", cfg["LEADS_BOT_TOKEN"])
    owners = [str(i) for i in finder.SOURCES.get("owner_ids", [])]
    now = datetime.now(timezone.utc)

    tg = client(cfg)
    await tg.connect()  # без start(): по расписанию нельзя спрашивать номер, окна никто не видит
    try:
        if not await tg.is_user_authorized():
            raise SystemExit("Нет входа в аккаунт: запусти «Вход в Telegram.bat»")
        me = await tg.get_me()
        peers = await folder_peers(tg)
        if peers is None:
            log(f"нет папки «{FOLDER}» в Telegram: создай её и добавь туда чаты с заказами")
            return
        found, seen_total, skipped = [], 0, []
        for peer in peers:
            try:
                chat = await tg.get_entity(peer)
            except Exception as e:
                log(f"чат из папки не открылся: {type(e).__name__}")
                continue
            if isinstance(chat, User) or (isinstance(chat, Channel) and chat.broadcast and not chat.megagroup):
                continue  # личные переписки и каналы не читаем: каналы и так смотрит поиск в GitHub
            key = str(chat.id)
            kwargs = {"limit": PER_CHAT}
            if key in last:
                kwargs["min_id"] = last[key]
            newest = last.get(key, 0)
            async for msg in tg.iter_messages(chat, **kwargs):
                newest = max(newest, msg.id)
                if key not in last and now - msg.date > FIRST_RUN:
                    break
                text = finder.clean(msg.message or "")
                if not text or msg.sender_id == me.id:
                    continue
                seen_total += 1
                kind = finder.classify(text)
                if not kind:
                    continue
                fp = finder.fingerprint(text)
                if fp in prints:
                    continue
                prints[fp] = None
                sender = await msg.get_sender()
                link = (f"https://t.me/{chat.username}/{msg.id}" if getattr(chat, "username", None)
                        else f"https://t.me/c/{chat.id}/{msg.id}")
                why = fake_sender(finder, sender if isinstance(sender, User) else None)
                if why:
                    skipped.append(f"{link}: {why}")
                    continue
                contacts = [f"@{sender.username}"] if sender.username else [f"tg://user?id={sender.id}"]
                contacts += [c for c in finder.contacts(text, []) if c not in contacts]
                found.append({
                    "id": f"chat:{chat.id}/{msg.id}", "source": getattr(chat, "title", "чат"),
                    "title": text[:90], "text": text, "url": link, "contacts": contacts[:3],
                    "date": msg.date, "kind": kind,
                    "niche": finder.niche(text),
                })
            last[key] = newest
            await asyncio.sleep(PAUSE)
    finally:
        await tg.disconnect()

    for s in skipped:
        log(f"пропущена заявка {s}")
    found.sort(key=lambda l: bool(l["niche"]))
    for lead in found[-finder.MAX_PER_RUN:]:
        reply = finder.reply_message(lead)
        for chat_id in owners:
            try:
                finder.send(token, chat_id, finder.card(lead))
                finder.send(token, chat_id, reply, finder.ANSWERED_BUTTON)
            except requests.RequestException as e:
                log(f"не отправилось: {e}")
        time.sleep(1.2)
    log(f"чатов в папке {len(peers)}, сообщений {seen_total}, заявок {len(found)}, пропущено фейков {len(skipped)}")
    state["prints"] = list(prints)[-3000:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


async def login(cfg):
    async with client(cfg) as tg:
        await tg.start()  # спросит номер телефона и код из Telegram прямо в этом окне
        me = await tg.get_me()
        print(f"\nВход выполнен: {me.first_name} (@{me.username}). Это окно можно закрыть.")
        peers = await folder_peers(tg)
        print(f"Папка «{FOLDER}»: " + (f"чатов в ней {len(peers)}" if peers is not None
                                     else "не найдена, создай её в Telegram и добавь чаты с заказами"))


def main():
    cfg = env()
    for k in ("API_ID", "API_HASH", "LEADS_BOT_TOKEN"):
        if not cfg.get(k):
            raise SystemExit(f"В файле .env не заполнено {k}")
    if "--login" in sys.argv:
        asyncio.run(login(cfg))
        return
    try:
        asyncio.run(run(cfg, load_finder()))
    except SystemExit as e:
        log(e)
    except Exception as e:  # журнал вместо молчаливого падения в Планировщике
        log(f"ошибка: {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    main()
