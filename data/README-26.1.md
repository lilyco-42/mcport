# 26.1 攻坚的口径、复现与已知差异

> 全部数字为 **2026-11-14 二次修正后**实测：修正 `com/mojang/` 独立库误判（REPORT §5 第 15 条）后
> 重新实跑四条流水线，`data/` 内 CSV 已全部重生成。旧口径（76.9% / 4043 judged / 778 MISSING）
> 与首次"全收 com/mojang"的污染口径均**不再是结论**。

## 文件

| 文件 | 含义 |
|---|---|
| `14mods-to-26.1-baseline.csv` | 14 个 1.21.1 Fabric mod **原样**对 26.1 判定（4068 refs / 3977 judged / 0.1%） |
| `14mods-to-26.1-bridge-1.21.11.csv` | 单一 1.21.11 桥（63.8%） |
| `14mods-to-26.1-bridge-1.21.1.csv` | 单一 1.21.1 桥（65.7%） |
| `14mods-to-26.1-bridge-{merged,target26}.csv` | 两版合并 / 目标感知择一（均 68.1%） |
| `14mods-to-26.1-bridge-only.csv` | bridge-26 + 继承 BFS、未接 Mixin 注解改写（78.7%，LinkCheck 与最终一致） |
| `14mods-to-26.1-bridged.csv` | **最终产物**：bridge-26 + 继承 BFS + Mixin 注解改写（3109/3952 = 78.7%） |
| `bridge-stats.json` | 建桥对齐率、择一/重定位计数、Mixin token、四链路 LinkCheck 汇总、确定性校验 |
| `NOTICE-mappings.md` | 为何不分发 ProGuard 映射与完整桥表 |

CSV 表头：`mod,total,resolve,rename,sigchg,missing,external,judged,auto_fix_pct,as_is_pct`。
**分母是 `judged = total - external`**。26.1 最终 EXTERNAL = 116（91 条 `com/mojang/` 独立库
+ 25 条 JDK 继承），所以 **78.7% = 3109 / 3952**，而 3109 / 4068 = 76.4%。基线
EXTERNAL = 91、judged = 3977。中间策略 63.8 / 65.7 / 68.1% 各有自己的 judged
（3954 / 3952 / 3952），**不与早期那组"62.3 / 64.2 / 66.6%（以 4068 为分母）"混用**。

## 关键口径差异（避免误读）

1. §1/§4 里 `26.1 = 0.0% / 3820` 来自早期 decl 表，只收 `net/minecraft/`；
   26.1 另有 **474 个 `com/mojang/` 游戏类**，补全后 decl 为 10682 类、引用 4068 条。
2. `LinkCheck` 曾有两套独立前缀过滤（`main()` 与 `batch()`），只修一处会把
   `com/mojang/` 引用排除出分母，把 62.3% 虚报成 68.0%。统一 `isGameRef()` 后才是诚实数字。
3. 全收 `com/mojang/` 又引入新污染：DataFixerUpper / Brigadier / authlib / logging 是
   **独立库**，不在任何版本 client jar，API 不由 MC 版本决定，被误判成"MC 类消失"MISSING。
   自检（目标==源）因此掉到 97.5%，触发 §5 第 10 条哨兵。修法：从目标 decl 自证
   `com/mojang/<三级包>` 游戏包集合（26.1 = blaze3d / math / realmsclient），
   其余标 EXTERNAL；四版本各剔除固定的 91 条。26.3 新增 `renderpearl` 会被自动识别。
4. `pipeline-26.sh` 自行生成源 decl 时，`com/mojang/` C 行比研究归档多 23 条
   （S 行 8246 → 8269）。**四条流水线实测无数字微差**：C/M/F 映射行不变，
   78.7% 与归档 CSV 完全一致（`diff` 相同）。

## 复现

```bash
# 前置文件放在本地（脚本不下载、不分发，见 NOTICE-mappings.md）
#   /tmp/mc/map-1.21.1.txt  /tmp/mc/map-1.21.11.txt
#   /tmp/mc/jars/REAL-1.21.1.jar  /tmp/mc/jars/REAL-26.1.jar
#   /tmp/mc/inter-1.21.1.jar  /tmp/mc/i-1.21.11.jar  /tmp/mc/i-26.1.jar
bash pipeline-26.sh 1.21.1 26.1 /path/to/mods
```

脚本在非 UTF-8 / 空 `LANG` 环境下会自动切到可用 UTF-8 locale（REPORT §5 第 16 条）。

退出码：`0` = 全部可自动处理；`2` = after CSV 里仍有 SIGCHG/MISSING 需人工
（本次 26.1 需人工 843 = SIGCHG 156 + MISSING 687，故为 2）。

## 仍未解决（勿把 78.7% 读成"能跑"）

- `@Shadow`/`@Accessor` 声明名与 refmap 未改写；字节级扫描仍能看到 `field_6516`、
  `method_19293` 等声明名，以及 `ReflectionUtil` / `VanillaAoHelper` 里的反射字符串。
  26.x 的 Mixin 注解字符串 interTokens 1987 → 25（见 bridge-stats.json），但常规链路
  1987 → 1987 是**预期的**（intermediary→intermediary，无命名空间切换）。
- 687 条 MISSING 中 397 条是 26.1 已删除的成员、290 条是 owner 类不存在（包搬迁未全覆盖）。
- 语义漂移（同名同签名行为变了）在原理上不可机械检测。
- 真实客户端端到端未做：26.1 class major 69 需 JDK 25，本机只有 17/21，实测抛
  `UnsupportedClassVersionError`。91 条 EXTERNAL 是"本预言机不覆盖"，不是"证明稳定"。
- `Verifier` 对 jei 报的 1 个坏 class 是**基线就存在**的 JVM 类型注解问题，非重映射引入。

细节见 `../REPORT.md §8`。
