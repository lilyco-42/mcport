# Minecraft 跨版本 mod 失效：根因、量化边界与 McPort 方案

> **结论先行：*"任意版本都有效"在技术上不可达*。** 这不是工程努力不够 —— 我们量化出了天花板。
> 可达的目标是 **"约 80% 自动搬运 + 约 20% 精确预言 + 100% fail-loud"**（常规版本），26.x 去混淆断代后更低。
> 全部数据由本机实测复现，样本为 Modrinth 上 14 个真实 1.21.1 Fabric mod、4068 条 MC / 游戏库引用。
> **口径（2026-11-14 二次修正）**：早期报告用的 3820 条只收 `net/minecraft/`；补全 `com/mojang/` 后为 4068 条，
> 其中 91 条属 `com/mojang/` 独立库（DataFixerUpper / Brigadier / authlib / logging，client jar 不含）记为 EXTERNAL，
> 实际判定分母 judged=3951（26.1 为 3952 / 3977）。所有百分比的分母都是 judged，见 §5 第 15 条与 §8.4。

---

## 1. 为什么跨版本会失效：三层机制，逐层变坏

### 第 1 层（可自动修复）：符号引用在链接期炸掉 —— JVMS §5.4.3

mod 的 .class 里硬编码了 `Methodref(owner=net/minecraft/..., name=..., desc=...)`。
JVMS SE21 §5.4.3.3：解析失败抛 `NoSuchMethodError`；§5.4.3.2 字段 → `NoSuchFieldError`；§5.4.4 访问控制 → `IllegalAccessError`。
**关键点：解析发生在运行期而非编译期**，编译器完全不提醒你。

实测（`demo/run.sh` 场景 B，最小复现，无需下载 MC）：

```
== A. 源版本 (1.20.1) ==
mod started on MC 1.20.1 -> block=42

== B. 同一份二进制, 新版本 (1.21.1) ==
Exception in thread "main" java.lang.NoSuchMethodError: 'int net.mc.World.getBlock(int, int, int)'
        at demo.MyMod.main(MyMod.java:10)
```

JLS SE21 §13 的"二进制兼容"承诺只覆盖**库自身的演化**（§13.2 逐条列举哪些改动保证兼容），
完全不承诺"一个第三方程序在另一个版本上还能跑"。这是语言规范层面的边界，不是实现缺陷。

### 第 2 层（可半自动）：Mojang 的重构 + 混淆名重排

实测 1.20.1 → 1.21.11 的 API 流失（官方 ProGuard 映射口径、签名感知）：

| 指标 | 1.20.1 | 1.21.11 | 累计丢失 |
|---|---|---|---|
| net.minecraft 类 | 7436 | 10291 | 1428 (20.1%) |
| 方法 | 60966 | 85917 | **21797 (37.4%)** |
| 字段 | 35113 | 48636 | 8104 (24.4%) |

逐版本方法流失：1.20.1→1.21.1 丢 8903（14.8%）；1.21.1→1.21.4 丢 7103（10.1%）；1.21.4→1.21.11 丢 16522（22.0%）。

流失原因三分（21797 条）：**纯改名/改描述符 4808 (8.0%)** 可机器重映射；
**owner 类还在但成员没了 7695 (12.8%)** 需语义 shim；**owner 类整体删除 9816 (16.3%)** 需重实现。

→ 即便把自动重映射做到极致，也只能救回约 8~9% 的断链。大头是需要人工语义补齐的破坏性变更。

### 第 3 层（不可修复）：语义漂移 —— 静默错误

同名、同签名，行为变了。字节码层解析 100% 成功，不报任何错，结果却错。实测（场景 D）：

```
v1 getMaxHeight() -> 256       运行输出 D height=256
v2 getMaxHeight() -> 384       运行输出 D height=384   <- 无任何异常
加 agent (mappings=0)          运行输出 D height=384   <- 重映射救不了
```

**这一类失效无法被任何加载器、任何重映射器彻底判定。** 字节码骨架哈希能抓到实现变更的
**一部分**（§13 在四版真实 client jar 上量化出 4.6%–14.2% 的"可检测下界"），
但 85.8%–95.4% 的同名同签名方法三列指纹全同，那恰恰是静态工具**判不干净**的区间：
跳转目标重排、被调用者内部实现、注册表/配置/运行时状态、反射、资源与 native 都可能
改变行为而指纹不变。要彻底判定仍只剩测试或数据校验一条路。
这依旧是"任意版本绝对不失效"不可实现的**核心论据**，也是本方案 fail-loud 而非"尽量猜"的原因。

### 附加断代：官方去混淆（26.1）—— 实测"归零"

- `minecraft.wiki/w/Java_Edition_26.1`：26.1 是第一个**完全去混淆且无配套混淆变体**的正式版，
  采用 year.drop.hotfix 版本号，首个要求 Java 25。
- 官方 obfuscation maps 从 19w36a 到 1.21.11 每版都有；26.1 起不再需要（官方不再发布该变体）。
- 实测 Fabric intermediary maven：1.20.1 (508743B)、1.21.1 (582921B)、1.21.11 (797685B / 105146 行) 正常；
  但 **26.1 与 26.3 的 intermediary jar 只有 572 字节，mappings.tiny 全文只有表头一行**；
  `/v2/versions/yarn/26.1` 与 `/26.3` 均返回 `[]`。
- client jar 实测：1.21.11 有 10291 class 但只有 33 个 net/minecraft 路径（几乎全混淆）；
  26.1 有 10682 class / 10717 个 net/minecraft 路径（全去混淆）；class 文件 major 从 65 跳到 69。

**实测后果（最关键的一条）**：拿 14 个 1.21.1 mod 去判定 26.1，结果
**3820 条引用 RESOLVE = 0，MISSING = 3820（0.0%）**。
因为 mod 引用的是 `net/minecraft/class_XXXX` 这类 intermediary 名，而 26.1 的声明表里全是 Mojang 名。

→ **26.1 起"跨版本稳定命名"这层基础设施事实上归零。任何只建立在 intermediary 之上的兼容层在 26.1 断代。**

> 口径提示（2026-11-14 二次修正）：上面的 3820 条来自早期 decl 表（只收 `net/minecraft/`）。
> 把 `com/mojang/`(26.1 有 474 个类)纳入后统一口径为 **4068 条**，原样搬运 RESOLVE=4 / 3977 judged = 0.1%。
> 91 条 `com/mojang/` 独立库类（client jar 不含）另记 EXTERNAL；这条"归零"是**迁移前**结论，
> §8 记录了后续用官方 ProGuard 桥把静态可解析率恢复到 **78.7%（3109/3952）** 的工作。

### 环境约束：JDK 随版本跳变

官方 launchermeta javaVersion 实测：1.16.5→JDK 8；1.17.1→JDK 16；1.18.2/1.20.1/1.20.4→JDK 17；
1.21.1/1.21.4/1.21.11→JDK 21；26.1/26.2→JDK 25。NeoForge 现行文档亦要求 JDK 25。
→ **"一个进程内跑任意版本"不存在：JDK 主版本本身就在跳。**

---

## 2. 现成方案的 fit 矩阵（真数据，GitHub API 实测）

| 方案 | 星 | 许可 | 最近提交 | 它到底解决什么 | 对我们的价值 |
|---|---|---|---|---|---|
| FabricMC/fabric-loader | 905 | Apache-2.0 | 2026-10-19 | 自称 "mostly-version-independent"（注意 mostly） | 参考；仍逐版本适配 |
| Sinytra/Connector | 762 | MIT | 2026-10-30 | 让 Fabric mod 跑在 NeoForge | 跨**加载器**，不跨版本 |
| architectury-api | 455 | LGPL-3.0 | 2026-10-09 | 90+ 事件钩子、@ExpectPlatform | 减少多平台重复代码，仍逐版本重编译 |
| ViaVersion / ViaFabricPlus | 1654 / 686 | GPL-3.0 | 2026-11-07 | 协议层：新客户端连旧服 | 只解决网络协议，不解决 mod 二进制 |
| Weave-MC/Weave-Loader | 177 | GPL-3.0 | 2026-10-04 | 按版本族分段支持 1.7/1.8/1.12/1.16–1.21 | 证明"分段支持"是业界共识 |
| Ray-T-r/Forbric | 264 | Apache-2.0 | 2026-11-04 | 同进程跑 Fabric+Forge+NeoForge mod | README 自承 "Connector is mature and Forbric is not"，仅单版本 |
| unimined/Unimined | 129 | LGPL-2.1 | 2026-11-13 | 多版本构建工具 | 编译期，不是运行期兼容 |
| CleanroomMC/Cleanroom | 629 | NOASSERTION | 2026-11-13 | 1.12.2 Forge 续作，Java 25+ | 单版本长线维护的证明 |
| boomshroom/ObfLoader | 2 | 无 | 2014-03-20 | 曾想干我们想干的事 | **已死**，无许可不可用 |

**最有力反证（官方口径）**：Modrinth API 实测 sodium 共 **272 个版本文件、覆盖 41 个 game_versions**；
同一 26.3 下 Fabric 与 NeoForge 是**两个不同的 jar**
（sodium-fabric-0.9.3-beta.5+mc26.3.jar sha1 33ea0f572a / 1914521B vs sodium-neoforge-… sha1 bf3860fda5 / 1211839B）。
fabric-api 覆盖 396 个 game_versions —— **连 API 层自己都要逐版本适配**。

→ 生态共识：**没有"任意版本"的方案，只有"分段 + 逐版本适配"。** 所以目标只能是"把适配成本压到最低、残余风险精确预言"。

---

## 3. 方案：McPort —— 可判定 / 可自动修 / fail-loud

### 3.1 LinkCheck —— 跨版本可解析性预言机

模拟 JVMS §5.4.3 的符号引用解析（本类 → 超类链 → 接口，BFS），把 mod 每条 MC 引用分成五类：

| 判定 | 含义 | 处置 |
|---|---|---|
| RESOLVE | 同名同描述符存在（含继承） | 零改动可用 |
| RENAME | 同 (owner,desc) 在目标版本有唯一新名 | 自动重映射 |
| SIGCHG | 同 (owner,name) 存在但描述符变了 | 需桥接 shim |
| MISSING | owner 类或成员彻底消失 | 必须重实现 |
| EXTERNAL | 继承自 JDK（严格按成员存根表匹配）、或 `com/mojang/` 独立库类（目标 decl 自证不含） | 本预言机不覆盖，不计入分母 |

**自检哨兵**：目标==源版本时应判 ~100% RESOLVE。这条对照在 1 秒内暴露了四个真 bug（见 §5），
最近一次就是 §5 第 15 条：把 `com/mojang/` 独立库类误判成 MISSING，自检一度掉到 97.5%。
14 mod 自检实测 **99.7%（3939/3951）**，剩 12 条是真实断链：反射式调用不存在的成员；
另有 117 条 EXTERNAL（91 独立库 + 26 JDK 继承）不计入分母。

### 3.2 mkmap.py —— 以 intermediary 为身份的重映射表生成

**不用 official（混淆）名当身份桥**：实测 `class_1011` 在 1.21.1 对应 official `faj`、
在 1.21.11 对应 `fyh` —— Mojang 会把同一短名复用给无关类。
正确做法：class_XXXX / method_XXXXX 才是跨版本稳定身份，且只在 (owner,desc) 于源/目标两侧**均唯一**时产出改名。

产物（1.21.1 为源）：→ 1.21.11 共 M=20782 / F=11557 行；→ 1.20.1（反向）共 M=19043 / F=9872 行；恒等行仅 1.3%。

### 3.3 RemapTool —— 离线重映射器（可进构建流水线）

ASM `ClassRemapper` 重写 jar 内每个 class，输出新 jar，**不改输入**。
另有 `Verifier`（`CheckClassAdapter`）做结构完整性闸门：重映射后每个 class 必须仍能通过 ASM 校验。
实测 14 个 mod：重映射后 **1 个 jar 有 1 个 bad class**，对照原始 jar 同样报这一条
（jei 的 `IllegalArgumentException: Invalid type reference sort 0x13`，ASM 类型注解校验的已知限制），
**非重映射引入**；四条链路的 Verifier 输出一致。

### 3.4 McPortRuntime —— 启动期 -javaagent（"寄生 Java 本身"）

**必须走启动期 premain，不能靠 attach**：JEP 451（JDK 21 已交付）规定动态加载 agent 会发警告、
为将来默认禁止铺路，其 Non-Goal 明确写着"**不阻止通过 -javaagent / -agentlib 在启动时加载**"，且不对启动期加载发警告。
这是寄生方案唯一的长期合法路径。

- 只改写 mod 侧类（默认跳过 net/minecraft/、com/mojang/、java/、javax/、jdk/、sun/、com/sun/；
  26.1 起 474 个游戏类落在 `com/mojang/`，漏掉会把游戏自身也重写了）
- **磁盘文件零改动**（演示中 mod jar 的 sha1 前后一致）
- **fail-loud**：映射表里没有的引用原样放过 → JVM 抛 NoSuchMethodError。绝不猜名，因为猜错会产生 §1 第 3 层那种静默错误
- 映射表加载失败直接让进程起不来（否则 mod 会在运行期"莫名其妙"崩，难查一万倍）
- 依赖 ASM 9.9（ASM 9.9 才能读 class major 69 / Java 25 的 26.x）；MANIFEST 必须写 `Boot-Class-Path:` 指向 ASM jar

---

## 4. 量化结论：天花板在哪（14 个真实 mod，4068 条引用 / 3951 条判定）

样本：sodium / lithium / ferrite-core / iris / jei / cloth-config / modmenu / indium / c2me / krypton /
entityculling / fabric-api / reeses-sodium-options / noisium，全部从 Modrinth 官方 API 取 1.21.1 + fabric 的 primary 文件。

### 4.1 迁移前（原始 jar，只给映射表让预言机判定）

> **统一口径**：4068 条引用 = 全部 `net/minecraft/` + `com/mojang/` 符号引用。
> 其中 117 条 EXTERNAL（91 条 client jar 不含的 `com/mojang/` 独立库 + 26 条 JDK 继承成员），
> `judged = 4068 − 117 = 3951`，下表所有百分比的分母都是 judged。
> 26.1 的 EXTERNAL 为 91（原样）/ 116（重映射后），judged 相应为 3977 / 3952。

| 目标 | RESOLVE | RENAME | SIGCHG | MISSING | EXTERNAL | 判分母 | 自动修复上限 | 零改动存活 |
|---|---|---|---|---|---|---|---|---|
| **1.21.1（自检）** | 3939 | 0 | 1 | 11 | 117 | 3951 | **99.7%** ✅ | 99.7% |
| 1.21.11（向前兼容：往新搬） | 3119 | 26 | 240 | 566 | 117 | 3951 | **79.6%** | 78.9% |
| 1.20.1（向后兼容：往旧搬） | 3577 | 3 | 80 | 291 | 117 | 3951 | **90.6%** | 90.5% |
| 26.1（去混淆断代） | **4** | 0 | 2 | **3971** | 91 | 3977 | **0.1%** ❌ | 0.1% |

> §1 与旧归档里那个 3820 / 0.0% 是只收 `net/minecraft/` 的早期口径，作为历史记录保留；
> 补全 `com/mojang/` 474 个游戏类后同一批 mod 是 4068 条。经 §8 的 ProGuard 桥重映射后
> 26.1 达 3109 RESOLVE / 3952 judged = **78.7% 静态可解析**。不同口径**不可横向相减**。

