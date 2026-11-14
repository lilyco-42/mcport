# McPort —— Minecraft 跨版本 mod 兼容工具链

> 一句话：把"这个 mod 能不能在 X 版本跑"从**猜测**变成**可断言的布尔值**，并自动修掉能修的。

**完整调研与量化见 [REPORT.md](REPORT.md)。** 这里只给上手。

## 30 秒证明问题存在（无需下载 Minecraft）

```bash
bash demo/run.sh
```

五个场景（A–E，全部 30 秒内跑完、无需下载 Minecraft）：
1. **A** 源版本跑通：`mod started on MC 1.20.1 -> block=42`
2. **B** 同一份未改动的二进制换到新版本 → `NoSuchMethodError`（这正是线上 mod 崩溃的第一性机制）
3. **C** 加 `-javaagent:mcport-runtime.jar -Dmcport.map=map-v1-v2.tsv` → 又能跑，且 **jar 的 sha1 前后完全一致**（解纯改名 RENAME）
4. **D** 不给映射表 → 依然报错（**fail-loud**，绝不静默猜名）
5. **E** 连签名都改了（SIGCHG）的目标版本：
   - **E1** C 的纯改名路线把名字改对了，但 JVM 按 名+描述符 精确链接，仍报 `getBlockState(III)I` 不存在；
   - **E2** 换成 `-javaagent:build/hostbridge-runtime.jar -Dmcport.bridge=bridge-v2b.tsv` 的**宿主侧兼容桥** → 跑通，mod jar 仍一字节未改；输出 `block=6` 而源版本是 `42`，**故意暴露语义漂移**；
   - **E3** 时序铁律：类已加载后 `retransformClasses` 加方法被 HotSpot 拒绝（`attempted to add a method`），证明桥必须在**启动期 premain、类定义前**注入。

> `demo/run.sh` 用 JDK 17+ 的 `jar --date` 固定条目时间戳，连跑两遍产出的 5 个 jar sha256 完全一致；
> 旧 JDK 无该选项时自动降级（只是为了可复现，不影响 A–E 结论）。

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

HostBridge 规则表每行 6 列（TAB 分隔）：`owner / oldName / oldDesc / virtual或static / adapterClass / adapterMethod`。
适配器描述符由工具自动推导，人只写普通 Java 语义适配方法；`<init>`/`<clinit>`、重复签名、空表一律 fail-loud。
**它不消灭语义漂移**：E2 的 42 → 6 就是证据，也不覆盖 MISSING（成员/类已删除）。详见 REPORT.md §9。

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
> 目标版本已删除的成员、语义漂移、真实客户端端到端，全部未解决（REPORT.md §8.5）。

**所以："任意版本都有效"不可达。** 常规版本可达的是"~80% 自动 + ~20% 精确列出 + 100% fail-loud"；
26.x 是更低的 78.7% 静态天花板且附带额外硬缺口。
详见 REPORT.md §4、§7（诚实的边界声明）、§8（26.x 攻坚）与 §9（宿主侧兼容桥 / SIGCHG）。

## 构建

```bash
mkdir -p build lib
# 需要 ASM 9.9（读 Java 25 / class major 69 必需）
javac -nowarn -cp 'lib/*' -d build java/mcport/*.java
```

> **CI 注意**：若 `LANG`/`LC_ALL` 为空，JDK 用 `ANSI_X3.4-1968` 解码路径，中文目录会让 `javac`
> 误报 `file not found`。三条 `*.sh` 已内置 UTF-8 locale 自愈（REPORT §5 第 16 条）；
> 手动执行上面的裸 `javac` 时请先 `export LANG=C.UTF-8`。

许可提示：ASM 为 BSD-3；本工具链不与任何 GPL 项目（ViaVersion / Weave）有代码往来。
---

## 下载与发布

* 源码仓库：https://github.com/lilyco-42/mcport （MIT）
* 打包分发件：https://lain42.top/downloads/ 内条目 `mcport`，经 Cloudflare R2 签名票据通道加速下载。
* 发布通道说明见 [PUBLISHING.md](PUBLISHING.md)，第三方组件声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
* 热门 mod 转移测量与逐条兼容工单见 [data/hotmods/README.md](data/hotmods/README.md)。
