"""앱 아이콘(assets/icon.ico, assets/icon.png)을 생성합니다. 실행: python tools/make_icon.py

크기마다 4배로 크게 그린 뒤 줄여서 경계를 부드럽게 하고,
32px 이하에서는 눈금을 빼고 바늘을 굵게 그려 작은 아이콘에서도 알아볼 수 있게 합니다.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
SCALE = 4

TOP = (86, 180, 249)      # 하늘색
BOTTOM = (59, 95, 224)    # 진한 파랑
FACE = (255, 255, 255)
HAND = (38, 52, 99)       # 남색
ACCENT = (255, 138, 61)   # 주황 (분침 끝, 가운데 점)


def _gradient(size):
    """왼쪽 위에서 오른쪽 아래로 갈수록 진해지는 배경."""
    grad = Image.new("RGB", (size, size))
    px = grad.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
    return grad


def _hand(draw, c, angle_deg, length, width, color):
    a = math.radians(angle_deg - 90)
    end = (c + length * math.cos(a), c + length * math.sin(a))
    draw.line((c, c, *end), fill=color, width=width)
    r = width / 2
    draw.ellipse((end[0] - r, end[1] - r, end[0] + r, end[1] + r), fill=color)


def render(size):
    small = size <= 32
    n = size * SCALE
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))

    # 둥근 사각형 배경
    mask = Image.new("L", (n, n), 0)
    pad = round(n * 0.04)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, n - pad, n - pad), radius=round(n * 0.23), fill=255)
    img.paste(_gradient(n), (0, 0), mask)

    c = n / 2
    face_r = n * (0.36 if small else 0.33)

    # 시계판 아래 은은한 그림자
    if not small:
        shadow = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        off = n * 0.02
        ImageDraw.Draw(shadow).ellipse((c - face_r, c - face_r + off, c + face_r, c + face_r + off), fill=(20, 30, 80, 90))
        img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(n * 0.02)))

    draw = ImageDraw.Draw(img)
    draw.ellipse((c - face_r, c - face_r, c + face_r, c + face_r), fill=FACE)

    if not small:
        for i in range(12):
            a = math.radians(i * 30 - 90)
            major = i % 3 == 0
            outer = face_r * 0.86
            inner = face_r * (0.70 if major else 0.77)
            w = round(n * (0.022 if major else 0.012))
            draw.line((c + inner * math.cos(a), c + inner * math.sin(a),
                       c + outer * math.cos(a), c + outer * math.sin(a)),
                      fill=HAND if major else (150, 160, 190), width=w)

    # 10시 10분: 시침은 짧고 굵게, 분침은 끝을 주황색으로
    hand_w = round(n * (0.075 if small else 0.045))
    _hand(draw, c, 305, face_r * 0.48, hand_w, HAND)
    _hand(draw, c, 60, face_r * (0.70 if small else 0.66), round(hand_w * 0.8), ACCENT)

    dot = n * (0.06 if small else 0.045)
    draw.ellipse((c - dot, c - dot, c + dot, c + dot), fill=HAND)
    if not small:
        dot2 = dot * 0.45
        draw.ellipse((c - dot2, c - dot2, c + dot2, c + dot2), fill=ACCENT)

    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    images = [render(s) for s in ICO_SIZES]
    largest = images[-1]
    largest.save(os.path.join(ASSETS, "icon.png"))
    largest.save(os.path.join(ASSETS, "icon.ico"), format="ICO",
                 sizes=[(s, s) for s in ICO_SIZES], append_images=images[:-1])
    print("saved", ASSETS)


if __name__ == "__main__":
    main()
