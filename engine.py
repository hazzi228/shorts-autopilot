import sys, os, re, math, wave, subprocess, random, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = os.path.dirname(os.path.abspath(__file__))
try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"

W, H, FPS = 1080, 1920, 30
SR = 22050
FONT_DIR = os.path.join(S, "fonts")
BLACK = os.path.join(FONT_DIR, "Roboto-Black.ttf")
BOLD = os.path.join(FONT_DIR, "Roboto-Bold.ttf")
MED = os.path.join(FONT_DIR, "Roboto-Medium.ttf")
SERIF = os.path.join(FONT_DIR, "DejaVuSerif.ttf")
SERIF_B = os.path.join(FONT_DIR, "DejaVuSerif-Bold.ttf")
EMOJI = os.path.join(FONT_DIR, "NotoColorEmoji.ttf")
VOICE = os.path.join(S, "voice", "ru_RU-dmitri-medium.onnx")
HANDLE = "@PortfolioHazzer_bot"

_fonts = {}
def font(path, size):
    k = (path, size)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(path, size)
    return _fonts[k]

_emoji_cache = {}
def emoji_img(e, size):
    k = (e, size)
    if k not in _emoji_cache:
        f = ImageFont.truetype(EMOJI, 109)
        im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((8, 8), e, font=f, embedded_color=True)
        im = im.crop(im.getbbox())
        r = size / max(im.size)
        _emoji_cache[k] = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
    return _emoji_cache[k]

# ---------- mixed text (text + emoji) ----------
def is_emoji_cp(c):
    o = ord(c)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF or o in (0x231A, 0x231B, 0x23F3, 0x23F0)

def runs(text):
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if is_emoji_cp(c):
            j = i + 1
            while j < len(text) and (text[j] in "️‍" or (j > 0 and text[j - 1] == "‍")):
                j += 1
            out.append(("e", text[i:j]))
            i = j
        else:
            j = i
            while j < len(text) and not is_emoji_cp(text[j]):
                j += 1
            out.append(("t", text[i:j]))
            i = j
    return out

def text_width(text, f):
    w = 0
    for kind, s in runs(text):
        w += int(f.size * 1.05) if kind == "e" else f.getlength(s)
    return w