### 4.2 重映射之后（真的把字节码改了，再判定一次）

| 指标 | 重映射前 | 重映射后 |
|---|---|---|
| RESOLVE | 3119 | **3145 (+26)** |
| RENAME | 26 | **0**（全部已落盘为实际改名） |
| SIGCHG | 240 | 240（不变，需 shim） |
| MISSING | 566 | 566（不变，需重写） |
| EXTERNAL | 117 | 117（不计入分母） |
| 自动修复上限 | 79.6% | **79.6%**（上限即天花板，已兑现；零改动存活 78.9% → 79.6%） |

→ 这说明 RENAME 那部分**确实能被机械救回**，剩下的 806 条 SIGCHG+MISSING 是硬骨头，映射表无能为力。

### 4.3 单个 mod 的分布极不均匀（重要）

同样是 1.21.1 → 1.21.11，最好和最差差 37 个百分点（全口径 4068 refs，分母为各 mod 的 judged）：

| mod | 引用数 | 自动修复上限 |
|---|---|---|
| krypton / c2me | 4 / 9 | 100% |
| entityculling | 128 | 94.5% |
| lithium | 576 | 93.7% |
| noisium | 26 | 88.5% |
| jei | 1050 | 84.1% |
| reeses-sodium-options | 137 | 82.4% |
| indium | 109 | 82.1% |
| ferrite-core | 28 | 80.8% |
| modmenu | 190 | 80.2% |
| cloth-config | 288 | 78.2% |
| **sodium** | 696 | **76.9%** |
| **iris** | 827 | **63.3%** ← 渲染管线的 mod 最难 |
| fabric-api | 0 | —（无游戏符号引用） |

**规律：越贴近渲染/画布层（iris、sodium、indium、cloth-config）越难，越纯逻辑/纯数据（c2me、krypton、noisium）越好搬。**
因为渲染 API 是 Mojang 重构最频繁的区域（Blaze3D 重写、BufferBuilder/VertexConsumer 签名反复变）。

### 4.4 两个方向不对称（"向后兼容"比"向前兼容"容易）

样本全是 1.21.1 的 mod。搬去更新的 1.21.11（向前兼容）只有 **79.6%**；
搬去更旧的 1.20.1（向后兼容）反而有 **90.6%**。

**原因**：新版本才有结构性重构（1.21.4→1.21.11 单这一跳就丢了 22% 的方法，是全程最大的一跳）；
旧版本 API 更小更稳定。所以"往上搬"永远比"往下搬"贵。
这直接推翻了"向后向前兼容可以对称实现"的假设 —— 二者难度相差 11 个百分点，且方向相反于直觉。

### 4.5 定量结论

- 一个真实 mod 跨 4 个版本，**只靠自动重映射最多救 ~80%**（1.21.1 → 1.21.11 实测 79.6%）
- 剩下 **~20%**（240 条签名变更 + 566 条成员消失 = 806 / 3951）必须写适配层
- 再叠加 §1 第 3 层的语义漂移（连这 80% 都不保证语义正确）
- 而 **26.1 起这个 80% 在原生 intermediary 路径上直接归零**（intermediary 没了）；
  §8 用"官方 ProGuard 映射 + Fabric intermediary"重建身份桥后，26.1 恢复到 **78.7% 静态符号可解析**，
  但这不等于语义正确、也不等于能在真实客户端跑通。

→ **"任意版本绝对不失效"不可达；"~80% 自动 + ~20% 精确预言 + 100% fail-loud"可达（26.1 见 §8 的更低天花板与额外硬缺口）。**

---

## 5. 踩过的坑（都是真 bug，写出来让后来人省时间）

1. **tiny v1/v2 列序不同**。v1：`METHOD <owner> <desc> <official> <intermediary>`；v2：缩进层级 `m <desc> <official> <intermediary>`。早期把 v2 的 p[3]/p[2] 写反，映射表只剩 M=0 F=44（覆盖 0.1%），并产出 name/desc 互换的垃圾行。
2. **不能拿 tiny 当声明表**。tiny 只映射被混淆的名字，编译器合成成员（<init>、values()、ordinal()、桥接方法）不在里面 —— 会把 8.5% 的合法引用误判成 member gone，连"目标==源版本"的控制组都跑不到 100%。正确做法：成员声明以**目标版本真实字节码**为准，映射只用于改名。
3. **field_info 也有 attributes**。给 field 直接 pos += 2 会错位，症状是 rdesc() 里 d.index(';') 抛 ValueError: substring not found。
4. **包名过滤必须在映射之后**。混淆 jar 里类名是 a/b，先按 net/minecraft/ 过滤只剩十几个辅助类。
5. **EXTERNAL 判定不能靠类名前缀**。写着"类链里有 java/ 就是 JDK 继承"，结果任何解不出的成员都走到 java/lang/Object 被判 EXTERNAL，等于把 MISSING 全部洗白（14.2% 假阳性）。必须按成员 (name+desc) 严格查存根表。
6. **不要伪造父类 <init>()V 引用**。真实 super() 在字节码里就是一条 invokespecial Methodref，会自然被收集；伪造会让没有无参构造的类被误判 SIGCHG（9 条假阳性）。
7. **ASM 9.9 才能读 class major 69**（Java 25 的 26.x）。
8. **agent 的 MANIFEST 必须写 Boot-Class-Path** 指向 ASM jar，否则 transformer 里 NoClassDefFoundError: org/objectweb/asm/commons/Remapper。
9. **不要以 official 名为跨版本身份桥**（见 §3.2）。
10. **控制组是最高性价比的测试**。"目标==源版本"这一组 1 秒出结果，本次三个 bug 全靠它抓出来。
11. **两套过滤逻辑会静默漂移口径**。`LinkCheck.main()` 单 mod 路径与 `batch()/analyze()` 批量路径各写了一遍
    `startsWith("net/minecraft/")`；只改了第一处，重映射后 `com/mojang/` 引用被排除在分母外，
    当时把 62.3% 虚报成 68.0%。统一 `isGameRef()` 后得到全口径 4068 refs；
    但"全收 com/mojang"又引出第 15 条的库类污染，两次都靠控制组哨兵抓出来。
    **同一语义判断只能有一处实现**（见 §8 的 Mapping 单一来源）。
12. **集合迭代让构建产物不可复现**。`bridge.py`/`bridge26.py` 的 C/M/F/S 行来自 `set` 求交后的 dict，
    受 `PYTHONHASHSEED` 影响：重生成语义相同但 `sha256` 每次不同，CI 无法校验产物。
    全部改 `sorted(...)` 后，seed=1/2/777 三次输出字节一致。
13. **ClassRemapper 改不到注解里的字符串**。14 个 mod 的 Mixin 注解里有 1987 个 intermediary token
    （`@Mixin` 是 CLASS retention，必须同时扫 visible/invisible 注解）。正则踩了两轮：
    owner 字符类含 `;` 会贪婪吞掉分隔符；描述符写成 `(.*)` 不含返回值会漏掉 `()V`。
    修正后残留 25 条（无唯一候选，保留原名 fail-loud）。
14. **内嵌 Python 多行 `.replace()` 会被换行截断**（`SyntaxError: unterminated string literal`），
    导致"以为打了补丁其实没落盘"。改源码用逐行替换或三引号，并且**打完必须跑验证**再宣布修复。
15. **`com/mojang/` 下混着两类东西，前缀过滤不能一刀切**。26.1 client jar 里的
    `com/mojang/{blaze3d,realmsclient,math}` 是随游戏发布的类，但 `com/mojang/{serialization,datafixers,brigadier,authlib,logging}`
    是 DataFixerUpper / Brigadier / authlib 等**独立库**，不在任何版本 client jar 里，其 API 不由 MC 版本决定。
    第 11 条把整个 `com/mojang/` 纳入 `isGameRef()` 后，这 91 条引用在每个版本都被判成
    "MC 类消失"的 MISSING —— 自检从 99.7% 掉到 97.5%、往新只有 77.8%，
    26.1 的 76.9% 里也混着 91 条假 MISSING（真实应为 687 而非 778）。
    修法不硬编码库名：`loadDecl()` 收集目标 decl 里出现过的 `com/mojang/<三级包>` 作游戏包集合，
    `classify()` 把其余 com/mojang 引用标 EXTERNAL（**不是"证明稳定"，是"client jar 不含、本预言机不覆盖"**）。
    这样 26.3 新增的 `com/mojang/renderpearl` 也能自动识别。修复后 91 条固定豁免，
    四个目标版本 judged 统一为 3951（26.1 为 3952 / 3977），自检回到 99.7%。
    **教训：EXTERNAL 必须是"我明确不覆盖"的清单，不能是"我猜它没问题"的豁免。**
 16. **空 `LANG` 会让中文工作目录下的 `javac` 报 file not found**。`run_code` / 非 login CI 的
     `LANG`、`LC_ALL` 常为空，此时 JDK 的 `sun.jnu.encoding=ANSI_X3.4-1968`，
     `java -XshowSettings:properties` 实测 `file.encoding` 同为 ANSI_X3.4-1968；
     `javac java/mcport/*.java` 逐字报 `error: file not found: java/mcport/AnnotationDump.java`，
     但 `ls` 能看见文件、`bash -lc` 下（`LANG=zh_CN.UTF-8`）却完全正常 —— 之前四条流水线能跑
     只是因为后台作业走 login shell。实测 `LANG=C.UTF-8` 或 `C.utf8` 即恢复。
     三条脚本（`demo/run.sh` / `pipeline.sh` / `pipeline-26.sh`）现统一在 `cd` 后自愈：
     当前 locale 不含 UTF-8 时，从 `locale -a` 里挑 `C.UTF-8 / C.utf8 / en_US.UTF-8 / zh_CN.UTF-8`
     设 `LC_ALL`+`LANG` 并打印提示；已是 UTF-8 的环境不覆盖。无 LANG 环境实测 demo 四场景全绿。
     **教训：README 承诺"可直接进 CI"，CI 就不能依赖调用者的 locale。**
 17. **premain 抛异常在 HotSpot 上不是普通 Java 崩溃，而是 JVM native abort（rc=134）**。
     §12 的 fail-loud 用例（缺 `bridge.tsv` / 空规则表）在 JDK 17 与 JRE 25 都复现：
     `java.lang.instrument` 打印 `ASSERTION FAILED ... invokeJavaAgentMainMethod failed`，
     随后 `FATAL ERROR in native method: processing of -javaagent failed` 并可能生成 core 文件。
     这是「绝不带病启动」的预期表现，而不是 agent 失去控制；`demo/real26/run.sh` 用
     `ulimit -c 0` 避免污染工作区。另一坑：`DumpAgent` 的匿名内部类 `DumpAgent$1`
     初版没打进 fat jar，observer 在 premain 直接 `NoClassDefFoundError: demo26/DumpAgent$1`；
     agent 是 bootstrap 可见的类路径，**内部类/依赖 jar 必须一起打进 fat jar**。

---

## 6. 交付物与复现

```
mcport-跨版本兼容/
├── REPORT.md                        本报告（§8 26.x / §13 语义漂移 / §14 装载编排机 / §15 严格 C 行迁移 / §16 人工桥工作台 / §17 字符串姓名表面）
├── README.md                        上手
├── pipeline.sh                      常规版本流水线：声明表→映射表→扫描→重映射→校验→复测→工单
├── pipeline-26.sh                   26.x 专用流水线：ProGuard 建桥→继承/Mixin 改写→复测
├── java/mcport/
│   ├── LinkCheck.java               跨版本可解析性预言机（单 jar + 批量目录模式）
│   ├── Mapping.java                 映射表 + 继承 BFS 的**唯一实现**（工具与 agent 共用）
│   ├── RemapTool.java               离线重映射器（薄壳）
│   ├── MixinRewriter.java           Mixin 注解字符串改写（intermediary → 真实名）
│   ├── MixinCheck.java              注解残留维度的第二静态预言机
│   ├── AnnotationDump.java         真实注解格式采样器
│   ├── Verifier.java                重映射后字节码结构完整性闸门
│   ├── HostBridge.java              宿主侧启动期桥（SIGCHG 旧签名转发，§9 / §11）
│   ├── BodyHash.java                真实 jar 方法体指纹（§13）
│   ├── CallKind.java                从 mod 字节码恢复 Methodref 的 invoke opcode（§16）
│   └── McPortRuntime.java           启动期 -javaagent 兼容层（"寄生 Java 本身"）
├── tools/
│   ├── mkdecl.py                    生成目标版本 API 声明表（以真实字节码为准）
│   ├── mkmap.py                     生成 intermediary 身份的重映射表
│   ├── bridge.py                    官方 ProGuard × Fabric intermediary → inter→真实名桥
│   ├── bridge26.py                  版本择一 + 目标感知重定位 + S 行父类链
│   ├── drift_align.py               §13 官方 ProGuard 真实名身份对齐 + 聚合
│   ├── loader.py                    §14 版本无关装载编排机（分类 / 装配 / 预言机 / fail-loud）
│   ├── test_loader.py               §14 零外部数据 49 断言自包含回归
│   ├── relocate.py                  §15 严格 C 行类迁移补充生成器
│   ├── test_relocate.py             §15 零外部数据 27 断言自包含回归
│   ├── bridgegen.py                 §16 SIGCHG/MISSING 人工桥工作台（零自动修复）
│   ├── test_bridgegen.py            §16 零外部数据 61 断言自包含回归
│   ├── stringsurface.py           §17 LDC / refmap 字符串表面精确审计（默认只报告）
│   ├── test_stringsurface.py       §17 零外部数据 78 断言自包含回归
│   └── report.py                    JSON 报告 → 可执行迁移工单 markdown
├── demo/                            端到端最小复现（无需下载 MC）
│   ├── run.sh                       A 正常 / B 炸 / C agent 救活 / D fail-loud
│   └── src/{v1,v2,mod}              两版本假 API + 一份只针对 v1 编译的 mod
└── data/                            实测数据归档（只含测量 CSV / 统计 / 复现说明；不分发映射表）
    ├── 14mods-self-1.21.1.csv       自检对照（99.7% / judged 3951）
    ├── 14mods-to-1.21.11.csv        旧→新（79.6%）
    ├── 14mods-to-1.20.1.csv         新→旧（90.6%）
    ├── 14mods-remapped-1.21.11.csv  重映射后复测（79.6%，RENAME 已兑现）
    ├── 14mods-to-26.1-baseline.csv  26.1 原样搬运（4068 refs / 0.1%）
    ├── 14mods-to-26.1-bridged.csv   §8 桥接 + 继承/Mixin 改写后（78.7% 静态可解析）
    ├── 14mods-to-26.1-bridge-*.csv  各中间策略，全部按二次修正口径重算
    ├── bridge-stats.json            建桥/择一/重定位计数 + 四链路口径汇总
    ├── MIGRATION-iris-1.21.1-to-1.21.11.md   逐符号人工工单（示例，二次修正后重生成）
    ├── MIGRATION-sodium-1.21.1-to-1.21.11.md 同上
    ├── README-26.1.md               26.x 口径、复现命令、硬缺口
    ├── drift-summary.csv            §13 四版真实 jar 语义漂移聚合
    ├── drift-README.md              §13 口径与踩坑
    ├── drift-spec.example.json      §13 复现模板（路径占位符）
    ├── loader-scenarios.csv         §14 13 组实跑聚合（P1–P6 / S1–S7）
    ├── loader-README.md             §14 聚合口径与不分发声明
    ├── relocate-summary.csv         §15 两版本严格迁移聚合
    ├── relocate-README.md           §15 口径 / 合规 / 踩坑
    ├── relocate-spec.example.json   §15 复现模板（路径占位符）
    ├── bridgegen-summary.csv        §16 两版本 602 条工单分桶聚合
    ├── bridgegen-README.md          §16 口径 / 合规 / 踩坑
    ├── bridgegen-spec.example.json  §16 复现模板（路径占位符）
    ├── stringsurface-summary.csv   §17 两版本 21 列字符串表面聚合
    ├── stringsurface-README.md     §17 口径 / 合规 / 踩坑
    ├── stringsurface-spec.example.json  §17 复现模板（路径占位符）
    └── NOTICE-mappings.md           ProGuard 映射许可提示（禁止分发完整未修改映射）
```

