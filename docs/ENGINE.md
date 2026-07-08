# 渲染引擎 —— MMC5 / 分屏 / 字库

文本如何变成屏幕像素。地址约定：`PRG` = .nes 文件偏移 − 0x10；`CPU` = 6502 地址。
标注**确认**（从指令直接读出或实机验证）。逐字节 RAM/寄存器清单见 [`MEMMAP.md`](MEMMAP.md)。

## 卡带 / MMC5 配置

- Mapper 5 (MMC5)，PRG 512KB + CHR 512KB，带电池 SRAM，水平镜像。
- 模式寄存器（reset 于 `$E94E`）：`$5100=3`（PRG 8KB×4）、`$5101=1`（**CHR 4KB banking**）、
  `$5104=2`（ExRAM 作工作 RAM）。
- PRG 窗口：`$E000-$FFFF`=`$5117`=**固定 bank 63**；`$A000-$BFFF`=`$5115`=文本解引用时按需切换。
- 向量：`NMI=$E9C3  RESET=$E94E  IRQ=$F978`（均在 bank 63）。
- **可执行代码只在 bank 59–63**（PRG `0x76000–0x7FFFF`，顶部 40KB），其余 472KB 全是数据。

## tile 映射（恒等）

**PPU 编码字节 b → 字库 tile 号 = b。** 渲染链逐环验证：PPU 串字节 → 行缓冲 `$0469` →
字符对缓冲 `$04A9,X`（`$F176: STA $04A9,X`）→ VRAM 队列 `$0300` → `$2007`
（`$F8F6: LDA $0300,X; STA $2007`）。字库 = 一个 CHR 4KB bank = 256 tile。

## 字符几何

每个对话字符 = **上下两个 8×8 tile 竖排**（cell 8×16，字形在下格）：
- 每字生成一对 `[mark, char]` 存入 `$04A8`（偶=上格 tile，奇=下格 tile）。
- `char` = 字形 tile（恒等）；`mark` 默认 `0xFE`（空白），仅浊音/半浊音时置 `゛`/`゜`。
- 汉化定案用**原版 8×8 机制**：上格保持 `0xFE` 空白、下格填中文字模，每字仅 1 tile
  （密度 ~238 字/bank）。详见 [`LOCALIZATION.md`](LOCALIZATION.md)。

## 例程地图

| 例程 | CPU / PRG | 作用 |
|---|---|---|
| 文本渲染核心 | `$F0B7` / `0x7F0B7`（备用入口 `$F0C0`） | 句块串 → 块 → PPU 串 → `$04A8` 对缓冲 |
| level-1 指针解引 | `$EF96` / `0x7EF96` | 从 `$29/$2A` 取块串指针 |
| block→文本指针 | `$EFB9` / `0x7EFB9` | 内部调 `$F01D` |
| ×3+基址+切bank | `$F01D` / `0x7F01D` | text_pointer；用 ExRAM 基址表切 `$5115` |
| **string_pointer 解包** | `$EFC3` / `0x7EFC3` | 与 msgtool 逐位一致：`bank=b1&0x3F`、`ptrHi=(b3&0x1F)+0xA0`、`len=((b1>>6)<<3)+(b3>>5)` |
| 字符发射循环 | `$F135–$F185` | `$0469` → `$04A8` `[mark,char]` 对（**用途=名字/菜单排版**，非对话正文） |
| 矩形缓冲→VRAM队列 | `$E270` / `0x7E270` | `$04A8` → `$0300` 队列（宽度无关的垂直条带 blitter） |
| VRAM 队列刷新 | `$F8AA` / `0x7F8AA` | vblank 内把队列写 `$2007`，预算 `$0449`=76B/帧 |
| 行排版/分页 | `$A4D7`（bank61 `0x7A4D7`） | 走块串、处理控制码、按 30 tile 断行 |
| NMI | `$E9C3` | OAM DMA；调色板；行 IRQ（`$5203/$5204`）；载入 CHR bank |
| IRQ（光栅分屏） | `$F978` | 经 `($0633)` 分派；`$FF34` 从 `$045E,Y→$512B` 逐区切 CHR |

