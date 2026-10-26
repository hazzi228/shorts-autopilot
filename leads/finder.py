"""Поиск заказчиков на Telegram-ботов и сайты.

Раз в час читает открытые ленты заказов (публичные Telegram-каналы через t.me/s,
RSS бирж), оставляет только свежие заявки, где человеку нужен бот или сайт,
и присылает их в Telegram с готовым черновиком отклика. Писать заказчику
нужно самому: инструмент ничего не отправляет посторонним людям.

Запуск: python leads/finder.py [--dry-run]
Секреты: LEADS_BOT_TOKEN (токен бота от @BotFather), LEADS_CHAT_ID (необязательно, можно несколько через запятую).
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
    r"курсов(ая|ую|ой|ик)|дипломн|лабораторн|резюме|#ищу_работу|мои услуги|в (мою |нашу )?команду|обучени[ея]|курс(ы)? по|заработок без|"
    r"пассивный доход|полный рабочий день|в офис|оклад|по тк\b|казино|ставки|накрутк|арбитраж|18\+|"
    r"эскорт|взлом|forex|igaming|gambling|отзыв(ы|ов)? (на|о|для)|оставить отзыв|"
    r"уволиться|из найма|нужно для старта|новички зарабатыва|зарабатывать от|средняя зарплата")
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


# Ниши, где Hazzer уже силён и где чаще заказывают повторно: такие заявки помечаются и идут первыми.
NICHE_VPN = re.compile(r"\bvpn|\bвпн|подписк|цифров\w* товар|ключ(и|ей) доступа|продаж\w* (аккаунт|ключ)")
NICHE_SCHOOL = re.compile(r"онлайн[- ]?школ|\bкурс(?!ов(ая|ую|ой|ые|ик))|марафон|вебинар|инфобиз|эксперт|коуч|наставни|"
                          r"закрыт\w* (канал|чат|клуб)|приватн\w* (канал|чат)|платн\w* (канал|доступ|чат)")


def niche(text):
    t = text.lower()
    if NICHE_VPN.search(t):
        return "vpn"
    if NICHE_SCHOOL.search(t):
        return "school"
    return None


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


# Разделы Kwork: 37 создание сайтов, 38 доработка сайтов, 79 вёрстка, 41 скрипты и боты.
KWORK_SITE = {"37", "38", "79"}
KWORK_BOTS = "41"
# Настройка серверов и прочее администрирование: это не разработка сайта
KWORK_ADMIN = re.compile(r"varnish|nginx|apache|\bvps\b|\bdns\b|днс|ssl|сертификат|почт[ауы] на домен|перенос на (?:хостинг|сервер)")
MSK = timezone(timedelta(hours=3))


def from_kwork(categories, pages=2):
    """Открытые заказы Kwork из тех же запросов, что делает сама страница «Биржа проектов»."""
    for cat in categories:
        for page in range(1, pages + 1):
            r = requests.post("https://kwork.ru/projects", headers={**UA, "X-Requested-With": "XMLHttpRequest"},
                              data={"c": cat, "page": page}, timeout=25)
            r.raise_for_status()
            pag = (r.json().get("data") or {}).get("pagination") or {}
            for w in pag.get("data") or []:
                title, desc = clean(w.get("name")), clean(w.get("description"))
                price = w.get("priceLimit")
                price = f" (Бюджет: {float(price):,.0f} ₽)".replace(",", " ") if price else ""
                yield {
                    "id": f"kwork:{w['id']}",
                    "source": "Kwork",
                    "title": title[:120],
                    "text": f"{title}{price}. {desc}",
                    "url": f"https://kwork.ru/projects/{w['id']}",
                    "contacts": [],
                    "date": datetime.strptime(w["date_create"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MSK),
                    "category": str(w.get("category_id")),
                }
            if page >= (pag.get("last_page") or 1):
                break
            time.sleep(1)


def classify_kwork(lead):
    """Kwork уже разложил заказы по разделам, поэтому слова «нужен/сделать» не обязательны."""
    t = lead["text"].lower()
    if SKIP_WORDS.search(t):
        return None
    if lead["category"] in KWORK_SITE and not KWORK_ADMIN.search(t):
        return "site"
    if lead["category"] == KWORK_BOTS and re.search(r"\bбот|telegram|телеграм|\bтг\b|mini ?app|мини[- ]?прилож", t):
        return "bot"
    return None


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
    if kind == "bot" and lead.get("niche") == "vpn":
        offer = ("Как раз специализируюсь на этом: сделал два бота для продажи VPN-подписок с автовыдачей доступа, "
                 "оплатой через СБП, карту и крипту, промокодами, рефералами и админкой прямо в Telegram. "
                 "Заказчики оставили 5 звёзд.")
    elif kind == "bot" and lead.get("niche") == "school":
        offer = ("Делаю ботов для экспертов и онлайн-школ: оплата (СБП, карта, крипта), автоматическая выдача "
                 "доступа в закрытый канал и его продление, рассылки по ученикам, статистика продаж в админке.")
    elif kind == "bot":
        offer = ("Делаю Telegram-ботов под ключ: оплата (СБП, карта, крипта), личный кабинет клиента, "
                 "админ-панель прямо в боте, рассылки и статистика. Недавно сдал два бота для продажи VPN, "
                 "заказчики оставили 5 звёзд.")
    else:
        offer = ("Делаю сайты и лендинги под ключ: адаптив под телефон, формы заявок, оплата, "
                 "связка с Telegram, чтобы заявки сразу приходили вам в чат.")
    # Варианты фраз, чтобы одинаковые сообщения не выглядели как рассылка.
    pick = lambda options: options[int(hashlib.md5(lead["id"].encode()).hexdigest(), 16) % len(options)]
    hello = pick(["Здравствуйте! Увидел ваш заказ.", "Добрый день! Прочитал ваш заказ, могу взяться.",
                  "Здравствуйте! Готов сделать то, что вы описали."])
    if lead["id"].startswith(("rss:", "kwork:")):
        end = "Примеры работ и отзывы: @PortfolioHazzer_bot. Назову цену и срок, как только уточню пару деталей."
    else:
        end = pick(["Примеры работ и отзывы: @PortfolioHazzer_bot. Напишите пару деталей, и назову цену и срок.",
                    "Работы и отзывы можно посмотреть в @PortfolioHazzer_bot. Расскажите подробнее, отвечу сегодня.",
                    "Мои работы и отзывы: @PortfolioHazzer_bot. Если интересно, опишите задачу, назову цену и срок."])
    return f"{hello} {offer} {end}"


def collect():
    leads, errors = [], []
    jobs = [("tg", ch) for ch in SOURCES.get("telegram", [])]
    jobs += [("rss", r) for r in SOURCES.get("rss", [])]
    if SOURCES.get("kwork"):
        jobs.append(("kwork", {"name": "Kwork", "categories": SOURCES["kwork"]}))
    for kind, src in jobs:
        name = src if kind == "tg" else src["name"]
        try:
            if kind == "tg":
                items = list(from_telegram(src))
            elif kind == "rss":
                items = list(from_rss(src["name"], src["url"]))
            else:
                items = list(from_kwork(src["categories"]))
            leads += items
            print(f"  {name}: {len(items)} постов")
        except Exception as e:  # одна упавшая лента не должна ломать остальные
            errors.append(f"{name}: {type(e).__name__} {str(e)[:80]}")
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


def find_chat_ids(token, state):
    """Кому слать заявки. Новых получателей ищем среди тех, кто написал боту /start."""
    if os.environ.get("LEADS_CHAT_ID"):
        return [c.strip() for c in os.environ["LEADS_CHAT_ID"].split(",") if c.strip()], []
    ids = state.setdefault("chat_ids", [state.pop("chat_id")] if state.get("chat_id") else [])
    owners = {n.lstrip("@").lower() for n in SOURCES.get("owners", [])}
    if ids and not owners:
        return ids, []
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
    if not r.get("ok"):
        desc = r.get("description", "")
        if "webhook" in desc.lower():
            sys.exit("В LEADS_BOT_TOKEN токен бота-портфолио. Нужен отдельный новый бот от @BotFather (см. leads/README.md)")
        sys.exit(f"Telegram не принял LEADS_BOT_TOKEN: {desc}. Проверь, что токен скопирован целиком")
    new = []
    for upd in reversed(r.get("result", [])):
        chat = (upd.get("message") or {}).get("chat", {})
        if chat.get("type") != "private" or str(chat["id"]) in ids:
            continue
        # Без списка owners бот личный, и первый написавший ему и есть хозяин.
        if owners and (chat.get("username") or "").lower() not in owners:
            continue
        ids.append(str(chat["id"]))
        new.append(str(chat["id"]))
        if not owners:
            break
    return ids, new


def tags(lead):
    # Хэштеги кликабельны в Telegram: нажал #кворк, и видны только заявки с Kwork.
    site = {"kwork": "#кворк", "rss": "#флру"}.get(lead["id"].split(":")[0], "#тг")
    out = [site, "#бот" if lead["kind"] == "bot" else "#сайт"]
    if lead.get("niche"):
        out += ["#ниша", "#vpn" if lead["niche"] == "vpn" else "#школа"]
    return " ".join(out)


def card(lead):
    kind_name = "🤖 Бот" if lead["kind"] == "bot" else "🌐 Сайт"
    text = lead["text"]
    if len(text) > 700:
        text = text[:700].rsplit(" ", 1)[0] + "…"
    if lead.get("niche"):
        kind_name = "🔥 Твоя ниша · " + ("VPN и подписки" if lead["niche"] == "vpn" else "онлайн-школы") + "\n" + kind_name
    lines = [f"<b>{kind_name}</b> · {html.escape(lead['source'])} · "
             f"{lead['date'].astimezone(timezone(timedelta(hours=3))):%d.%m %H:%M} МСК",
             tags(lead), "", html.escape(text), ""]
    if lead["url"]:
        lines.append(f"🔗 <a href=\"{html.escape(lead['url'])}\">Открыть заявку</a>")
    if lead["id"].startswith(("rss:", "kwork:")):
        lines.append("✍️ Отклик оставляется прямо на сайте биржи, Telegram для этого не нужен")
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
        lead["kind"] = classify_kwork(lead) if lead["id"].startswith("kwork:") else classify(lead["text"])
        lead["niche"] = niche(lead["text"]) if lead["kind"] == "bot" else None
        fp = fingerprint(lead["text"])
        if not lead["kind"] or fp in prints:
            continue
        prints[fp] = None
        fresh.append(lead)

    log(f"просмотрено {len(raw)}, подходящих новых {len(fresh)}"
        + (f"; не открылись: {'; '.join(errors)}" if errors else ""))
    # Заявки из своих ниш точно попадут в выдачу и придут последними, то есть окажутся внизу чата.
    fresh = sorted(fresh, key=lambda l: bool(l["niche"]))
    # Не влезшие в этот раз не помечаем просмотренными: они придут при следующей проверке.
    for lead in fresh[:-MAX_PER_RUN]:
        seen.pop(lead["id"], None)
        prints.pop(fingerprint(lead["text"]), None)
    fresh = fresh[-MAX_PER_RUN:]

    if args.dry_run:
        for lead in fresh:
            print("\n" + "=" * 60 + "\n" + html.unescape(re.sub(r"<[^>]+>", "", card(lead))))
        return

    # При копировании легко захватить пробел, перенос строки или кавычки.
    token = re.sub(r'[\s"]', "", os.environ.get("LEADS_BOT_TOKEN", ""))
    if not token:
        sys.exit("Нет секрета LEADS_BOT_TOKEN (см. leads/README.md)")
    chat_ids, new_ids = find_chat_ids(token, state)
    if not chat_ids:
        sys.exit("Бот не знает, куда писать: открой в Telegram бота для заявок (того, чей токен в LEADS_BOT_TOKEN), "
                 "нажми Start или напиши ему любое сообщение, потом запусти ещё раз")
    for chat_id in new_ids:
        send(token, chat_id, "✅ Бот подключён. Сюда будут приходить заявки на ботов и сайты, "
                             "проверка каждый час с 8:00 до 23:00 по Москве."
                             + ("" if fresh else " Сейчас новых подходящих заявок нет."))

    for lead in fresh:
        for chat_id in chat_ids:
            try:
                send(token, chat_id, card(lead))
            except requests.RequestException as e:
                log(f"не отправилось в чат {chat_id}: {e}")
        time.sleep(1.2)

    state["ids"] = list(seen)[-5000:]
    state["prints"] = list(prints)[-3000:]
    SEEN_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
