"""Публикация ролика в Instagram Reels (Instagram API со входом через Instagram, бесплатно).

Ключ живёт 60 дней, поэтому раз в неделю продлеваем его и храним новый в репозитории
в зашифрованном виде (ig_token.enc, пароль в секрете IG_KEY). Первый ключ берётся из секрета INSTAGRAM_TOKEN.
"""
import os, time, json, subprocess, datetime

API = "https://graph.instagram.com/v21.0"
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
    desc = sc["description"].replace("#shorts", "#reels")
    return (sc["yt_title"] + "\n\n" + desc)[:2100]


def upload(path, sc, log):
    """Возвращает ссылку на опубликованный Reels."""
    import requests
    token = load_token()
    if not token:
        return None
    token = maybe_refresh(token, log)
    r = requests.post(API + "/me/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption(sc),
        "share_to_feed": "true", "access_token": token}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("Instagram не принял ролик (%s): %s" % (r.status_code, r.text[:300]))
    cid, uri = r.json()["id"], r.json()["uri"]
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = requests.post(uri, data=f, timeout=600, headers={
            "Authorization": "OAuth " + token, "offset": "0", "file_size": str(size)})
    if r.status_code != 200:
        raise RuntimeError("Instagram: загрузка файла не прошла (%s): %s" % (r.status_code, r.text[:300]))
    for _ in range(60):  # обработка видео обычно занимает 30-90 секунд
        time.sleep(10)
        st = requests.get(API + "/" + cid, params={"fields": "status_code,status", "access_token": token}, timeout=60).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError("Instagram не смог обработать видео: %s" % st.get("status"))
    else:
        raise RuntimeError("Instagram слишком долго обрабатывает видео")
    r = requests.post(API + "/me/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("Instagram не опубликовал ролик (%s): %s" % (r.status_code, r.text[:300]))
    mid = r.json()["id"]
    link = requests.get(API + "/" + mid, params={"fields": "permalink", "access_token": token}, timeout=60).json().get("permalink")
    return link or ("id " + mid)
