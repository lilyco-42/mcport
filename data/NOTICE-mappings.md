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

复现 `bash pipeline-26.sh` 时，请自行从 Mojang 官方途径取得：

- `$MAPS/map-<ver>.txt`：官方 ProGuard 映射（默认 `/tmp/mc/`）；
- `$MCJARS/REAL-<ver>.jar`：对应版本 client jar；
- `$MCJARS/inter-<ver>.jar` 或 `i-<ver>.jar`：Fabric intermediary jar。

脚本只读取这些路径，**不会下载、不会复制进本仓库、也不会写进 `data/`**。
ASM 9.9 为 BSD-3-Clause；本工具链不与任何 GPL 项目有代码往来。
