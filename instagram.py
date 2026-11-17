"""Публикация ролика в Instagram Reels (бесплатно, через официальный API Meta).

Подходят два вида ключа: со входом через Instagram (начинается с IG, живёт 60 дней)
и ключ страницы Facebook, к которой привязан Instagram (бессрочный).

Ключ живёт 60 дней, поэтому раз в неделю продлеваем его и храним новый в репозитории
в зашифрованном виде (ig_token.enc, пароль в секрете IG_KEY). Первый ключ берётся из секрета INSTAGRAM_TOKEN.
"""
import os, time, json, subprocess, datetime

API = "https://graph.instagram.com/v21.0"
FB_API = "https://graph.facebook.com/v21.0"
S = os.path.dirname(os.path.abspath(__file__))
ENC = os.path.join(S, "ig_token.enc")
META = os.path.join(S, "ig_token.json")  # когда ключ продлевали (без самого ключа)
REFRESH_DAYS = 7


def _openssl(args, data):
    key = os.environ.get("IG_KEY", "")
    if not key:
        raise RuntimeError("нет секрета IG_KEY")
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-a", "-A", "-pass", "env:IG_KEY"] + args,
                       input=data, capture_output=True, check=True)
    return r.stdout


def load_token():
    if os.path.exists(ENC) and os.environ.get("IG_KEY"):
        with open(ENC, "rb") as f:
            return _openssl(["-d"], f.read()).decode().strip()
    return os.environ.get("INSTAGRAM_TOKEN", "").strip()


def save_token(token):
    with open(ENC, "wb") as f:
        f.write(_openssl([], token.encode()))
    with open(META, "w") as f:
        json.dump({"refreshed": datetime.date.today().isoformat()}, f)


