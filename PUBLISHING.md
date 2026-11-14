# 发布通道 / Publishing

本仓库是 McPort 工具链的**源码与测量产物**，采用 MIT 许可（见 `LICENSE`）。

| 内容 | 位置 |
| --- | --- |
| 源码、文档、测量数据 | GitHub: https://github.com/lilyco-42/mcport |
| 打包分发件 `mcport-0.1.4-dist.tar.gz` | Cloudflare R2 桶 `lain42-dl`，key `downloads/mcport/0.1.4/mcport-0.1.4-dist.tar.gz` |
| 下载入口 | https://lain42.top/downloads/ → 条目 `mcport`（经 `dl.lilyco42.top` 的 R2 签名票据通道加速，遵循站点积分规则） |
| R2 目录 | `catalog/downloads.json`（Worker `lain42-dl-gate` 运行时读取，60s 缓存） |

## 可复现性

* `bash demo/run.sh` 在本机**六场景**全绿（A 跑通 / B `NoSuchMethodError` /
  C 加 `-javaagent` 后同一份未改动 mod jar 救活 / D 无映射表 fail-loud /
  E1 纯改名在 SIGCHG 上失效、E2 宿主侧桥救活且显式暴露 42→6 语义漂移、
  E3 HotSpot 拒绝已加载类新增方法 / F 双 agent 组合同时修 RENAME 与 SIGCHG：
  单 agent 各修一半、双挂且顺序无关、mod jar 零改动，见 REPORT §11）。
* `bash demo/real26/run.sh` 是可选的 S0–S11 实验（REPORT §12）：需自备 26.1 client jar 与 JRE 25，
  缺前置打印 `SKIP` 返回 0；发布包不含任何 Mojang 字节。已在 Temurin JRE 25.0.5 上全绿。
* demo 用 `jar --date` 固定条目时间戳，连跑两遍各 jar（含场景 F 实验 jar）sha256 一致。
* 发布前在隔离目录模拟全新 clone：两条流水线全链路实跑（`pipeline.sh` 8 步 / `pipeline-26.sh` 9 步），
  分别得到 319 / 331 条需人工引用并按约定 `exit 2`；`pipeline.sh` 已内置编译，不再依赖预先 `build/`。
* `bash pipeline.sh <srcVer> <dstVer> <modsDir>` 与 `bash pipeline-26.sh` 需要
  自备对应版本的 client jar、intermediary jar 与官方 ProGuard 映射，脚本不会
  下载、也不会把它们写入仓库。
* §13 的 `java/mcport/BodyHash.java` + `tools/drift_align.py` 在本机四版真实 client jar
  全量实跑，参数化版重跑与首次 `drift-summary.json` 逐字段一致；`data/drift-summary.csv`
  是可分发的聚合结果，`body-*.tsv` / 映射 / client jar 均不随包提供。

## 边界（务必阅读 REPORT.md §7 / §12 / §13）

静态符号可解析率 **不等于** 能在真实客户端运行。同名同签名语义漂移无法被
静态工具**彻底**判定（demo E2 用 42→6 实测展示；§13 给出 4.6%–14.2% 的可检测下界，
但 85.8%–95.4% 指纹全同区间仍判不干净）；Mixin refmap、反射字符串、真实客户端端到端验证均未覆盖。
HostBridge 只解决「旧签名能链接上」这一机械层，`<init>`、已被删除的成员（MISSING）、
需要真实游戏状态的语义，均不在其能力范围内。
双 agent 组合虽经最小复现验证可行（REPORT §11），但必须 `-Dmcport.only` 限定改写范围，
且未在真实客户端端到端验证。§12 只把「26.x 需要 JDK 25」这一环境门槛判干净，
不等于客户端/Fabric/LWJGL/真实 mod 已跑通。§13 只给语义漂移一个可检测下界，
85.8%–95.4% 的指纹全同区间静态工具仍判不干净，不证明任何 mod 能跑。
本工具不做「任意版本都有效」的承诺。

## 回滚

站点条目在 `/var/www/studio/downloads/manifest.json`；R2 目录对象为
`catalog/downloads.json`。两者在发布时均留有 `.bak-mcport-*` 备份。
