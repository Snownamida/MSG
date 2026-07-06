#!/usr/bin/env python3
"""驱动 mesen_ch1_seg.lua 分段跑完第一章（突破 testrunner 30000 帧限）。

每段：替换模板的 __START__/__STATE__ → 跑 Mesen testrunner → 解析 STEP/STATE/SEQ/DONE。
下段用上段的 STATE(savestate hex) 续跑。累积 SEQ（句→场景bank）到 preview/ch1_full_map.tsv。
"""
import subprocess
from pathlib import Path

MESEN = "/Applications/Mesen.app/Contents/MacOS/Mesen"
ROM = "Metal Slader Glory (Japan).nes"
TEMPLATE = Path("mesen_ch1_seg.lua").read_text(encoding="utf-8")
SCRATCH = "/private/tmp/claude-503/-Users-jixiang-sun-Projects-tgv-max/172b0728-4e1b-440e-8ad9-683e2e0895a9/scratchpad"

start, state, seg = 1, "", 0
seqmap = {}   # 句号 -> 场景bank
order = []

while True:
    seg += 1
    if seg > 8:
        print("段数超上限，停"); break
    script = TEMPLATE.replace("__START__", str(start)).replace("__STATE__", state)
    cur = f"{SCRATCH}/seg_cur.lua"
    Path(cur).write_text(script, encoding="utf-8")
    print(f"--- 段{seg}: START={start}, state={'有' if state else '无'} ---", flush=True)
    try:
        out = subprocess.run([MESEN, "--testrunner", ROM, cur], capture_output=True,
                             text=True, timeout=200).stdout
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "ignore") if isinstance(e.stdout, bytes) else (e.stdout or "")
    step, newstate, done = None, None, False
    for line in out.splitlines():
        if line.startswith("SEQ\t"):
            _, n, b = line.split("\t"); n = int(n)
            if n not in seqmap: seqmap[n] = b; order.append(n)
        elif line.startswith("STEP\t"):
            step = int(line.split("\t")[1])
        elif line.startswith("STATE\t"):
            newstate = line.split("\t")[1]
        elif "== DONE ==" in line:
            done = True
    print(f"    覆盖累计 {len(seqmap)} 句；本段末 step={step}", flush=True)
    if done:
        print("=== 第一章通关序列跑完 ===")
        break
    if step is None or newstate is None:
        print("!! 本段未产出 savestate（可能卡住/序列走偏），停"); break
    start, state = step + 1, newstate

# 输出合并映射
with open("preview/ch1_full_map.tsv", "w") as f:
    for n in sorted(seqmap): f.write(f"{n}\t{seqmap[n]}\n")
print(f"\n映射写入 preview/ch1_full_map.tsv：{len(seqmap)} 句")
from collections import Counter
print("各场景bank句数:", dict(Counter(seqmap.values())))
