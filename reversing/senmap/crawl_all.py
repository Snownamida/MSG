#!/usr/bin/env python3
"""逐场景爬:对 <workdir>/scene_ckpt/scene_*.hex 各跑 crawl.py → per-scene 菜单树;
合并成全章图(含 seqrun 的场景进程顺序作为 goto 链)。用法: crawl_all.py <workdir>"""
import sys, os, subprocess, glob, json, re

W = sys.argv[1]
SP = os.path.dirname(os.path.abspath(__file__))  # senmap/,crawl.py 所在
ckdir = os.path.join(W, "scene_ckpt")
ckpts = sorted(glob.glob(os.path.join(ckdir, "scene_*.hex")))
print(f"场景入口存档: {[os.path.basename(c) for c in ckpts]}", flush=True)

# 场景进程顺序(从 seqrun scene_map 的 SCENE 出现序,近似 goto 链)
order = []
smap = os.path.join(W, "scene_map.tsv")
if os.path.exists(smap):
    seen = set()
    for l in open(smap):
        p = l.split()
        if len(p) >= 3 and p[0] == "N":
            sc = p[2]
            if sc not in seen: seen.add(sc); order.append(sc)

chapter = {"scene_order": order, "scenes": {}}
for ck in ckpts:
    sc = re.search(r"scene_([0-9A-Fa-f]+)\.hex", ck).group(1)
    outj = os.path.join(W, f"map_{sc}.json")
    print(f"\n===== 爬场景 {sc} =====", flush=True)
    r = subprocess.run(["python3", os.path.join(SP, "crawl.py"), ck, outj, "40", "99"],
                       capture_output=True, text=True, timeout=1800)
    for ln in r.stdout.splitlines()[-3:]: print(" ", ln, flush=True)
    if os.path.exists(outj):
        chapter["scenes"][sc] = json.load(open(outj))["nodes"]
    json.dump(chapter, open(os.path.join(W, "chapter_map.json"), "w"), ensure_ascii=False, indent=1)

print(f"\n全章图完成:{len(chapter['scenes'])} 场景 → chapter_map.json;场景序 {order}")
