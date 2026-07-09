#!/usr/bin/env python3
"""DFS 爬虫编排器:从起始状态用 probe() 递归探索,状态签名去重建 JSON 状态图。
签名=场景+各选项(编号,类型,首2句)→自然处理回访变体/前往解锁/返回父菜单(同签名不重爬)。
用法: crawl.py <start.hex> <out.json> [maxnodes] [maxdepth]"""
import sys, json, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 同目录 crawlmod
from crawlmod import probe
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

start = sys.argv[1]; outp = sys.argv[2]
MAXNODES = int(sys.argv[3]) if len(sys.argv) > 3 else 60
MAXDEPTH = int(sys.argv[4]) if len(sys.argv) > 4 else 8

# 译文(标注句子)
TR = {}
try:
    for l in open(os.path.join(_ROOT, "translation", "struct_full.tsv"), encoding="utf-8"):
        if "\t" in l:
            a, b = l.split("\t", 1)
            if a.strip().isdigit(): TR[int(a)] = b.strip()
except Exception:
    pass

# 零页里的历史/位置字节(同菜单不同路径会变→从签名排除;实测同顶层菜单三路径 diff 得)。
# $87/$88(脚本指针)反而稳定=菜单身份,保留。$2C=光标位置,排除。
_VOL = {0x08, 0x17, 0x2C, 0x30, 0x5E, 0x62, 0x92, 0x9D, 0xA7, 0xA8,
        0xE1, 0xED, 0xEE, 0xEF, 0xF0, 0xF1, 0xF2, 0xF3}
def sig_of(menu, options):
    # ★收敛键=场景+零页逻辑状态哈希(掩掉4个易变计数器)。零页=菜单栈+脚本指针+脚本变量,
    # 干净持久(渲染噪声在$02xx-$05xx缓冲,不在零页)。同菜单/同进度→同零页→收敛。
    zp = menu.get("zp", "")
    if zp:
        b = bytearray.fromhex(zp)
        for v in _VOL:
            if v < len(b): b[v] = 0
        return menu["scene"] + ":" + b.hex()
    nopt = sum(1 for o in options if o["kind"] != "empty")
    return json.dumps([menu["scene"], menu.get("mid"), nopt])

nodes = []          # 节点列表(id=下标)
sig2id = {}
def save():
    json.dump({"nodes": nodes}, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

t0 = time.time()
def log(*a): print(f"[{time.time()-t0:6.0f}s n={len(nodes)}]", *a, flush=True)

MENU_CAP = 3   # 场景内菜单嵌套上限(枢纽→子菜单→目标对话);超过=叶子,防进度链爆炸
def crawl(state_hex, mdepth):
    menu, options, children = probe(state_hex)
    if menu is None:
        log("probe失败(无MENU)"); return None
    sig = sig_of(menu, options)
    if sig in sig2id: return sig2id[sig]
    nid = len(nodes); sig2id[sig] = nid
    node = {"id": nid, "scene": menu["scene"], "mdepth": mdepth, "options": []}
    nodes.append(node)
    log(f"节点{nid} 场景{menu['scene']} 菜单深{mdepth} 选项{sum(1 for o in options if o['kind']!='empty')}")
    save()
    for o in options:
        if o["kind"] == "empty": continue
        seq = o.get("seq", [])
        edge = {"opt": o["opt"], "kind": o["kind"], "sentences": seq,
                "preview": [f"{n}:{TR.get(n,'?')[:36]}" for n in seq[:4]]}
        ch = children.get(o["opt"])
        if ch and len(nodes) < MAXNODES:
            if o["kind"] == "goto":                       # 换场景:递归,菜单深重置
                edge["target"] = crawl(ch, 0)
            elif o["kind"] == "stay" and mdepth < MENU_CAP:  # 场景内菜单:递归到上限
                edge["target"] = crawl(ch, mdepth + 1)
        node["options"].append(edge)
        save()
    return nid

log("开始爬", start)
crawl(open(start).read().strip(), 0)
save()
log("完成。节点数", len(nodes), "→", outp)
