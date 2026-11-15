# 统一严格引用解析器聚合数据说明（REPORT §22 / §23 / §24）

本目录只含**可分发聚合数字、格式口径与路径占位符**，不含 Mojang client jar、官方 ProGuard 映射、第三方 mod 字节码、完整 LinkCheck 工单之外的输入或 mod jar。`tools/test_parse_unified.py` 只读取仓库内已有的 `data/hotmods/*.json` 聚合工单与合成符号文本；它是纯标准库自包含回归，不需要网络、游戏 jar 或映射。

## 输入与判定

```bash
python3 tools/test_parse_unified.py
```

* `tools/capability.py:parse_ref` 是唯一严格 JVMS §4.3 语法实现；`tools/bridgegen.py` 与 `tools/relocate.py` 通过 `importlib.util` 委托它，不复制宽松正则。
* 对外形状保持兼容：bridgegen 返回 `(owner, name, desc, M|F)`，relocate 返回 `(owner, name, desc, is_field_bool)`；内部统一按 `(owner, name, desc, M|F)` 比较。
* 0.2.2 的 8 份真实工单在统一键下分别有 197 / 1 条工具间分歧；0.2.3 两版均为 0，三工具对每版 1190 行均返回非 `None`。
* 对象数组字段 `shaderLightDirections[Lorg/joml/Vector3f;` 的精确键是 `F|com/mojang/blaze3d/systems/RenderSystem|shaderLightDirections|[Lorg/joml/Vector3f;`，不再是旧解析器的 `shader` 或单字符 `;` 错键。
* `data/parse-unified-summary.csv` 两行分别记录 1.21.11 / 26.1 的 4 份工单、分桶计数、28 条 EXTERNAL 原始行去重为 27 键、1019 个非 EXTERNAL 唯一键，以及源文本固有歧义 3 / 51 条。
* `data/parse-unified-spec.example.json` 只有路径占位符；`tools/test_parse_unified.py` 的 114 断言同时覆盖委托调用、对象数组、构造器、非法描述符、坏类名、注释 / 箭头剥离和 8 份真实工单聚合。

## 边界

统一解析器消除的是**工具内部误切分**，不是 Mojang API 差异、不是语义漂移证明，更不是「任意版本都有效」。源文本歧义 3 / 51 仍按最长合法成员名启发式记录，绝不把启发式写成证明。§16 的 `auto_fixed=0`、字段一律 `REJECT_FIELD`、§15 只读 `details.MISSING` 与严格三级接受均不变；同名同签名 42 与 6 的语义漂移仍静态不可彻底判定。 §23 的 `LinkCheck --refs-json` 让**新工单**可输出精确五元组，`tools/refcheck.py` 不再靠启发式猜 `(name,desc)`；本目录记录的 8 份历史真实工单 3 / 51 条源文本固有歧义没有配套结构化 refs，字节又必须保持，故仍按启发式留档，见 `data/refcheck-summary.csv`。 §24 只扩展链接面到类引用，不改任何工单符号文本解析，也不把统一解析升级成运行期证明；见 `data/classref-summary.csv` / `classref-README.md`。
