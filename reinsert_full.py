#!/usr/bin/env python3
"""全量回写工具（Phase 1：通用 token 编码器 + 单 bank 字库 + round-trip 自验）。

消费翻译串（中文 + 原样保留的 ~XXXX~ 控制码 + 保留的特殊图标），重建三层指针链，
把整份（或子集）译文写进 ROM。相比里程碑2/4 的单句 demo，这里是**任意句、任意文本**的编码器。

规范格式（与 translation/ 的译文一致）：
- `~HH~` / `~HHHH~` / `~HHHHHH~`：块串层控制码，原样还原为字节，不占字模。
- 特殊图标 token（`(特1)(特2)(特3)(爱心)(音符)(冒汗)★`）：复用 bank128 里的原 tile（fusion 画不出）。
- 其余每个可见字符：分配一个 fusion-8px 字模 tile（原版共享汉字如 忠/日/的 也各给新 tile，简单统一）。

编码策略（**每字一个共享 block**，学里程碑 2；不是"每段一块"——那样 block 数=段数会爆表）：
- 每个唯一字形（中文字/图标）→ 一个双字节 block，其 PPU 串 = 单码位 [tile 码]，全篇复用。
- 句子块串 = 控制码字节 + 字形 block 序列。block 数 = 唯一字形数（~1500 < 可用 ~2868 槽）。
- 全量回写=替换整个剧本 → 原字典 block/文本区/块串区全部回收（full-reclaim 模式）。

Phase 1 已验证：编码器 + round-trip。Phase 2 待解：多 bank 字库切换（>256 字形需按 bank 切 CHR）。
"""
import re
from PIL import Image, ImageDraw, ImageFont
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE

SRC = "Metal Slader Glory (Japan).nes"
FONT = "fonts/fusion-pixel-8px-monospaced-zh_hans.otf"
CHR0 = 0x10 + 512 * 1024; NEWBANK = 128

# 特殊图标 → 复用原 PPU 码（bank128=bank0 拷贝里就有这些 tile）
ICON_REUSE = {
    "(特1)": 0x15, "(特2)": 0x16, "(特3)": 0x18,
    "(爱心)": 0x19, "★": 0x1A, "(音符)": 0x1B, "(冒汗)": 0x09,
}
ICON_RE = re.compile("|".join(re.escape(k) for k in
                     sorted(ICON_REUSE, key=len, reverse=True)))
CTRL_RE = re.compile(r"~([0-9A-Fa-f]{2,6})~")

_FONT = ImageFont.truetype(FONT, 8)