复现（八步）：

```bash
# 1) 端到端演示：证明"炸"和"救活"（30 秒，无需 MC）
bash demo/run.sh

# 2) 真实 mod 批量判定：把"能不能上 X 版本"变成布尔值
java -cp "build:$ASM" mcport.LinkCheck \
  --decl decl-1.21.11.tsv --map map-1.21.1-1.21.11.tsv \
  --mods /path/to/mods --out before.csv

# 3) 全流程（含重映射 + 结构校验 + 复测 + 工单）
bash pipeline.sh 1.21.1 1.21.11 /path/to/mods

# 4) 26.x 去混淆断代专用链路（需本地官方 ProGuard 映射，脚本不会打包/分发它）
bash pipeline-26.sh 1.21.1 26.1 /path/to/mods

# 5) §14 装载编排机自包含回归（零外部数据、零 Mojang 字节、零网络）
python3 tools/test_loader.py

# 6) §15 严格 C 行迁移自包含回归（合成 decl/工单，27 断言）
python3 tools/test_relocate.py

# 7) §16 人工桥工作台自包含回归（合成 decl/工单/callkind，61 断言）
python3 tools/test_bridgegen.py

# 8) §17 字符串姓名表面自包含回归（合成 class / refmap / jar，78 断言）
python3 tools/test_stringsurface.py
```

退出码约定：**0 = 全部可自动处理；2 = 存在 SIGCHG/MISSING，需人工介入。**
可直接接入 CI，把"这个 mod 能不能上 X 版本"变成一个可断言的布尔值。

---

## 7. 诚实的边界声明

1. **达不到"任意版本都有效"**。§1 第 3 层语义漂移在原理上无法被任何静态工具彻底判定（§13 只给出可检测下界）；§4 量化出真实 mod 只剩 ~80% 可自动搬运。
2. **26.1 起 intermediary 归零**：原样搬运实测 0.0%(历史口径 3820) / 0.1%(统一口径 4068 / judged 3977)。
   §8 已用官方 ProGuard 映射 + Fabric intermediary 重建身份桥，把**静态符号可解析率**恢复到 **78.7%（3109/3952）**，
   属**部分解决**：Mixin refmap/@Shadow 声明名、反射字符串、包搬迁后仍不存在的成员、语义漂移、
   以及真实客户端端到端验证，全部**仍未解决**。
3. **JDK 主版本本身在跳**（8→16→17→21→25），进程内跨大版本不现实。
4. **未在真实 Minecraft 客户端里跑通端到端**（需要完整游戏 + Fabric 启动链）。
   26.x 需 JDK 25 / class major 69；本机默认 JDK 17/21 实测 `UnsupportedClassVersionError`。
   §12 已在临时安装的 Temurin JRE 25.0.5 上，把**真实 26.1 游戏类**加载到 JVM 并用
   启动期 `-javaagent` 编织、校验（含 `-Xverify:all`）、链接成功；但这仍**不是**
   Fabric/游戏启动链：只覆盖了一个无外部依赖的叶类与我们自编译的调用方，
   LWJGL/native、Mixin 启动、真实 mod 加载、资源包与网络栈一概未碰。
   demo/ 的 A–F 是等价最小复现，14 mod 的量化是离线字节码静态判定 ——
   它证明"能解析/不能解析"，不证明"跑起来行为正确"。
  91 条 `com/mojang/` 独立库引用被标 EXTERNAL（client jar 不含、本预言机不覆盖），**不是证明它们稳定**；
  真实运行仍需这些库与 26.x 的版本矩阵另行验证（§5 第 15 条）。
5. 定位不是"取代 Fabric/NeoForge"，而是**第三条路**：不重写 mod，只把"能不能跑"变成
   "可测量、可自动修、修不了的精确列出"。它与现有加载器**正交**，可叠加使用。

---

## 8. 26.x 身份层攻坚：原样 0.1% → 静态可解析 78.7%

> 本章是 m00651「继续」之后的增量工作。**所有百分比都是离线字节码静态符号可解析率，不等于能跑、更不等于语义正确。**

### 8.1 思路：把两个"半张地图"拼成一张

26.1 不再发布 obfuscation map，Fabric intermediary jar 缩成 572B 空表，yarn 26.1/26.3 返回 `[]`。
但 26.1 **用的就是 Mojang 真实名**，而 26.1 之前每个版本同时存在：

- 官方 ProGuard 映射：`真实名 -> 混淆短名`（如 `com.mojang.blaze3d.Blaze3D -> fvz:`）；
- Fabric intermediary：`混淆短名 -> class_N / method_M / field_K`（tiny v2）。

两者按 `(obfOwner, obfName, obfDesc)` 求交，即可得到 `intermediary -> 真实名`。`tools/bridge.py` 实现：
实测 **1.21.1 对齐 78401/78922 = 99.34%**、**1.21.11 对齐 93951/94916 = 98.98%**。
首版只有 ~40% 的根因是 ProGuard 左侧是**点分**真实名、描述符里却是 `Lnet/minecraft/X;` 斜杠内部名，
必须先 `replace('.', '/')` 再替换类型才能对上（详见工具 docstring 的 5 条坑）。

### 8.2 版本择一、目标感知重定位、父类链

`tools/bridge26.py` 把两版桥合成 26.1 专用表（归档产物 125913 行：C=10737 / M=57248 / F=49681 / S=8246；
`pipeline-26.sh` 自行生成源 decl 时补进 23 个 `com/mojang/` C 行，S=8269，C/M/F 不变）：

| 动作 | 实测 | 例子 |
|---|---|---|
| 版本择一（选目标 decl 里真实存在的名） | exact 9903 / fallback 727 | `class_563`：1.21.1 `client/model/ElytraModel` vs 1.21.11 `client/model/object/equipment/ElytraModel` |
| 目标感知重定位（唯一简单名命中才改） | relocated 107 | `platform/GlStateManager` → `opengl/GlStateManager` |
| S 行父类链透传 | supers 8246 / 8269 | `EditBox.method_25370()Z` 声明在父接口 `class_364`，按子类 owner 精确查表会漏 491 条 |

两版桥交集 C=7684 冲突 714、MF=65423 冲突 2774（多为 `lambda$...` 编号漂移，少数是真改名）。
`java/mcport/Mapping.java` 现在是**映射逻辑唯一来源**：精确命中优先，未命中沿 S 行父类/接口 BFS
（跳过 `java/lang/Object`），查不到保留原名让 LinkCheck fail-loud；离线 `RemapTool` 与启动期
`McPortRuntime` 都委托它。这是被 §5 第 11 条那次"两套过滤漂移虚报 5.7 个百分点"逼出来的结构约束。
`McPortRuntime` 的 DEFAULT_SKIP 同步补了 `com/mojang/`（26.1 有 474 个游戏类在此包），否则 agent 会去重写游戏自身。

### 8.3 Mixin 注解字符串

`ClassRemapper` 只改常量池/描述符，改不到 `@Mixin(targets=)`、`@Inject(method=)` 里的字符串。
`AnnotationDump` 采样真实格式后，`MixinRewriter` 在 `ClassRemapper` **之前**（都还在 intermediary 命名空间）
改写 class/field/method 的可见与不可见注解、参数/类型/局部变量注解及 `invokedynamic` bsmArgs：

- 全限定 `Lnet/minecraft/class_761;method_22977(...)V` → 改类、成员名、描述符类型；
- 裸 `method_N(desc)ret` → 用 `@Mixin` 的 targets 作 owner 查（`@Mixin` 是 CLASS retention，visible+invisible 都要收）；
- 裸 `field_N` / `method_N`（`@Accessor`/`@Invoker`）→ 按 `(owner,name)` 唯一候选反查，多候选宁可不动。

`MixinCheck` 实测 14 个 mod（26.x 建桥链路）：**interStrings 983 / interTokens 1987 → 25 / 25（降 98.7%）**，
`changed=960 unresolved=24`；LinkCheck 数字前后完全一致（改的是 LinkCheck 看不见的维度）。
残留 25 条因无描述符且映射表无唯一候选，保留原值 fail-loud。

> **常规链路 1987 → 1987 不是 bug**：`mkmap.py` 产的是 intermediary→intermediary 改名表（无 C 行），
> Mixin 注解里的 `class_N`/`method_N` token 本来就不该消失；只有发生命名空间切换（26.x 的
> `bridge-26.tsv` 有 10737 条 C 行把 `class_N` 换成 Mojang 真实名）时这个计数才应下降。
> 常规链路要看的是"改名已落盘"：`RENAME 26 → 0` 且 `RESOLVE 3119 → 3145`。

### 8.4 量化（统一口径，14 个真实 1.21.1 Fabric mod）

先修 `tools/mkdecl.py` 只收 `net/minecraft/` 的过滤，26.1 decl 从 10208 类补全到 **10682 类**
（含 474 个 `com/mojang/` 游戏类）；再修 `LinkCheck` batch 路径漏计 `com/mojang/` 的分母 bug；
最后按 §5 第 15 条把 91 条 `com/mojang/` **独立库**引用标 EXTERNAL（不覆盖、不计入分母）。
三条修复叠加后的统一口径：**4068 refs，judged = 4068 − EXTERNAL**。

| 阶段 | RESOLVE | RENAME | SIGCHG | MISSING | EXTERNAL | judged | 静态可解析 |
|---|---|---|---|---|---|---|---|
| 原样搬运（基线） | 4 | 0 | 2 | 3971 | 91 | 3977 | **0.1%** |
| bridge-1.21.11 | 2522 | 0 | 126 | 1306 | 114 | 3954 | **63.8%** |
| bridge-1.21.1 | 2597 | 0 | 38 | 1317 | 116 | 3952 | **65.7%** |
| 两版合并 | 2691 | 0 | 107 | 1154 | 116 | 3952 | **68.1%** |
| **最终（bridge-26 + 继承 BFS + Mixin 改写）** | **3109** | 0 | 156 | 687 | 116 | 3952 | **78.7%** |

**78.7% = 3109 / 3952**（EXTERNAL = 91 独立库 + 25 JDK 继承）；3109/4068 = 76.4%；
仍需人工 **843 = SIGCHG 156 + MISSING 687**。中间策略的 63.8/65.7/68.1% 各有自己的 judged
（3954 / 3952 / 3952），不与早期那组"62.3 / 64.2 / 66.6%（以 4068 为分母）"混用。
Mixin 注解改写前后 LinkCheck 数字完全一致，因为它修的是字符串维度而非符号引用维度。

单 mod 跨度很大：c2me/krypton 100%、entityculling 95.3%、lithium 93.4%、noisium 88.5%、jei 80.8%，
而 sodium 75.9%、iris 67.4%、fabric-api 0 refs（无 MC 符号引用）。CSV 见 `data/14mods-to-26.1-*.csv`。

最终 MISSING 687 按 LinkCheck 注释重新归因：**290 (42.2%) owner 类不在 26.1**（仍以
`platform/GlStateManager` 为主，重定位只覆盖 107 条 C 行）、**397 (57.8%) 真实名成员在 26.1 已不存在**
（如 `Uniform.glGetUniformLocation`、`RenderSystem.blendFuncSeparate`）。
旧报告的 778 条里含 91 条独立库类假 MISSING，已按 §5 第 15 条剔除。

### 8.5 仍然没解决的部分（不要把 78.7% 读成"能跑"）

1. **`@Shadow`/`@Accessor` 声明名与 refmap 未改写**。只改声明会与 mod 自身调用点脱节（那些 owner 是 mod 类，
   不在映射表），必须做全符号表重写或 refmap 改写 —— 这是另一层工作。字节级扫描仍能在 lithium/iris 等
   mod 里看到 `field_6516`、`method_19293` 等声明名与反射/配置字符串（`ReflectionUtil`、`VanillaAoHelper`）。
2. **语义漂移（§1 第 3 层）不可机械检测**：同名同签名但行为变了，78.7% 一个都覆盖不到。
3. **未在真实客户端端到端**：26.1 需 JDK 25 / class major 69，本机只有 17 与 21，实测抛
   `UnsupportedClassVersionError`；demo 只证明 JVMS 链接机制与 agent 改写有效。
4. **确定性**：桥表输出已改 `sorted(...)`，`PYTHONHASHSEED=1/2/777` 三次 `sha256` 一致，
   且与本研究产物数据行语义相同（86621 / 125912 行）。
   四条流水线（self / 1.21.11 / 1.20.1 / 26.1）+ `demo/run.sh` 在二次修正后全部实跑复测通过；
   `pipeline.sh` 的 RemapTool 明细日志也不再丢进 `/dev/null`；三条脚本补了 locale 自愈（§5 第 16 条），
   现在 `LANG` 为空的 CI / `run_code` 环境也能跑。
5. **许可**：官方 ProGuard 映射头部写明 "you may not redistribute the mappings complete and unmodified"。
   因此 `data/` **只归档测量 CSV、统计与复现脚本**，不分发 `bridge-26.tsv` 或原始 `map-*.txt`。
   复现者需自行从 Mojang 官方途径取得映射，见 `data/NOTICE-mappings.md`。


---

## 9. 宿主侧兼容桥 HostBridge：把 SIGCHG 从「列出来」推到「能链接」

> 本章是 m01283「继续」之后的增量工作。**它只推进机械链接层，不推翻 §7 的任何边界。**

### 9.1 动机：工单里最大的可动块是「名字还在、描述符变了」

4 个新增热门 mod 的 8 份 `LinkCheck --json` 工单（`data/hotmods/`）按
`details` 合计：**RESOLVE 1674 / RENAME 0 / SIGCHG 173 / MISSING 477 / EXTERNAL 56**。
RENAME 为 0 是因为这些 jar 已过离线重映射；剩下两类硬骨头里，SIGCHG 的形态高度一致：

```
com/mojang/blaze3d/systems/RenderSystem.setProjectionMatrix(Lorg/joml/Matrix4f;Lnet/minecraft/class_8251;)V
  # name kept by com/mojang/blaze3d/systems/RenderSystem, descriptor changed
com/mojang/blaze3d/systems/RenderSystem.setShaderLights(Lorg/joml/Vector3f;Lorg/joml/Vector3f;)V
  # name kept by ..., descriptor changed
net/minecraft/class_1043.<init>(IIZ)V
  # name kept by net/minecraft/class_1043, descriptor changed
```

