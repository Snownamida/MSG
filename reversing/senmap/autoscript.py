#!/usr/bin/env python3
"""全自动纯静态对话提取器 —— 库0句号 → 演出脚本 → 完整对话(白盒反编译器闭环)。

完整链(见 docs/SCRIPT_ENGINE.md,全部实证):
  库0句号 --$F01D公式--> 句子指针 --读3字节--> 演出脚本入口地址 --scriptdis扫描$4E--> 对话句号序列

$F01D:  t = 句号×3 + (base_lo | base_hi<<8);  指针 addr=$A000|(t&$1FFF), bank=((t>>13)&7)+base_bank
$EF73:  读指针3字节[b0,b1,b2] → 脚本 bank=b0|$80, addr=b1|((b2+$A0)<<8)

base 三张表 $5D1B/$5D1E/$5D21(按库0/1/2),场景初始化时设、演出中稳定 → 每场景动态读一次即可。
本工具默认用海边(场景0B)实读的 base;换场景传 --base。

用法: autoscript.py <库0句号> [--base b0..b8(9字节hex)] [--count N]
"""
import sys, os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "reversing", "senmap"))
from scriptdis import disasm_script, sent as _sent   # 复用 $4E 扫描 + 译文

ROM = open(os.path.join(_ROOT, "roms", "MSG-zh-demo.nes"), "rb").read()
# 海边场景(0B)实读 $5D1B-$5D23:  bank[3] · lo[3] · hi[3]
BASE_BEACH = [0x80, 0x80, 0x81, 0x8C, 0xB5, 0x4C, 0x00, 0x1C, 0x1D]

def _off(bank, addr):
    win = 0xA000 if addr >= 0xA000 else 0x8000
    return 16 + (bank & 0x7F) * 0x2000 + (addr - win)

def sent_ptr(lib, sn, base):
    """$F01D:库lib句号sn → 句子指针 (bank, addr)。"""
    lo, hi, bb = base[3 + lib], base[6 + lib], base[0 + lib]
    t = sn * 3 + (lo | hi << 8)
    return bb + ((t >> 13) & 7), 0xA000 | (t & 0x1FFF)

def script_entry(sn, base):
    """库0句号 → 演出脚本入口 (bank, addr)(读句子指针的3字节,$EF73 解读)。"""
    pb, pa = sent_ptr(0, sn, base)
    b0, b1, b2 = ROM[_off(pb, pa):_off(pb, pa) + 3]
    return b0 | 0x80, b1 | ((b2 + 0xA0) << 8)

def extract_dialogue(sn, base=BASE_BEACH, count=40):
    """库0句号 → 演出脚本反汇编 + 对话句号序列。返回 (脚本bank, 脚本addr, [(addr,句号)...])。"""
    sb, sa = script_entry(sn, base)
    ins = disasm_script(sb, sa, count)
    dlg = [(a, snn) for a, c, raw, snn in ins if snn is not None]
    return sb, sa, dlg


if __name__ == "__main__":
    sn = int(sys.argv[1], 0)
    base = BASE_BEACH
    count = 40
    for i, a in enumerate(sys.argv):
        if a == "--base": base = [int(x, 16) for x in sys.argv[i + 1].split()]
        if a == "--count": count = int(sys.argv[i + 1])
    sb, sa, dlg = extract_dialogue(sn, base, count)
    print(f"库0句号 {sn} → 演出脚本 bank{sb:02X}:${sa:04X}  对话 {len(dlg)} 句:")
    for a, snn in dlg:
        print(f"  ${a:04X}  句{snn} = {_sent(snn)[:40]}")
