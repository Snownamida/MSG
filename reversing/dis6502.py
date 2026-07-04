#!/usr/bin/env python3
"""Minimal 6502 disassembler + MMC5 ROM analysis helpers for Metal Slader Glory.

All offsets in comments are .nes FILE offsets (16B header included) unless noted
'PRG' (0-based into PRG ROM, = file-0x10) or 'CPU' (6502 address space).
"""
import sys

ROM = "/Users/jixiang.sun/Projects/snownamida-upgrades/MSG/Metal Slader Glory (Japan).nes"
CDL = "/Users/jixiang.sun/Projects/snownamida-upgrades/MSG/Metal Slader Glory (Japan).cdl"

data = open(ROM, "rb").read()
PRG = data[0x10:0x10 + 0x80000]      # 512KB
CHR = data[0x10 + 0x80000:]          # 512KB
cdl = open(CDL, "rb").read()
CDL_PRG = cdl[:0x80000]
CDL_CHR = cdl[0x80000:]

# ---------------- 6502 opcode table ----------------
# name, addressing mode, length
IMP, ACC, IMM, ZP, ZPX, ZPY, ABS, ABX, ABY, IND, INX, INY, REL = range(13)
MODELEN = {IMP:1, ACC:1, IMM:2, ZP:2, ZPX:2, ZPY:2, ABS:3, ABX:3, ABY:3,
           IND:3, INX:2, INY:2, REL:2}