### 渲染核心伪代码

```
render_line($F0B7):                     # $29/$2A=行块串指针, A=起始列*2
  ($18,$19) = resolve_ptr($29/$2A)      # $EF96
  loop over block-string ($18),Y:       # $F0D7
     b = read()
     if b==0x00: finalize()
     elif b>=0x80: block=(b<<8)|next    # 双字节块(MTE)
     else:         block=b
     expand_block(block) -> $0469[]     # $EFB9: block→text→string→拷PPU串
     for each PPU byte c in $0469:
        if c in {0x0E,0x0F}: $27=c; continue   # 锁存浊音到上格
        $04A8[k] = $27; $27=0xFE; $04A9[k+1]=c; k+=2
  # $E270 把 $04A8 作 2 行 blit 进 $0300 队列 → NMI 刷 $2007
```

## CHR bank

- CHR 4KB 模式：512KB = **128 个 4KB bank，每 bank 256 tile**（扩到 1MB 后 256 bank）。
- 文字在背景层，字库 bank = 写 `$512B` 的值。复位默认字库 = bank 0。
- **每个场景各自加载字库 bank**（不是全程共用 bank 0）：由背景 CG 命令 `70 <bank>` →
  处理程序 `$8307` 写 `$0450`。原版靠两级字典 256 tile 够复用，故从不切对话 bank；
  中文 1472 唯一字才产生多 bank 需求。
- **成套字库只有 bank0（对话字库）、bank10（标题字体）**，其余 126 个全是 CG 美术
  （全 128 bank 画成图集验证过，见 [`../reversing/tools/chr_atlas.py`](../reversing/tools/chr_atlas.py)）。

## 分屏渲染机制 ★核心

屏幕竖分多区（region），每区一套 CHR bank。区 bank 存 shadow 数组 **`$045E-$0461`**
（=region 0/1/2/3），源自 `$0450-$0453`：

- **NMI（每帧）** 从 `$0450-$0453` 拷入 `$045E-$0461`：
  `$EB79 LDA$0450;STA$045E` / `$EB7F LDA$0451;STA$045F` / `$EB85 LDA$0452;STA$0460` / `$EB8B …STA$0461`。
- **NMI `$EB58` `LDA $0450,X; STA $512B/$5123`** 设顶部 strip bank（X=0→`$0450`=CG，X=2→`$0452`）。
- **分屏 IRQ**（`$F978`→`JMP($0633)` 动态派发）+ `$FCC9/$FF34 `LDA $045E,Y; STA $512B`` 按区应用。
- 实测：普通场景 2 区（region0=CG / region1=对话框）；**场景 67 三段**=顶部绿字 strip（`$0452`）
  + 中间 CG portrait（region0）+ 底部对话框（region1）。region2/3 全程未渲染。

## 两套 emit（重要）

对话正文与名字/菜单走**两套独立的字符发射代码**（逆向踩过的关键坑）：

- **对话正文** = bank 62 打字机子系统（`$D2ED`–`$D346`、第二路径 `$D9EA`），与逐字显现状态机
  深度耦合（`$2D` 列游标、`$37` 显现字数、`$0557,X` 显现影子）。按 **1 列/字** 设计。
- **名字 / 菜单排版** = `$F135–$F185`（bank 61 `$A6CF` 调用）。

→ 汉化改的是数据侧 + 一条 NMI bank 钩子，**不碰这两套 emit**（早期误改 `$F135` 无效，
详见 [`HISTORY.md`](HISTORY.md) 里程碑 2/尝试）。真 16×16 才需重写 bank62 打字机（列宽、显现数组、
四连号发射），是有风险的子工程，列为后续 polish。
