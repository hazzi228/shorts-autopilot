"""Стиль «мини-фильм»: мультяшный герой в местах (комната, улица, магазин, банкомат, космос),
с ним что-то происходит, камера двигается, голос за кадром рассказывает историю.
Зритель — сам герой («ты»). Сделано по разбору вирусных анимаций в Shorts/TikTok (27.11.2026).

Сцену описывает поле "film" (если нет — герой просто стоит в комнате):
  {"bg": "room|street|shop|atm|space|server|park",
   "act": "stand|walk|sit|phone|shock|run",
   "mood": "neutral|happy|worried|shock|angry",
   "prop": "phone|usb|card|cash|none",     # что в руке
   "fx": "alarm|glitch|nosignal|money|hacker|crowd|dark|calm",
   "think": "💳",                           # пузырь-мысль с эмодзи над головой
   "sign": "ДЕНЬ 3",                        # светящаяся надпись в сцене
   "screen": "ok|red|code|off"}             # что на мониторе / терминале
Включается полем сценария "style": "film". Реклама — тот же баннер в середине, что и в drawn.
"""
import os, re, math, random, subprocess
from PIL import Image, ImageDraw, ImageFilter

import engine
import drawn
import dark
from engine import font, BLACK, BOLD, emoji_img, text_width, draw_mixed, ease_out, ease_out_back, CTA, CTA_DEFAULT

W, H, FPS = engine.W, engine.H, engine.FPS
GROUND = 1680          # линия пола / тротуара
BGW = 1500             # фон шире кадра, чтобы камера могла ехать
SKIN = (255, 210, 170)
HAIR = (70, 45, 35)
PANTS = (45, 55, 85)
SHOE = (30, 30, 36)
INK = (20, 18, 26)


def aa(draw_fn, w, h, k=2):
    """Рисуем в 2 раза крупнее и уменьшаем: сглаженные края без лишних библиотек."""
    im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(im), k)
    return im.resize((w, h), Image.LANCZOS)


# ---------- герой ----------

def limb(d, x0, y0, ang, ln, width, color, k):
    x1 = x0 + math.sin(math.radians(ang)) * ln
    y1 = y0 + math.cos(math.radians(ang)) * ln
    d.line((x0 * k, y0 * k, x1 * k, y1 * k), fill=color, width=int(width * k))
    r = width / 2
    d.ellipse(((x0 - r) * k, (y0 - r) * k, (x0 + r) * k, (y0 + r) * k), fill=color)
    return x1, y1


