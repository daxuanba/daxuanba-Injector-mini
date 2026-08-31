# -*- coding: utf-8 -*-
"""生成大轩巴入库器 mini 图标"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
OUT = BASE / 'assets' / 'icon.ico'
OUT.parent.mkdir(exist_ok=True)

BG = '#f1c40f'      # 大轩巴黄
FG = '#0b0b0b'      # 黑字
SIZES = [256, 128, 64, 48, 32, 16]

images = []
font_path = r"C:\Windows\Fonts\msyhbd.ttc"

for size in SIZES:
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 黄色圆形背景
    margin = max(2, size // 32)
    draw.ellipse([margin, margin, size - margin, size - margin], fill=BG)
    # 居中 DX 文字
    text = "DX"
    font_size = int(size * 0.55)
    font = ImageFont.truetype(font_path, font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), text, fill=FG, font=font)
    # 小尺寸转成 RGBA 但保存为 ICO 需要
    images.append(img)

images[0].save(OUT, format='ICO', sizes=[(s, s) for s in SIZES])
print(f'图标已生成: {OUT}')
