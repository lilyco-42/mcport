# Contract audit 聚合数据说明（REPORT §21 / §22 / §23 / §24）

本目录只含**可分发聚合数字、格式口径与路径占位符**，不含 Mojang client jar、官方 ProGuard 映射、第三方 mod 字节码、完整 LinkGate 契约或 audit JSON。完整契约由 `tools/linkgate_contract.py` 在调用方本机生成；`tools/contract_audit.py` 只读取调用方自备的契约、工单和 mod jar，报告写入 `--out` / `--summary` 指定的目录。

## 输入与判定

```bash
python3 tools/linkgate_contract.py --ticket '/work/tickets/26.1__*.json' \
  --version 26.1 --out /work/capability-26.1.tsv \
  --summary /work/linkgate-summary.csv
python3 tools/contract_audit.py --contract /work/capability-26.1.tsv \
  --modjar /work/mod.jar --version 26.1 \
  --ticket '/work/tickets/26.1__*.json' \
  --out /work/contract-audit.json --summary /work/contract-audit.csv
```

* canonical 契约：LF / 无 CR、4 行头、四列 TAB、owner/name/desc 严格 JVMS §4.3、status 大写且已知、键有序、无重复、无映射箭头文本。
* `--version` 与契约 `version` 头逐字绑定；`--ticket` 可重复，用于 `source_sha256` 校验、完整契约逐字节复现、`EXTERNAL` 精确分类。
* 默认游戏前缀：`net/minecraft/`、`com/mojang/blaze3d/`、`com/mojang/math/`、`com/mojang/realmsclient/`。`--game-prefix` 可追加。
* 游戏 ref 未命中契约记 `unknown_game_refs`；非游戏且非已知库前缀记 `unclassified_refs`（只有 `--allow-third-party` 显式豁免）；契约多 mod 聚合造成的 stale 默认只量化，`--fail-stale` 才阻断。
* 判定：`UNSUPPORTED` rc=1（结构/证据错误）、`NEEDS_MANUAL` rc=2（命中 MISSING/SIGCHG/RENAME）、`COVERAGE_ONLY_OK` rc=0（显式 `--coverage-only`）、`COVERAGE_OK` rc=0。`COVERAGE_OK` 仅表示静态契约覆盖，`does NOT mean runtime-compatible; RESOLVE and coverage do NOT prove semantic equivalence`。

## `data/contract-audit-summary.csv` 的 24 列

`schema,version,contract,modjar,contract_rows,contract_sha256,source_sha256,ticket_count,ticket_digest_ok,regenerated_bytes_match,classes,member_refs,covered,external,third_party,array_refs,unknown_game_refs,unclassified_refs,stale_contract_refs,known_blockers,renames,needs_manual_refs,verdict,reasons`。

两行分别来自 1.21.11 / 26.1 各 4 份真实 `data/hotmods/*.json` 工单生成的 canonical 契约，mod jar 是 §19 已有的合成 `demo/gate/build/gate-stub.jar`（1 个 class、2 个成员引用：1 条命中 MISSING、1 条 `java/lang/Object.<init>()V` 外部引用）。两行 `contract` 字段是逻辑文件名，不是仓库内真实完整契约路径。

实测两版：`ticket_digest_ok=1`、`regenerated_bytes_match=1`、`unknown_game_refs=0`、`unclassified_refs=0`、`stale_contract_refs=1018`、`needs_manual_refs=1`、`verdict=NEEDS_MANUAL`。28 条 EXTERNAL 原始行去重为 27 个精确键（`com/mojang/serialization/Codec.fieldOf` 在两份工单重复）；`source_sha256` 只由工单 basename + bytes 计算，严格 `parse_ref` 修复前后不变。

## 边界

`COVERAGE_OK` 不等于运行期兼容、不等于行为等价、不等于真实客户端启动成功；同名同签名语义漂移（demo G15 的 42 与 6）静态不可彻底判定。审计器只扫 class 常量池的 tag 9/10/11 成员引用，不执行 mod、不解析反射/配置/资源字符串的运行期取值、不修任何引用。`--allow-third-party` / `--coverage-only` 是人工显式豁免，不是稳定性证明。完整契约、audit JSON/CSV、stub jar 与任何 mod 二进制均不随本仓库分发。§22 的统一解析器回归见 `../tools/test_parse_unified.py` 与 `data/parse-unified-README.md`；它消除的是工具内部 197 / 1 条误切分，不是运行期兼容证明。 §23 的 `LinkCheck --refs-json` 从源头给新工单精确 `(kind,owner,name,desc,status)`，`tools/refcheck.py` 用结构化 multiset 消解合成碰撞；旧 `--json` 字节与 8 份真实工单不变，故本审计器的契约 / digest 复现口径不变，历史源文本固有歧义 3 / 51 仍不能追溯改写。 §24 的 `tools/classref.py` 独立扫 `CONSTANT_Class`（tag 7）与描述符里的类引用，补上本审计器只扫 tag 9/10/11 成员引用的盲区；本目录 24 列聚合与 canonical 契约口径不变，见 `data/classref-summary.csv` / `classref-README.md`。
