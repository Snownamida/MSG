-- 绿字属性写入追踪：绿字属性在 VRAM $23C0-$23FF(属性表)，经 $2007 写入。
-- 追踪 PPU 写地址(由 $2006 两次写拼出)，当写到 $23C0-$23FF 时，记录 地址/值/PC。
-- 目标：找到写绿字属性的代码 PC，看清为什么我的算出 $FE 而原版 $FF。
--
-- 用 MSG-zh-demo.nes：玩到通电绿字屏，停住，把 Log 复制给我。

local ppuaddr = 0
local latch = 0
local seen = {}

-- $2006: 两次写拼 PPU 地址(高字节先)
emu.addMemoryCallback(function(addr, value)
  if latch == 0 then ppuaddr = (value << 8); latch = 1
  else ppuaddr = ppuaddr | value; latch = 0 end
end, emu.callbackType.write, 0x2006)

-- $2007: 写 PPU 数据；若地址在属性表 $23C0-$23FF，记录
emu.addMemoryCallback(function(addr, value)
  if ppuaddr >= 0x23C0 and ppuaddr <= 0x23FF then
    local pc = 0
    local ok, st = pcall(emu.getState); if ok and st and st.cpu then pc = st.cpu.pc end
    local key = string.format("%04X=%02X", ppuaddr, value)
    if not seen[key] then
      seen[key] = true
      emu.log(string.format("属性 $%04X <- $%02X   (PC=%04X)", ppuaddr, value, pc))
    end
  end
  ppuaddr = (ppuaddr + ((latch == 0) and 1 or 32)) & 0x7FFF   -- 粗略自增(不影响记录)
end, emu.callbackType.write, 0x2007)

emu.log("== 属性写入追踪就绪：玩到通电绿字屏，停住，复制 Log ==")
