# Third-party notices / 第三方组件声明

## ASM 9.9 (BSD-3-Clause)

本仓库 `lib/*.jar` 与 `demo/libs/*.jar` 含 ASM 9.9 二进制，来源
https://asm.ow2.io/ ，许可原文 https://asm.ow2.io/license.html ：

> ASM: a very small and fast Java bytecode manipulation framework
> Copyright (c) 2000-2011 INRIA, France Telecom
> All rights reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
> 1. Redistributions of source code must retain the above copyright notice,
>    this list of conditions and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright notice,
>    this list of conditions and the following disclaimer in the documentation
>    and/or other materials provided with the distribution.
> 3. Neither the name of the copyright holders nor the names of its
>    contributors may be used to endorse or promote products derived from
>    this software without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
> AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
> IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
> ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
> LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
> CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
> SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
> INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
> CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
> ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
> POSSIBILITY OF SUCH DAMAGE.

## 未随本仓库分发的第三方材料

* **Minecraft client jar / intermediary jar / Mojang 官方 ProGuard 映射**：
  见 `data/NOTICE-mappings.md`。官方映射禁止「完整且未修改地再分发」，
  本仓库只保留聚合测量 CSV 与统计 JSON，不含任何映射表。§13 的 `BodyHash`
  中间产物 `body-*.tsv` 同理只留在本地工作目录，`data/` 只含
  `drift-summary.csv` 这类纯聚合数字与匿名口径。
* **真实 Minecraft 26.1 游戏类字节**：`demo/real26/` 的脚本只在运行时从使用者自备的
  `MC_26_1_JAR` 抽取**一个** `com/mojang/blaze3d/GpuOutOfMemoryException.class` 到被
  `.gitignore` 忽略的 `demo/build/real26/`；本仓库、Git 历史与分发包均不含任何 Mojang 类字节，
  亦不随包提供 26.1 client jar。
* **装载编排机 §14 的输入**：`tools/loader.py` 只在运行时读使用者自备的 client jar、
  `decl-*.tsv` / `map-*.tsv` / `bridge-*.tsv` 与 mod jar；`tools/test_loader.py` 用 tempfile
  合成等价假输入。两者都不下载、不复制、不内嵌 Mojang 类字节、官方映射或第三方 mod 字节码；
  生成的 plan / 工单只留在 `--out` / `--tickets` 指定目录。
* **严格 C 行迁移 §15 的输入与产物**：`tools/relocate.py` 只在运行时读调用方自备的
  `decl-*.tsv` 与 LinkCheck 工单 JSON；`supplement.tsv` / `accepted.tsv` / `stats.json` /
  `summary.csv` 只写进 `--out-dir`，不下载、不复制、不内嵌 Mojang 类字节、官方映射或第三方
  mod 字节码。`tools/test_relocate.py` 只合成等价假输入。`data/relocate-summary.csv` 与
  `data/relocate-README.md` 仅含聚合数字与口径，`data/relocate-spec.example.json` 仅含路径占位符。
* **人工桥工作台 §16 的输入与产物**：`tools/bridgegen.py` 只在运行时读调用方自备的
  `decl-*.tsv`、LinkCheck 工单 JSON、已重映射 mod jar 与 `CallKind.class`；`callkind.tsv` /
  `triage.tsv` / `bridge-candidates.tsv` / `adapters/*.java` / `stats.json` / `summary.csv`
  只写进 `--out-dir`，不下载、不复制、不内嵌 Mojang 类字节、官方映射或第三方 mod 字节码。
  `tools/test_bridgegen.py` 只合成等价假输入。`data/bridgegen-summary.csv` 与
  `data/bridgegen-README.md` 仅含聚合数字与口径，`data/bridgegen-spec.example.json` 仅路径占位符。
 * **字符串表面 §17 的输入与产物**：`tools/stringsurface.py` 只在运行时读调用方自备的
   `decl-*.tsv` / `map-*.tsv` 与已重映射 mod jar；`triage.tsv` / `stats.json` /
   `fixed/*.jar` / `summary.csv` 只写进 `--out-dir`，不下载、不复制、不内嵌 Mojang 类字节、
   官方映射或第三方 mod 字节码。`tools/test_stringsurface.py` 只合成等价假输入。
   `data/stringsurface-summary.csv` / `stringsurface-README.md` 仅聚合数字与口径，
   `data/stringsurface-spec.example.json` 仅路径占位符。
* **能力契约 / 出货闸门 §18 的输入与产物**：`tools/capability.py` 只在运行时读调用方自备的
  `decl-*.tsv` / `map-*.tsv` / `bridge-*.tsv`、loader plan JSON、LinkCheck 工单 JSON、
  stringsurface / bridgegen `stats.json`；`gate.json` / `map-audit.csv` / `surface-diff.csv` /
  `triage.tsv` / `stats.json` / `capability-<version>.tsv` 只写进 `--out-dir`，不下载、
  不复制、不内嵌 Mojang 类字节、官方映射或第三方 mod 字节码。
  `tools/test_capability.py` 只合成等价假输入。`data/capability-*.csv` 与
  `data/capability-README.md` 仅含聚合数字与口径，`data/capability-spec.example.json`
  仅路径占位符。

* **启动期闸门 §19 / §20 / §21 的输入与产物**：`java/mcport/LinkGate.java` 只读调用方自备的 mod jar 与 contract TSV，不下载、不复制、不内嵌 Mojang 类字节或第三方 mod 字节码；`demo/gate/run.sh` 里 `build/stubapi/` 的 `GlStateManager.java` 只是按签名手写的合成编译占位（注释明确 NOT Mojang code or bytes），不源自也不包含 Mojang 源码或类字节。`tools/linkgate_contract.py` 只读仓库内已有的 LinkCheck 工单 JSON 测量结果（计数与符号名）生成契约；完整契约、合成 stub 与任何 mod jar 都只写 `--out-dir` / `demo/gate/build/`，不进仓库与发布包。`data/linkgate-summary.csv` / `linkgate-README.md` / `linkgate-spec.example.json` 只含聚合数字、口径与路径占位符。§20 新增的 `demo/gate/contract-*.tsv` 仅含手写合成符号（或 64 位假 digest）与版本头，不含真实完整契约、Mojang 字节或第三方 mod 字节码；`demo/gate/build/` 中的 jar / 契约均为编译期临时产物，按 `.gitignore` 排除。

* **契约完整性与覆盖率审计 §21 的输入与产物**：`tools/contract_audit.py` 只读取调用方自备的 canonical contract TSV、LinkCheck 工单 JSON 与 mod jar，不下载、不复制、不内嵌 Mojang 类字节、官方映射、完整契约或第三方 mod 字节码；`tools/capability.py` 的严格 `parse_ref` 只解析工单里的符号文本。`contract_audit.json` / `contract_audit.csv` / 完整契约 / stub jar 均只写调用方 `--out` / `--summary` / `demo/gate/build/`，按 `.gitignore` 排除。`data/contract-audit-summary.csv` / `contract-audit-README.md` / `contract-audit-spec.example.json` 只含聚合数字、口径与路径占位符。

* **热门 Fabric mod 二进制**（Sodium / Iris / ImmediatelyFast / YACL /
  Xaero's Minimap / fabric-language-kotlin 等）：仅在本机 `/tmp` 下用于
  静态链接测量，**未复制进本仓库、未上传到任何下载通道**。其许可包含
  PolyForm-Shield-1.0.0、All-Rights-Reserved、LGPL-3.0 等，再分发需各自
  单独取得授权。`data/hotmods/` 只含测量结果（计数与符号名），不含 mod 字节码。
