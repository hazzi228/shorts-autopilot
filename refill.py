"""Пополняет scenarios.json новыми сценариями, когда старые заканчиваются.

Пишет сценарии бесплатный Gemini (секрет GEMINI_API_KEY с бесплатным ключом Google AI Studio).
Запуск: python refill.py            — пополнить, если осталось мало
        python refill.py --force    — пополнить в любом случае
        python refill.py --force --dry — только показать, что напишет ИИ, ничего не сохраняя
"""
import os, sys, json, re, time

S = os.path.dirname(os.path.abspath(__file__))
SCEN = os.path.join(S, "scenarios.json")
STATE = os.path.join(S, "state.json")
EMOJI_FONT = os.path.join(S, "fonts", "NotoColorEmoji.ttf")

MIN_LEFT = 6          # пополняем, когда осталось меньше двух дней роликов
BATCH = 2             # сценариев за один запрос к ИИ (у бесплатных моделей короткий лимит ответа)
ROUNDS = 6            # запросов за одно пополнение: 6 × 2 = 12 новых сценариев (4 дня)
# GitHub Models проверен 24.10.2026: на этом аккаунте отвечает пустым "OK", а старый адрес Azure больше не существует.
# Поэтому токен GitHub никуда не отправляем, сценарии пишет только Gemini.
MODELS = []
# (Pollinations без ключа проверен 24.10.2026: выдумывает факты, поэтому не используется)
# нужен секрет GEMINI_API_KEY (бесплатный ключ Google AI Studio)
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI = [(GEMINI_API, "gemini-3.8-flash"), (GEMINI_API, "gemini-flash-latest")]

ACCENTS = [(124, 92, 255), (0, 200, 255), (255, 120, 60), (40, 210, 140), (255, 70, 120), (255, 190, 40)]
HANDLE = "@PortfolioHazzer_reserv_bot"
# реклама — одна короткая фраза в самом конце: в середине ролика она обрывала удержание
# (по статистике канала зрители массово листали ровно там, где начиналась реклама)
AD_END = [
    ("Нужен телеграм-бот или сайт? Сделаю под ключ, ссылка на экране.",
     "Нужен Telegram-бот или сайт? 👉 " + HANDLE),
    ("Бота, который продаёт за тебя, сделаю под ключ. Ссылка на экране.",
     "Бот, который продаёт за тебя 👉 " + HANDLE),
    ("Делаю телеграм-ботов и сайты под ключ. Ссылка на экране.",
     "Telegram-боты и сайты под ключ 👉 " + HANDLE),
]


def ad_end(index):
    say, show = AD_END[index % len(AD_END)]
    return dict(ad=True, hero=["cta"], say=say, show=show)


CTA_DESC = "🤖 Делаю Telegram-ботов и сайты под ключ по приятной цене.\nПортфолио и отзывы: " + HANDLE

PROMPT = """Ты сценарист коротких вертикальных роликов (YouTube Shorts) на русском языке.
Каждый ролик — интересный малоизвестный факт или история про технологии, интернет, гаджеты, бренды, игры или изобретения.
Используй только известные, проверяемые факты. Никаких выдумок: если не уверен в дате или цифре, не пиши её.

Придумай {n} НОВЫХ роликов. Эти темы уже были, не повторяй их:
{used}

Верни строго JSON вида {{"videos": [ ... ]}}, где каждый ролик:
{{
  "id": "латиница-через-дефис, 1-3 слова",
  "topic": "короткая тема",
  "yt_title": "заголовок до 70 символов с интригой, а не пересказом (не раскрывай ответ), в конце один эмодзи",
  "story": [3 сцены],
  "ending": [2 сцены],
  "desc": "2 строки описания для YouTube, вторая строка — вопрос зрителю и 👇",
  "tags": ["4-5 тегов без решётки, по-русски или латиницей"]
}}
Сцена: {{"say": "...", "show": "...", "hero": {{"type": "emoji", "emoji": "один эмодзи", "caption": "подпись до 30 символов"}}}}
или hero {{"type": "big", "text": "до 6 символов, например год 1992 или 0:19", "caption": "подпись до 30 символов"}}.
В каждой сцене ещё "img": 1-2 коротких поисковых запроса НА АНГЛИЙСКОМ для фото в Wikimedia Commons
(люди, компании, устройства, места из сцены: "Steve Jobs", "IBM Personal Computer 5150", "CERN Meyrin").
Картинка на экране сменяется каждые 1,5-2 секунды, поэтому в сцене длиннее одного предложения нужно 2 запроса.

Правила:
- "say" читает робот-диктор: в нём НЕТ цифр и латинских букв. Числа и годы пиши словами
  ("в тысяча девятьсот девяносто втором году"), английские названия — русскими буквами ("ютуб", "эппл", "эс эм эс").
- "show" — тот же текст для экрана, там цифры и латиница можно.
- Каждая сцена 1-2 коротких предложения, до 120 символов. Без воды, вводных слов и повторов.
- Первая сцена story — хук на 1-2 секунды, до 60 символов: парадокс, интрига или прямой вызов зрителю.
  Хорошо: "Этот звонок стоил компании миллиарды.", "Ты пользуешься этим каждый день и не знаешь, кто это придумал."
  Плохо (так нельзя): "Сегодня расскажу про...", "Амазон начинался в гараже." — без интриги зритель листает дальше.
- Хук открывает вопрос, а ответ на него звучит только в первой сцене ending: так досматривают до конца.
- Вторая и третья сцены story подогревают интерес новыми деталями, без воды и вводных слов.
- Ролик целиком 20-30 секунд: короткие ролики чаще досматривают и пересматривают.
- Последняя сцена ending — вопрос зрителю, hero emoji с caption "пиши в комментариях", а в "show" в конце 👇.

Пример одного ролика:
{example}
"""

