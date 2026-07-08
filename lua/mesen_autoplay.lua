-- 自动游玩冒烟测试：看完开场动画 → NEW GAME → 模拟按键推进剧情，定期截图。
-- 用法: Mesen --testrunner <rom> mesen_autoplay.lua > play.log
-- 截图以 "PLAY<帧号>:<hex>" 行输出（io 被沙箱禁，只能走 print），shell 侧还原 PNG。
-- ⚠️ setInput 必须在 inputPolled 事件回调里调用，否则每帧被真实输入轮询覆盖（实测无效）。
-- 时间线：开场动画自动播（~f3000 完）；f3400 START 进 NEW GAME；之后 A 为主推对话，
-- 间插 ↓/B 制造变化避免卡死在同一菜单。

local frame = 0
local lastLen = -1
local lastSum = -1

local IDLE = { a = false, b = false, select = false, start = false, up = false, down = false, left = false, right = false }
local function btn(name)
  local t = {}
  for k, v in pairs(IDLE) do t[k] = v end
  t[name] = true
  return t
end

local want = nil
emu.addEventCallback(function()
  pcall(emu.setInput, want or IDLE, 0)
end, emu.eventType.inputPolled)

local function shot(tag)
  local ok, png = pcall(emu.takeScreenshot)
  if not (ok and type(png) == "string") then return end
  local sum = 0
  for i = 1, #png, 97 do sum = (sum + png:byte(i)) % 1000000007 end
  if #png == lastLen and sum == lastSum then return end   -- 静止画面去重
  lastLen = #png; lastSum = sum
  print(tag .. ":" .. (png:gsub(".", function(c) return string.format("%02x", c:byte()) end)))
end

emu.addEventCallback(function()
  frame = frame + 1
  want = nil

  if frame >= 3400 and frame < 3410 then want = btn("start") end    -- NEW GAME

  if frame > 3600 then
    local m = frame % 45
    if m < 4 then
      local presses = frame // 45
      if presses % 9 == 8 then want = btn("b")
      elseif presses % 5 == 4 then want = btn("down")
      else want = btn("a") end
    end
  end

  if frame % 200 == 0 then shot("PLAY" .. frame) end

  if frame >= 30000 then
    shot("PLAY" .. frame)
    print("== 游玩结束 ==")
    emu.stop(0)
  end
end, emu.eventType.startFrame)

pcall(emu.setEmulationSpeed, 0)
print("== 自动游玩启动 ==")
