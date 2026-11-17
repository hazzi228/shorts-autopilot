"""Отправка ролика в черновики TikTok (бесплатно, официальный Content Posting API).

Пока приложение TikTok не прошло аудит, публиковать сразу для всех нельзя, поэтому ролик уходит
во «входящие» TikTok: приходит уведомление, владелец открывает черновик и жмёт «Опубликовать».

Вход в TikTok делает владелец командой /tiktok в боте-портфолио; бот кладёт ключ в KV (tiktok_auth).
Ключ доступа живёт сутки, поэтому каждый раз получаем новый по refresh_token и сохраняем обновлённый.
Нужны секреты TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET и CLOUDFLARE_* (как для Instagram).
"""
import os, json, time, secrets

API = "https://open.tiktokapis.com/v2"
KEY = "tiktok_auth"


def _access_token(kv, log):
    import requests
    auth = kv.get(KEY)
    if not auth:
        return None
    auth = json.loads(auth)
    r = requests.post(API + "/oauth/token/", timeout=60, data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"].strip(),
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"].strip(),
        "grant_type": "refresh_token", "refresh_token": auth["refresh_token"]}).json()
    if "access_token" not in r:
        raise RuntimeError("TikTok не обновил ключ (напиши боту /tiktok и войди заново): %s"
                           % (r.get("error_description") or r.get("error") or str(r)[:200]))
    if r.get("refresh_token") and r["refresh_token"] != auth["refresh_token"]:
        auth["refresh_token"] = r["refresh_token"]
        kv.put(KEY, json.dumps(auth), ttl=max(86400, int(r.get("refresh_expires_in") or 365 * 86400)))
    return r["access_token"]


def direct():
    """Публиковать сразу, а не в черновики: включается переменной TIKTOK_MODE=direct в настройках GitHub."""
    return os.environ.get("TIKTOK_MODE", "").strip().lower() == "direct"


def caption(sc):
    desc = sc["description"].replace("#shorts", "#fyp").replace("?start=shorts", "?start=tiktok")
    return (sc["yt_title"] + "\n\n" + desc)[:2100]


def notify(kv, sc, log):
    """Присылает владельцу в бот-портфолио описание для черновика: API черновиков текст не принимает."""
    import requests
    key = "tt_note-" + secrets.token_hex(16)
    url = kv.bot_url()
    if not url or not kv.put(key, caption(sc).encode(), ttl=3600):
        return
    r = requests.post(url + "/tiktok/note/" + key, timeout=60)
    if not r.ok:
        log("Не удалось прислать описание для TikTok в Telegram: %s" % _err(r))


def _upload(path, sc, log, kv):
    """Отправляет ролик в черновики TikTok. Возвращает publish_id, None, если TikTok не подключён, или False, если не обработал."""
    import requests
    if not os.environ.get("TIKTOK_CLIENT_KEY", "").strip():
        return None
    if os.environ.get("TIKTOK_TEST_FALLBACK"):  # проверка запасного пути из tt-post.yml
        return False
    token = _access_token(kv, log)
    if not token:
        log("TikTok не подключён: напиши боту /tiktok")
        return False
    size = os.path.getsize(path)
    head = {"Authorization": "Bearer " + token, "Content-Type": "application/json; charset=UTF-8"}
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    # Одним куском можно до 64 МБ, наши ролики меньше.
    if direct():
        # Сразу публикация (после аудита Direct Post): текст идёт вместе с роликом, черновик не нужен.
        info = requests.post(API + "/post/publish/creator_info/query/", headers=head, timeout=60).json().get("data") or {}
        opts = info.get("privacy_level_options") or ["SELF_ONLY"]
        privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in opts else opts[0]
        if privacy != "PUBLIC_TO_EVERYONE":
            log("TikTok разрешает только приватность %s: аудит Direct Post ещё не пройден" % privacy)
        r = requests.post(API + "/post/publish/video/init/", headers=head, timeout=60, json={
            "post_info": {"title": caption(sc)[:2200], "privacy_level": privacy, "disable_comment": False,
                          "disable_duet": False, "disable_stitch": False},
            "source_info": source}).json()
    else:
        r = requests.post(API + "/post/publish/inbox/video/init/", headers=head, timeout=60,
                          json={"source_info": source}).json()
    data = r.get("data") or {}
    if not data.get("upload_url"):
        raise RuntimeError("TikTok не принял ролик: %s" % str(r.get("error") or r)[:300])
    with open(path, "rb") as f:
        up = requests.put(data["upload_url"], data=f.read(), timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Range": "bytes 0-%d/%d" % (size - 1, size)})
    if up.status_code not in (200, 201):
        raise RuntimeError("TikTok: загрузка файла не прошла (%s): %s" % (up.status_code, up.text[:300]))
    pid = data["publish_id"]
    log("TikTok: ролик загружен, publish_id " + pid)
    st = {}
    for _ in range(90):  # до 15 минут: в часы пик TikTok обрабатывает ролик дольше 5 минут
        time.sleep(10)
        try:  # TikTok иногда отвечает не JSON (сбой на их стороне): просто спрашиваем ещё раз
            st = requests.post(API + "/post/publish/status/fetch/", headers=head, timeout=60,
                               json={"publish_id": pid}).json().get("data") or {}
        except Exception as e:
            log("TikTok: статус пока не получен (%s)" % e)
            continue
        if st.get("status") in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            if not direct():
                notify(kv, sc, log)
            return pid
        if st.get("status") == "FAILED":
            raise RuntimeError("TikTok не обработал ролик: %s" % st.get("fail_reason"))
    log("TikTok за 15 минут не обработал ролик (статус %s)" % st.get("status"))
    return False


def upload(path, sc, log):
    """Отправляет ролик в TikTok. Если не вышло, присылает владельцу в бот сам ролик и описание для ручной загрузки."""
    if not os.environ.get("TIKTOK_CLIENT_KEY", "").strip():
        return None
    from cfkv import KV
    kv = KV()
    if not kv.ok:
        return None
    try:
        pid = _upload(path, sc, log, kv)
    except Exception as e:
        send_fallback(kv, path, sc, "TikTok не принял ролик: %s" % str(e)[:200], log)
        raise
    if pid is False:
        send_fallback(kv, path, sc, "TikTok за 15 минут не обработал ролик", log)
    return pid


def send_fallback(kv, path, sc, why, log):
    """Кладёт ролик и описание в KV на час и просит бота прислать их владельцу."""
    import requests
    try:
        key = secrets.token_hex(16)
        url = kv.bot_url()
        with open(path, "rb") as f:
            ok = url and kv.put("tt_vid-" + key, f.read(), ttl=3600) and \
                kv.put("tt_fail-" + key, json.dumps({"why": why, "caption": caption(sc)}).encode(), ttl=3600)
        if not ok:
            log("Не удалось подготовить ролик для отправки в бот")
            return
        r = requests.post(url + "/tiktok/fail/" + key, timeout=180)
        log("Ролик и описание для TikTok отправлены в бот" if r.ok else "Бот не прислал ролик: %s" % _err(r))
    except Exception as e:
        log("Не удалось прислать ролик в бот: %s" % str(e)[:200])


def _err(r):
    """Короткая причина ошибки бота: вместо целой HTML-страницы Cloudflare берём её заголовок."""
    import re
    m = re.search(r"<title>(.*?)</title>", r.text or "", re.S | re.I)
    return "%s %s" % (r.status_code, (m.group(1).strip() if m else (r.text or "")[:200]))
