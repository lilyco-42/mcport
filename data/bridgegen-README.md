# SIGCHG 人工桥工作台（bridgegen）—— 数据说明

`data/bridgegen-summary.csv` 只是**纯聚合数字**，来自 `tools/bridgegen.py` 在 8 份本机
LinkCheck 工单（4 个热门 mod × 2 个目标版本，均为 §15 重映射/类迁移复测后的票）+ 两张目标
声明表 + 8 个已重映射 mod jar 上的实跑（2026-11-15，REPORT.md §16）。仓库与发布包**不含**
任何 Mojang client jar 字节、官方 ProGuard 映射、intermediary jar、完整 `bridge-*.tsv`、
第三方 mod 字节码或 `callkind.tsv` / `triage.tsv` / `adapters/*.java` 运行时产物；
后者只写进调用方 `--out-dir` 指定的目录，从不入库。

## 输入（全部自备，运行时读）

| 输入 | 形态 | 来源 |
| --- | --- | --- |
| `--spec` JSON | `{schema:1, targets:[{version, decl, tickets[], jars[] 或 callkind}]}`，见 `bridgegen-spec.example.json` | 调用方 |
| 目标声明表 `decl-<ver>.tsv` | `C/S/M/F` 行；`M/F` 为 `owner/name/desc` | `tools/mkdecl.py` 从自备 client jar 生成 |
| 工单 `*.json` | `details.SIGCHG[]` / `details.MISSING[]` 的 `owner.name+desc  # 注释` | `LinkCheck --json` |
| 已重映射 mod jar | zip；用于恢复每条 Methodref 的 invoke 形态 | 调用方自备，脚本只读 |
| `--classes` | 含 `mcport/CallKind.class` 的编译目录 | `javac -nowarn -cp "lib/*" -d build java/mcport/*.java` |

## 输出（写到 `--out-dir/<version>/`）

* `callkind.tsv`：4 列 `owner/name/desc/kind`，kind = static / virtual / interface / special / mixed / other；
  由 `java/mcport/CallKind.java` 从字节码直接恢复，补 LinkCheck 工单丢掉的 invoke opcode 维度。
* `triage.tsv`：每条工单引用的分类与拒绝原因，按 ref 归并前后可审计。
* `bridge-candidates.tsv`：**仅供人工审阅**的 HostBridge 6 列候选规则，文件头明确 `never auto-load`。
* `adapters/*.java`：可编译但方法体一律 `throw new UnsupportedOperationException("MCPORT_HUMAN_REVIEW_REQUIRED ...")` 的骨架；
  旧参数如何变成新调用是语义，工具不代写。
* `stats.json` / 顶层 `summary.csv`：分版本计数与拒绝原因；`auto_fixed=0` 是硬编码断言。
* `bridge-rules.tsv`：**只有显式加 `--emit-rules` 才写**，内容与候选表相同，表示人已确认并自行负责加载。

## 判据链（任一步不过就 fail-loud 拒绝，绝不静默猜）

1. **恢复 opcode**：LinkCheck 工单只保留 JVMS §5.4.3 的 owner.name+desc 三元组，
   不含 INVOKESTATIC / INVOKEVIRTUAL / INVOKEINTERFACE / INVOKESPECIAL；HostBridge 6 列规则必须区分 virtual/static，
   猜错会让解析期抛 `IncompatibleClassChangeError`。mixed / interface / special / 缺 opcode 一律拒绝。
2. **目标候选**：`Decl` 的 M 与 F **分表**，镜像 `LinkCheck` 的父类链 + 接口 BFS 找同名成员；
   字段、构造、无候选、歧义一律拒绝（字段和方法可同名，不能混表）。
3. **转换判定**：只认 identity / JLS 5.1.2 数值 widening / int-family / 旧 void 丢弃目标返回值；
   引用类型、窄化、反向 widening、参数个数变化都拒绝。数值 widening 与 void 丢弃仍会改变精度/ Observable 行为，
   **只标 SKELETON_MECHANICAL_UNSAFE，绝不算自动修复**。
4. **去重**：同一缺失符号出现在多个 mod 工单时按 `(owner,name,desc,newDesc,kind)` 去重，
   计 `duplicate_candidates`；否则 HostBridge 会为同 owner 注入重复签名导致 VerifyError。
5. **零自动修复**：`--emit-rules` 之外不产可加载规则；骨架一律抛异常；`stats.auto_fixed=0`。

