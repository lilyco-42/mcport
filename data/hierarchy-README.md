# decl 继承层跨工具对账 / Hierarchy reconciliation（REPORT §25）

`data/hierarchy-summary.csv` 是 `tools/hierarchy.py` 三次真实 CLI 实跑的 36 列聚合；每行一个场景，不含 Mojang client jar、官方 ProGuard 映射或第三方 mod 二进制。

## 文件
- `tools/hierarchy.py`：纯标准库离线对账器；`tools/test_hierarchy.py` 390 条自包含断言；`demo/gate/run.sh` G37–G42。
- `data/hierarchy-spec.example.json`：仅路径占位符与本工具 CLI 形状，不含任何 decl / map 字节。
- 本文件只记录聚合口径与结论；临时 decl / map / JSON / CSV 写入 `demo/gate/build/hierarchy/`，按 `.gitignore` 排除。

## 三次实跑
| 场景 | decl | verdict | 关键计数 |
| --- | --- | --- | --- |
| 正常继承链 | decl-good.tsv（合成，6 行） | `HIERARCHY_OK` rc=0 | rows=6 / c_classes=2 / s_rows=2 / edges=2 / resolve=1 / external=1 |
| 摘要碰撞 | collide-a.tsv + --compare-decl collide-b.tsv | `NEEDS_MANUAL` rc=2 | capability_digest 相同、hierarchy_digest 不同、capability_digest_collision=1 |
| F-only 黄金 decl | demo/gate/refcheck-decl.tsv（§23 fixture） | `NEEDS_MANUAL` rc=2 | divergent=1、CAPABILITY_DECL_REJECTED、CAPABILITY_NO_C_ROWS、NO_HIERARCHY_ROWS |

## 口径
36 列：schema,tool,version,decl,decl_sha256,decl_digest_ok,compare_decl,compare_decl_sha256,compare_capability_digest,compare_hierarchy_digest,capability_digest,hierarchy_digest,capability_digest_collision,map,map_sha256,map_rows,map_ignored_rows,map_target_missing,rows,row_kinds,c_class_count,java_class_count,classref_class_count,divergent_owner_count,divergent_owners,s_rows,super_edges,iface_edges,resolve,rename,missing,external,third_party,needs_manual,verdict,reasons。

真实基线：8 份 `data/hotmods/*.json` 每版 1190 行、`data/refcheck-legacy-golden.json` 274B / sha256 1e398ea4c07c911537f5ba6aeaa582d3ea18a7f10eba11c1c7f2387f5844254c、`demo/gate/refcheck-decl.tsv` 96B / sha256 12bc31aaaf2c06066c5756dd45a92f0b54dfe0feed25e947c06ae723b47d7508、5 个 tracked demo jar 均逐字节不变。

## 边界
`HIERARCHY_OK` / `HIERARCHY_ONLY_OK` 只表示显式 S 行的父类 / 接口目标被同一份 decl 静态覆盖且三工具 class surface 无分歧；rc=2 是 NEEDS_MANUAL、rc=1 是 UNSUPPORTED，均 fail-loud。本工具不改 `tools/capability.py` 的 C-only 语义与 C/M/F digest（保护 274B 黄金、8 份工单、source_sha256、canonical 契约、G25 / G30、javac 32、1065 断言与 180 条旧闸门断言），不接入 premain、不重映射、不执行游戏、不覆盖反射 / JSON 字符串类名、运行期 ClassLoader / Mixin / Fabric 行为与同名同签名语义漂移（G15 的 42→6 仍是铁证）。`does NOT mean runtime-compatible; hierarchy coverage does NOT prove semantic equivalence`。179 SIGCHG + 423 MISSING 人工缺口、真实客户端端到端、§21.4 源文本固有歧义 3 / 51 全部不变。
