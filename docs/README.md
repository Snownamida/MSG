# 知识库索引

合金月神（Metal Slader Glory, FC）中文化工程的知识库。全部逆向结论、汉化方案、内容地图都在这里，
按 **引擎原理 → 汉化实现 → 内容 → 历程** 四层组织。

## 🗺️ 知识地图

### 一、引擎原理（游戏本身怎么工作）

| 文档 | 讲什么 | 想解决什么时看 |
|---|---|---|
| [TEXT_SYSTEM.md](TEXT_SYSTEM.md) | 文本**两级字典压缩**、编码层、结构块（携带演出语义） | 剧本 2781 句是怎么存/解出来的 |
| [SCRIPT_ENGINE.md](SCRIPT_ENGINE.md) | **脚本/对话演出引擎** + 白盒反编译工具链 | "选某选项→显示哪句对话"是怎么来的；能否从代码直接推导对话 |
| [ENGINE.md](ENGINE.md) | **MMC5 分屏渲染**、字库 bank、tile 几何、例程地图 | 画面/对话框/立绘是怎么画出来的 |
| [MEMMAP.md](MEMMAP.md) | 内存 / 寄存器 **逐字节速查表** | 查某个 RAM 地址、$5xxx 寄存器、关键代码地址 |

### 二、汉化实现（我们怎么改它）

| 文档 | 讲什么 |
|---|---|
| [LOCALIZATION.md](LOCALIZATION.md) | 汉化总方案：像素字模 · 每场景独立字库 bank（单点 asm 钩子）· 数据回写 · 密语/存档 · 已知限制 |

### 三、内容与历程

| 文档 | 讲什么 |
|---|---|
| [CHAPTER1.md](CHAPTER1.md) | 第一章内容地图：场景流程 · 存档/密语 · 句子→场景映射 · 各场景对话 |
| [HISTORY.md](HISTORY.md) | 研发历程时间线：里程碑 · 死胡同 · 教训 |

## 📖 阅读路径

- **初次了解**：项目根 [README](../README.md) → `TEXT_SYSTEM` → `ENGINE` → `LOCALIZATION`
- **查引擎细节**：`MEMMAP`（速查）· `SCRIPT_ENGINE`（脚本/对话）· `ENGINE`（渲染）
- **做翻译**：`CHAPTER1` + [translation/GLOSSARY.md](../translation/GLOSSARY.md)
- **跑逆向工具**：见 `reversing/`（`tools/` 通用工具、`senmap/` 遍历+白盒反编译、`data/` 产物）

## 分工边界（避免重复查错地方）

- **渲染机制原理** 看 `ENGINE`；**同一批寄存器/地址的速查** 看 `MEMMAP`（`ENGINE` 讲“为什么”，`MEMMAP` 是“是什么/在哪”）。
- **文本编码/压缩** 看 `TEXT_SYSTEM`；**脚本如何驱动对话演出** 看 `SCRIPT_ENGINE`（前者是数据格式，后者是执行引擎）。
