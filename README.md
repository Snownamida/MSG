# 合金月神（Metal Slader Glory）文本导出

[HAL 研究所 1991 年的 FC 视觉小说《Metal Slader Glory》](https://en.wikipedia.org/wiki/Metal_Slader_Glory)
文本量巨大（当年唯一的 1MB FC 卡带），剧本在 ROM 里以**两级字典压缩**存储。
本项目逆向了这套文本系统，把全部 2781 句日文剧本解出为可读文本——汉化的第一步。

## 文本系统结构（逆向成果）

```
句子编号(1~2781) ──算术──▶ 句子指针 ──读3B──▶ 句子
    ──bank运算──▶ 文本块串指针 ──读到0x00──▶ 文本块串
    ──拆分──▶ 文本块 block（<0x80 单字节 / ≥0x80 双字节；即 MTE 字典）
    ──查表──▶ 文本指针 ──读3B──▶ 文本
    ──位运算解包──▶ 字符串地址+长度 ──读──▶ PPU 编码串
    ──码表──▶ Unicode 文本
```

关键常量：句子表 `0x1CC5`（2781 条 × 3B）、block→文本表 `0x3D5C`、
块串按 bank 散布在 PRG 各处；控制码分双字节（05/07/0B/0C/13/14/16/18）与
三字节（0F/10/12/17）两类；PPU 串层另有 0x0E/0x0F 浊音·半浊音前缀。

## 用法

ROM 请**自备**（版权原因不随仓库分发），命名为 `Metal Slader Glory (Japan).nes`
放在本目录（或用 `--rom` 指定）。仅需 Python 3.9+，零依赖。

```bash
python3 msgtool.py export -o script_ja.txt   # 导出全部 2781 句（含 ~控制码~）
python3 msgtool.py export --no-codes         # 纯文本（阅读用）
python3 msgtool.py blocks -o blocks_ja.txt   # 导出 MTE 字典（全部文本块）
python3 msgtool.py used                      # 用 FCEUX .cdl 统计实际用到的句子
python3 msgtool.py map                       # PRG 文本数据分布图（回写规划用）
```

已入库的导出结果：[`script_ja.txt`](script_ja.txt)（全剧本）、[`blocks_ja.txt`](blocks_ja.txt)（字典）。

## 历史

- 2020-12：用 C（Visual Studio）完成逆向与首版导出器——当时兼有练 C 的目的。
  C 版本完整保留在 git 历史中：tag [`c-final`](../../tree/c-final)。
- 2026-07：重写为零依赖的单文件 Python（`msgtool.py`），并与 C 版逐句对账验证：
  2156 句逐字一致；617 句差异源于 C 旧版把 0x04/0x06 当终止符提前截断
  （最终版 C 源码中已注释掉该行为，本版与最终版一致）；8 句差异源于旧码表
  占位符（`（伏）`→`状`、`（了）`→`了` 等）。另修复了 C 版浊音前缀在串尾时的
  越界读。

## 后续（汉化路线图）

- [x] 文本导出（`msgtool.py`）
- [ ] 翻译（2781 句日→中，可并行）
- [~] 回写工具（`reinsert.py`）：**单句内核跑通** —— 重建到空闲区 + text 指针反解 + 块串就地重建；句 62 round-trip 一致、零副作用。待扩展全量（中文字典构建；>256 字需配合 bank 切换）。
- [ ] 字库/引擎：8×8 已实证太糊，需 16×16 + 渲染例程改造（MMC5 扩展属性模式，见上文路线）——最大难点

## 许可

代码 MIT © Snownamida。游戏文本版权归 HAL 研究所，导出文本仅供研究与爱好者翻译。
