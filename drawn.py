"""Рисованный стиль роликов: светлый «бумажный» фон в точку, плоская графика,
пиксельный маскот канала, карточки-наклейки с белой обводкой, рукописное подчёркивание
и субтитры, которые появляются слово за словом.

Сцена может задать картинку полем "draw" (см. KINDS ниже). Если его нет,
берётся старое поле "hero", так что старые сценарии тоже собираются в этом стиле.

  ["question", "Почему *айфон* тормозит?"]  — заголовок-хук, *слово* подчёркнуто, маскот с «?»
  ["mascot", "📱", "подпись", "hacker"]    — маскот (наряд: hacker / helmet / crown / ""), рядом предмет
  ["card", "🔐", "Заголовок", "подпись"]     — белая карточка интерфейса
  ["big", "2005", "подпись"]                — огромное число / слово с подчёркиванием (числа считаются вверх)
  ["rule", 3, "Текст правила"]              — карточка «ПРАВИЛО №3»
  ["terminal", ["строка", "строка"]]        — тёмное окно терминала, текст печатается
  ["phone", "🔔", "текст уведомления"]       — телефон с всплывающим уведомлением
  ["chat", ["вопрос", "ответ"], "подпись"]  — переписка
  ["emoji", "😲", "подпись"]                 — большая наклейка-эмодзи
  ["cta"]                                   — карточка Telegram-бота с кнопкой (реклама в конце)
"""
import os, re, math, random, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import engine
from engine import font, BLACK, BOLD, MED, emoji_img, text_width, draw_mixed, wrap, ease_out, ease_out_back, CTA, CTA_DEFAULT

W, H, FPS = engine.W, engine.H, engine.FPS
PAPER = (247, 245, 240)
DOT = (214, 210, 202)
INK = (24, 24, 30)
GREY = (128, 128, 140)
RED = (232, 66, 58)
CARD = (255, 255, 255)
MONO = os.path.join(engine.FONT_DIR, "DejaVuSansMono-Bold.ttf")

# ---------- общие приёмы ----------

def sticker(im, border=12, shadow=True):
    """Белая обводка как у наклейки + мягкая тень."""
    pad = border + 30
    big = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    big.alpha_composite(im, (pad, pad))
    a = big.split()[3].point(lambda v: 255 if v > 40 else 0)
    dil = a.filter(ImageFilter.MaxFilter(border * 2 + 1)) if border else a
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", big.size, (40, 30, 20, 0))
        sh.putalpha(dil.point(lambda v: v * 50 // 255).filter(ImageFilter.GaussianBlur(14)))
        out.alpha_composite(sh, (0, 14))
    white = Image.new("RGBA", big.size, (255, 255, 255, 0))
    white.putalpha(dil)
    out.alpha_composite(white)
    out.alpha_composite(big)
    return out.crop(out.getbbox())


def soft_card(w, h, r=44, fill=CARD):
    """Карточка интерфейса: скругление и мягкая тень."""
    pad = 50
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new("L", im.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 16, pad + w, pad + h + 16), r, fill=46)
    sh = sh.filter(ImageFilter.GaussianBlur(20))
    s = Image.new("RGBA", im.size, (40, 30, 20, 0)); s.putalpha(sh)
    im.alpha_composite(s)
    ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + w, pad + h), r, fill=fill + (255,),
                                         outline=(230, 228, 222, 255), width=2)
    return im, pad


def scribble(d, x0, x1, y, p, color=RED, width=12, seed=1):
    """Рукописное подчёркивание, рисуется слева направо (p от 0 до 1)."""
    rnd = random.Random(seed)
    pts, n = [], 40
    ph, amp = rnd.uniform(0, 6), rnd.uniform(4, 8)
    for i in range(n + 1):
        t = i / n
        if t > p:
            break
        x = x0 + (x1 - x0) * t
        yy = y + amp * math.sin(t * 7 + ph) + 10 * (t - 0.5) * rnd.choice((1, -1)) * 0.3
        pts.append((x, yy))
    if len(pts) > 1:
        d.line(pts, fill=color, width=width, joint="curve")
        for q in (pts[0], pts[-1]):
            d.ellipse((q[0] - width / 2, q[1] - width / 2, q[0] + width / 2, q[1] + width / 2), fill=color)


def scaled(img, s):
    if abs(s - 1) < 0.003:
        return img
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BILINEAR)


def faded(img, a):
    if a >= 0.999:
        return img
    img = img.copy()
    img.putalpha(img.split()[3].point(lambda v: int(v * max(0.0, a))))
    return img


def paste_c(fr, img, cx, cy):
    fr.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


# ---------- пиксельный маскот канала ----------
MASCOT = [
    "..LL......RR..",
    ".LLLL....RRRR.",
    ".LLLLLRRRRRRRD",
    "LLLLLLLRRRRRRD",
    "LLEELLLRRREERD",
    "LLEHLLLRRREHRD",
    "LLLLLLLRRRRRRD",
    "LLLLLLMMRRRRRD",
    ".LLLLLLRRRRRD.",
    ".LL.LL..RR.RD.",
]
MC = {"L": (162, 148, 255), "R": (126, 108, 255), "D": (88, 72, 216), "E": (18, 16, 40), "H": (125, 215, 255),
      "M": (18, 16, 40)}
