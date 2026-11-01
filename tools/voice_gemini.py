"""Примеры живых голосов Gemini TTS (бесплатный ключ GEMINI_API_KEY) + для сравнения edge-tts."""
import asyncio, base64, json, os, subprocess, sys, time
import requests

KEY = os.environ.get("GEMINI_API_KEY", "")
API = "https://generativelanguage.googleapis.com/v1beta"
TEXT = ("Интернет мог стать платным. Его спас один человек. "
        "В тысяча девятьсот девяносто третьем году ЦЕРН открыл технологию веба для всех: бесплатно и без патентов. "
        "Тим Бернерс-Ли мог разбогатеть на этом. Но выбрал открытый интернет. А ты бы отдал такое изобретение бесплатно?")
STYLE = ("Прочитай как популярный русский блогер в коротком видео: живо, уверенно, с естественной интонацией, "
         "паузами на точках и запятых, интригой в первой фразе и вопросом в конце. Не торопись, но и не тяни. Текст:\n")
VOICES = ["Charon", "Puck", "Fenrir", "Orus", "Enceladus", "Algenib", "Iapetus"]


def models():
    r = requests.get(API + "/models", params={"key": KEY, "pageSize": 200}, timeout=30).json()
    names = [m["name"].split("/")[-1] for m in r.get("models", []) if "tts" in m["name"]]
    print("TTS-модели:", names)
    return sorted(names, key=lambda n: ("preview" in n, n), reverse=True)


def gemini(model, voice, path):
    body = {"contents": [{"parts": [{"text": STYLE + TEXT}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    r = requests.post("%s/models/%s:generateContent" % (API, model), params={"key": KEY}, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError("%s %s" % (r.status_code, r.text[:200]))
    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    raw = path + ".pcm"
    open(raw, "wb").write(pcm)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", raw,
                    "-b:a", "128k", path], check=True)
    os.remove(raw)


async def edge(out):
    import edge_tts
    for name, v in [("90-Дмитрий-Microsoft", "ru-RU-DmitryNeural"), ("99-Флориан-сейчас", "de-DE-FlorianMultilingualNeural")]:
        try:
            await edge_tts.Communicate(TEXT, v, rate="+8%").save(os.path.join(out, name + ".mp3"))
            print("ok", name)
        except Exception as e:
            print("fail", name, e)


def main(out):
    os.makedirs(out, exist_ok=True)
    ms = models()
    for i, v in enumerate(VOICES):
        for m in ms:
            try:
                gemini(m, v, os.path.join(out, "%02d-Google-%s.mp3" % (i + 1, v)))
                print("ok", v, m)
                break
            except Exception as e:
                print("fail", v, m, e)
        time.sleep(21)  # бесплатный лимит — несколько запросов в минуту
    asyncio.run(edge(out))
    ok = [f for f in os.listdir(out) if os.path.getsize(os.path.join(out, f)) > 5000]
    print("готово:", ok)
    if not ok:
        sys.exit(1)


main(sys.argv[1] if len(sys.argv) > 1 else "samples")
