# 发布通道 / Publishing

本仓库是 McPort 工具链的**源码与测量产物**，采用 MIT 许可（见 `LICENSE`）。

| 内容 | 位置 |
| --- | --- |
| 源码、文档、测量数据 | GitHub: https://github.com/lilyco-42/mcport |
| 打包分发件 `mcport-0.2.4-dist.tar.gz` | GitHub Release `v0.2.4` 资产 `https://github.com/lilyco-42/mcport/releases/download/v0.2.4/mcport-0.2.4-dist.tar.gz` |
| 下载入口 | https://lain42.top/downloads/ → 条目 `mcport`（当前 `mirror.url` 为 GitHub Release 直链，无票据/积分；**不是** R2 加速） |
| 原定 R2 目标 | 桶 `lain42-dl`，key `downloads/mcport/0.2.4/mcport-0.2.4-dist.tar.gz`；目录对象 `catalog/downloads.json` 仍指向 0.1.8（凭据恢复后补传） |

## 发布通道状态（2026-11-16）

* R2 发布链被凭据阻塞：远端 `/etc/codex-cf.env` 的 `CF_API_TOKEN` 与本机历史 token 均被 Cloudflare 返回 401；Wrangler OAuth `refresh_token` 交换返回 `invalid_grant`（已撤销）。因此本版仍**没有**上传 R2 对象，也没有改写 R2 `catalog/downloads.json`；站点 0.2.4 条目改走已存在的 GitHub Release 直链通道。
* 直链是现有页面行为：`mirror` 有 `url` 且无 `slug` 时前端按「GitHub 直链 · 断点续传」展示；它绕过 `dl.lilyco42.top/d/mcport` 的 HMAC 票据、10 积分计费与 Cloudflare R2 加速/Range 代理。此偏差需用户确认，不作为等效加速。
* 恢复 R2：取得具备 R2 写权限的新 CF API token 或 S3 凭据后，上传上述 tar 到目标 key，把 `catalog/downloads.json` 的 `mcport` 项更新为 0.2.4 的 `name` / `size` / `key`（保持 `slug=mcport`），再把 manifest `mirror.url` 切回 `https://dl.lilyco42.top/d/mcport` 并恢复 `mirror.slug=mcport`；发布前先备份 catalog 与 manifest。Worker / 计费 / 前端均无需改动。
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
* §21 的 `tools/capability.py` 严格 `parse_ref` + `tools/contract_audit.py` / `tools/test_contract_audit.py` 零外部数据 110 断言全绿；`demo/gate/run.sh` G25–G27 在两版 8 份真实工单 / canonical 契约 / 合成 stub 上实跑，修复 1 条 0.2.1 已知 SIGCHG 静默放行并把契约来源、键语法、覆盖率改为 fail-loud；`data/contract-audit-summary.csv` / `contract-audit-README.md` / `contract-audit-spec.example.json` 仅聚合数字、口径与路径占位符。
* §22 的 `tools/bridgegen.py` / `tools/relocate.py` 统一委托严格 `capability.parse_ref`，`tools/test_parse_unified.py` 与 `demo/gate/run.sh` G28 在两版 8 份真实工单上实跑（114 断言；G28 加入时闸门为 28 场景 136 断言），197 / 1 工具内部分歧归零、零 None、零自动修复；`data/parse-unified-summary.csv` / `parse-unified-README.md` / `parse-unified-spec.example.json` 仅聚合数字、口径与路径占位符。
* §23 的 `java/mcport/LinkCheck.java --refs-json` + `tools/refcheck.py` / `tools/test_refcheck.py` 零外部数据 216 断言全绿；`demo/gate/run.sh` G29–G31 在合成碰撞 fixture、274B 旧 `--json` 黄金字节、含引号 / 反斜杠路径与两版 8 份真实工单上实跑（structured=2 / legacy=2 / ambiguous=2 / resolved=1 / diverged=1、31 场景 158 断言），历史源文本固有歧义 3 / 51 按启发式留档；`data/refcheck-summary.csv` / `refcheck-README.md` / `refcheck-spec.example.json` 仅聚合数字、口径与路径占位符。
* §19 / §20 的 `java/mcport/LinkGate.java` + `tools/linkgate_contract.py` 零外部数据 27 断言全绿；`demo/gate/run.sh` 31 场景 158 断言全绿（含 G29–G31 结构化引用对账）（含真实 26.1 工单契约→JVM premain 阻断合成 stub、语义漂移 42→6、warn 不豁免配置错误，以及 §20 版本绑定 / 空 jar / 冲突契约 / 非法状态与非法头的 fail-loud）；`data/linkgate-summary.csv` 仅聚合数字，完整契约、stub 字节与 mod 二进制均不随包提供。
* §18 的 `tools/test_capability.py` 零外部数据 158 断言全绿；`tools/capability.py` 在
  四版真实声明表、三张 map/bridge、17 份 loader plan、50 份 LinkCheck 工单、2 份
  stringsurface 与 2 份 bridgegen 聚合 stats 上跑出 clean / manual / poison / full 四组闸门
  （`READY` / `NEEDS_MANUAL` / `UNSUPPORTED` / `UNSUPPORTED`）；`data/capability-*.csv`
  仅聚合数字，gate / triage / 完整能力清单均不随包提供。

