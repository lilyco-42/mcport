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

**这一类失效无法被任何加载器、任何重映射器、任何字节码工具检测出来。** 只能靠测试或数据校验。
这是"任意版本绝对不失效"不可实现的**核心论据**，也是本方案 fail-loud 而非"尽量猜"的原因。

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

---

## 6. 交付物与复现

```
mcport-跨版本兼容/
├── REPORT.md                        本报告（§8 = 26.x 去混淆断代攻坚）
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
│   └── McPortRuntime.java           启动期 -javaagent 兼容层（"寄生 Java 本身"）
├── tools/
│   ├── mkdecl.py                    生成目标版本 API 声明表（以真实字节码为准）
│   ├── mkmap.py                     生成 intermediary 身份的重映射表
│   ├── bridge.py                    官方 ProGuard × Fabric intermediary → inter→真实名桥
│   ├── bridge26.py                  版本择一 + 目标感知重定位 + S 行父类链
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
    └── NOTICE-mappings.md           ProGuard 映射许可提示（禁止分发完整未修改映射）
```

复现（四步）：

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
```

退出码约定：**0 = 全部可自动处理；2 = 存在 SIGCHG/MISSING，需人工介入。**
可直接接入 CI，把"这个 mod 能不能上 X 版本"变成一个可断言的布尔值。

---

## 7. 诚实的边界声明

1. **达不到"任意版本都有效"**。§1 第 3 层语义漂移在原理上不可检测；§4 量化出真实 mod 只剩 ~80% 可自动搬运。
2. **26.1 起 intermediary 归零**：原样搬运实测 0.0%(历史口径 3820) / 0.1%(统一口径 4068 / judged 3977)。
   §8 已用官方 ProGuard 映射 + Fabric intermediary 重建身份桥，把**静态符号可解析率**恢复到 **78.7%（3109/3952）**，
   属**部分解决**：Mixin refmap/@Shadow 声明名、反射字符串、包搬迁后仍不存在的成员、语义漂移、
   以及真实客户端端到端验证，全部**仍未解决**。
3. **JDK 主版本本身在跳**（8→16→17→21→25），进程内跨大版本不现实。
4. **未在真实 Minecraft 客户端里跑通端到端**（需要完整游戏 + Fabric 启动链）。
   26.x 在本机连加载都不可能：本机只有 JDK 17/21，实测 26.1 `com/mojang/blaze3d/Blaze3D.class`
   的 class major = 69（需 Java 25），JDK 21 直接抛 `UnsupportedClassVersionError`。
   demo/ 用的是等价最小复现（同样的 JVMS 机制、同样的 NoSuchMethodError），
   14 mod 的量化是离线字节码静态判定 —— 它证明"能解析/不能解析"，不证明"跑起来行为正确"。
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

*数据来源：GitHub API（2026-11-14）取仓库健康度；minecraft.wiki 取混淆时间线；
本机 client jar / intermediary jar / ProGuard 映射取 API 流失；JLS/JVMS SE21 与 JEP 451/457/484 原文取 JVM 层约束；
Modrinth 官方 API 取 mod 样本与"逐版本构建"事实；§8 的对齐率、引用归因与 Mixin 计数均为本机实测
（官方 ProGuard 映射 × Fabric intermediary × 26.1 client jar × 14 个 Modrinth mod 字节码，2026-11-14）。
§4 / §8 的 4068 条统一口径与 91 条 `com/mojang/` 独立库豁免，来自 2026-11-14 二次修正后的
四条流水线实跑（`/tmp/mcport-work-{self2,fwd2,back2,26b}/out/`），`data/` 内 CSV 已同步重生成。*