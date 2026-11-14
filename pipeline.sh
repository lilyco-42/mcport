#!/usr/bin/env bash
# McPort 一键流水线：声明表 -> 重映射表 -> 预言机 -> 重映射 -> 复测 -> 工单
# 用法: bash pipeline.sh <srcVer> <dstVer> <modsDir>
#   例: bash pipeline.sh 1.21.1 1.21.11 /tmp/mc/mods/batch
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
WORK=${WORK:-/tmp/mcport-work}; mkdir -p "$WORK/remapped" "$WORK/out"
ASM=$(ls lib/asm-*.jar | tr "\n" ":")
JARS=${MCJARS:-/tmp/mc/jars}   # REAL-<ver>.jar（client jar）
INTERS=${INTERS:-/tmp/mc}      # i-<ver>.jar / inter-<ver>.jar（intermediary jar）

# 不同来源的中间名 jar 命名不一致，先找 client jar 目录再找 INTERS。
find_inter() {
  local v=$1 p
  for p in "$JARS/i-$v.jar" "$JARS/inter-$v.jar" "$INTERS/i-$v.jar" "$INTERS/inter-$v.jar"; do
    if [ -f "$p" ]; then echo "$p"; return 0; fi
  done
  echo "缺少 intermediary jar: $v" >&2; return 1
}
SRC_INTER=$(find_inter "$SRC"); DST_INTER=$(find_inter "$DST")

echo "== 1/8 生成目标版本声明表 =="
python3 tools/mkdecl.py --client "$JARS/REAL-$DST.jar" \
  --intermediary "$DST_INTER" --out "$WORK/out/decl-$DST.tsv"

echo "== 2/8 生成重映射表 =="
[ -f "$WORK/out/map-$SRC-$DST.tsv" ] || python3 tools/mkmap.py \
  "$SRC_INTER" "$DST_INTER" "$WORK/out/map-$SRC-$DST.tsv"

echo "== 3/8 预言机扫描（迁移前）=="
java -cp "build:$ASM" mcport.LinkCheck --decl "$WORK/out/decl-$DST.tsv" \
  --map "$WORK/out/map-$SRC-$DST.tsv" --mods "$MODS" --out "$WORK/out/before-$DST.csv"

echo "== 4/8 离线重映射 =="
: > "$WORK/out/remap.log"
for f in "$MODS"/*.jar; do
  java -cp "build:$ASM" mcport.RemapTool --map "$WORK/out/map-$SRC-$DST.tsv" \
    --in "$f" --out "$WORK/remapped/$(basename "$f")" 2>>"$WORK/out/remap.log"
done
echo "  重映射明细日志: $WORK/out/remap.log"

echo "== 5/8 字节码结构校验 =="
bad=0
for f in "$WORK"/remapped/*.jar; do
  java -cp "build:$ASM" mcport.Verifier --jar "$f" > "$WORK/out/verify-$(basename "$f").txt" || bad=$((bad+1))
done
echo "结构校验: $bad 个 jar 有坏 class"

echo
echo "== 6/8 Mixin 注解残留校验（第二预言机维度）=="
java -cp "build:$ASM" mcport.MixinCheck "$MODS"/*.jar > "$WORK/out/mixin-before.txt" || true
java -cp "build:$ASM" mcport.MixinCheck "$WORK"/remapped/*.jar > "$WORK/out/mixin-after.txt" || true
echo -n 'BEFORE '; head -1 "$WORK/out/mixin-before.txt"
echo -n 'AFTER  '; head -1 "$WORK/out/mixin-after.txt"


echo "== 7/8 复测 =="
java -cp "build:$ASM" mcport.LinkCheck --decl "$WORK/out/decl-$DST.tsv" \
  --mods "$WORK/remapped" --out "$WORK/out/after-$DST.csv"
echo
echo "== 8/8 生成迁移工单（每个 mod 一份 markdown）=="
for f in "$MODS"/*.jar; do
  b=$(basename "$f" .jar)
  java -cp "build:$ASM" mcport.LinkCheck --decl "$WORK/out/decl-$DST.tsv" \
    --map "$WORK/out/map-$SRC-$DST.tsv" --mod "$f" \
    --json "$WORK/out/report-$b.json" >/dev/null 2>&1 || true
  [ -f "$WORK/out/report-$b.json" ] && python3 tools/report.py "$WORK/out/report-$b.json" \
    > "$WORK/out/MIGRATION-$b.md"
done
echo "工单: $WORK/out/MIGRATION-*.md"
echo
echo "产物: $WORK/out/{decl,map}-*.tsv  {before,after}-$DST.csv  MIGRATION-*.md  remapped: $WORK/remapped/"

# 文档承诺的退出码：0 = 全部可自动处理；2 = 仍有 SIGCHG/MISSING 需人工。
# 从 after CSV 聚合（表头: mod,total,resolve,rename,sigchg,missing,external,judged,...）
NEED_MANUAL=$(awk -F, 'NR>1 && NF>=6 { s += $5 + $6 } END { print s+0 }' "$WORK/out/after-$DST.csv")
echo "需人工处理: $NEED_MANUAL 条 (SIGCHG + MISSING)"
if [ "$NEED_MANUAL" -gt 0 ]; then
  echo "== 结论: 存在需人工处理的引用, exit 2 =="
  exit 2
fi
echo "== 结论: 全部可自动处理, exit 0 =="
exit 0