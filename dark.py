"""Тёмный «киношный» стиль «Что будет, если…» (как вирусные анимации в TikTok/Shorts, ноябрь 2026):
почти чёрный фон со световым пятном, светящиеся цифры и силуэты, крупные слова по центру
по одному-два, жёлтым — слово, которое звучит сейчас. Зритель — герой истории («ты»).

Картинку сцены задаёт поле "dark" (если его нет, берётся "hero"):
  ["count", "1000000", "подпись"]     — огромное светящееся число (числа считаются вверх)
  ["people", 100, 1, "подпись"]       — сетка силуэтов: всего 100, последние 1 — красные
  ["icon", "📱", "подпись"]            — большой эмодзи в светящемся кольце
  ["alert", "ВНИМАНИЕ!", "строка"]    — красная рамка-предупреждение
  ["timer", "00:59", "подпись"]       — цифровой таймер, идёт обратный отсчёт
  ["text"]                            — только слова
Включается полем сценария "style": "dark". Реклама — тот же баннер в середине, что и в drawn.
"""
import os, re, math, random, subprocess
from PIL import Image, ImageDraw, ImageFilter

import engine
import drawn
from engine import font, BLACK, BOLD, emoji_img, text_width, draw_mixed, ease_out, ease_out_back, CTA, CTA_DEFAULT

W, H, FPS = engine.W, engine.H, engine.FPS
BG = (9, 9, 14)
WHITE = (245, 245, 250)
GOLD = (255, 205, 60)
RED = (240, 60, 55)
VIS_Y = 760      # центр картинки сцены
CAP_Y = 1330     # центр крупных слов


def glow(layer, color, radius=18, strength=2):
    """Светящаяся копия слоя под ним."""
    a = layer.split()[3]
    g = Image.new("RGBA", layer.size, color + (0,))
    g.putalpha(a.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, v * strength)))
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(g)
    out.alpha_composite(layer)
    return out


def text_layer(text, size, color, pad=60):
    f = font(BLACK, size)
    tw = int(text_width(text, f))
    im = Image.new("RGBA", (tw + pad * 2, int(size * 1.35) + pad * 2), (0, 0, 0, 0))
    draw_mixed(im, (pad, pad), text, f, color)
    return im


def fit_text(text, size, maxw, color):
    while size > 40 and text_width(text, font(BLACK, size)) > maxw:
        size -= 6
    return text_layer(text, size, color)


def paste_c(fr, img, cx, cy):
    fr.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def scaled(img, s):
    s = max(0.01, s)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BICUBIC)


def faded(img, a):
    if a >= 0.999:
        return img
    im = img.copy()
    im.putalpha(im.split()[3].point(lambda v: int(v * max(0, a))))
    return im


# ---------- фон ----------

def make_bg(tint):
    bg = Image.new("RGBA", (W, H), BG + (255,))
    spot = Image.new("L", (W, H), 0)
    ImageDraw.Draw(spot).ellipse((W / 2 - 620, VIS_Y - 700, W / 2 + 620, VIS_Y + 700), fill=255)
    spot = spot.filter(ImageFilter.GaussianBlur(260))
    col = Image.new("RGBA", (W, H), tint + (0,))
    col.putalpha(spot.point(lambda v: int(v * 0.55)))
    bg.alpha_composite(col)
    return bg


DUST = [(random.Random(i).uniform(0, W), random.Random(i + 99).uniform(0, H),
         random.Random(i + 7).uniform(1.5, 4), random.Random(i + 3).uniform(10, 40)) for i in range(70)]


def draw_dust(fr, t):
    d = ImageDraw.Draw(fr)
    for x, y, r, sp in DUST:
        yy = (y - t * sp) % H
        a = int(60 + 50 * math.sin(t * 1.3 + x))
        d.ellipse((x - r, yy - r, x + r, yy + r), fill=(255, 230, 190, a))


# ---------- картинки сцен ----------

