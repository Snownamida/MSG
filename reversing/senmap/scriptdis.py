#!/usr/bin/env python3
"""演出脚本静态反汇编器 —— 纯静态从 $EDE5 脚本 bytecode 提对话(白盒反编译器雏形)。

原理(见 docs/SCRIPT_ENGINE.md §对话演出引擎):对话演出由解释器 $EDE5 驱动,脚本指针 $1E/$1F。
每条命令 = 命令字节 + 参数;命令 $4E <句号lo> <句号hi> = 显示对话。命令长度 = 命令表(bankBD)的
$66 标志(1 + $66&$08 + $66&$80),部分命令处理程序自读脚本流(靠动态 trace 修正)。

给定脚本地址+bank,静态扫描:逐命令按长度前进,遇 $4E 提句号 → 纯静态得对话序列。
(控制流跳转 C1/切库尚未完全跟随;先做单段线性扫描 + $4E 对话识别。)

用法: scriptdis.py <bank_hex> <addr_hex> [count]
"""
import sys, os, re

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROM = open(os.path.join(_ROOT, "roms", "MSG-zh-demo.nes"), "rb").read()

# 句号→译文(校验 $4E 提取正确性;LUA_OFF=1)
TR = {}
for l in open(os.path.join(_ROOT, "translation", "struct_full.tsv"), encoding="utf-8"):
    if "\t" in l:
        a, b = l.split("\t", 1)
        if a.strip().isdigit():
            TR[int(a)] = re.sub(r'~[0-9A-Fa-f]+~|\{[sg][0-9A-Fa-f]{2}\}', '', b).replace('/', ' ').strip()
def sent(n): return TR.get(n + 1, f"?{n}")

# 命令表在 bankBD 的 $8000 窗口:$8004+类别*2 = 4个类别表基址;表项[c*4] = ($13,$66,handler_lo,hi)
_CMDBANK = 0xBD & 0x7F
_c0 = 16 + _CMDBANK * 0x2000
def _cb(a): return ROM[_c0 + (a - 0x8000)]
_BASES = [_cb(0x8004 + i * 2) | _cb(0x8005 + i * 2) << 8 for i in range(4)]

# 处理程序自读脚本流的命令(动态 trace 实测步长 / 演出脚本结构推断,覆盖 $66 公式算不出的)
# 演出脚本一条对话 = $40 00(开框) · $4E <句号lo hi>(显示) · $41(收尾)
_FIXUP = {0x00: 2, 0x03: 2, 0x1D: 1, 0x27: 1, 0x3C: 3, 0x40: 2, 0x41: 1, 0x49: 2, 0x4E: 3}

def cmd_len(c):
    if c in _FIXUP: return _FIXUP[c]
    cat = (c >> 5) & 3; y = (c * 4) & 0xFF
    v66 = _cb(_BASES[cat] + y + 1)
    return 1 + (1 if v66 & 0x08 else 0) + (1 if v66 & 0x80 else 0)

def _rom_off(bank, addr):
    b = bank & 0x7F
    win = 0xA000 if addr >= 0xA000 else 0x8000
    return 16 + b * 0x2000 + (addr - win)

def disasm_script(bank, addr, count=40):
    """从 (bank, addr) 线性扫描 count 条命令,返回 [(addr, cmd, raw_bytes, 句号|None)]。"""
    out = []
    o = _rom_off(bank, addr)
    a = addr
    for _ in range(count):
        c = ROM[o]
        ln = cmd_len(c)
        raw = ROM[o:o + ln]
        sn = None
        if c == 0x4E and ln >= 3:
            sn = raw[1] | raw[2] << 8
        out.append((a, c, raw, sn))
        o += ln; a += ln
        if a >= 0xC000:  # 越出窗口
            break
    return out


if __name__ == "__main__":
    bank = int(sys.argv[1], 16); addr = int(sys.argv[2], 16)
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    print(f"=== 演出脚本反汇编 bank{bank:02X}:${addr:04X} ===")
    print(f"(命令表 bankBD, 类别基址 {[f'{b:04X}' for b in _BASES]})")
    for a, c, raw, sn in disasm_script(bank, addr, count):
        raws = " ".join(f"{b:02X}" for b in raw)
        tag = ""
        if sn is not None: tag = f"  ★对话 句{sn} = {sent(sn)[:24]}"
        print(f"  {a:04X}  {raws:<10} len={len(raw)}{tag}")
