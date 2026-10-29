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


def caption(sc):
    desc = sc["description"].replace("#shorts", "#fyp")
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
        log("Не удалось прислать описание для TikTok в Telegram: %s" % r.text[:200])


def upload(path, sc, log):
    """Отправляет ролик в черновики TikTok. Возвращает publish_id или None, если TikTok не подключён."""
    import requests
    if not os.environ.get("TIKTOK_CLIENT_KEY", "").strip():
        return None
    from cfkv import KV
    kv = KV()
    if not kv.ok:
        return None
    token = _access_token(kv, log)
    if not token:
        return None
    size = os.path.getsize(path)
    head = {"Authorization": "Bearer " + token, "Content-Type": "application/json; charset=UTF-8"}
    # Одним куском можно до 64 МБ, наши ролики меньше.
    r = requests.post(API + "/post/publish/inbox/video/init/", headers=head, timeout=60, json={
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}}).json()
    data = r.get("data") or {}
    if not data.get("upload_url"):
        raise RuntimeError("TikTok не принял ролик: %s" % str(r.get("error") or r)[:300])
    with open(path, "rb") as f:
        up = requests.put(data["upload_url"], data=f.read(), timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Range": "bytes 0-%d/%d" % (size - 1, size)})
    if up.status_code not in (200, 201):
        raise RuntimeError("TikTok: загрузка файла не прошла (%s): %s" % (up.status_code, up.text[:300]))
    pid = data["publish_id"]
    for _ in range(30):
        time.sleep(10)
        st = requests.post(API + "/post/publish/status/fetch/", headers=head, timeout=60,
                           json={"publish_id": pid}).json().get("data") or {}
        if st.get("status") in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            notify(kv, sc, log)
            return pid
        if st.get("status") == "FAILED":
            raise RuntimeError("TikTok не обработал ролик: %s" % st.get("fail_reason"))
    log("TikTok ещё обрабатывает ролик, черновик придёт позже")
    notify(kv, sc, log)
    return pid