def silhouette(color, h=110):
    w = int(h * 0.62)
    im = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    hr = h * 0.17
    cx = (w + 20) / 2
    d.ellipse((cx - hr, 10, cx + hr, 10 + hr * 2), outline=color, width=5)
    d.rounded_rectangle((cx - w * 0.42, 10 + hr * 2 + 6, cx + w * 0.42, h + 8), int(w * 0.3), outline=color, width=5)
    return glow(im, color, 8, 2)


def kind_of(sc):
    k = sc.get("dark")
    if k:
        return list(k)
    h = sc.get("hero") or ["emoji", "💡", ""]
    if h[0] == "big":
        return ["count", h[1], h[2] if len(h) > 2 else ""]
    if h[0] == "emoji":
        return ["icon", h[1], h[2] if len(h) > 2 else ""]
    return ["icon", "💡", h[2] if len(h) > 2 else ""]


def label(text, color=WHITE):
    return fit_text(text.upper(), 58, 900, color) if text else None


def prep(k, accent):
    P = {"k": k[0], "kind": k}
    kind = k[0]
    if kind == "count":
        P["label"] = label(k[2] if len(k) > 2 else "")
    elif kind == "people":
        total, hot = int(k[1]), int(k[2]) if len(k) > 2 else 0
        P["total"], P["hot"] = total, hot
        n = min(total, 30)
        P["cols"] = n if n <= 5 else 5 if n <= 10 else 10
        P["n"] = n
        sz = 190 if n <= 10 else 110
        P["cold"], P["red"] = silhouette(GOLD, sz), silhouette(RED, sz)
        P["label"] = label(k[3] if len(k) > 3 else "")
    elif kind == "icon":
        P["img"] = emoji_img(k[1], 380)
        ring = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((40, 40, 560, 560), outline=tuple(accent), width=10)
        P["ring"] = glow(ring, tuple(accent), 22, 3)
        P["label"] = label(k[2] if len(k) > 2 else "")
    elif kind == "alert":
        w, h = 900, 520
        pan = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
        ImageDraw.Draw(pan).rounded_rectangle((40, 40, w + 40, h + 40), 30, fill=(40, 6, 8, 235), outline=RED, width=8)
        pan = glow(pan, RED, 26, 2)
        tl = fit_text(k[1].upper(), 130, w - 80, WHITE)
        paste_c(pan, glow(tl, RED, 12, 1), pan.width / 2, 40 + h * 0.33)
        if len(k) > 2 and k[2]:
            sub = fit_text(k[2].upper(), 80, w - 80, WHITE)
            paste_c(pan, sub, pan.width / 2, 40 + h * 0.7)
        P["img"] = pan
    elif kind == "timer":
        P["label"] = label(k[2] if len(k) > 2 else "")
    return P


def fmt_num(v, like):
    s = str(v)
    if " " in like:  # «1 000 000» — разряды через пробел, как в исходной строке
        s = "{:,}".format(v).replace(",", " ")
    return s


