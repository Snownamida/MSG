# 第二章装箱方案(build_ch2 / 扩展 build_012)

第二章遍历已达成(见 `reversing/data/ch2_scene_map.tsv`,seqrun stage_2 产出)。本文固化装箱设计,供实现。

## 数据
- **句号→场景**:`reversing/data/ch2_scene_map.tsv`(346 句,句号 243-704,27 场景;LUA 句号,tr=句号+1)。
- 范围内 ~98 句缺口(未走到的分支对话)+ dumpall 全集(`dumpall.py`,1578 句)覆盖所有分支——build 时用 dumpall 演出段把场景传播到同段的分支句。

## 字库容量
- CHR bank = 4KB = 256 tile 槽;扣固定码(名字/命令/标点/假名)后 **每 bank ~200 独有汉字**。
- 第二章去重汉字 822;7 个大场景超 213:**68=359, 38=328, 5F=278, 4B=265, 5C=240, 28=220, 57=215**。

## 分配(实测可行:346句→40bank,空闲池101,富余)
- 默认:字库 bank = `场景|0x80`(复用 build_ch1_mb 的 NMI 单点改,已在 ROM)。
- 溢出:大场景按剧情顺序(句号序)贪心切多 bank,超 ~200 独有字开新 B bank。多 bank 场景:
  `68(4), 38(3), 4B(3), 28/2F/57/5C/5F/62(各2)` = 13 个溢出 B bank。
- B bank 逐句切换:复用 build_ch1_mb 硬骨头③ 的 ExRAM 钩子($5FA5,shadow $5FFF),把逐句→bank 写进 B-list。
  ★同 bank 相邻句共显安全(按句号顺序分组,不跨话题边界拆)。

## 与第一章的场景重叠(统一 012 构建)
- **00**:两章都跳过(保原版假名密语/存档屏,勿改)。
- **5C**:第一章仅瞬态 CG(检查是否装了 5C 对话);第二章机场主用(240字)。bank DC 存第二章 5C 字。
- **67**:第一章绿字(~104字,走 GREEN_BANK $E0)+第二章 67(2字);并集小,合并即可。
- 注意 `场景60|0x80=$E0` 撞 GREEN_BANK → 第二章场景60 改用空闲 bank(或 GREEN 换号)。

## 实现步骤
1. build 加载 ch2_scene_map + dumpall 传播 → 完整第二章 gui_scene。
2. 扩范围过滤:纳入第二章句号(217-769,跳过场景00)。
3. 泛化分配循环:每场景按句号序贪心装 bank(默认 + 溢出B),生成逐句 B-list。
4. 处理重叠场景(5C/67 合并两章字);解决 60↔GREEN bank 冲突。
5. 写 CHR 字模 + 句子 block 流 + B-list 进 ExRAM 钩子。
6. QA:seqrun 开 `QA_SHOTS=1` 跑第二章截图巡检,验证每句显示正确(font==场景|0x80 或 B bank)。

## QA 遍历
`seqrun.py` step15+ 已能完整走通第二章(过5C机场/V-MH输入)。QA 时 `QA_SHOTS=1` 截每对话页,查 PAGE 行的 font/expect 是否 OK。