def draw_mixed(im, xy, text, f, fill, stroke=0, stroke_fill=(0, 0, 0)):
    x, y = xy
    d = ImageDraw.Draw(im)
    asc, desc = f.getmetrics()
    for kind, s in runs(text):
        if kind == "e":
            e = emoji_img(s, int(f.size * 0.95))
            im.alpha_composite(e, (int(x + f.size * 0.05), int(y + (asc + desc - e.height) / 2)))
            x += int(f.size * 1.05)
        else:
            d.text((x, y), s, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            x += f.getlength(s)

def wrap(text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if text_width(t, f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines

def ease_out_back(t):
    t = min(max(t, 0), 1)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

def ease_out(t):
    t = min(max(t, 0), 1)
    return 1 - (1 - t) ** 3

def rounded_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=255)
    return m

def glow(im, color, radius=30, strength=1.0):
    """Return image with colored glow behind alpha shape."""
    pad = radius * 2
    base = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    a = im.split()[3]
    sh = Image.new("RGBA", im.size, color + (0,))
    sh.putalpha(a.point(lambda v: int(v * 0.8 * strength)))
    base.alpha_composite(sh, (pad, pad))
    base = base.filter(ImageFilter.GaussianBlur(radius))
    base.alpha_composite(im, (pad, pad))
    return base

# ---------- screenshots ----------
def phone(im, accent, max_h=1050, max_w=700):
    r = min(max_h / im.height, max_w / im.width)
    sc = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS).convert("RGBA")
    border = 14
    ph = Image.new("RGBA", (sc.width + border * 2, sc.height + border * 2), (0, 0, 0, 0))
    ImageDraw.Draw(ph).rounded_rectangle((0, 0, ph.width - 1, ph.height - 1), 48, fill=(20, 22, 30, 255), outline=accent + (255,), width=4)
    sc.putalpha(rounded_mask(sc.size, 36))
    ph.alpha_composite(sc, (border, border))
    return glow(ph, accent, 40, 0.7)

# ---------- hero builders ----------
def hero_big(text, sub, accent):
    size = 330
    f = font(BLACK, size)
    while f.getlength(text) > 920:
        size -= 10
        f = font(BLACK, size)
    tw = int(f.getlength(text))
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (tw + 20, asc + desc + 10), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 0), text, font=f, fill=(255, 255, 255))
    # градиент заливки
    grad = Image.new("RGBA", im.size)
    gd = ImageDraw.Draw(grad)
    for yy in range(im.height):
        t = yy / im.height
        c = tuple(int(255 * (1 - t) + accent[i] * t) for i in range(3))
        gd.line([(0, yy), (im.width, yy)], fill=c + (255,))
    grad.putalpha(im.split()[3])
    g = glow(grad, accent, 35, 1.0)
    if not sub:
        return g
    fs = font(BOLD, 56)
    lines = wrap(sub, fs, 900)
    sh = 70 * len(lines)
    out = Image.new("RGBA", (max(g.width, 960), g.height + sh + 10), (0, 0, 0, 0))
    out.alpha_composite(g, ((out.width - g.width) // 2, 0))
    y = g.height - 40
    for ln in lines:
        lw = text_width(ln, fs)
        draw_mixed(out, (int((out.width - lw) / 2), y), ln, fs, (210, 214, 230))
        y += 70
    return out

def hero_emoji(e, sub, accent):
    em = emoji_img(e, 380)
    disc = Image.new("RGBA", (560, 560), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse((0, 0, 559, 559), fill=accent + (60,))
    disc = disc.filter(ImageFilter.GaussianBlur(30))
    disc.alpha_composite(em, ((560 - em.width) // 2, (560 - em.height) // 2))
    if not sub:
        return disc
    fs = font(BOLD, 58)
    lines = wrap(sub, fs, 900)
    out = Image.new("RGBA", (960, 560 + 80 * len(lines)), (0, 0, 0, 0))
    out.alpha_composite(disc, ((960 - 560) // 2, 0))
    y = 560
    for ln in lines:
        lw = text_width(ln, fs)
        draw_mixed(out, (int((960 - lw) / 2), y), ln, fs, (225, 228, 240))
        y += 80
    return out

def bubble(text, mine, accent):
    f = font(MED, 54)
    lines = wrap(text, f, 600)
    w = int(max(text_width(l, f) for l in lines)) + 70
    h = 70 * len(lines) + 50
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    col = accent + (255,) if mine else (44, 48, 64, 255)
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), 36, fill=col)
    y = 22
    for l in lines:
        draw_mixed(im, (35, y), l, f, (255, 255, 255))
        y += 70
    return im

def hero_oldweb():
    im = Image.new("RGBA", (900, 760), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 899, 56), fill=(205, 205, 205))
    d.text((24, 12), "http://info.cern.ch/hypertext/WWW/TheProject.html", font=font(SERIF, 24), fill=(40, 40, 40))
    d.text((40, 90), "World Wide Web", font=font(SERIF_B, 64), fill=(0, 0, 0))
    body = ("The WorldWideWeb (W3) is a wide-area hypermedia information retrieval initiative "
            "aiming to give universal access to a large universe of documents.")
    f = font(SERIF, 34)
    y = 200
    for ln in wrap(body, f, 820):
        d.text((40, y), ln, font=f, fill=(0, 0, 0)); y += 48
    y += 20
    for link in ["What's out there?", "Help", "Software Products", "Technical", "Bibliography", "People"]:
        d.text((40, y), link, font=f, fill=(0, 0, 238))
        lw = f.getlength(link)
        d.line((40, y + 42, 40 + lw, y + 42), fill=(0, 0, 238), width=2)
        y += 56
    im.putalpha(rounded_mask(im.size, 24))
    return glow(im, (0, 200, 255), 40, 0.6)

def hero_sticker():
    im = Image.new("RGBA", (820, 820), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((60, 60, 760, 760), 30, fill=(22, 22, 24), outline=(70, 70, 76), width=6)
    d.text((110, 690), "NeXT", font=font(BLACK, 44), fill=(90, 90, 96))
    st = Image.new("RGBA", (560, 300), (250, 248, 236, 255))
    sd = ImageDraw.Draw(st)
    sd.text((30, 30), "This machine is a server.", font=font(BOLD, 36), fill=(30, 30, 30))
    sd.text((30, 100), "DO NOT", font=font(BLACK, 76), fill=(210, 20, 20))
    sd.text((30, 185), "POWER IT DOWN!!", font=font(BLACK, 62), fill=(210, 20, 20))
    st = st.rotate(-6, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(st, ((820 - st.width) // 2, 230))
    return glow(im, (0, 200, 255), 40, 0.4)

def hero_cta(accent):
    w, h = 940, 830
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 56, fill=(18, 20, 30, 235), outline=accent + (255,), width=4)
    d.text((60, 60), "Hazzer", font=font(BLACK, 96), fill=(255, 255, 255))
    y = 180
    for ln in wrap("Telegram-боты и сайты под ключ", font(BOLD, 60), 820):
        d.text((60, y), ln, font=font(BOLD, 60), fill=accent); y += 72
    y += 30
    for item in ["Оплата: СБП, карта, крипта", "Личный кабинет и админ-панель", "От идеи до запуска", "Приятная цена"]:
        d.ellipse((60, y + 12, 96, y + 48), fill=accent)
        d.line((69, y + 30, 76, y + 38), fill=(255, 255, 255), width=5)
        d.line((76, y + 38, 89, y + 22), fill=(255, 255, 255), width=5)
        d.text((120, y), item, font=font(MED, 48), fill=(230, 232, 240)); y += 76
    y += 20
    x = 60
    for _ in range(5):
        e = emoji_img("⭐", 58); im.alpha_composite(e, (x, y)); x += 66
    d.text((x + 16, y + 4), "отзывы клиентов", font=font(MED, 44), fill=(200, 204, 220))
    return im, y + 100

def cta_button(accent, pulse):
    label = "✈  " + HANDLE
    size = 84
    f = font(BLACK, size)
    while text_width(label, f) > 760:
        size -= 2; f = font(BLACK, size)
    tw = text_width(label, f)
    bw, bh = int(tw + 120), 150
    b = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    ImageDraw.Draw(b).rounded_rectangle((0, 0, bw - 1, bh - 1), 75, fill=accent + (255,))
    draw_mixed(b, (60, (bh - sum(f.getmetrics())) // 2), label, f, (255, 255, 255))
    if pulse != 1:
        b = b.resize((int(bw * pulse), int(bh * pulse)), Image.LANCZOS)
    return b

REVIEWS = [
    ("Заказчик · бот для продажи VPN", "Все сделал по красоте, молодец."),
    ("Заказчик · бот для продажи VPN", "Продавец супер! Сделал отличного бота, очень терпеливый, всё детально объяснил и переделал мелкие недочеты. Однозначно лучший исполнитель, рекомендую!"),
]

def review_card(who, text, accent, letter):
    w = 940
    f = font(MED, 46)
    lines = wrap("«" + text + "»", f, w - 120)
    h = 250 + 62 * len(lines)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 44, fill=(24, 27, 38, 245), outline=accent + (200,), width=3)
    d.ellipse((50, 45, 140, 135), fill=accent)
    lw = font(BLACK, 50).getlength(letter)
    d.text((95 - lw / 2, 58), letter, font=font(BLACK, 50), fill=(255, 255, 255))
    d.text((165, 50), "Отзыв клиента", font=font(BOLD, 44), fill=(255, 255, 255))
    d.text((165, 102), who, font=font(MED, 34), fill=(170, 176, 196))
    stars = []
    x = 50
    for i in range(5):
        stars.append((x, 160)); x += 62
    y = 230
    for ln in lines:
        d.text((60, y), ln, font=f, fill=(232, 234, 242)); y += 62
    return im, stars

def draw_review(fr, card, stars, x, y, lt):
    fr.alpha_composite(card, (x, y))
    for i, (sx, sy) in enumerate(stars):
        p = ease_out_back((lt - 0.3 - i * 0.12) / 0.3)
        if p <= 0:
            continue
        e = emoji_img("⭐", max(4, int(54 * p)))
        fr.alpha_composite(e, (x + sx + (54 - e.width) // 2, y + sy + (54 - e.height) // 2))

def hero_timer(t, accent):
    sz = 700
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((30, 30, sz - 30, sz - 30), outline=(60, 64, 80), width=28)
    frac = max(0.0, 1 - t / 3.0)
    if frac > 0:
        d.arc((30, 30, sz - 30, sz - 30), -90, -90 + 360 * frac, fill=accent, width=28)
    n = str(max(0, math.ceil(3 - t))) if t < 3 else "0"
    f = font(BLACK, 300)
    tw = f.getlength(n)
    asc, desc = f.getmetrics()
    d.text(((sz - tw) / 2, (sz - asc - desc) / 2 - 10), n, font=f, fill=(255, 255, 255))
    fs = font(BOLD, 52)
    lw = fs.getlength("секунды")
    d.text(((sz - lw) / 2, sz / 2 + 140), "секунды", font=fs, fill=(200, 204, 220))
    return glow(im, accent, 30, 0.6)

# ---------- audio ----------
# Нейронный голос Microsoft (edge-tts). Если сервис не ответил, весь остаток ролика озвучивает Piper (Дмитрий).
EDGE_VOICE = os.environ.get("EDGE_VOICE", "de-DE-FlorianMultilingualNeural")
EDGE_RATE = os.environ.get("EDGE_RATE", "+5%")
_edge_off = not EDGE_VOICE


def tts_edge(text, path):
    import asyncio, edge_tts
    mp3 = path.replace(".wav", "_edge.mp3")
    last = None
    for attempt in range(3):
        try:
            asyncio.run(edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE).save(mp3))
            if os.path.getsize(mp3) > 2000:
                break
            last = RuntimeError("пустой ответ")
        except Exception as e:
            last = e
        time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError("edge-tts: %s" % last)
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", mp3, "-af", "highpass=f=70",
                    "-ar", str(SR), "-ac", "1", path], check=True)


def tts(text, path):
    global _edge_off
    if not _edge_off:
        try:
            tts_edge(text, path)
            return read_voice(path)
        except Exception as e:
            print("Нейроголос недоступен (%s), озвучиваю Дмитрием" % e)
            _edge_off = True
    return tts_piper(text, path)


def read_voice(path):
    with wave.open(path, "rb") as wf:
        a = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        sr = wf.getframerate()
    # обрезаем тишину по краям
    nz = np.where(np.abs(a) > 0.01)[0]
    if len(nz):
        a = a[max(0, nz[0] - 200): nz[-1] + 1500]
    return a, sr


def tts_piper(text, path):
    from piper import PiperVoice, SynthesisConfig
    global _voice
    try:
        _voice
    except NameError:
        _voice = PiperVoice.load(VOICE)
    cfg = SynthesisConfig(length_scale=1.07, noise_scale=0.667, noise_w_scale=0.8)
    with wave.open(path, "wb") as wf:
        _voice.synthesize_wav(text, wf, syn_config=cfg)
    # только лёгкая чистка, без эха (эхо давало "металлический" звук)
    proc = path.replace(".wav", "_fx.wav")
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", path, "-af",
                    "highpass=f=80,equalizer=f=300:t=q:w=1:g=-2,equalizer=f=3000:t=q:w=1.5:g=1.5",
                    
                    "-ar", "22050", "-ac", "1", proc], check=True)
    return read_voice(proc)

def music(dur, sr, seed):
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur * sr)) / sr
    out = np.zeros_like(t)
    bpm = 88
    beat = 60 / bpm
    bar = beat * 4
    # Am  F  C  G
    prog = [[57, 60, 64], [53, 57, 60], [48, 55, 60, 64], [55, 59, 62]]
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    nb = int(dur / bar) + 1
    for b in range(nb):
        ch = prog[b % 4]
        s0 = int(b * bar * sr)
        n = int(bar * sr)
        tt = np.arange(n) / sr
        env = np.minimum(1, tt / 0.6) * np.minimum(1, (bar - tt) / 0.4)
        pad = sum(np.sin(2 * np.pi * hz(m) * tt) + 0.3 * np.sin(2 * np.pi * hz(m) * 2 * tt + 0.5) for m in ch)
        bass = np.sin(2 * np.pi * hz(ch[0] - 12) * tt) * 1.2
        seg = (pad * 0.12 + bass * 0.18) * env
        # арпеджио восьмыми
        for k in range(8):
            m = ch[k % len(ch)] + 12 + (12 if k in (3, 7) else 0)
            ns = int(k * beat / 2 * sr)
            ln = int(beat / 2 * sr * 1.6)
            ta = np.arange(min(ln, n - ns)) / sr
            seg[ns:ns + len(ta)] += np.sin(2 * np.pi * hz(m) * ta) * np.exp(-ta * 14) * 0.07
        # мягкая бочка и хэт
        for k in range(4):
            ns = int(k * beat * sr)
            if k in (0, 2):
                ta = np.arange(int(0.25 * sr)) / sr
                f = 110 * np.exp(-ta * 20) + 45
                kick = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-ta * 14) * 0.35
                seg[ns:ns + len(kick)] += kick[: max(0, n - ns)]
            hs = int((k * beat + beat / 2) * sr)
            ta = np.arange(int(0.05 * sr)) / sr
            hat = rng.standard_normal(len(ta)) * np.exp(-ta * 80) * 0.03
            seg[hs:hs + len(hat)] += hat[: max(0, n - hs)]
        e = min(len(out), s0 + n)
        out[s0:e] += seg[: e - s0]
    # простой лоупасс
    k = np.ones(6) / 6
    out = np.convolve(out, k, mode="same")
    fade = int(1.5 * sr)
    out[-fade:] *= np.linspace(1, 0, fade)
    out[:int(0.5 * sr)] *= np.linspace(0, 1, int(0.5 * sr))
    return out / (np.abs(out).max() + 1e-9)

def whoosh(sr):
    n = int(0.5 * sr)
    rng = np.random.default_rng(1)
    x = rng.standard_normal(n)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    # фильтр с плывущей частотой: скользящее среднее разной длины
    y = np.convolve(x, np.ones(8) / 8, mode="same")
    return y * env * 0.12

# ---------- captions ----------
def chunk_caption(text):
    words = text.split()
    chunks, cur = [], []
    for w_ in words:
        cur.append(w_)
        ln = len(" ".join(cur))
        if ln >= 16 or len(cur) >= 4 or re.search(r"[.,:!?»…]$", w_):
            chunks.append(" ".join(cur)); cur = []
    if cur:
        if chunks and len(" ".join(cur)) < 6:
            chunks[-1] += " " + " ".join(cur)
        else:
            chunks.append(" ".join(cur))
    return chunks

# ---------- main ----------
def build(v, out_path, work):
    os.makedirs(work, exist_ok=True)
    accent = tuple(v["accent"])
    GAP = 0.32
    audio_parts, timeline, t = [], [], 0.5
    sr = SR
    for i, sc in enumerate(v["scenes"]):
        a, sr = tts(sc["say"], os.path.join(work, "s%02d.wav" % i))
        d = len(a) / sr
        gap = GAP + (0.25 if (sc.get("ad") != v["scenes"][min(i + 1, len(v["scenes"]) - 1)].get("ad")) else 0)
        timeline.append(dict(sc, start=t, voice_end=t + d, end=t + d + gap))
        audio_parts.append((t, a))
        t += d + gap
    total = t + 0.8
    timeline[-1]["end"] = total
    n = int(total * sr)
    voice = np.zeros(n)
    for st, a in audio_parts:
        s0 = int(st * sr); voice[s0:s0 + len(a)] += a
    voice = voice / (np.abs(voice).max() + 1e-9) * 0.92
    mus = music(total, sr, 7)
    # ducking
    env = np.convolve(np.abs(voice), np.ones(int(0.3 * sr)) / int(0.3 * sr), mode="same")
    duck = 1 - 0.55 * np.clip(env / 0.05, 0, 1)
    mix = voice + mus * 0.12 * duck
    # whoosh на входе и выходе из рекламы
    wh = whoosh(sr)
    for i, sc in enumerate(timeline):
        prev_ad = timeline[i - 1].get("ad") if i else None
        if i and bool(sc.get("ad")) != bool(prev_ad):
            s0 = max(0, int((sc["start"] - 0.3) * sr)); mix[s0:s0 + len(wh)] += wh[: n - s0]
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.95
    wav_path = os.path.join(work, "mix.wav")
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((mix * 32767).astype(np.int16).tobytes())

    # подготовка визуала
    shots = {}
    phones = {}
    heroes = []
    for sc in timeline:
        h = sc["hero"]
        if h[0] == "big":
            heroes.append(hero_big(h[1], h[2], accent))
        elif h[0] == "emoji":
            heroes.append(hero_emoji(h[1], h[2], accent))
        elif h[0] == "oldweb":
            heroes.append(hero_oldweb())
        elif h[0] == "sticker":
            heroes.append(hero_sticker())
        elif h[0] == "chat":
            heroes.append(None)
        elif h[0] == "reviews":
            heroes.append([review_card(REVIEWS[0][0], REVIEWS[0][1], accent, "N"),
                           review_card(REVIEWS[1][0], REVIEWS[1][1], accent, "Ю")])
        elif h[0] == "cta":
            heroes.append(hero_cta(accent))
        else:
            heroes.append(None)
        # субтитры
        ch = chunk_caption(sc["show"])
        L = sum(len(c) + 3 for c in ch)
        dur = sc["voice_end"] - sc["start"]
        tt, caps = sc["start"], []
        for c in ch:
            dd = dur * (len(c) + 3) / L
            caps.append((tt, tt + dd, c)); tt += dd
        sc["caps"] = caps
    chat_bubbles = None
    for sc in timeline:
        if sc["hero"][0] == "chat":
            chat_bubbles = [bubble(sc["hero"][1][0], True, accent), bubble(sc["hero"][1][1], False, accent)]

    # фон
    bg = Image.new("RGBA", (W, H))
    bd = ImageDraw.Draw(bg)
    for y in range(H):
        tt = y / H
        c = tuple(int(10 + (accent[i] * 0.18) * tt) for i in range(3))
        bd.line([(0, y), (W, y)], fill=c + (255,))
    grid = Image.new("RGBA", (W, H + 120), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, W, 120):
        gd.line([(x, 0), (x, H + 120)], fill=(255, 255, 255, 10), width=2)
    for y in range(0, H + 120, 120):
        gd.line([(0, y), (W, y)], fill=(255, 255, 255, 10), width=2)
    blob = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
    ImageDraw.Draw(blob).ellipse((150, 150, 750, 750), fill=accent + (90,))
    blob = blob.filter(ImageFilter.GaussianBlur(120))
    blob2 = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
    ImageDraw.Draw(blob2).ellipse((150, 150, 750, 750), fill=(255, 60, 160, 50) if accent[2] > 200 else (60, 140, 255, 50))
    blob2 = blob2.filter(ImageFilter.GaussianBlur(120))

    title_f = font(BOLD, 44)
    cap_f = font(BLACK, 76)
    chip_cache = {}
    def chip(text, col):
        if text not in chip_cache:
            tw = text_width(text, title_f)
            c = Image.new("RGBA", (int(tw + 64), 84), (0, 0, 0, 0))
            ImageDraw.Draw(c).rounded_rectangle((0, 0, c.width - 1, 83), 42, fill=col)
            draw_mixed(c, (32, 14), text, title_f, (255, 255, 255))
            chip_cache[text] = c
        return chip_cache[text]

    ff = subprocess.Popen([
        FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", wav_path, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-shortest", "-movflags", "+faststart", out_path],
        stdin=subprocess.PIPE)

    nframes = int(total * FPS)
    for fi in range(nframes):
        t = fi / FPS
        si = next((i for i, sc in enumerate(timeline) if sc["start"] - (0.5 if i == 0 else 0) <= t < sc["end"]), len(timeline) - 1)
        sc = timeline[si]
        lt = t - sc["start"]
        is_ad = bool(sc.get("ad"))
        fr = bg.copy()
        fr.alpha_composite(grid, (0, -int((t * 30) % 120)))
        fr.alpha_composite(blob, (int(-200 + 160 * math.sin(t * 0.4)), int(300 + 200 * math.cos(t * 0.3))))
        fr.alpha_composite(blob2, (int(400 + 150 * math.cos(t * 0.35)), int(900 + 220 * math.sin(t * 0.27))))

        # прогресс-бар
        d = ImageDraw.Draw(fr)
        d.rectangle((0, 0, W, 10), fill=(255, 255, 255, 40))
        d.rectangle((0, 0, int(W * t / total), 10), fill=accent + (255,))

        # верхняя плашка
        if is_ad:
            c = chip("Портфолио: " + HANDLE, accent + (230,))
        else:
            c = chip(v["title"], (255, 255, 255, 30))
        fr.alpha_composite(c, ((W - c.width) // 2, 130))

        # герой
        hero_cy = 820
        k = sc["hero"][0]
        hero = heroes[si]
        pop = ease_out_back(lt / 0.45)
        fade = min(1, max(0, lt / 0.25))
        float_y = int(12 * math.sin(t * 2.2))
        if k == "timer":
            hero = hero_timer(max(0, lt - 0.2) * 3.0 / max(1.0, (sc["voice_end"] - sc["start"]) * 0.45), accent)
        if hero is not None and k not in ("cta", "reviews"):
            img = hero
            if pop < 0.999 or pop > 1.001:
                s = 0.6 + 0.4 * pop
                img = hero.resize((max(1, int(hero.width * s)), max(1, int(hero.height * s))), Image.BILINEAR)
            if fade < 1:
                img = img.copy(); img.putalpha(img.split()[3].point(lambda a: int(a * fade)))
            fr.alpha_composite(img, ((W - img.width) // 2, hero_cy - img.height // 2 + float_y))
        elif k == "chat":
            if sc["hero"][2]:
                lab = chip(sc["hero"][2], (255, 255, 255, 30))
                fr.alpha_composite(lab, ((W - lab.width) // 2, 420))
            b1, b2 = chat_bubbles
            p1 = ease_out(lt / 0.4)
            if p1 > 0:
                fr.alpha_composite(b1, (W - 80 - b1.width + int(200 * (1 - p1)), 600 + float_y))
            p2 = ease_out((lt - 1.4) / 0.4)
            if lt > 1.4:
                fr.alpha_composite(b2, (80 - int(200 * (1 - p2)), 640 + b1.height + float_y))
            if 0.6 < lt < 1.4:
                dots = Image.new("RGBA", (180, 90), (0, 0, 0, 0))
                dd = ImageDraw.Draw(dots)
                dd.rounded_rectangle((0, 0, 179, 89), 40, fill=(44, 48, 64, 255))
                for j in range(3):
                    a_ = 120 + int(135 * (0.5 + 0.5 * math.sin(t * 8 - j)))
                    dd.ellipse((35 + j * 40, 33, 59 + j * 40, 57), fill=(255, 255, 255, a_))
                fr.alpha_composite(dots, (80, 640 + b1.height + float_y))
        elif k == "reviews":
            (c1, s1), (c2, s2) = hero
            gap = 50
            top = hero_cy - (c1.height + gap + c2.height) // 2 - 40
            p1 = ease_out(lt / 0.45)
            draw_review(fr, c1, s1, (W - c1.width) // 2 + int((1 - p1) * 900), top + float_y, lt)
            p2 = ease_out((lt - 0.9) / 0.45)
            if lt > 0.9:
                draw_review(fr, c2, s2, (W - c2.width) // 2 - int((1 - p2) * 900), top + c1.height + gap + float_y, lt - 0.9)
        elif k == "shots":
            keys = sc["hero"][1]
            dur = sc["end"] - sc["start"]
            per = dur / len(keys)
            idx = min(len(keys) - 1, int(lt / per))
            p = phones[keys[idx]]
            tr = ease_out((lt - idx * per) / 0.35)
            x = (W - p.width) // 2 + int((1 - tr) * 700)
            if idx > 0 and tr < 1:
                q = phones[keys[idx - 1]]
                fr.alpha_composite(q, ((W - q.width) // 2 - int(tr * 900), hero_cy - q.height // 2 + float_y))
            fr.alpha_composite(p, (x, hero_cy - p.height // 2 + float_y))
            tag = chip(shots[keys[idx]][1] + "  ⭐ 5/5", (0, 0, 0, 170))
            fr.alpha_composite(tag, ((W - tag.width) // 2, hero_cy + p.height // 2 - 150 + float_y))
        elif k == "cta":
            card, by = hero
            s = 0.6 + 0.4 * pop
            img = card if abs(s - 1) < 0.001 else card.resize((int(card.width * s), int(card.height * s)), Image.BILINEAR)
            top = hero_cy - 80 - img.height // 2
            fr.alpha_composite(img, ((W - img.width) // 2, top))
            if lt > 0.5:
                btn = cta_button(accent, 1 + 0.05 * math.sin((lt - 0.5) * 6))
                fr.alpha_composite(btn, ((W - btn.width) // 2, top + img.height + 40))

        # субтитры
        cap = next((c for c in sc["caps"] if c[0] <= t < c[1]), None)
        if cap is None and sc["caps"] and t >= sc["caps"][-1][0]:
            cap = sc["caps"][-1] if t < sc["voice_end"] + 0.25 else None
        if cap:
            ct = t - cap[0]
            s = 0.85 + 0.15 * ease_out_back(ct / 0.18)
            f = font(BLACK, max(20, int(76 * s)))
            lines = wrap(" ".join(x if (x.startswith("@") or "." in x[:-1]) else x.upper() for x in cap[2].split()), f, 960)
            y = 1500 - (len(lines) - 1) * 48
            for li, ln in enumerate(lines):
                lw = text_width(ln, f)
                col = (255, 230, 80) if (li == 0 and is_ad) else (255, 255, 255)
                draw_mixed(fr, (int((W - lw) / 2), y), ln, f, col, stroke=8, stroke_fill=(0, 0, 0))
                y += 96
        ff.stdin.write(fr.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()
    if ff.returncode != 0:
        raise RuntimeError("ffmpeg не смог собрать видео")
    final = out_path[:-4] + "_n.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", out_path, "-c:v", "copy", "-af",
                    "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", final], check=True)
    os.replace(final, out_path)
    return out_path, total

