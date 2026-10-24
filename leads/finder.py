"""Поиск заказчиков на Telegram-ботов и сайты.

Раз в час читает открытые ленты заказов (публичные Telegram-каналы через t.me/s,
RSS бирж), оставляет только свежие заявки, где человеку нужен бот или сайт,
и присылает их в Telegram с готовым черновиком отклика. Писать заказчику
нужно самому: инструмент ничего не отправляет посторонним людям.

Запуск: python leads/finder.py [--dry-run]
Секреты: LEADS_BOT_TOKEN (токен бота от @BotFather), LEADS_CHAT_ID (необязательно).
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
SOURCES = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
SEEN_FILE = HERE / "seen.json"
LOG_FILE = HERE / "log.txt"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "ru-RU,ru;q=0.9"}
MAX_AGE = timedelta(days=SOURCES.get("max_age_days", 3))
MAX_PER_RUN = SOURCES.get("max_per_run", 15)

# Заявка должна быть именно про создание бота или сайта: глагол «нужен / сделать / разработать»
# и рядом, через пару слов, сам бот или сайт.
NEED = r"(нуж[еан]|нужн|требуе|ищ[уе]|ищет|созда|сдела|разраб|напис|напиш|собра|запуст|доработ|передел|" \
       r"сверст|верст|кто (может|сделает|возьм))"
THING = r"(?P<bot>(телеграм|telegram|тг|tg)[- ]?бот\w*|чат[- ]?бот\w*|бот(а|ов|ы|ом)?\b|mini ?app|" \
        r"мини[- ]?приложени\w*)|(?P<site>сайт\w*|лендинг\w*|landing|интернет[- ]магазин\w*|" \
        r"одностранич\w*|веб[- ]?приложени\w*|web[- ]?app)"
REQUEST = re.compile(NEED + r"\w*[\s,:-]+(?:[\w-]+[\s,:]+){0,3}?(?:" + THING + ")")
# Объявления исполнителей, резюме, вакансии в штат и чужие профессии нам не нужны.
SKIP_WORDS = re.compile(
    r"ищу (работу|заказ|клиент|подработ)|возьму (заказ|в работу)|предлагаю (услуг|свои)|(^|\s)сделаю\b|"
    r"резюме|#ищу_работу|мои услуги|в (мою |нашу )?команду|обучени[ея]|курс(ы)? по|заработок без|"
    r"пассивный доход|полный рабочий день|в офис|оклад|по тк\b|казино|ставки|накрутк|арбитраж|18\+|"
    r"эскорт|взлом|forex|igaming|gambling|отзыв(ы|ов)? (на|о|для)|оставить отзыв")
# Если в начале заявки другая профессия (дизайн, видео, SEO...), это не наш заказ.
OTHER_JOB = re.compile(
    r"дизайн|моушн|motion|ролик|видео|монтаж|seo|продвижени|копирайт|текст(ы|ов)? для|маркетолог|"
    r"marketing|smm|таргет|контент|excel|эксель|1с\b|перевод|фото|логотип|аватар|баннер")


def log(msg):
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} {msg}"
    print(line, flush=True)
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines() if LOG_FILE.exists() else []
    LOG_FILE.write_text("\n".join((lines + [line])[-300:]) + "\n", encoding="utf-8")


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def classify(text):
    """Возвращает 'bot', 'site' или None, если это не заявка на бота или сайт."""
    t = text.lower()
    if SKIP_WORDS.search(t) or OTHER_JOB.search(t[:120]):
        return None
    m = REQUEST.search(t)
    if not m:
        return None
    return "bot" if m.group("bot") else "site"


def get(url):
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.text


def from_telegram(channel):
    """Последние посты публичного канала из веб-версии t.me/s/<канал>."""
    soup = BeautifulSoup(get(f"https://t.me/s/{channel}"), "html.parser")
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        body = msg.select_one(".tgme_widget_message_text")
        stamp = msg.select_one("time[datetime]")
        if not body or not stamp:
            continue
        text = clean(body.get_text(" "))
        links = [a["href"] for a in body.select("a[href]")]
        yield {
            "id": "tg:" + msg["data-post"],
            "source": f"@{channel}",
            "title": text[:90],
            "text": text,
            "url": f"https://t.me/{msg['data-post']}",
            "contacts": contacts(text, links),
            "date": datetime.fromisoformat(stamp["datetime"]),
        }


def from_rss(name, url):
    root = ElementTree.fromstring(get(url).encode("utf-8"))
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        desc = clean(BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" "))
        link = (item.findtext("link") or "").strip()
        try:
            date = parsedate_to_datetime(item.findtext("pubDate"))
        except (TypeError, ValueError):
            date = datetime.now(timezone.utc)
        yield {
            "id": "rss:" + (link or hashlib.md5(title.encode()).hexdigest()),
            "source": name,
            "title": title[:120],
            "text": f"{title}. {desc}",
            "url": link,
            "contacts": [],
            "date": date,
        }


def contacts(text, links):
    """Контакты, которые автор сам указал в объявлении."""
    found = re.findall(r"(?<![\w.])@[A-Za-z][A-Za-z0-9_]{4,31}\b", text)
    found += [l for l in links if l.startswith(("https://t.me/", "http://t.me/", "tg://"))]
    out = []
    for c in found:
        if c not in out:
            out.append(c)
    return out[:3]


def draft(kind, lead):
    """Короткий вежливый отклик, который можно скопировать и поправить."""
    if kind == "bot":
        offer = ("Делаю Telegram-ботов под ключ: оплата (СБП, карта, крипта), личный кабинет клиента, "
                 "админ-панель прямо в боте, рассылки и статистика. Недавно сдал два бота для продажи VPN, "
                 "заказчики оставили 5 звёзд.")
    else:
        offer = ("Делаю сайты и лендинги под ключ: адаптив под телефон, формы заявок, оплата, "
                 "связка с Telegram, чтобы заявки сразу приходили вам в чат.")
    return (f"Здравствуйте! Увидел ваш заказ. {offer} Работы и отзывы: @PortfolioHazzer_bot. "
            f"Расскажите чуть подробнее о задаче и сроках, назову цену и срок в тот же день.")


def collect():
    leads, errors = [], []
    jobs = [("tg", ch) for ch in SOURCES.get("telegram", [])]
    jobs += [("rss", r) for r in SOURCES.get("rss", [])]
    for kind, src in jobs:
        try:
            items = list(from_telegram(src) if kind == "tg" else from_rss(src["name"], src["url"]))
            leads += items
            print(f"  {src if kind == 'tg' else src['name']}: {len(items)} постов")
        except Exception as e:  # одна упавшая лента не должна ломать остальные
            errors.append(f"{src if kind == 'tg' else src['name']}: {type(e).__name__} {str(e)[:80]}")
        time.sleep(1)
    return leads, errors


def fingerprint(text):
    """Одну и ту же заявку часто публикуют в нескольких каналах."""
    words = re.findall(r"[a-zа-яё0-9]+", text.lower())
    return hashlib.md5(" ".join(words[:40]).encode()).hexdigest()


def send(token, chat_id, text):
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20, json={
        "chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
    if r.status_code == 429:
        time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1)
        return send(token, chat_id, text)
    r.raise_for_status()


def find_chat_id(token, state):
    if os.environ.get("LEADS_CHAT_ID"):
        return os.environ["LEADS_CHAT_ID"].strip()
    if state.get("chat_id"):
        return state["chat_id"]
    # Берём того, кто написал боту /start. Бот новый и личный, так что это хозяин.
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
    for upd in reversed(r.get("result", [])):
        chat = (upd.get("message") or {}).get("chat", {})
        if chat.get("type") == "private":
            state["chat_id"] = str(chat["id"])
            return state["chat_id"]
    return None


def card(lead):
    kind_name = "🤖 Бот" if lead["kind"] == "bot" else "🌐 Сайт"
    text = lead["text"]
    if len(text) > 700:
        text = text[:700].rsplit(" ", 1)[0] + "…"
    lines = [f"<b>{kind_name}</b> · {html.escape(lead['source'])} · "
             f"{lead['date'].astimezone(timezone(timedelta(hours=3))):%d.%m %H:%M} МСК",
             "", html.escape(text), ""]
    if lead["url"]:
        lines.append(f"🔗 <a href=\"{html.escape(lead['url'])}\">Открыть заявку</a>")
    if lead["contacts"]:
        lines.append("✉️ Контакт: " + ", ".join(html.escape(c) for c in lead["contacts"]))
    lines += ["", "<b>Черновик отклика</b> (нажми, чтобы скопировать):",
              f"<code>{html.escape(draft(lead['kind'], lead))}</code>"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="только показать, ничего не отправлять")
    ap.add_argument("--days", type=float, help="за сколько дней смотреть заявки (для проверки)")
    args = ap.parse_args()

    state = json.loads(SEEN_FILE.read_text(encoding="utf-8")) if SEEN_FILE.exists() else {}
    seen = dict.fromkeys(state.get("ids", []))  # dict, чтобы помнить порядок и срезать старые
    prints = dict.fromkeys(state.get("prints", []))
    first_run = not state.get("ids")

    # В первый раз берём только сутки, чтобы не завалить старыми заявками.
    window = timedelta(days=args.days) if args.days else timedelta(days=1) if first_run else MAX_AGE
    raw, errors = collect()
    now = datetime.now(timezone.utc)
    fresh = []
    for lead in sorted(raw, key=lambda l: l["date"]):
        if lead["id"] in seen:
            continue
        seen[lead["id"]] = None
        if now - lead["date"] > window:
            continue
        lead["kind"] = classify(lead["text"])
        fp = fingerprint(lead["text"])
        if not lead["kind"] or fp in prints:
            continue
        prints[fp] = None
        fresh.append(lead)

    log(f"просмотрено {len(raw)}, подходящих новых {len(fresh)}"
        + (f"; не открылись: {'; '.join(errors)}" if errors else ""))
    fresh = fresh[-MAX_PER_RUN:]

    if args.dry_run:
        for lead in fresh:
            print("\n" + "=" * 60 + "\n" + html.unescape(re.sub(r"<[^>]+>", "", card(lead))))
        return

    token = os.environ.get("LEADS_BOT_TOKEN", "").strip()
    if not token:
        sys.exit("Нет секрета LEADS_BOT_TOKEN (см. leads/README.md)")
    chat_id = find_chat_id(token, state)
    if not chat_id:
        sys.exit("Бот не знает, куда писать: открой своего бота в Telegram и нажми Start, потом запусти ещё раз")

    for lead in fresh:
        send(token, chat_id, card(lead))
        time.sleep(1.2)

    state["ids"] = list(seen)[-5000:]
    state["prints"] = list(prints)[-3000:]
    SEEN_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
