#!/usr/bin/env python3
"""句子地图 → 交互式状态机图（自包含 HTML，无外部依赖）。

把 chapter_map.json 画成每场景一张状态机：节点=菜单状态，边=选项，边上标转换语句
（该选项触发的首句对话），点节点看该状态所有选项的完整对话。

数据诚实性：节点/边/目标(target) 来自爬虫，**结构准确**；边上的对话来自爬虫记录的句子
序列，**去重保序**后展示——但仍可能混入菜单标签句/回到菜单的通用响应（爬虫记录的是"按下
选项后一段时间窗口内的所有句子"，无法完全区分，见 docs/HISTORY.md 的 crawl 局限）。故边上
对话标为「经过的句子」而非「精确台词」。要精确需改 crawlmod 只记"到下个菜单前的新句"并重爬。

用法: render_graph.py [out.html]   产物含译文 → gitignore。
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CM = os.path.join(ROOT, "reversing", "data", "chapter_map.json")
TSV = os.path.join(ROOT, "translation", "struct_full.tsv")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "reversing", "data", "chapter1_graph.html")

SCENE_NAME = {"0B": "海边", "10": "店门口", "11": "经销店内", "17": "查米近景",
              "0E": "工作间", "12": "海岬", "14": "阿源车内", "00": "密语／存档屏"}

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
    return len(t) <= 7 and "「" not in t

cm = json.load(open(CM))
order = cm["scene_order"]

graphs = {}
for sc in order:
    if sc not in cm["scenes"]:
        continue
    nodes = cm["scenes"][sc]
    # 场景高频噪声句（回到菜单的通用响应，出现在过半选项里）
    from collections import Counter
    freq = Counter()
    nopt = 0
    for n in nodes:
        for e in n["options"]:
            if e.get("kind") == "empty":
                continue
            nopt += 1
            for s in set(x for x in e["sentences"] if isinstance(x, int)):
                freq[s] += 1
    noise = {s for s, f in freq.items() if nopt and f >= max(2, nopt * 0.5)}

    G = {"name": SCENE_NAME.get(sc, sc), "nodes": [], "edges": []}
    for n in nodes:
        G["nodes"].append({"id": n["id"], "d": n.get("mdepth", 0)})
        for e in n["options"]:
            if e.get("kind") == "empty":
                continue
            seq = [s for s in e["sentences"] if isinstance(s, int)]
            seen, clean = set(), []
            for s in seq:
                if s not in seen:
                    seen.add(s); clean.append(s)
            # 边标签 = 首个"新剧情句"(非标签非噪声)预览；没有就用首个标签
            lead = next((s for s in clean if s not in noise and not is_label(s)), None)
            if lead is None:
                lead = next((s for s in clean if is_label(s)), None)
            label = (txt(lead)[:14] if lead else f"选项{e['opt']}")
            G["edges"].append({
                "f": n["id"], "opt": e["opt"], "to": e.get("target"),
                "kind": e["kind"], "label": label,
                "lines": [{"t": txt(s), "tag": ("标签" if is_label(s) else "噪声" if s in noise else "对话")}
                          for s in clean],
            })
    graphs[sc] = G

DATA = json.dumps(graphs, ensure_ascii=False)

HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>合金月神 · 第一章 句子地图（状态机）</title>
<style>
 :root{--bg:#14141f;--pan:#1c1c2b;--ink:#e8e6df;--dim:#8a8798;--edge:#4a4a63;
       --node:#26263a;--nodeb:#3a3a55;--accent:#6cc6b8;--gold:#d8b86a;--goto:#c97b8e}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 "PingFang SC","Microsoft YaHei",system-ui}
 header{padding:14px 20px;border-bottom:1px solid #2a2a3a}
 h1{margin:0 0 4px;font-size:18px;color:var(--gold);letter-spacing:1px}
 .hint{color:var(--dim);font-size:12.5px}
 #tabs{display:flex;flex-wrap:wrap;gap:6px;padding:12px 20px}
 .tab{padding:6px 12px;border:1px solid #34344a;border-radius:8px;background:var(--pan);
      color:var(--ink);cursor:pointer;font-size:13px}
 .tab.on{border-color:var(--accent);color:#fff;background:#23233a}
 #main{display:flex;gap:0;height:calc(100vh - 150px)}
 #canvas{flex:1;overflow:auto;position:relative}
 svg{display:block}
 .node rect{fill:var(--node);stroke:var(--nodeb);stroke-width:1.5;rx:8;cursor:pointer}
 .node.sel rect{stroke:var(--accent);stroke-width:2.5;fill:#23233a}
 .node text{fill:var(--ink);font-size:12px;pointer-events:none}
 .edge{fill:none;stroke:var(--edge);stroke-width:1.5}
 .edge.goto{stroke:var(--goto);stroke-dasharray:5 3}
 .edge.back{stroke:#3a3a4a;stroke-dasharray:2 3}
 .elabel{fill:var(--dim);font-size:11px}
 .elabel.goto{fill:var(--goto)}
 #side{width:340px;min-width:340px;background:var(--pan);border-left:1px solid #2a2a3a;
       overflow:auto;padding:16px}
 #side h2{font-size:14px;color:var(--accent);margin:0 0 10px}
 .opt{margin:0 0 16px;padding:10px;background:#191926;border-radius:8px;border:1px solid #2a2a3a}
 .opt .hd{color:var(--gold);font-size:13px;margin-bottom:6px}
 .ln{margin:3px 0;font-size:13px}
 .ln .b{font-size:10px;padding:1px 5px;border-radius:4px;margin-right:6px;vertical-align:middle}
 .b.对话{background:#243b36;color:#8fe0cd} .b.标签{background:#3a3550;color:#c8b8ea}
 .b.噪声{background:#2a2a33;color:#777}
 .empty{color:var(--dim);font-size:13px}
</style></head><body>
<header><h1>合金月神 · 第一章 · 句子地图（状态机）</h1>
<div class="hint">节点=菜单状态 · 实线边=场景内选项 · <span style="color:var(--goto)">粉虚线=换场景(goto)</span> · 灰虚线=返回/环。
边上是该选项触发的<b>首句</b>；点节点看该状态所有选项的完整对话。
<b style="color:var(--gold)">对话栏可能混菜单标签/通用句</b>（爬虫记录局限，见色标）。</div></header>
<div id="tabs"></div>
<div id="main"><div id="canvas"><svg id="svg"></svg></div>
<div id="side"><div class="empty">← 点一个节点看它的选项与对话</div></div></div>
<script>
const G = __DATA__;
const order = Object.keys(G);
let cur = order[0];
const svg = document.getElementById("svg"), side = document.getElementById("side"), tabs = document.getElementById("tabs");
const NS = "http://www.w3.org/2000/svg";
const NW = 132, NH = 34, COLW = 210, ROWH = 78, PADX = 30, PADY = 26;

order.forEach(sc=>{
  const b=document.createElement("div"); b.className="tab"+(sc===cur?" on":"");
  b.textContent=sc+" "+G[sc].name; b.onclick=()=>{cur=sc;draw();}; tabs.appendChild(b);
});

function el(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;}

function layout(g){
  const byd={}; g.nodes.forEach(n=>{(byd[n.d]=byd[n.d]||[]).push(n);});
  const pos={};
  Object.keys(byd).forEach(d=>byd[d].forEach((n,i)=>{pos[n.id]={x:PADX+d*COLW,y:PADY+i*ROWH};}));
  return pos;
}

function draw(){
  [...tabs.children].forEach((t,i)=>t.classList.toggle("on",order[i]===cur));
  const g=G[cur], pos=layout(g);
  while(svg.firstChild)svg.removeChild(svg.firstChild);
  let maxX=0,maxY=0; g.nodes.forEach(n=>{maxX=Math.max(maxX,pos[n.id].x+NW+40);maxY=Math.max(maxY,pos[n.id].y+NH+40);});
  svg.setAttribute("width",Math.max(maxX,600)); svg.setAttribute("height",Math.max(maxY,300));
  const defs=el("defs",{});
  defs.innerHTML='<marker id="ar" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#6b6b85"/></marker>';
  svg.appendChild(defs);
  // 边
  g.edges.forEach(e=>{
    if(e.to==null || !pos[e.to]) {  // 无目标(叶子/换场景未捕获):画短桩
      return;
    }
    const a=pos[e.f], b=pos[e.to];
    const x1=a.x+NW, y1=a.y+NH/2, x2=b.x, y2=b.y+NH/2;
    const back = b.x<=a.x;
    const cls = e.kind==="goto"?"goto":(back?"back":"");
    const mx=(x1+x2)/2;
    const d = back
      ? `M${x1},${y1} C${x1+40},${y1-30} ${x2-40},${y2-30} ${x2},${y2}`
      : `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
    svg.appendChild(el("path",{d,class:"edge "+cls,"marker-end":"url(#ar)"}));
    const t=el("text",{x:mx,y:(y1+y2)/2-4,class:"elabel "+cls,"text-anchor":"middle"});
    t.textContent=(e.kind==="goto"?"→ ":"")+e.label; svg.appendChild(t);
  });
  // 节点
  g.nodes.forEach(n=>{
    const p=pos[n.id], grp=el("g",{class:"node","data-id":n.id});
    grp.appendChild(el("rect",{x:p.x,y:p.y,width:NW,height:NH,rx:8}));
    const t=el("text",{x:p.x+10,y:p.y+21}); t.textContent=`#${n.id} · 深${n.d}`; grp.appendChild(t);
    grp.onclick=()=>showNode(n.id);
    svg.appendChild(grp);
  });
}

function showNode(id){
  [...svg.querySelectorAll(".node")].forEach(g=>g.classList.toggle("sel",g.dataset.id==id));
  const g=G[cur], edges=g.edges.filter(e=>e.f==id);
  let h=`<h2>节点 #${id} 的选项（${edges.length}）</h2>`;
  if(!edges.length) h+='<div class="empty">叶子节点，无进一步选项。</div>';
  edges.forEach(e=>{
    const tgt = e.kind==="goto" ? "换场景" : (e.to!=null?`→ 节点#${e.to}`:"叶子");
    h+=`<div class="opt"><div class="hd">选项${e.opt} · ${e.kind} · ${tgt}</div>`;
    e.lines.forEach(l=>{ h+=`<div class="ln"><span class="b ${l.tag}">${l.tag}</span>${l.t}</div>`; });
    h+=`</div>`;
  });
  side.innerHTML=h;
}
draw();
</script></body></html>"""

open(OUT, "w", encoding="utf-8").write(HTML.replace("__DATA__", DATA))
ne = sum(len(g["edges"]) for g in graphs.values())
nn = sum(len(g["nodes"]) for g in graphs.values())
print(f"生成 {OUT}")
print(f"  {len(graphs)} 场景状态机，{nn} 节点，{ne} 边")
