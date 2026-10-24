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


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "samples"))