EXAMPLE = {
    "id": "sms", "topic": "Первое SMS в истории", "yt_title": "Первое SMS в мире было всего из двух слов 📱",
    "story": [
        {"say": "Первое эс эм эс в истории состояло всего из двух слов.", "show": "Первое SMS в истории состояло всего из двух слов.",
         "hero": {"type": "emoji", "emoji": "📱", "caption": "первое SMS"}, "img": ["SMS text message mobile phone"]},
        {"say": "Третьего декабря тысяча девятьсот девяносто второго года инженер Нил Папворт отправил с компьютера на телефон сообщение: Мэрри Кристмас.",
         "show": "3 декабря 1992 года инженер Нил Папворт отправил с компьютера на телефон: «Merry Christmas».",
         "hero": {"type": "big", "text": "1992", "caption": "3 декабря"}, "img": ["Neil Papworth", "Orbitel 901"]},
        {"say": "Ответить получатель не смог. На телефонах тогда просто не было возможности писать сообщения.",
         "show": "Ответить получатель не смог. На телефонах тогда просто не было возможности писать сообщения.",
         "hero": {"type": "emoji", "emoji": "🤷", "caption": "ответить было нельзя"}, "img": ["Nokia 1011", "1990s mobile phone"]}],
    "ending": [
        {"say": "А через несколько лет люди отправляли уже миллиарды сообщений в день.", "show": "А через несколько лет люди отправляли уже миллиарды сообщений в день.",
         "hero": {"type": "big", "text": "SMS", "caption": "миллиарды в день"}, "img": ["Nokia 3310", "Texting on mobile phone"]},
        {"say": "Помнишь своё первое сообщение?", "show": "Помнишь своё первое сообщение? 👇",
         "hero": {"type": "emoji", "emoji": "💬", "caption": "пиши в комментариях"}}],
    "desc": "Первое SMS отправили 3 декабря 1992 года. Всего два слова, и ответить на него было невозможно 😅\nПомнишь своё первое сообщение? Пиши в комментариях 👇",
    "tags": ["sms", "история", "технологии", "телефон"],
}


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_cmap = None
def emoji_ok(e):
    global _cmap
    if _cmap is None:
        from fontTools.ttLib import TTFont
        _cmap = set(TTFont(EMOJI_FONT)["cmap"].getBestCmap())
    cps = [ord(c) for c in e if ord(c) not in (0xFE0F, 0x200D)]
    return 0 < len(cps) <= 3 and all(c in _cmap for c in cps)


class Bad(Exception):
    pass


def clean_say(t):
    t = " ".join(str(t).split())
    if not t or len(t) > 220:
        raise Bad("say длина")
    if re.search(r"[0-9A-Za-z]", t):
        raise Bad("в say цифры или латиница: " + t)
    return t


LINK = re.compile(r"https?://|www\.|t\.me|@\w|\b[\w-]+\.(ru|com|net|org|io|me|su|рф|xyz|top|link)\b", re.I)


def no_links(t):
    """ИИ не должен вставлять в ролик свои ссылки и чужие @ники: в ролике рекламируется только наш бот."""
    if LINK.search(t):
        raise Bad("ссылка в тексте: " + t[:80])
    return t


def scene(raw):
    h = raw.get("hero") or {}
    say = clean_say(raw.get("say", ""))
    show = no_links(" ".join(str(raw.get("show") or say).split())[:220])
    cap = no_links(" ".join(str(h.get("caption", "")).split())[:34])
    if h.get("type") == "big":
        txt = str(h.get("text", "")).strip()
        if not txt or len(txt) > 7:
            raise Bad("big text")
        hero = ["big", txt, cap]
    else:
        e = str(h.get("emoji", "")).strip()
        if not emoji_ok(e):
            e = "💡"
        hero = ["emoji", e, cap]
    img = [" ".join(str(q).split())[:60] for q in (raw.get("img") or []) if str(q).strip()][:2]
    out = dict(say=say, show=show, hero=hero)
    if img:
        out["img"] = img
    return out