§1 第 1 层已经写明 JVMS §5.4.3 按 **类名 + 成员名 + 描述符** 精确链接。于是
`McPortRuntime` 那套「改 mod 侧引用名」的天花板非常清楚：名字改对了，描述符还是旧的，
一样抛 `NoSuchMethodError`。demo 场景 E1 用最小复现把它变成可断言的事实：

```
-- E1. 纯改名路线 (C) 在连签名都变了的版本上失效 --
[mcport] map loaded: class=0 method=1 field=0 super=0
Exception in thread "main" java.lang.NoSuchMethodError: 'int net.mc.World.getBlockState(int, int, int)'
   (退出码 1 ; 报错里是 getBlockState(III)I —— 名字改对了, 描述符仍对不上)
```

源 mod 写死 `getBlock(III)I`；目标版本只有 `getBlockState(BlockPos)I`。
把名字改成 `getBlockState` 之后，JVM 找的是 **`getBlockState(III)I`**，仍不存在。

### 9.2 反方向：不改 mod，改宿主

`/home/lilyco/文档/deepseek-harness/default-workspace/mcport-跨版本兼容/java/mcport/HostBridge.java` 是第二条正交路线：
在**目标版本游戏类定义之前**注入一个旧签名的转发壳，让旧引用能链接上；真正的语义落在
普通人写的静态适配器里（demo 为 `demo/src/adapter/demo/BlockAdapter.java`）。

规则表 `-Dmcport.bridge=<file>` 每行 6 列（TAB）：

```tsv
# owner  oldName  oldDesc  kind  adapterClass  adapterMethod
net/mc/World	getBlock	(III)I	virtual	demo/BlockAdapter	getBlock
```

`kind=virtual` 时适配器首参自动补宿主 `this`，描述符由工具推导为
`(Lnet/mc/World;III)I`；`kind=static` 则不补。参数槽位按 `Type.getSize()` 累加
（long/double 占 2 槽），返回值按 `getOpcode(IRETURN)` 或 `RETURN` 处理。
`visitEnd()` 注入前先扫一遍宿主已有方法，撞名同描述符直接跳过（否则 `VerifyError`）。
`<init>` / `<clinit>`、规则表为空、列数不对、kind 非法一律 fail-loud。
**语义适配体不自动生成**：旧参数如何变成新调用是语义，机械推导不出来，猜错就是静默错误。

实测（demo E2，JDK 17.0.20.1）：

```
-- E2. 同一份 mod jar + 宿主侧桥 -> 跑通 (mod 零改动) --
mod started on MC 1.21.1-SIGCHG -> block=6
   mod jar sha1: 3796a161a6a9bd31460de4e163375b5ff16add3f
   注意: 源版本 getBlock(1,2,3)=42, 这里=6 -> 名字与描述符都链接上了, 语义仍变了 (§1 第 3 层)
```

注意 `42 → 6` **不是 bug，是刻意设计的证据**：源版本 `getBlock` 固定返回 42，
新版本 `getBlockState(new BlockPos(1,2,3))` 返回 6。名字与描述符都链接上了、进程正常退出，
行为却已经不同 —— 这正是 §1 第 3 层「语义漂移无法被静态工具彻底判定」的最小可执行演示。
HostBridge 把「链接不上」推进到「链接得上」，但把「行为对不对」明确交还给人。

### 9.3 时序铁律：必须在类定义前，不能运行时补

scratch 实验（`/tmp/bridge-exp`）与 demo E3 都验证同一条 JVM 约束：
pre-define 阶段的 `ClassFileTransformer` 可以新增方法；类**已加载**后调用
`Instrumentation.retransformClasses` 再新增方法，HotSpot 直接拒绝：

```
-- E3. 时序铁律: 类已加载后 retransform 加方法被 HotSpot 拒绝 --
loaded net.mc.World methods=2
EXPECTED (HotSpot): UnsupportedOperationException: class redefinition failed: attempted to add a method
   => 宿主桥必须在类定义前 (-javaagent premain) 注入, 不能运行时补
```

首版探针试图反射 `sun.instrument.InstrumentationImpl`，被 JPMS 挡下
（`IllegalAccessException: module java.instrument does not export sun.instrument to unnamed module`），
改用导出的 `java.lang.instrument.Instrumentation` 接口才得到上面这条真正的 JVM 错误。
因此 `HostBridge` **故意不注册** `canRetransform=true`，`redefined != null` 时打印
`REFUSE retransform of already-loaded ...` 并原样放过，绝不制造「以为加上了」的错觉。
这与 JEP 451 的边界一致：原文写明
*"It is not a goal to prevent agents from being loaded at JVM startup via the -javaagent or -agentlib command-line options, nor to issue warnings upon such use."*
—— 长期合法的寄生方式仍只有启动期 `-javaagent`，动态 attach 不在路线内。

### 9.4 可复现性：修掉 demo 自己的两个真 bug

1. **退出码显示错**：E1 初版写 `E1=$(cmd | head -3)` 后取 `${PIPESTATUS[0]}`，
   捕获的是赋值语句的状态，把 java 崩溃错显示成「退出码 0」。改为重定向到
   `build/e1.out` 后取 `$?`，并新增断言 `[ "$E1RC" -ne 0 ]`。E2/E3 同样改为
   临时文件 + 显式 `-eq 0` 断言，脚本不再靠 `grep` 字符串隐式判成功。
2. **jar 时间戳漂移**：`jar cf` 每次写入当前时间，导致 demo 连跑两遍 4 个受版本控制的
   jar 全部变脏、sha1 变化，与「可复现分发包」自相矛盾。改用 JDK 17+ 的
   `jar --date=2026-11-14T00:00:00Z`（`jar --help | grep -- '--date='` 探测，缺失时降级）。
   实测连跑两遍，5 个 jar 的 sha256 逐行一致：

```
778532aea2b46269f2892e247c97cda66e5b5c1b2d012556cabe47b0504723ff  api-v1.jar
e3353f5f6f82f1560976c8a16b8a14dce4d63a60569712f107b9a49ac5294898  api-v2.jar
f8bf088c2e83d4c718edf9482d05ca8ac6073a991e19dc90452cc92990df14fb  api-v2b.jar
60c0bc871848fb30c69aa68589dfac4268989662173ebc3c431969e9d0153423  mod-1.20.1.jar
f3f4aa8852806cd59fdfb7e2f8078171b8533157ef38b420b7b94b3bc23457ac  mcport-runtime.jar
```

全量 `javac -nowarn -cp 'lib/*' -d build java/mcport/*.java` 通过（22 个 class，
含新增 `HostBridge.class`），`demo/run.sh` 两遍 `FINAL_EXIT=0`、末尾 `OK`。

### 9.5 边界：这一章**没有**解决什么

1. **173 条 SIGCHG 一条都还没被真实修复**。`demo/bridge-v2b.tsv` 只有一个玩具规则，
   真实条目的适配器需要逐条读上游源码/反编译、确认参数语义、写测试；本仓库不含这些适配器。
2. **477 条 MISSING 不在能力范围内**。`RenderSystem.disableBlend()V # member gone`、
   `GlStateManager._activeTexture(I)V # owner class gone` 这类没有可转发的目标，
   生成转发壳只会把链接期错误推迟成运行期错误，反而更糟。工具选择不去碰它们。
3. **`<init>` 明确不支持**：构造器改变意味着对象布局/初始化契约变了，不是加个壳能糊过去的；
   工单里 `class_1043.<init>(IIZ)V`、`RenderTarget.<init>(Z)V` 都属此类，仍需改 mod。
4. **语义漂移（§1 第 3 层）依旧无法被静态工具彻底判定**。E2 的 42→6 是明证；同名同签名行为变化
   连静态扫描都不会报，HostBridge 更不会。
5. **仍未在真实 Minecraft 客户端端到端**；26.x 需 JDK 25 / class major 69 这一环境门槛已由
    §12 在 JRE 25 + 真实 26.1 游戏类上收窄为「启动期编织/校验/链接可行」，
    但本章 A–F 本身仍是等价最小复现 + JVM 规范/实测，不证明任何 14 mod 或 4 热门 mod 能跑。
6. **双 agent 组合已验证可行，但必须限定改写授权范围**（由 §11 收窄本条）。两个
   `-javaagent` 同进程挂载、顺序反转均实测通过，两处改写落在**不同类**上互不覆盖；
   但 `McPortRuntime` 默认「改所有非 `DEFAULT_SKIP` 前缀的类」，映射表若命中宿主或
   自写适配器会静默误改名（§11.4 的 G7）。组合必须 `-Dmcport.only=<mod 包>`。
   这仍是**最小复现级结论**，未在真实 Minecraft 客户端双挂验证。

**净结论**：跨版本失效里「符号链接不上」这一层，可以从「约 80% 可静态解析」再往前推到
「SIGCHG 有可运行的机械适配路线」；但「任意版本都有效」仍然不可达，
因为语义与已删除成员这两层与 JVM 链接机制无关，加载器补不出来。

---

## 10. 发布前隔离 smoke：两个交付链 bug

0.1.1 发布前，把工作区复制到 `/tmp/mc-port-smoke`（排除 `.git` / `build` / `*.class`），
模拟「用户刚 clone 仓库、直接按 README 跑」。两条流水线各暴露一次真实交付问题：

| 脚本 | 首次 smoke | 根因 | 修复与复跑 |
| --- | --- | --- | --- |
| `pipeline.sh` | 第 3 步 `ClassNotFoundException: mcport.LinkCheck`，exit 1 | 全新 clone 没有 `build/`，但 8 个步骤都用 `java -cp "build:$ASM"`；`pipeline-26.sh` 有 1/9 编译，常规脚本漏了 | 新增 0/8 `javac -nowarn -cp 'lib/*' -d build java/mcport/*.java` 与 `[ -d "$MODS" ]` 自检。复跑 8 步全通：1162 judged / **319 需人工**（SIGCHG 99 + MISSING 220），按约定 exit 2 |
| `pipeline-26.sh` | 误传 `1.21.1 1.21.11 26.1 <modsDir>`，报 `缺少 intermediary jar: /tmp/mc/hot/remapped-26.1` | 用法是 `<srcVer> <dstVer> <modsDir> [lastVerWithProguard]`，第 3 参必须是目录；误把 `26.1` 当 modsDir 后触发的是下一层报错 | 加 `[ -d "$MODS" ]` fail-loud 并打印正确用法。按 `1.21.1 26.1 /tmp/mc/hot/remapped-26.1 1.21.11` 复跑 9 步全通：1162 judged / **331 需人工**（SIGCHG 74 + MISSING 257），exit 2 |

**`exit 2` 不是失败**：它是 §3.1 / README 约定的「仍有 SIGCHG/MISSING 需人工」闸门。
本次只修交付链的可复现性，不改变任何兼容性结论；§9.5 的 6 条边界在本章发布时全部不变
（第 6 条后来由 §11 的双 agent 组合实验收窄）。
教训：README 写「可直接进 CI」时，CI 既不能依赖预编译产物，也不能让错参数穿透到第二步才报无关错误。

---

## 11. 双 agent 组合：RENAME 与 SIGCHG 在同一份 mod 里同时修

### 11.1 为什么必须做这一轮

§9 分别验证了两条路线：`McPortRuntime` 改 **mod 侧**引用解纯改名（RENAME），
`HostBridge` 在**宿主类定义前**注入旧签名转发壳解 SIGCHG。但真实 mod 不会分类崩——
一份字节码里完全可以同时有「只改了名」和「连签名都变了」的引用。若两个
`ClassFileTransformer` 在同一 JVM 里互相覆盖、顺序敏感、或共享 `Mapping` 状态时串味，
§9 的两个单点结论就不能相加。§9.5 第 6 条因此诚实标注「未验证同进程双 agent 组合」。
本章在隔离目录 `/tmp/combo-exp` 把这条边界攻掉，并把结论固化成 `demo/run.sh` 场景 F。

### 11.2 最小复现构造

| 角色 | 内容 |
| --- | --- |
| 源版本 `net/mc/Region` | `getBlock(III)I`=42（目标里只改名）、`getBiome(III)I`=7（目标里连签名都变） |
| 目标版本 `net/mc/Region` | `readBlock(III)I`=42（RENAME）、`getBiomeAt(BlockPos)`=x+y+z（SIGCHG）、`classify(int)` 带分支制造 `StackMapTable` |
| mod `demo/ComboMod` | **同一个 main** 里同时调 `r.getBlock(1,2,3)` 与 `r.getBiome(1,2,3)`，并反射打印宿主方法表 |
| 语义适配器 `demo/ComboAdapter` | `getBiome(Region,int,int,int)` → `r.getBiomeAt(new BlockPos(x,y,z))`；源 7 → 6 显式暴露漂移 |
| `combo-map.tsv` | `M\tnet/mc/Region\t(III)I\tgetBlock\treadBlock`（mod 侧重命名表） |
| `combo-bridge.tsv` | `net/mc/Region\tgetBiome\t(III)I\tvirtual\tdemo/ComboAdapter\tgetBiome`（宿主侧桥规则） |

关键设计：两条改写作用于**不同类**——`McPortRuntime` 只该改 `demo/ComboMod`，
`HostBridge` 只改 `net/mc/Region`。这是组合能成立的结构性原因，不是运气。

### 11.3 六场景 F：单 agent 各修一半，双 agent 才跑通

| 场景 | 挂载 | 结果 |
| --- | --- | --- |
| F0 plain | 无 | `rc=1`，`NoSuchMethodError: 'int net.mc.Region.getBlock(int, int, int)'` |
| F1 runtime | 仅 `mcport-runtime.jar` | `rc=1`，死在 `getBiome(III)I`（**SIGCHG 没修**），改名层已生效 |
| F2 bridge | 仅 `hostbridge.jar` | `rc=1`，死在 `getBlock(III)I`（**RENAME 没修**），打印 `[hostbridge] rules=1 owners=[net/mc/Region]` |
| F3 both + `only` | 双 agent + `-Dmcport.only=demo/` | `rc=0`，`combo on 1.21.1-COMBO block=42 biome=6`；方法表含 `getBiome/3` 与 `readBlock/3` |
| F4 both default | 双 agent，不加 `only` | `rc=0`，同 F3（此表未投毒，故侥幸也对） |
| F5 both reverse | 先 hostbridge 后 mcport | `rc=0`，同 F3 → **顺序无关** |

正式 `demo/run.sh` 把它固化成 F1（单 runtime 断言 `getBiome` 报错）、F2（单 bridge 断言
`getBlock` 报错）、F3（双 agent + `only`，断言 `rc=0` / `block=42 biome=6` / `getBiome/3` /
mod jar sha1 零改动）、F4（顺序反转断言同结果）。六场景 A–F 实跑 `DEMO6_RC=0`，末尾 `OK`。

### 11.4 第二轮加严 G：真坑在「默认改写范围」

在目标宿主里加 `classify(int)`（`javap -v` 确认有 2 处 `StackMapTable`），另造一份
`combo-map-poison.tsv` 故意多投一条 `getBiomeAt(Lnet/mc/BlockPos;)I → getBiomeAtV2`，
模拟映射表命中宿主方法的情形：

