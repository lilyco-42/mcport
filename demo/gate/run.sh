#!/usr/bin/env bash
# LinkGate 启动期能力闸门端到端实验 (REPORT §19 / §20).
# 所有产物在 demo/gate/build/（gitignore），不触碰 demo/*.jar tracked 二进制。
# 固定 jar --date，保证两次运行产物字节一致；mod jar 在所有场景前后 sha1 不变。
set -e
cd "$(dirname "$0")"

_cur_lc="${LC_ALL:-${LANG:-}}"
case "$_cur_lc" in
  *UTF-8*|*utf-8*|*utf8*|*UTF8*) ;;
  *)
    _avail="$(locale -a 2>/dev/null || true)"
    _lo="${_avail,,}"
    for _c in C.UTF-8 C.utf8 en_US.UTF-8 zh_CN.UTF-8; do
      case "$_lo" in *"${_c,,}"*) export LC_ALL="$_c" LANG="$_c"; break;; esac
    done
    ;;
esac

JAVAC=${JAVAC:-javac}
JAVA=${JAVA:-java}
JAR_DATE=""
if jar --help 2>&1 | grep -q -- '--date='; then JAR_DATE="--date=2026-11-15T00:00:00Z"; fi

rm -rf build && mkdir -p build/api build/api2 build/mod build/agent

