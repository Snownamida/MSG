#!/usr/bin/env python3
"""纯静态菜单选项解析器(白盒正解:解菜单定义数据的语法,不跑游戏猜)。

动态 DOWN 测遍历的病根:靠"跑游戏按按钮、看光标动不动"猜选项类型,选项语义多样时会
猜错、漏项(海边查看只探到大海/山丘,漏机场)。正解是读菜单定义数据本身——它是确定的语法:

  菜单定义 = 顶层命令块链(查看/交谈/回头看/休息…),块地址存在 $04E8 选项指针表。
  每块 = 标签句号(头2字节,小端,Lua系) + 内容 bytecode。
  内容里 **`$50 <标签句>` / `$02 <标签句>` = 一个子选项**(50=看景/话题,02=看人/导航)。
    句100=前往(切场景) · 句102=回头看。中间夹坐标命令($01/$05/$C1/$0A)与对话 bytecode。

按相邻块指针差切块边界,块内扫 $50/$02 <标签>,去重 + 剔除块自引用 + 剔除对话句(带「),
即得完整选项树——比动态遍历完整(不漏"探尽才解锁"的选项),且无需 DOWN 测猜类型。

现为"半静态":动态读一次菜单定义字节(避开 $5115 bank 映射定位),之后解析纯静态。
纯 ROM 定位需另解 bank 映射($5115 菜单态=143,≠脚本 bank $C5)。

用法: staticmenu.py <scene.hex>
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from mesen import run_lua, NMI

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
blob = open(sys.argv[1]).read().strip()

LUA = r'''
pcall(emu.setEmulationSpeed,0)
local frame=0
emu.addEventCallback(function() frame=frame+1 end, emu.eventType.startFrame)
local co=coroutine.create(function()
  for _=1,40 do coroutine.yield() end
  print("SCENE "..string.format("%02X", rd(0x0450)))
  local base=rd(0x0529+rd(0x21))
  local ptrs={}
  for opt=0,7 do local p=rd(0x04E8+base+opt*2)+rd(0x04E8+base+opt*2+1)*256
    if p==0 then break end; ptrs[#ptrs+1]=p end
  print("PTRS "..table.concat(ptrs," "))
  if #ptrs>0 then
    local lo=ptrs[1]; local hi=ptrs[#ptrs]+90
    local d={}; for a=lo,hi do d[#d+1]=string.format("%04X:%02X",a,rd(a)) end
    print("MEM "..table.concat(d," "))
  end
end)
local loaded=false; local fin=false
emu.addMemoryCallback(function()
  if not loaded then if frame>=20 then emu.loadSavestate(unhex("__BLOB__")); loaded=true end return end
  if coroutine.status(co)~="dead" then coroutine.resume(co) elseif not fin then fin=true; emu.stop(0) end
  if frame>1200 then emu.stop(0) end
end, emu.callbackType.exec, __NMI__, __NMI__)
'''.replace("__BLOB__", blob).replace("__NMI__", str(NMI))

out = run_lua(LUA, os.path.join(_ROOT, "roms", "MSG-zh-demo.nes"), timeout=120)

TR = {}
for l in open(os.path.join(_ROOT, "translation", "struct_full.tsv"), encoding="utf-8"):
    if "\t" in l:
        a, b = l.split("\t", 1)
        if a.strip().isdigit():
            TR[int(a)] = re.sub(r'~[0-9A-Fa-f]+~|\{[sg][0-9A-Fa-f]{2}\}', '', b).replace('/', ' ').strip()
def s(luan): return TR.get(luan + 1, f"?{luan}")          # Lua句号 → tr(LUA_OFF=1)
def isl(luan):                                            # 是"选项标签"(短名,无对话符号,非职员表越界)
    t = s(luan)
    return len(t) <= 7 and "「" not in t and not t.startswith("?") and not re.search(r'[A-Za-z]', t)

scene = "??"; ptrs = []; mem = {}
for l in out.splitlines():
    if l.startswith("SCENE"): scene = l.split()[1]
    elif l.startswith("PTRS"): ptrs = [int(x) for x in l[5:].split()]
    elif l.startswith("MEM"):
        for tok in l[4:].split():
            a, v = tok.split(":"); mem[int(a, 16)] = int(v, 16)

print(f"=== 场景{scene} 纯静态选项树({len(ptrs)}个顶层命令块)===")
for bi in range(len(ptrs)):
    lo = ptrs[bi]; hi = ptrs[bi + 1] if bi + 1 < len(ptrs) else ptrs[bi] + 74
    head = mem.get(lo, 0) | mem.get(lo + 1, 0) << 8
    seen = set(); opts = []
    i = lo + 2
    while i < hi - 2:
        pre = mem.get(i); lab = mem.get(i + 1, 0) | mem.get(i + 2, 0) << 8
        if pre in (0x50, 0x02) and mem.get(i + 2) == 0 and 0 < lab < 200 \
           and lab != head and lab not in seen and isl(lab):
            seen.add(lab); opts.append(lab); i += 3
        else:
            i += 1
    print(f"\n■ {s(head)}(块@{lo:04X}):")
    for lab in opts:
        tag = "  →前往(切场景)" if lab == 100 else ("  →回头看" if lab == 102 else "")
        print(f"    {s(lab)}{tag}")
print("\nSTATIC_DONE")
