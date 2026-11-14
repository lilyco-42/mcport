# 严格 C 行类迁移补充（relocate）—— 数据说明

本目录的 `relocate-summary.csv` 只是**纯聚合数字**，来自 `tools/relocate.py` 在 8 份本机
LinkCheck 工单 + 两份目标版本声明表上的实跑（2026-11-15，REPORT.md §15）。
仓库与发布包**不含**任何 Mojang client jar 字节、官方 ProGuard 映射、intermediary jar、
完整 `bridge-*.tsv` 或第三方 mod 字节码；`supplement.tsv` / `accepted.tsv` 是运行时产物，
只写进调用方 `--out-dir` 指定的目录，从不入库。

## 输入（全部自备，运行时读）

| 输入 | 形态 | 来源 |
| --- | --- | --- |
| `--spec` JSON | `{schema:1, targets:[{version, decl, tickets:[...]}]}（见 `relocate-spec.example.json`） | 调用方 |
| 目标声明表 `decl-`ver`.tsv` | `C/S/M/F` 行，`M/F` 为 `owner/name/desc` | `tools/mkdecl.py` 从自备 client jar 生成 |
| LinkCheck 工单 `*.json` | `details.MISSING[]` 里的 `owner.name+desc  # 注释` 字符串 | `LinkCheck --json` |

## 输出（写到 `--out-dir/<version>/`）

* `supplement.tsv`：**仅 C 行** `C<oldOwner><newOwner>`，喂给 `RemapTool --map`。
* `accepted.tsv`：被接受的逐条引用（含重映射后的描述符），供审计。
* `stats.json` / `summary.csv`：分版本计数与拒绝原因。

## 三级严格判据（任一步不过就 fail-loud 拒绝，绝不静默猜）

1. **类级唯一同名投票**：只对「老 owner 不在目标 decl」的 MISSING 引用，找目标 decl 中
   同名同描述符成员所在的候选 owner；仅当 `simple(老owner) == simple(新owner)`
   且候选唯一才生成 `C` 行。不同简单名、歧义、`<init>`/`<clinit>` 一律拒绝。
2. **整张 C 行重映射描述符**：把字段类型/方法参数里的 `L<oldOwner>;` token 全表替换
   （5 轮收敛），否则内部类字段（如 `BLEND` 指向 `GlStateManager`$class_1017）会漏。
3. **目标直接声明校验**：`(newOwner, name, mappedDesc)` 必须在目标 decl 的 `M/F` 行
   **直接声明**，否则拒绝（成员在新类里也被删了）。

## 数字（`relocate-summary.csv`）

1.21.11：decl 类 10291，4 份工单共 220 条 MISSING，生成 4 条 C 行，接受 29 条；
26.1：decl 类 10682，4 份工单共 257 条 MISSING，生成 1 条 C 行，接受 19 条。
**合计 48 条**（不是 Round 2 粗估的 44）。两版本 `ambiguous=0`、`parse_fail=0`、
`constructor_rejected=0`；`owner_exists` 是老类仍在 decl（属别的问题，不归迁移），
`no_strict_c_line` 是没有严格同名类的换包候选，`no_exact_mapped_decl` 是搬过去后成员也已被删。

端到端复测（`RemapTool` 改字节码后无 `--map` 复测）桶转移：
1.21.11 `MISSING→RESOLVE 29` / `MISSING→SIGCHG 2`；26.1 `MISSING→RESOLVE 19` / `MISSING→SIGCHG 4`。
那 6 条 `MISSING→SIGCHG` 是 `_clear(IZ)V`、`_texImage2D(...IntBuffer;)V`、
`BLEND`/`DEPTH` 等：新类里同名但描述符也变，LinkCheck 诚实地重新判成需人工，
**机械迁移没有把它们洗白**。

口径区分（别混）：`different_simple_rejected`（6 / 24）是生成器统计的「有同名同描述符候选
但简单名不同」的引用数；7 类危险关键字样本（`GuiGraphics.bufferSource`、
`FastColor$ARGB32.multiply` 等）在复测工单里 4 / 9 条仍判 MISSING，
证明不同简单名误配没有被迁移成 RESOLVE；Round 2 的「13 条危险误配」是 57 条唯一候选里
`DIFFERENT_SIMPLE` 的条目数，三者分母不同，都是「拒绝」方向的证据。

## 复现（自备制品，脚本不下载不入库）

```bash
python3 tools/test_relocate.py                 # 27 条自包含断言（合成 decl/工单）
python3 tools/relocate.py --spec /work/spec.json --out-dir /work/gen
# 对每个 version，把 gen/<v>/supplement.tsv 喂给 RemapTool，再无 --map 复测：
javac -nowarn -cp 'lib/*' -d build java/mcport/*.java
java -cp 'build:lib/*' mcport.RemapTool --map /work/gen/<v>/supplement.tsv \
  --in /work/remapped-<v>/mod.jar --out /work/fixed-<v>/mod.jar
java -cp 'build:lib/*' mcport.LinkCheck --decl /path/to/decl-<v>.tsv \
  --mod /work/fixed-<v>/mod.jar --json /work/fixed-<v>/mod.json
```

## 踩坑（真事）

* 第一版逐条独立匹配用了只认 `(...)` 结尾的方法正则，漏掉 `()V`/`(I)I` 带返回类型与字段描述符，
  477 条里 404 条 parse fail；必须复用 `^(.+?)\.([^.(]+)(\(.*\).*)$` 且字段单独一支。
* 逐条独立匹配会漏掉字段 desc 里的旧包 token，改成**先类级投票生成整张 C 行、再重映射描述符**才救回内部类字段。
* 把候选全集打印出来会截断输出（26.1 的 `<init>()V` 有 1765 个不同简单名候选），只打印计数。
* 端到端脚本里 `assert delta[sigchg]==0` 断言写太严而失败：6 条诚实地转成 SIGCHG 属预期，非工具 bug。

## 边界

48 条只是**符号可解析候选**，不证明行为等价、不证明能在真实客户端跑。
173 条 SIGCHG + 477 条 MISSING 的主体仍需人工；语义漂移（§13）、Mixin refmap、
反射字符串、真实客户端端到端、26.x 需 JDK 25，全都没被本章收窄。
