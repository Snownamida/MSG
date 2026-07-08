-- GUI 抓头像框信息：玩到「说话人小头像+边框」那屏，按 SELECT，把日志区所有 DUMP 行贴给我。
-- 我据此定位边框用哪些 tile 码、哪个 CHR bank，精准修掉边框中文乱码。
--
-- 用法（Mesen GUI）：
--   1. 打开 MSG-zh-demo.nes（汉化版），Debug → Script Window → 打开本文件 → Run
--   2. 玩到有说话人小头像的对话（如梓/艾莉娜说话，右下有小头像+边框"记")
--   3. 停在那一屏，按一下手柄 SELECT
--   4. 把日志区所有以 DUMP 开头的行全选复制给我

local CPU = emu.memType.nesMemory
local PPU = emu.memType.nesPpuMemory

local function dump()
  local st = emu.getState()
  emu.log("==== DUMP 开始（复制以下所有 DUMP 行给我）====")
  -- CHR bank 映射（sprite $5120-27 + bg $5128-2B）
  local cb = {}
  for i = 0, 11 do cb[i] = st["mapper.chrBanks" .. i] end
  emu.log(string.format("DUMP chrBanks: %d %d %d %d %d %d %d %d | bg: %d %d %d %d  chrMode=%s",
    cb[0], cb[1], cb[2], cb[3], cb[4], cb[5], cb[6], cb[7], cb[8], cb[9], cb[10], cb[11], tostring(st["mapper.chrMode"])))
  emu.log(string.format("DUMP regs 0450-0463: %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X",
    emu.read(0x0450,CPU),emu.read(0x0451,CPU),emu.read(0x0452,CPU),emu.read(0x0453,CPU),emu.read(0x0454,CPU),emu.read(0x0455,CPU),
    emu.read(0x0456,CPU),emu.read(0x0457,CPU),emu.read(0x0458,CPU),emu.read(0x0459,CPU),emu.read(0x045A,CPU),emu.read(0x045B,CPU),
    emu.read(0x045C,CPU),emu.read(0x045D,CPU),emu.read(0x045E,CPU),emu.read(0x045F,CPU),emu.read(0x0460,CPU),emu.read(0x0461,CPU),
    emu.read(0x0462,CPU),emu.read(0x0463,CPU)))
  -- 4 个 nametable 的所有非空 tile（含 行,列,tile码）——找头像框区的框 tile
  for _, nt in ipairs({0x2000, 0x2400, 0x2800, 0x2C00}) do
    for r = 0, 29 do
      local line = {}
      for c = 0, 31 do
        local t = emu.read(nt + r * 0x20 + c, PPU)
        if t ~= 0 and t ~= 0x24 and t ~= 0xFD and t ~= 0xFE and t ~= 0xFF then
          line[#line + 1] = string.format("c%d=%02X", c, t)
        end
      end
      if #line > 0 then emu.log(string.format("DUMP NT%04X R%02d: %s", nt, r, table.concat(line, " "))) end
    end
  end
  -- OAM：所有可见 sprite（x,y,tile）
  local usered = pcall(emu.read, 0, emu.memType.nesSpriteRam)
  local sp = {}
  for i = 0, 63 do
    local y, t, at, x
    if usered then
      y = emu.read(i*4, emu.memType.nesSpriteRam); t = emu.read(i*4+1, emu.memType.nesSpriteRam)
      x = emu.read(i*4+3, emu.memType.nesSpriteRam)
    else
      y = emu.read(0x0200+i*4, CPU); t = emu.read(0x0201+i*4, CPU); x = emu.read(0x0203+i*4, CPU)
    end
    if y < 0xEF then sp[#sp+1] = string.format("(%d,%d)t%02X", x, y, t) end
  end
  emu.log("DUMP OAM: " .. table.concat(sp, " "))
  emu.log("==== DUMP 结束 ====")
end

local last = 0
emu.addEventCallback(function()
  pcall(emu.drawString, 8, 8, "framedump: 玩到头像那屏按 SELECT 输出", 0x00FF00, 0x000000)
  local ok, pad = pcall(emu.getInput, 0)
  if ok and pad and pad.select then
    local fc = emu.getState()["ppu.frameCount"]
    if fc - last > 60 then last = fc; dump() end
  end
end, emu.eventType.startFrame)

emu.log("== framedump 启动：玩到说话人小头像那屏，按 SELECT 输出 DUMP 行 ==")
