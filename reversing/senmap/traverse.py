#!/usr/bin/env python3
"""完美遍历测绘器(脚本流正解版)。

★判定实验(commute)证明:本引擎是"脚本流"——菜单选择顺序改变内部状态($87/$88 脚本位置、
菜单栈),无可签名去重的有限状态空间。故不能靠"状态签名收敛"(那对 FSM 才成立)。
正解=**内容层面收敛**:选项签名 = (场景, 选项号, 它触发的句号集)。内容等价的选择只深入一次
→ 对话内容有限 → 必然收敛,且不漏任何"能带来新对话"的分支。goto 跨场景递归。

用法: traverse.py <start.hex> <out.json> [maxnodes] [maxdepth]
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawlmod import probe

start = sys.argv[1]; outp = sys.argv[2]
MAXNODES = int(sys.argv[3]) if len(sys.argv) > 3 else 300
MAXDEPTH = int(sys.argv[4]) if len(sys.argv) > 4 else 15
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TR = {}
try:
    for l in open(os.path.join(_ROOT, "translation", "struct_full.tsv"), encoding="utf-8"):
        if "\t" in l:
            a, b = l.split("\t", 1)
            if a.strip().isdigit(): TR[int(a)] = b.strip()
except Exception:
    pass

nodes = []
seen_edge = set()      # ★内容边去重:(scene, opt, frozenset(句号)) 探过即不再深入
seen_sent = set()      # 全局可达句(收敛指标:饱和即停探)
def save(): json.dump({"nodes": nodes, "reach": sorted(seen_sent)}, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
t0 = time.time()
def log(*a): print(f"[{time.time()-t0:6.0f}s n={len(nodes)} 句{len(seen_sent)}]", *a, flush=True)

def crawl(state_hex, depth):
    menu, options, children = probe(state_hex)
    if menu is None:
        log("probe失败"); return None
    nid = len(nodes)
    node = {"id": nid, "scene": menu["scene"], "depth": depth, "options": []}
    nodes.append(node)
    log(f"节点{nid} 场景{menu['scene']} 深{depth} 选项{sum(1 for o in options if o['kind']!='empty')}")
    for o in options:
        if o["kind"] == "empty": continue
        seq = [s for s in o.get("seq", []) if isinstance(s, int)]
        seen_sent.update(seq)
        edge = {"opt": o["opt"], "kind": o["kind"], "sentences": seq,
                "preview": [f"{n}:{TR.get(n,'?')[:30]}" for n in seq[:3]]}
        esig = (menu["scene"], o["opt"], frozenset(seq))
        ch = children.get(o["opt"])
        if ch and esig not in seen_edge and len(nodes) < MAXNODES:
            seen_edge.add(esig)                       # ★按内容去重,不按状态
            if o["kind"] == "goto": edge["target"] = crawl(ch, 0)
            elif depth < MAXDEPTH: edge["target"] = crawl(ch, depth + 1)
        node["options"].append(edge)
        save()
    return nid

log("开始遍历", os.path.basename(start))
crawl(open(start).read().strip(), 0)
save()
log("完成。节点", len(nodes), "内容边", len(seen_edge), "可达句", len(seen_sent))
print("可达句:", sorted(seen_sent))
