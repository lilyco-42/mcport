#!/usr/bin/env bash
# McPort 26.x 专用流水线：官方 ProGuard × Fabric intermediary 重建身份桥。
# 用法: bash pipeline-26.sh <srcVer> <dstVer> <modsDir> [lastVerWithProguard]
#   例: bash pipeline-26.sh 1.21.1 26.1 /tmp/mc/mods/batch
#   默认第 4 参数 = 1.21.11（最后一个仍有官方 ProGuard 映射的版本）。
#
# 输入（默认路径，可用环境变量覆盖；脚本不下载、不打包、不分发任何映射表）：
#   MCJARS=/tmp/mc/jars      REAL-<ver>.jar
#   INTERS=/tmp/mc           i-<ver>.jar / inter-<ver>.jar
#   MAPS=/tmp/mc             map-<ver>.txt（Mojang 官方 ProGuard 映射）
#   WORK=/tmp/mcport-work-26
# 许可见 data/NOTICE-mappings.md：官方映射禁止完整未修改再分发。
set -euo pipefail
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
SRC=${1:?src version}; DST=${2:?dst version}; MODS=${3:?mods dir}
LAST=${4:-1.21.11}
MCJARS=${MCJARS:-/tmp/mc/jars}
INTERS=${INTERS:-/tmp/mc}
MAPS=${MAPS:-/tmp/mc}
WORK=${WORK:-/tmp/mcport-work-26}
OUT="$WORK/out"; REM="$WORK/remapped"
mkdir -p "$OUT" "$REM" build
ASM=$(ls lib/asm-*.jar | tr "\n" ":")

# 同一个版本在不同来源里可能叫 i-<ver>.jar 或 inter-<ver>.jar；先找 client jar 目录再找 INTERS。
find_inter() {
  local v=$1 p
  for p in "$MCJARS/i-$v.jar" "$MCJARS/inter-$v.jar" "$INTERS/i-$v.jar" "$INTERS/inter-$v.jar"; do
    if [ -f "$p" ]; then echo "$p"; return 0; fi
  done
  echo "缺少 intermediary jar: $v (找过 $MCJARS 与 $INTERS)" >&2; return 1
}
require() { [ -f "$1" ] || { echo "缺少输入文件: $1" >&2; exit 1; }; }

