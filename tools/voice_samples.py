"""Примеры голосов: нейронные голоса Microsoft (edge-tts), бесплатно."""
import asyncio, os, sys, edge_tts

TEXT = "Первое видео на ютубе длилось всего девятнадцать секунд. А сегодня у него сотни миллионов просмотров!"
VOICES = [
    ("01-Дмитрий-нейро", "ru-RU-DmitryNeural"),
    ("02-Светлана-нейро", "ru-RU-SvetlanaNeural"),
    ("03-Дарья-нейро", "ru-RU-DariyaNeural"),
    ("04-Эндрю-мульти", "en-US-AndrewMultilingualNeural"),
    ("05-Брайан-мульти", "en-US-BrianMultilingualNeural"),
    ("06-Флориан-мульти", "de-DE-FlorianMultilingualNeural"),
    ("07-Ава-мульти", "en-US-AvaMultilingualNeural"),
    ("08-Эмма-мульти", "en-US-EmmaMultilingualNeural"),
]


async def main(out):
    os.makedirs(out, exist_ok=True)
    for name, voice in VOICES:
        try:
            await edge_tts.Communicate(TEXT, voice, rate="+8%").save(os.path.join(out, name + ".mp3"))
            print("ok", name)
        except Exception as e:
            print("fail", name, e)
    try:
        from gtts import gTTS
        gTTS(TEXT, lang="ru").save(os.path.join(out, "09-Google.mp3"))
        print("ok google")
    except Exception as e:
        print("fail google", e)
    ok = [f for f in os.listdir(out) if os.path.getsize(os.path.join(out, f)) > 5000]
    for f in os.listdir(out):
        if f not in ok:
            os.remove(os.path.join(out, f))
    print("готово:", ok)
    if not ok:
        sys.exit(1)


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "samples"))