def hero(pose, shirt, k=2):
    """Герой в позе. pose: dict(la, ra — углы рук, ll, rl — углы ног, mood, blink, prop, look, sit).
    Возвращает картинку 420x900, ноги внизу по центру."""
    Wc, Hc = 420, 900
    im = Image.new("RGBA", (Wc * k, Hc * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = Wc / 2
    hip = 600
    sh = 400
    look = pose.get("look", 0)
    # ноги
    if not pose.get("sit"):
        for ang, side in ((pose.get("ll", 0), -1), (pose.get("rl", 0), 1)):
            fx, fy = limb(d, cx + side * 34, hip, ang, 250, 58, PANTS, k)
            d.ellipse(((fx - 40 + side * 8) * k, (fy - 14) * k, (fx + 44 + side * 8) * k, (fy + 26) * k), fill=SHOE)
    # руки за телом (дальняя)
    arm_w = 46
    # туловище (худи)
    d.rounded_rectangle(((cx - 112) * k, (sh - 20) * k, (cx + 112) * k, (hip + 40) * k), int(70 * k), fill=shirt)
    pocket = tuple(max(0, c - 30) for c in shirt)
    d.rounded_rectangle(((cx - 60) * k, (hip - 70) * k, (cx + 60) * k, (hip - 10) * k), int(20 * k), fill=pocket)
    d.line(((cx - 26) * k, (sh + 10) * k, (cx - 18) * k, (sh + 90) * k), fill=(240, 240, 245), width=int(7 * k))
    d.line(((cx + 26) * k, (sh + 10) * k, (cx + 18) * k, (sh + 90) * k), fill=(240, 240, 245), width=int(7 * k))
    # руки: плечо + предплечье, углы от «вниз», плюс — вправо по экрану
    sleeve = tuple(int(c * 0.82) for c in shirt)
    hands = []
    for side, u, f_ in ((-1, pose.get("lu", -12), pose.get("lf", -6)), (1, pose.get("ru", 12), pose.get("rf", 6))):
        x0 = cx + side * 96
        ex, ey = limb(d, x0, sh + 34, u, 150, arm_w, sleeve, k)
        hx, hy = limb(d, ex, ey, f_, 125, arm_w - 4, sleeve, k)
        d.ellipse(((hx - 30) * k, (hy - 30) * k, (hx + 30) * k, (hy + 30) * k), fill=SKIN)
        hands.append((hx, hy))
    # голова
    hx0, hy0 = cx + look * 6, 230
    R = 150
    d.ellipse(((hx0 - R) * k, (hy0 - R) * k, (hx0 + R) * k, (hy0 + R) * k), fill=SKIN)
    d.ellipse(((hx0 - R - 18) * k, (hy0 - 30) * k, (hx0 - R + 22) * k, (hy0 + 30) * k), fill=SKIN)
    d.ellipse(((hx0 + R - 22) * k, (hy0 - 30) * k, (hx0 + R + 18) * k, (hy0 + 30) * k), fill=SKIN)
    # волосы: шапка с вихрами
    d.chord(((hx0 - R - 6) * k, (hy0 - R - 14) * k, (hx0 + R + 6) * k, (hy0 + R - 40) * k), 180, 360, fill=HAIR)
    for i in range(7):
        a = math.radians(200 + i * 23)
        px, py = hx0 + math.cos(a) * (R - 10), hy0 - 40 + math.sin(a) * (R - 10)
        d.polygon([((px - 30) * k, (py + 10) * k), ((px + math.cos(a) * 60) * k, (py + math.sin(a) * 60 - 10) * k),
                   ((px + 30) * k, (py + 10) * k)], fill=HAIR)
    mood = pose.get("mood", "neutral")
    ex = [hx0 - 55 + look * 10, hx0 + 55 + look * 10]
    ey = hy0 + 10
    big = mood == "shock"
    for x in ex:
        if pose.get("blink"):
            d.line(((x - 22) * k, ey * k, (x + 22) * k, ey * k), fill=INK, width=int(7 * k))
        else:
            r1 = 30 if big else 24
            d.ellipse(((x - r1) * k, (ey - r1 - 4) * k, (x + r1) * k, (ey + r1 + 4) * k), fill=(255, 255, 255))
            pr = 11 if big else 13
            d.ellipse(((x - pr + look * 6) * k, (ey - pr) * k, (x + pr + look * 6) * k, (ey + pr) * k), fill=INK)
    # брови
    tilt = {"neutral": 0, "happy": -4, "worried": 14, "shock": -14, "angry": -18}.get(mood, 0)
    for i, x in enumerate(ex):
        s = 1 if i == 0 else -1
        y = ey - (48 if big else 40)
        d.line(((x - 26) * k, (y + s * tilt * 0.5 * (-1 if mood == "worried" else 1)) * k,
                (x + 26) * k, (y - s * tilt * 0.5 * (-1 if mood == "worried" else 1)) * k), fill=HAIR, width=int(10 * k))
    # рот
    my = hy0 + 80
    if mood in ("shock",):
        d.ellipse(((hx0 - 24) * k, (my - 26) * k, (hx0 + 24) * k, (my + 30) * k), fill=(120, 30, 40))
    elif mood == "happy":
        d.chord(((hx0 - 50) * k, (my - 40) * k, (hx0 + 50) * k, (my + 30) * k), 0, 180, fill=(120, 30, 40))
    elif mood in ("worried", "angry"):
        d.arc(((hx0 - 40) * k, (my - 6) * k, (hx0 + 40) * k, (my + 40) * k), 200, 340, fill=INK, width=int(8 * k))
    else:
        d.line(((hx0 - 26) * k, my * k, (hx0 + 26) * k, my * k), fill=INK, width=int(8 * k))
    d.ellipse(((hx0 - 100) * k, (my - 40) * k, (hx0 - 60) * k, (my - 14) * k), fill=(255, 170, 150))
    d.ellipse(((hx0 + 60) * k, (my - 40) * k, (hx0 + 100) * k, (my - 14) * k), fill=(255, 170, 150))
    im = im.resize((Wc, Hc), Image.LANCZOS)
    return im, hands


def pose_for(act, mood, t, lt, prop):
    p = dict(mood=mood, blink=((t + 1.5) % 3.1) < 0.12, ll=0, rl=0, look=0, prop=prop)
    sway = 3 * math.sin(t * 2)
    p.update(lu=-12 + sway, lf=-6 + sway, ru=12 - sway, rf=6 - sway)
    if act in ("walk", "run"):
        sp = 9 if act == "walk" else 15
        a = math.sin(lt * sp) * (24 if act == "walk" else 38)
        p.update(ll=a, rl=-a, lu=-a * 0.7, lf=-a * 0.7 + 25, ru=a * 0.7, rf=a * 0.7 + 25, look=1)
    elif act == "phone":
        p.update(lu=-18, lf=140, ru=18, rf=-140)
    elif act == "shock":
        w = 6 * math.sin(lt * 20)
        p.update(lu=-150 + w, lf=-165 + w, ru=150 - w, rf=165 - w)
    elif act == "sit":
        p.update(sit=True, lu=25, lf=75 + 10 * math.sin(lt * 14), ru=35, rf=80 + 10 * math.sin(lt * 14 + 1.5), look=1)
    if prop in ("usb", "card", "cash") and act in ("stand", "worried"):
        p.update(ru=40, rf=165)
    if prop == "phone" and act == "stand":
        p.update(lu=-18, lf=140, ru=18, rf=-140)
    return p


def draw_prop(fr, prop, hand, screen_col, t):
    hx, hy = hand
    if prop == "phone":
        ph = aa(lambda d, k: (d.rounded_rectangle((0, 0, 90 * k, 160 * k), 16 * k, fill=(25, 25, 32)),
                              d.rounded_rectangle((8 * k, 12 * k, 82 * k, 148 * k), 8 * k, fill=screen_col)), 90, 160)
        g = dark.glow(ph, screen_col, 14, 1)
        fr.alpha_composite(g, (int(hx - g.width / 2), int(hy - g.height / 2 - 30)))
    elif prop == "usb":
        u = aa(lambda d, k: (d.rounded_rectangle((0, 20 * k, 70 * k, 120 * k), 10 * k, fill=(40, 120, 230)),
                             d.rectangle((15 * k, 0, 55 * k, 26 * k), fill=(200, 200, 210))), 70, 120)
        fr.alpha_composite(u.rotate(-20, expand=True, resample=Image.BICUBIC), (int(hx - 40), int(hy - 130)))
    elif prop == "card":
        c = aa(lambda d, k: (d.rounded_rectangle((0, 0, 150 * k, 95 * k), 12 * k, fill=(255, 190, 40)),
                             d.rectangle((14 * k, 30 * k, 44 * k, 52 * k), fill=(200, 160, 60))), 150, 95)
        fr.alpha_composite(c, (int(hx - 75), int(hy - 100)))
    elif prop == "cash":
        c = aa(lambda d, k: d.rounded_rectangle((0, 0, 170 * k, 80 * k), 8 * k, fill=(90, 190, 110)), 170, 80)
        fr.alpha_composite(c.rotate(10, expand=True), (int(hx - 85), int(hy - 90)))


# ---------- места ----------

def window_city(d, k, x0, y0, x1, y1, seed=1):
    r = random.Random(seed)
    d.rectangle((x0 * k, y0 * k, x1 * k, y1 * k), fill=(18, 24, 52))
    for _ in range(40):
        sx, sy = r.uniform(x0, x1), r.uniform(y0, y0 + (y1 - y0) * 0.5)
        d.ellipse(((sx - 2) * k, (sy - 2) * k, (sx + 2) * k, (sy + 2) * k), fill=(220, 220, 255))
    x = x0
    while x < x1:
        bw = r.uniform(50, 110)
        bh = r.uniform((y1 - y0) * 0.3, (y1 - y0) * 0.8)
        d.rectangle((x * k, (y1 - bh) * k, min(x1, x + bw) * k, y1 * k), fill=(30, 34, 60))
        for wy in range(int(y1 - bh + 14), int(y1 - 10), 28):
            for wx in range(int(x + 10), int(min(x1, x + bw) - 14), 24):
                if r.random() < 0.45:
                    d.rectangle((wx * k, wy * k, (wx + 12) * k, (wy + 14) * k), fill=(255, 210, 110))
        x += bw + 6


def bg_room(k, night=True):
    def f(d, k):
        d.rectangle((0, 0, BGW * k, H * k), fill=(62, 66, 104))
        d.rectangle((0, GROUND * k, BGW * k, H * k), fill=(92, 68, 60))
        for x in range(0, BGW, 90):
            d.line((x * k, GROUND * k, (x - 60) * k, H * k), fill=(80, 58, 52), width=3 * k)
        # окно
        d.rounded_rectangle((210 * k, 380 * k, 690 * k, 900 * k), 14 * k, fill=(230, 225, 215))
        window_city(d, k, 230, 400, 670, 880, 3)
        d.line((450 * k, 400 * k, 450 * k, 880 * k), fill=(230, 225, 215), width=14 * k)
        # постер и полка
        d.rounded_rectangle((900 * k, 470 * k, 1120 * k, 760 * k), 10 * k, fill=(240, 90, 80))
        d.ellipse((960 * k, 540 * k, 1060 * k, 640 * k), fill=(255, 210, 80))
        d.rectangle((1180 * k, 640 * k, 1440 * k, 660 * k), fill=(120, 84, 70))
        for i, c in enumerate(((90, 160, 240), (240, 200, 80), (120, 200, 140), (230, 110, 150))):
            d.rectangle(((1200 + i * 50) * k, (540 + (i % 2) * 20) * k, (1240 + i * 50) * k, 640 * k), fill=c)
        # плинтус
        d.rectangle((0, (GROUND - 16) * k, BGW * k, GROUND * k), fill=(48, 50, 80))
    return aa(f, BGW, H)


def desk_fg(screen):
    def f(d, k):
        d.rounded_rectangle((330 * k, 1250 * k, 1170 * k, 1300 * k), 12 * k, fill=(150, 104, 76))
        d.rectangle((370 * k, 1300 * k, 410 * k, GROUND * k), fill=(120, 84, 62))
        d.rectangle((1090 * k, 1300 * k, 1130 * k, GROUND * k), fill=(120, 84, 62))
        # монитор (стоит спиной к нам? нет — сбоку, экран видно)
        d.rounded_rectangle((620 * k, 960 * k, 1100 * k, 1230 * k), 18 * k, fill=(28, 28, 36))
        d.rectangle((830 * k, 1230 * k, 890 * k, 1252 * k), fill=(40, 40, 48))
        d.rounded_rectangle((420 * k, 1225 * k, 640 * k, 1250 * k), 8 * k, fill=(50, 50, 60))
    im = aa(f, W, H)
    scr = {"ok": (90, 170, 255), "red": (230, 50, 50), "code": (20, 40, 25), "off": (15, 15, 20)}.get(screen, (90, 170, 255))
    sd = ImageDraw.Draw(im)
    sd.rounded_rectangle((640, 980, 1080, 1210), 10, fill=scr)
    if screen == "code":
        r = random.Random(4)
        for y in range(1000, 1200, 26):
            sd.rectangle((660, y, 660 + r.randint(80, 380), y + 12), fill=(80, 230, 120))
    if screen == "red":
        f2 = font(BLACK, 90)
        sd.text((860 - f2.getlength("!") / 2, 1040), "!", font=f2, fill=(255, 255, 255))
    return im


def bg_street(k, day=False):
    def f(d, k):
        top, bot = ((120, 190, 240), (200, 230, 250)) if day else ((14, 16, 40), (60, 40, 90))
        for y in range(0, GROUND, 8):
            c = tuple(int(top[i] + (bot[i] - top[i]) * y / GROUND) for i in range(3))
            d.rectangle((0, y * k, BGW * k, (y + 8) * k), fill=c)
        r = random.Random(7)
        x = -20
        while x < BGW:  # дальние дома
            bw, bh = r.uniform(120, 220), r.uniform(500, 900)
            d.rectangle((x * k, (GROUND - 120 - bh) * k, (x + bw) * k, (GROUND - 120) * k),
                        fill=(150, 170, 200) if day else (34, 32, 62))
            x += bw + 10
        x = -40
        while x < BGW:  # ближние дома с окнами
            bw, bh = r.uniform(260, 380), r.uniform(560, 760)
            col = r.choice([(200, 120, 100), (180, 150, 120), (120, 130, 160)]) if day else r.choice([(60, 48, 80), (52, 58, 90), (70, 50, 70)])
            d.rectangle((x * k, (GROUND - bh) * k, (x + bw) * k, GROUND * k), fill=col)
            for wy in range(int(GROUND - bh + 40), GROUND - 140, 110):
                for wx in range(int(x + 30), int(x + bw - 70), 90):
                    lit = r.random() < (0.2 if day else 0.55)
                    d.rectangle((wx * k, wy * k, (wx + 54) * k, (wy + 70) * k),
                                fill=(255, 214, 120) if lit else ((150, 190, 230) if day else (30, 30, 50)))
            # дверь/витрина
            d.rectangle(((x + bw / 2 - 50) * k, (GROUND - 150) * k, (x + bw / 2 + 50) * k, GROUND * k), fill=(40, 34, 40))
            x += bw + 30
        d.rectangle((0, GROUND * k, BGW * k, (GROUND + 90) * k), fill=(150, 150, 160) if day else (70, 70, 84))
        d.rectangle((0, (GROUND + 90) * k, BGW * k, H * k), fill=(60, 60, 70) if day else (34, 34, 42))
        for x in range(60, BGW, 260):
            d.rectangle((x * k, (GROUND + 210) * k, (x + 130) * k, (GROUND + 226) * k), fill=(230, 230, 230))
        for x in range(200, BGW, 560):  # фонари
            d.rectangle((x * k, (GROUND - 620) * k, (x + 16) * k, GROUND * k), fill=(40, 40, 50))
            d.rounded_rectangle(((x - 40) * k, (GROUND - 640) * k, (x + 56) * k, (GROUND - 610) * k), 10 * k, fill=(40, 40, 50))
    im = aa(f, BGW, H)
    if not day:  # свет фонарей
        gl = Image.new("RGBA", (BGW, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        for x in range(200, BGW, 560):
            gd.ellipse((x - 120, GROUND - 700, x + 140, GROUND - 480), fill=(255, 220, 140, 120))
            gd.polygon([(x - 30, GROUND - 610), (x + 46, GROUND - 610), (x + 200, GROUND), (x - 180, GROUND)], fill=(255, 220, 140, 40))
        im.alpha_composite(gl.filter(ImageFilter.GaussianBlur(30)))
    return im


def bg_shop(k):
    def f(d, k):
        d.rectangle((0, 0, BGW * k, H * k), fill=(240, 226, 200))
        d.rectangle((0, GROUND * k, BGW * k, H * k), fill=(200, 190, 175))
        r = random.Random(2)
        for sy in (520, 760, 1000):
            d.rectangle((60 * k, sy * k, (BGW - 60) * k, (sy + 18) * k), fill=(150, 110, 80))
            x = 80
            while x < BGW - 120:
                bw, bh = r.uniform(50, 90), r.uniform(90, 180)
                d.rounded_rectangle((x * k, (sy - bh) * k, (x + bw) * k, sy * k), 8 * k,
                                    fill=r.choice([(230, 80, 70), (80, 160, 230), (250, 200, 60), (90, 190, 110), (180, 110, 210)]))
                x += bw + 12
        d.rounded_rectangle((420 * k, 1240 * k, 1500 * k, GROUND * k), 10 * k, fill=(120, 86, 66))
        d.rectangle((420 * k, 1240 * k, 1500 * k, 1280 * k), fill=(160, 120, 90))
        d.rounded_rectangle((900 * k, 1100 * k, 1080 * k, 1250 * k), 14 * k, fill=(40, 40, 50))
    return aa(f, BGW, H)


def bg_atm(k):
    def f(d, k):
        d.rectangle((0, 0, BGW * k, H * k), fill=(150, 150, 160))
        for y in range(0, GROUND, 120):
            d.line((0, y * k, BGW * k, y * k), fill=(140, 140, 150), width=4 * k)
        d.rectangle((0, GROUND * k, BGW * k, H * k), fill=(90, 90, 100))
        for x0 in (780,):
            d.rounded_rectangle((x0 * k, 760 * k, (x0 + 420) * k, GROUND * k), 20 * k, fill=(40, 80, 160))
            d.rounded_rectangle(((x0 + 50) * k, 860 * k, (x0 + 370) * k, 1080 * k), 12 * k, fill=(30, 30, 40))
            d.rectangle(((x0 + 90) * k, 1180 * k, (x0 + 330) * k, 1200 * k), fill=(20, 20, 26))
            for i in range(3):
                for j in range(3):
                    d.rounded_rectangle(((x0 + 120 + i * 64) * k, (1240 + j * 60) * k, (x0 + 170 + i * 64) * k,
                                         (1284 + j * 60) * k), 6 * k, fill=(200, 200, 210))
            d.rounded_rectangle((x0 * k, 680 * k, (x0 + 420) * k, 750 * k), 12 * k, fill=(230, 60, 60))
    im = aa(f, BGW, H)
    ImageDraw.Draw(im).text((990 - font(BLACK, 46).getlength("БАНКОМАТ") / 2, 688), "БАНКОМАТ", font=font(BLACK, 46), fill=(255, 255, 255))
    return im


def bg_space(k):
    def f(d, k):
        d.rectangle((0, 0, BGW * k, H * k), fill=(6, 8, 22))
        r = random.Random(9)
        for _ in range(260):
            x, y, s = r.uniform(0, BGW), r.uniform(0, H), r.uniform(1, 3.5)
            d.ellipse(((x - s) * k, (y - s) * k, (x + s) * k, (y + s) * k), fill=(230, 230, 255))
        d.ellipse((-600 * k, 1250 * k, (BGW + 600) * k, 3400 * k), fill=(40, 110, 200))
        d.ellipse((-300 * k, 1420 * k, 500 * k, 1700 * k), fill=(70, 160, 90))
        d.ellipse((800 * k, 1380 * k, 1400 * k, 1600 * k), fill=(70, 160, 90))
    return aa(f, BGW, H)


def bg_server(k):
    def f(d, k):
        d.rectangle((0, 0, BGW * k, H * k), fill=(14, 18, 30))
        d.rectangle((0, GROUND * k, BGW * k, H * k), fill=(24, 28, 40))
        for x in range(40, BGW, 250):
            d.rounded_rectangle((x * k, 500 * k, (x + 200) * k, GROUND * k), 10 * k, fill=(34, 40, 58))
            for y in range(540, GROUND - 40, 60):
                d.rectangle(((x + 20) * k, y * k, (x + 180) * k, (y + 40) * k), fill=(24, 28, 42))
    return aa(f, BGW, H)


def bg_park(k):
    def f(d, k):
        for y in range(0, GROUND, 8):
            c = (int(130 + 90 * y / GROUND), int(200 + 40 * y / GROUND), 250)
            d.rectangle((0, y * k, BGW * k, (y + 8) * k), fill=c)
        d.ellipse((1100 * k, 220 * k, 1300 * k, 420 * k), fill=(255, 230, 120))
        r = random.Random(5)
        d.rectangle((0, (GROUND - 200) * k, BGW * k, H * k), fill=(110, 190, 100))
        for x in range(-50, BGW, 230):
            h = r.uniform(380, 520)
            d.rectangle(((x + 90) * k, (GROUND - 200 - h * 0.5) * k, (x + 120) * k, (GROUND - 160) * k), fill=(120, 80, 50))
            d.ellipse((x * k, (GROUND - 200 - h) * k, (x + 210) * k, (GROUND - 200 - h * 0.35) * k), fill=(60, 150, 70))
        d.polygon([(560 * k, (GROUND - 200) * k), (940 * k, (GROUND - 200) * k), (1300 * k, H * k), (200 * k, H * k)], fill=(220, 200, 160))
    return aa(f, BGW, H)


BGS = {"room": bg_room, "street": bg_street, "shop": bg_shop, "atm": bg_atm, "space": bg_space,
       "server": bg_server, "park": bg_park, "day": lambda k: bg_street(k, True)}
_bg_cache = {}


def get_bg(name):
    if name not in _bg_cache:
        _bg_cache[name] = BGS.get(name, bg_room)(2)
    return _bg_cache[name]


# ---------- эффекты ----------

def hacker_fig():
    def f(d, k):
        d.chord((40 * k, 0, 360 * k, 420 * k), 180, 360, fill=(14, 14, 20))
        d.rounded_rectangle((40 * k, 200 * k, 360 * k, 900 * k), 80 * k, fill=(14, 14, 20))
        d.ellipse((90 * k, 90 * k, 310 * k, 330 * k), fill=(4, 4, 8))
        d.ellipse((140 * k, 190 * k, 180 * k, 216 * k), fill=(255, 40, 40))
        d.ellipse((220 * k, 190 * k, 260 * k, 216 * k), fill=(255, 40, 40))
    return aa(f, 400, 900)


_hk = None


def think_bubble(e):
    b = aa(lambda d, k: (d.ellipse((0, 0, 300 * k, 260 * k), fill=(255, 255, 255)),
                         d.ellipse((40 * k, 250 * k, 90 * k, 300 * k), fill=(255, 255, 255)),
                         d.ellipse((10 * k, 300 * k, 40 * k, 330 * k), fill=(255, 255, 255))), 300, 330)
    em = emoji_img(e, 170)
    b.alpha_composite(em, (int(150 - em.width / 2), int(130 - em.height / 2)))
    return b


def neon_sign(text):
    return dark.glow(dark.fit_text(text.upper(), 96, 900, (255, 236, 170)), (255, 150, 30), 18, 2)


# ---------- субтитры: крупные слова сверху, белые с обводкой ----------

CAP_Y = 330


def draw_caption(fr, cap, t, first):
    size = 104
    f = font(BLACK, size)
    words = cap[2]
    full = " ".join(w.upper() for _, _, w in words)
    while text_width(full, f) > 960 and size > 60:
        size -= 6; f = font(BLACK, size)
    sp = f.getlength(" ")
    ws = [(a, b, w.upper(), text_width(w.upper(), f)) for a, b, w in words
          if t >= (0 if first and cap[0] < 0.5 else a - 0.05)]
    tot = sum(x[3] for x in ws) + sp * (len(ws) - 1)
    x = (W - tot) / 2
    for a, b, w, ww in ws:
        on = a <= t < b
        lay = Image.new("RGBA", (int(ww + 60), int(size * 1.5)), (0, 0, 0, 0))
        draw_mixed(lay, (30, 10), w, f, dark.GOLD if on else (255, 255, 255), stroke=10, stroke_fill=(10, 10, 14))
        fr.alpha_composite(lay, (int(x - 30), int(CAP_Y - lay.height / 2)))
        x += ww + sp


# ---------- сборка ----------

# Для сценариев без поля "film" (обычные факты) сцены придумываются сами:
# хук — герой с телефоном, дальше идёт по улице, сидит за компьютером, гуляет, в конце вопрос зрителю.
AUTO = [
    [dict(bg="room", act="phone", mood="worried"), dict(bg="street", act="walk", mood="neutral"),
     dict(bg="room", act="sit", mood="shock", screen="code"), dict(bg="day", act="stand", mood="happy"),
     dict(bg="room", act="stand", mood="happy")],
    [dict(bg="street", act="phone", mood="shock"), dict(bg="room", act="sit", mood="neutral", screen="ok"),
     dict(bg="day", act="walk", mood="happy"), dict(bg="shop", act="stand", mood="worried"),
     dict(bg="street", act="stand", mood="happy")],
    [dict(bg="park", act="phone", mood="worried"), dict(bg="room", act="sit", mood="worried", screen="code"),
     dict(bg="street", act="walk", mood="neutral"), dict(bg="room", act="shock", mood="shock"),
     dict(bg="park", act="stand", mood="happy")],
]


def auto_scene(sc, i, n, seed):
    plan = AUTO[seed % len(AUTO)]
    f = dict(plan[-1] if i == n - 1 else plan[min(i, len(plan) - 2)])
    h = sc.get("hero") or []
    if h and h[0] == "big" and len(h) > 1:
        f["sign"] = str(h[1]) + ((" " + h[2]) if len(h) > 2 and h[2] and len(str(h[1]) + h[2]) < 16 else "")
    elif h and h[0] in ("emoji",) and len(h) > 1:
        f["think"] = h[1]
    return f


def scene_of(sc, i=0, n=1, seed=0):
    f = dict(sc.get("film") or auto_scene(sc, i, n, seed))
    f.setdefault("bg", "room"); f.setdefault("act", "stand"); f.setdefault("mood", "neutral")
    f.setdefault("prop", "phone" if f["act"] == "phone" else "none")
    return f


def build(v, out_path, work):
    global _hk
    os.makedirs(work, exist_ok=True)
    CTA.clear(); CTA.update(CTA_DEFAULT, **(v.get("cta") or {}))
    accent = tuple(v.get("accent") or (255, 120, 60))
    shirt = tuple(int(c * 0.85) for c in accent)
    v = drawn.place_banner(v)
    timeline, total, wav_path = engine.make_audio(v, work)
    seed = sum(map(ord, v.get("id", "")))
    plain = [sc for sc in timeline if not sc.get("banner")]
    for sc in timeline:
        sc["caps"] = dark.captions(sc)
        sc["F"] = None if sc.get("banner") else scene_of(sc, plain.index(sc), len(plain), seed)
    desks = {}
    thinks = {}
    signs = {}
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
        lt = max(0, t - sc["start"])
        dur = max(0.5, sc["end"] - sc["start"])
        first = si == 0
        if sc.get("banner"):
            if frozen is None:
                fz = last_fr.filter(ImageFilter.GaussianBlur(6))
                fz.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 150)))
                frozen = fz
            fr = Image.new("RGBA", (W, H))
            drawn.draw_banner(fr, frozen, lt, dur, t)
            ff.stdin.write(fr.convert("RGB").tobytes())
            continue
        frozen = None
        F = sc["F"]
        act = F["act"]
        fx = F.get("fx") or []
        fx = set([fx] if isinstance(fx, str) else fx)
        bg = get_bg(F["bg"])
        # камера: медленный проезд по фону (на ходьбе быстрее)
        pan = (BGW - W) * (0.5 + (0.5 if act in ("walk", "run") else 0.18) * (lt / dur - 0.5) * (1 if si % 2 else -1))
        fr = bg.crop((int(pan), 0, int(pan) + W, H)).copy()

        # толпа сзади
        if "crowd" in fx:
            for i in range(9):
                x = 80 + i * 120 + 20 * math.sin(i * 3.1)
                h = 330 + (i % 3) * 30
                ImageDraw.Draw(fr).rounded_rectangle((x, GROUND - h, x + 90, GROUND), 40, fill=(30, 30, 44, 255))
                ImageDraw.Draw(fr).ellipse((x + 10, GROUND - h - 70, x + 80, GROUND - h), fill=(30, 30, 44, 255))

        # герой
        pose = pose_for(act, F["mood"], t, lt, F["prop"])
        img, hands = hero(pose, shirt)
        scale = 1.2
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.BILINEAR)
        hands = [(x * scale, y * scale) for x, y in hands]
        hx = W / 2
        if act in ("walk", "run"):
            hx = W * (0.3 + 0.4 * min(1, lt / dur))
        jump = 0
        if act == "shock":
            jump = -60 * math.sin(min(1, lt / 0.35) * math.pi)
        bob = 6 * math.sin(lt * 18) if act in ("walk", "run") else 4 * math.sin(t * 2)
        if act == "sit":
            top = GROUND - img.height + 190
            hx = W * 0.36
        else:
            top = GROUND - img.height + 24 + jump + bob
        ox = int(hx - img.width / 2)
        if F.get("hero", True):
            fr.alpha_composite(img, (ox, int(top)))
        hand = (ox + hands[1][0], top + hands[1][1])
        scr_col = {"red": (230, 60, 60), "off": (20, 20, 26), "code": (30, 200, 90)}.get(F.get("screen"), (110, 190, 255))
        if F["prop"] != "none" and act != "sit" and F.get("hero", True):
            draw_prop(fr, F["prop"], hand, scr_col, t)
        if act == "sit":
            key = F.get("screen", "ok")
            if key not in desks:
                desks[key] = desk_fg(key)
            fr.alpha_composite(desks[key], (0, GROUND - 1560))

        if "hacker" in fx:
            if _hk is None:
                _hk = hacker_fig()
            a = ease_out(min(1, lt / 0.6))
            fr.alpha_composite(dark.faded(_hk, a), (int(W - 330 + (1 - a) * 200), GROUND - 900 + 30))
        if "money" in fx:
            r = random.Random(si)
            for i in range(10):
                p = (lt * 0.8 + i / 10) % 1
                x = hand[0] + (r.uniform(-1, 1) * 500) * p
                y = hand[1] - 900 * p + 200 * p * p
                note = Image.new("RGBA", (120, 60), (90, 190, 110, 255))
                ImageDraw.Draw(note).ellipse((45, 15, 75, 45), outline=(40, 120, 60), width=4)
                note = note.rotate(p * 400 + i * 40, expand=True)
                fr.alpha_composite(dark.faded(note, 1 - p), (int(x), int(y)))
        if F.get("think"):
            e = F["think"]
            if e not in thinks:
                thinks[e] = think_bubble(e)
            a = 1 if first else ease_out_back(min(1, max(0, lt - 0.3) / 0.4))
            if a > 0.02:
                b = dark.scaled(thinks[e], a)
                fr.alpha_composite(b, (int(hx + 120), int(top - 120 + 8 * math.sin(t * 2.5))))
        if "nosignal" in fx:
            ic = emoji_img("📵", 150)
            a = 0.5 + 0.5 * abs(math.sin(t * 4))
            fr.alpha_composite(dark.faded(ic, a), (int(hx - 260), int(top - 60)))
        if F.get("sign"):
            s = F["sign"]
            if s not in signs:
                signs[s] = neon_sign(s)
            fl = 1 if (t * 7) % 5 > 0.3 else 0.4
            dark.paste_c(fr, dark.faded(signs[s], fl), W / 2, 560)
        if "dark" in fx:
            fr.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 10, 140)))
        if "alarm" in fx:
            a = int(70 + 60 * abs(math.sin(t * 5)))
            fr.alpha_composite(Image.new("RGBA", (W, H), (230, 20, 20, a)))

        # камера: наезд + тряска на шоке/тревоге
        z = 1.0 + 0.06 * (lt / dur) + (0.04 if (next((i for i, c in enumerate(sc["caps"]) if c[0] <= t < c[1]), 0) % 2) else 0)
        if z > 1.002:
            zw, zh = int(W * z), int(H * z)
            fr = fr.resize((zw, zh), Image.BILINEAR).crop(((zw - W) // 2, (zh - H) // 2, (zw - W) // 2 + W, (zh - H) // 2 + H))
        if (act == "shock" and lt < 0.5) or "alarm" in fx:
            sx = int(10 * math.sin(t * 70)) if act == "shock" and lt < 0.5 else int(4 * math.sin(t * 50))
            fr = fr.transform((W, H), Image.AFFINE, (1, 0, sx, 0, 1, 0))
        if "glitch" in fx and (t * 3) % 1 < 0.25:
            r = random.Random(int(t * 30))
            for _ in range(6):
                y = r.randint(0, H - 60); hgt = r.randint(10, 60); dx = r.randint(-40, 40)
                strip = fr.crop((0, y, W, y + hgt))
                fr.paste(strip, (dx, y))
        if si and lt < 0.12:  # склейка: короткая вспышка в чёрное
            fr.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(230 * (1 - lt / 0.12)))))
        # виньетка сверху под субтитры
        fr.alpha_composite(TOPSHADE)
        fr.alpha_composite(brand, (60, 110))
        d = ImageDraw.Draw(fr)
        d.rounded_rectangle((60, 1880, W - 60, 1888), 4, fill=(50, 50, 60))
        d.rounded_rectangle((60, 1880, 60 + int((W - 120) * t / total), 1888), 4, fill=dark.GOLD)

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
        if left < 0.3 and fi > 0:
            fr = Image.blend(fr, first_fr, 1 - left / 0.3)
        last_fr = fr.copy()
        ff.stdin.write(fr.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()
    if ff.returncode != 0:
        raise RuntimeError("ffmpeg не смог собрать видео")
    engine.finish(out_path)
    return out_path, total


def _topshade():
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    for y in range(0, 560):
        d.line((0, y, W, y), fill=(0, 0, 0, int(150 * (1 - y / 560))))
    return g


TOPSHADE = _topshade()
