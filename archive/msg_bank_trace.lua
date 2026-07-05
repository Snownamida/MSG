-- BG 4 个 1KB slot 追踪：MMC5 的 BG 图案按 tile 号分 4 段用不同 bank：
--   tile 0x00-0x3F→$5128, 0x40-0x7F→$5129, 0x80-0xBF→$512A, 0xC0-0xFF→$512B
-- 记录这 4 个寄存器每次写入的值 + 扫描线，看绿字区/对话框区各段用哪个 bank。
--
-- 用 MSG-zh-demo.nes：玩到"通电"绿字屏，停住不动，把 Log 复制给我。

local names = {[0x5128]="$5128(tile 00-3F)", [0x5129]="$5129(tile 40-7F)",
               [0x512A]="$512A(tile 80-BF)", [0x512B]="$512B(tile C0-FF)"}
local seen = {}
local frames = 0

local function cb(addr, value)
  if frames > 4 then return end
  local sl = -99
  local ok, st = pcall(emu.getState)
  if ok and st and st.ppu then sl = st.ppu.scanline end
  local key = string.format("%x@%d=%d", addr, sl, value)
  if not seen[key] then
    seen[key] = true
    emu.log(string.format("扫描线%4d: %s <- bank %d", sl, names[addr] or string.format("$%04X", addr), value))
  end
end

for _, r in ipairs({0x5128, 0x5129, 0x512A, 0x512B}) do
  emu.addMemoryCallback(cb, emu.callbackType.write, r, r)
end
emu.addEventCallback(function() frames = frames + 1 end, emu.eventType.startFrame)
emu.log("== BG 4-slot 追踪就绪：玩到通电绿字屏，停住，复制 Log ==")
