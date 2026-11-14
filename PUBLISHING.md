# 发布通道 / Publishing

本仓库是 McPort 工具链的**源码与测量产物**，采用 MIT 许可（见 `LICENSE`）。

| 内容 | 位置 |
| --- | --- |
| 源码、文档、测量数据 | GitHub: https://github.com/lilyco-42/mcport |
| 打包分发件 `mcport-0.1.0-dist.tar.gz` | Cloudflare R2 桶 `lain42-dl`，key `downloads/mcport/0.1.0/mcport-0.1.0-dist.tar.gz` |
| 下载入口 | https://lain42.top/downloads/ → 条目 `mcport`（经 `dl.lilyco42.top` 的 R2 签名票据通道加速，遵循站点积分规则） |
| R2 目录 | `catalog/downloads.json`（Worker `lain42-dl-gate` 运行时读取，60s 缓存） |

## 可复现性

* `bash demo/run.sh` 在本机四场景全绿（A 跑通 / B `NoSuchMethodError` /
  C 加 `-javaagent` 后同一份未改动 mod jar 救活 / D 无映射表 fail-loud）。
* `bash pipeline.sh <srcVer> <dstVer> <modsDir>` 与 `bash pipeline-26.sh` 需要
  自备对应版本的 client jar、intermediary jar 与官方 ProGuard 映射，脚本不会
  下载、也不会把它们写入仓库。

## 边界（务必阅读 REPORT.md §7）

静态符号可解析率 **不等于** 能在真实客户端运行。同名同签名语义漂移无法被
静态检测；Mixin refmap、反射字符串、真实客户端端到端验证均未覆盖。
本工具不做「任意版本都有效」的承诺。

## 回滚

站点条目在 `/var/www/studio/downloads/manifest.json`；R2 目录对象为
`catalog/downloads.json`。两者在发布时均留有 `.bak-mcport-*` 备份。
