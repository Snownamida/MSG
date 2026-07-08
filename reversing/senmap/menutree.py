#!/usr/bin/env python3
"""白盒遍历图提取器(从引擎数据结构 $04E8 菜单表直接提取,非黑盒试探)。
递归读每层 $04E8[$0529[$21]+光标×2]→选项块→标签句(选项名),选中记 $F071 对话句,
分类 叶子/子菜单/前往。输出场景的选项树+对话句=遍历图。实测海边:交谈→梓→父母的事=句187。
雏形:子菜单节点的对话句含标签噪声待过滤;探尽解锁的选项(如机场/前往)需累积探尽。
用法: menutree.py <scene_ckpt.hex>"""
import sys, os, re
import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"tools"))
from mesen import run_lua, NMI
_ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
blob=open(sys.argv[1] if len(sys.argv)>1 else _ROOT+"/reversing/data/scene_0B.hex").read().strip()
LUA=r'''
pcall(emu.setEmulationSpeed,0)
local PRG=emu.memType.nesPrgRom
local function prg(o) return emu.read(o,PRG) end
local frame=0
emu.addEventCallback(function() frame=frame+1 end, emu.eventType.startFrame)
local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local want=IDLE
emu.addEventCallback(function() pcall(emu.setInput,want,0) end, emu.eventType.inputPolled)
local function set(b) local t={} for k,v in pairs(IDLE) do t[k]=v end if b then t[b]=true end want=t end
local dlg={}; local nd=0; local rec=false
emu.addMemoryCallback(function()
  if not rec then return end
  local p=rd(0x87)+rd(0x88)*256; local n
  if p>=0xBCB5 and p<0xBFFF and rd(0xA000)==prg(0) then n=(p-0xBCB5)//3
  elseif p>=0xA000 and p<0xBD4B and rd(0xA000)==prg(0x2000) then n=(p-0xA000)//3+281 end
  if n and not dlg[n] then dlg[n]=true; nd=nd+1 end
end, emu.callbackType.exec, 0xF071, 0xF071)
local co=coroutine.create(function()
  local function yf(x) for _=1,(x or 1) do coroutine.yield() end end
  local function tap(b) set(b);yf(3);set(nil);yf(14) end
  local function optlabels()
    local base=rd(0x0529+rd(0x21)); local out={}
    for i=0,7 do local p=rd(0x04E8+base+i*2)+rd(0x04E8+base+i*2+1)*256
      if p==0 then break end; out[#out+1]=rd(p)+rd(p+1)*256 end
    return out
  end
  local function explore(depth, path)
    if depth>3 then return end
    local labs=optlabels(); local sc0=rd(0x0450); local d0=rd(0x21)
    for i=1,#labs do
      local ent=emu.createSavestate()
      local t=0; while rd(0x2C)~=(i-1) and t<12 do tap("down"); t=t+1 end
      dlg={}; nd=0; rec=true
      tap("a"); yf(34); rec=false
      local ds={}; for n,_ in pairs(dlg) do ds[#ds+1]=n end; table.sort(ds)
      local submenu=false
      if rd(0x0450)==sc0 then local c0=rd(0x2C); set("down");yf(3);set(nil);yf(9)
        if rd(0x2C)~=c0 then submenu=true; local t=0; while rd(0x2C)~=0 and t<12 do set("up");yf(3);set(nil);yf(7);t=t+1 end end end
      if rd(0x0450)~=sc0 then
        print(string.format("%s%s[%d] ★前往→场景%02X", string.rep("  ",depth),path,labs[i],rd(0x0450)))
      else
        print(string.format("%s%s[%d] %s 对话句:{%s}", string.rep("  ",depth),path,labs[i],
          submenu and "子菜单" or "叶子", table.concat(ds,",")))
        if submenu then explore(depth+1, path.."."..labs[i]) end
      end
      emu.loadSavestate(ent); yf(12)
    end
  end
  yf(40); local sc=string.format("%02X",rd(0x0450)); print("== 场景"..sc.."白盒菜单树 =="); explore(0,sc); print("TREE_DONE")
end)
local loaded=false; local fin=false
emu.addMemoryCallback(function()
  if not loaded then if frame>=20 then emu.loadSavestate(unhex("__BLOB__")); loaded=true end return end
  if coroutine.status(co)~="dead" then local ok,e=coroutine.resume(co); if not ok then print("ERR "..tostring(e)) end
  elseif not fin then fin=true; emu.stop(0) end
  if frame>9000 then print("TO"); emu.stop(0) end
end, emu.callbackType.exec, __NMI__, __NMI__)
'''
LUA=LUA.replace("__BLOB__",blob).replace("__NMI__",str(NMI))
out=run_lua(LUA,_ROOT+"/roms/MSG-zh-demo.nes",timeout=300)
TR={}
for l in open(_ROOT+"/translation/struct_full.tsv",encoding="utf-8"):
    if "\t" in l:
        a,b=l.split("\t",1)
        if a.strip().isdigit(): TR[int(a)]=re.sub(r'~[0-9A-Fa-f]+~|\{[sg][0-9A-Fa-f]{2}\}','',b).replace('/',' ').strip()
def s(n): return TR.get(n+1,f"?{n}")[:10]
def isl(n):
    t=TR.get(n+1,"")
    return len(t)<=7 and "「" not in t
for l in out.splitlines():
    if l.startswith(("==","TREE","TO","ERR")) or "[" in l:
        l=re.sub(r"\[(\d+)\]",lambda m:f"[{s(int(m.group(1)))}]",l)
        l=re.sub(r"\{([\d,]+)\}",lambda m:"{"+",".join(s(int(x)) for x in m.group(1).split(",") if x and not isl(int(x)))+"}",l)
        print(l)
