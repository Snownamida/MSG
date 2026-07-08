#!/usr/bin/env python3
"""全量回写工具：把整份中文译文回写进 ROM（多 bank 字库 + 三层指针重建 + round-trip 自验）。

规范格式（与 translation/ 译文一致）：
- `~HH~`/`~HHHH~`/`~HHHHHH~`：块串层控制码，原样还原字节，不占字模。
- 特殊图标 token（`(特1)(特2)(特3)(爱心)(音符)(冒汗)★`）：复用每个字库 bank 里保留的原 tile。
- 其余每个可见字符：分配一个 fusion-8px 字模 tile。

多 bank 装箱（核心）：整份译文约 1472 唯一字，一个 CHR bank 只有 ~216 可用 tile 码。
对话框一屏只显示一个 CHR bank，故**同一句的字形必须全在同一 bank**。用 first-fit-decreasing
把 2781 句装进最少的 bank（实测 CAP=216 → 106 个，< 可用 128），每句记下所属 bank
（`sent_bank`，供每句渲染前设置 CHR bank 的 asm 钩子使用——那是仅剩的一步）。

编码：每唯一(bank,字)→字模 tile；每 PPU 码 → 一个共享 block（PPU 串=单码位，渲染按激活 bank 取 tile）；
句块串 = 控制码字节 + 字形 block 序列，重建到扩 PRG 的块串区，句子/text 指针反解。

空间布局（避免四结构互撞，均在各自可达范围）：
  句子表 0x1CC5 / 文本表 0x3D5C / PPU 串区 0x5F60-0x76000 / 块串区 0x76000-0x100010（扩 PRG→1MB）。
"""
import os
import re
from PIL import Image, ImageDraw, ImageFont
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # src/x.py → 项目根
SRC = os.path.join(_ROOT, "roms", "Metal Slader Glory (Japan).nes")
FONT = os.path.join(_ROOT, "fonts", "fusion-pixel-8px-monospaced-zh_hans.otf")
CHR0 = 0x10 + 512 * 1024
NEWBANK = 128                       # 字库起始 CHR bank（0-127 = 原版 CG，128+ = 中文字库）
CAP = 216                           # 每 bank 可用字模码数（保守：预留 0xD0-0xDF 边框区）

# 特殊图标 → 复用原 PPU 码（每个字库 bank = bank0 拷贝，这些 tile 都在）
ICON_REUSE = {
    "(特1)": 0x15, "(特2)": 0x16, "(特3)": 0x18,
    "(爱心)": 0x19, "★": 0x1A, "(音符)": 0x1B, "(冒汗)": 0x09,
}
ICON_RE = re.compile("|".join(re.escape(k) for k in sorted(ICON_REUSE, key=len, reverse=True)))
CTRL_RE = re.compile(r"~([0-9A-Fa-f]{2,6})~")
# 码池：0x10-0xCF + 0xE0-0xFD，去掉图标码；预留 0xD0-0xDF(边框) / 0xFE(空白) / 0xFF / 0x00-0x0F(控制)
CODE_POOL = [c for c in list(range(0x10, 0xD0)) + list(range(0xE0, 0xFE))
             if c not in ICON_REUSE.values()]
assert len(CODE_POOL) >= CAP

_FONT = ImageFont.truetype(FONT, 8)
_GLYPH_CACHE = {}


