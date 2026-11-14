# 热门 mod 转移测量（4 个新增样本，1.21.1 Fabric）

输入为从 Modrinth 下载的 4 个真实 mod 的 1.21.1 Fabric 版本 jar，**仅在本机
`/tmp/mc/mods/hot/` 用于静态链接测量，不在本仓库内、也不对外分发**。

| 目标版本 | 转移前需人工 | 转移后需人工 | 说明 |
| --- | --- | --- | --- |
| 1.21.11 | 329 / 1162 | 319 / 1162 | 常规版本增益很小 |
| 26.1 | 1160 / 1166 | 331 / 1162 | 官方去混淆断代，建桥后 ≈0% → 60–74% |

`before-*.csv` / `after-*.csv` 是逐 mod 汇总；`*.json` 是逐条符号
（RESOLVE / RENAME / SIGCHG / MISSING / EXTERNAL）修复工单，由
`LinkCheck --json` 导出，供人工逐条修复。**这些工单是待办，不是已修复**。
`fabric-language-kotlin` 为纯 Kotlin 运行时库，0 条游戏引用，无需转移。

许可：ImmediatelyFast / YACL = LGPL-3.0-or-later，
fabric-language-kotlin = Apache-2.0，Xaero's Minimap = All-Rights-Reserved。
