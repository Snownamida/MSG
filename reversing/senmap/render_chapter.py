#!/usr/bin/env python3
"""渲染全章句子地图为可读文档。读 chapter_map.json,每场景:去重展示菜单树(选项→中文对话)。
用法: render_chapter.py <workdir>"""
import sys, os, json, re
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # senmap/→reversing/→项目根

W = sys.argv[1]
cm = json.load(open(os.path.join(W, "chapter_map.json")))
TR = {}
for l in open(os.path.join(_ROOT, "translation", "struct_full.tsv"), encoding="utf-8"):
    if "\t" in l:
        a, b = l.split("\t", 1)
        if a.strip().isdigit(): TR[int(a)] = re.sub(r"~[0-9A-Fa-f]+~|\{[sg][0-9A-Fa-f]{2}\}", "", b).replace("/", "  ").strip()

SCENE_NAME = {"0A": "序幕", "30": "机甲", "67": "通电", "0B": "海边", "10": "店门口", "11": "店内(经销店)",
              "17": "查米近景", "0E": "工作间", "12": "场景12", "13": "场景13", "14": "阿源车内",
              "16": "穿梭机", "00": "密语/存档系统屏"}

def clean(n):
    return TR.get(n, f"?{n}")

out = ["# 合金月神 第一章 句子地图(爬虫自动生成·初版)", ""]
out.append("场景进程顺序: " + " → ".join(f"{s}({SCENE_NAME.get(s,s)})" for s in cm.get("scene_order", [])))
out.append("")

for sc, nodes in cm["scenes"].items():
    nm = {n["id"]: n for n in nodes}
    out.append(f"\n## 场景 {sc} {SCENE_NAME.get(sc,'')}  ({len(nodes)}节点)")
    # 收集该场景所有出现的对话句(去重,主线/回访≤216优先)
    allsent = []
    for n in nodes:
        for e in n["options"]:
            for s in e["sentences"]:
                if isinstance(s, int) and s not in allsent: allsent.append(s)
    # 菜单树(从节点0,去重防环)
    def show(nid, ind, seen):
        if nid in seen: out.append("  " * ind + f"↑回节点{nid}"); return
        seen = seen | {nid}
        for e in nm[nid]["options"]:
            ss = [s for s in e["sentences"] if isinstance(s, int)]
            txt = " / ".join(clean(s)[:26] for s in ss[:2])
            out.append("  " * ind + f"◦ 选项{e['opt']}: {txt}")
            t = e.get("target")
            if t is not None and t != nid and t in nm: show(t, ind + 1, seen)
    if 0 in nm: show(0, 0, set())
    out.append(f"  【本场景出现的对话句({len(allsent)}): {','.join(str(s) for s in sorted(allsent))}】")

doc = "\n".join(out)
open(os.path.join(W, "chapter_map.md"), "w", encoding="utf-8").write(doc)
print(doc[:2500])
print(f"\n...(完整存 {W}/chapter_map.md, {len(cm['scenes'])}场景)")