def glyph8x8(ch):
    im = Image.new("L", (8, 8), 0); d = ImageDraw.Draw(im); d.fontmode = "1"
    bb = d.textbbox((0, 0), ch, font=_FONT)
    d.text(((8 - (bb[2] - bb[0])) // 2 - bb[0], 0), ch, fill=255, font=_FONT)
    p1 = bytearray([0xFF] * 8)
    for r in range(8):
        for c in range(8):
            if im.getpixel((c, r)) > 127: p1[r] &= 0xFF ^ (1 << (7 - c))
    return bytes([0xFF] * 8) + bytes(p1)


def tokenize(s):
    """译文串 → token 列表：('ctrl', bytes) | ('icon', code) | ('ch', 字符)。"""
    out = []; i = 0
    while i < len(s):
        m = CTRL_RE.match(s, i)
        if m:
            h = m.group(1)
            if len(h) % 2: raise ValueError(f"控制码奇数位: ~{h}~")
            out.append(("ctrl", bytes.fromhex(h))); i = m.end(); continue
        m = ICON_RE.match(s, i)
        if m:
            out.append(("icon", ICON_REUSE[m.group(0)])); i = m.end(); continue
        out.append(("ch", s[i])); i += 1
    return out


class Encoder:
    """把译文回写进 ROM 副本。每字共享 block + 三层指针重建。

    full_reclaim=True：全量替换整个剧本，原字典 block / 文本区 / 块串区全部可用。
    """
    # 布局（避免四结构互撞）：句子表 0x1CC5-0x3D5C；文本表 0x3D5C-最多 0x5F58（全 block 范围）；
    # PPU 串区放文本表之后、块串之前；块串区在扩 PRG 里（block_string_pointer 可达至 0x10E00F）。
    TEXT_FREE = (0x5F60, 0x76000)      # PPU 串区（1 码位/字，string_pointer 可达）
    BLK_FREE = (0x76000, 0x100010)     # 块串区（扩 PRG 到 1MB）

    def __init__(self, src=SRC, full_reclaim=True):
        self.rom = bytearray(open(src, "rb").read())
        self.R = Rom(bytes(self.rom))
        # 扩 PRG→1MB（块串空间）、扩 CHR→1MB、拷贝 bank0、B 命门
        self.rom[4] = 64            # PRG 页数 512KB→1MB（16KB/页 × 64）
        self.rom[5] = 128           # CHR 512KB→1MB
        prg = bytearray(self.rom[0x10:0x10 + 0x80000]) + bytes(0x80000)
        chr_ = bytearray(self.rom[0x10 + 0x80000:0x10 + 0x100000]) + bytes(0x80000)
        self.rom = bytearray(self.rom[:0x10]) + prg + chr_
        self.dst = 0x10 + 0x100000 + NEWBANK * 4096   # CHR 现在在 1MB PRG 之后
        base_chr = 0x10 + 0x100000
        self.rom[self.dst:self.dst + 4096] = self.rom[base_chr:base_chr + 4096]
        assert self.rom[0x7EB8F:0x7EB8F + 3] == bytes([0xAD, 0x51, 0x04])
        self.rom[0x7EB8F:0x7EB8F + 3] = bytes([0xA9, NEWBANK, 0xEA])
        # block 槽：full_reclaim 时单字节 0x20-0x7F + 双字节 0x8080-0x8B53 全可用
        blocks = list(range(0x20, 0x80))
        if full_reclaim: blocks += list(range(0x8080, 0x8B54))
        else:
            used = self._used_blocks(); blocks = [b for b in blocks if b not in used]
        self.free_blocks = iter(blocks)
        self.code_pool = iter(c for c in range(0x10, 0x100)
                              if c not in (0x0E, 0x0F, 0xFE) and c not in ICON_REUSE.values())
        self.tp = self.TEXT_FREE[0]; self.bp = self.BLK_FREE[0]
        self.codes = {}          # 字形 → PPU 码
        self.code2ch = {}        # 反向（round-trip 用）
        self.blk_of = {}         # PPU 码 → 共享 block

    def _used_blocks(self):
        used = set()
        for n in range(1, 2782):
            raw = self.R.sentence_blocks(n); i = 0
            while i < len(raw):
                b = raw[i]
                if b in TRIPLE_BYTE: i += 3
                elif b in DOUBLE_BYTE: i += 2
                elif b == 0x00: i += 1
                elif b < 0x80: used.add(b); i += 1
                else: used.add((b << 8) + raw[i + 1]); i += 2
        return used

    def _code_for(self, ch):
        if ch not in self.codes:
            c = self.codes[ch] = next(self.code_pool)
            self.code2ch[c] = ch
            self.rom[self.dst + c * 16: self.dst + c * 16 + 16] = glyph8x8(ch)
        return self.codes[ch]

    def _block_for(self, code):
        """PPU 码 → 共享双字节 block（PPU 串=单码位 [code]），全篇复用。"""
        if code not in self.blk_of:
            if self.tp + 1 > self.TEXT_FREE[1]: raise MemoryError("PPU 串区满")
            self.rom[self.tp] = code
            t3 = self._solve_text(self.tp, 1); self.tp += 1
            if t3 is None: raise ValueError("text 反解失败")
            blk = next(self.free_blocks)
            self.rom[self.R.text_pointer(blk):self.R.text_pointer(blk) + 3] = t3
            self.blk_of[code] = blk
        return self.blk_of[code]

    def _solve_text(self, ptr, length):
        for b1 in range(256):
            for b3 in range(256):
                if ((b1 >> 6) << 3) + (b3 >> 5) != length: continue
                base = (((b1 & 0x3F) - 0x2A) << 13) + (((b3 & 0x1F) ^ 0xA0) << 8)
                b2 = ptr - 0x4A010 - base
                if 0 <= b2 <= 255: return bytes([b1, b2, b3])
        return None

    def _solve_sentence(self, addr):
        D = addr - 0x56010
        for b3 in range(256):
            rem = D - ((b3 + 0xA0) << 8)
            if rem < 0: continue
            X, b2 = divmod(rem, 0x2000)
            if b2 > 255: continue
            b1 = X + 0x30
            if 0x30 <= b1 <= 0x7F: return bytes([b1, b2, b3])
        return None

    def encode_sentence(self, n, text):
        """把句 n 重编码为 text（每字形一个共享 block）。原子性：失败抛异常。"""
        bs = bytearray()
        for kind, v in tokenize(text):
            if kind == "ctrl":
                bs += v
            else:
                code = v if kind == "icon" else self._code_for(v)
                blk = self._block_for(code)
                bs += bytes([blk]) if blk < 0x80 else bytes([blk >> 8, blk & 0xFF])
        bs.append(0x00)
        if self.bp + len(bs) > self.BLK_FREE[1]: raise MemoryError("块串区满")
        addr = self.bp; self.rom[addr:addr + len(bs)] = bs; self.bp += len(bs)
        s3 = self._solve_sentence(addr)
        if s3 is None: raise ValueError(f"块串地址 {addr:X} 不可达")
        self.rom[self.R.sentence_pointer(n):self.R.sentence_pointer(n) + 3] = s3

    def decode_sentence(self, n):
        """按我们的 code↔字 映射 + 控制码 token 解码（round-trip 验证用）。"""
        P = Rom(bytes(self.rom))
        raw = P.sentence_blocks(n); out = []; i = 0
        icon_inv = {v: k for k, v in ICON_REUSE.items()}
        while i < len(raw):
            b = raw[i]
            if b in TRIPLE_BYTE:
                out.append("~" + raw[i:i + 3].hex().upper() + "~"); i += 3
            elif b in DOUBLE_BYTE:
                out.append("~" + raw[i:i + 2].hex().upper() + "~"); i += 2
            elif b == 0x00: break
            else:
                blk = b if b < 0x80 else (b << 8) + raw[i + 1]
                i += 1 if b < 0x80 else 2
                for c in P.block_ppu(blk):
                    if c in icon_inv: out.append(icon_inv[c])
                    elif c in self.code2ch: out.append(self.code2ch[c])
                    else: out.append(f"?{c:02X}?")
        return "".join(out)


def _norm(s):
    """把控制码统一成大写十六进制，便于 round-trip 比对（原 sentence_text 已是 ~XX~ 形式）。"""
    return re.sub(r"~([0-9A-Fa-f]+)~", lambda m: "~" + m.group(1).upper() + "~", s)


if __name__ == "__main__":
    # 自验：拿原文当"译文"喂进去，能塞多少句、round-trip 是否全对
    R0 = Rom(open(SRC, "rb").read())
    enc = Encoder()
    done = 0; first_bad = None
    try:
        for n in range(1, 2782):
            src = _norm(R0.sentence_text(n, codes=True))
            enc.encode_sentence(n, src)
            back = _norm(enc.decode_sentence(n))
            if back != src and first_bad is None:
                first_bad = (n, src, back)
            done = n
    except (MemoryError, ValueError, StopIteration) as e:
        print(f"容量到顶 @句{done + 1}: {type(e).__name__} {e}")
    print(f"编码 {done} 句；唯一字模 {len(enc.codes)}；PPU 串用 {enc.tp - enc.TEXT_FREE[0]}B，"
          f"块串用 {enc.bp - enc.BLK_FREE[0]}B")
    # round-trip 全查
    R0 = Rom(open(SRC, "rb").read())
    bad = []
    for n in range(1, done + 1):
        if _norm(enc.decode_sentence(n)) != _norm(R0.sentence_text(n, codes=True)):
            bad.append(n)
    print(f"round-trip: {done - len(bad)}/{done} 一致" + (" ✓" if not bad else f"，首个坏句 {bad[0]}"))
    if bad:
        n = bad[0]
        print("  原:", _norm(R0.sentence_text(n, codes=True))[:80])
        print("  新:", _norm(enc.decode_sentence(n))[:80])
