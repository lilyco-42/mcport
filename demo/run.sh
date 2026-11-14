#!/usr/bin/env bash
# McPort 端到端演示: 一份未改动的 mod 二进制, 跨到新版本仍能跑。
#
#   A. 在 v1(源版本) 上跑        -> 正常
#   B. 同一份未改动 jar 在 v2 上跑 -> NoSuchMethodError (跨版本失效的第一性机制)
#   C. 同一份未改动 jar + -javaagent 改 mod 侧引用 -> 跑通 (纯改名 RENAME 可解)
#   D. 不给映射表 -> fail-loud, 不静默出错
#   E. 连签名都改了 (SIGCHG) 的目标版本: 宿主侧兼容桥 HostBridge
#      E1 证明 C 的纯改名路线在 SIGCHG 上救不了
#      E2 同一份 mod jar + 宿主桥 -> 跑通, 且显式暴露语义漂移 (42 -> 6)
#      E3 证明"类已加载后再加方法"被 HotSpot 拒绝 -> 必须启动期 premain
set -e
cd "$(dirname "$0")"

# --- locale 自愈（REPORT §5 第 16 条）---
# JDK 用 sun.jnu.encoding 解码文件路径。若调用者 LANG/LC_ALL 为空或非 UTF-8
# （CI / 非 login shell 常见，本机实测 ANSI_X3.4-1968），中文工作目录会让 javac
# 报 "file not found: java/mcport/...java"。只在当前 locale 非 UTF-8 时切到可用
# UTF-8 locale；已经是 UTF-8 的环境一律不覆盖。
_cur_lc="${LC_ALL:-${LANG:-}}"
case "$_cur_lc" in
  *UTF-8*|*utf-8*|*utf8*|*UTF8*) ;;
  *)
    _avail_lc="$(locale -a 2>/dev/null || true)"
    _avail_lo="${_avail_lc,,}"
    for _cand in C.UTF-8 C.utf8 en_US.UTF-8 zh_CN.UTF-8; do
      case "$_avail_lo" in
        *"${_cand,,}"*) export LC_ALL="$_cand" LANG="$_cand"
                        echo "[mcport] locale -> $_cand (UTF-8 路径解码)"
                        break ;;
      esac
    done
    ;;
esac

ASM="libs/asm-9.9.jar:libs/asm-commons-9.9.jar:libs/asm-tree-9.9.jar"
JAVAC=${JAVAC:-javac}
JAVA=${JAVA:-java}

# --- 可复现构建：JDK 17+ 的 jar --date 固定条目时间戳 ---
# 不固定时每次 run.sh 重建的 demo jar 都带当前时间，sha1 会漂移，
# 既让 git 反复变脏，也让"可复现分发包"名不副实。旧 JDK 无 --date 时降级。
JAR_DATE=""
if jar --help 2>&1 | grep -q -- '--date='; then
  JAR_DATE="--date=2026-11-14T00:00:00Z"
fi

rm -rf build && mkdir -p build/v1 build/v2 build/v2b build/mod build/adapter \
                build/agent build/hostbridge build/probe