| 场景 | 条件 | 结果 |
| --- | --- | --- |
| G1 / G2 | `-Dmcport.only=demo/ComboMod` / `=demo/` | `rc=0`，宿主方法表正常 `getBiomeAt/1` |
| G3 / G4 | 默认范围（宿主带 `StackMapTable`）/ 顺序反转 | `rc=0`，**无 VerifyError / ClassFormatError**，默认改写后字节仍合法 |
| G5 | 缺 `-Dmcport.map` | `rc=1`，明确 `NoSuchMethodError`（fail-loud） |
| G6 | 缺 `-Dmcport.bridge` | `IllegalStateException: [hostbridge] no -Dmcport.bridge=<spec>; refusing to start`（fail-loud） |
| **G7 poison + 默认范围** | 投毒表，不加 `only` | `rc=0` 但方法表变成 `getBiomeAtV2/1`：映射表把**宿主** `getBiomeAt` 静默改名，适配器调用被一起改坏 |
| G8 poison + `only` | 投毒表，限定 mod 类 | `rc=0`，方法表正常 `getBiomeAt/1` |

`mod` jar 前后 sha1 均 `0e3df8c68a6f6b90bb092c60a005d95b11cc7ad0`：
agent 全程不落盘。G7 是本章最有用的一条：`DEFAULT_SKIP` 只排除了
`net/minecraft/ / com/mojang/ / java/ / javax/ / jdk/ / sun/ / com/sun/`，
**不认识用户自写的 adapter 包和共享类**。默认「改所有非 skip 类」在单 agent 场景没事，
一旦与宿主桥组合、且映射表含宿主条目，就会静默改坏宿主 → 桥转发到不存在的方法。

> **组合纪律（写进 demo F3/F4）**：双 agent 必须同时给
> `-Dmcport.only=<mod 包前缀>`，把 `McPortRuntime` 的授权范围锁死在 mod 类；
> 宿主与 adapter 只交给 `HostBridge` 在 pre-define 阶段按 owner 精确匹配处理。

### 11.5 边界收窄后的净结论

§9.5 第 6 条从「**未验证**同进程双 agent 组合」收窄为「**已验证可行**，但必须
`-Dmcport.only` 限定改写范围，且仍是最小复现级、未在真实客户端双挂」。
其余边界里，173 条 SIGCHG 仍待人工写适配器、477 条 MISSING 无转发目标、
`<init>` 不支持、语义漂移无法彻底判定（F3 的 42/6 又一次自证）、真实客户端端到端
**一条都没松动**；「26.x JDK 25 未做」已由 §12 收窄为
「真实 26.1 类 + JRE 25 + 双 agent 编织/校验/链接已验证，仍非客户端启动链」。
**「任意版本都有效」依旧不可达**：本章只证明「符号链接不上」这一层里，
两种机械改写可以在同一 JVM 里安全叠加，没有碰到语义层与已删除成员层。

---

## 12. JRE 25 × 真实 26.1 major-69 类：把「本机连加载都不可能」收窄到可验证层

### 12.1 为什么单独做这一轮

§7 第 4 条、§9.5 第 5 条原先写的是「本机只有 JDK 17/21，26.x 连加载都不可能」。
这只证明**本机默认运行时**不够，并不证明「启动期 `-javaagent` 方案遇到 Java 25 / class major 69 会失效」。
两者是不同命题：JVM 字节码版本、ASM 读写能力、JVM 校验器、`java.instrument` premain 四层都要分别过。
所以这一轮只在隔离目录做最小可判定实验，不下载/不分发任何游戏字节到仓库。

### 12.2 实验输入与合规边界

* 本机默认 `openjdk 17.0.20.1`；临时安装 Temurin **JRE 25.0.5+8**（清华 Adoptium 镜像，
  `sha256 6fac98f0c8202efc3135a9e9e42aa61963ec42d1c5cbb40caf231e7b14a24ef6`，含 `java.instrument@25.0.5`）。
* 真实类来自本机 `REAL-26.1.jar` 的 `com/mojang/blaze3d/GpuOutOfMemoryException.class`：
  **436 B / class major 69 / sha1 `a401a336c2ede849b840601504992b41483e37bc`**，
  `javap` 只声明构造器，常量池无 `org/lwjgl`、`net/minecraft` 等外部依赖，是能脱离游戏加载的叶类。
* 编译期 stub、调用方、adapter、observer transformer 都是本仓库自写源码；
  `out/stub` 故意**不进入运行期 classpath**。`demo/real26/` 与发布包**不含 Mojang 字节**：
  脚本运行时从使用者自备的 `MC_26_1_JAR` 抽取，缺前置则打印 `SKIP` 并返回 0。
* ASM 9.9 支持 `V25`；三个 agent 打成 fat jar（ASM 对 bootstrap 可见），避免
  `NoClassDefFoundError: org/objectweb/asm/...` 与 observer 内部类漏打包。

### 12.3 S0–S11 实测（`bash demo/real26/run.sh`，输出 `REAL26_OK`）

| 场景 | 结果 | 它判定了什么 |
| --- | --- | --- |
| S0 | 默认 JDK 17 `UnsupportedClassVersionError`，rc=1 | 类版本门槛真实存在，不是文档推测 |
| S1 | JRE 25 `LOADED ... major=69`，rc=0 | 真实 26.1 字节码能被 Java 25 定义 |
| S2 | 无 agent `NoSuchMethodError: legacyMessage()`，rc=1 | 旧引用在真实目标类上确实链接失败 |
| S3 | HostBridge 注入后 `REAL-26.1-BRIDGE-OK`、`major=69`、`declared=legacyMessage`，rc=0 | **真实 major-69 类在 pre-define 被编织、通过校验并链接** |
| S4 | 只有 McPortRuntime：改名生效但宿主仍缺方法，rc=1 | RENAME 单路线的边界在真实类上复现 |
| S5/S6 | 双 agent 与顺序反转均 `REAL-26.1-BRIDGE-OK`，rc=0 | §11 的组合结论在 JRE 25 / 真实类上成立；`-javaagent` 启动期加载无 JEP 451 动态 agent 警告 |
| S7/S8 | 缺 bridge 规则表 / 缺映射表均 fail-loud | 失败语义跨 JDK 17→25 不变；S7 的 `premain` 抛异常由 JVM 以 native abort（rc=134）表现，脚本 `ulimit -c 0` 防 core dump |
| S9 | observer 落盘变换后字节：**535 B / major 69 / sha1 `18cf2fca971ca3887b42602789b1fc765aa41585`**，`javap` 多出且只多出 `legacyMessage()` | 字节级证明「在内存里改，jar 里原类不变」，且没有把 class 降级成旧版本 |
| S10 | 只挂 McPortRuntime 时 observer dump sha1 **等于原类** `a401a336…`，且调用仍 `NoSuchMethodError` | `-Dmcport.only=demo26/LegacyRename` 把改写严格锁在调用方，宿主一字节未动 |
| S11 | `-Xverify:all` + 双 agent + observer：rc=0，dump 仍 535 B / major 69 | 强校验模式下编织结果仍合法，不是靠关闭验证侥幸通过 |

### 12.4 收窄到哪里，以及没有收窄到哪里

**收窄**：原先「26.x 需要 JDK 25，本机不可能加载」只剩「需要 JRE 25」这一条环境事实；
在 JRE 25 上，ASM 9.9 读写 major 69、`java.instrument` premain、HostBridge 注入、
McPortRuntime 限定改写、JVM 全量校验、链接、fail-loud、双 agent 顺序无关，全部实测通过。

**没有收窄**：真实 Minecraft 客户端/Fabric 启动链、LWJGL/native 库、Mixin 注入链、
资源与网络栈、任何一个真实 mod 能跑；173 条 SIGCHG 与 477 条 MISSING 仍需人工，
`<init>` 与语义漂移仍不可修，§1 第 3 层依旧封死「任意版本都有效」。
本实验选的是**一个无外部依赖的叶类**，这是为了把 JVM 层命题判干净，
绝不能外推成「26.1 客户端能启动」或「78.7% 静态可解析率等于能运行」。

### 12.5 复现

```bash
MC_26_1_JAR=/path/to/26.1-client.jar JAVA25=/path/to/jre25/bin/java bash demo/real26/run.sh
# 或让脚本按固定 sha256 拉 JRE 25：
MC_26_1_JAR=/path/to/26.1-client.jar MC_REAL26_AUTO_JRE=1 bash demo/real26/run.sh
```

缺 jar / 缺 JRE 25 时打印 `SKIP` 并返回 0，因此 `bash demo/run.sh` 的 A–F 六场景与
纯 JDK 17 可复现性完全不受影响；`demo/real26/README.md` 逐项列出证明与不证明的边界。

---

## 13. 语义漂移真实 jar 量化：把"检测不出来"拆成可检测下界 + 不可判定区间

### 13.1 动机与前置调研（/lyco ACQUIRE）

§1 第 3 层此前只有人造 demo（场景 D 的 `256 -> 384`、E2 的 `42 -> 6`）作证据，
措辞"任何字节码工具检测不出来"过于绝对。本轮把它升级成四个**真实 client jar 的全量测量**，
目的不是推翻结论，而是把"检测不出来"精确化到哪一段能判、哪一段判不干净。

先按 /lyco 做现成方案检索：精确项目名命中
`siom79/japicmp`（784★ Apache-2.0，2026-11-08 活跃）、
`revapi/revapi`（224★ Apache-2.0）、
`mojohaus/clirr-maven-plugin`（12★，已 archived）。
三者都只做 **API / 字节码签名级** 兼容比较（类/方法/描述符的增删与可见性），
不读方法体、不判行为等价，对"同名同签名但实现变了"这一层 fit < 50%。
无 ≥80% fit 且活跃的 adopt 候选，硬约束（只留聚合测量、不分发 Mojang 映射与 client jar）
也不允许直接套用，故 **build** 一个最小"方法体指纹 + 稳定身份对齐"预言机。

### 13.2 方法（两个工具，都不分发输入）

* `java/mcport/BodyHash.java`：ASM 9.9 `SKIP_DEBUG|SKIP_FRAMES` 遍历 jar 内每个
  非 abstract / 非 native 方法，算三列 SHA-256：`sk`（opcode 序列 + 数值/字符串常量 +
  变量索引 + switch 分支数 + IINC 增量，**刻意抹掉所有 owner/name/desc/Type 与跳转 Label**）、
  `op`（纯 opcode 序列）、`call`（调用目标 owner.name:desc）。
  抹掉名字使混淆短名变化不影响比较；抹掉 Label 与调用目标，正是"骨架一致 ≠ 语义一致"的证据来源。
* `tools/drift_align.py`：身份**不用**混淆短名、**不用** Fabric intermediary，
  而用官方 ProGuard 映射把 1.21.1 / 1.21.11 的 `(obfOwner,obfName,obfDesc)` 反解成
  `(真实类内部名, 真实成员名, 真实描述符)`；26.1 / 26.3 已去混淆，三元组本身即真实身份。
  两侧落到同一命名空间，于是 `1.21.11 ↔ 26.1` 可跨去混淆断代直接对齐。
  分类：`op` 异 → OPCODE_DIFF；`op` 同 `sk` 异 → OPERAND_DIFF；
  仅 26.1→26.3 开启 `call` 比较（混淆名与真实名混排时该列天然不可比）→ CALL_TARGET_DIFF；
  三列全同 → `identical_all_fingerprints`。

合规：`body-*.tsv` 含真实成员名与指纹，是**本地测量中间产物**，不进仓库、不进发布包；
`data/` 只留 `drift-summary.csv`（纯聚合计数）、`drift-README.md`、
`drift-spec.example.json`（路径占位符）。见 `data/NOTICE-mappings.md`。

### 13.3 四版全量实测（2026-11-14 本机，真实 client jar）

BodyHash 输出规模：1.21.1 = 8269 类 / 71190 方法，1.21.11 = 10291 / 86600，
26.1 = 10682 / 89518，26.3 = 11383 / 95427，全部 RC=0 无 WARN。
参数化版 `tools/drift_align.py` 重跑与首次实验 `drift-summary.json` 逐字段一致。

| 版本对 | 同身份方法 | OPCODE_DIFF | OPERAND_DIFF | CALL_TARGET_DIFF | **可检测下界** | **三列全同** | call 可比 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1.21.1→1.21.11 | 49618 | 5699 | 99 | — | **5798 (11.69%)** | 43820 (88.31%) | 否 |
| 1.21.11→26.1 | 74316 | 3312 | 107 | — | **3419 (4.60%)** | 70897 (95.40%) | 否 |
| 26.1→26.3 | 78555 | 3944 | 88 | 1817 | **5849 (7.45%)** | 72706 (92.55%) | 是 |
| 1.21.1→26.1 | 44808 | 6254 | 106 | — | **6360 (14.19%)** | 38448 (85.81%) | 否 |

`old_unmapped/new_unmapped`（官方映射未列出的 `<init>` / `<clinit>` / 部分 override）
直接跳过，不计入分母。`26.1→26.3` 的 1817 条 CALL_TARGET_DIFF 是"骨架没变、调用目标变了"的实例。

### 13.4 收窄到哪里，以及没有松动什么

**收窄**：§1 第 3 层原句"任何字节码工具检测不出来"改成"任何工具都无法**彻底判定**"。
现在能给出真实 jar 上"同名同签名方法里实现字节码指纹确实变了"的**可检测下界**
（4.6%–14.2%），并明确 `85.8%–95.4%` 是静态工具**判不干净**的区间。
demo E2 的 `42 → 6` 属 LDC 常量变化，是 `sk` 能抓到的子集，不再是"完全抓不到"。

**没有松动一毫米**：
* 指纹全同**不等于**行为相同。被抹掉的恰是能改变行为的东西：跳转目标重排、被调用者
  内部实现、注册表/配置/运行时状态、反射、资源与 native；比较 `call` 也看不到被调用者内部。
* 指纹不同**不等于**一定坏掉，可能只是无害重构。可检测下界是"实现变更候选"，不是"失效率"。
* 这些数字**不给** 78.7% 静态可解析率加任何可运行性保证，不证明任何 mod 能跑；
  173 条 SIGCHG + 477 条 MISSING、`<init>`、Mixin refmap / 反射字符串、真实客户端端到端，
  全部照旧未解决。
* 因此"任意版本绝对不失效不可实现"的核心论据不变，方案仍是 fail-loud 而非"尽量猜"。
  静态字节码比较能**列出风险候选**，彻底判定仍只能靠测试或数据校验。

### 13.5 复现与踩坑

```bash
mkdir -p build && javac -nowarn -cp 'lib/*' -d build java/mcport/*.java
for v in 1.21.1 1.21.11 26.1 26.3; do
  java -Xmx1g -cp 'build:lib/*' mcport.BodyHash "/path/to/REAL-$v.jar" "/work/body-$v.tsv"
done
python3 tools/drift_align.py --repo . --spec /work/drift-spec.json --out-dir /work/out
```

所有输入自备（client jar + 官方 ProGuard 映射），脚本不下载、不复制任何 Mojang 字节或映射文本；
`data/drift-spec.example.json` 是带 `<WORKDIR>/<MAPS>` 占位符的模板。
本轮新增 4 个可复现踩坑（详见 `data/drift-README.md`"踩过的坑"）：
① `Collections.list(Enumeration<? extends ZipEntry>)` 泛型推断冲突必须逐个 add；
② 一开始用 intermediary 当身份只命中 39310/71190 行，得到 10.64% / 5.13%
   **已废弃不可引用**，改官方 ProGuard 真实名后才是上表；
