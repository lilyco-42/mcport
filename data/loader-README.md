# 装载编排机实跑聚合（REPORT §14）

`loader-scenarios.csv` 只记录 `tools/loader.py` 在本机对本自备输入的**聚合决策结果**：
P1–P6 是 4 个真实 mod × 5 个真实 client jar / JDK17·21·25 的纯路由决策；
S1–S7 是加 `--check` / `--emit-script` 后的装配与符号预言机场景。
列 `total / resolve / sigchg / missing / ceiling` 来自 LinkCheck 工单的计数，
`ceiling` 即 `autoFixCeiling`（分母含 EXTERNAL，与 `data/hotmods/` 的 `as_is` 口径不同）。

**仓库与发布包不含** client jar、官方 ProGuard 映射、完整 `decl/map/bridge` 表、
热门 mod 二进制或逐条符号工单；本机实验只把符号链接放在 `/tmp/mcport-loader-art/`，
工单与 plan 分别在 `/tmp/loader-tk-s*`、`/tmp/loader-*.json`，均不随包分发。
可复现的零外部数据回归是 `python3 tools/test_loader.py`（49 断言，最终 `RESULT ALL_OK 49`）。

口径坑：26.x bridge 表不能当 `LinkCheck --map`；必须先 `RemapTool` 离线重映射，
再用真实名 `decl-<dst>.tsv` 无 `--map` 复测（`pipeline-26.sh` 口径）。详见 REPORT §14.6。
