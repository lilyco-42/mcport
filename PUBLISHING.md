# 发布通道 / Publishing

本仓库是 McPort 工具链的**源码与测量产物**，采用 MIT 许可（见 `LICENSE`）。

| 内容 | 位置 |
| --- | --- |
| 源码、文档、测量数据 | GitHub: https://github.com/lilyco-42/mcport |
| 打包分发件 `mcport-0.1.9-dist.tar.gz` | GitHub Release `v0.1.9` 资产 `https://github.com/lilyco-42/mcport/releases/download/v0.1.9/mcport-0.1.9-dist.tar.gz` |
| 下载入口 | https://lain42.top/downloads/ → 条目 `mcport`（当前 `mirror.url` 为 GitHub Release 直链，无票据/积分；**不是** R2 加速） |
| 原定 R2 目标 | 桶 `lain42-dl`，key `downloads/mcport/0.1.9/mcport-0.1.9-dist.tar.gz`；目录对象 `catalog/downloads.json` 仍指向 0.1.8（凭据恢复后补传） |

## 发布通道状态（2026-11-15）

* R2 发布链被凭据阻塞：远端 `/etc/codex-cf.env` 的 `CF_API_TOKEN` 与本机历史 token 均被 Cloudflare 返回 401；Wrangler OAuth `refresh_token` 交换返回 `invalid_grant`（已撤销）。因此本版**没有**上传 R2 对象，也没有改写 R2 `catalog/downloads.json`；站点 0.1.9 条目改走已存在的 GitHub Release 直链通道。
* 直链是现有页面行为：`mirror` 有 `url` 且无 `slug` 时前端按「GitHub 直链 · 断点续传」展示；它绕过 `dl.lilyco42.top/d/mcport` 的 HMAC 票据、10 积分计费与 Cloudflare R2 加速/Range 代理。此偏差需用户确认，不作为等效加速。
* 恢复 R2：取得具备 R2 写权限的新 CF API token 或 S3 凭据后，上传上述 tar 到目标 key，把 `catalog/downloads.json` 的 `mcport` 项更新为 0.1.9 的 `name` / `size` / `key`（保持 `slug=mcport`），再把 manifest `mirror.url` 切回 `https://dl.lilyco42.top/d/mcport` 并恢复 `mirror.slug=mcport`；发布前先备份 catalog 与 manifest。Worker / 计费 / 前端均无需改动。
* 完整性：任何通道下载后都应核对 `mirror.sha256`；`sha256sum -c` 与 `tar tzf` 是发布验收的硬条件。


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
* §14 的 `tools/test_loader.py` 零外部数据 49 断言全绿；`tools/loader.py` 在 5 个真实
  client jar + 4 个真实 mod 上跑通 P1–P6 / S1–S7，制品目录仅本机符号链接，不随包提供。
* §15 的 `tools/test_relocate.py` 零外部数据 27 断言全绿；`tools/relocate.py` 在 8 份真实
  工单 + 2 份真实声明表上生成 5 条 C 行，`RemapTool` + 无 `--map` 复测得到 48 条静态 RESOLVE；
  `data/relocate-summary.csv` 仅聚合数字，输入与生成的 C 行均不随包提供。
* §16 的 `java/mcport/CallKind.java` + `tools/test_bridgegen.py` 零外部数据 61 断言全绿；
  `tools/bridgegen.py` 在 §15 复测后的 8 份真实工单 + 2 份真实声明表 + 8 个已重映射 mod jar
  上分桶 602 条引用，得到 4 条唯一人工候选规则与 `auto_fixed=0`；`data/bridgegen-summary.csv`
  仅聚合数字，callkind / triage / adapter 骨架均不随包提供。
* §17 的 `tools/test_stringsurface.py` 零外部数据 78 断言全绿；`tools/stringsurface.py` 在
  §15 复测后的 8 个真实 mod jar 上 audit / rewrite 实跑：7288 次字符串出现、70 条可精确改名、
  150 条 fail-loud、6 个真实条目改写，4 个改写 class 经 `javap` / `unzip -t` / LinkCheck 复测；
  `data/stringsurface-summary.csv` 仅聚合数字，triage / fixed jar 均不随包提供。
