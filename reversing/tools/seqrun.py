#!/usr/bin/env python3
"""可续跑的 scenetrace 序列执行器 —— 脚本本身就是"怎么玩"的答案,分段跑完整条序列。
序列拆成步骤(STEPS);每段从存档+START_STEP续跑,临近帧限就存档+记步号+停;下段接着跑。
用户洞察:mesen_gui_scenetrace 的 option_view 序列已编码全流程(option_view({3})=各地点探完后的前往)。
用法:
  python3 reversing/seqrun.py <workdir>                    # 从头(step0=开机)
  python3 reversing/seqrun.py <workdir> <state.hex> <step> # 从存档的第<step>步续跑
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesen import run_lua, extract_pngs, extract_blob, NMI

LUA = r"""
pcall(emu.setEmulationSpeed,0)
local M=emu.memType.nesMemory
local PRG=emu.memType.nesPrgRom
local function rd(a) return emu.read(a,M) end
local function prg(o) return emu.read(o,PRG) end
local function _hex(s) local t={} for i=1,#s do t[i]=string.format("%02x",s:byte(i)) end return table.concat(t) end
local function unhex(h) local b={} for i=1,#h,2 do b[#b+1]=string.char(tonumber(h:sub(i,i+1),16)) end return table.concat(b) end

local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local KEY={A="a",B="b",up="up",down="down",left="left",right="right",start="start",select="select"}
local want=nil
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)
local function setbtn(name) local t={} for k,v in pairs(IDLE) do t[k]=v end if name then t[KEY[name] or name]=true end want=t end

-- 场景+句号追踪
local frame=0   -- 前置(N回调需读它做截图稳定判定)
local SAVE_SCENES=(__SAVESCENES__==1); local scene_saved={}
local lastN=-1; local lastScene=-1; local lastN_frame=0; local lastptr=-1
emu.addMemoryCallback(function()
  local p=rd(0x87)+rd(0x88)*256
  -- 旧公式 N(仅主表准,给 scene_map 向后兼容);深句靠 NRAW+宿主反查表
  local n
  if p>=0xBCB5 and p<0xBFFF and rd(0xA000)==prg(0) then n=(p-0xBCB5)//3
  elseif p>=0xA000 and p<0xBD4B and rd(0xA000)==prg(0x2000) then n=(p-0xA000)//3+281 end
  if n and n~=lastN then lastN=n; lastN_frame=frame; print(string.format("N\t%d\t%02X", n, rd(0x0450))) end
  -- ★NRAW:指针变化即记(A000/A001指纹+ptr+场景)→宿主反查真实句号,深句可靠。极频繁→仅 QA_SHOTS 开(否则拖慢到超时)
  if __SHOTS__==1 and p~=lastptr and p>=0xA000 then lastptr=p
    print(string.format("NRAW\t%02X\t%02X\t%04X\t%02X", rd(0xA000), rd(0xA001), p, rd(0x0450)))
  end
end, emu.callbackType.exec, 0xF071, 0xF071)

