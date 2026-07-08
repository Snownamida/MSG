#!/usr/bin/env python3
"""爬虫探测模块:probe(state_hex) 探一个菜单态的所有选项。
每选项:回档→光标到i→按A→只在有对话箭头($0200==F0)时推进并记句子(子菜单无箭头→自然停)→
分类 goto(换场景)/stay(留本场景,存结果态供递归)/empty(选项不存在)。返回结构 + 各 stay/goto 的子状态hex。
"""
import json, os
_MSG = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # senmap/→reversing/→项目根
import sys
sys.path.insert(0, _MSG + "/reversing/tools")
from mesen import run_lua, NMI

ROM = _MSG + "/roms/MSG-zh-demo.nes"

_LUA_TMPL = r'''
pcall(emu.setEmulationSpeed,0)
local PRG=emu.memType.nesPrgRom
local function prg(o) return emu.read(o,PRG) end
local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local KEY={a="a",b="b",d="down",u="up"}
local want=IDLE
emu.addEventCallback(function() pcall(emu.setInput,want,0) end, emu.eventType.inputPolled)
local function set(b) local t={} for k,v in pairs(IDLE) do t[k]=v end if b then t[KEY[b] or b]=true end want=t end
local frame=0
emu.addEventCallback(function() frame=frame+1 end, emu.eventType.startFrame)
local lastN=-1; local seq={}
emu.addMemoryCallback(function()
  local p=rd(0x87)+rd(0x88)*256; local n
  if p>=0xBCB5 and p<0xBFFF and rd(0xA000)==prg(0) then n=(p-0xBCB5)//3
  elseif p>=0xA000 and p<0xBD4B and rd(0xA000)==prg(0x2000) then n=(p-0xA000)//3+281 end
  if n and n~=lastN then lastN=n; seq[#seq+1]=n end
end, emu.callbackType.exec, 0xF071, 0xF071)

local MAXOPT=__MAXOPT__
local LOADED=false; local menu_blob=nil; local sc0=nil
local opt=0; local co=nil; local save_req=false; local save_out=nil
local function newco(o)
  return coroutine.create(function()
    local function yf(n) for _=1,(n or 1) do coroutine.yield() end end
    local function tap(b,h,g) set(b); yf(h or 4); set(nil); yf(g or 12) end
    emu.loadSavestate(menu_blob); yf(12); seq={}; lastN=-1
    local tries=0
    while rd(0x2C)~=o and tries<16 do tap("d",4,10); tries=tries+1 end
    if rd(0x2C)~=o then print(string.format('NODE {"opt":%d,"kind":"empty"}', o)); return end
    tap("a",6,18)
    -- ★鲁棒推进:按DOWN测光标区分 菜单(光标动→到达,停)vs 对话(光标不动→按A推进)。
    -- beach对话不用$0200箭头,故不能靠它。
    local kind="stay"
    for it=1,40 do
      if rd(0x0450)~=sc0 then kind="goto"; break end
      local c0=rd(0x2C)
      set("down"); yf(3); set(nil); yf(9)
      if rd(0x2C)~=c0 then          -- 光标动了=到了菜单
        local t=0; while rd(0x2C)~=0 and t<14 do set("up"); yf(3); set(nil); yf(7); t=t+1 end  -- 复位光标0
        break
      else
        tap("a",4,10)               -- 对话/过场:推进
      end
    end
    yf(8)
    local sc1=rd(0x0450)
    save_req=true; while save_req do yf() end   -- 存结果态
    print(string.format('NODE {"opt":%d,"kind":"%s","scene":"%02X","seq":[%s],"cursor":%d,"arrow":"%02X"}',
      o, kind, sc1, table.concat(seq,","), rd(0x2C), rd(0x0200)))
    print("CHILD "..o.." "..save_out)
  end)
end
local rep=false
emu.addMemoryCallback(function()
  if not LOADED then if frame>=20 then emu.loadSavestate(unhex("__BLOB__")); LOADED=true end return end
  if frame<30 then return end
  if menu_blob==nil then menu_blob=emu.createSavestate(); sc0=rd(0x0450)
    print(string.format('MENU {"scene":"%02X","cursor":%d,"arrow":"%02X","mid":%d}', rd(0x0450),rd(0x2C),rd(0x0200),rd(0x87)+rd(0x88)*256))
    -- 零页状态(收敛键基础;$08/$17/$9D/$E1 是易变计数器,宿主会掩掉)
    local zp={} for a=0,0xFF do zp[#zp+1]=string.format("%02x",rd(a)) end
    print("ZP "..table.concat(zp))
    co=newco(opt); return end
  if save_req then save_out=_hex(emu.createSavestate()); save_req=false end
  if co and coroutine.status(co)~="dead" then local ok,e=coroutine.resume(co); if not ok then print("ERR "..tostring(e)) end return end
  opt=opt+1
  if opt>MAXOPT then if not rep then rep=true; emu.stop(0) end return end
  co=newco(opt)
end, emu.callbackType.exec, __NMI__, __NMI__)
'''


def probe(state_hex, maxopt=6, timeout=200):
    lua = (_LUA_TMPL.replace("__MAXOPT__", str(maxopt))
           .replace("__BLOB__", state_hex).replace("__NMI__", str(NMI)))
    out = run_lua(lua, ROM, timeout=timeout)
    menu = None; options = []; children = {}
    for ln in out.splitlines():
        if ln.startswith("MENU "): menu = json.loads(ln[5:])
        elif ln.startswith("ZP "):
            if menu is not None: menu["zp"] = ln[3:].strip()
        elif ln.startswith("NODE "): options.append(json.loads(ln[5:]))
        elif ln.startswith("CHILD "):
            p = ln.split(" ", 2); children[int(p[1])] = p[2]
        elif ln.startswith("ERR"): print("  [lua]", ln, file=sys.stderr)
    return menu, options, children


if __name__ == "__main__":
    st = open(sys.argv[1]).read().strip()
    m, o, c = probe(st, int(sys.argv[2]) if len(sys.argv) > 2 else 5)
    print(json.dumps({"menu": m, "options": o}, ensure_ascii=False))
    print("children:", list(c), file=sys.stderr)
