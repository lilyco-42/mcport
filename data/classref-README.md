# 类级链接面审计 / Class-level linkage audit（REPORT §24）

`data/classref-summary.csv` 是 `tools/classref.py` 三次真实 CLI 实跑的 27 列聚合；每行一个场景，不含 Mojang client jar、官方 ProGuard 映射或第三方 mod 二进制。

## 文件

* `tools/classref.py`：纯标准库离线审计器，复用 `tools/contract_audit.py` 的常量池解析器 / 描述符校验 / 数组归一化。
* `tools/test_classref.py`：225 条自包含断言，零网络、零游戏 jar、零官方映射、零第三方二进制、零 javac。
* `demo/gate/run.sh` G32–G36：36 场景 180 断言中的 22 条新增断言，覆盖 PASS / 盲区 / 改名 / digest / 前缀 / 版本。
* `data/classref-spec.example.json`：路径占位符模板，不嵌入任何输入字节。

## 27 列

`schema,tool,version,decl,decl_sha256,decl_digest_ok,map,map_sha256,map_rows,map_ignored_rows,map_target_missing,modjar,classes,cp_class_refs,desc_type_refs,unique_class_refs,array_refs,own_classes,resolve,rename,missing,external,third_party,self_count,needs_manual,verdict,reasons`。

## 实测

| 场景 | verdict | rc | resolve / rename / missing | external / third_party / self | needs_manual |
| --- | --- | --- | --- | --- | --- |
| 合成 decl 绑定 sha256 | `CLASSREFS_OK` | 0 | 1 / 0 / 0 | 9 / 0 / 1 | 0 |
| §23 的 274B 成员 PASS jar | `NEEDS_MANUAL` | 2 | 1 / 0 / 1 | 1 / 1 / 1 | 1 |
| 合成 C 改名表 | `NEEDS_MANUAL` | 2 | 0 / 1 / 0 | 9 / 0 / 1 | 1 |

8 份 `data/hotmods/*.json` 每版 1190 行、GAME 2324 / EXTERNAL 56；`java/lang/Object` 不在工单 owner 中却出现在 demo jar 的类引用面，证明旧成员工单没有类级链接面。5 个 tracked demo jar 全部可扫：`api-v1` / `api-v2` / `api-v2b` 各 4 唯一类，`mcport-runtime` 62 唯一类 / 3 数组，`mod-1.20.1` 11 唯一类。

## 边界

`CLASSREFS_OK` 只表示静态类解析面可覆盖，不等于运行期兼容、行为等价或真实客户端启动成功；`CLASSREFS_ONLY_OK` 仅 `--coverage-only` 时 rc=0，仍逐条列出 `MISSING` / `RENAME`；`NEEDS_MANUAL` rc=2；`UNSUPPORTED` rc=1。审计器不新增 JVM 层加载器、不接 `premain`、不重映射、不执行 mod、不覆盖反射 / JSON 字符串类名（§17）与资源运行期取值、不模拟 ClassLoader / Mixin / Fabric、不证明同名同签名语义等价（G15 的 42→6 仍是铁证）。179 SIGCHG + 423 MISSING 人工缺口、真实客户端 / Fabric / LWJGL / Mixin 端到端、§21.4 源文本固有歧义 3 / 51 全部不变。

§21 / §22 / §23 的契约、canonical 复现、统一解析与结构化五元组口径逐字不变：274B 黄金、8 份历史工单、`source_sha256`、G25 `regenerated_bytes_match` 与 G30 `cmp` 均不受影响。见 `data/linkgate-README.md` / `data/contract-audit-README.md` / `data/parse-unified-README.md` / `data/refcheck-README.md`。
