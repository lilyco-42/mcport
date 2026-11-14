#!/usr/bin/env bash
# McPort 端到端演示: 一份未改动的 mod 二进制, 跨到新版本仍能跑。
#
#   A. 在 v1(源版本) 上跑        -> 正常
#   B. 同一份未改动 jar 在 v2 上跑 -> NoSuchMethodError (跨版本失效的第一性机制)
#   C. 同一份未改动 jar + -javaagent -> 跑通; 磁盘上的 jar 一个字节都没变
#   D. 不给映射表 -> 仍然 fail-loud, 不静默出错
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

rm -rf build && mkdir -p build/v1 build/v2 build/mod build/agent

echo "== 编译 v1 API 与 mod =="
$JAVAC -nowarn -d build/v1 src/v1/net/mc/*.java
$JAVAC -nowarn -cp build/v1 -d build/mod src/mod/demo/MyMod.java
(cd build/v1 && jar cf ../../api-v1.jar net/mc/*.class)
(cd build/mod && jar cf ../../mod-1.20.1.jar demo/*.class)

echo "== 编译 v2 API =="
$JAVAC -nowarn -d build/v2 src/v2/net/mc/*.java
(cd build/v2 && jar cf ../../api-v2.jar net/mc/*.class)

echo "== 编译 McPort 运行时 agent =="
$JAVAC -nowarn -cp "$ASM" -d build/agent ../java/mcport/Mapping.java ../java/mcport/MixinRewriter.java ../java/mcport/McPortRuntime.java
printf 'Premain-Class: mcport.McPortRuntime\nCan-Retransform-Classes: true\nBoot-Class-Path: libs/asm-9.9.jar libs/asm-commons-9.9.jar libs/asm-tree-9.9.jar\n' > build/agent/MANIFEST.MF
(cd build/agent && jar cfm ../../mcport-runtime.jar MANIFEST.MF mcport/*.class)

# 映射表: getBlock(int,int,int) -> getBlockState(int,int,int)
printf 'M\tnet/mc/World\t(III)I\tgetBlock\tgetBlockState\n' > map-v1-v2.tsv

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
echo "== C. 同一份二进制 + McPort 启动期 agent =="
$JAVA -javaagent:mcport-runtime.jar -Dmcport.map=map-v1-v2.tsv \
      -cp api-v2.jar:mod-1.20.1.jar demo.MyMod
echo "   mod jar sha1: $(sha1sum mod-1.20.1.jar | cut -d' ' -f1)"

echo
echo "== D. 不给映射表 -> fail-loud, 绝不静默猜名 =="
set +e
$JAVA -javaagent:mcport-runtime.jar -cp api-v2.jar:mod-1.20.1.jar demo.MyMod 2>&1 | head -3
set -e
echo
echo "OK"
