# §18 版本能力契约 / 出货闸门：聚合口径 / 合规 / 踩坑

本文件只含**纯聚合计数与口径说明**。`tools/capability.py` 运行时才读使用者自备的
`decl-*.tsv` / `map-*.tsv` / `bridge-*.tsv`、loader plan JSON、LinkCheck 工单 JSON、
stringsurface / bridgegen `stats.json`；`gate.json` / `map-audit.csv` / `surface-diff.csv` /
`triage.tsv` / `stats.json` / `capability-<version>.tsv` 只写 `--out-dir`，
**不进仓库、不进发布包**。仓库与发布包不含任何 Mojang client jar、官方 ProGuard 映射、
第三方 mod 字节码，也不含逐条符号表或完整能力清单。

## 输入与输出

| 文件 | 内容 |
|---|---|
| `--spec` | schema=1，versions[] / maps[] / plans[] / tickets[] / stats{}；模板 `capability-spec.example.json` 仅路径占位符 |
| `gate.json` | 三档 verdict + 逐条 evidence + contracts / map_audits / surface_diffs（不分发） |
| `map-audit.csv` | 映射双向审计逐行计数（不分发） |
| `surface-diff.csv` | 版本间 API 表面差逐组计数（不分发） |
| `triage.tsv` | 逐条 evidence.reason（不分发） |
| `stats.json` | 分桶计数（不分发） |
| `capability-<version>.tsv` | 仅 `--emit-contract` 产出的完整能力清单（不分发） |

## 口径（本机四版真实声明表 / 三张映射 / 17 份 plan / 50 份工单实测）

* `data/capability-contracts.csv`（4 行）：每行 = 一个目标版本的 C/M/F 去重集合规模 + 确定性
  `capability_digest`（C/M/F 行排序后 SHA-256）。1.20.1 111484 / 1.21.1 127876 /
  1.21.11 155818 / 26.1 161309 行。26.1 为官方去混淆 `deobf`，其余为 intermediary `obf`。
* `data/capability-map-audit.csv`（5 行，22 列）：`strict` 仅在 kind=map 且源/目标 decl
  双向全部直接命中、零逆向碰撞、零歧义时为真。四张严格 map（含 reverse 反演）全部 strict；
  26.x bridge 因含 10737 条 C 行、11 次类身份碰撞、197/265 次成员逆向碰撞、源/目标未命中，
  strict=False 且列 6 条 reason，**永不作为 LinkCheck `--map`**。
* `data/capability-surface-diff.csv`（5 行，24 列）：same / lost / added / renamed /
  mapped_target_absent / sigchg / missing 按 C/M/F 分别计数；`identity_break` 仅在
  26.x bridge 方向为真（类 same 仅 21，renamed 7549）。
* `data/capability-gates.csv`（4 行）：clean=READY(0)、manual=NEEDS_MANUAL(2)、
  poison=UNSUPPORTED(1)、full=UNSUPPORTED(1)；full 共 50 条 evidence =
  10 READY / 12 NEEDS_MANUAL / 28 UNSUPPORTED。

## 三档 verdict（绝不承诺行为等价）

* `READY`（退出码 0）：仅表示静态符号证据齐备且零 SIGCHG/MISSING、零 unresolved 字符串、
  零未审桥候选。不表示能在真实客户端运行，也不表示行为等价。
* `NEEDS_MANUAL`（退出码 2）：存在人工适配缺口；必须逐条看 `triage.tsv`。
* `UNSUPPORTED`（退出码 1）：证据不足或计划非法（PLAN_ONLY 未符号复测 / 26.x startup agent /
  把 26.x bridge 当 LinkCheck `--map` / deobf 缺身份桥 / 工单标量不自洽 / 输入错误）。

## 易混口径与踩坑

1. `strict map` 的 reverse 允许（无 C 行、无歧义时互换 old/new 名）；26.x bridge 含 C 行，
   `reverse_map` 必须直接拒绝，否则会把命名空间身份桥误用为逐成员改名表。
2. `surface_diff` 的 `*_sigchg` 是「同名不同描述符」，`*_missing` 是「同名也消失」，
   两者都属**静态需人工**，不可相减、不可并入 `renamed` 洗白。
3. `map_audit` 的 `m_dst_hit=40754 / 57248`（71.2%）是 bridge 经 C 行换 owner + 描述符替换后的
   目标直接命中率，不是静态可解析率，更不是能通过率。
4. 工单解析必须放宽 `<init>` / `<clinit>`：50 份真实工单 14584 条引用若按普通标识符规则
   会误判构造器为坏格式；`gate_tickets` 同时校验 details 数组长度与 MOD 标量一致性。
5. `surface_diff` 必须一次性预建 `(owner,name)` 索引集合；在循环内重建全量表会超时。
6. loader plan 的 `AUTO` 只在有 `check` 且 `rc=0`、零 sigchg/missing 时才升 READY；
   `PLAN_ONLY` 一律 UNSUPPORTED（未符号复测不得发启动脚本）。
7. `claim_policy` 固定为 `static-evidence-only; no runtime claim`；`assert_no_claims` 自检
   禁止 verdict 越界与承诺词，失败直接抛异常。
* 自包含回归 `tools/test_capability.py` 156 断言，零外部数据；真实实测来源见 REPORT §18.7。