def glyph8x8(ch):
    if ch in _GLYPH_CACHE: return _GLYPH_CACHE[ch]
    im = Image.new("L", (8, 8), 0); d = ImageDraw.Draw(im); d.fontmode = "1"
    bb = d.textbbox((0, 0), ch, font=_FONT)
    d.text(((8 - (bb[2] - bb[0])) // 2 - bb[0], 0), ch, fill=255, font=_FONT)
    p1 = bytearray([0xFF] * 8)
    for r in range(8):
        for c in range(8):
            if im.getpixel((c, r)) > 127: p1[r] &= 0xFF ^ (1 << (7 - c))
    g = _GLYPH_CACHE[ch] = bytes([0xFF] * 8) + bytes(p1)
    return g


def tokenize(s):
    """译文串 → [('ctrl', bytes) | ('icon', code) | ('ch', 字符)]。"""
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


def sentence_chars(text):
    """句子里需要字模的唯一字符集（去控制码/图标）。"""
    return frozenset(v for k, v in tokenize(text) if k == "ch")


def pack_banks(char_sets, cap=CAP, priority=()):
    """first-fit-decreasing 装箱：char_sets={n:frozenset} → (sent_bank{n:b}, bank_chars[set])。
    超过 cap 的句子（如 380）不装，返回在 oversized 里。
    priority：这些句子优先占 bank 0（demo 用：把开场幕塞进默认 bank，无需 asm 钩子即可实机看）。"""
    banks = []; sent_bank = {}; oversized = []
    pri = [n for n in priority if n in char_sets]
    if pri:
        b0 = set()
        for n in pri:
            b0 |= char_sets[n]; sent_bank[n] = 0
        assert len(b0) <= cap, f"优先幕唯一字 {len(b0)} > {cap}"
        banks.append(b0)
    rest = sorted((kv for kv in char_sets.items() if kv[0] not in sent_bank),
                  key=lambda kv: -len(kv[1]))
    for n, cs in rest:
        if len(cs) > cap:
            oversized.append(n); continue
        best, grow = -1, 1 << 30
        for i, b in enumerate(banks):
            u = len(b | cs)
            if u <= cap and u - len(b) < grow:
                grow, best = u - len(b), i
        if best < 0:
            banks.append(set(cs)); best = len(banks) - 1
        else:
            banks[best] |= cs
        sent_bank[n] = best
    return sent_bank, banks, oversized


class Encoder:
    TEXT_FREE = (0x5F60, 0x76000)      # PPU 串区（string_pointer 可达）
    BLK_FREE = (0x76000, 0x100010)     # 块串区（扩 PRG 到 1MB）

    def __init__(self, translation, src=SRC, priority=()):
        self.rom = bytearray(open(src, "rb").read())
        self.R = Rom(bytes(self.rom))
        # 扩 PRG→1MB（块串空间）、扩 CHR→1MB、B 命门
        self.rom[4] = 64; self.rom[5] = 128
        prg = bytearray(self.rom[0x10:0x10 + 0x80000]) + bytes(0x80000)
        chr_ = bytearray(self.rom[0x10 + 0x80000:0x10 + 0x100000]) + bytes(0x80000)
        self.rom = bytearray(self.rom[:0x10]) + prg + chr_
        self.base_chr = 0x10 + 0x100000
        assert self.rom[0x7EB8F:0x7EB8F + 3] == bytes([0xAD, 0x51, 0x04])
        self.rom[0x7EB8F:0x7EB8F + 3] = bytes([0xA9, NEWBANK, 0xEA])   # 默认 bank（asm 钩子将改成按句）
        # block 槽（全量替换 → 原字典全回收）+ 空闲指针
        self.free_blocks = iter(list(range(0x20, 0x80)) + list(range(0x8080, 0x8B54)))
        self.tp = self.TEXT_FREE[0]; self.bp = self.BLK_FREE[0]
        self.blk_of = {}                   # PPU 码 → 共享 block
        self.tr = translation
        # 1) 装箱
        self.char_sets = {n: sentence_chars(t) for n, t in translation.items() if t}
        self.sent_bank, self.bank_chars, self.oversized = pack_banks(self.char_sets, priority=priority)
        self.nbanks = len(self.bank_chars)
        # 2) 每 bank：拷 bank0（保边框/空白/图标），分配码 + 写字模
        self.b_char2code = []; self.b_code2ch = []
        for b, chars in enumerate(self.bank_chars):
            dst = self.base_chr + (NEWBANK + b) * 4096
            self.rom[dst:dst + 4096] = self.rom[self.base_chr:self.base_chr + 4096]
            c2c, c2ch = {}, {}
            for code, ch in zip(CODE_POOL, sorted(chars)):
                c2c[ch] = code; c2ch[code] = ch
                self.rom[dst + code * 16: dst + code * 16 + 16] = glyph8x8(ch)
            self.b_char2code.append(c2c); self.b_code2ch.append(c2ch)

    def _block_for(self, code):
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

    def encode_all(self):
        """把所有已装箱句子回写。返回成功句号列表。"""
        done = []
        for n in sorted(self.sent_bank):
            c2c = self.b_char2code[self.sent_bank[n]]
            bs = bytearray()
            for kind, v in tokenize(self.tr[n]):
                if kind == "ctrl":
                    bs += v
                else:
                    code = v if kind == "icon" else c2c[v]
                    blk = self._block_for(code)
                    bs += bytes([blk]) if blk < 0x80 else bytes([blk >> 8, blk & 0xFF])
            bs.append(0x00)
            if self.bp + len(bs) > self.BLK_FREE[1]: raise MemoryError("块串区满")
            addr = self.bp; self.rom[addr:addr + len(bs)] = bs; self.bp += len(bs)
            s3 = self._solve_sentence(addr)
            if s3 is None: raise ValueError(f"块串 {addr:X} 不可达")
            self.rom[self.R.sentence_pointer(n):self.R.sentence_pointer(n) + 3] = s3
            done.append(n)
        return done

    def decode_sentence(self, n):
        """按该句所属 bank 的 码↔字 解码（round-trip 验证）。"""
        P = Rom(bytes(self.rom))
        raw = P.sentence_blocks(n); out = []; i = 0
        icon_inv = {v: k for k, v in ICON_REUSE.items()}
        code2ch = self.b_code2ch[self.sent_bank[n]]
        while i < len(raw):
            b = raw[i]
            if b in TRIPLE_BYTE: out.append("~" + raw[i:i + 3].hex().upper() + "~"); i += 3
            elif b in DOUBLE_BYTE: out.append("~" + raw[i:i + 2].hex().upper() + "~"); i += 2
            elif b == 0x00: break
            else:
                blk = b if b < 0x80 else (b << 8) + raw[i + 1]
                i += 1 if b < 0x80 else 2
                for c in P.block_ppu(blk):
                    if c in code2ch: out.append(code2ch[c])
                    elif c in icon_inv: out.append(icon_inv[c])
                    else: out.append(f"?{c:02X}?")
        return "".join(out)


def _norm(s):
    return re.sub(r"~([0-9A-Fa-f]+)~", lambda m: "~" + m.group(1).upper() + "~", s)


def load_translation(path=os.path.join(_ROOT, "translation", "script_zh.tsv")):
    tr = {}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if "\t" in line:
            ns, zh = line.split("\t", 1); tr[int(ns)] = _norm(zh)
        elif line.strip().isdigit():
            tr[int(line.strip())] = ""
    return tr


if __name__ == "__main__":
    import sys
    tr = load_translation()
    demo = "demo" in sys.argv
    # demo：把开场幕（句 55-100：做梦→机甲→通电→故障→去店铺）优先塞进 bank 0，
    # 这样默认 bank 128 就显示开场中文，无需 asm 钩子即可实机验证真实译文管线。
    priority = range(55, 101) if demo else ()
    out = os.path.join(_ROOT, "roms", "MSG-zh-demo.nes" if demo else "MSG-zh-full.nes")
    enc = Encoder(tr, priority=priority)
    print(f"装箱：{enc.nbanks} 个字库 bank（CHR {NEWBANK}..{NEWBANK + enc.nbanks - 1}，可用 128），"
          f"超容需拆页的句：{enc.oversized}")
    done = enc.encode_all()
    bad = [n for n in done if enc.decode_sentence(n) != tr[n]]
    print(f"回写 {len(done)} 句；共享 block {len(enc.blk_of)}；"
          f"PPU 串 {enc.tp - enc.TEXT_FREE[0]}B，块串 {enc.bp - enc.BLK_FREE[0]}B")
    print(f"round-trip: {len(done) - len(bad)}/{len(done)} 一致" + (" ✓" if not bad else f"，首坏 {bad[0]}"))
    if bad:
        n = bad[0]; print("  原:", tr[n][:80]); print("  新:", enc.decode_sentence(n)[:80])
    else:
        open(out, "wb").write(enc.rom)
        if demo:
            b0 = sorted(n for n in enc.sent_bank if enc.sent_bank[n] == 0)
            print(f"✓ 写出 {out} ({len(enc.rom)} bytes)；bank0(默认显示)含句 {b0[0]}..{b0[-1]} 共 {len(b0)} 句"
                  f"（开场幕）→ 实机走 NEW GAME 看开场中文；其余幕因未加 bank 钩子会乱码，属预期")
        else:
            print(f"✓ 写出 {out} ({len(enc.rom)} bytes)；注：多 bank 钩子未加，仅 bank0 句子正常")
