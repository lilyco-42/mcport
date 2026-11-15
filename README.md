# McPort —— Minecraft 跨版本 mod 兼容工具链

> 一句话：把"这个 mod 能不能在 X 版本跑"从**猜测**变成**可断言的布尔值**，并自动修掉能修的。

**完整调研与量化见 [REPORT.md](REPORT.md)。** 这里只给上手。

## 30 秒证明问题存在（无需下载 Minecraft）

```bash
bash demo/run.sh
```

六个场景（A–F，全部 30 秒内跑完、无需下载 Minecraft）：
1. **A** 源版本跑通：`mod started on MC 1.20.1 -> block=42`
2. **B** 同一份未改动的二进制换到新版本 → `NoSuchMethodError`（这正是线上 mod 崩溃的第一性机制）
3. **C** 加 `-javaagent:mcport-runtime.jar -Dmcport.map=map-v1-v2.tsv` → 又能跑，且 **jar 的 sha1 前后完全一致**（解纯改名 RENAME）
4. **D** 不给映射表 → 依然报错（**fail-loud**，绝不静默猜名）
5. **E** 连签名都改了（SIGCHG）的目标版本：
   - **E1** C 的纯改名路线把名字改对了，但 JVM 按 名+描述符 精确链接，仍报 `getBlockState(III)I` 不存在；
   - **E2** 换成 `-javaagent:build/hostbridge-runtime.jar -Dmcport.bridge=bridge-v2b.tsv` 的**宿主侧兼容桥** → 跑通，mod jar 仍一字节未改；输出 `block=6` 而源版本是 `42`，**故意暴露语义漂移**；
   - **E3** 时序铁律：类已加载后 `retransformClasses` 加方法被 HotSpot 拒绝（`attempted to add a method`），证明桥必须在**启动期 premain、类定义前**注入。
6. **F** 同一份 mod 里同时有纯改名与改签名两类引用（双 agent 组合，REPORT §11）：
   - **F1** 仅 mod 侧 agent → SIGCHG 那条死在 `getBiome`；**F2** 仅宿主桥 → RENAME 那条死在 `getBlock`；
   - **F3** 两个 `-javaagent` 同挂 + `-Dmcport.only=<mod 包>` → `block=42 biome=6`，mod jar 零改动；
   - **F4** agent 顺序反转结果不变。`-Dmcport.only` 是组合纪律：默认改写范围会误改宿主/adapter（§11.4 G7）。

> `demo/run.sh` 用 JDK 17+ 的 `jar --date` 固定条目时间戳，连跑两遍 demo 根目录 5 个发布 jar
> 与 `build/` 下实验 jar 的 sha256 各自完全一致；旧 JDK 无该选项时自动降级（只影响可复现，不影响 A–F 结论）。

## 组件