## 数字（`bridgegen-summary.csv`，17 列）

| 目标版本 | total | SIGCHG | MISSING | 唯一候选规则 | 不安全骨架引用 | 语义拒绝 | opcode 拒绝 | 构造 | 字段 | 歧义 | 无目标 | 重复 | auto_fixed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.21.11 | 290 | 101 | 189 | 2 | 3 | 51 | 28 | 18 | 37 | 0 | 153 | 1 | 0 |
| 26.1 | 312 | 78 | 234 | 2 | 3 | 30 | 30 | 16 | 34 | 5 | 194 | 1 | 0 |
| **合计** | **602** | **179** | **423** | **4** | **6** | **81** | **58** | **34** | **71** | **5** | **347** | **2** | **0** |

4 条唯一候选：`class_1041.method_4495()D` → `()I`（i2d）、
`class_1144.method_4873(... )V` → 有返回值（pop）、
`com/mojang/blaze3d/platform/Window.getGuiScale()D` → `()I`（i2d）、
`net/minecraft/client/sounds/SoundManager.play(...)V` → 有返回值（pop）。
其中 6 条不安全骨架引用去重成 4 条规则（各版本 3 条引用 / 2 条规则 / 1 条重复）；
它们只是**可审计的人工起点**，任何一条都不构成行为等价。

三处易混口径：① 153 / 194 是 `REJECT_NO_TARGET`（MISSING 在新声明表找不到同名成员），
不是 `REJECT_UNPARSED`（两版本均为 0）；旧版 16 列表头曾被误读，修复后 17 列由
`csv.DictReader` 逐列对齐断言。② 骨架引用数 3+3 是 triage 行，规则数 2+2 是去重后规则。
③ 179 / 423 是 §15 复测后的工单桶，不是 Round 2 的 173 / 477。

## 复现（自备制品，脚本不下载不入库）

```bash
python3 tools/test_bridgegen.py                 # 61 条自包含断言（合成 decl/工单/callkind）
javac -nowarn -cp "lib/*" -d build java/mcport/*.java
python3 tools/bridgegen.py --spec /work/spec.json --out-dir /work/gen \
  --classes build --java java
# 人工逐条审阅候选与 adapter 骨架后，才考虑显式 --emit-rules
```

## 踩坑（真事，均已修）

* 第一版方法正则 `(\(.*\))$` 要求描述符以右括号结尾，漏掉 `()V` / `(I)I` 的返回类型，
  179 条 SIGCHG 全被误判无候选；必须 `^(.+?)\.([^.(]+)(\(.*\).*)$` 且字段单独一支。
* `Decl` 初版把 M/F 行放进同一张表，真实 decl 里 `class_8685.comp_1626` 同时是方法和字段，
  被误判歧义；修成 M/F 分表后 602 条 triage 只有这一条从 REJECT_AMBIGUOUS 变为 REJECT_SEMANTIC_CONVERSION。
* 同一符号在 2 个 mod 票里出现，旧版生成 6 条规则、2 个 adapter 各含重复 public static 方法；
  去重后 4 条唯一规则，且 `adapters_for` 再加一道重复方法断言。
* `param_conv` 用 `WIDEN.get(old,set())` 才不漏 B/S/C 的 int-family；`return_conv` 方向写反
  会把 target double 到 legacy float 的窄化误当 widening，重写并加注释明确只认 identity / widening。
* `CallKind.java` 的 `--in` / `--out` 用 `a[++i]` 无边界检查，缺值会数组越界；已补显式异常。
* 发布脚本常见坑：JS 模板字符串内嵌 Markdown 反引号会编译失败；精确锚点替换必须先 dry-run 校验 `count=1`，
  缩进逐字不符会整批不落盘；`String.replace(anchor, text)` 会把 text 里的
  `` $` `` 当特殊替换模式（ REPORT 曾因此膨胀 4 倍），replacement 必须写成函数 `() => text`。

## 边界

**零自动修复**：`auto_fixed=0`，4 条候选也只是抛异常骨架，不是任何 mod 的补丁。
§15 复测后 8 份工单仍为 179 SIGCHG + 423 MISSING 需人工；语义漂移（§13）无法被静态工具
彻底判定，Mixin refmap / `@Shadow` 声明名、反射字符串、真实客户端 / Fabric / LWJGL 端到端、
26.x 需 JDK 25 全都没被本章收窄。「全平台全版本任意 mod 都能跑」仍不可达。
