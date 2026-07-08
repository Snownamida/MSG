// chapter1.ink → 自包含 HTML 文字冒险播放器（inkjs 运行时 + 剧本内联，本地双击即玩）。
// 依赖 inkjs（npm i inkjs）。路径可用环境变量覆盖：
//   INKJS_FULL = ink-full.js（编译器，默认 'inkjs/full'）
//   INKJS_RT   = ink.js（运行时，内联进 HTML；默认从 INKJS_FULL 同目录取）
// 用法: node ink_to_html.js <in.ink> <out.html>
// ⚠ 产物含译文 → gitignore，仅本地打开，勿上传外部服务。
const fs = require("fs"), path = require("path");

const FULL = process.env.INKJS_FULL || "inkjs/full";
const inkjs = require(FULL);
const RT = process.env.INKJS_RT ||
  path.join(path.dirname(require.resolve(FULL)), "ink.js");

const [, , inkPath, outPath] = process.argv;
const src = fs.readFileSync(inkPath, "utf8");
const story = new inkjs.Compiler(src).Compile();
const json = story.ToJson().replace(/<\//g, "<\\/");   // 防 </script> 提前闭合
const runtime = fs.readFileSync(RT, "utf8");

const html = `<!doctype html>
<html lang="zh"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>合金月神 · 第一章</title>
<style>
  :root{--bg:#14141f;--ink:#e8e6df;--dim:#8a8798;--accent:#6cc6b8;--gold:#d8b86a}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:"Hiragino Sans","PingFang SC","Microsoft YaHei",system-ui,serif;
    line-height:1.9;font-size:17px}
  #wrap{max-width:640px;margin:0 auto;padding:48px 22px 120px}
  h1{font-size:22px;color:var(--gold);font-weight:600;letter-spacing:2px;
    border-bottom:1px solid #2a2a3a;padding-bottom:14px;margin-bottom:28px}
  .line{margin:0 0 14px;animation:fade .5s ease}
  .chosen{color:var(--dim);font-size:15px;margin:18px 0 6px;padding-left:2px}
  .end{color:var(--gold);text-align:center;margin-top:40px;letter-spacing:4px}
  #choices{position:sticky;bottom:0;background:linear-gradient(transparent,var(--bg) 24px);
    padding-top:24px;display:flex;flex-direction:column;gap:8px}
  .choice{font:inherit;text-align:left;color:var(--ink);background:#1e1e2e;
    border:1px solid #34344a;border-radius:10px;padding:12px 16px;cursor:pointer;
    transition:.15s;line-height:1.6}
  .choice:hover{border-color:var(--accent);background:#23233a;color:#fff;transform:translateX(3px)}
  @keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
</style></head><body>
<div id="wrap">
  <h1>合金月神 · 第一章</h1>
  <div id="story"></div>
  <div id="choices"></div>
</div>
<script>${runtime}</script>
<script>
const storyContent = ${json};
const story = new inkjs.Story(storyContent);
const storyEl = document.getElementById("story");
const choicesEl = document.getElementById("choices");
function step(){
  while(story.canContinue){
    const t = story.Continue().trim();
    if(t){ const p=document.createElement("p"); p.className="line"; p.textContent=t; storyEl.appendChild(p); }
  }
  choicesEl.innerHTML="";
  story.currentChoices.forEach((c,i)=>{
    const b=document.createElement("button"); b.className="choice"; b.textContent=c.text;
    b.onclick=()=>{
      const ch=document.createElement("p"); ch.className="chosen"; ch.textContent="▸ "+c.text; storyEl.appendChild(ch);
      story.ChooseChoiceIndex(i); step();
      window.scrollTo({top:document.body.scrollHeight,behavior:"smooth"});
    };
    choicesEl.appendChild(b);
  });
  if(story.currentChoices.length===0){
    const e=document.createElement("p"); e.className="end"; e.textContent="—— 完 ——"; choicesEl.appendChild(e);
  }
}
step();
</script>
</body></html>`;

fs.writeFileSync(outPath, html);
console.log("生成", outPath, (html.length/1024|0)+"KB（含内联 inkjs 运行时 + 剧本）");
