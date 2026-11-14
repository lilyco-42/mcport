# McPort —— Minecraft 跨版本 mod 兼容工具链

> 一句话：把"这个 mod 能不能在 X 版本跑"从**猜测**变成**可断言的布尔值**，并自动修掉能修的。

**完整调研与量化见 [REPORT.md](REPORT.md)。** 这里只给上手。

## 30 秒证明问题存在（无需下载 Minecraft）

```bash
bash demo/run.sh
```

四个场景：
1. **A** 源版本跑通：`mod started on MC 1.20.1 -> block=42`
2. **B** 同一份未改动的二进制换到新版本 → `NoSuchMethodError`（这正是线上 mod 崩溃的第一性机制）
3. **C** 加 `-javaagent:mcport-runtime.jar -Dmcport.map=map-v1-v2.tsv` → 又能跑，且 **jar 的 sha1 前后完全一致**
4. **D** 不给映射表 → 依然报错（**fail-loud**，绝不静默猜名）

## 组件

| 工具 | 干什么 | 命令 |
|---|---|---|
| `LinkCheck` | 预言机：把每条 MC 引用判成 RESOLVE / RENAME / SIGCHG / MISSING | `java -cp "build:$ASM" mcport.LinkCheck --decl decl-X.tsv --mods dir/` |
| `Mapping` | 映射表 + 继承链 BFS 的**唯一实现**，离线工具与 agent 共用 | 被下面两者委托，不单独调用 |
| `RemapTool` | 离线重映射：改名字、描述符、Mixin 注解字符串，输出新 jar | `mcport.RemapTool --map map.tsv --in a.jar --out b.jar` |
| `McPortRuntime` | 启动期 javaagent：不碰磁盘，运行时改写 mod 字节码 | `-javaagent:mcport-runtime.jar` |
| `MixinRewriter` / `MixinCheck` | 改写 / 统计 Mixin 注解里残留的 intermediary 字符串 | `mcport.MixinCheck remapped/*.jar` |
| `tools/bridge.py` | 官方 ProGuard × Fabric intermediary → `inter → 真实名` 桥 | `python3 tools/bridge.py --proguard map.txt --intermediary i.jar --out b.tsv --tsv` |
| `tools/bridge26.py` | 版本择一 + 目标感知重定位 + S 行父类链，产 26.x 专用表 | `python3 tools/bridge26.py --bridge a.tsv --bridge b.tsv --src-decl s.tsv --dst-decl d.tsv --out m.tsv` |

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
详见 REPORT.md §4、§7（诚实的边界声明）与 §8（26.x 攻坚）。

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
