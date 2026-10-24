"""Пополняет scenarios.json новыми сценариями, когда старые заканчиваются.

Пишет сценарии бесплатный ИИ GitHub Models (доступ даёт сам GitHub Actions через GITHUB_TOKEN).
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
BATCH = 4             # сценариев за один запрос к ИИ (ограничение бесплатного лимита на длину ответа)
ROUNDS = 3            # запросов за одно пополнение: 3 × 4 = 12 новых сценариев (4 дня)
# (адрес, модель): сначала новый адрес GitHub Models, потом старый (Azure), он тоже принимает токен GitHub
MODELS = [
    ("https://models.github.ai/inference/chat/completions", "openai/gpt-4.1"),
    ("https://models.inference.ai.azure.com/chat/completions", "gpt-4o"),
    ("https://models.github.ai/inference/chat/completions", "openai/gpt-4o"),
    ("https://models.inference.ai.azure.com/chat/completions", "gpt-4o-mini"),
]

ACCENTS = [(124, 92, 255), (0, 200, 255), (255, 120, 60), (40, 210, 140), (255, 70, 120), (255, 190, 40)]
HANDLE = "@PortfolioHazzer_bot"
AD2 = [
    ("Бот сам принимает заявки и оплату, пока ты спишь. Сделаю такого и тебе, по приятной цене. Все работы и отзывы в боте-портфолио, ссылка на экране.",
     "Бот принимает заявки и оплату, пока ты спишь. Сделаю и тебе по приятной цене. Портфолио: " + HANDLE),
    ("Хороший сайт или бот сам приводит клиентов. Сделаю от идеи до запуска, по приятной цене. Все работы и отзывы в боте-портфолио, ссылка на экране.",
     "Хороший сайт или бот сам приводит клиентов. Сделаю от идеи до запуска по приятной цене. Портфолио: " + HANDLE),
    ("Магазин, запись клиентов или продажа подписок прямо в телеграме. Сделаю под ключ, по приятной цене. Все работы и отзывы в боте-портфолио, ссылка на экране.",
     "Магазин, запись клиентов или подписки прямо в Telegram. Сделаю под ключ по приятной цене. Портфолио: " + HANDLE),
]
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
  "yt_title": "цепляющий заголовок до 70 символов, в конце один эмодзи",
  "story": [3 сцены],
  "bridge": {{"say": "...", "show": "..."}},
  "ending": [2 сцены],
  "desc": "2 строки описания для YouTube, вторая строка — вопрос зрителю и 👇",
  "tags": ["4-5 тегов без решётки, по-русски или латиницей"]
}}
Сцена: {{"say": "...", "show": "...", "hero": {{"type": "emoji", "emoji": "один эмодзи", "caption": "подпись до 30 символов"}}}}
или hero {{"type": "big", "text": "до 6 символов, например год 1992 или 0:19", "caption": "подпись до 30 символов"}}.

Правила:
- "say" читает робот-диктор: в нём НЕТ цифр и латинских букв. Числа и годы пиши словами
  ("в тысяча девятьсот девяносто втором году"), английские названия — русскими буквами ("ютуб", "эппл", "эс эм эс").
- "show" — тот же текст для экрана, там цифры и латиница можно.
- Каждая сцена 1-2 коротких предложения, до 160 символов.
- Первая сцена story — сильный крючок. Ролик целиком около 30-40 секунд.
- "bridge" — одна фраза, которая плавно связывает тему ролика с тем, что бизнесу нужен сайт или телеграм-бот
  (без слов "реклама" и без имени автора, оно добавится само).
- Последняя сцена ending — вопрос зрителю, hero emoji с caption "пиши в комментариях", а в "show" в конце 👇.

Пример одного ролика:
{example}
"""

