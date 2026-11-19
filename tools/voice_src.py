"""Исходник для пробы клонирования: фразы канала голосом Enceladus (Gemini) -> work/src.wav"""
import os, sys, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine
TEXTS = [
    "Как пятнадцатилетний школьник заставил НАСА выключить компьютеры на три недели?",
    "В тысяча девятьсот девяносто девятом году Джонатан Джеймс из Флориды залез на сервер военного агентства США.",
    "Кстати, нужен телеграм-бот или сайт? Сделаю под ключ, быстро и недорого. Ищи в Телеграме Портфолио Хаззер бот.",
]
pre = engine.tts_gemini_all(TEXTS)
if not pre:
    sys.exit("Gemini TTS не ответил")
sr = pre[0][1]
a = np.concatenate([np.concatenate([x, np.zeros(int(0.35 * s))]) for x, s in pre])
os.makedirs("work", exist_ok=True)
with wave.open("work/src.wav", "wb") as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
    wf.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
print("src.wav", len(a) / sr, "с")