③ ProGuard 点分真实名必须先 `replace('.', '/')` 再替换描述符（历史 40% 对齐率坑）；
④ 身份集合迭代受 `PYTHONHASHSEED` 影响，输出必须 `sorted(...)`；
⑤ 混淆↔去混淆的 `call` 列不可比，保守关闭以免把命名断代误报成实现变化。


## 14. 版本无关的装载编排机：分类 → 装配 → 预言机 → fail-loud

### 14.1 需求边界与 /lyco ACQUIRE（为什么不是「再造一个 Fabric」）

新目标「做好全平台全版本 mod 加载机器」若按字面理解为**任意平台、任意 MC 版本、任意 mod 都能直接运行**，
与 §1 三层机制、§2 fit 矩阵、§7 边界、§8 的 26.x 断代、§13 的语义漂移量化直接冲突：
Bedrock 是 C++ 无 JVM 字节码；同名同签名方法体的 85.8%–95.4% 指纹全同区间静态判不干净；
成员被删除（477 条 MISSING）没有可转发目标。因此**不谎称做出字面意义的万能加载器**。
本轮交付的是可实现的等效物：一台**与 MC 版本无关的装载编排机** `tools/loader.py`，
输入任意 `(mod jar, 目标 client jar)`，不查版本白名单，靠 jar 结构与 `version.json` 自动分代，
选择已被验证的装配路线，跑符号预言机，写出结构化 plan / 逐条工单 / 启动包装脚本，
并在不支持、缺制品、需人工、未 check 时一律 fail-loud。它**不是** Minecraft 启动器，
不生成游戏启动命令，`MCPORT_LAUNCH_CMD` 必须由使用者自己的启动器提供。

按 /lyco 的 gh 近义词循环实跑（2026-11-15，账号 lilyco-42）：
`universal minecraft mod loader` / `cross version mod loader` / `platform agnostic mod launcher` /
`javaagent minecraft launcher` 四个词均 0 命中；`version independent mod loader` 只命中
`FabricMC/fabric-loader`（903★，pushed 2026-10-19，desc "Fabric's mostly-version-independent mod loader."）
与两个 0★ fork。复核 `Sinytra/Connector`（762★，只把 Fabric mod 接到 NeoForge）、
`GeyserMC/Geyser`（5967★，Bedrock→Java 协议代理）、`ViaVersion/ViaVersion`（1654★，只做网络协议）。
无 ≥80% fit 且活跃的 adopt 候选；硬约束是「不分发 Mojang client jar / 映射 / 第三方 mod 二进制，
且必须 fail-loud 而非静默猜名」，故 **build** 最小编排层，复用仓库已有的 `LinkCheck` / `RemapTool` /
`McPortRuntime` / `HostBridge`，不引入新的运行时依赖。

### 14.2 分代判据：只读 jar 结构，不加载类、不查版本表

`probe_client()` 读 `version.json` 的 `id / java_version / protocol_version / world_version`，
统计 `net/minecraft/<pkg>/` 层级真实类 `nm_hier`、jar 根级短名类 `root_short`、首个 `.class` 的 major，
按 `nm_hier/classes ≥ 0.5` 判 `deobf`、`root_short/classes ≥ 0.5` 判 `obf`、
`classes=0` 判 `non_jvm`、其余 `unknown`。`CLASS_MAJOR_JAVA = {61:17, 65:21, 69:25}` 只作环境门槛。
五个真实 client jar 实跑：

| target | classes | major | java | protocol | nm_hier / ratio | root_short | generation |
|---|---:|---:|---:|---:|---:|---:|---|
| 1.20.1 | 7436 | 61 | 17 | 763 | 25 / 0.0034 | 7388 | obf |
| 1.21.1 | 8269 | 65 | 21 | 767 | 26 / 0.0031 | 8220 | obf |
| 1.21.11 | 10291 | 65 | 21 | 774 | 33 / 0.0032 | 10201 | obf |
| 26.1 | 10682 | 69 | 25 | 775 | 10187 / 0.9537 | 0 | deobf |
| 26.3 | 11383 | 69 | 25 | 777 | 10715 / 0.9413 | 0 | deobf |

`probe_mod()` 读 `fabric.mod.json` / `neoforge.mods.toml` / `mods.toml`，
统计 `class_|method_|field_[0-9]+` 与 `net/minecraft/<小写包>/<类>` 字节、Mixin 配置、
`.dll/.so/.dylib/.jnilib/.exe` native 文件、声明的 `minecraft` / `java` 依赖。
7 个真实样本（c2me / cloth-config / entityculling / ImmediatelyFast / fabric-language-kotlin /
xaerominimap / yacl）均为 `loader=fabric`、native=0；`fabric-language-kotlin` 0 条游戏引用。

### 14.3 决策矩阵与三套已验证装配路线

| route | 条件 | strategy | 装配 / 预言机口径 | verdict |
|---|---|---|---|---|
| `SAME_VERSION` | mod 声明的 MC 与目标 `id` 相符 | `none` | 不挂 agent；`LinkCheck --map` 自检 | AUTO / NEEDS_MANUAL |
| `NO_GAME_REFS` | 0 条游戏引用（如纯 Kotlin 运行时） | `none` | 不挂 agent；空工单 | AUTO |
| `OBF_CROSS` | 混淆期跨版（1.20.1–1.21.11） | `startup` | `-javaagent:mcport-runtime.jar -Dmcport.map=map-<src>-<dst>.tsv`，`LinkCheck --map`（`pipeline.sh` 工单口径） | AUTO / NEEDS_MANUAL |
| `DEOBF_BREAK` | 26.x 去混淆断代 | `offline` | **先** `RemapTool --map bridge-<dst>.tsv`，再对重映射 jar 用真实名 `decl-<dst>.tsv` **不给 --map** 复测（`pipeline-26.sh` 口径）；**不挂 agent** | AUTO / NEEDS_MANUAL |
| `RUNTIME_JAVA_MISMATCH` / `NATIVE_BOUND` / `UNSUPPORTED_LOADER` / `UNSUPPORTED_NON_JVM` / `UNKNOWN_GENERATION` | Java 不匹配 / native / 非 Fabric / 非 JVM / 无法分代 | — | 拒绝装配，`jvmArgs=[]` | UNSUPPORTED |
| `MISSING_ARTIFACT` | 缺 `decl-*.tsv` / `map-*.tsv` / `bridge-*.tsv` | — | 拒绝无映射表装配 | MISSING_ARTIFACT |

退出码：`0` 全部可装配（AUTO / PLAN_ONLY）、`2` 有 SIGCHG+MISSING 需人工、`1` 不支持 / 缺制品 / 检查失败。
`--emit-script` 生成 Bash 包装，只从 `verdict in (AUTO, PLAN_ONLY)` 收集 `JVM_ARGS`，
要求外部设置 `MCPORT_LAUNCH_CMD`；**硬错误优先**：`manual / unsupported / missing_artifacts` 任一非 0
或存在非 AUTO/PLAN_ONLY 项 → `REFUSE ... exit 2`；否则若未跑 `--check` → 再次 `REFUSE`；
只有全部 AUTO 且已 check 才 `exec "$MC_JAVA" "${JVM_ARGS[@]}" $MCPORT_LAUNCH_CMD`。

### 14.4 七场景实跑（真实 client jar + 真实 mod，2026-11-15）

制品目录 `/tmp/mcport-loader-art` 只放 8 个指向本机 `decl/map/bridge` 的符号链接，不含 Mojang 字节。

| 场景 | target / java | mod | route / strategy | 关键结果 | rc |
|---|---|---|---|---|---:|
| S1 | 1.21.11 / JDK21 | ImmediatelyFast | OBF_CROSS / startup | `total=155 resolve=78 sigchg=13 missing=56 ceiling=50.3`，`jvmArgs` 两条，NEEDS_MANUAL | 2 |
| S2 | 26.1 / JRE25 | ImmediatelyFast | DEOBF_BREAK / offline | `RemapTool` 成功；复测 `resolve=86 sigchg=9 missing=52 ceiling=55.5`，`jvmArgs=[]` | 2 |
| S3 | 26.1 / JRE25 | ImmediatelyFast + `--strategy startup` | DEOBF_BREAK / startup | **无条件 UNSUPPORTED**，`check=null remap=null jvmArgs=[]` | 1 |
| S4 | 26.1 / JRE25 | fabric-language-kotlin | NO_GAME_REFS / none | `total=0`，AUTO，脚本 exec | 0 |
| S5 | 1.21.11 / JDK21 | ImmediatelyFast，无 `--check` | OBF_CROSS / startup | PLAN_ONLY；脚本仅 `REFUSE: plan-only ...`，无 exec | 0 |
| S6 | 26.1 / JRE25 | ImmediatelyFast，无 `--artifacts` | DEOBF_BREAK / offline | 缺 `bridge-26.1.tsv` → MISSING_ARTIFACT | 1 |
| S7 | 1.21.1 / JDK21 | c2me + `--check` | SAME_VERSION / none | `total=9 resolve=9 ceiling=100`，AUTO，脚本 exec | 0 |

另有六组纯路由决策 P1–P6（4 个 mod × 5 个真实 jar / JDK17·21·25）：
P3 往旧 1.20.1 + JDK17 时 c2me / ImmediatelyFast 因声明 `java>=21` 判 `RUNTIME_JAVA_MISMATCH`；
P4 26.1 + JDK17 时 4 个 mod 全 UNSUPPORTED（class major 69 需 Java 25）；
P5 26.1 + JRE25 时 3 个 `DEOBF_BREAK`、1 个 `NO_GAME_REFS`，`missing_artifacts=0`；
P6 不给制品时 3 个 `MISSING_ARTIFACT`，证明 fail-loud 不是空话。

### 14.5 自包含回归：零外部数据、零 Mojang 字节、零网络

`tools/test_loader.py` 用 `tempfile` 合成 obf / deobf / non_jvm 三类 client jar
（含 `version.json` 与 `ca fe ba be` + major）、八类 mod jar、decl/map/bridge 文本、
伪 `java`（按 `FAKE_JAVA_MAJOR` 报版本，按 `--json` 写确定性 LinkCheck 工单），
覆盖 probe / decide / strategy / jvm_args 的 19 个单元断言与 I1–I6 集成断言：
PLAN_ONLY 不 exec、NEEDS_MANUAL 硬拒绝、26.x startup 有无 `--check` 都 UNSUPPORTED、
缺制品 fail-loud、NO_GAME_REFS 可执行、native / 异加载器 / 非 JVM / Java 不匹配均 UNSUPPORTED。
`python3 tools/test_loader.py` 最终 `RESULT ALL_OK 49`；`python3 -m py_compile tools/loader.py tools/test_loader.py` OK。

### 14.6 四个真 bug / 口径坑（写下来防止回归）

1. **26.x bridge 表绝不能当 `LinkCheck --map`**：`LinkCheck.loadMap()`（`java/mcport/LinkCheck.java:297-305`）
   只认 `M` 行 `owner|desc|oldName → newName`，不处理 bridge 的 `C` 行整类改名与描述符整体换命名空间。
   修补前 C5 把 `bridge-26.1.tsv` 直接喂 `--map` 得 `resolve=4 missing=141`（虚报）；
   改成 `RemapTool` 先改字节码、再对真实名 decl 无 `--map` 复测后 S2 得 `resolve=86 missing=52`。
2. **26.x startup 一律拒绝**：启动期 agent 加载身份桥不仅 check 口径错，装配本身也只跑过离线链路；
   加固为有无 `--check` 都判 UNSUPPORTED 且清空 `jvmArgs`，不再生成带 `-javaagent` 的假可执行方案。
3. **plan-only 不启动**：早期 `--emit-script` 会把未跑预言机的 PLAN_ONLY 直接 `exec`；
   现在未 `--check` 必 `REFUSE ... exit 2`。
4. **硬错误必须先于 plan-only 提示**：原判定顺序让「unsupported + 未 check」只提示未 check，
   掩盖了真实原因；最终 `hard → not a.check → exec` 三级顺序由 S3/S5/S6 与 I1–I4 覆盖。
   另两处测试环境坑：run_code 里 `sys.executable` 为 `''` 需回退 `/usr/bin/python3`；
   伪 java 固定报 21 会把 26.1/Java25 场景误判成 RUNTIME_JAVA_MISMATCH，必须按场景传 `FAKE_JAVA_MAJOR=25`。

### 14.7 本章收窄了什么、没有收窄什么

收窄：**「给定任意 `(mod, target)` 组合，能不能自动判代、自动选已验证路线、自动给出正确的 JVM 参数或离线重映射产物、
并把不能自动处理的部分精确列出且拒绝执行」** 从人肉判断变成了 49 断言 + 13 组真实/合成场景可复现的程序。
仍没有收窄：它不是游戏启动器，不启动 Fabric / Forge / NeoForge / 真实客户端，不覆盖 Bedrock、native 库、
Mixin refmap / `@Shadow` 声明名、反射字符串、`<init>`、已删除成员、语义漂移（§13 的 85.8%–95.4% 区间），
也不把 78.7% 静态符号可解析率变成「能跑」。**「全平台全版本任意 mod 都能跑」仍不可达**；
本章给出的是在这条硬边界内，能自动做对、且做不到的部分一定 fail-loud 的装载编排机。

复现（自备 client jar / 映射制品，仓库不提供）：

```bash
python3 tools/test_loader.py
python3 tools/loader.py --repo . --target /path/to/REAL-26.1.jar \
  --mod /path/to/mod.jar --java /path/to/jre25/bin/java \
  --source 1.21.1 --artifacts /path/to/artifacts \
  --check --tickets /tmp/tickets --out plan.json --emit-script launch.sh
```

## 15. 严格 C 行类迁移：把 MISSING 里「同名类换包」机械解析出来

### 15.1 需求边界与 /lyco ACQUIRE

§14 的装载编排机只保证「能自动做对的部分自动做、做不到的部分 fail-loud」；
4 个热门 mod × 2 个目标版本的 8 份 LinkCheck 工单仍剩 **173 条 SIGCHG + 477 条 MISSING** 需人工。
本章只问一个更窄的问题：MISSING 里「老 owner 类整包搬走、但同名同描述符成员还在」的那部分，
能不能在不猜语义的前提下机械修掉？

/lyco ACQUIRE：`gh search repos` 五个近义词
（`minecraft mapping class relocation tool` / `fabric intermediary class move remapper` /
`mixin refmap generator` / `minecraft auto bridge generator` / `asm class relocation minecraft`）
每个 `--limit 5` 全部 0 hits，连续两轮空。硬约束是**不分发 Mojang client jar / 官方映射 /
第三方 mod 二进制**，且任何不确定必须 fail-loud；现成 API-diff 工具（§2 / §13 的 japicmp / revapi / clirr）
只比签名、不处理「类换包 + 常量池整体改名」的字节码改写。故 build 最小自研生成器 `tools/relocate.py`。

### 15.2 工单形态与三级严格判据

