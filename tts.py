import asyncio, json, os, edge_tts
VOICE = "de-DE-FlorianMultilingualNeural"
RATE = os.environ.get("RATE", "+4%")
lines = json.load(open("lines.json", encoding="utf-8"))
os.makedirs("tts", exist_ok=True)

async def one(i, text):
    mp3, js = "tts/%03d.mp3" % i, "tts/%03d.json" % i
    for attempt in range(5):
        try:
            words = []
            with open(mp3, "wb") as f:
                async for ch in edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary").stream():
                    if ch["type"] == "audio":
                        f.write(ch["data"])
                    elif ch["type"] == "WordBoundary":
                        words.append([ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]])
            json.dump({"text": text, "words": words}, open(js, "w", encoding="utf-8"), ensure_ascii=False)
            return
        except Exception as e:
            print("retry", i, e); await asyncio.sleep(3 + attempt * 3)
    raise SystemExit("TTS failed on line %d" % i)

async def main():
    for i, t in enumerate(lines):
        await one(i, t); print(i, "ok", flush=True)
asyncio.run(main())
