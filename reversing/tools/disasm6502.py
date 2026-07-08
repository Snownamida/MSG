#!/usr/bin/env python3
"""极简 6502 反汇编器 —— 白盒逆向的"静态读"核心武器。

给一段字节 + 起始 CPU 地址,输出反汇编行。零变量命名(不做符号化),纯指令级,
够用来读引擎子程序(取句子、选中派发、bank 切换)的逻辑。合法 6502 opcode 全覆盖。

用法:
  from disasm6502 import disasm
  for addr, raw, text in disasm(bytes_obj, 0xF000): print(f"{addr:04X}  {raw:<9}  {text}")
"""

# opcode → (助记符, 寻址模式)
_OPS = {
    0x00:("BRK","imp"),0x01:("ORA","indx"),0x05:("ORA","zp"),0x06:("ASL","zp"),
    0x08:("PHP","imp"),0x09:("ORA","imm"),0x0A:("ASL","acc"),0x0D:("ORA","abs"),
    0x0E:("ASL","abs"),0x10:("BPL","rel"),0x11:("ORA","indy"),0x15:("ORA","zpx"),
    0x16:("ASL","zpx"),0x18:("CLC","imp"),0x19:("ORA","absy"),0x1D:("ORA","absx"),
    0x1E:("ASL","absx"),0x20:("JSR","abs"),0x21:("AND","indx"),0x24:("BIT","zp"),
    0x25:("AND","zp"),0x26:("ROL","zp"),0x28:("PLP","imp"),0x29:("AND","imm"),
    0x2A:("ROL","acc"),0x2C:("BIT","abs"),0x2D:("AND","abs"),0x2E:("ROL","abs"),
    0x30:("BMI","rel"),0x31:("AND","indy"),0x35:("AND","zpx"),0x36:("ROL","zpx"),
    0x38:("SEC","imp"),0x39:("AND","absy"),0x3D:("AND","absx"),0x3E:("ROL","absx"),
    0x40:("RTI","imp"),0x41:("EOR","indx"),0x45:("EOR","zp"),0x46:("LSR","zp"),
    0x48:("PHA","imp"),0x49:("EOR","imm"),0x4A:("LSR","acc"),0x4C:("JMP","abs"),
    0x4D:("EOR","abs"),0x4E:("LSR","abs"),0x50:("BVC","rel"),0x51:("EOR","indy"),
    0x55:("EOR","zpx"),0x56:("LSR","zpx"),0x58:("CLI","imp"),0x59:("EOR","absy"),
    0x5D:("EOR","absx"),0x5E:("LSR","absx"),0x60:("RTS","imp"),0x61:("ADC","indx"),
    0x65:("ADC","zp"),0x66:("ROR","zp"),0x68:("PLA","imp"),0x69:("ADC","imm"),
    0x6A:("ROR","acc"),0x6C:("JMP","ind"),0x6D:("ADC","abs"),0x6E:("ROR","abs"),
    0x70:("BVS","rel"),0x71:("ADC","indy"),0x75:("ADC","zpx"),0x76:("ROR","zpx"),
    0x78:("SEI","imp"),0x79:("ADC","absy"),0x7D:("ADC","absx"),0x7E:("ROR","absx"),
    0x81:("STA","indx"),0x84:("STY","zp"),0x85:("STA","zp"),0x86:("STX","zp"),
    0x88:("DEY","imp"),0x8A:("TXA","imp"),0x8C:("STY","abs"),0x8D:("STA","abs"),
    0x8E:("STX","abs"),0x90:("BCC","rel"),0x91:("STA","indy"),0x94:("STY","zpx"),
    0x95:("STA","zpx"),0x96:("STX","zpy"),0x98:("TYA","imp"),0x99:("STA","absy"),
    0x9A:("TXS","imp"),0x9D:("STA","absx"),0xA0:("LDY","imm"),0xA1:("LDA","indx"),
    0xA2:("LDX","imm"),0xA4:("LDY","zp"),0xA5:("LDA","zp"),0xA6:("LDX","zp"),
    0xA8:("TAY","imp"),0xA9:("LDA","imm"),0xAA:("TAX","imp"),0xAC:("LDY","abs"),
    0xAD:("LDA","abs"),0xAE:("LDX","abs"),0xB0:("BCS","rel"),0xB1:("LDA","indy"),
    0xB4:("LDY","zpx"),0xB5:("LDA","zpx"),0xB6:("LDX","zpy"),0xB8:("CLV","imp"),
    0xB9:("LDA","absy"),0xBA:("TSX","imp"),0xBC:("LDY","absx"),0xBD:("LDA","absx"),
    0xBE:("LDX","absy"),0xC0:("CPY","imm"),0xC1:("CMP","indx"),0xC4:("CPY","zp"),
    0xC5:("CMP","zp"),0xC6:("DEC","zp"),0xC8:("INY","imp"),0xC9:("CMP","imm"),
    0xCA:("DEX","imp"),0xCC:("CPY","abs"),0xCD:("CMP","abs"),0xCE:("DEC","abs"),
    0xD0:("BNE","rel"),0xD1:("CMP","indy"),0xD5:("CMP","zpx"),0xD6:("DEC","zpx"),
    0xD8:("CLD","imp"),0xD9:("CMP","absy"),0xDD:("CMP","absx"),0xDE:("DEC","absx"),
    0xE0:("CPX","imm"),0xE1:("SBC","indx"),0xE4:("CPX","zp"),0xE5:("SBC","zp"),
    0xE6:("INC","zp"),0xE8:("INX","imp"),0xE9:("SBC","imm"),0xEA:("NOP","imp"),
    0xEC:("CPX","abs"),0xED:("SBC","abs"),0xEE:("INC","abs"),0xF0:("BEQ","rel"),
    0xF1:("SBC","indy"),0xF5:("SBC","zpx"),0xF6:("INC","zpx"),0xF8:("SED","imp"),
    0xF9:("SBC","absy"),0xFD:("SBC","absx"),0xFE:("INC","absx"),
}
# 寻址模式 → 操作数长度
_LEN = {"imp":0,"acc":0,"imm":1,"zp":1,"zpx":1,"zpy":1,"indx":1,"indy":1,"rel":1,
        "abs":2,"absx":2,"absy":2,"ind":2}


