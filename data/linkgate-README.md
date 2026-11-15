# LinkGate 启动期能力闸门 / 契约数据说明（REPORT §19 / §20）

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