OPC = {}
def d(op, name, mode): OPC[op] = (name, mode)
# load/store
d(0xA9,'LDA',IMM); d(0xA5,'LDA',ZP); d(0xB5,'LDA',ZPX); d(0xAD,'LDA',ABS)
d(0xBD,'LDA',ABX); d(0xB9,'LDA',ABY); d(0xA1,'LDA',INX); d(0xB1,'LDA',INY)
d(0xA2,'LDX',IMM); d(0xA6,'LDX',ZP); d(0xB6,'LDX',ZPY); d(0xAE,'LDX',ABS); d(0xBE,'LDX',ABY)
d(0xA0,'LDY',IMM); d(0xA4,'LDY',ZP); d(0xB4,'LDY',ZPX); d(0xAC,'LDY',ABS); d(0xBC,'LDY',ABX)
d(0x85,'STA',ZP); d(0x95,'STA',ZPX); d(0x8D,'STA',ABS); d(0x9D,'STA',ABX)
d(0x99,'STA',ABY); d(0x81,'STA',INX); d(0x91,'STA',INY)
d(0x86,'STX',ZP); d(0x96,'STX',ZPY); d(0x8E,'STX',ABS)
d(0x84,'STY',ZP); d(0x94,'STY',ZPX); d(0x8C,'STY',ABS)
# transfers
d(0xAA,'TAX',IMP); d(0xA8,'TAY',IMP); d(0xBA,'TSX',IMP); d(0x8A,'TXA',IMP)
d(0x9A,'TXS',IMP); d(0x98,'TYA',IMP)
# stack
d(0x48,'PHA',IMP); d(0x68,'PLA',IMP); d(0x08,'PHP',IMP); d(0x28,'PLP',IMP)
# logic
d(0x29,'AND',IMM); d(0x25,'AND',ZP); d(0x35,'AND',ZPX); d(0x2D,'AND',ABS)
d(0x3D,'AND',ABX); d(0x39,'AND',ABY); d(0x21,'AND',INX); d(0x31,'AND',INY)
d(0x09,'ORA',IMM); d(0x05,'ORA',ZP); d(0x15,'ORA',ZPX); d(0x0D,'ORA',ABS)
d(0x1D,'ORA',ABX); d(0x19,'ORA',ABY); d(0x01,'ORA',INX); d(0x11,'ORA',INY)
d(0x49,'EOR',IMM); d(0x45,'EOR',ZP); d(0x55,'EOR',ZPX); d(0x4D,'EOR',ABS)
d(0x5D,'EOR',ABX); d(0x59,'EOR',ABY); d(0x41,'EOR',INX); d(0x51,'EOR',INY)
d(0x24,'BIT',ZP); d(0x2C,'BIT',ABS)
# arithmetic
d(0x69,'ADC',IMM); d(0x65,'ADC',ZP); d(0x75,'ADC',ZPX); d(0x6D,'ADC',ABS)
d(0x7D,'ADC',ABX); d(0x79,'ADC',ABY); d(0x61,'ADC',INX); d(0x71,'ADC',INY)
d(0xE9,'SBC',IMM); d(0xE5,'SBC',ZP); d(0xF5,'SBC',ZPX); d(0xED,'SBC',ABS)
d(0xFD,'SBC',ABX); d(0xF9,'SBC',ABY); d(0xE1,'SBC',INX); d(0xF1,'SBC',INY)
d(0xC9,'CMP',IMM); d(0xC5,'CMP',ZP); d(0xD5,'CMP',ZPX); d(0xCD,'CMP',ABS)
d(0xDD,'CMP',ABX); d(0xD9,'CMP',ABY); d(0xC1,'CMP',INX); d(0xD1,'CMP',INY)
d(0xE0,'CPX',IMM); d(0xE4,'CPX',ZP); d(0xEC,'CPX',ABS)
d(0xC0,'CPY',IMM); d(0xC4,'CPY',ZP); d(0xCC,'CPY',ABS)
# inc/dec
d(0xE6,'INC',ZP); d(0xF6,'INC',ZPX); d(0xEE,'INC',ABS); d(0xFE,'INC',ABX)
d(0xC6,'DEC',ZP); d(0xD6,'DEC',ZPX); d(0xCE,'DEC',ABS); d(0xDE,'DEC',ABX)
d(0xE8,'INX',IMP); d(0xC8,'INY',IMP); d(0xCA,'DEX',IMP); d(0x88,'DEY',IMP)
# shifts
d(0x0A,'ASL',ACC); d(0x06,'ASL',ZP); d(0x16,'ASL',ZPX); d(0x0E,'ASL',ABS); d(0x1E,'ASL',ABX)
d(0x4A,'LSR',ACC); d(0x46,'LSR',ZP); d(0x56,'LSR',ZPX); d(0x4E,'LSR',ABS); d(0x5E,'LSR',ABX)
d(0x2A,'ROL',ACC); d(0x26,'ROL',ZP); d(0x36,'ROL',ZPX); d(0x2E,'ROL',ABS); d(0x3E,'ROL',ABX)
d(0x6A,'ROR',ACC); d(0x66,'ROR',ZP); d(0x76,'ROR',ZPX); d(0x6E,'ROR',ABS); d(0x7E,'ROR',ABX)
# jumps/calls
d(0x4C,'JMP',ABS); d(0x6C,'JMP',IND); d(0x20,'JSR',ABS)
d(0x60,'RTS',IMP); d(0x40,'RTI',IMP); d(0x00,'BRK',IMP)
# branches
d(0x10,'BPL',REL); d(0x30,'BMI',REL); d(0x50,'BVC',REL); d(0x70,'BVS',REL)
d(0x90,'BCC',REL); d(0xB0,'BCS',REL); d(0xD0,'BNE',REL); d(0xF0,'BEQ',REL)
# flags
d(0x18,'CLC',IMP); d(0x38,'SEC',IMP); d(0x58,'CLI',IMP); d(0x78,'SEI',IMP)
d(0xB8,'CLV',IMP); d(0xD8,'CLD',IMP); d(0xF8,'SED',IMP); d(0xEA,'NOP',IMP)

