#!/usr/bin/env python3
"""合金月神 (Metal Slader Glory, HAL 研究所, 1991, FC) 文本工具。

2020 年的 Visual Studio C 实现（见 git 历史，tag: c-final）的 Python 重写。
把 ROM 里两级字典压缩的日文剧本解出为可读文本，为汉化做准备。

文本系统的数据流（各层均为去 ROM 查表的解引用）：

    句子编号(1~2781) ──算术──▶ 句子指针 ──读3B──▶ 句子
        ──bank运算──▶ 文本块串指针 ──读到0x00──▶ 文本块串
        ──拆分──▶ 文本块 block (<0x80 单字节 / >=0x80 双字节；即 MTE 字典)
        ──查表──▶ 文本指针 ──读3B──▶ 文本
        ──位运算解包──▶ 字符串地址+长度 ──读──▶ PPU 编码串
        ──码表──▶ Unicode 文本

用法（ROM 请自备，默认放在本目录）：
    python3 msgtool.py export             # 导出全部 2781 句剧本
    python3 msgtool.py blocks             # 导出字典（全部文本块）
    python3 msgtool.py used               # 用 .cdl 统计游戏实际用到哪些句子
    python3 msgtool.py map                # PRG ROM 字节用途图谱（找空闲空间用）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------- 常量（来自逆向，见 git 历史中的 typeDef.h） ----------------

ROM_DEFAULT = "Metal Slader Glory (Japan).nes"
CDL_DEFAULT = "Metal Slader Glory (Japan).cdl"

SENTENCE_TOTAL = 2781
SENTENCE_PTR_START = 0x1CC5     # 句子指针表起点（.nes 文件偏移，含 16B header）
BLOCK_TEXT_TABLE = 0x3D5C       # block → 文本 的表
BLOCK_START, BLOCK_END = 0x8000, 0x8B57  # block 编号区间（生成器形式）
PRG_END = 0x80010               # header 0x10 + PRG 512KB；文本全部在 PRG

# 文本块串里的控制码（块串层，不同于 PPU 串层的 0x0E/0x0F）
DOUBLE_BYTE = {0x05, 0x07, 0x0B, 0x0C, 0x13, 0x14, 0x16, 0x18}
TRIPLE_BYTE = {0x0F, 0x10, 0x12, 0x17}

# ---------------- 码表（PPU 编码 → Unicode） ----------------
# 忠实照搬 C 版（含其取字习惯：部分汉字用了简体近形字，如 対→对、況→况）。
# 保持与 C 版输出可逐字节对账；修字形属于后续翻译阶段的事。

CHARSET = (
    "(00) (01) (02) (03) (04) ！ ！！ ？ ！？ (冒汗) % / ー .. ゛ ゜ "
    ". 「 」 “ ” (特1) (特2) | (特3) (爱心) ★ (音符) 方 本 名 明 "
    "0 1 2 3 4 5 6 7 8 9 A B C D E F "
    "G H I J K L M N O P Q R S T U V "
    "W X Y Z ァ ィ ェ ォ ッ ャ ュ ョ っ ゃ ゅ ょ "
    "あ い う え お か き く け こ さ し す せ そ た "
    "ち つ て と な に ぬ ね の は ひ ふ へ ほ ま み "
    "む め も や ゆ よ ら り る れ ろ わ を ん 目 夜 "
    "ア イ ウ エ オ カ キ ク ケ コ サ シ ス セ ソ タ "
    "チ ツ テ ト ナ ニ ヌ ネ ノ ハ ヒ フ ヘ ホ マ ミ "
    "ム メ モ ヤ ユ ヨ ラ リ ル レ ロ ワ ヲ ン 用 了 "
    "々 以 井 宇 央 下 化 何 可 回 外 核 危 机 気 休 "
    "居 况 区 空 兄 月 光 向 灰 行 合 今 才 在 作 子 "
    "志 死 私 自 主 手 住 出 所 小 少 床 泊 照 上 状 "
    "心 人 生 先 全 体 对 知 中 宙 忠 日 的 天 当 同 "
    "内 入 任 年 発 反 不 父 武 分 兵 法 (FC) (FD) SPACE (FF)"
).split()
CHARSET[0xFE] = " "  # 空格占位（split 吃掉了真实空格）
assert len(CHARSET) == 0x100

# 0x0E 前缀：浊音（下一字节查此表）
DAKUTEN: dict[int, str] = {0x82: "ヴ"}
DAKUTEN.update(zip(range(0x55, 0x64), "がぎぐげござじずぜぞだぢづでど"))
DAKUTEN.update(zip(range(0x85, 0x94), "ガギグゲゴザジズゼゾダヂヅデド"))
DAKUTEN.update(zip(range(0x69, 0x6E), "ばびぶべぼ"))
DAKUTEN.update(zip(range(0x99, 0x9E), "バビブベボ"))

# 0x0F 前缀：半浊音。注：0x9C 的「ぺ」为 C 版原有笔误（应为片假名ペ），暂保留以便对账
HANDAKUTEN: dict[int, str] = {}
HANDAKUTEN.update(zip(range(0x69, 0x6E), "ぱぴぷぺぽ"))
HANDAKUTEN.update(zip(range(0x99, 0x9E), "パピプぺポ"))


# ---------------- ROM 解析 ----------------

class Rom:
    """只读解析器：实现上面数据流图里的每一步。地址均为 .nes 文件偏移。"""

    def __init__(self, data: bytes):
        self.d = data

    # ---- 地址算术（原 value_calculate.c） ----

    @staticmethod
    def sentence_pointer(n: int) -> int:
        return 3 * (n - 1) + SENTENCE_PTR_START

    def block_string_pointer(self, sentence: bytes) -> int:
        b1, b2, b3 = sentence
        return 0x56010 + ((b1 & 0x7F) - 0x30) * 0x2000 + ((b3 + 0xA0) << 8) + b2

    @staticmethod
    def text_pointer(block: int) -> int:
        if block <= 0x7F:
            block += 0x8000
        return 3 * (block - 0x8000) + BLOCK_TEXT_TABLE

    @staticmethod
    def string_pointer(text: bytes) -> tuple[int, int]:
        b1, b2, b3 = text
        ptr = (((b1 & 0x3F) - 0x2A) << 13) + (((b3 & 0x1F) ^ 0xA0) << 8) + b2 + 0x4A010
        length = ((b1 >> 6) << 3) + (b3 >> 5)
        return ptr, length

    # ---- 解引用（原 unreference.c） ----

    def read3(self, off: int) -> bytes:
        return self.d[off:off + 3]

    def read_block_string(self, off: int) -> bytes:
        """读文本块串：跳过控制码参数，读到 0x00 终止（含终止符）。"""
        out = bytearray()
        i = off
        while True:
            if len(out) >= 2048:
                print(f"警告：{off:X} 的块串超过 2048 字节", file=sys.stderr)
                break
            b = self.d[i]
            out.append(b)
            i += 1
            if b in DOUBLE_BYTE or b >= 0x80:
                out.append(self.d[i]); i += 1
            elif b in TRIPLE_BYTE:
                out += self.d[i:i + 2]; i += 2
            elif b == 0x00:
                break
        return bytes(out)

    def read_ppu_string(self, ptr: int, length: int) -> bytes:
        """读 PPU 编码串。首字节为 0 时长度改由第二字节低 7 位 +2 决定。"""
        if not self.d[ptr]:
            length = (self.d[ptr + 1] & 0x7F) + 2
        length = min(length, 32)  # 同 C 版：超 32 视为异常并截断
        return self.d[ptr:ptr + length]

    # ---- 组合层 ----

    def block_ppu(self, block: int) -> bytes:
        text = self.read3(self.text_pointer(block))
        return self.read_ppu_string(*self.string_pointer(text))

    def block_text(self, block: int) -> str:
        return decode_ppu(self.block_ppu(block))

    def sentence_blocks(self, n: int) -> bytes:
        sentence = self.read3(self.sentence_pointer(n))
        return self.read_block_string(self.block_string_pointer(sentence))

    def sentence_text(self, n: int, codes: bool = True) -> str:
        """展开句子。codes=True 时控制码以 ~XXXX~ 形式内联（回写时需要）。"""
        s = self.sentence_blocks(n)
        out: list[str] = []
        i = 0
        while i < len(s):
            b = s[i]
            if b in TRIPLE_BYTE:
                if codes:
                    out.append(f"~{b:02X}{s[i+1]:02X}{s[i+2]:02X}~")
                i += 3
            elif b in DOUBLE_BYTE:
                if codes:
                    out.append(f"~{b:02X}{s[i+1]:02X}~")
                i += 2
            elif b == 0x00:
                i += 1
            elif b < 0x80:
                out.append(self.block_text(b))
                i += 1
            else:
                out.append(self.block_text((b << 8) + s[i + 1]))
                i += 2
        return "".join(out)


def decode_ppu(ppu: bytes) -> str:
    """PPU 编码串 → Unicode（原 string_ppu_to_unicode）。"""
    out: list[str] = []
    i = 0
    while i < len(ppu):
        b = ppu[i]
        if b in (0x0E, 0x0F):               # 浊音/半浊音前缀
            i += 1
            # 前缀在串末尾时无后续字节：C 版此处越界读栈内存、碰巧查到空串，
            # 等效于什么都不输出——这里显式实现同样效果
            if i < len(ppu):
                table = DAKUTEN if b == 0x0E else HANDAKUTEN
                out.append(table.get(ppu[i], ""))
        elif b == 0x00:                     # 补空隙：跳过下一字节
            i += 1
        else:
            out.append(CHARSET[b])
        i += 1
    return "".join(out)


def iter_blocks():
    """block 编号序列：0x00~0x7F，然后 0x8080~0x8B57（同 C 版遍历方式）。"""
    for g in range(BLOCK_START, BLOCK_END + 1):
        yield g if g > 0x807F else g - 0x8000


# ---------------- 子命令 ----------------

def cmd_export(rom: Rom, args) -> None:
    lines = (f"{n}\t{rom.sentence_text(n, codes=not args.no_codes)}"
             for n in range(1, SENTENCE_TOTAL + 1))
    write_out(args.output, "\n".join(lines) + "\n")


def cmd_blocks(rom: Rom, args) -> None:
    lines = (f"{b:04X}\t{rom.block_text(b)}" for b in iter_blocks())
    write_out(args.output, "\n".join(lines) + "\n")


def cmd_used(_rom: Rom, args) -> None:
    """读 FCEUX 的 .cdl（无 16B header），bit1=作为数据被读过 → 句子被使用。"""
    cdl = Path(args.cdl).read_bytes()
    used = []
    for n in range(1, SENTENCE_TOTAL + 1):
        flag = cdl[Rom.sentence_pointer(n) - 0x10]
        if flag & 0b10:
            bank = (flag & 0b1100) >> 2
            used.append((n, bank))
    print("句子编号\t指针\t被使用时映射在 bank")
    for n, bank in used:
        print(f"{n}\t{Rom.sentence_pointer(n):X}\t{bank}")
    print(f"共 {len(used)}/{SENTENCE_TOTAL} 句被使用过", file=sys.stderr)


def cmd_map(rom: Rom, args) -> None:
    """PRG 字节用途图谱：给每类数据标区间（找空闲空间/回写规划用）。"""
    SENT, BLKS, TEXT, STRG = 1, 2, 4, 8
    marks = bytearray(PRG_END)

    for n in range(1, SENTENCE_TOTAL + 1):
        p = Rom.sentence_pointer(n)
        for k in range(3):
            marks[p + k] |= SENT
        bsp = rom.block_string_pointer(rom.read3(p))
        for k in range(len(rom.read_block_string(bsp))):
            marks[bsp + k] |= BLKS

    for b in iter_blocks():
        tp = Rom.text_pointer(b)
        for k in range(3):
            marks[tp + k] |= TEXT
        ptr, length = Rom.string_pointer(rom.read3(tp))
        if length >= 32 or ptr + length > PRG_END:
            continue
        s = rom.read_ppu_string(ptr, length)
        for k in range(len(s)):
            marks[ptr + k] |= STRG

    names = {0: "空闲", SENT: "句子表", BLKS: "块串", TEXT: "文本表", STRG: "字符串"}
    print("起始\t结束\t大小\t用途")
    start = 0
    for i in range(1, PRG_END + 1):
        if i == PRG_END or marks[i] != marks[start]:
            m = marks[start]
            label = names.get(m) or "+".join(v for k, v in names.items() if k and m & k)
            if m or (i - start) >= args.min_free:
                print(f"{start:05X}\t{i - 1:05X}\t{i - start}\t{label}")
            start = i


def write_out(path: str | None, content: str) -> None:
    if path:
        Path(path).write_text(content, encoding="utf-8")
        print(f"已写入 {path}", file=sys.stderr)
    else:
        sys.stdout.write(content)


def main() -> None:
    ap = argparse.ArgumentParser(description="合金月神 (Metal Slader Glory) 文本工具")
    ap.add_argument("--rom", default=ROM_DEFAULT, help="ROM 路径（请自备）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("export", help="导出全部句子")
    p.add_argument("-o", "--output")
    p.add_argument("--no-codes", action="store_true", help="不内联 ~控制码~")

    p = sub.add_parser("blocks", help="导出字典（全部文本块）")
    p.add_argument("-o", "--output")

    p = sub.add_parser("used", help="统计哪些句子被游戏实际使用（需 .cdl）")
    p.add_argument("--cdl", default=CDL_DEFAULT)

    p = sub.add_parser("map", help="PRG 字节用途图谱")
    p.add_argument("--min-free", type=int, default=64, help="小于此值的空闲区间不显示")

    args = ap.parse_args()
    rom_path = Path(args.rom)
    if not rom_path.exists():
        sys.exit(f"找不到 ROM：{rom_path}\n请自备 ROM 放到仓库根目录（版权原因不随仓库分发）。")
    rom = Rom(rom_path.read_bytes())
    {"export": cmd_export, "blocks": cmd_blocks, "used": cmd_used, "map": cmd_map}[args.cmd](rom, args)


if __name__ == "__main__":
    main()
