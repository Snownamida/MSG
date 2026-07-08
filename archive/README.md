# archive/ —— 历史脚本存档

各里程碑攻关时用过的一次性脚本，成果已固化进 `../docs/`（技术参考）与 `../docs/HISTORY.md`
（里程碑历程）。留存备查，不再维护；import 路径多已失效（核心库已迁入 `../src/`）。
当前活跃管线见 `../src/`。

## 汉化构建脚本（均被 `../src/build_ch1_mb.py`（多 bank 定版）取代）
- `build_ch1.py` — 单 bank 第一章版（多 bank 架构前身）
- `build_16x16.py` — 双宽 16×16 尝试（放弃，改用 fusion-8px 8×8）
- `build_8x8.py` — 8×8 原版引擎 demo
- `build_b_demo.py` — B 命门（扩 CHR 专属 bank128）NMI 补丁 demo
- `build_opening.py` — 早期拍平版开场（丢结构，演出崩）
- `build_opening_struct.py` — 诊断版，证明名字块驱动演出

## 回写工具（被 `../src/reinsert_full.py`（装箱架构）取代）
- `reinsert.py` — 早期单 bank 就地回写
- `fullreinsert.py` — 早期全量回写试验

## 驱动 / 概念验证
- `drive_segments.py` — 早期分段自动驱动（被 `../reversing/tools/seqrun.py` 取代）
- `patch_poc.py` — 最初的字模回写概念验证

## 调试 Lua（功能已并入 `../lua/mesen_headless_green.lua` 的通用 dump）
- `msg_trace.lua` — 句子指针表读取追踪
- `msg_bank_trace.lua` — MMC5 BG 4-slot bank 追踪
- `msg_attr_trace.lua` — 绿字属性写入追踪
- `debug_dump.lua` — 早期状态 dump