477 条 MISSING 按注释粗分：`# owner class gone` 192 条、老 owner 仍在 decl 但成员消失 285 条。
在「老 owner 不在目标 decl + 目标 decl 中存在唯一同名同描述符候选」的 57 条里，
**44 条 simple 名相同**（几乎全是 `com/mojang/blaze3d/platform/GlStateManager` 及内部类
→ `com/mojang/blaze3d/opengl/GlStateManager` 换包），
**13 条 simple 名不同**，是危险偶合：`GuiGraphics.bufferSource` → `RenderBuffers`、
`FastColor`$ARGB32.multiply` → `ARGB`、`BufferUploader.draw` → `RenderType`、
`HoverEvent`$ItemStackInfo.getItemStack` → `Display`$ItemDisplay` 等。
同名同描述符**不是**语义证据，所以不同简单名一律拒绝。

`tools/relocate.py`（纯标准库，`schema=1`，`--spec` / `--out-dir`）执行三级判据：

1. **类级唯一同名投票**：只取 MISSING 里老 owner 不在目标 decl 的引用，按
   `(name, desc)` 找目标 decl 的直接声明 owner；仅当 `simple(old) == simple(new)`
   且候选唯一才生成 `C` 行。不同简单名、歧义、`<init>`/`<clinit>` 直接拒绝。
2. **整张 C 行重映射描述符**：把方法参数与字段类型里的 `L<oldOwner>;` token 全表替换
   （5 轮收敛），否则 `BLEND` / `DEPTH` 这类指向内部类的字段会漏改。
3. **目标直接声明校验**：`(newOwner, name, mappedDesc)` 必须命中目标 decl 的 `M/F` 行；
   成员在新类里也被删了就拒绝。

输出 `supplement.tsv`（**仅 C 行**）、`accepted.tsv`、`stats.json`、`summary.csv`
到调用方 `--out-dir`，不写入仓库。`tools/test_relocate.py` 用 tempfile 合成 decl/工单，
零 Mojang 字节、零网络，**27 断言全绿**，覆盖字段 desc 重映射、内部类对、确定性重跑、
不同简单名 / 歧义 / 构造拒绝。

### 15.3 两版本实测（8 份真实工单 + 2 份真实目标声明表）

| 目标 | decl 类 | 工单 | MISSING | parse_fail | 严格 C 行 | 接受 | owner_exists | 无严格 C 行 | 搬过去成员也没了 | 不同简单名拒绝 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.21.11 | 10291 | 4 | 220 | 0 | 4 | **29** | 141 | 41 | 9 | 6 |
| 26.1 | 10682 | 4 | 257 | 0 | 1 | **19** | 144 | 83 | 11 | 24 |
| 合计 | — | 8 | 477 | 0 | 5 | **48** | 285 | 124 | 20 | 30 |

**合计严格机械可修 48 条**，不是 Round 2 粗估的 44 条（粗估没做整张 C 行描述符重映射，
漏了 8 个内部类字段）。两版本 `ambiguous=0`。C 行共 5 对：1.21.11 为
`platform/GlStateManager` 主类 + 3 个内部类 → `opengl/...`；26.1 只有主类，
去混淆后的真实名空间里没有同名内部类候选，故 `BLEND`/`DEPTH` 落进
`no_exact_mapped_decl`。`owner_exists` 是老类仍在 decl、属别的失效机制，不归迁移。
聚合数字见 `data/relocate-summary.csv`，口径见 `data/relocate-README.md`。

### 15.4 端到端复测：RemapTool 改字节码后，无 --map 复测

链路：`relocate.py` 产 C 行补充 → `javac` 全量 →
`RemapTool --map supplement.tsv` 对 4 个已重映射 mod jar 再改常量池 owner / 描述符 / 类型引用 →
`LinkCheck --decl <目标 decl> --mod <fixed.jar> --json`（**不带 `--map`**）。

| 目标 | total | RESOLVE | SIGCHG | MISSING |
| --- | --- | --- | --- | --- |
| 1.21.11 before → after | 1190 | 843 → **872** | 99 → 101 | 220 → **189** |
| 26.1 before → after | 1190 | 831 → **850** | 74 → 78 | 257 → **234** |
| 合计 before → after | 2380 | 1674 → **1722** | 173 → **179** | 477 → **423** |

按「C 行规范化引用 + 忽略 `#` 注释 + 集合归并」复核桶转移：
1.21.11 `MISSING→RESOLVE 29` / `MISSING→SIGCHG 2`；
26.1 `MISSING→RESOLVE 19` / `MISSING→SIGCHG 4`。
那 6 条没有洗白：`_clear(IZ)V`、`_texImage2D(IIIIIIIILjava/nio/IntBuffer;)V`、
`BLEND`/`DEPTH` 在新类里同名但描述符也变了（或内部类 C 行缺失），
LinkCheck 诚实地重新判成需人工。7 类危险关键字样本复测仍全部 MISSING（4 / 9 条），
**13 条不同简单名误配 0 洗白**。EXTERNAL 56 条不变；2380 − 56 = 2324 判定数前后守恒。

### 15.5 关键技术转折：为什么不改 LinkCheck、不新增 RELOCATE 桶

`java/mcport/LinkCheck.java:41` 的 `CLS_RENAME` 与 `:301`
`if (p[0].equals("C")) CLS_RENAME.put(p[1], p[2])` 是全文件仅有的两处引用；
`:257-274 classify()` 在 `!CLASSES.contains(owner) && !SUPER.containsKey(owner)` 时
直接判 `MISSING # owner class gone`，完全不查 `CLS_RENAME` —— 这是死代码缺陷。
但 §14.6 已经证明 26.x 的 `bridge-26.tsv` 绝不能当 `LinkCheck --map`
（`loadMap` 只读 C/M/F、不读 S 行、不整体换描述符命名空间；早期 C5 直接喂得到
`resolve=4 / ceiling=2.6` 的虚报）。

正确路线**不是**给预言机加一个 `RELOCATE` 桶，而是**先把字节码真的改对、再复测**：
`relocate.py` 产 C 行补充 → `RemapTool` 走 `Mapping.mapClass` 改常量池 →
LinkCheck 看到的是已改好的新 owner，自然判 RESOLVE。于是省掉了原设想的
「改 `main` 汇总 / `writeJson` details / `analyze` 数组 / `batch` CSV /
`tools/loader.py` 五处 + 新增桶」；旧五字段工单 JSON 完全向后兼容，
`tools/test_loader.py` 49 断言与 demo A–F 未回归。
若将来要让 `--map` 直接吃 C 行，必须先修 `classify()`，并同步 §14.6 的口径。

### 15.6 本章收窄了什么、没有收窄什么

收窄：MISSING 里 **48 条「同类换包 + 成员仍在」** 从人工列表变成机械可解析、可复现、
且拒绝规则明确的 C 行补充；「不能机械修」的边界从粗口径变成 4 类可执行判据
（不同简单名 / 歧义 / 构造 / 目标成员已删）。

仍没有收窄：8 份工单复测后仍有 **179 条 SIGCHG + 423 条 MISSING** 需人工；
173 条 SIGCHG 的参数/返回类型转换是语义，不能无脑生成桥；477 条 MISSING 的主体、
§13 的 85.8%–95.4% 指纹全同判不干净区间、Mixin refmap / `@Shadow` 声明名、
反射字符串、`<init>`、真实客户端 / Fabric / LWJGL 端到端、26.x 需 JDK 25，全部未解决。
**48 条只是符号可解析候选，不证明行为等价，更不证明能跑。**
「全平台全版本任意 mod 都能跑」仍不可达；本章只是把编排机里可自动做对的那部分又推进了一格。

### 15.7 复现与踩坑（自备制品，脚本不下载不入库）

```bash
python3 tools/test_relocate.py
python3 tools/relocate.py --spec /work/spec.json --out-dir /work/gen
javac -nowarn -cp 'lib/*' -d build java/mcport/*.java
java -cp 'build:lib/*' mcport.RemapTool --map /work/gen/1.21.11/supplement.tsv --in /work/mod.jar --out /work/fixed.jar
java -cp 'build:lib/*' mcport.LinkCheck --decl /path/to/decl-1.21.11.tsv --mod /work/fixed.jar --json /work/fixed.json
```

* 第一版逐条独立匹配用了只认 `(...)` 结尾的方法正则，漏掉 `()V` / `(I)I` 带返回类型
  与字段描述符，477 条里 404 条 parse fail；方法必须 `^(.+?)\.([^.(]+)(\(.*\).*)$`、字段单独一支。
* 逐条独立匹配会漏掉字段 desc 里的旧包 token；改成**先类级投票生成整张 C 行、再重映射描述符**才救回内部类字段。
* 把候选全集打印出来会截断输出（26.1 的 `<init>()V` 有 1765 个不同简单名候选），只打印计数。
* 端到端脚本里 `assert delta[sigchg]==0` 断言写太严而失败：6 条诚实地转成 SIGCHG 属预期，非工具 bug。

---

## 16. SIGCHG 人工桥工作台：零自动修复的负结果（2026-11-15）

§15 把 MISSING 里 48 条「同类换包」变成机械可解析后，8 份真实工单仍有
**179 条 SIGCHG + 423 条 MISSING** 需人工。本章攻的是第一个桶：
「同名不同描述符」能否自动生成 `HostBridge` 转发规则？结论是 **不能安全自动修**；
交付物是把这个负结果变成可复现、可审计、fail-loud 的工作台，而不是补丁。

### 16.1 需求边界与 /lyco ACQUIRE

`gh search repos` 五个近义词 `minecraft host bridge agent` / `mixin signature adapter generator` /
`minecraft descriptor change adapter` / `javaagent method bridge generator` /
`minecraft sigchg remapper` 全部 0 hits（每个 `--limit 5`）；连续两轮空；
japicmp / revapi / clirr 只做 API 签名级比较、不读方法体，fit < 50%。硬约束仍是
「不分发 Mojang client jar / 官方映射 / 第三方 mod 二进制 + 猜不出来就拒绝」→ build 最小自研。
与 §14/§15 一样，本章不承诺让 mod 跑起来，只把「哪一步能自动、哪一步必须人写」判干净。

### 16.2 三个契约：工单丢 opcode、CallKind 恢复、HostBridge 六列

1. `LinkCheck` 的 `writeJson` 固定五数组 `RESOLVE/RENAME/SIGCHG/MISSING/EXTERNAL`，
   `collect` 用 ASM 收 Methodref / Fieldref / Type / Ldc / invokedynamic 后只留
   `owner|name|desc` 三元组（JVMS §5.4.3 的链接身份），**丢掉 invoke opcode**。
2. `HostBridge` 规则恰好 6 列 `owner / oldName / oldDesc / kind / adapterClass / adapterMethod`，
   `kind` 只接受 `virtual`（注入实例方法，adapter 首参为宿主 this）或 `static`；
   把 `invokevirtual` 猜成 static，解析期会抛 `IncompatibleClassChangeError`；
   `interface` / `special` / `mixed`、`<init>`/`<clinit>` 一律不支持。
3. 新增 `java/mcport/CallKind.java`：`ZipInputStream` + `ClassReader`（`SKIP_DEBUG|SKIP_FRAMES`），
   在 `visitMethodInsn` 把 INVOKESTATIC / INVOKEVIRTUAL / INVOKEINTERFACE / INVOKESPECIAL
   记成 static / virtual / interface / special，同一三元组多种 opcode 记 `mixed`，输出 4 列 TSV。
   `--in`/`--out` 缺值显式抛异常，不再数组越界。
4. `tools/bridgegen.py` 的 `Decl` 把 **M 与 F 分表**（`LinkCheck` 的 `findMember` 本来就是
   `meth ? METHODS : FIELDS`），候选查找镜像父类链 + 接口 BFS；字段、构造、无候选、歧义全拒绝。
   真实 decl 里 `class_8685.comp_1626` 同时是方法和字段，混表会误判歧义。

### 16.3 602 条引用的分桶实测

输入：§15 复测后的 8 份工单（4 个热门 mod × 1.21.11 / 26.1）、两张真实目标声明表、
8 个已重映射 mod jar。命令与聚合产物见 §16.7 / `data/bridgegen-summary.csv`（17 列纯计数）。

| 目标版本 | total | SIGCHG | MISSING | 唯一候选规则 | 不安全骨架引用 | 语义拒绝 | opcode 拒绝 | 构造 | 字段 | 歧义 | 无目标 | 重复 | auto_fixed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.21.11 | 290 | 101 | 189 | 2 | 3 | 51 | 28 | 18 | 37 | 0 | 153 | 1 | 0 |
| 26.1 | 312 | 78 | 234 | 2 | 3 | 30 | 30 | 16 | 34 | 5 | 194 | 1 | 0 |
| **合计** | **602** | **179** | **423** | **4** | **6** | **81** | **58** | **34** | **71** | **5** | **347** | **2** | **0** |

口径：`REJECT_NO_TARGET`（153 / 194）是 MISSING 在新 decl 找不到同名成员；
`REJECT_UNPARSED` 两版本均为 0（旧版 16 列表头曾被误读成 153，修复后 17 列由
`csv.DictReader` 逐列断言）。`REJECT_OPCODE` 含 interface / special / mixed；
`SKELETON_MECHANICAL_UNSAFE` 是 triage 行数，去重后才是规则数。

### 16.4 四条唯一候选，零自动修复

镜像 `LinkCheck` BFS 后 138 条 SIGCHG 有唯一同名候选，但只有 6 条引用（去重成 4 条规则）
满足「参数可转换 + 返回可转换」的纯机械形状：

* `net/minecraft/class_1041.method_4495()D` → `()I`（i2d 扩宽）；
* `net/minecraft/class_1144.method_4873(Lnet/minecraft/class_1113;)V` → 有返回值（pop 丢弃）；
* `com/mojang/blaze3d/platform/Window.getGuiScale()D` → `()I`（i2d 扩宽）；
* `net/minecraft/client/sounds/SoundManager.play(...SoundInstance;)V` → 有返回值（pop 丢弃）。

**这四条全都不安全**：`double`→`int` 丢精度/改数值语义，void→有返回值会丢掉调用方
本该消费的结果（demo E2 的 42→6 正是同名同签名语义漂移的教训）。因此
`bridge-candidates.tsv` 文件头写死 `HUMAN REVIEW REQUIRED; never auto-load`；
`adapters/*.java` 是可编译但方法体一律
`throw new UnsupportedOperationException("MCPORT_HUMAN_REVIEW_REQUIRED ...")` 的骨架；
只有显式 `--emit-rules` 才额外写可加载的 `bridge-rules.tsv`（语义由人确认并负责）；
`stats.auto_fixed = 0` 是硬编码断言。**旧参数如何变成新调用是语义，机械推导不出来。**

### 16.5 修复的五个真 bug（都写进 `tools/test_bridgegen.py` 的 61 断言）

1. 方法正则 `(\(.*\))$` 要求描述符以右括号结尾，漏掉 `()V` / `(I)I` 的返回类型，
   179 条 SIGCHG 全被误判「无候选」；正解 `^(.+?)\.([^.(]+)(\(.*\).*)$` 且字段单独一支。
2. `Decl` 初版把 M/F 行混进一张表，`class_8685.comp_1626` 被误判歧义；分表后
   602 条 triage 只有这一条从 `REJECT_AMBIGUOUS` 变为 `REJECT_SEMANTIC_CONVERSION`。