def draw_scene(fr, P, lt, t, first):
    k = P["k"]
    pop = 1.0 if first else ease_out_back(min(1, lt / 0.3))
    if k == "count":
        txt = str(P["kind"][1])
        digits = txt.replace(" ", "")
        shown = txt
        if re.fullmatch(r"\d{1,10}", digits) and not first and not re.fullmatch(r"(19|20)\d\d", digits):
            v = int(digits)
            shown = fmt_num(int(v * ease_out(min(1, lt / 1.1))), txt)
        layer = glow(fit_text(shown, 280, 960, GOLD), GOLD, 26, 2)
        paste_c(fr, scaled(layer, 0.75 + 0.25 * pop), W / 2, VIS_Y - 60)
        if P["label"] is not None:
            paste_c(fr, faded(P["label"], 1 if first else ease_out(lt / 0.35)), W / 2, VIS_Y + 160)
    elif k == "people":
        n, cols = P["n"], P["cols"]
        hot = min(P["hot"], n)
        cw, ch = P["cold"].width * 0.95, P["cold"].height * 1.02
        rows = (n + cols - 1) // cols
        x0 = W / 2 - cw * cols / 2 + cw / 2
        y0 = VIS_Y - ch * rows / 2 + ch / 2 - 40
        for i in range(n):
            r, c = divmod(i, cols)
            ap = 1 if first else ease_out_back(min(1, max(0, lt * 12 - i * 0.35) / 1.2))
            if ap <= 0.01:
                continue
            red = i >= n - hot
            img = P["red"] if red else P["cold"]
            if red and lt > 0.8:
                img = faded(img, 0.55 + 0.45 * abs(math.sin(t * 5)))
            paste_c(fr, scaled(img, ap), x0 + c * cw, y0 + r * ch)
        if P["label"] is not None:
            paste_c(fr, faded(P["label"], 1 if first else ease_out(lt / 0.35)), W / 2, y0 + rows * ch - ch / 2 + 90)
    elif k == "icon":
        s = 1 + 0.04 * math.sin(t * 3)
        paste_c(fr, scaled(P["ring"], (0.8 + 0.2 * pop) * s), W / 2, VIS_Y - 40)
        paste_c(fr, scaled(P["img"], 0.6 + 0.4 * pop), W / 2, VIS_Y - 40 + 8 * math.sin(t * 2.2))
        if P["label"] is not None:
            paste_c(fr, faded(P["label"], 1 if first else ease_out(lt / 0.35)), W / 2, VIS_Y + 300)
    elif k == "alert":
        sh = 0 if first or lt > 0.4 else 14 * math.sin(lt * 60) * (1 - lt / 0.4)
        paste_c(fr, scaled(P["img"], 0.85 + 0.15 * pop), W / 2 + sh, VIS_Y - 40)
    elif k == "timer":
        m = re.fullmatch(r"(\d+):(\d\d)", str(P["kind"][1]))
        txt = str(P["kind"][1])
        if m:
            sec = max(0, int(m.group(1)) * 60 + int(m.group(2)) - (0 if first else int(lt * 3)))
            txt = "%02d:%02d" % divmod(sec, 60)
        layer = glow(fit_text(txt, 260, 960, RED), RED, 24, 2)
        paste_c(fr, layer, W / 2, VIS_Y - 60)
        if P["label"] is not None:
            paste_c(fr, P["label"], W / 2, VIS_Y + 150)


# ---------- крупные слова по центру ----------

def chunks(text):
    out, cur = [], []
    for w in text.split():
        cur.append(w)
        if len(cur) >= 2 or len(" ".join(cur)) >= 13 or re.search(r"[.,:!?»…—]$", w):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def captions(sc):
    ch = chunks(re.sub(r"\s*[👇👆]+", "", sc["show"]))
    L = sum(len(w) + 2 for c in ch for w in c) or 1
    dur = sc["voice_end"] - sc["start"]
    t, caps = sc["start"], []
    for c in ch:
        ws = []
        for w in c:
            dd = dur * (len(w) + 2) / L
            ws.append((t, t + dd, w)); t += dd
        caps.append((ws[0][0], ws[-1][1], ws))
    return caps


def draw_caption(fr, cap, t, first):
    words = cap[2]
    size = 118
    f = font(BLACK, size)
    full = " ".join(w.upper() for _, _, w in words)
    while text_width(full, f) > 980 and size > 60:
        size -= 6; f = font(BLACK, size)
    sp = f.getlength(" ")
    ws = [(a, b, w.upper(), text_width(w.upper(), f)) for a, b, w in words]
    ws = [x for x in ws if t >= (0 if first and cap[0] < 0.5 else x[0] - 0.05)]  # центрируем только уже сказанные слова
    tot = sum(x[3] for x in ws) + sp * (len(ws) - 1)
    x = (W - tot) / 2
    for a, b, w, ww in ws:
        vis = 0 if first and cap[0] < 0.5 else a - 0.05
        if t >= vis:
            p = min(1, (t - vis) / 0.12)
            on = a <= t < b
            col = GOLD if on else WHITE
            lay = text_layer(w, size, col, pad=30)
            if on:
                lay = glow(lay, GOLD, 16, 1)
            s = 0.8 + 0.2 * ease_out_back(p)
            lay = scaled(lay, s)
            fr.alpha_composite(lay, (int(x + ww / 2 - lay.width / 2), int(CAP_Y - lay.height / 2)))
        x += ww + sp


