-- MSG 16×16 调试 v3：CPU空间 vs PRG-ROM直读，判 emit 是否被 bank 映射绕开
-- 我的 patch 开头字节序列 = a0 01 a5 14 10 15；原版 = a0 01 a5 14 10 1b
-- 用法：Debug → Script Window → 粘贴 → Run；玩到开场对话显示后复制 Log。

local function dump(base, n, mt)
  local s = {}
  for i = 0, n - 1 do s[#s + 1] = string.format("%02x", emu.read(base + i, mt)) end
  return table.concat(s)
end

local shown = 0
emu.addMemoryCallback(function(addr, value)
  if shown >= 4 then return end
  shown = shown + 1
  local cpu = emu.memType.nesMemory
  local prg = emu.memType.nesPrgRom
  emu.log(string.format("--- A3 write #%d (val=%02x) ---", shown, value))
  emu.log("  CPU  $F135 = " .. dump(0xF135, 16, cpu))     -- 实际执行的
  emu.log("  PRG 0x7F135= " .. dump(0x7F135, 16, prg))    -- 文件里的(我的patch)
  emu.log("  0469=" .. dump(0x0469, 16, cpu))
  emu.log("  04A8=" .. dump(0x04A8, 24, cpu))
end, emu.callbackType.write, 0x04A3)

emu.log("== dump v3 ready ==")
