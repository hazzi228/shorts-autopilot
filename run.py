"""Автопилот: берёт следующий сценарий, собирает ролик, обновляет папку на рабочем столе и загружает на YouTube.

Запуск: python run.py            — обычный запуск (по расписанию)
        python run.py --no-upload — собрать ролик без загрузки (проверка)
        python run.py --check     — только сказать, пора ли выпускать ролик (для облака)
"""
import os, sys, json, glob, shutil, datetime, traceback, time

S = os.path.dirname(os.path.abspath(__file__))
os.chdir(S)
CONFIG = os.path.join(S, "config.json")
SCEN = os.path.join(S, "scenarios.json")
ADS = os.path.join(S, "ads.json")  # рекламные ролики для слота 12:00, идут по кругу
STATE = os.path.join(S, "state.json")
TOKEN = os.path.join(S, "token.json")
LOG = os.path.join(S, "log.txt")
LOCK = os.path.join(S, "run.lock")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def log(msg):
    line = "[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        print(line)
    except Exception:
        pass


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def output_dir(cfg):
    d = cfg.get("output_dir") or os.path.join(os.path.expanduser("~"), "Desktop", "Рекламные ролики")
    os.makedirs(d, exist_ok=True)
    return d


def description_text(sc):
    return sc["description"].strip()


