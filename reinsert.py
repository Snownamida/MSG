#!/usr/bin/env python3
"""回写编码器 v1（里程碑 1：正确回写单句，无重叠副作用）。

与 patch_poc 的就地覆写不同，本工具把中文数据**重建到空闲区**：
- 每个中文字征用一个「空 block 槽」（原版未引用的 block），其字符串放 PRG 空闲区；
- 用 text 反解让该 block 的 text_pointer 指向空闲区的新串（不碰任何共享字节）；
- 句子的块串**就地重建**（块串句间不重叠，安全）——保留名字「结构，内容换成新 block；
- 字模写进该场景用到的字库 bank。
这样彻底避开字典字符串重叠导致的「得觉错位」。

当前仍是 8×8（tile 恒等、单字节码位 ≤256 字），够单句/短场景验证；
全量 + 16×16 需配合引擎改造（见 REVERSING.md 路线）。
"""
from PIL import Image, ImageDraw, ImageFont
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"
OUT = "MSG-zh-test.nes"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
CHR0 = 0x10 + 512 * 1024
TEXT_TABLE = 0x3D5C          # block → text 表（每 block 3 字节）
STRDATA = 0x4A010            # string_pointer 的基址
FONT_BANKS = [0, 11, 48]     # 标题/海边/开场机甲 场景字库 bank
STR_FREE = (0x06010, 0x14239)  # 存放中文字符串的空闲区

TARGET = 62
TRANS = "这就是这次从阿源那儿买来的那台吗总觉得挺有意思的呢"


def solve_text(ptr: int, length: int) -> bytes:
    """反解 text 3 字节，使 string_pointer(text) == (ptr, length)。"""
    for b1 in range(256):
        for b3 in range(256):
            if ((b1 >> 6) << 3) + (b3 >> 5) != length:
                continue
            base = (((b1 & 0x3F) - 0x2A) << 13) + (((b3 & 0x1F) ^ 0xA0) << 8)
            b2 = ptr - STRDATA - base
            if 0 <= b2 <= 255:
                return bytes([b1, b2, b3])
    raise ValueError(f"无法反解 text: ptr={ptr:X} len={length}")


