# LinkGate 启动期能力闸门 / 契约数据说明（REPORT §19 / §20 / §21 / §22 / §23 / §24 / §25）

本节只描述数据格式与可分发聚合，**不携带任何 Mojang client jar、官方 ProGuard 映射、
第三方 mod 二进制或完整契约**。真实契约 `capability-<version>.tsv` 由 `tools/linkgate_contract.py`
在调用方本机从自备 LinkCheck 工单生成，输出到 `--out`，不进仓库与发布包。

## 契约格式

```text
# mcport-linkgate-contract schema=1 version=<version>
# source_tickets=<N> source_sha256=<sha256-of-basename+bytes>
# UNKNOWN refs default to RESOLVE; READY/RESOLVE does NOT mean runtime-compatible.
# owner<TAB>name<TAB>desc<TAB>status
owner<TAB>name<TAB>desc<TAB>RESOLVE|RENAME|SIGCHG|MISSING
```

* `owner` / `name` / `desc` 与 JVM 常量池 `CONSTANT_Methodref` / `Fieldref` / `InterfaceMethodref` 的
  class/NameAndType 解码结果逐字一致（内部类名用 `/`，描述符为 JVM 描述符）。
* `RESOLVE`：静态证据显示目标版本符号可解析；`RENAME`：McPortRuntime 可机械改名；
  `SIGCHG` / `MISSING`：硬阻断，需人工 HostBridge / adapter 显式 opt-in。
* 未知引用按 `RESOLVE` 处理：闸门只拦显式已知坏，不把缺证据误报成坏；但 `RESOLVE` 不证明能跑。
* 同一 `(owner,name,desc)` 在不同工单出现冲突状态 → 生成阶段 `ContractError`、exit 2，不输出半成品。

## 启动参数

```bash
java -javaagent:linkgate.jar \
  -Dmcport.gate=/work/capability-26.1.tsv \
  -Dmcport.gate.modjar=/work/mod.jar \
  -Dmcport.gate.policy=reject|warn \
  -Dmcport.gate.version=26.1 \
  -cp /work/mod.jar:/work/api.jar demo.GateMod
```

* `policy=reject`（默认，未知值 fail-closed 同 reject）：任何 blocker → `System.exit(2)`；
  业务 stdout 为空，stderr 打印逐条 `BLOCKER` 与 `REJECT`。
* `policy=warn`：打印 `WARN: <n>` 与 `PASS` 后照常启动；不是放行证明。
* 参数缺失、契约文件/ mod jar 不存在、class 文件无法解析 → `FAIL` 且 rc=2；
  `policy=warn` 也不豁免；绝不把 premain 异常抛给 HotSpot（实测会 native abort rc=134）。
* §20 加固：给 `-Dmcport.gate.version` 时契约头 `version=` 必须逐字匹配，缺头/错版即 `FAIL`；
  空 jar / 无 `.class` / 非 ZIP 输入、冲突契约状态、冲突/非法头、未知 status 拼写一律 `FAIL`。
* `SIGCHG` 默认硬阻断，即使 `RENAME` 机械可修也不降级；需要人工桥显式 opt-in。

## 分发边界

`data/linkgate-summary.csv` 仅含两版真实工单的聚合计数（工单数、原始引用、忽略的 EXTERNAL、
唯一引用、重复引用、RESOLVE/RENAME/SIGCHG/MISSING 分桶与源摘要）。完整契约与契约里的真实
符号名不进仓库；`demo/gate/contract-*.tsv` 只含最小合成示例（`net/mc/World` / `java/lang/String`）。
聚合由 `tools/linkgate_contract.py --summary` 生成，`source_sha256` 只由 basename+bytes 计算，
不含调用方绝对路径，可重复生成。

## §21 / §22 / §23 / §24 / §25 canonical 审计、统一解析、结构化引用、类级链接与继承层兼容性

`tools/linkgate_contract.py` 生成的是 canonical 契约；旧 `LinkGate` 为向后兼容仍接受双空格、注释行、不足 4 列噪声行等宽松手写契约（即 `demo/gate/contract-*.tsv`）。`tools/contract_audit.py` 反过来要求严格 4 列 TAB、合法 JVMS 描述符、有序唯一键、四行头和合法 `source_sha256`，并逐字节复现工单；因此旧 fixture 被审计器 `CONTRACT_NOT_CANONICAL` 拒绝是设计结果，不代表 `LinkGate` 退化。§21 同时修复 `capability.parse_ref` 的宽松字段描述符切分，避免 `shaderLightDirections[Lorg/joml/Vector3f;` 被拆成永不可能命中常量池的错键；两版聚合计数与 `source_sha256` 不变。审计器路径模板见 `data/contract-audit-spec.example.json`，聚合见 `data/contract-audit-summary.csv`。§22 进一步让 `bridgegen` / `relocate` 委托同一严格 `capability.parse_ref`；契约生成器、审计器与两版 `source_sha256` 均不变，跨工具回归见 `tools/test_parse_unified.py` 与 `data/parse-unified-summary.csv`。§23 新增 `LinkCheck --refs-json` 精确五元组输出与 `tools/refcheck.py` multiset 对账，只对新工单消除源文本歧义；普通 `--json` details 逐字节不变，因此本目录契约、`source_sha256` 与 G25 `regenerated_bytes_match` 不受影响；历史真实工单的 3 / 51 条固有歧义仍按启发式留档，见 `data/refcheck-summary.csv` / `refcheck-README.md`。 §24 新增 `tools/classref.py` 离线类级链接面审计，只读目标 decl、可选 C 改名表与 mod jar 的 `CONSTANT_Class` / 描述符类引用；本目录契约、`source_sha256` 与 G25 `regenerated_bytes_match` 仍不受影响，见 `data/classref-summary.csv` / `classref-README.md`。 §25 的 `tools/hierarchy.py` 只读加补 decl 继承层视图与 S 行目标对账，不改本节任何契约 / 工单 / 类引用聚合字节；见 `data/hierarchy-summary.csv` / `hierarchy-README.md`。