3. 同一缺失符号出现在 2 个 mod 工单，旧版生成 6 条规则、2 个 adapter 各含重复的
   `public static` 方法（javac 必然报错，`HostBridge` 注入重复签名会 `VerifyError`）；
   按 `(owner,name,desc,newDesc,kind)` 去重后 4 条唯一规则，`duplicate_candidates=2`，
   `adapters_for` 再加一道重复方法断言。
4. `param_conv` 要用 `WIDEN.get(old, set())` 才不漏 B/S/C 的 int-family；
   `return_conv` 方向写反会把 target double 到 legacy float 的窄化误当 widening，
   已整体重写并明确只认 identity / JLS 5.1.2 widening。
5. `CallKind.java` 的 `a[++i]` 无边界检查，缺值数组越界；补显式异常。

### 16.6 本章收窄了什么、没有收窄什么

收窄：把「SIGCHG 能否自动生成桥」从一句猜测变成 602 条逐条可审计的分桶、
4 条候选 + 2 条重复 + 0 自动修复；补齐工单缺失的 opcode 维度；
修正 M/F 分表与候选去重两个会产出坏字节码的真 bug。
**没有收窄**：8 份工单复测后仍是 **179 SIGCHG + 423 MISSING** 需人工；
§13 的语义漂移无法被静态工具彻底判定，Mixin refmap / `@Shadow` 声明名、反射字符串、
真实客户端 / Fabric / LWJGL 端到端、26.x 需 JDK 25、`<init>` 与已删除成员，全部未解决。
**四条候选不是补丁，不证明行为等价，更不证明能跑。**
「全平台全版本任意 mod 都能跑」仍不可达；本章只是把「必须人工」的证据做实。

### 16.7 复现与踩坑（自备制品，脚本不下载不入库）

```bash
python3 tools/test_bridgegen.py                 # 61 断言，合成 decl/工单/callkind，零外部数据
javac -nowarn -cp 'lib/*' -d build java/mcport/*.java
python3 tools/bridgegen.py --spec /work/spec.json --out-dir /work/gen --classes build --java java
# 逐条人工审阅候选与抛异常骨架后，才考虑显式 --emit-rules
```

* 产物 `callkind.tsv` / `triage.tsv` / `bridge-candidates.tsv` / `adapters/*.java` /
  `stats.json` / `summary.csv` 只写 `--out-dir`，含真实成员名的中间表不进仓库、不进发布包；
  `data/` 只留 `bridgegen-summary.csv` 纯聚合 + 口径 + 路径占位模板。
* 精确锚点替换必须先 dry-run 校验 `count=1`：缩进逐字不符会整批不落盘；
  JS 模板字符串里内嵌 Markdown 反引号会直接编译失败（用占位符拼接）；
  **最隐蔽的一条**：`String.replace(anchor, replacementString)` 会把 replacement 里的
  `` $` `` 当成「插入匹配前缀」特殊模式，正则 `...)$` 后紧跟反引号就会把整段前文复制进替换串，
  REPORT 曾因此从 87KB 膨胀到 350KB；replacement **必须写成函数** `() => text`。
* 发布脚本的宽正则 `stats\.json$` 曾误伤自带的 `data/bridge-stats.json`；
  与 §14/§15 同理，本章所有「可分发」判定都只认聚合数字，不认逐条符号表。



## 17. 字符串姓名表面：LDC / refmap 的精确审计与重写（2026-11-15）

### 17.1 需求边界与 /lyco ACQUIRE

§15 / §16 只处理字节码里的符号引用（Methodref / Fieldref / 描述符 / Mixin 注解）。
但 `RemapTool` 对非 `.class` 条目一律 `zout.write(data)` 原样复制，ASM
`Remapper.mapValue` 对裸 String 也原样放行；`MixinCheck` 只数注解字符串。于是
**refmap JSON、`Class.forName` 风格 LDC、配置里的点分类名**构成第二个姓名表面，
五字段 LinkCheck 工单完全看不到它。本机四个已重映射热门 mod 的资源逐条哈希比对
证明：`RemapTool` / §15 重映射**没有改动任何非 class 资源**。

/lyco ACQUIRE 五个 gh 近义词 `minecraft reflection string remapper` /
`mixin refmap remapper tool` / `class forName mod remapper` /
`minecraft string constant remap` / `fabric refmap analyzer` 全部 0 hits（连续两轮空）；
japicmp / revapi / clirr 只比签名不读字符串常量，fit < 50%。硬约束「不分发 Mojang
client jar / 映射 / 第三方 mod 二进制 + 猜不出来就 fail-loud」→ build 最小自研
`tools/stringsurface.py`。本节不承诺「修好 mod」，只把第二表面里**能精确验证**的
改名做掉、把不能的逐条列出。

### 17.2 三个契约

* **工单缺维度**：LinkCheck `writeJson` 只留 `owner|name|desc`，看不到字符串。
* **常量池**：只改 `CONSTANT_String`(8) 指向的 Utf8；若同一 Utf8 还被
  `CONSTANT_Class` / `NameAndType` 引用（shared），追加新 Utf8 槽并只改
  `CONSTANT_String.name_index`，绝不碰共享名字；重建后恢复原 class major。
  Modified UTF-8 / 非 ASCII 改名一律 `DECODE_FAIL` 不改字节。
* **目标可验证**：类 token 只有当老名字不在目标 decl、C 行唯一映射到**目标 decl 里
  存在**的新 owner 才改；`Lowner;name(desc)ret` 形式的成员还要联合映射 owner /
  成员名 / 描述符 token，且 `(newOwner,newName,newDesc)` 必须在目标 decl 声明或
  继承命中。映射表 M/F 键是 `(owner,desc,name)`，decl 表是 `(owner,name,desc)`，
  两套 BFS 必须分开（§17.5 第 2 条）。

### 17.3 8 个真实 jar 的表面分布

输入：§15 复测后的 4 个已重映射热门 mod × 2 个目标版本（1.21.11 / 26.1），两张
真实 decl 与两张真实 map（1.21.11 为 C=0 的 identity 表，26.1 为 intermediary→真实名桥）。
每版本 jars=4 / class_entries=1140 / resource_entries=13 / string_occurrences=3644 /
unique_strings=2606 / no_game_token=3510。

| 版本 | 精确可改 | 已在目标 | unresolved | 映射目标缺失 | 成员目标缺失 | 改写条目 |
|---|---|---|---|---|---|---|
| 1.21.11 | 2（成员） | 36 | 96 | 0 | 0 | 1 |
| 26.1 | 68（10 类 + 58 成员） | 12 | 54 | 33 | 10 | 5 |
| 合计 | 70 | 48 | 150 | 33 | 10 | 6 |

1.21.11 的 2 条是 `xaerominimap.refmap.json` 里 `method_18096(...)` → `method_76795(...)`
的两处副本；26.1 的 68 条含 4 个 `.class` 里的 LDC（`Lnet/minecraft/class_276;` →
`Lcom/mojang/blaze3d/pipeline/RenderTarget;` 等 10 条）与 refmap 的 58 条成员联合映射。
`unresolved` 150 条（含 `MAPPED_TARGET_MISSING` 33 + `MEMBER_TARGET_MISSING` 10）
**全部保持原字节**并进 `triage.tsv`，进程 `exit 2`。聚合见 `data/stringsurface-summary.csv`。

### 17.4 结构验证：改了字符串，不改符号链接

* 26.1 的 4 个改写 `.class` 逐个 `javap -verbose` rc=0、`major version: 65`、LDC 出现
  新真实名；两个 `fixed/*.jar` 的 `unzip -t` 全通过，refmap JSON 可重新 `json.loads`。
* 对 26.1 原 jar 与 fixed jar 复跑 `LinkCheck --decl decl-26.1.tsv`：五字段工单
  `details` 数组**逐字节相同**（`total=768 / resolve=578 / sigchg=49 / missing=137`），
  唯一差异是 JSON 里的 `mod` 路径字段。`MixinCheck` 输出亦相同
  （`mixinClasses=37 annotationStrings=110`）。证明字符串表面改写**不污染**
  §15 / §16 的符号预言机口径。
* audit 与 rewrite 两次运行的 `triage.tsv` 哈希一致（确定性）。
* 1.21.11 的 fixed refmap 含新名 `method_76795`、不含旧名 `method_18096`。

### 17.5 五个真 bug（均已修复并写进 78 断言回归）

1. **JSON key collision 漏判**：原 `if nk in out and nk != k` 在 `nk==k` 时放过真碰撞；
   改 `if nk in out: raise ValueError`。
2. **decl 表类型混淆**：`decl_methods/fields` 是 set 而通用 `_bfs` 假定 dict →
   `AttributeError: set object has no attribute get`；拆成 map 字典 BFS + decl 集合 BFS。
3. **javap classpath 指错**：`-cp` 指到目录而非 fixed jar 本身，报
   `Error: class not found: t.Shared`。
4. **JSON 重序列化假改写**：无精确改名时仍 `json.dumps` 导致缩进变化，4 个
   `fabric.mod.json` / `*.mixins.json` 被误判改写（首轮 `rewritten=26`）；加
   `changed[0]` 标志、无改名直接返回原字节 → 真实 `rewritten=6`。这是「把格式差异
   当修复」的假阳性，最危险。
5. **粗扫误判**：早期用正则扫 `.class` 原始字节得「上百个类名字符串」，精确常量池
   解析证明 8 个 jar 的裸类名 LDC 为 0，真实盲区在 `L...;` 描述符形态与 refmap JSON。

另有 §16 已记的 `String.replace(anchor, replacementString)` 会把 replacement 里的
`$` 紧跟反引号当成「插入匹配前缀」特殊模式；本章插入同样用函数式替换 `() => text`。

### 17.6 本章收窄了什么、没有收窄什么

**收窄**：把「Mixin refmap / 反射字符串未覆盖」从一句边界，变成可执行的精确审计器：
70 条可验证改名、150 条逐条 fail-loud、6 个真实文件条目改写，且改后符号预言机工单不变。

**没有收窄**：`--rewrite` 只是**符号**改名，不证明这些字符串在运行期被如何使用
（反射、序列化、网络协议、配置 schema）；26.1 的 33 条 MAPPED_TARGET_MISSING 与
10 条 MEMBER_TARGET_MISSING 说明映射表本身也不完整；`assets/` 下的点分类名文案被
有意排除；179 SIGCHG + 423 MISSING（§16 口径）仍需人工；真实客户端 / Fabric /
LWJGL / Mixin 运行时 / 语义漂移 / Bedrock 全部未解决。**静态可解析率仍不等于能跑，
「全平台全版本任意 mod 都能跑」仍不可达。**

### 17.7 复现与踩坑（自备制品，脚本不下载不入库）

```bash
python3 tools/test_stringsurface.py                 # 78 断言，零外部数据
python3 tools/stringsurface.py --spec /work/spec.json --out-dir /work/audit
python3 tools/stringsurface.py --spec /work/spec.json --out-dir /work/rw --rewrite
```

* 默认只审计不写 jar；`--rewrite` 才产 `fixed/*.jar`；有 unresolved 就 `exit 2`。
* spec 模板见 `data/stringsurface-spec.example.json`（仅路径占位符）；聚合数字见
  `data/stringsurface-summary.csv`（21 列纯计数）；口径 / 合规 / 踩坑见
  `data/stringsurface-README.md`。
* `triage.tsv` / `stats.json` / `fixed/*.jar` 只写 `--out-dir`，**不进仓库与发布包**
  （发布脚本有禁止断言）。
* 中文路径 + 空 locale 会让裸 `javac` 报 `file not found`（§5 第 16 条），所有 `*.sh`
  已 locale 自愈。



*数据来源：GitHub API（2026-11-14）取仓库健康度；minecraft.wiki 取混淆时间线；
本机 client jar / intermediary jar / ProGuard 映射取 API 流失；JLS/JVMS SE21 与 JEP 451/457/484 原文取 JVM 层约束；
Modrinth 官方 API 取 mod 样本与"逐版本构建"事实；§8 的对齐率、引用归因与 Mixin 计数均为本机实测
（官方 ProGuard 映射 × Fabric intermediary × 26.1 client jar × 14 个 Modrinth mod 字节码，2026-11-14）。
§4 / §8 的 4068 条统一口径与 91 条 `com/mojang/` 独立库豁免，来自 2026-11-14 二次修正后的
四条流水线实跑（`/tmp/mcport-work-{self2,fwd2,back2,26b}/out/`），`data/` 内 CSV 已同步重生成。
§9 的时序约束来自本机 HotSpot 17.0.20.1 实测与
JEP 451 / Java SE 17 `java.lang.instrument.Instrumentation` 文档；工单计数来自
`data/hotmods/*.json` 的 `details` 数组（2026-11-14）。
§10 来自隔离目录 `/tmp/mc-port-smoke` 的两条流水线实跑日志（2026-11-14，输入为 4 个热门 mod 的重映射样本）。
§11 来自 `/tmp/combo-exp` 的双 agent F/G 实跑与 `demo/run.sh` 六场景全绿日志（2026-11-14）。
§12 来自 `/tmp/real26-exp` 与 `demo/real26/run.sh` 的 S0–S11 实跑（2026-11-14，Temurin JRE 25.0.5 + 真实 26.1 client jar 内的单个 major-69 叶类）。
§13 来自四个真实 client jar（1.21.1 / 1.21.11 / 26.1 / 26.3）的 `java/mcport/BodyHash.java` 全量指纹
与 `tools/drift_align.py` 官方 ProGuard 真实名身份对齐实跑（2026-11-14，参数化版重跑逐字段一致；
`data/drift-summary.csv` 为聚合结果，输入字节与映射均不分发）。
§14 来自 `tools/loader.py` / `tools/test_loader.py` 在 5 个真实 client jar、4 个真实 mod 上的
P1–P6 / S1–S7 实跑与 49 条自包含断言（2026-11-15；制品目录仅符号链接，输入字节不分发）。
§15 来自 `tools/relocate.py` / `tools/test_relocate.py` 在 4 个热门 mod × 2 个目标版本的 8 份真实
LinkCheck 工单、两张真实目标声明表上的生成 + RemapTool + 无 `--map` 复测实跑（2026-11-15；48 条接受、13 条误配未洗白；输入字节与映射均不分发，聚合数字见 `data/relocate-summary.csv`）。
§16 来自 `java/mcport/CallKind.java` / `tools/bridgegen.py` / `tools/test_bridgegen.py` 在 §15 复测后的
8 份真实工单、2 份目标声明表、8 个已重映射 mod jar 上的实跑与 61 条自包含断言（2026-11-15；602 条引用、
4 条唯一人工候选、`auto_fixed=0`；输入字节、callkind/triage/骨架均不分发，聚合数字见 `data/bridgegen-summary.csv`）。
§17 来自 `tools/stringsurface.py` / `tools/test_stringsurface.py` 在 §15 复测后的 8 个真实
mod jar、2 张目标声明表、2 张映射表上的 audit / rewrite 实跑、4 个改写 `.class` 的 `javap` 结构校验与
78 条自包含断言（2026-11-15；7288 次字符串出现、70 条精确可改、150 条 fail-loud、6 个真实条目改写；
输入字节、triage / fixed jar 均不分发，聚合数字见 `data/stringsurface-summary.csv`）。*
