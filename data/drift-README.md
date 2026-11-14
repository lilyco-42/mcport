# 真实 jar 语义漂移量化 / Drift measurement (REPORT §13)

本目录只存**聚合数字**与复现模板。输入（`body-*.tsv`、官方 ProGuard 映射、
Minecraft client jar）都是使用者自备的本地测量中间产物，**不进仓库、不进发布包**，
理由见 [NOTICE-mappings.md](NOTICE-mappings.md)。

## 这组数字是什么

`drift-summary.csv` 的每行是一个版本对。对四个真实 client jar
（1.21.1 / 1.21.11 / 26.1 / 26.3）里的每个非 abstract / 非 native 方法，
`java/mcport/BodyHash.java` 计算三列 SHA-256 指纹：

| 列 | 内容 | 刻意排除了什么 |
| --- | --- | --- |
| `sk` | opcode 序列 + 数值/字符串常量 + 变量索引 + switch 分支数 + IINC 增量 | **所有 owner/name/desc/Type**（统一写 `REF`）、跳转 Label |
| `op` | 纯 opcode 字节序列 | 一切操作数 |
| `call` | 调用目标 `M:owner.name:desc` / 字段 / 类型 / invokedynamic | 调用目标**内部实现** |

`tools/drift_align.py` 用**真实命名身份**对齐两版，而不是混淆短名或 Fabric
intermediary：

* 1.21.1 / 1.21.11 的 `(owner,name,desc)` 是混淆短名，用该版本官方 ProGuard
  映射反解成 `(真实类内部名, 真实成员名, 真实描述符)`；
* 26.1 / 26.3 起官方去混淆，`(owner,name,desc)` 本身就是真实身份；
* 两侧落到同一命名空间，因此 `1.21.11 → 26.1` 可跨去混淆断代直接对齐。

分类优先级：`op` 不同 → `OPCODE_DIFF`；`op` 同但 `sk` 不同 → `OPERAND_DIFF`；
仅在 26.1→26.3 启用 `call` 比较（混淆名与真实名混排时该列天然不可比），
`sk`/`op` 同但 `call` 不同 → `CALL_TARGET_DIFF`；三列全同 →
`identical_all_fingerprints`。

| 版本对 | 同身份方法 | 指纹不同（可检测下界） | 三列全同（不可判定区间） | call 可比 |
| --- | ---: | ---: | ---: | --- |
| 1.21.1→1.21.11 | 49618 | 5798 (11.69%) | 43820 (88.31%) | 否 |
| 1.21.11→26.1 | 74316 | 3419 (4.60%) | 70897 (95.40%) | 否 |
| 26.1→26.3 | 78555 | 5849 (7.45%) | 72706 (92.55%) | 是 |
| 1.21.1→26.1 | 44808 | 6360 (14.19%) | 38448 (85.81%) | 否 |

`old_unmapped` / `new_unmapped` 是官方映射未列出的合成/特殊方法（`<init>`、
`<clinit>`、部分 override 等），直接跳过，不计入分母。

## 正确读法 / 错误读法

* **能说**：同名同签名的方法里，有 4.6%–14.2% 的实现字节码指纹确实变了。
  这是"实现变更候选"的**可检测下界**，不是"坏掉的比例"。
* **能说**：85.8%–95.4% 的方法三列指纹全同，静态工具**判不干净**。
* **不能说**：指纹全同 = 行为相同。被抹掉的恰好是能改变行为的东西：
  跳转目标重排、被调用者内部实现变化、注册表/配置/运行时状态、反射、资源与
  native 代码。`26.1→26.3` 里 1817 条 `CALL_TARGET_DIFF` 就是"骨架没变、
  调用目标变了"的实例；即使比较调用目标，也看不到被调用者内部。
* **不能说**：这给 78.7% 静态可解析率加了任何可运行性保证。§13 不证明任何
  mod 能跑，只把 §1 第 3 层"检测不出来"精确化为"可检测下界 + 不可判定区间"，
  核心结论**没有松动**：任意版本绝对不失效不可实现。
* demo E2 的 `42 → 6` 是 LDC 常量变化，属于 `sk` 能抓到的**子集**；
  §1 原句"任何字节码工具检测不出来"因此被收窄为"任何工具都无法彻底判定"。

## 复现（自备输入，脚本不下载任何东西）

```bash
mkdir -p build && javac -nowarn -cp 'lib/*' -d build java/mcport/*.java
for v in 1.21.1 1.21.11 26.1 26.3; do
  java -Xmx1g -cp 'build:lib/*' mcport.BodyHash "/path/to/REAL-$v.jar" "/work/body-$v.tsv"
done
# 把 drift-spec.example.json 里的 <WORKDIR>/<MAPS> 换成自备路径
python3 tools/drift_align.py --repo . --spec /work/drift-spec.json --out-dir /work/out
```

`tools/drift_align.py` 输出 `drift-summary.json`（纯聚合数字）与
`drift-anon-*.tsv`（`sha256(真实身份)[:16]` 匿名变更样例）。两者都不含真实类名、
方法名、映射文本或游戏字节。`body-*.tsv` 含真实成员名，**只留在本地工作目录**。

## 踩过的坑

1. `Collections.list(Enumeration<? extends ZipEntry>)` 与 `List<ZipEntry>` 泛型推断冲突，
   必须逐个 `add`（`javac` 报 `inference variable T has incompatible equality constraints`）。
2. 一开始用 Fabric intermediary `class_XXXX/method_YYYYY` 当身份，1.21.1 的 71190
   行只有 39310 行命中（`<init>` / `toString` / 部分库方法不在 tiny 成员表里），
   得到的 10.64% / 5.13% **已废弃，不可引用**。改用官方 ProGuard 真实名后才是上表。
3. ProGuard 左侧是点分真实名，替换描述符前必须先 `replace('.', '/')`，
   否则 `Lnet.minecraft.X;` 对不上 `Lnet/minecraft/X;`（历史踩坑，成员对齐率约 40%）。
4. 身份集合迭代顺序受 `PYTHONHASHSEED` 影响，输出必须 `sorted(...)` 才能跨次复现。
5. 混淆版 ↔ 去混淆版的 `call` 列含名字，天然不可比；本轮保守关闭，避免把命名
   断代误报成"实现变化"。

*数据来源：2026-11-14 本机四个真实 client jar 全量实跑，
`java/mcport/BodyHash.java` + `tools/drift_align.py`；参数化版重跑与首次实验
`drift-summary.json` 逐字段完全一致。*