echo "== 1/9 输入自检 + 编译 =="
SRC_INTER=$(find_inter "$SRC"); LAST_INTER=$(find_inter "$LAST"); DST_INTER=$(find_inter "$DST")
require "$MCJARS/REAL-$SRC.jar"; require "$MCJARS/REAL-$DST.jar"
require "$MAPS/map-$SRC.txt"; require "$MAPS/map-$LAST.txt"
echo "  src=$SRC last=$LAST dst=$DST"
echo "  inter: $SRC_INTER | $LAST_INTER | $DST_INTER"
javac -nowarn -cp 'lib/*' -d build java/mcport/*.java
echo "  javac OK (Mapping / MixinRewriter 共用实现)"

echo
echo "== 2/9 生成目标版本声明表（含 com/mojang/）=="
python3 tools/mkdecl.py --client "$MCJARS/REAL-$DST.jar" \
  --intermediary "$DST_INTER" --out "$OUT/decl-$DST.tsv"

echo
echo "== 3/9 生成源版本声明表（S 行父类链）=="
python3 tools/mkdecl.py --client "$MCJARS/REAL-$SRC.jar" \
  --intermediary "$SRC_INTER" --out "$OUT/decl-$SRC.tsv"
echo -n "  decl-$DST classes: "; grep -c '^C' "$OUT/decl-$DST.tsv" || true
echo -n "  decl-$SRC supers:  "; grep -c '^S' "$OUT/decl-$SRC.tsv" || true

echo
echo "== 4/9 建两版 inter -> Mojang 真实名桥 =="
PYTHONHASHSEED=0 python3 tools/bridge.py --proguard "$MAPS/map-$SRC.txt" \
  --intermediary "$SRC_INTER" --out "$OUT/bridge-$SRC.tsv" --tsv
PYTHONHASHSEED=0 python3 tools/bridge.py --proguard "$MAPS/map-$LAST.txt" \
  --intermediary "$LAST_INTER" --out "$OUT/bridge-$LAST.tsv" --tsv

echo
echo "== 5/9 合成 26.x 专用表（版本择一 + 重定位 + S 行）=="
PYTHONHASHSEED=0 python3 tools/bridge26.py \
  --bridge "$OUT/bridge-$SRC.tsv" --bridge "$OUT/bridge-$LAST.tsv" \
  --src-decl "$OUT/decl-$SRC.tsv" --dst-decl "$OUT/decl-$DST.tsv" \
  --out "$OUT/bridge-$DST.tsv"

echo
echo "== 6/9 迁移前基线（不给 --map，原样搬运判定）=="
java -cp "build:$ASM" mcport.LinkCheck --decl "$OUT/decl-$DST.tsv" \
  --mods "$MODS" --out "$OUT/before-$DST.csv" 2>&1 | tail -3

echo
echo "== 7/9 离线重映射（映射 + 继承 BFS + Mixin 注解字符串）=="
for f in "$MODS"/*.jar; do
  java -cp "build:$ASM" mcport.RemapTool --map "$OUT/bridge-$DST.tsv" \
    --in "$f" --out "$REM/$(basename "$f")" 2>>"$OUT/remap.log"
done
echo -n "  remapped jars: "; ls -1 "$REM"/*.jar | wc -l

echo
echo "== 8/9 三重校验：Verifier / MixinCheck / LinkCheck 复测 =="
bad=0
for f in "$REM"/*.jar; do
  java -cp "build:$ASM" mcport.Verifier --jar "$f" > "$OUT/verify-$(basename "$f").txt" 2>&1 || bad=$((bad+1))
done
echo "  Verifier: $bad 个 jar 有坏 class（jei 的 1 个为基线既有，见 REPORT §8.5）"
java -cp "build:$ASM" mcport.MixinCheck "$MODS"/*.jar > "$OUT/mixin-before.txt" || true
java -cp "build:$ASM" mcport.MixinCheck "$REM"/*.jar > "$OUT/mixin-after.txt" || true
echo -n '  Mixin BEFORE '; head -1 "$OUT/mixin-before.txt"
echo -n '  Mixin AFTER  '; head -1 "$OUT/mixin-after.txt"
java -cp "build:$ASM" mcport.LinkCheck --decl "$OUT/decl-$DST.tsv" \
  --mods "$REM" --out "$OUT/after-$DST.csv" 2>&1 | tail -3

echo
echo "== 9/9 迁移工单（基于重映射后 jar，列出真正剩余问题）=="
for f in "$REM"/*.jar; do
  b=$(basename "$f" .jar)
  java -cp "build:$ASM" mcport.LinkCheck --decl "$OUT/decl-$DST.tsv" --mod "$f" \
    --json "$OUT/report-$b.json" >/dev/null 2>&1 || true
  [ -f "$OUT/report-$b.json" ] && python3 tools/report.py "$OUT/report-$b.json" > "$OUT/MIGRATION-$b.md"
done
echo "  工单: $OUT/MIGRATION-*.md"
echo
echo "产物: $OUT/{decl,bridge}-*.tsv  {before,after}-$DST.csv  MIGRATION-*.md  remapped: $REM/"

# 与 pipeline.sh 相同的退出码约定
NEED_MANUAL=$(awk -F, 'NR>1 && NF>=6 { s += $5 + $6 } END { print s+0 }' "$OUT/after-$DST.csv")
echo "需人工处理: $NEED_MANUAL 条 (SIGCHG + MISSING)"
if [ "$NEED_MANUAL" -gt 0 ]; then echo "== 结论: 仍需人工介入, exit 2 =="; exit 2; fi
echo "== 结论: 全部可自动处理, exit 0 =="; exit 0