local START_HEX="__START_HEX__"
local START_STEP=__START_STEP__
local CAP=__CAP__
local LOADED=(#START_HEX==0)
local CKPT,SEQ_DONE=false,false
local CUR_STEP=START_STEP
local ss_req=0; local ss_blob=nil; local last_blob=nil; local last_step=START_STEP

local co  -- 前置
emu.addEventCallback(function()
  frame=frame+1
  if lastScene~=rd(0x0450) then lastScene=rd(0x0450); print("SCENE "..string.format("%02X",lastScene).." @frame"..frame) end
  if LOADED and co and coroutine.status(co)~="dead" then
    local ok,err=coroutine.resume(co); if not ok then print("CORO_ERR "..tostring(err)) end
  end
end, emu.eventType.startFrame)

local REPORTED=false
local shot_done={}
emu.addMemoryCallback(function()
  if not LOADED then if frame>=20 then emu.loadSavestate(unhex(START_HEX)); LOADED=true end return end
  if ss_req==1 then ss_blob=emu.createSavestate(); ss_req=0 end
  -- 每场景入口 checkpoint(SAVE_SCENES 环境):新场景第一次到"输入就绪的菜单态"时存档,供逐场景爬菜单树
  if SAVE_SCENES then local sc=rd(0x0450)
    if not scene_saved[sc] and rd(0x0200)~=0xF0 and rd(0x17)==0x10 then
      scene_saved[sc]=true
      print("SCENECKPT "..string.format("%02X",sc).." "..(_hex(emu.createSavestate())))
    end
  end
  -- QA:每个新句子的对话页各截一张(去重),供拼联系表验证渲染
  -- 稳定后才截(lastN 在 $F071 早于渲染更新;需等 tiles+bank 都到位,否则抓到"新tiles+旧bank"过渡帧=假乱码)
  if lastN>=0 and rd(0x0200)==0xF0 and (frame-lastN_frame)>=10 and not shot_done[lastN] then
    shot_done[lastN]=true
    -- 记录显示时字库 bank $045F 与场景 $0450:字库应=($0450|0x80),不等则跨场景乱码
    local sc=rd(0x0450); local fb=rd(0x045F); local p=rd(0x87)+rd(0x88)*256
    print(string.format("PAGE n=%d ptr=%04X A000=%02X scene=%02X font=%02X expect=%02X %s", lastN, p, rd(0xA000), sc, fb, (sc|0x80), (fb==(sc|0x80)) and "OK" or "MISMATCH"))
    if __SHOTS__==1 then local png=emu.takeScreenshot(); print("SHOT_START s"..lastN.."_"..string.format("%02X",sc)); print(_hex(png)); print("SHOT_END") end
  end
  if not REPORTED and (CKPT or SEQ_DONE or frame>=CAP+3000) then
    REPORTED=true
    -- 干净续跑点:输出最后一个"完成的步"的存档,下段从 last_step 接
    local out_blob = last_blob or emu.createSavestate()
    print("END last_step="..last_step.." cur="..CUR_STEP.." "..(SEQ_DONE and "全序列完" or "checkpoint").." $0450="..string.format("%02X",rd(0x0450)))
    local png=emu.takeScreenshot(); print("SHOT_START final"); print(_hex(png)); print("SHOT_END")
    print("BLOB_START end"); print(_hex(out_blob)); print("BLOB_END")
    emu.stop(0)
  end
end, emu.callbackType.exec, __NMI__, __NMI__)

-- 原语
local function fa() coroutine.yield() end
local function press(b) setbtn(b); fa(); fa(); setbtn(nil); fa(); fa() end
local stall=0
local function wait_ready(exit_if_cant)
  local timer=rd(0x9D); local w=0
  while rd(0x17)~=0x10 do fa(); w=w+1
    if exit_if_cant and rd(0x9D)==(timer-1)%256 then return false end
    if w>1200 then stall=stall+1; return false end end
  stall=0; return true
end
local function press_opt(b,times) for _=1,times do wait_ready(); press(b) end end
local function wait_page() local w=0 while rd(0x0200)~=0xF0 do fa(); w=w+1; if w>1800 then return false end end return true end
local function do_save() ss_req=1; while ss_req~=0 do fa() end return ss_blob end
local function next_para(times)
  if type(times)=="number" then for _=1,times do if wait_page() then press("A") end end
  else while wait_ready(true)==false do if not wait_page() then break end; press("A") end end
end
local function option_view(opt,rep,dont_reset)
  for _=1,rep do local i=1
    while opt[i] do wait_ready(); local tries=0
      while rd(0x2C)~=opt[i]-1 do press_opt("down",1); wait_ready(); tries=tries+1; if tries>12 then break end end
      press_opt("A",1); i=i+1 end
    i=i-1; next_para("to_next_option")
    if not dont_reset then while opt[i] do wait_ready(); while rd(0x2C)~=0 do press_opt("up",1); wait_ready() end; press_opt("B",1); i=i-1 end end
  end
end
-- 错误输入(第二章 V-MH/MH 制造编号方向格):先等就绪 $15==0xFF,再按方向序列
local function wi(seq)
  local w=0
  while rd(0x15)~=0xFF do fa(); w=w+1; if w>4000 then return end end  -- 超时防挂(输入屏没出现)
  for _,b in ipairs(seq) do press(b); fa(); fa() end
end
local function wi_VMH() wi({"up","right","up","right","up","A"}) end
local function wi_MH()  wi({"up","right","up","A"}) end
-- 推过 CG 过场($0200=FF,如穿梭机发射):按 A 推进,直到菜单就绪或对话页(不靠 wait_ready 的短超时)
local function advance_cg(maxf)
  local f0=frame
  while (frame-f0)<(maxf or 6000) do
    if rd(0x17)==0x10 or rd(0x0200)==0xF0 then return true end
    if (frame-f0)%30<3 then press("A") else fa() end
  end
  return false
end

-- 步骤表(照搬 mesen_gui_scenetrace 的前进序列,每行=一步,可续跑)
local STEPS={
  function() option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},1); option_view({2,2,1},2); option_view({3},1,true) end,
  function() option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},2); option_view({2,2},2); option_view({3},2,true); option_view({3,1},1,true) end,
  function() option_view({1,1},2); option_view({1,2},3); option_view({2,1,1},4); option_view({2,1,2},2); option_view({3},1,true) end,
  function() option_view({3,3},1,true) end,
  function() option_view({1,1},2); option_view({1,2},1); option_view({2,1},1); option_view({2,1,1},2); option_view({2,1,2},1,true) end,
  function() press_opt("down",1); press_opt("A",1); next_para("to_next_option") end,
  function() option_view({1,1},1); option_view({2,1},1); option_view({2,2},1); option_view({1,2},1,true) end,
  function() press_opt("down",1); press_opt("A",1); next_para("to_next_option") end,
  function() press_opt("down",1); press_opt("A",1); next_para("to_next_option") end,
  function() press_opt("A",1); next_para("to_next_option") end,
  function() option_view({1,1},2); option_view({1,2},1); option_view({1,3},1); option_view({2,1},1); option_view({2,2},1) end,
  function() press_opt("down",3); press_opt("A",1); next_para(1) end,
  function() wait_ready(); press_opt("A",1); wait_ready() end,
  function() option_view({3},1,true) end,
