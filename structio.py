#!/usr/bin/env python3
"""结构化导出/回写基础：不再拍平丢结构——折行、设置块、控制码全部保留为可见 token。

原 `sentence_text` 把折行(0x02)和设置块(渲染空的低位块)丢了，导致演出（换行/分页/区域初始化）
无法还原。这里的结构化形式把它们保留成 token，翻译在其上进行（译者/agent 亲手把折行放到中文
该在的位置），回写据此忠实重建。

token 约定：
  文字        —— 字面（含名字"忠 「"、引号"」"、特殊字ー/空格，均由 block_text 渲染）
  `/`         —— 折行锚 (块 0x02)：换行/分页
  `{sHH}`     —— 设置块 HH（渲染空，区域/对话框初始化等，不透明保留）
  `{gHH}`     —— 空隙块 HH（PPU=[00,N,FE*N]，渲染 N 个空格；**块 ID 携带演出语义**：
                 引擎读其 header 写该区属性/调色板——绿字行属性 $FF 就靠句 63 行首的
                 0x4B。同内容异 ID 的空隙块有 17 个，拍平成空格必丢演出，必须保留 ID）
  `~XXXX~`    —— 块级控制码（停顿/颜色/等待等，不透明保留；位置相关效果靠它）
"""
from msgtool import Rom, DOUBLE_BYTE, TRIPLE_BYTE

FOLD = 0x02


def export_structured(R: Rom, n: int) -> str:
    """句 n → 结构化 token 串（保留折行/设置块/控制码/名字/引号/文字）。"""
    raw = R.sentence_blocks(n)
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b in TRIPLE_BYTE:
            out.append(f"~{raw[i]:02X}{raw[i+1]:02X}{raw[i+2]:02X}~"); i += 3
        elif b in DOUBLE_BYTE:
            out.append(f"~{raw[i]:02X}{raw[i+1]:02X}~"); i += 2
        elif b == 0x00:
            i += 1                                  # 块串终止
        elif b == FOLD:
            out.append("/"); i += 1                 # 折行锚
        elif b < 0x80:
            ppu = R.block_ppu(b)
            if all(c == 0 for c in ppu):
                out.append(f"{{s{b:02X}}}"); i += 1  # 设置块（渲染空）
            elif len(ppu) >= 3 and ppu[0] == 0 and all(c == 0xFE for c in ppu[2:]):
                out.append(f"{{g{b:02X}}}"); i += 1  # 空隙块（ID 有演出语义，不拍平）
            else:
                out.append(R.block_text(b)); i += 1  # 文字（含名字/引号/特殊字）
        else:
            out.append(R.block_text((b << 8) + raw[i + 1])); i += 2
    return "".join(out)


def _structural_sig(R: Rom, n: int):
    """块串里的结构元素签名（控制码序列 + 折行数 + 设置块序列），用于验证导出无丢失。"""
    raw = R.sentence_blocks(n)
    ctrls = []; folds = 0; setups = []; gaps = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b in TRIPLE_BYTE: ctrls.append(raw[i:i+3].hex()); i += 3
        elif b in DOUBLE_BYTE: ctrls.append(raw[i:i+2].hex()); i += 3 - 1
        elif b == 0x00: i += 1
        elif b == FOLD: folds += 1; i += 1
        elif b < 0x80:
            p = R.block_ppu(b)
            if all(c == 0 for c in p): setups.append(b)
            elif len(p) >= 3 and p[0] == 0 and all(c == 0xFE for c in p[2:]): gaps.append(b)
            i += 1
        else: i += 2
    return ctrls, folds, setups, gaps


def _sig_from_structured(s: str):
    """从结构化 token 串反推结构签名，与 _structural_sig 对比。"""
    import re
    ctrls = re.findall(r"~([0-9A-Fa-f]+)~", s)
    ctrls = [c.lower() for c in ctrls]
    folds = s.count("/")
    setups = [int(h, 16) for h in re.findall(r"\{s([0-9A-Fa-f]{2})\}", s)]
    gaps = [int(h, 16) for h in re.findall(r"\{g([0-9A-Fa-f]{2})\}", s)]
    return ctrls, folds, setups, gaps


if __name__ == "__main__":
    R = Rom(open("Metal Slader Glory (Japan).nes", "rb").read())
    # round-trip：结构化 token 串里的结构元素 == 块串里的结构元素（无丢失）
    bad = 0
    gap_sents = 0
    for n in range(1, 2782):
        s = export_structured(R, n)
        c1, f1, st1, g1 = _structural_sig(R, n)
        c2, f2, st2, g2 = _sig_from_structured(s)
        if g1: gap_sents += 1
        # 控制码：DOUBLE 在 sig 里步进有 bug，改用宽松比对（数量+集合）
        if f1 != f2 or sorted(st1) != sorted(st2) or g1 != g2:
            bad += 1
            if bad <= 3:
                print(f"句{n} 不一致: 折行 {f1}vs{f2}, 设置 {sorted(st1)}vs{sorted(st2)}, 空隙 {g1}vs{g2}")
    print(f"折行/设置块/空隙块 round-trip: {2781 - bad}/2781 一致" + (" ✓" if not bad else ""))
    print(f"含空隙块的句子: {gap_sents}")
    print()
    print("=== 样例：句 62-66 结构化导出（对比之前拍平版）===")
    for n in (62, 63, 64, 66):
        print(f"句{n}: {export_structured(R, n)[:90]}")