OUTFITS = {
    # строки поверх головы: (строка, столбец, рисунок, цвет)
    "hacker": [(-1, 1, "HHHHHHHHHHHH", (40, 40, 52)), (0, 0, "HHHHHHHHHHHHHH", (40, 40, 52)),
               (1, 0, "HH..........HH", (40, 40, 52)), (2, 0, "H............H", (40, 40, 52)),
               (4, 1, "GGGGGGGGGGGG", (30, 220, 120))],
    "helmet": [(-1, 2, "YYYYYYYYYY", (255, 196, 40)), (0, 1, "YYYYYYYYYYYY", (255, 196, 40)),
               (1, 0, "YYYYYYYYYYYYYY", (232, 160, 20))],
    "crown": [(-2, 3, "Y..Y..Y..", (255, 196, 40)), (-1, 3, "YYYYYYYYY", (255, 196, 40))],
}


def mascot(px=34, blink=False, outfit=""):
    rows = MASCOT
    top = 2
    im = Image.new("RGBA", (14 * px, (len(rows) + top) * px), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            col = MC[ch]
            if blink and ch in "EH":
                col = MC["L"] if c < 7 else MC["R"]
                if r == 5:
                    col = MC["E"]
            d.rectangle((c * px, (r + top) * px, (c + 1) * px - 1, (r + top + 1) * px - 1), fill=col)
    for r, c0, pat, col in OUTFITS.get(outfit, []):
        for i, ch in enumerate(pat):
            if ch != ".":
                d.rectangle(((c0 + i) * px, (r + top) * px, (c0 + i + 1) * px - 1, (r + top + 1) * px - 1), fill=col)
    return im


_mascot_cache = {}


def mascot_sticker(blink, outfit, px=34):
    k = (blink, outfit, px)
    if k not in _mascot_cache:
        _mascot_cache[k] = sticker(mascot(px, blink, outfit), border=14)
    return _mascot_cache[k]


# ---------- текст с выделением ----------

def rich(text):
    """'Почему *айфон* тормозит' -> [(слово, акцент)]"""
    out = []
    for w in text.split():
        acc = w.startswith("*") or w.endswith("*") or "*" in w
        out.append((w.replace("*", ""), acc))
    return out


def headline(text, size=96, maxw=940):
    """Заголовок по центру: акцентные слова красные и подчёркнуты. Возвращает (картинку, список подчёркиваний)."""
    words = rich(text)
    f = font(BLACK, size)
    while True:
        sp = f.getlength(" ")
        lines, cur, cw = [], [], 0
        for w, a in words:
            ww = text_width(w, f)
            if cur and cw + sp + ww > maxw:
                lines.append((cur, cw)); cur, cw = [], 0
            cw += (sp if cur else 0) + ww
            cur.append((w, a, ww))
        if cur:
            lines.append((cur, cw))
        if len(lines) <= 3 or size < 60:
            break
        size -= 6; f = font(BLACK, size)
    lh = int(size * 1.18)
    im = Image.new("RGBA", (maxw + 40, lh * len(lines) + 40), (0, 0, 0, 0))
    unders = []
    y = 0
    for ln, lw in lines:
        x = (im.width - lw) / 2
        for w, a, ww in ln:
            draw_mixed(im, (int(x), y), w, f, RED if a else INK)
            if a:
                unders.append((x - 6, x + ww + 6, y + int(size * 1.08)))
            x += ww + sp
        y += lh
    return im, unders


# ---------- картинки сцен ----------

def kind_of(sc):
    dr = sc.get("draw")
    if dr:
        return list(dr)
    h = sc.get("hero") or ["emoji", "💡", ""]
    if h[0] in ("cta", "reviews"):
        return ["cta"]
    if h[0] == "big":
        return ["big", h[1], h[2] if len(h) > 2 else ""]
    if h[0] == "chat":
        return ["chat", h[1], h[2] if len(h) > 2 else ""]
    if h[0] == "emoji":
        return ["emoji", h[1], h[2] if len(h) > 2 else ""]
    return ["mascot", "", h[2] if len(h) > 2 else "", ""]


def label_pill(text, dark=False):
    f = font(BOLD, 46 if dark else 56)
    tw = text_width(text, f)
    hh = 90 if dark else 106
    im = Image.new("RGBA", (int(tw + 76), hh), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, hh - 1), hh // 2,
                                         fill=(INK if dark else (234, 230, 222)) + (255,))
    draw_mixed(im, (38, (hh - sum(f.getmetrics())) // 2), text, f, (255, 255, 255) if dark else INK)
    return im


def prep(kind, accent):
    """Всё статичное для сцены рисуем один раз."""
    k = kind[0]
    P = {"k": k, "kind": kind}
    if k == "question":
        P["head"], P["unders"] = headline(kind[1], 100)
        P["q"] = sticker(qmark(), border=10)
    elif k in ("mascot",):
        P["prop"] = sticker(emoji_img(kind[1], 230), border=12) if len(kind) > 1 and kind[1] else None
        P["label"] = label_pill(kind[2]) if len(kind) > 2 and kind[2] else None
        P["outfit"] = kind[3] if len(kind) > 3 else ""
    elif k == "emoji":
        P["img"] = sticker(emoji_img(kind[1], 420), border=16)
        P["label"] = label_pill(kind[2]) if len(kind) > 2 and kind[2] else None
    elif k == "card":
        P["img"] = ui_card(kind[1], kind[2], kind[3] if len(kind) > 3 else "", accent)
    elif k == "big":
        P["label"] = label_pill(kind[2]) if len(kind) > 2 and kind[2] else None
    elif k == "rule":
        P["img"] = rule_card(kind[1], kind[2])
        P["head"], P["unders"] = headline("ПРАВИЛО *№%s*" % kind[1], 92)
    elif k == "terminal":
        P["lines"] = kind[1]
    elif k == "phone":
        P["phone"] = phone_body()
        P["note"] = notification(kind[1], kind[2])
    elif k == "chat":
        P["b"] = [bubble(kind[1][0], False), bubble(kind[1][1], True)]
        P["label"] = label_pill(kind[2]) if len(kind) > 2 and kind[2] else None
    elif k == "banner":
        pass
    elif k == "cta":
        P["img"] = cta_card()
        P["m"] = mascot_sticker(False, "", 22)
    return P


def qmark():
    f = font(BLACK, 230)
    im = Image.new("RGBA", (220, 280), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((30, 0), "?", font=f, fill=RED)
    return im.crop(im.getbbox())


def ui_card(e, title, sub, accent):
    w = 940
    tf, sf = font(BLACK, 84), font(MED, 56)
    tl = wrap(title, tf, w - 340)
    sl = wrap(sub, sf, w - 340) if sub else []
    h = max(420, 120 + len(tl) * 98 + len(sl) * 70 + 60)
    im, pad = soft_card(w, h)
    d = ImageDraw.Draw(im)
    # «окно»: три точки сверху
    for i, c in enumerate(((255, 95, 87), (255, 189, 46), (40, 200, 64))):
        d.ellipse((pad + 34 + i * 34, pad + 30, pad + 54 + i * 34, pad + 50), fill=c)
    ic = 230
    ix, iy = pad + 50, pad + (h - ic) // 2 + 20
    d.rounded_rectangle((ix, iy, ix + ic, iy + ic), 40, fill=tuple(int(c * 0.18 + 255 * 0.82) for c in accent))
    em = emoji_img(e, 150)
    im.alpha_composite(em, (ix + (ic - em.width) // 2, iy + (ic - em.height) // 2))
    y = pad + (h - (len(tl) * 98 + len(sl) * 70)) // 2 + 20
    for ln in tl:
        draw_mixed(im, (pad + 320, y), ln, tf, INK); y += 98
    for ln in sl:
        draw_mixed(im, (pad + 320, y), ln, sf, GREY); y += 70
    return im


def rule_card(n, text):
    w = 920
    tf = font(BLACK, 60)
    tl = wrap(text.upper(), tf, w - 250)
    h = max(220, len(tl) * 74 + 100)
    im, pad = soft_card(w, h, 36)
    d = ImageDraw.Draw(im)
    bx, by = pad + 40, pad + (h - 150) // 2
    d.rounded_rectangle((bx, by, bx + 150, by + 150), 30, fill=RED)
    nf = font(BLACK, 92 if len(str(n)) < 2 else 76)
    tw = nf.getlength(str(n))
    d.text((bx + (150 - tw) / 2, by + 18), str(n), font=nf, fill=(255, 255, 255))
    y = pad + (h - len(tl) * 74) // 2
    for ln in tl:
        draw_mixed(im, (pad + 230, y), ln, tf, INK); y += 74
    return im


def phone_body():
    w, h = 560, 1000
    im = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((30, 30, 30 + w, 30 + h), 90, fill=INK)
    d.rounded_rectangle((52, 52, 8 + w, 8 + h), 72, fill=(232, 238, 252))
    d.rounded_rectangle((30 + w / 2 - 80, 70, 30 + w / 2 + 80, 110), 20, fill=INK)
    # иконки приложений
    cols = [(255, 110, 100), (255, 190, 70), (90, 200, 120), (90, 160, 255), (170, 120, 255), (255, 140, 200)]
    for r in range(4):
        for c in range(4):
            x, y = 95 + c * 120, 520 + r * 120
            d.rounded_rectangle((x, y, x + 86, y + 86), 24, fill=cols[(r * 4 + c) % len(cols)] + (140,))
    return sticker(im, border=0)


def notification(e, text):
    w = 700
    f = font(BOLD, 46)
    tl = wrap(text, f, w - 180)[:3]
    h = 60 + len(tl) * 56
    im, pad = soft_card(w, h, 34)
    em = emoji_img(e, 80)
    im.alpha_composite(em, (pad + 34, pad + (h - em.height) // 2))
    y = pad + 30
    for ln in tl:
        draw_mixed(im, (pad + 140, y), ln, f, INK); y += 56
    return im


def bubble(text, mine):
    f = font(BOLD, 50)
    tl = wrap(text, f, 640)
    w = max(text_width(x, f) for x in tl) + 80
    h = len(tl) * 64 + 50
    im, pad = soft_card(int(w), h, 40, fill=(RED if mine else CARD))
    y = pad + 25
    for ln in tl:
        draw_mixed(im, (pad + 40, y), ln, f, (255, 255, 255) if mine else INK); y += 64
    return im


def cta_card():
    w, h = 940, 520
    im, pad = soft_card(w, h, 50)
    d = ImageDraw.Draw(im)
    ms = mascot(16)
    ax, ay = pad + 50, pad + 50
    d.ellipse((ax, ay, ax + 210, ay + 210), fill=(28, 26, 50))
    im.alpha_composite(ms, (ax + (210 - ms.width) // 2, ay + (210 - ms.height) // 2 + 6))
    nf = font(BLACK, 70 if len(CTA["name"]) < 14 else 56)
    d.text((pad + 300, pad + 70), CTA["name"], font=nf, fill=INK)
    d.text((pad + 300, pad + 160), "бот", font=font(MED, 44), fill=GREY)
    y = pad + 300
    for ln in wrap(CTA["subtitle"], font(BOLD, 52), w - 100)[:2]:
        draw_mixed(im, (pad + 50, y), ln, font(BOLD, 52), INK); y += 64
    return im


def cta_button(pulse):
    label = "✈  " + CTA["handle"]
    size = 76
    f = font(BLACK, size)
    while text_width(label, f) > 760:
        size -= 2; f = font(BLACK, size)
    tw = text_width(label, f)
    bw, bh = int(tw + 120), 140
    b = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    ImageDraw.Draw(b).rounded_rectangle((0, 0, bw - 1, bh - 1), 70, fill=(42, 160, 230))
    draw_mixed(b, (60, (bh - sum(f.getmetrics())) // 2), label, f, (255, 255, 255))
    return scaled(b, pulse)


def draw_scene(fr, P, lt, dur, t, sc, accent, first):
    """Рисует картинку сцены в кадр. lt — время от начала сцены."""
    k = P["k"]
    kind = P["kind"]
    cy = 800
    pop = 1.0 if first else ease_out_back(min(1, lt / 0.35))
    bob = 10 * math.sin(t * 2.4)
    blink = (t % 2.7) < 0.12
    d = ImageDraw.Draw(fr)

    if k == "question":
        head = P["head"]
        hy = 520
        paste_c(fr, faded(scaled(head, 0.85 + 0.15 * pop), min(1, pop + 0.3)), W / 2, hy)
        ox = (W - head.width) / 2
        oy = hy - head.height / 2
        for i, (x0, x1, y) in enumerate(P["unders"]):
            p = 1.0 if first and lt > 0.5 else ease_out(max(0, lt - 0.25 - i * 0.2) / 0.45)
            scribble(d, ox + x0, ox + x1, oy + y, p, seed=i + 3)
        m = mascot_sticker(blink, "", 30)
        paste_c(fr, scaled(m, 0.7 + 0.3 * pop), W / 2 - 60, 980 + bob)
        q = P["q"]
        qa = ease_out_back(min(1, max(0, lt - 0.4) / 0.35)) if not first else 1
        if qa > 0.01:
            q2 = scaled(q, qa).rotate(8 * math.sin(t * 3), resample=Image.BICUBIC, expand=True)
            paste_c(fr, q2, W / 2 + 230, 820 + bob * 0.5)

    elif k == "mascot":
        m = mascot_sticker(blink, P["outfit"], 34)
        paste_c(fr, scaled(m, 0.6 + 0.4 * pop), W / 2 - (90 if P["prop"] else 0), cy + 40 + bob)
        if P["prop"] is not None:
            pa = ease_out_back(min(1, max(0, lt - 0.25) / 0.35)) if not first else 1
            if pa > 0.01:
                pr = scaled(P["prop"], pa).rotate(6 * math.sin(t * 2.2 + 1), resample=Image.BICUBIC, expand=True)
                paste_c(fr, pr, W / 2 + 250, cy - 170 - bob * 0.6)
        if P["label"] is not None:
            paste_c(fr, faded(P["label"], ease_out(lt / 0.3) if not first else 1), W / 2, cy + 400)

    elif k == "emoji":
        im = P["img"].rotate(4 * math.sin(t * 2), resample=Image.BICUBIC, expand=True)
        paste_c(fr, scaled(im, 0.6 + 0.4 * pop), W / 2, cy + bob)
        if P["label"] is not None:
            paste_c(fr, faded(P["label"], ease_out(lt / 0.3) if not first else 1), W / 2, cy + 340)

    elif k == "card":
        paste_c(fr, scaled(P["img"], 0.7 + 0.3 * pop), W / 2, cy + bob * 0.4)
        m = mascot_sticker(blink, "", 16)
        mp = ease_out_back(min(1, max(0, lt - 0.35) / 0.35)) if not first else 1
        if mp > 0.01:
            paste_c(fr, scaled(m, mp), W / 2 + 330, cy - P["img"].height / 2 + 10 + bob)

    elif k == "big":
        txt = str(kind[1])
        shown = txt
        if re.fullmatch(r"\d{1,9}", txt) and not first:
            v = int(txt)
            p = ease_out(min(1, lt / 0.9))
            shown = str(int(v * p)) if len(txt) != 4 else str(int(int(txt[:2] + "00") + (v - int(txt[:2] + "00")) * p))
        size = 300 if len(txt) <= 4 else max(130, int(300 * 4 / len(txt)))
        f = font(BLACK, size)
        tw = f.getlength(txt)
        layer = Image.new("RGBA", (int(tw + 80), int(size * 1.3)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(((layer.width - f.getlength(shown)) / 2, 0), shown, font=f, fill=INK)
        layer = scaled(layer, 0.7 + 0.3 * pop)
        paste_c(fr, layer, W / 2, cy - 40)
        p = 1 if first else ease_out(max(0, lt - 0.35) / 0.45)
        scribble(d, W / 2 - tw / 2, W / 2 + tw / 2, cy - 40 + size * 0.62, p, width=16, seed=len(txt))
        if P["label"] is not None:
            paste_c(fr, faded(P["label"], ease_out(lt / 0.3) if not first else 1), W / 2, cy + 280)

    elif k == "rule":
        head = P["head"]
        paste_c(fr, head, W / 2, 500)
        ox, oy = (W - head.width) / 2, 500 - head.height / 2
        for i, (x0, x1, y) in enumerate(P["unders"]):
            scribble(d, ox + x0, ox + x1, oy + y, 1 if first else ease_out(max(0, lt - 0.2) / 0.4), width=10, seed=9)
        x = W / 2 + (0 if first else (1 - ease_out(min(1, lt / 0.35))) * 900)
        paste_c(fr, P["img"], x, cy + 20 + bob * 0.3)
        m = mascot_sticker(blink, "helmet", 24)
        paste_c(fr, m, W / 2 + 280, cy + P["img"].height / 2 + 100 + bob)

    elif k == "terminal":
        tw_, th_ = 940, 150 + 76 * len(P["lines"])
        win = Image.new("RGBA", (tw_, th_), (0, 0, 0, 0))
        wd = ImageDraw.Draw(win)
        wd.rounded_rectangle((0, 0, tw_ - 1, th_ - 1), 36, fill=(22, 24, 32))
        for i, c in enumerate(((255, 95, 87), (255, 189, 46), (40, 200, 64))):
            wd.ellipse((30 + i * 36, 28, 52 + i * 36, 50), fill=c)
        mf = font(MONO if os.path.exists(MONO) else BOLD, 50)
        while max(mf.getlength(x) for x in P["lines"]) > tw_ - 90 and mf.size > 26:
            mf = font(MONO if os.path.exists(MONO) else BOLD, mf.size - 2)
        chars = int(max(0, lt - 0.2) * 22) if not first else 999
        y = 100
        for ln in P["lines"]:
            s = ln[:max(0, chars)]
            chars -= len(ln)
            wd.text((40, y), s, font=mf, fill=(120, 255, 160) if ln.startswith("$") or ln.startswith(">") else (230, 232, 240))
            if 0 <= chars < 3 and (t * 2) % 1 < 0.5:
                wd.rectangle((40 + mf.getlength(s) + 6, y + 4, 40 + mf.getlength(s) + 28, y + 46), fill=(230, 232, 240))
            y += 76
            if chars < 0:
                break
        sh = sticker(win, border=0)
        paste_c(fr, scaled(sh, 0.8 + 0.2 * pop), W / 2, cy)
        m = mascot_sticker(blink, "hacker", 18)
        paste_c(fr, m, W / 2 + 330, cy + th_ / 2 + 60 + bob)

    elif k == "phone":
        ph = P["phone"]
        paste_c(fr, scaled(ph, 0.65 + 0.22 * pop), W / 2, cy + 40 + bob * 0.3)
        np_ = 1 if first else ease_out_back(min(1, max(0, lt - 0.4) / 0.4))
        if np_ > 0.01:
            nt = P["note"]
            paste_c(fr, scaled(nt, np_), W / 2, cy - 220 + (1 - np_) * -150)

    elif k == "chat":
        b1, b2 = P["b"]
        if P["label"] is not None:
            paste_c(fr, P["label"], W / 2, 450)
        p1 = 1 if first else ease_out(min(1, lt / 0.35))
        fr.alpha_composite(faded(b1, p1), (60 - int((1 - p1) * 200), int(560 + bob * 0.3)))
        p2 = ease_out(max(0, lt - 1.0) / 0.35)
        if p2 > 0:
            fr.alpha_composite(faded(b2, p2), (W - 60 - b2.width + int((1 - p2) * 200), int(560 + b1.height + bob * 0.3)))

    elif k == "cta":
        card = P["img"]
        paste_c(fr, scaled(card, 0.7 + 0.3 * pop), W / 2, cy - 60)
        if lt > 0.4:
            btn = cta_button(1 + 0.04 * math.sin((lt - 0.4) * 6))
            paste_c(fr, btn, W / 2, cy - 60 + card.height / 2 + 60)



# ---------- рекламный баннер в середине ролика ----------
# Ролик «встаёт на паузу», по центру раскрывается тёмная полоса-баннер,
# голос читает рекламную фразу, потом баннер схлопывается и ролик идёт дальше.
AD_MID = [
    ("Кстати, нужен телеграм-бот или сайт? Сделаю под ключ, быстро и недорого. Ищи в Телеграме Портфолио Хаззер бот.",
     "Нужен Telegram-бот или сайт? 👉 @PortfolioHazzer_bot"),
    ("Пауза на рекламу. Делаю телеграм-ботов и сайты под ключ, по приятной цене. Ищи в Телеграме Портфолио Хаззер бот.",
     "Telegram-боты и сайты под ключ 👉 @PortfolioHazzer_bot"),
    ("Кстати, бот, который продаёт за тебя, можно заказать у меня. Ищи в Телеграме Портфолио Хаззер бот.",
     "Бот, который продаёт за тебя 👉 @PortfolioHazzer_bot"),
]
GREEN = (70, 225, 100)
BAN_H = 470


def place_banner(v):
    """Рекламную сцену из конца ставим в середину и превращаем в баннер."""
    sc = [dict(x) for x in v["scenes"]]
    ads = [i for i, x in enumerate(sc) if x.get("ad")]
    if len(ads) != 1 or ads[0] != len(sc) - 1 or len(sc) < 4:
        return v
    ad = sc.pop()
    ad["banner"] = True
    if not v.get("cta"):  # свои факты: фраза подлиннее, чтобы баннер успели рассмотреть
        say, show = AD_MID[sum(map(ord, v["id"])) % len(AD_MID)]
        ad["say"], ad["show"] = say, show
    pos = (len(sc) + 1) // 2
    sc.insert(pos, ad)
    return dict(v, scenes=sc)


def glossy_panel(w, h, r=34):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = Image.new("RGBA", (w, h))
    gd = ImageDraw.Draw(g)
    for y in range(h):
        k = y / h
        c = int(70 - 50 * k)
        gd.line([(0, y), (w, y)], fill=(c, c, c + 4, 255))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    im.paste(g, (0, 0), m)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), r, outline=(120, 120, 128, 255), width=3)
    d.rounded_rectangle((10, 6, w - 11, h // 2), r - 8, fill=(255, 255, 255, 18))  # блик
    return im


def red_button(text, w=None):
    f = font(BLACK, 64)
    while text_width(text, f) > 700:
        f = font(BLACK, f.size - 2)
    tw = text_width(text, f)
    bw, bh = int(w or tw + 110), 112
    b = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    g = Image.new("RGBA", (bw, bh))
    gd = ImageDraw.Draw(g)
    for y in range(bh):
        k = y / bh
        gd.line([(0, y), (bw, y)], fill=(int(250 - 40 * k), int(80 - 30 * k), int(60 - 25 * k), 255))
    m = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, bw - 1, bh - 1), 26, fill=255)
    b.paste(g, (0, 0), m)
    ImageDraw.Draw(b).rounded_rectangle((8, 6, bw - 9, bh // 2), 20, fill=(255, 255, 255, 40))
    draw_mixed(b, (int((bw - tw) / 2), int((bh - sum(f.getmetrics())) / 2)), text, f, (255, 255, 255))
    return b


def banner_panels():
    """Три «кадра» баннера: что делаю, что умеет, куда идти."""
    out = []
    sub = CTA["subtitle"]
    words = sub.split()
    top, acc = (" ".join(words[:-2]), " ".join(words[-2:])) if len(words) > 3 else (sub, "")
    f1, f2 = font(BOLD, 62), font(BLACK, 66)
    w = 820
    p = glossy_panel(w, 250)
    draw_mixed(p, (int((w - text_width(top, f1)) / 2), 50), top, f1, (255, 255, 255))
    if acc:
        draw_mixed(p, (int((w - text_width(acc, f2)) / 2), 130), acc, f2, GREEN)
    out.append(p)
    items = list(CTA.get("items") or [])[:2]
    p = glossy_panel(w, 250)
    fi = font(BOLD, 50)
    while items and max(text_width(x, fi) for x in items) > w - 170 and fi.size > 30:
        fi = font(BOLD, fi.size - 2)
    y = 52
    for it in items:
        d = ImageDraw.Draw(p)
        d.ellipse((60, y + 8, 106, y + 54), fill=GREEN)
        d.line((72, y + 31, 81, y + 41), fill=(20, 20, 20), width=6)
        d.line((81, y + 41, 96, y + 20), fill=(20, 20, 20), width=6)
        txt = it
        while text_width(txt, fi) > w - 170 and len(txt) > 4:
            txt = txt[:-2]
        draw_mixed(p, (130, y), txt, fi, (255, 255, 255))
        y += 86
    out.append(p)
    p = glossy_panel(w, 330)
    lab = "Ищи в Telegram"
    draw_mixed(p, (int((w - text_width(lab, f1)) / 2), 40), lab, f1, (255, 255, 255))
    btn = red_button(CTA["handle"].replace("t.me/", "@"), w - 100)
    p.alpha_composite(btn, (50, 170))
    out.append(p)
    return out


def banner_strip():
    st = Image.new("RGBA", (W, BAN_H), (8, 8, 10, 255))
    d = ImageDraw.Draw(st)
    for y in range(18, BAN_H, 36):
        for x in range(18, W, 36):
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(32, 32, 38))
    return st


_ban = {}


def draw_banner(fr, frozen, lt, dur, t):
    if "panels" not in _ban or _ban.get("for") != CTA["handle"]:
        _ban.update(panels=banner_panels(), strip=banner_strip(), **{"for": CTA["handle"]})
        _ban["icons"] = [sticker(emoji_img(e, 110), border=0, shadow=False) for e in ("🤖", "✈️", "💬", "⭐", "🚀", "💸")]
    fr.alpha_composite(frozen)
    # значок паузы над баннером
    pa = min(1, lt / 0.2)
    ov = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.ellipse((0, 0, 139, 139), fill=(255, 255, 255, int(50 * pa)))
    d.rectangle((44, 40, 62, 100), fill=(255, 255, 255, int(235 * pa)))
    d.rectangle((78, 40, 96, 100), fill=(255, 255, 255, int(235 * pa)))
    fr.alpha_composite(ov, (W // 2 - 70, H // 2 - BAN_H // 2 - 190))
    # раскрытие и схлопывание полосы
    open_ = ease_out(min(1, lt / 0.3))
    close = ease_out(min(1, max(0, dur - lt) / 0.3))
    k = min(open_, close)
    hh = max(4, int(BAN_H * k))
    strip = _ban["strip"].crop((0, (BAN_H - hh) // 2, W, (BAN_H - hh) // 2 + hh)).copy()
    sd = ImageDraw.Draw(strip)
    if k > 0.9:
        # летающие иконки за панелью
        rnd = random.Random(7)
        for i in range(10):
            ic = _ban["icons"][i % len(_ban["icons"])]
            ang = rnd.uniform(0, 6.28)
            spd = rnd.uniform(160, 300)
            ph = (lt * 0.6 + rnd.random()) % 1
            x = W / 2 + math.cos(ang) * (220 + spd * ph * 2.2)
            y = hh / 2 + math.sin(ang) * (60 + spd * ph * 0.6)
            sz = 0.55 + 0.45 * math.sin(ph * 3.14)
            im = faded(scaled(ic, sz).rotate(lt * 90 * (1 if i % 2 else -1) + i * 40, expand=True), math.sin(ph * 3.14))
            strip.alpha_composite(im, (int(x - im.width / 2), int(y - im.height / 2)))
        # панели по очереди, каждая выезжает с «подскоком»
        body = max(0.5, dur - 0.6)
        n = len(_ban["panels"])
        pi = min(n - 1, int(max(0, lt - 0.3) / (body / n)))
        plt = max(0, lt - 0.3) - pi * body / n
        p = _ban["panels"][pi]
        s = 0.7 + 0.3 * ease_out_back(min(1, plt / 0.3))
        img = scaled(p, s)
        if pi == n - 1:  # кнопка «дышит»
            img = scaled(p, s * (1 + 0.03 * math.sin(plt * 7)))
        strip.alpha_composite(img, (int((W - img.width) / 2), int((hh - img.height) / 2)))
        # плашка «реклама»
        lf = font(BOLD, 30)
        sd.rounded_rectangle((24, 20, 24 + text_width("РЕКЛАМА", lf) + 32, 66), 14, fill=(255, 255, 255, 40))
        sd.text((40, 26), "РЕКЛАМА", font=lf, fill=(220, 220, 225))
    sd.line((0, 0, W, 0), fill=(90, 90, 100), width=3)
    sd.line((0, hh - 2, W, hh - 2), fill=(90, 90, 100), width=3)
    fr.alpha_composite(strip, (0, (H - hh) // 2))


# ---------- субтитры ----------

def chunks(text):
    words = text.split()
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(" ".join(cur)) >= 20 or len(cur) >= 4 or re.search(r"[.,:!?»…]$", w):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    # одно короткое слово отдельно смотрится пусто: приклеиваем к предыдущему куску
    res = []
    for c in out:
        if res and len(" ".join(c)) < 8 and len(res[-1]) <= 4:
            res[-1] = res[-1] + c
        else:
            res.append(c)
    return res


def captions(sc):
    ch = chunks(sc["show"])
    L = sum(len(w) + 2 for c in ch for w in c)
    dur = sc["voice_end"] - sc["start"]
    t, caps = sc["start"], []
    for c in ch:
        ws = []
        for w in c:
            dd = dur * (len(w) + 2) / L
            ws.append((t, t + dd, w)); t += dd
        caps.append((ws[0][0], ws[-1][1], ws))
    return caps


def draw_caption(fr, cap, t, first, ad):
    size = 78
    f = font(BLACK, size)
    words = [(a, b, w) for a, b, w in cap[2]]
    if max(text_width(w, f) for _, _, w in words) > 960:
        k = 960 / max(text_width(w, f) for _, _, w in words)
        size = int(size * k); f = font(BLACK, size)
    sp = f.getlength(" ")
    lines, cur, cw = [], [], 0
    for wd in words:
        ww = text_width(wd[2], f)
        if cur and cw + sp + ww > 960:
            lines.append((cur, cw)); cur, cw = [], 0
        cw += (sp if cur else 0) + ww
        cur.append((wd, ww))
    if cur:
        lines.append((cur, cw))
    y = 1420 - (len(lines) - 1) * size * 0.6
    for ln, lw in lines:
        x = (W - lw) / 2
        for (a, b, w), ww in ln:
            vis = 0 if first and cap[0] < 0.5 else a  # хук виден с первого кадра
            p = 1 if t >= vis + 0.12 else max(0, (t - vis + 0.06) / 0.18)
            if p > 0:
                on = a <= t < b
                col = (RED if not ad else (42, 160, 230)) if on else INK
                layer = Image.new("RGBA", (int(ww + 20), int(size * 1.4)), (0, 0, 0, 0))
                draw_mixed(layer, (10, 0), w, f, col)
                if p < 1:
                    layer = faded(layer.filter(ImageFilter.GaussianBlur(6 * (1 - p))), p)
                fr.alpha_composite(layer, (int(x - 10), int(y + 18 * (1 - p))))
            x += ww + sp
        y += size * 1.2


# ---------- сборка ----------

def build(v, out_path, work):
    os.makedirs(work, exist_ok=True)
    CTA.clear(); CTA.update(CTA_DEFAULT, **(v.get("cta") or {}))
    accent = tuple(v["accent"])
    v = place_banner(v)
    timeline, total, wav_path = engine.make_audio(v, work)
    preps = [prep(["banner"] if sc.get("banner") else kind_of(sc), accent) for sc in timeline]
    for sc in timeline:
        sc["caps"] = captions(sc)

    # фон: бумага в точку + лёгкая виньетка
    bg = Image.new("RGBA", (W, H), PAPER + (255,))
    bd = ImageDraw.Draw(bg)
    for y in range(30, H, 54):
        for x in range(27, W, 54):
            bd.ellipse((x - 3, y - 3, x + 3, y + 3), fill=DOT)
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse((-300, -200, W + 300, H + 200), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(220))
    shade = Image.new("RGBA", (W, H), (200, 192, 178, 0))
    shade.putalpha(vig.point(lambda a: int((255 - a) * 0.35)))
    bg.alpha_composite(shade)

    # верхняя строка: название канала + шкала «сколько осталось»
    brand = label_pill("НЕ ЗНАЛ?", dark=True)
    n_sc = len(timeline)

    ff = subprocess.Popen([
        engine.FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-", "-i", wav_path, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-shortest", "-movflags", "+faststart", out_path],
        stdin=subprocess.PIPE)

    frozen, last_fr = None, bg.copy()
    for fi in range(int(total * FPS)):
        t = fi / FPS
        si = next((i for i, sc in enumerate(timeline) if sc["start"] - (0.2 if i == 0 else 0) <= t < sc["end"]),
                  len(timeline) - 1)
        sc = timeline[si]
        lt = t - sc["start"]
        first = si == 0
        if sc.get("banner"):
            if frozen is None:
                fz = last_fr.filter(ImageFilter.GaussianBlur(6))
                fz.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 185)))
                frozen = fz
            fr = Image.new("RGBA", (W, H))
            draw_banner(fr, frozen, lt, sc["end"] - sc["start"], t)
            d = ImageDraw.Draw(fr)
            d.rounded_rectangle((60, 1880, W - 60, 1890), 5, fill=(80, 80, 86))
            d.rounded_rectangle((60, 1880, 60 + int((W - 120) * t / total), 1890), 5, fill=(255, 255, 255))
            ff.stdin.write(fr.convert("RGB").tobytes())
            continue
        frozen = None
        fr = bg.copy()
        draw_scene(fr, preps[si], lt, sc["end"] - sc["start"], t, sc, accent, first)

        # смена сцены: короткая «шторка» цвета бумаги, чтобы склейка ощущалась
        if si and lt < 0.12:
            fr.alpha_composite(Image.new("RGBA", (W, H), PAPER + (int(200 * (1 - lt / 0.12)),)))

        # медленный наезд камеры
        z = 1.0 + 0.035 * min(1.0, lt / max(0.5, sc["end"] - sc["start"]))
        if z > 1.002:
            zw, zh = int(W * z), int(H * z)
            big = fr.resize((zw, zh), Image.BILINEAR)
            fr = big.crop(((zw - W) // 2, (zh - H) // 2, (zw - W) // 2 + W, (zh - H) // 2 + H))

        # шапка
        fr.alpha_composite(brand, (60, 110))
        d = ImageDraw.Draw(fr)
        for i in range(n_sc):
            x = W - 70 - (n_sc - i) * 46
            done = i < si or (i == si and lt > 0.2)
            d.ellipse((x, 140, x + 30, 170), fill=(RED if done else (215, 211, 203)))
        d.rounded_rectangle((60, 1880, W - 60, 1890), 5, fill=(225, 221, 213))
        d.rounded_rectangle((60, 1880, 60 + int((W - 120) * t / total), 1890), 5, fill=INK)

        cap = next((c for c in sc["caps"] if c[0] <= t < c[1]), None)
        if cap is None and sc["caps"] and t >= sc["caps"][-1][0] and t < sc["voice_end"] + 0.25:
            cap = sc["caps"][-1]
        if cap is None and first and sc["caps"]:
            cap = sc["caps"][0]
        if cap:
            draw_caption(fr, cap, t, first, bool(sc.get("ad")))
        last_fr = fr.copy()
        ff.stdin.write(fr.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()
    if ff.returncode != 0:
        raise RuntimeError("ffmpeg не смог собрать видео")
    engine.finish(out_path)
    return out_path, total