def maybe_refresh(token, log):
    import requests
    last = None
    if os.path.exists(META):
        try:
            last = datetime.date.fromisoformat(json.load(open(META))["refreshed"])
        except Exception:
            pass
    if not token.startswith("IG"):
        return token  # ключ страницы Facebook бессрочный, продлевать не нужно
    if last and (datetime.date.today() - last).days < REFRESH_DAYS:
        return token
    if not os.environ.get("IG_KEY"):
        return token
    r = requests.get(API.rsplit("/", 1)[0] + "/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=60)
    if r.status_code == 200 and r.json().get("access_token"):
        token = r.json()["access_token"]
        save_token(token)
        log("Ключ Instagram продлён")
    else:
        log("Не удалось продлить ключ Instagram: %s" % r.text[:200])
    return token


def caption(sc):
    desc = sc["description"].replace("#shorts", "#reels").replace("?start=shorts", "?start=reels")
    return (sc["yt_title"] + "\n\n" + desc)[:2100]


def upload(path, sc, log):
    """Возвращает ссылку на опубликованный Reels."""
    token = load_token()
    if not token:
        return None
    try:
        return _upload(path, sc, log, token)
    except _BadToken as e:
        # Сохранённый ключ страницы перестал работать (Meta иногда сбрасывает его после проверки аккаунта):
        # берём новый из ключа пользователя INSTAGRAM_TOKEN.
        fresh = os.environ.get("INSTAGRAM_TOKEN", "").strip()
        if not fresh or fresh == token:
            raise
        log("Сохранённый ключ Instagram не работает (%s), беру новый из INSTAGRAM_TOKEN" % str(e)[:150])
        return _upload(path, sc, log, fresh)


class _BadToken(RuntimeError):
    pass


def _upload(path, sc, log, token):
    import requests
    token = maybe_refresh(token, log)
    if token.startswith("IG"):
        api, me = API, "me"
    else:
        api = FB_API
        info = requests.get(FB_API + "/me", params={"fields": "instagram_business_account", "access_token": token}, timeout=60).json()
        if "instagram_business_account" not in info:
            # это ключ пользователя: берём из него бессрочный ключ страницы с привязанным Instagram и сохраняем
            pages = requests.get(FB_API + "/me/accounts", params={
                "fields": "access_token,instagram_business_account", "access_token": token}, timeout=60).json()
            page = next((p for p in pages.get("data", []) if p.get("instagram_business_account")), None)
            if not page:
                raise _BadToken("нет страницы Facebook с привязанным Instagram: %s" % str(pages)[:200])
            token, info = page["access_token"], page
            if os.environ.get("IG_KEY"):
                save_token(token)
                log("Ключ страницы Facebook сохранён (бессрочный)")
        me = info["instagram_business_account"]["id"]
    hosted = _host(path, log)
    try:
        params = {"media_type": "REELS", "caption": caption(sc), "share_to_feed": "true", "access_token": token}
        if hosted:
            params["video_url"] = hosted[0]
        else:
            params["upload_type"] = "resumable"
        r = requests.post("%s/%s/media" % (api, me), data=params, timeout=60)
        if r.status_code != 200:
            raise RuntimeError("Instagram не принял ролик (%s): %s" % (r.status_code, r.text[:300]))
        cid = r.json()["id"]
        if not hosted:
            _rupload(r.json()["uri"], path, token, api, cid)
        _wait(api, cid, token)
    finally:
        if hosted:
            hosted[1]()
    r = requests.post("%s/%s/media_publish" % (api, me), data={"creation_id": cid, "access_token": token}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("Instagram не опубликовал ролик (%s): %s" % (r.status_code, r.text[:300]))
    mid = r.json()["id"]
    link = requests.get(api + "/" + mid, params={"fields": "permalink", "access_token": token}, timeout=60).json().get("permalink")
    return link or ("id " + mid)


def _rupload(uri, path, token, api, cid):
    """Прямая загрузка файла (на пути через Facebook Meta её отклоняет, поэтому только запасной вариант)."""
    import requests
    with open(path, "rb") as f:
        body = f.read()
    r = requests.post(uri, data=body, timeout=600, headers={
        "Authorization": "OAuth " + token, "offset": "0", "file_size": str(len(body)),
        "Content-Type": "application/octet-stream"})
    if r.status_code != 200:
        st = requests.get(api + "/" + cid, params={"fields": "status_code,video_status",
                                                  "access_token": token}, timeout=60).text
        raise RuntimeError("Instagram: загрузка файла не прошла (%s): %s; контейнер: %s"
                           % (r.status_code, r.text[:300], st[:500]))


def _wait(api, cid, token):
    import requests
    for _ in range(60):  # обработка видео обычно занимает 30-90 секунд
        time.sleep(10)
        st = requests.get(api + "/" + cid, params={"fields": "status_code,status", "access_token": token}, timeout=60).json()
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") == "ERROR":
            raise RuntimeError("Instagram не смог обработать видео: %s" % st.get("status"))
    raise RuntimeError("Instagram слишком долго обрабатывает видео")


KV_LIMIT = 24 * 1024 * 1024  # в Cloudflare KV одно значение не больше 25 МБ


def _host(path, log):
    """Кладёт ролик на час в память бота-портфолио (Cloudflare KV), бот отдаёт его по ссылке,
    Instagram скачивает ролик сам. Возвращает (ссылка, удалить) или None, если Cloudflare не настроен."""
    import secrets
    from cfkv import KV
    kv = KV()
    bot = kv.bot_url() if kv.ok else None
    if not bot:
        log("Cloudflare: не нашёл память или адрес бота, пробую прямую загрузку")
        return None
    if os.path.getsize(path) > KV_LIMIT:
        small = path + ".ig.mp4"
        from engine import FFMPEG
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path, "-c:v", "libx264", "-preset", "medium",
                        "-crf", "26", "-maxrate", "3M", "-bufsize", "6M", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", small], check=True)
        path = small
    key = "reel-%s.mp4" % secrets.token_hex(16)
    with open(path, "rb") as f:
        if not kv.put(key, f.read(), ttl=3600):
            log("Cloudflare не принял ролик, пробую прямую загрузку")
            return None
    return "%s/ig/%s" % (bot, key), lambda: kv.delete(key)
