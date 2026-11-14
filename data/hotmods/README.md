# 热门 mod 转移测量（4 个新增样本，1.21.1 Fabric）

输入为从 Modrinth 下载的 4 个真实 mod 的 1.21.1 Fabric 版本 jar，**仅在本机
`/tmp/mc/mods/hot/` 用于静态链接测量，不在本仓库内、也不对外分发**。

| 目标版本 | 转移前需人工 | 转移后需人工 | 说明 |
| --- | --- | --- | --- |
| 1.21.11 | 329 / 1162 | 319 / 1162 | 常规版本增益很小 |
| 26.1 | 1160 / 1166 | 331 / 1162 | 官方去混淆断代，建桥后 ≈0% → 60–74% |

`before-*.csv` / `after-*.csv` 是逐 mod 汇总；`*.json` 是逐条符号
（RESOLVE / RENAME / SIGCHG / MISSING / EXTERNAL）修复工单，由
`LinkCheck --json` 导出，供人工逐条修复。**这些工单是待办，不是已修复**。
`fabric-language-kotlin` 为纯 Kotlin 运行时库，0 条游戏引用，无需转移。

许可：ImmediatelyFast / YACL = LGPL-3.0-or-later，
fabric-language-kotlin = Apache-2.0，Xaero's Minimap = All-Rights-Reserved。

## 与 HostBridge 的关系（REPORT.md §9、§11）

8 份工单的 `details` 合计：**SIGCHG 173 / MISSING 477 / RENAME 0 / RESOLVE 1674 / EXTERNAL 56**。

* `SIGCHG` 的形态是「名字还在、描述符变了」，例如
  `RenderSystem.setProjectionMatrix(Matrix4f, class_8251)V` → 26.1 的第二参变成
  `com/mojang/blaze3d/vertex/VertexSorting`。**纯改名重映射改完仍然是 NoSuchMethodError**
  （demo E1 用最小复现自证）。HostBridge 提供的「宿主类定义前注入旧签名转发壳」是这类
  条目的可行机械路线，但**每一条仍需人写语义适配器**：旧参数怎么变成新调用无法推导。
  本仓库里 `demo/bridge-v2b.tsv` + `demo/src/adapter/demo/BlockAdapter.java` 是最小可编译范例，
   `demo/combo-*.tsv` + 场景 F 进一步验证「纯改名与 SIGCHG 同挂双 agent」可叠加（§11），
   但**都不等于这 173 条已经修好**：每条仍需人写语义适配器。
* `MISSING` 的 477 条里含「成员已删」与「owner 类不存在」，HostBridge 可以生成转发壳，
  但没有可转发的目标时仍必须改 mod 逻辑或放弃该版本 —— 这不是加载器能凭空补的。
* `RENAME 0` 是因为这些 jar 已经过离线重映射；原始未转移 jar 的改名条目见 `before-*.csv`。

结论不变：这些 JSON 是**待办工单**，不是已修复清单。