def upload_once(path, sc, cfg):
    """Загрузка через requests: он сам берёт системный прокси Windows (VPN-клиент), лишние библиотеки не нужны."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request, AuthorizedSession

    if not os.path.exists(TOKEN):
        raise RuntimeError("Нет token.json: запусти setup.bat, чтобы войти в YouTube")
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        with open(TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    body = {
        "snippet": {
            "title": sc["yt_title"][:100],
            "description": description_text(sc)[:4900],
            "tags": sc.get("tags", [])[:15],
            "categoryId": "28",
            "defaultLanguage": "ru",
            "defaultAudioLanguage": "ru",
        },
        "status": {"privacyStatus": cfg.get("privacy", "public"), "selfDeclaredMadeForKids": False},
    }
    size = os.path.getsize(path)
    s = AuthorizedSession(creds)
    r = s.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        json=body,
        headers={"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        timeout=120,
    )
    if r.status_code != 200 or "Location" not in r.headers:
        raise RuntimeError("YouTube не принял запрос (%s): %s" % (r.status_code, r.text[:300]))
    with open(path, "rb") as f:
        r = s.put(r.headers["Location"], data=f,
                  headers={"Content-Type": "video/mp4", "Content-Length": str(size)}, timeout=900)
    if r.status_code not in (200, 201):
        raise RuntimeError("Загрузка не прошла (%s): %s" % (r.status_code, r.text[:300]))
    return r.json()["id"]


def upload(path, sc, cfg):
    waits = [30, 90, 180, 300]
    for attempt in range(len(waits) + 1):
        try:
            return upload_once(path, sc, cfg)
        except Exception as e:
            if attempt == len(waits) or "token.json" in str(e) or "invalid_grant" in str(e):
                raise
            log("Не получилось загрузить (%s), пробую ещё раз через %d сек" % (str(e)[:150], waits[attempt]))
            time.sleep(waits[attempt])


def write_descriptions(out_dir, sc, fname, video_id, err):
    lines = ["ОПИСАНИЕ К РОЛИКУ", ""]
    lines.append("Файл: " + fname)
    if video_id:
        lines.append("Загружен на YouTube: https://youtube.com/shorts/" + video_id)
    elif err:
        lines.append("НЕ ЗАГРУЖЕН на YouTube: " + err)
        lines.append("Можно выложить вручную, текст ниже.")
    lines += ["", "Заголовок:", sc["yt_title"], "", "Описание:", description_text(sc), ""]
    with open(os.path.join(out_dir, "Описания.txt"), "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))


def pid_alive(pid):
    """Жив ли процесс (если окно закрыли крестиком, lock-файл остаётся, а процесса уже нет)."""
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


SLOTS_MSK = [8, 12, 16, 22]  # во сколько по Москве выходят ролики
AD_SLOT_MSK = 12             # в этот слот выходит реклама бота для продавцов Playerok (ads.json), в остальные факты
SLOT_WINDOW_H = 3            # если GitHub опоздал, ролик всё равно выходит в течение 3 часов после слота


def last_upload_utc():
    """Время последнего успешного ролика по log.txt (в облаке время в логе по UTC), или None."""
    if not os.path.exists(LOG):
        return None
    last = None
    with open(LOG, encoding="utf-8") as f:
        for line in f:
            if "Загружен на YouTube" in line:
                last = line
    if not last:
        return None
    try:
        return datetime.datetime.strptime(last[1:20], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def current_slot():
    """Последний начавшийся слот: (час по Москве, начало слота по UTC)."""
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    msk = now + datetime.timedelta(hours=3)
    starts = [msk.replace(hour=h, minute=0, second=0, microsecond=0) - datetime.timedelta(days=d)
              for d in (0, 1) for h in SLOTS_MSK]
    start = max(t for t in starts if t <= msk)
    return start.hour, start - datetime.timedelta(hours=3)


def slot_due():
    """Пора ли выпускать ролик: идёт окно слота, а в этом слоте ролика ещё не было.
    Расписание GitHub часто опаздывает на час-два, поэтому оно запускается каждый час, а решает этот код."""
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    start = current_slot()[1]
    if now - start > datetime.timedelta(hours=SLOT_WINDOW_H):
        return False
    last = last_upload_utc()
    return not (last and last >= start - datetime.timedelta(minutes=30))


def main():
    no_upload = "--no-upload" in sys.argv
    if "--check" in sys.argv:
        # быстрая проверка до установки библиотек: печатает due=true/false для GitHub Actions
        due = slot_due()
        print("due=" + ("true" if due else "false"))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write("due=%s\n" % ("true" if due else "false"))
        return
    if os.path.exists(LOCK) and (datetime.datetime.now().timestamp() - os.path.getmtime(LOCK)) < 3 * 3600:
        try:
            other = int(open(LOCK).read().strip() or 0)
        except Exception:
            other = 0
        if other and pid_alive(other):
            log("Уже идёт другой запуск, выхожу")
            return
        log("Прошлый запуск был прерван, продолжаю")
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    try:
        cfg = load_json(CONFIG, {})
        scenarios = load_json(SCEN, [])
        state = load_json(STATE, {"used": []})
        ads = load_json(ADS, [])
        is_ad = bool(ads) and ("--ad" in sys.argv or ("--fact" not in sys.argv and current_slot()[0] == AD_SLOT_MSK))
        todo = [s for s in scenarios if s["id"] not in state["used"]]
        if is_ad:
            sc = ads[state.get("ads_done", 0) % len(ads)]
            log("Собираю рекламный ролик: %s (%s)" % (sc["id"], sc["yt_title"]))
        elif not todo:
            log("Сценарии закончились. Попроси Claude сделать новую пачку и положить scenarios.json в эту папку.")
            return
        else:
            sc = todo[0]
            log("Собираю ролик: %s (%s), осталось сценариев: %d" % (sc["id"], sc["yt_title"], len(todo) - 1))

        import engine
        work = os.path.join(S, "work")
        shutil.rmtree(work, ignore_errors=True)
        tmp_video = os.path.join(work, "video.mp4")
        os.makedirs(work, exist_ok=True)
        engine.build(sc, tmp_video, work)
        log("Ролик собран")

        video_id, err = None, None
        if not no_upload and cfg.get("upload", True):
            try:
                video_id = upload(tmp_video, sc, cfg)
                log("Загружен на YouTube: https://youtube.com/shorts/" + video_id)
            except Exception as e:
                err = str(e)[:300]
                log("Ошибка загрузки на YouTube: " + err)
                log(traceback.format_exc())
            # Reels только после YouTube: иначе при повторе сценария в Instagram вышел бы дубль.
            # Ошибка Instagram не мешает YouTube и не ломает запуск.
            try:
                import instagram
                link = instagram.upload(tmp_video, sc, log) if video_id else None
                if link:
                    log("Опубликован в Instagram: " + link)
            except Exception as e:
                log("Ошибка публикации в Instagram: " + str(e)[:300])
            try:
                import tiktok
                if video_id and tiktok.upload(tmp_video, sc, log):
                    log(("Опубликован в TikTok: " if tiktok.direct() else "Отправлен в черновики TikTok: ") + sc["yt_title"])
            except Exception as e:
                log("Ошибка отправки в TikTok: " + str(e)[:300])

        # в папке на рабочем столе остаётся только свежий ролик и его описание
        out_dir = output_dir(cfg)
        for old in glob.glob(os.path.join(out_dir, "*.mp4")):
            try:
                os.remove(old)
            except OSError as e:
                log("Не удалось удалить старое видео %s: %s" % (old, e))
        fname = "%s %s.mp4" % (datetime.datetime.now().strftime("%Y-%m-%d %H-%M"), sc["id"])
        shutil.copyfile(tmp_video, os.path.join(out_dir, fname))
        write_descriptions(out_dir, sc, fname, video_id, err)

        # если загрузка не удалась, сценарий не помечаем: в следующий запуск попробуем снова
        if not no_upload and (video_id or not cfg.get("upload", True)):
            if is_ad:
                state["ads_done"] = state.get("ads_done", 0) + 1
            else:
                state["used"].append(sc["id"])
            save_json(STATE, state)
        log("Готово: " + fname)
        shutil.rmtree(work, ignore_errors=True)
        if err and os.environ.get("GITHUB_ACTIONS"):
            # в облаке помечаем запуск красным, чтобы GitHub прислал письмо об ошибке
            sys.exit(1)
    except Exception:
        log("Ошибка: " + traceback.format_exc())
        raise
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


if __name__ == "__main__":
    main()
