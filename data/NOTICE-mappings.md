# 映射数据许可提示 / NOTICE

本目录 **不分发** Mojang 官方 ProGuard 映射（`map-*.txt`）、由它生成的完整
`bridge-*.tsv` / `bridge-26.tsv`，也不分发 Minecraft client jar 或 intermediary jar 的副本。

理由：官方 `map-1.21.11.txt` 头部原文明确写着：

> (c) 2020 Microsoft Corporation. These mappings are provided "as-is" and you bear the
> risk of using them. You may copy and use the mappings for development purposes, but
> **you may not redistribute the mappings complete and unmodified**.
> ... governed by the Minecraft End User License Agreement available at
> https://account.mojang.com/documents/minecraft_eula

因此 `data/` 只保留**测量产物**：LinkCheck 的逐 mod CSV、计数统计 JSON、复现说明。
这些文件只含 `mod,total,resolve,...` 之类的聚合数字与少量符号名样本，
不构成"完整且未修改的映射表"。

§13 的语义漂移测量同理：`BodyHash` 生成的 `body-*.tsv` 含真实成员名与字节码指纹，
属**本地测量中间产物**，一律不分发；`data/drift-summary.csv` 与
`data/drift-README.md` 只含聚合数字与匿名口径，`data/drift-spec.example.json` 只含路径占位符。
匿名样例 `drift-anon-*.tsv` 只有 `sha256(真实身份)[:16]`，本仓库连它也不收录。

复现 `bash pipeline-26.sh` 时，请自行从 Mojang 官方途径取得：

- `$MAPS/map-<ver>.txt`：官方 ProGuard 映射（默认 `/tmp/mc/`）；
- `$MCJARS/REAL-<ver>.jar`：对应版本 client jar；
- `$MCJARS/inter-<ver>.jar` 或 `i-<ver>.jar`：Fabric intermediary jar。

脚本只读取这些路径，**不会下载、不会复制进本仓库、也不会写进 `data/`**。
§14 的 `tools/loader.py` 同理：用 `--artifacts` 指向自备目录，按 `decl-<ver>.tsv` /
`map-<src>-<dst>.tsv` / `bridge-<ver>.tsv` 命名查找，缺表即 `MISSING_ARTIFACT` 拒绝装配；
`tools/test_loader.py` 只合成等价的空/短表做回归，仓库与发布包均不含真实映射行。
§15 的 `tools/relocate.py` 同理：`--spec` 指向自备声明表与工单，输出目录只写
`supplement.tsv`（仅 C 行）/ `accepted.tsv` / `stats.json` / `summary.csv`，
这些都**不进仓库、不进发布包**；`data/` 只保留 `relocate-summary.csv` 这类纯聚合数字、
`relocate-README.md` 口径说明与 `relocate-spec.example.json` 路径占位符。
`tools/test_relocate.py` 用 tempfile 合成等价假输入，仓库与发布包均不含真实映射行。

§16 的 `tools/bridgegen.py` 同理：`--spec` 指向自备声明表、工单与已重映射 mod jar；
`callkind.tsv`（含真实成员名与 opcode）、`triage.tsv`（含逐条符号）、候选规则与
`adapters/*.java` 骨架都**不进仓库、不进发布包**；`data/` 只保留
`bridgegen-summary.csv` 这类纯聚合数字、`bridgegen-README.md` 口径说明与
`bridgegen-spec.example.json` 路径占位符。`tools/test_bridgegen.py` 用 tempfile 合成等价假输入。


§17 的 `tools/stringsurface.py` 同理：`--spec` 指向自备声明表、映射表与 mod jar；
`triage.tsv`（含逐条字符串与类名）、`stats.json`、`fixed/*.jar` 都**不进仓库、不进发布包**；
`data/` 只保留 `stringsurface-summary.csv` 这类纯聚合数字、`stringsurface-README.md` 口径说明
与 `stringsurface-spec.example.json` 路径占位符。`tools/test_stringsurface.py` 用 tempfile 合成等价假输入。
ASM 9.9 为 BSD-3-Clause；本工具链不与任何 GPL 项目有代码往来。