* §18 的 `tools/test_capability.py` 零外部数据 156 断言全绿；`tools/capability.py` 在
  四版真实声明表、三张 map/bridge、17 份 loader plan、50 份 LinkCheck 工单、2 份
  stringsurface 与 2 份 bridgegen 聚合 stats 上跑出 clean / manual / poison / full 四组闸门
  （`READY` / `NEEDS_MANUAL` / `UNSUPPORTED` / `UNSUPPORTED`）；`data/capability-*.csv`
  仅聚合数字，gate / triage / 完整能力清单均不随包提供。

## 边界（务必阅读 REPORT.md §7 / §12 / §13 / §14 / §15 / §16 / §17 / §18）

静态符号可解析率 **不等于** 能在真实客户端运行。同名同签名语义漂移无法被
静态工具**彻底**判定（demo E2 用 42→6 实测展示；§13 给出 4.6%–14.2% 的可检测下界，
但 85.8%–95.4% 指纹全同区间仍判不干净）；Mixin refmap 与反射字符串已由 §17 做精确审计和 fail-loud 改写，但不覆盖运行期语义；§18 把静态证据合成三档出货闸门但不覆盖运行期语义；真实客户端端到端验证仍未覆盖。
HostBridge 只解决「旧签名能链接上」这一机械层，`<init>`、已被删除的成员（MISSING）、
需要真实游戏状态的语义，均不在其能力范围内。
双 agent 组合虽经最小复现验证可行（REPORT §11），但必须 `-Dmcport.only` 限定改写范围，
且未在真实客户端端到端验证。§12 只把「26.x 需要 JDK 25」这一环境门槛判干净，
不等于客户端/Fabric/LWJGL/真实 mod 已跑通。§13 只给语义漂移一个可检测下界，
85.8%–95.4% 的指纹全同区间静态工具仍判不干净，不证明任何 mod 能跑。
§14 的装载编排机只保证「能自动做对的部分自动做、做不到的部分 fail-loud」，
不是游戏启动器，不覆盖 Bedrock / native / Mixin refmap / 语义漂移 / 真实客户端端到端。
§15 只把 MISSING 里 48 条同名类换包变成机械可解析的 C 行补充，复测后仍有
179 条 SIGCHG + 423 条 MISSING 需人工；13 条不同简单名偶合 fail-loud 拒绝，静态可解析率仍不等于能跑。
§16 明确 **零自动修复**：4 条候选规则与抛异常 adapter 骨架只是人工起点，
`--emit-rules` 需显式人工确认；数值 widening / void 丢弃仍是语义变化，不证明任何 mod 能跑。
§17 只改**符号字符串**：70 条可精确改名、150 条逐条 fail-loud、6 个真实条目改写；
改写后符号预言机工单不变，但 `assets/` 文案、反射 / 序列化 / 配置 schema 的运行期语义仍未解决。
§18 只做静态能力契约与证据闸门：四版声明表 + 5 组映射 / 桥审计 + 50 条 evidence，
`READY` 仅表示静态符号证据齐备且零 SIGCHG/MISSING，绝不升级为行为等价或启动成功；
26.x bridge 逆向碰撞、PLAN_ONLY、未审桥候选、unresolved 字符串一律 fail-loud。
本工具不做「任意版本都有效」或「全平台全版本任意 mod 都能跑」的承诺。

## 回滚

站点条目在 `/var/www/studio/downloads/manifest.json`；0.1.9 发布前留有
`.bak-mcport-018-*` 备份。回滚时把 `mcport` 条目恢复为该备份（0.1.8 / R2 票据通道），并把 GitHub Release `v0.1.9` 标为草稿或删除资产；R2 `catalog/downloads.json` 本版未改写，无需回滚。待 R2 写凭据恢复后按上一节补传并统一切换。