def _fmt(mode, addr, ops):
    if mode in ("imp","acc"): return ""
    if mode == "imm": return f"#${ops[0]:02X}"
    if mode == "zp":  return f"${ops[0]:02X}"
    if mode == "zpx": return f"${ops[0]:02X},X"
    if mode == "zpy": return f"${ops[0]:02X},Y"
    if mode == "indx":return f"(${ops[0]:02X},X)"
    if mode == "indy":return f"(${ops[0]:02X}),Y"
    if mode == "rel":
        off = ops[0] - 256 if ops[0] >= 0x80 else ops[0]
        return f"${(addr + 2 + off) & 0xFFFF:04X}"
    w = ops[0] | ops[1] << 8
    if mode == "abs":  return f"${w:04X}"
    if mode == "absx": return f"${w:04X},X"
    if mode == "absy": return f"${w:04X},Y"
    if mode == "ind":  return f"(${w:04X})"
    return ""


def disasm(data, base, limit=None):
    """反汇编 data(bytes),CPU 起始地址 base。返回 [(addr, rawhex, text)]。"""
    out = []
    i = 0
    n = len(data) if limit is None else min(limit, len(data))
    while i < n:
        op = data[i]; addr = base + i
        mn, mode = _OPS.get(op, ("???", "imp"))
        ln = _LEN[mode]
        ops = [data[i + 1 + k] for k in range(ln) if i + 1 + k < len(data)]
        raw = " ".join(f"{data[i + k]:02X}" for k in range(min(1 + ln, len(data) - i)))
        text = f"{mn} {_fmt(mode, addr, ops)}".strip() if op in _OPS else f".db ${op:02X}"
        out.append((addr, raw, text))
        i += 1 + ln
    return out


if __name__ == "__main__":
    import sys
    # 用法: disasm6502.py <hexstring> <base_hex>
    data = bytes.fromhex(sys.argv[1])
    base = int(sys.argv[2], 16)
    for addr, raw, text in disasm(data, base):
        print(f"{addr:04X}  {raw:<11}  {text}")