EXAMPLE = {
    "id": "sms", "topic": "Первое SMS в истории", "yt_title": "Первое SMS в мире было всего из двух слов 📱",
    "story": [
        {"say": "Первое эс эм эс в истории состояло всего из двух слов.", "show": "Первое SMS в истории состояло всего из двух слов.",
         "hero": {"type": "emoji", "emoji": "📱", "caption": "первое SMS"}},
        {"say": "Третьего декабря тысяча девятьсот девяносто второго года инженер Нил Папворт отправил с компьютера на телефон сообщение: Мэрри Кристмас.",
         "show": "3 декабря 1992 года инженер Нил Папворт отправил с компьютера на телефон: «Merry Christmas».",
         "hero": {"type": "big", "text": "1992", "caption": "3 декабря"}},
        {"say": "Ответить получатель не смог. На телефонах тогда просто не было возможности писать сообщения.",
         "show": "Ответить получатель не смог. На телефонах тогда просто не было возможности писать сообщения.",
         "hero": {"type": "emoji", "emoji": "🤷", "caption": "ответить было нельзя"}}],
    "bridge": {"say": "Сегодня в телефоне можно не только переписываться, но и покупать в пару нажатий.",
               "show": "Сегодня в телефоне не только переписываются, но и покупают в пару нажатий."},
    "ending": [
        {"say": "А через несколько лет люди отправляли уже миллиарды сообщений в день.", "show": "А через несколько лет люди отправляли уже миллиарды сообщений в день.",
         "hero": {"type": "big", "text": "SMS", "caption": "миллиарды в день"}},
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


def scene(raw):
    h = raw.get("hero") or {}
    say = clean_say(raw.get("say", ""))
    show = " ".join(str(raw.get("show") or say).split())[:220]
    cap = " ".join(str(h.get("caption", "")).split())[:34]
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
    return dict(say=say, show=show, hero=hero)


def build_video(raw, index, taken):
    vid = re.sub(r"[^a-z0-9-]", "", str(raw.get("id", "")).lower().replace(" ", "-")).strip("-")[:40] or "fact"
    base, n = vid, 2
    while vid in taken:
        vid = "%s-%d" % (base, n)
        n += 1
    story = [scene(x) for x in raw.get("story", [])]
    ending = [scene(x) for x in raw.get("ending", [])]
    if len(story) != 3 or not 1 <= len(ending) <= 2:
        raise Bad("число сцен")
    br = raw.get("bridge") or {}
    b_say = clean_say(br.get("say", ""))
    b_show = " ".join(str(br.get("show") or b_say).split())
    ad1 = dict(ad=True, hero=["reviews"],
               say=b_say + " Я Хаззер, делаю телеграм боты и сайты под ключ. Вот что пишут мои заказчики.",
               show=b_show + " Я Hazzer, делаю Telegram-ботов и сайты под ключ. Отзывы заказчиков ⭐ 5 из 5")
    a2 = AD2[index % 3]
    ad2 = dict(ad=True, hero=["cta"], say=a2[0], show=a2[1])
    tags = [str(t).replace("#", "").strip() for t in raw.get("tags", []) if str(t).strip()][:5] + ["телеграмбот"]
    hashtags = " ".join("#" + t.replace(" ", "") for t in tags + ["shorts"])
    title = " ".join(str(raw.get("yt_title", "")).split())[:95]
    desc = str(raw.get("desc", "")).strip()
    if not title or not desc:
        raise Bad("нет заголовка или описания")
    return dict(id=vid, title=str(raw.get("topic") or title)[:80], accent=list(ACCENTS[index % len(ACCENTS)]),
                yt_title=title, description=desc + "\n\n" + CTA_DESC + "\n\n" + hashtags,
                tags=tags + ["shorts", "интересные факты"], scenes=story + [ad1, ad2] + ending)


def ask_ai(prompt):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("нет GITHUB_TOKEN")
    last = None
    for api, model in MODELS:
        try:
            import requests
            r = requests.post(api, timeout=180, json={
                "model": model, "temperature": 0.9, "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}]}, headers={
                "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "shorts-autopilot"})
            if r.status_code != 200:
                raise RuntimeError("%s %s" % (r.status_code, r.text[:300]))
            if "json" not in r.headers.get("Content-Type", ""):
                raise RuntimeError("ответ не JSON (%s, %s, %r)" % (r.url, r.headers.get("Content-Type"), r.text[:100]))
            try:
                text = r.json()["choices"][0]["message"]["content"]
            except Exception:
                raise RuntimeError("непонятный ответ: %r" % r.text[:300])
            m = re.search(r"\{.*\}", text, re.S)
            return json.loads(m.group(0))["videos"], model
        except Exception as e:
            print("Модель %s (%s) не ответила: %s" % (model, api, e))
            last = e
            time.sleep(5)
    raise RuntimeError("ни одна модель не ответила: %s" % last)


def refill(force=False, dry=False):
    scen = load(SCEN, [])
    used = set(load(STATE, {"used": []})["used"])
    left = sum(1 for s in scen if s["id"] not in used)
    print("Осталось сценариев: %d" % left)
    if left >= MIN_LEFT and not force:
        return 0
    taken = {s["id"] for s in scen}
    added = 0
    for _ in range(ROUNDS):
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
