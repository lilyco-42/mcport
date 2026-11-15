# 结构化引用对账 / Structured refs reconciliation（REPORT §23 / §24）

0.2.4 不再只靠 `LinkCheck.toString()` 的 `owner + "." + name + desc` 无分隔符文本猜 `(name,desc)`。
`java/mcport/LinkCheck.java` 新增 `--refs-json <path>`，在 `classify()` 阶段直接把常量池里读到的
精确 `(kind,owner,name,desc,status)` 五元组按字典序写成确定性 JSON；旧 `--json` 的 `details`
文本逐字节不变（保护 8 份真实工单、`source_sha256`、canonical 契约与 G25 `regenerated_bytes_match`）。

## 文件

* `data/refcheck-legacy-golden.json`：未改 LinkCheck 用合成 `demo/gate/build/refmod.jar` 生成的 274B 旧 `--json` 黄金字节；G30 用 `cmp` 证明改动后普通路径逐字节相同。
* `demo/gate/refcheck-decl.tsv`：两行声明，故意构造 `net/minecraft/Api.BLEND:Lnet/minecraft/Thing;` 与 `net/minecraft/Api.B:LENDLnet/minecraft/Thing;` 两个不同 Fieldref，legacy 文本都渲染成 `net/minecraft/Api.BLENDLnet/minecraft/Thing;`。
* `demo/gate/src/refapi/**`、`demo/gate/src/refmod/**`：纯手写合成 Java，无 Mojang 字节。
* `tools/refcheck.py`：纯标准库离线审计器，把 `--refs-json` 精确五元组与 `--json` legacy 文本做 multiset 对账，严格枚举每条文本的合法切分，只用结构化池消解歧义；对启发式与真值不一致的行记 `HEURISTIC_DIVERGED` 并如实报告，成功 stdout 强制带 `does NOT mean runtime-compatible; exact refs do NOT prove semantic equivalence`。
* `tools/test_refcheck.py`：216 条自包含断言，只读本仓库 8 份 `data/hotmods/*.json` 与合成 fixture，零网络、零游戏 jar、零官方映射、零第三方 mod 二进制。
* `data/refcheck-summary.csv` / `data/refcheck-spec.example.json`：聚合数字与路径占位符。

## 实测

合成碰撞 fixture：`structured=2 legacy=2 ambiguous=2 resolved=1 diverged=1 golden_bytes_match=true`。
两条相同 legacy 文本都歧义，结构化 multiset 把一条判为 `B / LENDLnet/minecraft/Thing;`、另一条判为
`BLEND / Lnet/minecraft/Thing;`；`capability.parse_ref` 取最长合法成员名的启发式会把两条都猜成 `BLEND`，
审计器如实记 1 条 `heuristic_diverged_lines`，不假装启发式正确。

旧真实工单的源文本固有歧义（1.21.11 = 3、26.1 = 51）**仍留档**：这些工单是历史字节，没有对应的
`--refs-json`，0.2.4 不能追溯式消解，只能保持字节不变、继续按启发式留档。新工单从 0.2.4 起
可用 `--refs-json` 从源头消除歧义。

## 边界

`STRUCTURED_REFS_OK` 只表示结构化五元组与 legacy 文本 multiset 对得上、且黄金字节一致；
它不运行游戏、不新增 JVM 层加载器、不重映射 mod、不扩大 `LinkGate` 的 `PASS` 集合、
不证明同名同签名语义等价（demo G15 的 42→6 仍是铁证）。179 SIGCHG + 423 MISSING 人工缺口、
真实客户端 / Fabric / LWJGL / Mixin 端到端、反射 / 配置 / 资源字符串运行期取值均不变。

§24 用同一 274B 黄金 jar 证明成员级 `resolve=2 / missing=0` 时类级仍可能 `MISSING`；本目录结构化五元组与历史歧义口径不变，见 `data/classref-summary.csv` / `classref-README.md`。
