# archive/ —— 历史脚本存档

各里程碑攻关时用过的一次性脚本，成果已固化进 `../REVERSING.md`。留存备查，不再维护；
import 路径可能已失效（依赖的核心库仍在仓库根目录）。当前活跃管线见根目录。

## build 脚本（早期渲染/演出尝试，均被 `../build_ch1.py` 取代）
- `build_16x16.py` — 双宽 16×16 尝试（放弃，改用 fusion-8px 8×8）
- `build_8x8.py` — 8×8 原版引擎 demo
- `build_b_demo.py` — B 命门（扩 CHR 专属 bank128）NMI 补丁 demo
- `build_opening.py` — 早期拍平版开场（丢结构，演出崩）
- `build_opening_struct.py` — 诊断版，证明名字块驱动演出

## 回写工具（被 `../reinsert_full.py`（装箱架构）取代）
- `reinsert.py` — 早期单 bank 就地回写
- `fullreinsert.py` — 早期全量回写试验

## 调试 Lua（功能已并入 `../mesen_headless_green.lua` 的通用 dump）
- `msg_trace.lua` — 句子指针表读取追踪
- `msg_bank_trace.lua` — MMC5 BG 4-slot bank 追踪
- `msg_attr_trace.lua` — 绿字属性写入追踪
- `debug_dump.lua` — 早期状态 dump