## 边界（务必阅读 REPORT.md §7 / §12 / §13 / §14 / §15 / §16 / §17 / §18 / §19 / §20 / §21 / §22 / §23）

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
§19 只在启动期扫描 class 常量池里的成员引用并按显式契约干净拒绝；它不修任何东西，`RESOLVE` / `PASS` 不证明运行期语义一致，G15 的 42→6 就是铁证；反射 / 配置 / 资源字符串不在扫描射程（§17），契约质量依赖上游工单，真实客户端端到端仍未覆盖。
§20 只收紧「闸门说 `PASS`」的前提：契约 `version` 头须与 `-Dmcport.gate.version` 绑定、mod jar 必须真的被扫到 class、契约行 / 头不得互相冲突、状态与 `source_sha256` 头必须合法；它仍是纯启动期拒绝，不新增 JVM 层加载器、不修任何引用、不扩大「能跑」集合，G15 的 42→6 仍然 `PASS`。
§18 只做静态能力契约与证据闸门：四版声明表 + 5 组映射 / 桥审计 + 50 条 evidence，
`READY` 仅表示静态符号证据齐备且零 SIGCHG/MISSING，绝不升级为行为等价或启动成功；
26.x bridge 逆向碰撞、PLAN_ONLY、未审桥候选、unresolved 字符串一律 fail-loud。
§21 只收紧「契约有资格说覆盖」的证据前提：canonical 契约、工单字节复现、严格 JVMS 键语法、常量池覆盖率、EXTERNAL / 第三方 / stale 分类全部可机器复核；它不新增 JVM 层加载器、不重映射、不执行 mod、不证明运行期语义，G15 的 42 与 6 同名同签名语义漂移仍是静态不可判铁证。源文本固有歧义（1.21.11 / 26.1 分别 3 / 51 条）仍留档；§22 已把独立 `bridgegen` / `relocate` 解析器差异（197 / 1 条）归零，但统一解析仍不是运行期证明。
§22 只统一三工具对工单符号文本的严格 JVMS §4.3 切分，保持 `auto_fixed=0`、字段 `REJECT_FIELD`、relocate 只读 MISSING；它不改 mod 字节、不新增 JVM 层加载器、不消除源文本固有歧义、不证明同名同签名语义等价，也不覆盖真实客户端端到端。
§23 只让**新工单**可从源头输出精确 `(kind,owner,name,desc,status)` 并用 multiset 对账消解文本歧义；普通 `--json` 字节不变，8 份历史真实工单的 3 / 51 条源文本歧义不能追溯改写，仍按启发式留档。`STRUCTURED_REFS_OK` 不证明运行期兼容或语义等价，不重映射、不新增 JVM 层加载器、不扩大 `PASS` / 自动修复集合，G15 的 42→6 仍是铁证。
本工具不做「任意版本都有效」或「全平台全版本任意 mod 都能跑」的承诺。

## 回滚

站点条目在 `/var/www/studio/downloads/manifest.json`；0.2.4 发布前留有
`.bak-mcport-024-*` 备份（含 0.2.3 / GitHub 直链条目，另有 `.bak-mcport-023-*` / `.bak-mcport-022-*` 等更早备份），更早还有 `.bak-mcport-020-*` / `.bak-mcport-019-*` / `.bak-mcport-018-*`。回滚时把 `mcport` 条目恢复为对应备份，并把 GitHub Release `v0.2.4` 标为草稿或删除资产；R2 `catalog/downloads.json` 本版未改写，无需回滚。待 R2 写凭据恢复后按上一节补传并统一切换。
