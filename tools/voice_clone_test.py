"""Проба: голос Enceladus (Gemini) перекрашивается в голос владельца канала (OpenVoice v2, без обучения).
Записи владельца лежат в voiceclone/ref.tar.enc (зашифрованы ключом VOICE_KEY, репозиторий публичный).
Результат: samples/voice/*.mp3 — исходник и перекрашенный вариант."""
import os, sys, glob, subprocess, wave
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine

OUT = "samples/voice"
os.makedirs(OUT, exist_ok=True)
TEXTS = [
    "Как пятнадцатилетний школьник заставил НАСА выключить компьютеры на три недели?",
    "В тысяча девятьсот девяносто девятом году Джонатан Джеймс из Флориды залез на сервер военного агентства США.",
    "Кстати, нужен телеграм-бот или сайт? Сделаю под ключ, быстро и недорого. Ищи в Телеграме Портфолио Хаззер бот.",
]


def save(a, sr, path):
    a = np.clip(a, -1, 1)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((a * 32767).astype(np.int16).tobytes())


pre = engine.tts_gemini_all(TEXTS)
if not pre:
    sys.exit("Gemini TTS не ответил")
parts, sr = [], pre[0][1]
for a, s in pre:
    parts += [a, np.zeros(int(0.35 * s))]
src = os.path.join("work", "src.wav"); os.makedirs("work", exist_ok=True)
save(np.concatenate(parts), sr, src)
src22 = "work/src22.wav"
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-ar", "22050", "-ac", "1", src22], check=True)

import torch, types
# водяной знак OpenVoice не нужен: подменяем модуль wavmark заглушкой, модель знака = None
_wm = types.ModuleType("wavmark")
_wm.load_model = lambda: types.SimpleNamespace(to=lambda dev: None)
sys.modules["wavmark"] = _wm
from openvoice.api import ToneColorConverter
conv = ToneColorConverter("ckpt/converter/config.json", device="cpu")
conv.watermark_model = None
conv.load_ckpt("ckpt/converter/checkpoint.pth")
refs = sorted(glob.glob("work/ref/*.wav"))
tgt = conv.extract_se(refs)
srcse = conv.extract_se([src22])
for tau in (0.3, 0.5):
    out = "work/conv_%s.wav" % tau
    conv.convert(audio_src_path=src22, src_se=srcse, tgt_se=tgt, output_path=out, tau=tau)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", out, "-af", "loudnorm=I=-16:TP=-1.5", "-b:a", "128k",
                    "%s/твой-голос-tau%s.mp3" % (OUT, tau)], check=True)
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src22, "-af", "loudnorm=I=-16:TP=-1.5", "-b:a", "128k",
                "%s/исходник-Enceladus.mp3" % OUT], check=True)
print("готово:", os.listdir(OUT))