def glyph_tile(ch: str) -> bytes:
    """中文字 → 8×8 tile。匹配原字库位平面：plane0 全 FF，plane1 笔画=位 0、背景=位 1。"""
    S = 32
    hi = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(hi)
    f = ImageFont.truetype(FONT, int(S * 0.98))
    bb = d.textbbox((0, 0), ch, font=f)
    d.text(((S - (bb[2] - bb[0])) // 2 - bb[0], (S - (bb[3] - bb[1])) // 2 - bb[1]), ch, fill=255, font=f)
    sm = hi.resize((8, 8), Image.BILINEAR).point(lambda v: 1 if v > 55 else 0)
    p1 = bytearray([0xFF] * 8)
    for r in range(8):
        for c in range(8):
            if sm.getpixel((c, r)):
                p1[r] &= 0xFF ^ (1 << (7 - c))
    return bytes([0xFF] * 8) + bytes(p1)


def main() -> None:
    rom = bytearray(open(SRC, "rb").read())
    R = Rom(bytes(rom))

    # 收集被引用的 block，求空 block 槽（优先双字节区，块串里统一占 2 字节）
    used = set()
    for n in range(1, 2782):
        raw = R.sentence_blocks(n)
        i = 0
        while i < len(raw):
            b = raw[i]
            if b in TRIPLE_BYTE: i += 3
            elif b in DOUBLE_BYTE: i += 2
            elif b == 0x00: i += 1
            elif b < 0x80: used.add(b); i += 1
            else: used.add((b << 8) + raw[i + 1]); i += 2
    # 单字节 block 合法值 = 0x20–0x7F（0x00 终止、0x01–0x1F 与双/三字节控制码冲突，均不可用）
    free_dbl = [b for b in range(0x8080, 0x8B58) if b not in used]
    free_sgl = [b for b in range(0x20, 0x80) if b not in used]
    free_blocks = free_dbl + free_sgl
    print(f"合法空 block 槽: 双字节 {len(free_dbl)} + 单字节 {len(free_sgl)} = {len(free_blocks)}")
    need = len(dict.fromkeys(TRANS))
    if need > len(free_blocks):
        raise SystemExit(f"译文需 {need} 个唯一字，但只有 {len(free_blocks)} 个合法空槽——需重用共享 block 或扩表")

    # 分配：每个唯一中文字 → (空 block, tile 码位)；写字模 + 空闲区串 + text 表项
    str_p = STR_FREE[0]
    tile_code = 0xB0
    assigned: dict[str, int] = {}   # 字 → 双字节 block 编号
    for ch in dict.fromkeys(TRANS):        # 去重保序
        blk = free_blocks.pop(0)
        code = tile_code; tile_code += 1
        # 字模写进各场景字库 bank
        g = glyph_tile(ch)
        for bank in FONT_BANKS:
            base = CHR0 + bank * 4096 + code * 16
            rom[base:base + 16] = g
        # 空闲区放该字的 PPU 串（单字节 = tile 码位）
        rom[str_p] = code
        text3 = solve_text(str_p, 1)
        str_p += 1
        # 写 block → text 表项（用 msgtool 的换算，单字节 block 会先 +0x8000）
        tp = R.text_pointer(blk)
        rom[tp:tp + 3] = text3
        assigned[ch] = blk

    # 句 62 块串就地重建：保留名字「(block 0x21) + 新中文 block 序列 + 0x00
    s3 = R.read3(R.sentence_pointer(TARGET))
    bs_addr = R.block_string_pointer(s3)
    orig_len = len(R.sentence_blocks(TARGET))
    new = bytearray([0x21])                # block 0x21 = "エリナ 「"
    for ch in TRANS:
        blk = assigned[ch]
        new += bytes([blk]) if blk < 0x80 else bytes([blk >> 8, blk & 0xFF])
    new += bytes([0x00])
    assert len(new) <= orig_len, f"新块串 {len(new)} > 原 {orig_len}，放不下"
    new += bytes([0x00]) * (orig_len - len(new))  # 尾部补 0，不越界到邻句
    rom[bs_addr:bs_addr + orig_len] = new

    open(OUT, "wb").write(rom)
    print(f"回写句 {TARGET}：{len(assigned)} 个中文字 → 空 block；字符串占空闲区 {STR_FREE[0]:05X}..{str_p:05X}")
    print("码位:", " ".join(f"{ord(c):#0}" and f"{assigned[c]:04X}={c}" for c in assigned))

    # ── round-trip 验证：patched ROM 解出的句 62 码位流 == 译文 ──
    P = Rom(bytes(rom))
    inv = {}   # tile 码位 → 中文字
    for ch, blk in assigned.items():
        ppu = P.block_ppu(blk)
        inv[ppu[0]] = ch
    raw = P.sentence_blocks(TARGET)
    got, i = [], 0
    while i < len(raw):
        b = raw[i]
        if b in TRIPLE_BYTE: i += 3
        elif b in DOUBLE_BYTE: i += 2
        elif b == 0x00: i += 1
        elif b < 0x80:
            for c in P.block_ppu(b):
                if c not in (0x0E, 0x0F, 0x00): got.append(inv.get(c, "·"))
            i += 1
        else:
            blk = (b << 8) + raw[i + 1]
            for c in P.block_ppu(blk):
                if c not in (0x0E, 0x0F, 0x00): got.append(inv.get(c, "·"))
            i += 2
    decoded = "".join(got)
    print(f"\n句 {TARGET} 回写后解码: {decoded}")
    print("round-trip:", "✓ 译文完整还原" if decoded.endswith(TRANS) else "✗ 不一致")

    # ── 副作用检查：随机若干句解码应与 patch 前完全一致 ──
    import random; random.seed(7)
    changed = 0
    for n in random.sample(range(1, 2782), 40):
        if n == TARGET: continue
        if R.sentence_text(n) != P.sentence_text(n):
            changed += 1
    print(f"副作用检查: 抽查 40 句，{changed} 句被意外改动", "✓ 零副作用" if changed == 0 else "✗")


if __name__ == "__main__":
    main()
