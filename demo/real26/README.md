# 可选实验：真实 Minecraft 26.1 类 + JRE 25 + 启动期 `-javaagent`

对应 `REPORT.md` §12。**默认不运行**：需要使用者自备两个东西，缺任意一个脚本打印 `SKIP` 并返回 0，
因此 `bash demo/run.sh` 在纯 JDK 17 上的六场景可复现性完全不受影响。

```bash
# 1) 自备 26.1 client jar（本仓库/发布包都不含任何 Mojang 字节）
# 2) 自备 JRE 25；或让脚本按固定 sha256 从清华 Adoptium 镜像下载
MC_26_1_JAR=/path/to/26.1-client.jar \
JAVA25=/path/to/jre25/bin/java bash demo/real26/run.sh

# 或者：
MC_26_1_JAR=/path/to/26.1-client.jar MC_REAL26_AUTO_JRE=1 bash demo/real26/run.sh
```

`JAVA25` 未设置时，脚本会先探测 `/tmp/lead-jdk25/jdk-25.0.5+8-jre/bin/java` 与
`/tmp/mcport-real26-jre25/bin/java`。JRE 25 tarball 的 sha256 固定为
`6fac98f0c8202efc3135a9e9e42aa61963ec42d1c5cbb40caf231e7b14a24ef6`。

## 它证明什么 / 不证明什么

证明：真实 26.1 `class major 69` 类在 JRE 25 上可被 `premain` 阶段 `-javaagent` 编织、
通过 JVM 校验（含 `-Xverify:all`）与链接；`McPortRuntime`（改 mod 侧）与 `HostBridge`
（改宿主侧）双挂顺序无关；`-Dmcport.only` 能把改写锁在 mod 包；fail-loud 在 JRE 25 上仍成立。

**不证明**：任何真实 mod 能跑、真实客户端/Fabric 启动链、LWJGL/native 库加载、语义漂移、
173 条 SIGCHG 或 477 条 MISSING 已被修复。选的是无外部依赖的叶类，调用方是我们自编译的 stub。

## 文件

| 文件 | 作用 |
| --- | --- |
| `GpuOutOfMemoryException.java` | 仅编译期用的自有小 stub；`out/stub` 故意不放运行期 classpath |
| `Legacy.java` / `LegacyRename.java` | 旧调用方：SIGCHG 路径 / RENAME 路径 |
| `Probe.java` | 只 `Class.forName` 加载真实 major-69 类 |
| `Adapter.java` | 纯 JDK 语义适配器（无 LWJGL 依赖） |
| `DumpAgent.java` | 观察型 transformer，落盘前一个 agent 变换后的字节 |
| `Hello.java` | 与 26.1 类无关的类，用于 premain fail-loud 测试 |
| `bridge.tsv` / `map.tsv` | 一条宿主桥规则 / 一条纯改名映射 |
| `run.sh` | S0–S11 场景与断言，输出 `REAL26_OK` |

> premain 抛异常会让 JVM 以 native abort（rc=134）结束而非普通 Java 异常，
> 脚本已 `ulimit -c 0` 防止生成 core dump（REPORT §5 第 17 条）。
