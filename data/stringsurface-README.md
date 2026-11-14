# §17 字符串姓名表面：聚合口径 / 合规 / 踩坑

本文件只含**纯聚合计数与口径说明**。`tools/stringsurface.py` 运行时才读使用者自备的
`decl-*.tsv` / `map-*.tsv` / mod jar；`triage.tsv` / `stats.json` / `fixed/*.jar`
只写 `--out-dir`，**不进仓库、不进发布包**。仓库与发布包不含任何 Mojang client jar、
官方 ProGuard 映射、第三方 mod 字节码，也不含逐条符号表。

## 输入与输出

| 文件 | 内容 |
|---|---|
| `--spec` | schema=1，targets[] 每项 `{version, decl, map, jars[]}`；模板 `stringsurface-spec.example.json` 仅路径占位符 |
| `<version>/triage.tsv` | 每条非 NO_GAME_TOKEN 字符串的 old/new/status/reason（不分发） |
| `<version>/stats.json` | 分桶计数（不分发） |
| `<version>/fixed/*.jar` | 仅 `--rewrite` 产生，只含精确改名条目（不分发） |
| `summary.csv` | 21 列纯聚合，即 `stringsurface-summary.csv` |

## 21 列口径（本机 8 个真实 jar 实测）

| 版本 | jars | class | resource | strings | unique | no_game | target_present | exact_remap | member_exact_remap | unresolved | mapped_target_missing | member_target_missing | rewritten_jars | rewritten_entries |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.21.11 | 4 | 1140 | 13 | 3644 | 2606 | 3510 | 36 | 0 | 2 | 96 | 0 | 0 | 0* / 1 | 0* / 1 |
| 26.1 | 4 | 1140 | 13 | 3644 | 2606 | 3510 | 12 | 10 | 58 | 54 | 33 | 10 | 0* / 1 | 0* / 5 |

* `stringsurface-summary.csv` 取自**默认审计模式**（不写 jar，故两列 rewritten=0）；
  显式 `--rewrite` 的实跑另外改写 6 个条目（1.21.11 一个 refmap 值、26.1 四个 LDC `.class`
  加一个 refmap JSON）。两种模式的分桶数字与 `triage.tsv` 哈希完全一致，仅 rewritten 列不同。
* `unresolved` 是 `UNRESOLVED + MAPPED_TARGET_MISSING + MEMBER_TARGET_MISSING` 之和：
  1.21.11 = 96，26.1 = 11 + 33 + 10 = 54，合计 150。进程因此 `exit 2`（fail-loud 预期）。
* `exact=70`（2 + 68）是**符号可精确改名**的下界，不是「已修复 70 个 mod 问题」；
  字符串被反射 / 序列化 / 配置 schema 如何使用，静态工具判不干净。
* 另外六列 `external` / `no_owner_member` / `named_no_owner` /
  `member_missing_desc` / `invalid_json` / `cp_parse_fail` 两版均为 0。

## 三套易混口径

1. 早期用正则扫 `.class` 原始字节得到「上百个类名字符串」是**粗扫误判**；精确常量池
   解析证明 8 个 jar 的裸类名 LDC 为 0，真实盲区在 `L...;` 描述符形态与 refmap JSON。
2. `TARGET_PRESENT` 表示老名字已在目标 decl 声明，**不需要改**；`EXACT_REMAP` /
   `MEMBER_EXACT_REMAP` 才是可精确改写。`MAPPED_TARGET_MISSING` 表示 C 行映射到的
   新类不在目标 decl，说明映射表本身不完整，一律拒绝。
3. §15 的 48 条 / §16 的 179 SIGCHG + 423 MISSING 是**字节码符号**口径；本章 7288 条
   是**字符串出现次数**（含 3510 条与游戏无关的字符串），两套分母不可相加。

## 复现（自备制品，脚本不下载不入库）

```bash
python3 tools/test_stringsurface.py                 # 78 断言，零外部数据
python3 tools/stringsurface.py --spec /work/spec.json --out-dir /work/audit
python3 tools/stringsurface.py --spec /work/spec.json --out-dir /work/rw --rewrite
```

默认只审计不写 jar；`--rewrite` 才产 `fixed/*.jar`；有 unresolved 就 `exit 2`。

## 五个真 bug / 踩坑

1. JSON key collision 检测漏判：`if nk in out and nk != k` 在 `nk==k` 时放过真碰撞。
2. decl 表是 set 而通用 `_bfs` 假定 dict，报 `AttributeError: set object has no attribute get`；
   映射表 M/F 键是 `(owner,desc,name)`，decl 表是 `(owner,name,desc)`，必须两套 BFS。
3. `javap -verbose` 的 `-cp` 要指到 fixed **jar 本身**，不是解压目录。
4. **最危险**：无精确改名时仍 `json.dumps` 重序列化，4 个 `fabric.mod.json` /
   `*.mixins.json` 因缩进变化被误判改写（首轮 `rewritten=26`）。加 `changed[0]` 标志后
   无改名直接返回原字节，真实 `rewritten=6`。「把格式差异当修复」是假阳性。
5. §16 已记的 `String.replace(anchor, replacementString)` 会把 replacement 里的
   `$` 紧跟反引号当成「插入匹配前缀」；文档补丁一律用函数式替换 `() => text`。

## 边界

`--rewrite` 只是符号改名；不证明运行期行为等价，不覆盖 `assets/` 下的点分类名文案、
反射 / 序列化 / 网络协议 / 配置 schema、真实客户端 / Fabric / LWJGL / Mixin 运行时、
语义漂移与 Bedrock。**静态可解析率不等于能跑。**
