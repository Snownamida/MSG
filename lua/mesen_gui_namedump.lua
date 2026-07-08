-- 名字列精准dump：玩到「忠和梓同屏」那行对话(Image 79那屏)，按 SELECT。
-- 输出每个含「(0x11)的行：从列0到「的所有tile码(名字区)。我据此定死名字对齐。
local PPU = emu.memType.nesPpuMemory
local function dump()
  emu.log("==== NAMEDUMP 开始(复制所有 ND 行给我)====")
  for _, nt in ipairs({0x2000, 0x2400, 0x2800, 0x2C00}) do
    for r = 0, 29 do
      -- 找该行第一个 「(0x11)
      local qcol = nil
      for c = 0, 31 do if emu.read(nt + r*0x20 + c, PPU) == 0x11 then qcol = c; break end end
      if qcol then
        local cells = {}
        for c = 0, qcol do cells[#cells+1] = string.format("c%02d=%02X", c, emu.read(nt + r*0x20 + c, PPU)) end
        emu.log(string.format("ND NT%04X R%02d 「@c%02d: %s", nt, r, qcol, table.concat(cells, " ")))
      end
    end
  end
  emu.log("==== NAMEDUMP 结束 ====")
end
local last = 0
emu.addEventCallback(function()
  pcall(emu.drawString, 8, 8, "namedump: 忠+梓同屏那行按 SELECT", 0x00FF00, 0x000000)
  local ok, pad = pcall(emu.getInput, 0)
  if ok and pad and pad.select then
    local fc = emu.getState()["ppu.frameCount"]
    if fc - last > 60 then last = fc; dump() end
  end
end, emu.eventType.startFrame)
emu.log("== namedump 启动：玩到忠+梓同屏，按 SELECT 输出 ND 行 ==")