def build_video(raw, index, taken):
    vid = re.sub(r"[^a-z0-9-]", "", str(raw.get("id", "")).lower().replace(" ", "-")).strip("-")[:40] or "fact"
    base, n = vid, 2
    while vid in taken:
        vid = "%s-%d" % (base, n)
        n += 1
    story = [scene(x) for x in raw.get("story", [])][:3]
    ending = [scene(x) for x in raw.get("ending", [])][-2:]
    if len(story) != 3 or not ending:
        raise Bad("число сцен")
    tags = [no_links(str(t).replace("#", "").strip()) for t in raw.get("tags", []) if str(t).strip()][:5] + ["телеграмбот"]
    hashtags = " ".join("#" + t.replace(" ", "") for t in tags + ["shorts"])
    title = " ".join(str(raw.get("yt_title", "")).split())[:95]
    desc = str(raw.get("desc", "")).strip()
    if not title or not desc:
        raise Bad("нет заголовка или описания")
    no_links(title)
    no_links(desc)
    return dict(id=vid, title=str(raw.get("topic") or title)[:80], accent=list(ACCENTS[index % len(ACCENTS)]),
                yt_title=title, description=desc + "\n\n" + CTA_DESC + "\n\n" + hashtags,
                tags=tags + ["shorts", "интересные факты"], scenes=story + ending + [ad_end(index)])


_dead = set()  # модели, которые уже не ответили в этом запуске


def ask_one(api, model, token, prompt):
    import requests
    body = {"model": model, "temperature": 0.9, "max_tokens": 8000,
            "messages": [{"role": "user", "content": prompt}]}
    r = requests.post(api, timeout=150, json=body, headers={
        "Authorization": "Bearer " + token, "User-Agent": "shorts-autopilot"})
    if r.status_code != 200:
        raise RuntimeError("%s %s" % (r.status_code, r.text[:300]))
    if "json" not in r.headers.get("Content-Type", ""):
        raise RuntimeError("ответ не JSON (%s, %r)" % (r.headers.get("Content-Type"), r.text[:100]))
    try:
        text = r.json()["choices"][0]["message"].get("content") or ""
    except Exception:
        raise RuntimeError("непонятный ответ: %r" % r.text[:300])
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError("в ответе нет сценариев: %r" % text[-300:])
    try:
        data = json.loads(m.group(0))
    except ValueError:
        from json_repair import repair_json  # модели иногда ошибаются в запятых
        data = json.loads(repair_json(m.group(0)))
    return data["videos"]


def ask_ai(prompt):
    last = None
    plan = (GEMINI if os.environ.get("GEMINI_API_KEY") else []) + MODELS
    for api, model in plan:
        if (api, model) in _dead:
            continue
        token = os.environ.get("GEMINI_API_KEY")
        for wait in (0, 20, 60):
            time.sleep(wait)
            try:
                return ask_one(api, model, token, prompt), model
            except Exception as e:
                print("Модель %s не ответила: %s" % (model, str(e)[:200]))
                last = e
                # перегрузка бывает временной: ждём и пробуем ещё раз, остальные ошибки сразу пропускаем
                if not re.match(r"(429|500|502|503|504) ", str(e)):
                    break
        _dead.add((api, model))
    raise RuntimeError("ни одна модель не ответила: %s" % last)


TIME_BUDGET = 12 * 60  # не дольше 12 минут за запуск, чтобы не тратить лишние минуты GitHub


def refill(force=False, dry=False):
    scen = load(SCEN, [])
    used = set(load(STATE, {"used": []})["used"])
    left = sum(1 for s in scen if s["id"] not in used)
    print("Осталось сценариев: %d" % left)
    if left >= MIN_LEFT and not force:
        return 0
    taken = {s["id"] for s in scen}
    added = 0
    started = time.time()
    for _ in range(ROUNDS):
        if time.time() - started > TIME_BUDGET:
            print("Время на пополнение вышло, остальное допишу в следующий раз")
            break
        titles = "\n".join("- " + s["title"] for s in scen)
        prompt = PROMPT.format(n=BATCH, used=titles, example=json.dumps(EXAMPLE, ensure_ascii=False, indent=1))
        try:
            raws, model = ask_ai(prompt)
        except Exception as e:
            print("Не удалось получить сценарии: %s" % e)
            break
        for raw in raws:
            try:
                v = build_video(raw, len(scen), taken)
            except Exception as e:
                print("Пропускаю неудачный сценарий: %s" % e)
                continue
            scen.append(v)
            taken.add(v["id"])
            added += 1
            print("+ %s (%s, %s)" % (v["id"], v["yt_title"], model))
    if added and dry:
        print(json.dumps(scen[-added:], ensure_ascii=False, indent=1))
    elif added:
        tmp = SCEN + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(scen, f, ensure_ascii=False, indent=1)
        os.replace(tmp, SCEN)
    print("Добавлено новых сценариев: %d" % added)
    return added


if __name__ == "__main__":
    refill("--force" in sys.argv, "--dry" in sys.argv)
