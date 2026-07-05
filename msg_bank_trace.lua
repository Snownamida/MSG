-- 绿字区域 bank 追踪：记录每帧 $512B(BG CHR bank) 的写入 + 发生的扫描线，
-- 看清屏幕被分成几个横向区域、各用哪个 CHR bank（绿字在顶部，对话框在底部=128）。
--
-- 用【MSG-zh-demo.nes】跑：玩到"通电"那屏（顶部有绿字乱码、中间男孩 CG、底部对话框），
-- 停一两秒让它稳定，然后把 Log 复制给我。我要看：绿字扫描线(约 16-40)激活的 bank 是多少、
-- 和中间 CG、底部对话框(128) 是不是不同的区。

local seen = {}
local frame = 0

emu.addMemoryCallback(function(addr, value)
  if frame > 3 then return end                 -- 只抓开头几帧，避免刷屏
  local sl = -1
  local ok, st = pcall(emu.getState)
  if ok and st and st.ppu then sl = st.ppu.scanline end
  local key = string.format("sl%d=%d", sl, value)
  if not seen[key] then
    seen[key] = true
    emu.log(string.format("帧%d 扫描线%3d: $512B <- bank %d", frame, sl, value))
  end
end, emu.callbackType.write, 0x512B)

emu.addEventCallback(function() frame = frame + 1 end, emu.eventType.startFrame)
emu.log("== bank 追踪就绪：玩到通电绿字屏，稳定后复制 Log ==")
