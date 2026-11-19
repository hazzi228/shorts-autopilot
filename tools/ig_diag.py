"""Подробная диагностика публикации Reels: права ключа, аккаунт, файл, разные способы публикации.
Останавливается на первом удачном способе (тогда ролик реально выходит в Instagram)."""
import json, os, sys, time, subprocess, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine, instagram

T = instagram.load_token()
UID = instagram.IG_USER_ID
V = "https://graph.facebook.com/v21.0"
NV = "https://graph.facebook.com"


def show(title, r):
    try:
        body = r.json()
    except Exception:
        body = r.text[:500]
    hdr = {k: v for k, v in r.headers.items() if k.lower() in ("www-authenticate", "x-fb-debug", "x-app-usage",
                                                             "x-business-use-case-usage", "facebook-api-version")}
    print("==", title, "->", r.status_code, json.dumps(body, ensure_ascii=False)[:1500], hdr, flush=True)
    return body


print("Ключ начинается на", T[:4], "длина", len(T))
show("me", requests.get(NV + "/me", params={"fields": "id,name", "access_token": T}))
show("me/permissions", requests.get(NV + "/me/permissions", params={"access_token": T}))
show("ig account", requests.get(NV + "/" + UID, params={"fields": "id,username,name,media_count,followers_count", "access_token": T}))
show("publishing limit", requests.get(NV + "/" + UID + "/content_publishing_limit", params={"fields": "config,quota_usage", "access_token": T}))
show("last media", requests.get(NV + "/" + UID + "/media", params={"fields": "id,media_type,media_product_type,timestamp", "limit": 3, "access_token": T}))

sc = next(s for s in json.load(open("scenarios.json", encoding="utf-8")) if s["id"] == os.environ["SCENARIO"])
os.makedirs("work", exist_ok=True)
engine.build(sc, "work/video.mp4", "work")
hosted = instagram._host("work/video.mp4", print)
src = "work/video.mp4.ig.mp4"
try:
  print(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                      "format=duration,size,bit_rate:stream=codec_name,profile,width,height,r_frame_rate,pix_fmt,sample_rate,channels,bit_rate",
                      "-of", "json", src], capture_output=True, text=True).stdout)
except Exception as e:
  print("ffprobe:", e, subprocess.run([engine.FFMPEG, "-hide_banner", "-i", src], capture_output=True, text=True).stderr[-1500:])
if hosted:
    h = requests.get(hosted[0], stream=True, timeout=60)
    print("== файл по ссылке:", h.status_code, h.headers.get("content-type"), h.headers.get("content-length"), flush=True)
    h.close()


def wait(api, cid):
    for _ in range(60):
        time.sleep(10)
        st = show("container", requests.get(api + "/" + cid, params={"fields": "id,status_code,status", "access_token": T}))
        if st.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"):
            return st.get("status_code")
    return "TIMEOUT"


def attempt(name, api, extra, pause=0, resumable=False):
    print("\n######", name, flush=True)
    params = dict(extra, media_type="REELS", access_token=T)
    if resumable:
        params["upload_type"] = "resumable"
    else:
        params["video_url"] = hosted[0]
    c = show("create", requests.post(api + "/" + UID + "/media", data=params))
    if "id" not in c:
        return False
    cid = c["id"]
    if resumable:
        body = open(src, "rb").read()
        show("rupload", requests.post(c["uri"], data=body, headers={"Authorization": "OAuth " + T, "offset": "0",
                                                                   "file_size": str(len(body))}))
    if wait(api, cid) != "FINISHED":
        return False
    if pause:
        print("пауза", pause, "с", flush=True)
        time.sleep(pause)
    p = show("publish", requests.post(api + "/" + UID + "/media_publish", data={"creation_id": cid, "access_token": T}))
    if "id" in p:
        show("permalink", requests.get(NV + "/" + p["id"], params={"fields": "permalink", "access_token": T}))
        return True
    return False


try:
    ok = (attempt("A: как в автопилоте, но пауза 60 с перед публикацией", V, {"caption": sc["yt_title"]}, pause=60)
          or attempt("B: без версии API (версия приложения по умолчанию)", NV, {"caption": sc["yt_title"]})
          or attempt("C: прямая загрузка файла (resumable)", V, {"caption": sc["yt_title"]}, resumable=True))
    print("\nИТОГ:", "получилось" if ok else "ни один способ не прошёл")
finally:
    if hosted:
        hosted[1]()