__STAGE2_STEPS__
}

co=coroutine.create(function()
  if START_STEP==0 then
    while frame<3300 do fa() end
    press("start"); for _=1,40 do fa() end
    next_para("to_next_option")
  end
  for si=START_STEP+1,#STEPS do
    CUR_STEP=si
    print("DOSTEP "..si.." $0450="..string.format("%02X",rd(0x0450)))
    STEPS[si]()
    print("DONESTEP "..si.." $0450="..string.format("%02X",rd(0x0450)).." stall="..stall)
    last_blob=do_save(); last_step=si   -- 每步完成存干净检查点
    if frame>=CAP or stall>=4 then CKPT=true; return end
  end
  SEQ_DONE=true
end)
"""


# 第二章 stage_2_1+stage_2_2 扁平 op 列表(照搬原始 FCEUX 自动化.lua;option_view 可断点,press/next/wi 组原子)
STAGE2_OPS = [
    "advance_cg()", 'press_opt("A",1)', "next_para(2)",
    "option_view({1},1)", "option_view({2,1},2)", "option_view({3,1},1,true)",
    "option_view({1,1},1)", "option_view({2,1},1,true)",                                                  # moonface
    "option_view({1,1},1)", "option_view({2,1},1)", "option_view({2,2},1)", "option_view({3,1},1,true)",  # 调查moonface
    "option_view({1,1},6)", "option_view({1,2},1)", "option_view({2},1,true)",                            # 驾驶室
    "option_view({1,1},1)", "option_view({1,2},1)",                                                       # 登机
    "option_view({2,2},1,true)",                                                                          # 调查561
    "option_view({1,1},1,true)", 'press_opt("A",1); next_para("to_next_option")',
    "option_view({1,1},1)", "option_view({2,1},1,true)",                                                  # station bay
    "option_view({1,1},1)", "option_view({1,2},1)", "option_view({2,1},1)", "option_view({2,2},1)",       # data room
    "option_view({1,1},1)", "option_view({1,2},1)", "option_view({2,1},1)",                               # 调查前台
    'press_opt("down",1); press_opt("A",1); press_opt("down",1); press_opt("A",1); next_para(1); wi_VMH(); wi_VMH(); wi_VMH(); next_para("to_next_option")',  # V-MH输入
    "option_view({1,1},1)", "option_view({1,2},1)", "option_view({2,1},1,true)",                          # 调查561
    "option_view({1,1},1)", "option_view({2,1},1)", "option_view({2,2},1,true)",                          # 调查moonface
    "option_view({2,1},1)", "option_view({2,2},1,true)",                                                  # 驾驶室
    "option_view({1,1},1)", "option_view({2,1},1)", "option_view({2,2},1,true)",                          # main floor
    "option_view({1,1},1)", "option_view({2,1},1)", "option_view({2,3},1)", "option_view({2,1},1)", "option_view({2,2},2)", "option_view({1,1},2)", "option_view({1,1},1)", "option_view({1,1},4)",  # sub floor
    "option_view({1,1},1)", "option_view({1,2},2)", "option_view({2,1},2)", "option_view({2,2},1)", "option_view({2,3},1)", "option_view({1,1},1)", "option_view({1,2},1)",  # data office
    "option_view({1,1},2)", "option_view({1,2},1)", "option_view({1,3},1)", "option_view({2,1},1)", "option_view({2,2},1)", "option_view({1,1},2,true)",  # mechanic
    "option_view({1,1},1)", "option_view({1,2},1,true)", "option_view({1,1},1,true)", "option_view({2},2)", "option_view({1},2)", "option_view({3},1,true)", "option_view({1,2},1,true)",  # data office
    "option_view({1,1},2)", "option_view({1,2},2)", "option_view({2},1)", "option_view({3},1,true)", "option_view({1,3},1,true)",  # mechanic
    "option_view({1},1)", 'press_opt("down",2); press_opt("A",1); next_para(1); wait_ready(); press_opt("A",1); wait_ready()',  # 上船
    "option_view({2,1},1,true)", "option_view({1,1},1)", "option_view({1,2},1)", "option_view({1,3},1,true)",
    "option_view({1,1},1)", "option_view({2,1},1,true)",                                                  # 调查驾驶室
    "option_view({1,1},1)", "option_view({1,2},1)", "option_view({2,1},1)", "option_view({2,2},1)", "option_view({3},1,true)",  # 调查
    "option_view({1,1},1)", "option_view({1,2},1)", "option_view({2,1},1)", "option_view({2,2},1)",
    'press_opt("down",1); press_opt("A",1); press_opt("down",1); press_opt("A",1); next_para(12)',
    "option_view({1,1},3)", "option_view({2,1},5)", "option_view({2,2},1)", "option_view({2,3},4)", "option_view({3},2)", "option_view({2,3},1,true)",  # 希尔琪奴
    "option_view({1,1},1,true)", "option_view({1,1},1)", "option_view({2},1,true)", "option_view({1,1,1},1)", "option_view({1,1,2},2)", "option_view({2},2)", "option_view({3},1,true)", "option_view({1,2},1,true)",
    'press_opt("down",1); press_opt("A",1); next_para(1); wait_ready(); press_opt("A",1); next_para(1)',
    "option_view({1,1},1,true)", 'wait_ready(); press_opt("A",1); next_para("to_next_option")',
    "option_view({1,1},1)", "option_view({2,1},1,true)", "option_view({1},1)", "option_view({2},1)", "option_view({3},1,true)",  # 回到bay
    'press_opt("down",1); press_opt("A",1); next_para("to_next_option"); press_opt("A",1); next_para(15)',
    "option_view({1,2},1)", "option_view({1,1},4)", "option_view({1,1},1,true)", "option_view({1,2},3,true)", "option_view({1,1},2)", "option_view({1,2},1,true)",
    "option_view({1,1},1)", "option_view({1,2},1)", "option_view({1,3},1)", "option_view({1,4},1)", "option_view({2},1,true)", "option_view({1,3},1,true)", "option_view({1,1},1,true)",
    'press_opt("down",1); press_opt("A",1); next_para(1); wait_ready(); press_opt("A",1); wait_ready()',
    "option_view({1,1},1,true)",
    # ===== stage_2_2 =====
    "option_view({1,1},1)", "option_view({2,1},1,true)", "option_view({1,1},2)", "option_view({2,1},1)", "option_view({2,2},1)", "option_view({3,1},1,true)",
    "option_view({1,1},1)", "option_view({1,2},2)", "option_view({2,1},1)", "option_view({2,2},3)", "option_view({3},1,true)",
    "option_view({1,1},1)", "option_view({1,2},1)", "option_view({2},1,true)", "option_view({1,2},1)", "option_view({1,1},1)", "option_view({2,1},1,true)", "option_view({1,1},1)",
    'press_opt("A",1); press_opt("down",1); press_opt("A",1); next_para(3); press_opt("down",1); press_opt("A",1); next_para(1); wait_ready(); press_opt("A",1); next_para(1)',
    "option_view({1,3},1,true)", "option_view({1,1},1,true)", "option_view({1,1},1)", "option_view({1,2},1)", "option_view({1,3,1},2)", "option_view({1,3,2},5)", "option_view({2},1,true)",
    "option_view({1,1},1,true)", "option_view({1,1},1)", "option_view({1,2},1)", "option_view({1,3},1)", "option_view({2},1,true)",
    "option_view({1,2},4)", "option_view({1,3},4)", "option_view({1,4},4)", "option_view({1,1},6)", "option_view({1,1},1,true)", "option_view({2,1},4)", "option_view({2,2},4)", "option_view({2,3},4)", "option_view({2,4},4)", "option_view({1},1,true)",
    "option_view({1},2)", "option_view({2},2)", "option_view({3},3)", "option_view({4},3)", "option_view({3},3)", "option_view({3},1,true)",  # 女服务员
    'press_opt("A",1); next_para(1); wait_ready(); press_opt("A",1); next_para("to_next_option")',
]


def _gen_stage2_steps():
    """把 STAGE2_OPS 按权重切成小步(每步≤5导航单元,只在 option_view 后断),生成 Lua 步函数。"""
    import re as _re
    def w(op):
        m = _re.search(r"option_view\(\{[^}]*\},(\d+)", op)
        if m: return int(m.group(1))
        if "next_para(12)" in op or "next_para(15)" in op: return 2
        if "wi_VMH" in op: return 3
        return 1
    steps, cur, cw = [], [], 0
    for op in STAGE2_OPS:
        cur.append(op); cw += w(op)
        if op.startswith("option_view") and cw >= 5:
            steps.append(cur); cur, cw = [], 0
    if cur: steps.append(cur)
    return "\n".join("  function() " + "; ".join(s) + " end,  -- 第二章步" + str(i) for i, s in enumerate(steps))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    rom = os.path.join(os.path.dirname(os.path.dirname(here)), "roms", os.environ.get("ROM", "MSG-zh-demo.nes"))
    W = sys.argv[1] if len(sys.argv) > 1 else "."
    state = sys.argv[2] if len(sys.argv) > 2 else None
    step = sys.argv[3] if len(sys.argv) > 3 else "0"
    hexs = open(state).read().strip() if state and os.path.exists(state) else ""
    cap = os.environ.get("SEQ_CAP", "16000")
    savescenes = "1" if os.environ.get("SAVE_SCENES") else "0"
    shots = "1" if os.environ.get("QA_SHOTS") else "0"
    lua = (LUA.replace("__STAGE2_STEPS__", _gen_stage2_steps())
           .replace("__NMI__", str(NMI)).replace("__START_HEX__", hexs)
           .replace("__START_STEP__", step).replace("__CAP__", cap).replace("__SAVESCENES__", savescenes)
           .replace("__SHOTS__", shots))
    out = run_lua(lua, rom, timeout=int(int(cap) / 130) + 50)
    # 每场景入口 checkpoint → scene_ckpt/<hex>
    ckdir = os.path.join(W, "scene_ckpt"); os.makedirs(ckdir, exist_ok=True)
    for ln in out.splitlines():
        if ln.startswith("SCENECKPT "):
            p = ln.split(" ", 2)
            fn = os.path.join(ckdir, f"scene_{p[1]}.hex")
            if not os.path.exists(fn): open(fn, "w").write(p[2]); print("SCENECKPT ->", fn)
    for ln in out.splitlines():
        if ln.startswith(("DOSTEP", "DONESTEP", "END", "SCENE", "CORO_ERR", "PAGE")):
            print(ln)
    # 累积句号→场景映射(跨段拼全图)
    nlines = [ln for ln in out.splitlines() if ln.startswith("N\t")]
    with open(os.path.join(W, "scene_map.tsv"), "a") as f:
        for ln in nlines:
            f.write(ln + "\n")
    # ★NRAW 原始采样(A001/A001/ptr/scene)→ nraw.tsv,供宿主反查表映射真实句号(深句可靠)
    rawlines = [ln for ln in out.splitlines() if ln.startswith("NRAW\t")]
    with open(os.path.join(W, "nraw.tsv"), "a") as f:
        for ln in rawlines:
            f.write(ln + "\n")
    print(f"本段新增句号采样 {len(nlines)} 行 → scene_map.tsv;NRAW {len(rawlines)} 行 → nraw.tsv")
    pngs = extract_pngs(out, W, prefix="seq")
    # 每页对话截图 → 裁对话框区存 qa_pages/(跨段累积,按 句号_场景 去重)
    from PIL import Image
    pagedir = os.path.join(W, "qa_pages"); os.makedirs(pagedir, exist_ok=True)
    npg = 0
    for tag, p in pngs:
        if tag.startswith("s"):
            im = Image.open(p).crop((0, 160, 256, 240))
            im.save(os.path.join(pagedir, f"{tag}.png")); npg += 1
        elif tag == "final":
            os.replace(p, os.path.join(W, "seqrun_final.png")); print("SHOT ->", os.path.join(W, "seqrun_final.png"))
    print(f"本段对话页截图 {npg} 张 → qa_pages/")
    blob = extract_blob(out, "end")
    if blob:
        open(os.path.join(W, "seqrun_end.hex"), "w").write(blob); print("STATE_OUT -> seqrun_end.hex")


if __name__ == "__main__":
    main()