echo "== 编译 v1 API 与 mod =="
$JAVAC -nowarn -d build/v1 src/v1/net/mc/*.java
$JAVAC -nowarn -cp build/v1 -d build/mod src/mod/demo/MyMod.java
(cd build/v1 && jar --create --file=../../api-v1.jar $JAR_DATE net/mc/*.class)
(cd build/mod && jar --create --file=../../mod-1.20.1.jar $JAR_DATE demo/*.class)

echo "== 编译 v2 API =="
$JAVAC -nowarn -d build/v2 src/v2/net/mc/*.java
(cd build/v2 && jar --create --file=../../api-v2.jar $JAR_DATE net/mc/*.class)

echo "== 编译 McPort 运行时 agent =="
$JAVAC -nowarn -cp "$ASM" -d build/agent ../java/mcport/Mapping.java ../java/mcport/MixinRewriter.java ../java/mcport/McPortRuntime.java
printf 'Premain-Class: mcport.McPortRuntime\nCan-Retransform-Classes: true\nBoot-Class-Path: libs/asm-9.9.jar libs/asm-commons-9.9.jar libs/asm-tree-9.9.jar\n' > build/agent/MANIFEST.MF
(cd build/agent && jar --create --file=../../mcport-runtime.jar --manifest=MANIFEST.MF $JAR_DATE mcport/*.class)

# 映射表: getBlock(int,int,int) -> getBlockState(int,int,int)
printf 'M\tnet/mc/World\t(III)I\tgetBlock\tgetBlockState\n' > map-v1-v2.tsv

echo "== 编译 v2b (改名 + 改签名 = SIGCHG) 与语义适配器 =="
$JAVAC -nowarn -d build/v2b src/v2b/net/mc/*.java
(cd build/v2b && jar --create --file=../../api-v2b.jar $JAR_DATE net/mc/*.class)
$JAVAC -nowarn -cp build/v2b -d build/adapter src/adapter/demo/BlockAdapter.java

echo "== 编译宿主侧兼容桥 agent (HostBridge) =="
$JAVAC -nowarn -cp "$ASM" -d build/hostbridge ../java/mcport/HostBridge.java
printf 'Premain-Class: mcport.HostBridge\n' > build/hostbridge/MANIFEST.MF
(cd build/hostbridge && jar --create --file=../../build/hostbridge-runtime.jar --manifest=MANIFEST.MF $JAR_DATE mcport/*.class)

echo "== 编译 retransform 时序探针 =="
$JAVAC -nowarn -cp "$ASM" -d build/probe src/agent/demo/LimitAgent.java src/probe/demo/RetransformLimit.java
printf 'Premain-Class: demo.LimitAgent\nCan-Retransform-Classes: true\n' > build/probe/MANIFEST.MF
(cd build/probe && jar --create --file=../../build/limit-probe.jar --manifest=MANIFEST.MF $JAR_DATE demo/*.class)
echo "== 编译双 agent 组合实验 (RENAME + SIGCHG 同时出现) =="
mkdir -p build/v1c build/v2c build/modc build/adapterc
$JAVAC -nowarn -d build/v1c src/v1c/net/mc/*.java
$JAVAC -nowarn -cp build/v1c -d build/modc src/modc/demo/ComboMod.java
$JAVAC -nowarn -d build/v2c src/v2c/net/mc/*.java
$JAVAC -nowarn -cp build/v2c -d build/adapterc src/adapterc/demo/ComboAdapter.java
(cd build/modc && jar --create --file=../../build/combo-mod.jar $JAR_DATE demo/*.class)
(cd build/v2c && jar --create --file=../../build/combo-api-v2c.jar $JAR_DATE net/mc/*.class)

echo
echo "== A. 源版本 (1.20.1) =="
$JAVA -cp api-v1.jar:mod-1.20.1.jar demo.MyMod

echo
echo "== B. 同一份二进制, 新版本 (1.21.1) =="
set +e
$JAVA -cp api-v2.jar:mod-1.20.1.jar demo.MyMod 2>&1 | head -3
echo "   (退出码 ${PIPESTATUS[0]} —— 这正是跨版本失效的第一性机制)"
set -e

echo
echo "== C. 同一份二进制 + McPort 启动期 agent (改 mod 侧引用) =="
$JAVA -javaagent:mcport-runtime.jar -Dmcport.map=map-v1-v2.tsv \
      -cp api-v2.jar:mod-1.20.1.jar demo.MyMod
echo "   mod jar sha1: $(sha1sum mod-1.20.1.jar | cut -d' ' -f1)"

echo
echo "== D. 不给映射表 -> fail-loud, 绝不静默猜名 =="
set +e
$JAVA -javaagent:mcport-runtime.jar -cp api-v2.jar:mod-1.20.1.jar demo.MyMod 2>&1 | head -3
set -e

echo
echo "== E. SIGCHG 目标版本: 宿主侧兼容桥 HostBridge =="
echo
echo "-- E1. 纯改名路线 (C) 在连签名都变了的版本上失效 --"
set +e
$JAVA -javaagent:mcport-runtime.jar -Dmcport.map=map-v1-v2.tsv \
        -cp api-v2b.jar:mod-1.20.1.jar demo.MyMod > build/e1.out 2>&1
E1RC=$?
set -e
head -3 build/e1.out
echo "   (退出码 $E1RC ; 报错里是 getBlockState(III)I —— 名字改对了, 描述符仍对不上)"
[ "$E1RC" -ne 0 ] || { echo "FAIL E1: expected a link failure"; exit 1; }
grep -q 'getBlockState' build/e1.out || { echo "FAIL E1: expected renamed-but-wrong-descriptor error"; exit 1; }

echo
echo "-- E2. 同一份 mod jar + 宿主侧桥 -> 跑通 (mod 零改动) --"
S1=$(sha1sum mod-1.20.1.jar | cut -d' ' -f1)
set +e
$JAVA -javaagent:build/hostbridge-runtime.jar -Dmcport.bridge=bridge-v2b.tsv \
        -cp "$ASM:api-v2b.jar:build/adapter:mod-1.20.1.jar" demo.MyMod > build/e2.out 2>/dev/null
E2RC=$?
set -e
cat build/e2.out
S2=$(sha1sum mod-1.20.1.jar | cut -d' ' -f1)
echo "   mod jar sha1: $S1"
[ "$E2RC" -eq 0 ] || { echo "FAIL E2: bridge run failed (rc=$E2RC)"; exit 1; }
[ "$S1" = "$S2" ] || { echo "FAIL E2: mod jar changed on disk"; exit 1; }
grep -q 'block=6' build/e2.out || { echo "FAIL E2: bridge did not link"; exit 1; }
echo "   注意: 源版本 getBlock(1,2,3)=42, 这里=6 -> 名字与描述符都链接上了, 语义仍变了 (§1 第 3 层)"

echo
echo "-- E3. 时序铁律: 类已加载后 retransform 加方法被 HotSpot 拒绝 --"
set +e
$JAVA -javaagent:build/limit-probe.jar \
        -cp "$ASM:api-v2b.jar:build/limit-probe.jar" demo.RetransformLimit > build/e3.out 2>&1
E3RC=$?
set -e
cat build/e3.out
[ "$E3RC" -eq 0 ] || { echo "FAIL E3: probe crashed (rc=$E3RC)"; exit 1; }
grep -q 'attempted to add a method' build/e3.out \
  || { echo "FAIL E3: expected HotSpot to reject schema change"; exit 1; }
echo "   => 宿主桥必须在类定义前 (-javaagent premain) 注入, 不能运行时补"
echo

echo
echo "== F. 双 agent 组合: RENAME + SIGCHG 同时修 (REPORT §11) =="
COMBO_CP="$ASM:build/combo-api-v2c.jar:build/adapterc:build/combo-mod.jar"
COMBO_AGENT="-javaagent:mcport-runtime.jar -javaagent:build/hostbridge-runtime.jar"

echo
echo "-- F1. 只有 mod 侧重命名 agent -> SIGCHG 那条仍链接失败 --"
set +e
$JAVA -javaagent:mcport-runtime.jar -Dmcport.map=combo-map.tsv -cp "$COMBO_CP" demo.ComboMod > build/f1.out 2>&1
F1RC=$?
set -e
head -3 build/f1.out
[ "$F1RC" -ne 0 ] || { echo "FAIL F1: expected SIGCHG link failure"; exit 1; }
grep -q getBiome build/f1.out || { echo "FAIL F1: expected getBiome error"; exit 1; }

echo
echo "-- F2. 只有宿主侧桥 agent -> RENAME 那条仍链接失败 --"
set +e
$JAVA -javaagent:build/hostbridge-runtime.jar -Dmcport.bridge=combo-bridge.tsv -cp "$COMBO_CP" demo.ComboMod > build/f2.out 2>&1
F2RC=$?
set -e
head -3 build/f2.out
[ "$F2RC" -ne 0 ] || { echo "FAIL F2: expected RENAME link failure"; exit 1; }
grep -q getBlock build/f2.out || { echo "FAIL F2: expected getBlock error"; exit 1; }

echo
echo "-- F3. 双 agent + -Dmcport.only 限定 mod 类 -> 两条都修好, mod 零改动 --"
S1=$(sha1sum build/combo-mod.jar | cut -d' ' -f1)
set +e
$JAVA $COMBO_AGENT -Dmcport.map=combo-map.tsv -Dmcport.bridge=combo-bridge.tsv -Dmcport.only=demo/ComboMod -cp "$COMBO_CP" demo.ComboMod > build/f3.out 2>/dev/null
F3RC=$?
set -e
cat build/f3.out
S2=$(sha1sum build/combo-mod.jar | cut -d' ' -f1)
[ "$F3RC" -eq 0 ] || { echo "FAIL F3: combo run failed (rc=$F3RC)"; exit 1; }
[ "$S1" = "$S2" ] || { echo "FAIL F3: mod jar changed on disk"; exit 1; }
grep -q 'block=42 biome=6' build/f3.out || { echo "FAIL F3: both refs not linked"; exit 1; }
grep -q 'getBiome/3' build/f3.out || { echo "FAIL F3: bridge method absent"; exit 1; }
echo "   combo-mod sha1: $S1 (零改动) ; 源 42/7 -> 桥后 42/6, 语义漂移仍显式可见"

echo
echo "-- F4. agent 顺序反转 -> 结果不变 (两处改写落在不同类, 互不覆盖) --"
set +e
$JAVA -javaagent:build/hostbridge-runtime.jar -javaagent:mcport-runtime.jar -Dmcport.map=combo-map.tsv -Dmcport.bridge=combo-bridge.tsv -Dmcport.only=demo/ComboMod -cp "$COMBO_CP" demo.ComboMod > build/f4.out 2>/dev/null
F4RC=$?
set -e
cat build/f4.out
[ "$F4RC" -eq 0 ] || { echo "FAIL F4: reversed-order run failed"; exit 1; }
grep -q 'block=42 biome=6' build/f4.out || { echo "FAIL F4: order-dependent result"; exit 1; }
echo "   => 双 agent 组合可行且顺序无关; 纪律: -Dmcport.only 只授权 mod 包, 勿改到 adapter/共享类"
echo "OK"
