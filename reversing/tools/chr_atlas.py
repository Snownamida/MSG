#!/usr/bin/env python3
"""把 ROM 的全部 CHR bank(4KB=256 tiles)画成图集，肉眼找字模/图案——不再猜 bank。

用法: python3 preview/chr_atlas.py <rom> <输出前缀> [起始bank] [结束bank]
每张图 32 个 bank(8列×4行)，bank 内 16×16 tiles，2 倍放大，bank 号标在左上。
"""
import sys
from PIL import Image, ImageDraw

rom = open(sys.argv[1], "rb").read()
prefix = sys.argv[2]
CHR0 = 0x10 + 512 * 1024
nbank = (len(rom) - CHR0) // 4096
b0 = int(sys.argv[3]) if len(sys.argv) > 3 else 0
b1 = int(sys.argv[4]) if len(sys.argv) > 4 else nbank
PAL = [(0, 0, 0), (100, 100, 100), (180, 180, 180), (255, 255, 255)]
S = 2          # 放大倍数
BW = 128 * S   # bank 图宽
LB = 14        # 标签高


def bank_img(b):
    im = Image.new("RGB", (128, 128), (0, 0, 0))
    px = im.load()
    base = CHR0 + b * 4096
    for t in range(256):
        tx, ty = (t % 16) * 8, (t // 16) * 8
        off = base + t * 16
        for y in range(8):
            p0, p1 = rom[off + y], rom[off + y + 8]
            for x in range(8):
                bit = 7 - x
                c = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
                px[tx + x, ty + y] = PAL[c]
    return im.resize((BW, BW), Image.NEAREST)


banks = list(range(b0, min(b1, nbank)))
PER = 32
for page, i in enumerate(range(0, len(banks), PER)):
    grp = banks[i:i + PER]
    cols, rows = 8, (len(grp) + 7) // 8
    sheet = Image.new("RGB", (cols * (BW + 4), rows * (BW + LB + 4)), (30, 30, 60))
    dr = ImageDraw.Draw(sheet)
    for j, b in enumerate(grp):
        x, y = (j % cols) * (BW + 4), (j // cols) * (BW + LB + 4)
        dr.text((x + 2, y + 1), f"bank {b} (${b:02X})", fill=(255, 255, 0))
        sheet.paste(bank_img(b), (x, y + LB))
    out = f"{prefix}_p{page}.png"
    sheet.save(out)
    print(out, f"banks {grp[0]}-{grp[-1]}")