| 工具 | 干什么 | 命令 |
|---|---|---|
| `LinkCheck` | 预言机：把每条 MC 引用判成 RESOLVE / RENAME / SIGCHG / MISSING | `java -cp "build:$ASM" mcport.LinkCheck --decl decl-X.tsv --mods dir/` |
| `Mapping` | 映射表 + 继承链 BFS 的**唯一实现**，离线工具与 agent 共用 | 被下面两者委托，不单独调用 |
| `RemapTool` | 离线重映射：改名字、描述符、Mixin 注解字符串，输出新 jar | `mcport.RemapTool --map map.tsv --in a.jar --out b.jar` |
| `McPortRuntime` | 启动期 javaagent：不碰磁盘，运行时改写 **mod 侧**引用（解纯改名） | `-javaagent:mcport-runtime.jar` |
| `HostBridge` | 启动期 javaagent：在**宿主类定义前**注入旧签名转发壳，解 SIGCHG；语义交给普通 Java 适配器 | `-javaagent:hostbridge-runtime.jar -Dmcport.bridge=rules.tsv` |
| `MixinRewriter` / `MixinCheck` | 改写 / 统计 Mixin 注解里残留的 intermediary 字符串 | `mcport.MixinCheck remapped/*.jar` |
| `tools/bridge.py` | 官方 ProGuard × Fabric intermediary → `inter → 真实名` 桥 | `python3 tools/bridge.py --proguard map.txt --intermediary i.jar --out b.tsv --tsv` |
| `tools/bridge26.py` | 版本择一 + 目标感知重定位 + S 行父类链，产 26.x 专用表 | `python3 tools/bridge26.py --bridge a.tsv --bridge b.tsv --src-decl s.tsv --dst-decl d.tsv --out m.tsv` |
| `tools/loader.py` | 版本无关的装载编排机：分代 → 选装配路线 → 符号预言机 → fail-loud | `python3 tools/loader.py --repo . --target REAL-X.jar --mod a.jar --check` |
| `tools/test_loader.py` | 零外部数据的 49 断言自包含回归 | `python3 tools/test_loader.py` |
| `tools/relocate.py` | 严格 C 行类迁移补充：把 MISSING 里同名类换包机械解析出来 | `python3 tools/relocate.py --spec spec.json --out-dir gen/` |
| `tools/test_relocate.py` | 零外部数据的 27 断言自包含回归 | `python3 tools/test_relocate.py` |
| `java/mcport/CallKind.java` | 从 mod 字节码恢复 Methodref 的 invoke opcode，补工单缺失维度 | `java -cp `build:lib/*` mcport.CallKind --in a.jar --out kinds.tsv` |
| `tools/bridgegen.py` | SIGCHG/MISSING 人工桥工作台：候选规则 + 抛异常 adapter 骨架，零自动修复 | `python3 tools/bridgegen.py --spec spec.json --out-dir gen/` |
| `tools/test_bridgegen.py` | 零外部数据的 61 断言自包含回归 | `python3 tools/test_bridgegen.py` |
| `tools/stringsurface.py` | LDC / refmap 第二姓名表面精确审计，默认只报告，`--rewrite` 才写 fixed jar | `python3 tools/stringsurface.py --spec spec.json --out-dir gen/` |
| `tools/test_stringsurface.py` | 零外部数据的 78 断言自包含回归 | `python3 tools/test_stringsurface.py` |
| `tools/capability.py` | 四版能力契约 + 严格 map 双向自证 + 26.x bridge 审计 + 三档 fail-loud 出货闸门 | `python3 tools/capability.py --spec spec.json --out-dir gate/` |
| `tools/test_capability.py` | 零外部数据的 158 断言自包含回归 | `python3 tools/test_capability.py` |
| `java/mcport/LinkGate.java` | 启动期 JVM 常量池闸门：真实契约扫 mod，MISSING/SIGCHG 拒启动，零字节修改 | `java -javaagent:linkgate.jar -Dmcport.gate=... -Dmcport.gate.modjar=... Main` |
| `tools/linkgate_contract.py` | 从 LinkCheck 工单生成确定性启动期契约 + 聚合统计，冲突即拒 | `python3 tools/linkgate_contract.py --ticket "data/hotmods/26.1__*.json" --version 26.1 --out gate.tsv --summary s.csv` |
| `tools/test_linkgate_contract.py` | 零外部数据 27 断言 + 可选真实工单聚合的契约回归 | `python3 tools/test_linkgate_contract.py` |
| `tools/refcheck.py` | §23 结构化 `--refs-json` 五元组 × legacy 文本 multiset 对账，启发式分歧 fail-loud | `python3 tools/refcheck.py --refs-json refs.json --ticket legacy.json --golden golden.json` |
| `tools/test_refcheck.py` | 零外部数据的 216 断言自包含回归 | `python3 tools/test_refcheck.py` |

HostBridge 规则表每行 6 列（TAB 分隔）：`owner / oldName / oldDesc / virtual或static / adapterClass / adapterMethod`。
适配器描述符由工具自动推导，人只写普通 Java 语义适配方法；`<init>`/`<clinit>`、重复签名、空表一律 fail-loud。
**它不消灭语义漂移**：E2 的 42 → 6 就是证据，也不覆盖 MISSING（成员/类已删除）。详见 REPORT.md §9；与 `McPortRuntime` 双挂的组合纪律与实测见 §11（demo 场景 F）。

配套：`Verifier`（重映射后结构校验闸门）、`AnnotationDump`（注解格式采样）、
`tools/mkdecl.py`（生成目标版本声明表）、`tools/mkmap.py`（生成常规重映射表）、`tools/report.py`（JSON → 迁移工单）。

> 26.1 起官方完全去混淆、intermediary 变空表，常规 `mkmap.py` 链路失效；
> 用 `bash pipeline-26.sh 1.21.1 26.1 /path/to/mods` 走 §8 的建桥链路。

## 全流程一条命令

```bash
bash pipeline.sh 1.21.1 1.21.11 /path/to/mods

# 26.x 去混淆断代专用（需本地官方 ProGuard 映射，脚本不打包/分发）
bash pipeline-26.sh 1.21.1 26.1 /path/to/mods
```

退出码：`0` = 全部可自动处理；`2` = 还剩 SIGCHG/MISSING 需人工。可直接进 CI。

两条脚本都会自动 `javac` 到 `build/`，全新 clone 无需预构建；第 3 个参数必须是真实存在的 mods 目录，
否则立即 fail-loud。`pipeline-26.sh` 的第 4 个可选参数是「最后一个仍有官方 ProGuard 映射的版本」
（默认 `1.21.11`），不要把版本号写到第 3 位；发布前隔离 smoke 见 `REPORT.md` §10。

## 实测天花板（14 个真实 1.21.1 Fabric mod，4068 条引用）

| 目标 | 自动修复上限（judged = total − EXTERNAL） |
|---|---|
| 1.21.1 自检 | 99.7% |
| 1.21.11（往新搬） | **79.6%** |
| 1.20.1（往旧搬） | **90.6%** |
| 26.1（官方去混淆后，**原样搬运**） | **0.1%**（4068 refs / 3977 judged） |
| 26.1（**§8 建桥重映射后**，静态符号可解析） | **78.7%**（3109 / 3952） |

> 统一口径：补全 `com/mojang/` 游戏类后 14 个 mod 共 4068 refs；
> 91 条 `com/mojang/` 独立库（DataFixerUpper / Brigadier / authlib / logging）不在 client jar，
> 判 EXTERNAL 不计入分母（REPORT.md §5 第 15 条）。`26.1 = 0.0% / 3820` 是早期只收
> `net/minecraft/` 的历史口径，保留在 §1/§4 作对照，不与本表数字相减。
> **78.7% 只代表符号能解析，不代表能跑**：Mixin refmap/@Shadow 声明名、反射字符串、
> 目标版本已删除的成员、语义漂移、真实客户端端到端，仍未彻底解决；§17 已把 Mixin refmap / 反射 LDC 纳入精确审计与 fail-loud，§18 再把四版能力契约与全部证据合成 READY / NEEDS_MANUAL / UNSUPPORTED 出货闸门，但不等于运行期语义已解决（REPORT.md §8.5 / §17）。

**所以："任意版本都有效"不可达。** 常规版本可达的是"~80% 自动 + ~20% 精确列出 + 100% fail-loud"；
26.x 是更低的 78.7% 静态天花板且附带额外硬缺口。
详见 REPORT.md §4、§7（诚实的边界声明）、§8（26.x 攻坚）、§9（宿主侧兼容桥 / SIGCHG）、
§11（双 agent 组合）、§12（JRE 25 × 真实 26.1 类）、§13（真实 jar 语义漂移量化）与
§14（版本无关的装载编排机）、§15（严格 C 行类迁移）与 §16（零自动修复的人工桥工作台）、§17（字符串姓名表面审计）与 §18（版本能力契约 / fail-loud 出货闸门）。

## 可选：真实 26.1 类 × JRE 25（REPORT §12）

`demo/real26/run.sh` 是**独立可选实验**，不属于 A–F，也不改变它们的「30 秒 / JDK 17 / 无需下载 Minecraft」前提。
它需要使用者自备 `MC_26_1_JAR`（26.1 client jar）与 `JAVA25`（JRE 25），或让脚本按固定 sha256
拉取 Temurin JRE 25.0.5；缺前置直接打印 `SKIP` 并返回 0。脚本运行时从 jar 抽取
`com/mojang/blaze3d/GpuOutOfMemoryException.class`（436 B / class major 69），
**仓库与发布包不含该字节**。S0–S11 实测证明：JDK 17 拒绝 major 69、JRE 25 能加载、
无 agent 仍 `NoSuchMethodError`、启动期 `HostBridge` 在真实 major-69 类上注入旧签名后
通过 `-Xverify:all` 全量校验并链接、双 agent 顺序无关且无 JEP 451 动态加载警告、
observer dump 显示只在内存里多出且只多出 `legacyMessage()`、`-Dmcport.only=demo26/LegacyRename`
使宿主类字节保持不变、缺规则表/映射表一律 fail-loud。

```bash
MC_26_1_JAR=/path/to/26.1-client.jar JAVA25=/path/to/jre25/bin/java bash demo/real26/run.sh
```

**不证明** Fabric / 客户端启动、LWJGL/native、Mixin 注入链、任何真实 mod 能跑；
173 条 SIGCHG / 477 条 MISSING、`<init>`、语义漂移与真实客户端端到端仍未解决（REPORT §12.4）。

## 真实 jar 语义漂移量化（REPORT §13）

`java/mcport/BodyHash.java` + `tools/drift_align.py` 在四个真实 client jar
（1.21.1 / 1.21.11 / 26.1 / 26.3）上全量实测：同名同签名方法里
**4.6%–14.2%** 的实现字节码指纹确实变了（可检测下界），
**85.8%–95.4%** 三列指纹全同（静态工具判不干净的区间）。
指纹全同 ≠ 行为相同，指纹不同 ≠ 一定坏掉；§13 只把「检测不出来」精确化，
**不推翻「任意版本绝对不失效不可实现」**，也不给 78.7% 静态可解析率加任何可运行性保证。

```bash
# 自备 client jar 与官方 ProGuard 映射；输入与映射都不进仓库
java -Xmx1g -cp 'build:lib/*' mcport.BodyHash /path/to/REAL-<ver>.jar /work/body-<ver>.tsv
python3 tools/drift_align.py --repo . --spec /work/drift-spec.json --out-dir /work/out
```

`data/drift-summary.csv` 是聚合数字，`data/drift-README.md` 是口径与踩坑，
`data/drift-spec.example.json` 是路径占位符模板。**仓库与发布包不含** `body-*.tsv`、
映射文本或任何 Mojang 字节（见 `data/NOTICE-mappings.md`）。
GH 同类工具（japicmp / revapi / clirr）只比 API 签名、不读方法体，fit < 50%，故本轮自研最小预言机。

## 版本无关的装载编排机（REPORT §14）

`tools/loader.py` 不是 Minecraft 启动器，也不是「任意 mod 都能跑」的万能加载器：
它输入 `(mod jar, 目标 client jar)`，只读 jar 结构与 `version.json` 判 `obf / deobf / non_jvm`，
自动选三条已验证路线——同版本/无游戏引用不挂 agent；混淆期跨版用启动期
`-javaagent:mcport-runtime.jar -Dmcport.map=...`；26.x 断代先 `RemapTool` 离线重映射、
再对真实名声明表无 `--map` 复测、**不挂 agent**——然后跑 `LinkCheck` 写逐条工单，
生成启动包装脚本；缺制品 / Java 不匹配 / native / 异加载器 / 非 JVM / 需人工 / 未 `--check`
一律 `REFUSE ... exit 2`。游戏启动命令由使用者用 `MCPORT_LAUNCH_CMD` 提供。

```bash
python3 tools/test_loader.py   # 零外部数据、零 Mojang 字节、零网络；49 断言
python3 tools/loader.py --repo . --target /path/to/REAL-26.1.jar \
  --mod /path/to/mod.jar --java /path/to/jre25/bin/java \
  --source 1.21.1 --artifacts /path/to/decl-map-bridge \
  --check --tickets /tmp/tickets --out plan.json --emit-script launch.sh
```

本机实跑：5 个真实 client jar（1.20.1 / 1.21.1 / 1.21.11 / 26.1 / 26.3）+ 4 个真实 mod
的 P1–P6 路由与 S1–S7 装配/预言机场景；`RESULT ALL_OK 49`。制品需自备，
仓库与发布包不含 client jar、映射表或 mod 二进制（见 `data/NOTICE-mappings.md`）。
**边界**：不启动 Fabric / 真实客户端，不覆盖 Bedrock、native、Mixin refmap / `@Shadow`、
反射字符串、已删除成员与语义漂移；「全平台全版本任意 mod 都能跑」仍不可达。详见 REPORT §14.7 / §15.6 / §16.6。

## 严格 C 行类迁移补充（REPORT §15）

8 份热门 mod 工单里 173 条 SIGCHG + 477 条 MISSING 仍需人工；§15 只攻其中一类
「老 owner 类整包搬走、同名同描述符成员还在」的 MISSING。`tools/relocate.py`
按三级严格判据（类级唯一同名投票 → 整张 C 行重映射描述符 → 目标直接声明校验）
生成**仅 C 行**的 `supplement.tsv`，再交给 `RemapTool` 真的改字节码，
最后对目标声明表**不带 `--map`** 复测。

```bash
python3 tools/test_relocate.py                            # 27 断言，零外部数据
python3 tools/relocate.py --spec /work/spec.json --out-dir /work/gen
```

本机实跑：1.21.11 生成 4 条 C 行 / 接受 29 条，26.1 生成 1 条 C 行 / 接受 19 条，
**合计 48 条** MISSING → 静态 RESOLVE；另有 6 条诚实转成 SIGCHG，
13 条不同简单名的危险偶合 0 洗白。复测后 8 份工单为 179 SIGCHG + 423 MISSING，
**48 条只是符号可解析候选，不证明行为等价或能跑**。聚合数字见
`data/relocate-summary.csv`，口径与踩坑见 `data/relocate-README.md`，
输入模板见 `data/relocate-spec.example.json`（仅路径占位符）。
关键决策：不改 `LinkCheck`、不新增 RELOCATE 桶（其 `CLS_RENAME` 是死代码），
旧五字段 JSON 完全兼容；详见 REPORT §15.5。

## SIGCHG 人工桥工作台（REPORT §16）

§15 复测后仍有 **179 SIGCHG + 423 MISSING** 需人工。§16 不宣称修好任何一条，而是把
「能不能机械生成 HostBridge 规则」判干净：8 份真实工单共 **602 条引用**，恢复 invoke opcode、
镜像 LinkCheck 父类/接口 BFS、拒绝字段/构造/歧义/引用类型/窄化后，只剩 **4 条唯一候选规则**；
它们仍会改变精度或丢弃返回值，适配器只生成**抛异常骨架**，因此 **auto_fixed=0**。

```bash
python3 tools/test_bridgegen.py                           # 61 断言，零外部数据
javac -nowarn -cp 'lib/*' -d build java/mcport/*.java
python3 tools/bridgegen.py --spec /work/spec.json --out-dir /work/gen --classes build
# 逐条人工审阅后，才考虑显式 --emit-rules；候选表永不自动喂 JVM
```

本机实跑：1.21.11 `290/101/189 → 2 候选规则 / 1 重复`，26.1 `312/78/234 → 2 候选规则 / 1 重复`；
另有 347 条无目标、81 条语义拒绝、58 条 opcode 拒绝、34 条构造、71 条字段、5 条歧义。
聚合数字见 `data/bridgegen-summary.csv`，口径/踩坑见 `data/bridgegen-README.md`，
路径模板见 `data/bridgegen-spec.example.json`。**四条候选不是补丁，不代表行为等价或能跑。**
详见 REPORT §16.6。

## 字符串姓名表面（REPORT §17）

`RemapTool` 原样复制非 `.class` 资源，ASM 不改裸 String，Mixin refmap 与反射字符串是第二盲区。
§17 用 `tools/stringsurface.py` 精确解析 `CONSTANT_String` 与非 assets JSON：8 个真实 jar 共
**7288 次字符串出现**，其中 **70 条可精确改名**、**150 条 fail-loud**（`exit 2`）；
显式 `--rewrite` 只改 6 个真实条目（1 个 refmap 值 + 4 个 LDC `.class` + 1 个 refmap JSON）。
4 个改写 class 的 `javap` / `major 65` / `unzip -t` 全通过，改写前后 `LinkCheck.details` 与
`MixinCheck` 输出逐字节相同——**只改字符串，不改符号链接口径**。

```bash
python3 tools/test_stringsurface.py                            # 78 断言，零外部数据
python3 tools/stringsurface.py --spec /work/spec.json --out-dir /work/audit
python3 tools/stringsurface.py --spec /work/spec.json --out-dir /work/rw --rewrite
```

聚合见 `data/stringsurface-summary.csv`，口径 / 踩坑见 `data/stringsurface-README.md`，
路径模板见 `data/stringsurface-spec.example.json`。**符号改名不证明运行期行为等价、更不证明能跑。**
详见 REPORT §17.6。

## 版本能力契约 / 出货闸门（REPORT §18）

`tools/capability.py` 把四版真实 `decl` 表变成确定性能力清单，再把严格 map 双向自证、
26.x bridge 身份层审计、17 份 loader plan、50 份 LinkCheck 工单（14584 条引用）、
§16 / §17 聚合统计合成三档闸门：`READY`（静态证据齐备且零人工缺口，`rc=0`）、
`NEEDS_MANUAL`（`rc=2`）、`UNSUPPORTED`（`rc=1`）。full 场景 50 条 evidence =
**10 READY / 12 NEEDS_MANUAL / 28 UNSUPPORTED**；clean 场景才 7/7 READY。
26.x bridge 有 11 次类身份碰撞、197/265 次成员逆向碰撞，永远不自动升格为 LinkCheck `--map`；
把 C5 错误计划喂进 poison 场景必得 `UNSUPPORTED`。**`READY` 不表示能在真实客户端运行。**

```bash
python3 tools/test_capability.py                                  # 158 断言，零外部数据
python3 tools/test_linkgate_contract.py                           # 27 断言，零外部数据
python3 tools/capability.py --spec /work/spec.json --out-dir /work/gate
```

聚合见 `data/capability-{contracts,map-audit,surface-diff,gates}.csv`，口径 / 易混项见
`data/capability-README.md`，路径模板见 `data/capability-spec.example.json`。
详见 REPORT §18.6 / §18.9。

## 启动期能力闸门、契约、类级链接面与 decl 继承层审计（REPORT §19 / §20 / §21 / §22 / §23 / §24 / §25）

`LinkGate` 是不改 mod 字节的 `-javaagent`：在 `premain` 用纯 JDK 两遍解析 class 常量池，对照由 `tools/linkgate_contract.py` 从真实 LinkCheck 工单生成的契约，把 `MISSING` / `SIGCHG` 引用在启动前干净拒绝（rc=2、无 native abort）；`RENAME` 只计数，未知引用默认 `RESOLVE`，`warn` 只豁免已知 blocker 不豁免读表失败。§20 把契约 `version` 头绑定到 `-Dmcport.gate.version`，并把空 jar / 冲突状态 / 非法头 / 状态拼写错误全部改为 `FAIL`。两版真实工单各 4 份 / 1190 原始引用 / 1019 唯一引用；26.1 有 68 SIGCHG + 223 MISSING 会阻断。

```bash
bash demo/gate/run.sh                          # 42 场景 210 断言，含真实契约 JVM 阻断、类级链接盲区、decl 继承层对账与 42→6 语义漂移铁证
python3 tools/test_linkgate_contract.py        # 27 断言 + 可选真实工单聚合回归
python3 tools/test_contract_audit.py           # 110 断言，含真实 26.1 工单 canonical 复现
python3 tools/test_parse_unified.py              # 114 断言，三工具严格解析 + 8 真实工单聚合
python3 tools/test_refcheck.py                   # 216 断言，结构化引用对账 + 合成碰撞 + 8 真实工单只读
python3 tools/test_classref.py                   # 225 断言，类级链接面审计 + 常量池 / 描述符 / 5 demo jar 只读
python3 tools/test_hierarchy.py                  # 390 断言，decl 继承层跨工具对账 + 摘要碰撞 + 8 真实工单只读
```

§21 的 `tools/contract_audit.py` 是纯标准库离线审计器：严格校验 canonical 契约头 / 四列 TAB / JVMS 描述符，逐字节复现上游工单，扫描 mod jar 常量池并量化 covered / unknown / unclassified / stale / NEEDS_MANUAL；本轮还修掉 `capability.parse_ref` 的一个真实 SIGCHG 静默放行 bug。

聚合见 `data/linkgate-summary.csv` / `data/contract-audit-summary.csv` / `data/parse-unified-summary.csv` / `data/refcheck-summary.csv` / `data/classref-summary.csv` / `data/hierarchy-summary.csv`，口径见 `data/linkgate-README.md` / `data/contract-audit-README.md` / `data/parse-unified-README.md` / `data/refcheck-README.md` / `data/classref-README.md` / `data/hierarchy-README.md`，路径模板见对应 `*-spec.example.json`。**`PASS` / `COVERAGE_OK` / `CLASSREFS_OK` / `HIERARCHY_OK` 只表示静态链接符号或契约 / 类引用 / 继承层覆盖，不证明能跑或语义一致。**

§22 把 `bridgegen.py` / `relocate.py` 的 `parse_ref` 委托给 `capability.py` 的唯一严格 JVMS §4.3 解析器；对外四元组形状不变，8 份真实工单的 197 / 1 内部分歧归零，源文本固有歧义 3 / 51 仍留档，统一解析不扩大自动修复集合、不证明运行期语义。

§23 让 `LinkCheck --refs-json` 从源头输出精确 `(kind,owner,name,desc,status)` 五元组，旧 `--json` details 逐字节不变；`tools/refcheck.py` 用结构化 multiset 消解合成碰撞里两条同文字段引用的歧义（structured=2 / legacy=2 / ambiguous=2 / resolved=1 / diverged=1、274B 黄金字节一致），并把启发式与真值的分歧如实记入报告。历史真实工单的源文本固有歧义 3 / 51 不追溯改写，仍按启发式留档。**`STRUCTURED_REFS_OK` 只表示引用对账，不表示能跑或语义等价。**
§24 用 `tools/classref.py` 独立补上 `CONSTANT_Class`（JVMS 5.4.3.1）类级链接面：解析 tag 7 数组类、tag 12 / 16 与 field / method 描述符里的对象类，对照目标 decl 与可选 C 改名表，输出 `RESOLVE` / `RENAME` / `MISSING` / `EXTERNAL` / `THIRD_PARTY` / `SELF` 的 fail-loud JSON + 27 列 CSV。G34 用同一 274B 黄金 jar 证明成员级 `resolve=2 / missing=0` 时类级仍可 `MISSING`；`CLASSREFS_OK` / `CLASSREFS_ONLY_OK` 不证明运行期兼容，离线审计不接入 `premain`、不重映射、不改 8 份历史工单字节。**`CLASSREFS_OK` 只表示静态类引用可覆盖，不表示能跑或语义等价。**
§25 用 `tools/hierarchy.py` 把同一份 decl 在 `capability.load_decl`（只认 C 行、摘要不含 S 行）与 `LinkCheck.loadDecl` / `classref.parse_decl`（认 C/S/M/F 全 owner）之间的视图差异、显式父类 / 接口目标缺失 / 环 / 重复冲突 S 行、capability 摘要碰撞全部改为离线 fail-loud：36 列 CSV + JSON + 精确 rc，G40 用 F-only 黄金 decl 证明 capability 视图拒绝而另两工具接受，G39 证明只差 S 行的两份 decl 可拥有同一能力摘要。`HIERARCHY_OK` 只表示静态继承层对账通过，不接入 `premain`、不改任何历史工单 / Java / 映射字节、不证明运行期兼容或语义等价。


## 构建

```bash
mkdir -p build lib
# 需要 ASM 9.9（读 Java 25 / class major 69 必需）
javac -nowarn -cp 'lib/*' -d build java/mcport/*.java   # 含 §13 的 BodyHash
python3 tools/test_loader.py                            # §14 编排机 49 断言回归
python3 tools/test_relocate.py                          # §15 严格迁移 27 断言回归
python3 tools/test_bridgegen.py                         # §16 人工桥工作台 61 断言回归
python3 tools/test_stringsurface.py                     # §17 字符串表面 78 断言回归
python3 tools/test_capability.py                        # §18 出货闸门 158 断言回归
python3 tools/test_linkgate_contract.py                 # §19/§20 启动期契约 27 断言回归
python3 tools/test_contract_audit.py                    # §21 契约完整性与覆盖率 110 断言回归
python3 tools/test_parse_unified.py                      # §22 三工具统一严格解析 114 断言回归
python3 tools/test_refcheck.py                           # §23 结构化引用对账 216 断言回归
python3 tools/test_classref.py                           # §24 类级链接面审计 225 断言回归
python3 tools/test_hierarchy.py                          # §25 decl 继承层对账 390 断言回归
```

> **CI 注意**：若 `LANG`/`LC_ALL` 为空，JDK 用 `ANSI_X3.4-1968` 解码路径，中文目录会让 `javac`
> 误报 `file not found`。三条 `*.sh` 已内置 UTF-8 locale 自愈（REPORT §5 第 16 条）；
> 手动执行上面的裸 `javac` 时请先 `export LANG=C.UTF-8`。

许可提示：ASM 为 BSD-3；本工具链不与任何 GPL 项目（ViaVersion / Weave）有代码往来。
---

## 下载与发布

* 源码仓库：https://github.com/lilyco-42/mcport （MIT）
* 打包分发件：https://lain42.top/downloads/ 内条目 `mcport`，当前版本走 GitHub Release 直链（非 R2 加速），详见 PUBLISHING.md。
* 发布通道说明见 [PUBLISHING.md](PUBLISHING.md)，第三方组件声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
* 热门 mod 转移测量与逐条兼容工单见 [data/hotmods/README.md](data/hotmods/README.md)。