echo "== 编译 gate API / 语义漂移版 API / mod / LinkGate =="
$JAVAC -nowarn -d build/api src/gateapi/net/mc/*.java
$JAVAC -nowarn -d build/api2 src/gateapi2/net/mc/*.java
$JAVAC -nowarn -cp build/api -d build/mod src/gatemod/demo/*.java
$JAVAC -nowarn -d build/agent ../../java/mcport/LinkGate.java
(cd build/api && jar --create --file=../gate-api.jar $JAR_DATE net/mc/*.class)
(cd build/api2 && jar --create --file=../gate-api2.jar $JAR_DATE net/mc/*.class)
(cd build/mod && jar --create --file=../gate-mod.jar $JAR_DATE demo/*.class)
printf 'Premain-Class: mcport.LinkGate\n' > build/agent/MANIFEST.MF
(cd build/agent && jar --create --file=../linkgate.jar --manifest=MANIFEST.MF $JAR_DATE mcport/*.class)

API=build/gate-api.jar
API2=build/gate-api2.jar
MOD=build/gate-mod.jar
AG=build/linkgate.jar
CP="$API:$MOD"
CP2="$API2:$MOD"
S0=$(sha256sum "$MOD" | cut -d' ' -f1)
echo "   mod sha256(before)=$S0"

CHECKS=0
fact() { echo "GATE_FACT $1"; }
ck() {
  local label="$1"; shift
  CHECKS=$((CHECKS+1))
  if "$@"; then echo "GATE_ASSERT $CHECKS $label OK";
  else echo "GATE_ASSERT $CHECKS $label FAIL"; exit 1; fi
}
eq() { [ "$1" = "$2" ]; }
has() { grep -q -F -- "$2" "$1"; }
nhas() { ! grep -q -F -- "$2" "$1"; }
run() {
  local name="$1"; shift
  set +e
  "$@" > "build/$name.out" 2> "build/$name.err"
  local rc=$?
  set -e
  echo "$rc" > "build/$name.rc"
  fact "$name.rc=$rc"
}
rc() { cat "build/$1.rc"; }
ck_rc() { ck "$1" eq "$(rc "$2")" "$3"; }
ck_has() { ck "$1" has "build/$2.$3" "$4"; }
ck_nhas() { ck "$1" nhas "build/$2.$3" "$4"; }

echo
echo "== G1. 无闸门基线：源 API，mod 正常链接 =="
run G1 "$JAVA" -cp "$CP" demo.GateMod
ck_rc G1_rc_0 G1 0
ck_has G1_stdout_42 G1 out "gatemod block=42"
ck_nhas G1_stderr_gate G1 err "[linkgate]"

echo "== G2. RESOLVE contract：闸门 PASS，主程序照常运行 =="
run G2 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-resolve.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G2_rc_0 G2 0
ck_has G2_stdout_42 G2 out "gatemod block=42"
ck_has G2_pass G2 err "[linkgate] PASS"
ck_has G2_scanned_2 G2 err "scanned 2 classes"
ck_has G2_blockers_0 G2 err "blockers=0"

echo "== G3. MISSING contract + reject（默认）：干净拒绝，主程序一行业务输出都没有 =="
run G3 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-missing.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G3_rc_2 G3 2
ck_has G3_reject G3 err "[linkgate] REJECT"
ck_has G3_blocker G3 err "BLOCKER: net/mc/World|getBlock|(III)I -> MISSING"
ck G3_no_pass_marker nhas "build/G3.err" "[linkgate] PASS"
ck G3_stdout_empty eq "$(cat build/G3.out)" ""
ck G3_no_native_abort nhas "build/G3.err" "FATAL ERROR in native method"
ck G3_no_jvm_assert nhas "build/G3.err" "ASSERTION FAILED"

echo "== G4. 同一 MISSING + policy=warn：不拒绝，但明确 WARN 且业务照跑（不是静默放行） =="
run G4 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-missing.tsv -Dmcport.gate.modjar="$MOD" -Dmcport.gate.policy=warn -cp "$CP" demo.GateMod
ck_rc G4_rc_0 G4 0
ck_has G4_stdout_42 G4 out "gatemod block=42"
ck_has G4_warn G4 err "[linkgate] WARN: 1"
ck_has G4_pass G4 err "[linkgate] PASS"

echo "== G5. 缺 modjar 参数：缺省必拒（fail-loud，不假装扫过） =="
run G5 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-resolve.tsv -cp "$CP" demo.GateMod
ck_rc G5_rc_2 G5 2
ck_has G5_required G5 err "both required"
ck G5_no_main eq "$(cat build/G5.out)" ""

echo "== G6. 缺 contract 参数：同样拒绝 =="
run G6 "$JAVA" -javaagent:"$AG" -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G6_rc_2 G6 2
ck_has G6_required G6 err "both required"

echo "== G7. contract 文件不存在：IOException 被转成干净 rc=2，不触发 premain 抛异常/native abort =="
run G7 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-absent.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G7_rc_2 G7 2
ck_has G7_fail G7 err "[linkgate] FAIL"
ck G7_no_abort nhas "build/G7.err" "FATAL ERROR in native method"

echo "== G8. mod jar 不存在：同样干净拒绝 =="
run G8 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-resolve.tsv -Dmcport.gate.modjar=build/no-such-mod.jar -cp "$CP" demo.GateMod
ck_rc G8_rc_2 G8 2
ck_has G8_fail G8 err "[linkgate] FAIL"

echo "== G9. status 小写 + 不足 4 列的噪声行：大小写不敏感、噪声忽略、仍阻断 =="
run G9 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-lowercase.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G9_rc_2 G9 2
ck_has G9_blocker_upper G9 err "-> MISSING"
ck_has G9_reject G9 err "[linkgate] REJECT"

echo "== G10. SIGCHG：与 MISSING 同属硬阻断（人工桥必须显式 opt-in） =="
run G10 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-sigchg.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G10_rc_2 G10 2
ck_has G10_blocker G10 err "-> SIGCHG"

echo "== G11. RENAME：只提示可机械修复，不阻断 =="
run G11 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-rename.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G11_rc_0 G11 0
ck_has G11_rename_1 G11 err "rename=1"
ck_has G11_pass G11 err "[linkgate] PASS"

echo "== G12. 未知 policy：fail-closed 按 reject，不因拼写错误放行 =="
run G12 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-missing.tsv -Dmcport.gate.modjar="$MOD" -Dmcport.gate.policy=BOGUS -cp "$CP" demo.GateMod
ck_rc G12_rc_2 G12 2
ck_has G12_reject G12 err "[linkgate] REJECT"

echo "== G13. -javaagent:...=<contract> 参数形式（不写 -Dmcport.gate）也能取到契约 =="
run G13 "$JAVA" -javaagent:"$AG=contract-rename.tsv" -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G13_rc_0 G13 0
ck_has G13_rename_1 G13 err "rename=1"
ck_has G13_pass G13 err "[linkgate] PASS"

echo "== G14. 双槽 Long/Double + modified UTF-8 NUL 后的成员引用仍被精确扫出 =="
run G14 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-wide-missing.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G14_rc_2 G14 2
ck_has G14_scanned_2 G14 err "scanned 2 classes"
ck_has G14_wide_blocker G14 err "BLOCKER: java/lang/String|length|()I -> MISSING"
ck_has G14_blocker_world G14 err "BLOCKER: net/mc/World|getBlock|(III)I -> MISSING"
ck_has G14_blockers_2 G14 err "blockers=2"

echo "== G15. 语义漂移铁证：同名同签名、contract=RESOLVE、闸门 PASS、完全链接，结果 42 -> 6 =="
run G15 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-resolve.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP2" demo.GateMod
ck_rc G15_rc_0 G15 0
ck_has G15_pass G15 err "[linkgate] PASS"
ck_has G15_stdout_6 G15 out "gatemod block=6"
ck G15_no_42 nhas "build/G15.out" "block=42"
ck G15_no_link_error nhas "build/G15.err" "NoSuchMethodError"
echo "   => JVMS §5.4.3 链接全通过；静态/启动期闸门无法证明语义一致（§1 第 3 层）"

S1=$(sha256sum "$MOD" | cut -d' ' -f1)
echo "   mod sha256(after)=$S1"
ck G15_mod_zero_change eq "$S0" "$S1"
fact "mod.sha256=$S1"
fact "agent.jar=$(sha256sum "$AG" | cut -d' ' -f1)"
fact "api.jar=$(sha256sum "$API" | cut -d' ' -f1)"
fact "api2.jar=$(sha256sum "$API2" | cut -d' ' -f1)"
echo
echo "== G16. 真实 26.1 工单 -> 契约 -> JVM premain 闸门（零 Mojang 字节） =="
mkdir -p build/stubapi/com/mojang/blaze3d/platform build/stubmod/demo/stub
cat > build/stubapi/com/mojang/blaze3d/platform/GlStateManager.java <<'JAVA'
package com.mojang.blaze3d.platform;
// Synthetic compile-time signature-only placeholder. NOT Mojang code or bytes.
public final class GlStateManager {
    public static void _activeTexture(int unit) {}
}
JAVA
cat > build/stubmod/demo/stub/StubCall.java <<'JAVA'
package demo.stub;
public final class StubCall {
    public static void touch() {
        com.mojang.blaze3d.platform.GlStateManager._activeTexture(1);
    }
}
JAVA
$JAVAC -nowarn -d build/stubapi build/stubapi/com/mojang/blaze3d/platform/GlStateManager.java
$JAVAC -nowarn -cp build/stubapi -d build/stubmod build/stubmod/demo/stub/StubCall.java
(cd build/stubmod && jar --create --file=../gate-stub.jar $JAR_DATE demo/stub/*.class)
python3 ../../tools/linkgate_contract.py --ticket '../../data/hotmods/26.1__*.json' --version 26.1 --out build/contract-26.1.tsv --summary build/contract-26.1.csv
python3 ../../tools/linkgate_contract.py --ticket '../../data/hotmods/26.1__*.json' --version 26.1 --out build/contract-26.1b.tsv --summary build/contract-26.1b.csv >/dev/null
ck G16_contract_deterministic eq "$(cmp -s build/contract-26.1.tsv build/contract-26.1b.tsv; echo $?)" 0
ck G16_summary_version has build/contract-26.1.csv "26.1"
ck G16_summary_counts has build/contract-26.1.csv "26.1,4,1190,28,1019,143,728,0,68,223"
ck G16_contract_no_arrow nhas build/contract-26.1.tsv " -> "
ck G16_contract_exact_ref has build/contract-26.1.tsv "$(printf 'com/mojang/blaze3d/platform/GlStateManager\t_activeTexture\t(I)V\tMISSING')"
S_STUB0=$(sha256sum build/gate-stub.jar | cut -d' ' -f1)
echo "   stub sha256(before)=$S_STUB0"

echo "-- G16B: 真实契约扫 demo mod（未知引用默认 RESOLVE）--"
run G16B "$JAVA" -javaagent:"$AG" -Dmcport.gate=build/contract-26.1.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G16B_rc_0 G16B 0
ck_has G16B_pass G16B err "[linkgate] PASS"
ck_has G16B_blockers_0 G16B err "blockers=0"
ck_has G16B_stdout_42 G16B out "gatemod block=42"

echo "-- G16C: 真实契约扫含 MISSING 引用的合成 stub jar：premain 拒绝启动 --"
run G16C "$JAVA" -javaagent:"$AG" -Dmcport.gate=build/contract-26.1.tsv -Dmcport.gate.modjar=build/gate-stub.jar -cp "$CP" demo.GateMod
ck_rc G16C_rc_2 G16C 2
ck_has G16C_scanned_1 G16C err "scanned 1 classes"
ck_has G16C_blockers_1 G16C err "blockers=1"
ck_has G16C_blocker G16C err "BLOCKER: com/mojang/blaze3d/platform/GlStateManager|_activeTexture|(I)V -> MISSING"
ck_has G16C_reject G16C err "[linkgate] REJECT"
ck G16C_stdout_empty eq "$(cat build/G16C.out)" ""
ck G16C_no_link_error nhas "build/G16C.err" "java.lang.NoSuchMethodError"
ck G16C_no_abort nhas "build/G16C.err" "FATAL ERROR in native method"

echo "-- G16D: policy=warn 只豁免已知 blocker，业务照跑且明确 WARN --"
run G16D "$JAVA" -javaagent:"$AG" -Dmcport.gate=build/contract-26.1.tsv -Dmcport.gate.modjar=build/gate-stub.jar -Dmcport.gate.policy=warn -cp "$CP" demo.GateMod
ck_rc G16D_rc_0 G16D 0
ck_has G16D_warn G16D err "[linkgate] WARN: 1"
ck_has G16D_pass G16D err "[linkgate] PASS"
ck_has G16D_stdout_42 G16D out "gatemod block=42"
S_STUB1=$(sha256sum build/gate-stub.jar | cut -d' ' -f1)
ck G16_stub_zero_change eq "$S_STUB0" "$S_STUB1"
fact "stub.sha256=$S_STUB1"

echo "== G17. policy=warn 不豁免缺参数：配置错误一律干净拒绝 =="
run G17 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-resolve.tsv -Dmcport.gate.policy=warn -cp "$CP" demo.GateMod
ck_rc G17_rc_2 G17 2
ck_has G17_required G17 err "both required"
ck G17_stdout_empty eq "$(cat build/G17.out)" ""

echo "== G18. policy=warn 不豁免读表失败：无法扫描就拒绝 =="
run G18 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-absent.tsv -Dmcport.gate.modjar="$MOD" -Dmcport.gate.policy=warn -cp "$CP" demo.GateMod
ck_rc G18_rc_2 G18 2
ck_has G18_fail G18 err "[linkgate] FAIL"
ck G18_stdout_empty eq "$(cat build/G18.out)" ""

echo
echo "== G19. 契约版本绑定：匹配放行、错版/无头拒绝 =="
run G19_ok "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-26.1-head.tsv -Dmcport.gate.version=26.1 -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G19_ok_rc_0 G19_ok 0
ck_has G19_ok_version G19_ok err "[linkgate] version=26.1 OK"
ck_has G19_ok_pass G19_ok err "[linkgate] PASS"
ck_has G19_ok_stdout_42 G19_ok out "gatemod block=42"
run G19_wrong "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-26.1-head.tsv -Dmcport.gate.version=1.21.11 -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G19_wrong_rc_2 G19_wrong 2
ck_has G19_wrong_fail G19_wrong err "contract version mismatch: expected=1.21.11 contract=26.1"
ck_nhas G19_wrong_no_pass G19_wrong err "[linkgate] PASS"
ck G19_wrong_stdout_empty eq "$(cat build/G19_wrong.out)" ""
ck G19_wrong_no_abort nhas build/G19_wrong.err "FATAL ERROR in native method"
run G19_nohead "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-versionless.tsv -Dmcport.gate.version=26.1 -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G19_nohead_rc_2 G19_nohead 2
ck_has G19_nohead_fail G19_nohead err "contract has no version header"
ck G19_nohead_stdout_empty eq "$(cat build/G19_nohead.out)" ""

echo "== G20. 空 jar / 无 class 一律拒绝（消除 scans=0 假放行）=="
mkdir -p build/emptydir
printf 'no class entries\n' > build/emptydir/readme.txt
(cd build && jar --create --file=gate-empty.jar $JAR_DATE -C emptydir readme.txt)
printf 'not a zip\n' > build/gate-nonjar.bin
run G20 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-resolve.tsv -Dmcport.gate.modjar=build/gate-empty.jar -cp "$CP" demo.GateMod
ck_rc G20_rc_2 G20 2
ck_has G20_fail G20 err "mod jar contains no class entries"
ck G20_stdout_empty eq "$(cat build/G20.out)" ""
run G20_warn "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-resolve.tsv -Dmcport.gate.modjar=build/gate-empty.jar -Dmcport.gate.policy=warn -cp "$CP" demo.GateMod
ck_rc G20_warn_rc_2 G20_warn 2
ck_has G20_warn_fail G20_warn err "mod jar contains no class entries"
ck G20_warn_stdout_empty eq "$(cat build/G20_warn.out)" ""
run G20_nonjar "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-resolve.tsv -Dmcport.gate.modjar=build/gate-nonjar.bin -cp "$CP" demo.GateMod
ck_rc G20_nonjar_rc_2 G20_nonjar 2
ck_has G20_nonjar_fail G20_nonjar err "mod jar contains no class entries"
ck G20_nonjar_stdout_empty eq "$(cat build/G20_nonjar.out)" ""

echo "== G21. 契约行冲突 / 坏 digest 头：读表失败即拒绝 =="
run G21_conflict "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-conflict.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G21_conflict_rc_2 G21_conflict 2
ck_has G21_conflict_fail G21_conflict err "conflicting status for net/mc/World|getBlock|(III)I"
ck G21_conflict_stdout_empty eq "$(cat build/G21_conflict.out)" ""
run G21_digest "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-bad-digest.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G21_digest_rc_2 G21_digest 2
ck_has G21_digest_fail G21_digest err "bad source_sha256 header"
ck G21_digest_stdout_empty eq "$(cat build/G21_digest.out)" ""

echo "== G22. warn 不豁免版本绑定错误；真实 26.1 契约 + 正确版本放行 =="
run G22_warn "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-26.1-head.tsv -Dmcport.gate.version=1.21.11 -Dmcport.gate.modjar="$MOD" -Dmcport.gate.policy=warn -cp "$CP" demo.GateMod
ck_rc G22_warn_rc_2 G22_warn 2
ck_has G22_warn_fail G22_warn err "contract version mismatch"
ck G22_warn_stdout_empty eq "$(cat build/G22_warn.out)" ""
run G22_real "$JAVA" -javaagent:"$AG" -Dmcport.gate=build/contract-26.1.tsv -Dmcport.gate.version=26.1 -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G22_real_rc_0 G22_real 0
ck_has G22_real_version G22_real err "[linkgate] version=26.1 OK"
ck_has G22_real_pass G22_real err "[linkgate] PASS"
ck_has G22_real_stdout_42 G22_real out "gatemod block=42"

S1=$(sha256sum "$MOD" | cut -d' ' -f1)
ck G22_mod_zero_change eq "$S0" "$S1"
fact "mod.sha256.final=$S1"

echo
echo "== G23. 状态拼写错误静默放行被封死：unknown status 必须 FAIL =="
run G23 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-bad-status.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G23_rc_2 G23 2
ck_has G23_fail G23 err "unknown status MISSNG"
ck G23_stdout_empty eq "$(cat build/G23.out)" ""

echo "== G24. 重复 version 头不一致：conflicting header 必须 FAIL =="
run G24 "$JAVA" -javaagent:"$AG" -Dmcport.gate=contract-head-conflict.tsv -Dmcport.gate.modjar="$MOD" -cp "$CP" demo.GateMod
ck_rc G24_rc_2 G24 2
ck_has G24_fail G24 err "conflicting @version header"
ck G24_stdout_empty eq "$(cat build/G24.out)" ""

echo "GATE_RESULT assertions=$CHECKS OK"
echo OK