# ---------- сборка ----------

def build(v, out_path, work):
    os.makedirs(work, exist_ok=True)
    CTA.clear(); CTA.update(CTA_DEFAULT, **(v.get("cta") or {}))
    accent = tuple(v.get("accent") or (255, 120, 60))
    v = drawn.place_banner(v)
    timeline, total, wav_path = engine.make_audio(v, work)
    kinds = [["banner"] if sc.get("banner") else kind_of(sc) for sc in timeline]
    preps = [None if k[0] == "banner" else prep(k, accent) for k in kinds]
    bgs = {}
    for sc in timeline:
        sc["caps"] = captions(sc)

    brand = drawn.label_pill("НЕ ЗНАЛ?", dark=True)

    ff = subprocess.Popen([
        engine.FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-", "-i", wav_path, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-shortest", "-movflags", "+faststart", out_path],
        stdin=subprocess.PIPE)

    frozen, last_fr, first_fr = None, None, None
    for fi in range(int(total * FPS)):
        t = fi / FPS
        si = next((i for i, sc in enumerate(timeline) if sc["start"] - (0.2 if i == 0 else 0) <= t < sc["end"]),
                  len(timeline) - 1)
        sc = timeline[si]
        lt = t - sc["start"]
        first = si == 0
        if sc.get("banner"):
            if frozen is None:
                fz = (last_fr or make_bg(accent)).filter(ImageFilter.GaussianBlur(6))
                fz.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 150)))
                frozen = fz
            fr = Image.new("RGBA", (W, H))
            drawn.draw_banner(fr, frozen, lt, sc["end"] - sc["start"], t)
            ff.stdin.write(fr.convert("RGB").tobytes())
            continue
        frozen = None
        tint = RED if kinds[si][0] in ("alert", "timer") or (kinds[si][0] == "people" and kinds[si][2]) else accent
        tint = tuple(int(c * 0.45) for c in tint)
        if tint not in bgs:
            bgs[tint] = make_bg(tint)
        fr = bgs[tint].copy()
        draw_dust(fr, t)
        draw_scene(fr, preps[si], lt, t, first)

        ci = next((i for i, c in enumerate(sc["caps"]) if c[0] <= t < c[1]), 0)
        z = 1.0 + 0.04 * min(1.0, lt / max(0.5, sc["end"] - sc["start"])) + (0.05 if ci % 2 else 0)
        if z > 1.002:
            zw, zh = int(W * z), int(H * z)
            big = fr.resize((zw, zh), Image.BILINEAR)
            fr = big.crop(((zw - W) // 2, (zh - H) // 2, (zw - W) // 2 + W, (zh - H) // 2 + H))
        if si and lt < 0.1:  # склейка: короткая вспышка в чёрное
            fr.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(220 * (1 - lt / 0.1)))))

        fr.alpha_composite(brand, (60, 110))
        d = ImageDraw.Draw(fr)
        d.rounded_rectangle((60, 1880, W - 60, 1888), 4, fill=(50, 50, 60))
        d.rounded_rectangle((60, 1880, 60 + int((W - 120) * t / total), 1888), 4, fill=GOLD)

        cap = next((c for c in sc["caps"] if c[0] <= t < c[1]), None)
        if cap is None and sc["caps"] and sc["caps"][-1][0] <= t < sc["voice_end"] + 0.25:
            cap = sc["caps"][-1]
        if cap is None and first and sc["caps"]:
            cap = sc["caps"][0]
        if cap:
            draw_caption(fr, cap, t, first)
        if fi == 0:
            first_fr = fr.copy()
        left = total - t
        if left < 0.3 and fi > 0:  # петля: конец плавно переходит в первый кадр
            fr = Image.blend(fr, first_fr, 1 - left / 0.3)
        last_fr = fr.copy()
        ff.stdin.write(fr.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()
    if ff.returncode != 0:
        raise RuntimeError("ffmpeg не смог собрать видео")
    engine.finish(out_path)
    return out_path, total
