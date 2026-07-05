-- MSG 句子播放顺序 & 查表例程追踪
-- 用【原版】Metal Slader Glory (Japan).nes 跑（干净、正常播放）：
--   Debug → Script Window → 粘贴 → Run，然后 NEW GAME 玩开场那一幕，
--   开场演完（到能自由操作/进店铺）后，把 Log 全部复制给我。
--
-- 原理：句子指针表在 CPU $BCB5 起（句 n 的 3 字节指针在 $BCB5+3*(n-1)）。
-- 游戏每显示一句都会读它的指针 → 读取地址反算句号。只记 3 字节对齐的读，去重连续重复。

local BASE = 0xBCB5          -- 句 1 指针的 CPU 地址（页0 映射在 $A000 槽）
local TOP  = 0xBFFF          -- 该窗口覆盖句 1..~281（含开场）
local last = -1

local function onread(addr, value)
  local off = addr - BASE
  if off % 3 ~= 0 then return end           -- 只认指针三元组的首字节（对齐）
  local n = off // 3 + 1
  if n == last then return end              -- 去重：同一句连续读多次只记一次
  last = n
  local pc = 0
  local ok, st = pcall(emu.getState)
  if ok and st and st.cpu then pc = st.cpu.pc end
  emu.log(string.format("句 %d   (读@%04X, PC=%04X)", n, addr, pc))
end

emu.addMemoryCallback(onread, emu.callbackType.read, BASE, TOP)
emu.log("== 句子追踪就绪：NEW GAME 玩开场，然后复制 Log ==")
