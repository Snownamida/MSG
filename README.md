# 合金月神（Metal Slader Glory）中文化

[HAL 研究所 1991 年的 FC 视觉小说《Metal Slader Glory》](https://en.wikipedia.org/wiki/Metal_Slader_Glory)——
当年唯一的 1MB FC 卡带，文本量巨大，剧本以**两级字典压缩**存储。本项目逆向了整套文本 / 渲染引擎，
把全部 2781 句剧本解出、翻译并回写，目标是一个**完整可玩的中文版**。

## 当前状态

- **第一章可玩版**：118 句主线 + 41 回访对话中文化；立绘/头像/启动/密语存档全部正常。
- **引擎逆向**：文本系统、MMC5 分屏渲染、字库 bank 机制、内存映射全部摸清（见 `docs/`）。
- **多 bank 字库**：靠单点 asm 钩子让每个场景自动用独立中文字库 bank，绕开 256 tile/bank 限制。
- 进行中：全量翻译推广、热点场景第二 bank、句子地图导出 Ink（文字游玩）。

ROM 请**自备**（版权原因不随仓库分发），放入 `roms/`，命名 `Metal Slader Glory (Japan).nes`。

## 目录结构

```
src/          汉化构建工具链（从项目根运行）
  msgtool.py       文本系统解析/导出（零依赖）
  structio.py      结构化导出/回写（保留演出 token）
  reinsert_full.py 全量回写编码器（装箱架构）
  build_ch1_mb.py  第一章多 bank 构建（主入口）
roms/         ROM 与 .cdl（gitignored）
docs/         结构化知识库 ↓
reversing/
  tools/           逆向工具（dis6502 反汇编、mesen 无头驱动、seqrun/play/crawler…）
  senmap/          句子地图爬虫（菜单树 DFS）
  data/            trace / 场景映射 / 句子地图产物
lua/          Mesen Lua 脚本（GUI/无头 trace、自动游玩）
fonts/        Fusion Pixel Font（OFL，随仓库）
translation/  译文（结构化定稿 struct_full + flat 草稿）+ 术语表
archive/      历史脚本存档（不再维护）
```

## 文档（`docs/`）

| 文档 | 内容 |
|---|---|
| [TEXT_SYSTEM.md](docs/TEXT_SYSTEM.md) | 文本系统：两级字典压缩、编码、控制码、数据流 |
| [ENGINE.md](docs/ENGINE.md) | 渲染引擎：MMC5、tile 几何、例程地图、分屏、两套 emit |
| [MEMMAP.md](docs/MEMMAP.md) | 逐字节内存 / 寄存器映射表 |
| [LOCALIZATION.md](docs/LOCALIZATION.md) | 汉化实现方案（字模 / bank / 回写 / 密语），当前限制 |
| [HISTORY.md](docs/HISTORY.md) | 研发历程时间线（里程碑、死胡同、教训） |
| [CHAPTER1.md](docs/CHAPTER1.md) | 第一章内容地图（流程/机制/各场景对话） |

## 快速上手

```bash
# 导出日文剧本 / 字典 / 用途图谱
python3 src/msgtool.py export
python3 src/msgtool.py map

# 构建第一章汉化 ROM（→ roms/MSG-zh-demo.nes）
python3 src/build_ch1_mb.py

# 无头逆向观测（需 Mesen.app）
python3 reversing/tools/play.py --shot out.png
```

脚本用 `ROOT` 锚定（`__file__` 相对定位），可从任意目录运行。仅需 Python 3.9+；
`reinsert_full` 的字模渲染需 Pillow。

## 许可

代码 MIT © Snownamida。游戏文本 / 剧本版权归 HAL 研究所，逆向与译文仅供研究和爱好者翻译交流。
ROM 请自备（不随仓库分发）。字体 Fusion Pixel Font 为 OFL 授权。