def reg_name(addr):
    special = {
        0x2000:'PPUCTRL',0x2001:'PPUMASK',0x2002:'PPUSTATUS',0x2003:'OAMADDR',
        0x2004:'OAMDATA',0x2005:'PPUSCROLL',0x2006:'PPUADDR',0x2007:'PPUDATA',
        0x4014:'OAMDMA',0x4016:'JOY1',0x4017:'JOY2',
        0x5100:'MMC5_PRGMODE',0x5101:'MMC5_CHRMODE',0x5102:'MMC5_PRGRAMP1',
        0x5103:'MMC5_PRGRAMP2',0x5104:'MMC5_EXRAMMODE',0x5105:'MMC5_NTMAP',
        0x5106:'MMC5_FILL',0x5107:'MMC5_FILLATTR',
        0x5113:'MMC5_PRGRAM',0x5114:'MMC5_PRG0',0x5115:'MMC5_PRG1',
        0x5116:'MMC5_PRG2',0x5117:'MMC5_PRG3',
        0x5120:'MMC5_CHR0',0x5121:'MMC5_CHR1',0x5122:'MMC5_CHR2',0x5123:'MMC5_CHR3',
        0x5124:'MMC5_CHR4',0x5125:'MMC5_CHR5',0x5126:'MMC5_CHR6',0x5127:'MMC5_CHR7',
        0x5128:'MMC5_CHRB0',0x5129:'MMC5_CHRB1',0x512A:'MMC5_CHRB2',0x512B:'MMC5_CHRB3',
        0x5130:'MMC5_CHRUP',0x5200:'MMC5_VSPLIT',0x5203:'MMC5_IRQCMP',0x5204:'MMC5_IRQST',
        0x5205:'MMC5_MULLO',0x5206:'MMC5_MULHI',
    }
    return special.get(addr)

def disasm_one(buf, off, pc):
    """Disassemble one instruction at buf[off], displayed at CPU addr pc.
    returns (text, length)."""
    op = buf[off]
    if op not in OPC:
        return (f".db ${op:02X}", 1)
    name, mode = OPC[op]
    ln = MODELEN[mode]
    b1 = buf[off+1] if off+1 < len(buf) else 0
    b2 = buf[off+2] if off+2 < len(buf) else 0
    def annot(addr):
        r = reg_name(addr)
        return f"   ; {r}" if r else ""
    if mode == IMP:  return (name, 1)
    if mode == ACC:  return (f"{name} A", 1)
    if mode == IMM:  return (f"{name} #${b1:02X}", 2)
    if mode == ZP:   return (f"{name} ${b1:02X}", 2)
    if mode == ZPX:  return (f"{name} ${b1:02X},X", 2)
    if mode == ZPY:  return (f"{name} ${b1:02X},Y", 2)
    if mode == INX:  return (f"{name} (${b1:02X},X)", 2)
    if mode == INY:  return (f"{name} (${b1:02X}),Y", 2)
    if mode == REL:
        tgt = (pc + 2 + ((b1 ^ 0x80) - 0x80)) & 0xFFFF
        return (f"{name} ${tgt:04X}", 2)
    addr = b1 | (b2 << 8)
    if mode == ABS:  return (f"{name} ${addr:04X}{annot(addr)}", 3)
    if mode == ABX:  return (f"{name} ${addr:04X},X{annot(addr)}", 3)
    if mode == ABY:  return (f"{name} ${addr:04X},Y{annot(addr)}", 3)
    if mode == IND:  return (f"{name} (${addr:04X})", 3)
    return (f".db ${op:02X}", 1)

def disasm_range(prg_off, length, base_pc, show_cdl=True):
    """Linear disassembly of PRG[prg_off:prg_off+length], CPU base_pc at prg_off."""
    out = []
    i = 0
    while i < length:
        off = prg_off + i
        pc = base_pc + i
        text, ln = disasm_one(PRG, off, pc)
        raw = " ".join(f"{PRG[off+k]:02X}" for k in range(ln))
        flag = CDL_PRG[off]
        cf = ""
        if show_cdl:
            marks = ('C' if flag&1 else '.') + ('D' if flag&2 else '.')
            cf = f"[{marks} b{(flag>>2)&3}] "
        out.append(f"{off:05X}/{pc:04X}: {cf}{raw:<9} {text}")
        i += ln
    return "\n".join(out)

if __name__ == "__main__":
    print("PRG size", hex(len(PRG)), "CHR size", hex(len(CHR)))
