#!/usr/bin/env python3
"""句子地图 → Ink 脚本（供网页文字游玩）。

数据源（准确优先）：
- `reversing/data/ch1_sentence_scene.tsv` —— 句号→场景（实机遍历，纯数字，可靠）。据此把每句
  归到正确场景，避免爬虫菜单树"话题↔对话"错配（爬虫一个选项里混着标签句/剧情句/回访噪声，
  无法在导出层可靠还原精确分支——那是 crawl 阶段的局限，见 docs/HISTORY.md）。
- `chapter_map.json` —— 取每场景的菜单标签句集，作为"可聊话题"展示。
- `translation/struct_full.tsv` —— 译文。

产物：场景按 seqrun 进程顺序（scene_order）串成主线，玩家在场景间「前往」推进；每场景把该场景
剧情对话做成逐句翻页（▽），进入时列出"可聊话题"。含译文 → gitignore。
用法: export_ink.py [out.ink]   编译: inklecate / inkjs。
"""
import json, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CM = os.path.join(ROOT, "reversing", "data", "chapter_map.json")
SS = os.path.join(ROOT, "reversing", "data", "ch1_sentence_scene.tsv")
TSV = os.path.join(ROOT, "translation", "struct_full.tsv")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "reversing", "data", "chapter1.ink")

SCENE_NAME = {"0A": "序幕", "30": "机甲舱", "67": "通电", "0B": "海边", "10": "店门口",
              "11": "经销店内", "17": "查米近景", "0E": "工作间", "12": "海岬",
              "13": "转场", "14": "阿源车内", "16": "穿梭机", "00": "密语／存档屏"}

TR = {}
for l in open(TSV, encoding="utf-8"):
    if "\t" in l:
        a, b = l.split("\t", 1)
        if a.strip().isdigit():
            TR[int(a)] = re.sub(r"~[0-9A-Fa-f]+~|\{[sg][0-9A-Fa-f]{2}\}", "", b).replace("/", " ").strip()

def txt(n):
    return re.sub(r"\s+", " ", TR.get(n, f"（句{n}）")).strip()

def is_label(n):
    t = txt(n)
    return len(t) <= 7 and "「" not in t   # 短且无对话引号 = 菜单标签

# 每场景剧情句（准确，来自 sentence→scene 映射；排除标签句）
scene_sents = defaultdict(list)
for l in open(SS, encoding="utf-8"):
    if l.startswith("#") or not l.strip():
        continue
    p = l.split()
    if len(p) == 2 and p[0].isdigit():
        scene_sents[p[1]].append(int(p[0]))

# 每场景可聊话题（菜单标签句集，来自爬虫）
cm = json.load(open(CM))
order = cm["scene_order"]
scene_labels = defaultdict(list)
for sc, nodes in cm["scenes"].items():
    seen = set()
    for n in nodes:
        for e in n["options"]:
            for s in e.get("sentences", []):
                if isinstance(s, int) and is_label(s) and s not in seen:
                    seen.add(s); scene_labels[sc].append(s)

def story_of(sc):
    return [s for s in sorted(set(scene_sents.get(sc, []))) if not is_label(s)]

def esc(s):
    return s.replace("\n", " ").strip()

out = ["// 合金月神 · 第一章 —— 句子地图交互版（爬虫自动生成，供文字游玩）",
       "// reversing/senmap/export_ink.py 从 ch1_sentence_scene.tsv + chapter_map.json + 译文生成。",
       "", "-> start", "",
       "=== start ===",
       "《合金月神》第一章",
       "忠、艾莉娜、梓一行人为查一台神秘的作业机械「合金月神」的来历，从海边的经销店一路追寻。",
       "跟着他们走一遍，读读沿途的对话。", "",
       f"-> {'scene_' + order[0]}", ""]

for i, sc in enumerate(order):
    nxt = order[i + 1] if i + 1 < len(order) else None
    name = SCENE_NAME.get(sc, sc)
    story = story_of(sc)
    labels = scene_labels.get(sc, [])
    nxt_div = f"scene_{nxt}" if nxt else "ending"
    nxt_label = f"→ 前往 {SCENE_NAME.get(nxt, nxt)}" if nxt else "→ 休息（进入密语／存档）"

    out.append(f"=== scene_{sc} ===")
    out.append(f"# {sc} {name}")
    head = f"【{name}】"
    if labels:
        head += "可聊的话题：" + "、".join(esc(txt(s)) for s in labels) + "。"
    out.append(head)
    if not story:
        out.append(f"（过场）")
        out.append(f"-> {nxt_div}")
        out.append("")
        continue
    out.append("-> d0")
    out.append("")
    for k, s in enumerate(story):
        out.append(f"= d{k}")
        out.append(esc(txt(s)))
        if k + 1 < len(story):
            out.append(f"+ [▽] -> d{k + 1}")
        else:
            out.append(f"* [{nxt_label}] -> {nxt_div}")
        out.append("")

out += ["=== ending ===",
        "第一章到此告一段落。选「休息」会给出存档密语——下次选 CONTINUE、",
        "按假名逐字输入这句话即可读档（故密语保留原文假名，不翻译）。",
        "-> END", ""]

open(OUT, "w", encoding="utf-8").write("\n".join(out))
ns = sum(1 for sc in order if story_of(sc))
nsent = sum(len(story_of(sc)) for sc in order)
print(f"生成 {OUT}")
print(f"  {len(order)} 场景（{ns} 有对话），{nsent} 句剧情，{len(out)} 行")
