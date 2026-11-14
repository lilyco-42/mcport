#!/usr/bin/env bash
# Optional experiment: JRE 25 + a REAL Minecraft 26.1 client.jar (class major 69)
# + startup -javaagent weaving.  See REPORT.md section 12.
#
# This script distributes NO Mojang bytes:
#   * the real class is extracted at run time from YOUR 26.1 client jar (MC_26_1_JAR);
#   * JRE 25 is yours (JAVA25); only with MC_REAL26_AUTO_JRE=1 is it downloaded
#     from the TUNA Adoptium mirror with a pinned sha256.
# If either prerequisite is missing it prints SKIP and returns 0, so demo/run.sh
# keeps its plain-JDK17 six-scene reproducibility untouched.
set -u
cd "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
BUILD="$ROOT/demo/build/real26"
ulimit -c 0 2>/dev/null || true   # premain failure = JVM native abort; no core dumps

JAVAC="${JAVAC:-javac}"
JAVA_SYS="${JAVA_SYS:-java}"
MC_JAR="${MC_26_1_JAR:-}"
JAVA25="${JAVA25:-}"

if [ -z "$MC_JAR" ] || [ ! -f "$MC_JAR" ]; then
  echo "SKIP real26: set MC_26_1_JAR=/path/to/26.1-client.jar  (REPORT §12)"
  exit 0
fi
if [ -z "$JAVA25" ]; then
  JRE_HOME="${MC_REAL26_JRE_HOME:-/tmp/mcport-real26-jre25}"
  for c in /tmp/lead-jdk25/jdk-25.0.5+8-jre/bin/java "$JRE_HOME/bin/java"; do
    if [ -x "$c" ]; then JAVA25="$c"; break; fi
  done
fi
if [ -z "$JAVA25" ] && [ "${MC_REAL26_AUTO_JRE:-0}" = "1" ]; then
  JRE_HOME="${MC_REAL26_JRE_HOME:-/tmp/mcport-real26-jre25}"
  mkdir -p "$JRE_HOME"
  TGZ="$JRE_HOME/jre25.tar.gz"
  curl -fL --max-time 300 -sS -o "$TGZ" \
    https://mirrors.tuna.tsinghua.edu.cn/Adoptium/25/jre/x64/linux/OpenJDK25U-jre_x64_linux_hotspot_25.0.5_8.tar.gz \
    || { echo "FAIL jre25 download"; exit 1; }
  echo "6fac98f0c8202efc3135a9e9e42aa61963ec42d1c5cbb40caf231e7b14a24ef6  $TGZ" | sha256sum -c - \
    || { echo "FAIL jre25 sha256"; exit 1; }
  tar -xzf "$TGZ" -C "$JRE_HOME" --strip-components=1 || exit 1
  JAVA25="$JRE_HOME/bin/java"
fi
if [ -z "$JAVA25" ] || [ ! -x "$JAVA25" ]; then
  echo "SKIP real26: set JAVA25=/path/to/jre25/bin/java (or MC_REAL26_AUTO_JRE=1)"
  exit 0
fi
spec() { "$1" -XshowSettings:properties -version 2>&1 | grep "java.specification.version" | head -1 | tr -dc "0-9"; }
V25="$(spec "$JAVA25")"
VSYS="$(spec "$JAVA_SYS")"
echo "== JRE25 spec=$V25 ($("$JAVA25" -version 2>&1 | head -1)) ; system java spec=$VSYS"
[ "$V25" -ge 25 ] || { echo "SKIP real26: JAVA25 spec=$V25 is not >= 25"; exit 0; }

echo "== build =="
rm -rf "$BUILD"
mkdir -p "$BUILD/real" "$BUILD/out/stub" "$BUILD/out/mod" "$BUILD/out/adapter" \
         "$BUILD/out/probe" "$BUILD/hello" "$BUILD/classes" \
         "$BUILD/fat/hostbridge" "$BUILD/fat/mcport" "$BUILD/fat/dump"
(cd "$BUILD/real" && jar --extract --file "$MC_JAR" com/mojang/blaze3d/GpuOutOfMemoryException.class) \
  || { echo "FAIL: cannot extract class from $MC_JAR"; exit 1; }
CLS="$BUILD/real/com/mojang/blaze3d/GpuOutOfMemoryException.class"
[ -f "$CLS" ] || { echo "FAIL: class missing from jar"; exit 1; }
MAJOR="$(od -An -tu1 -j7 -N1 "$CLS" | tr -d " ")"
ORIG_SHA="$(sha1sum "$CLS" | cut -d" " -f1)"
echo "REAL_CLASS bytes=$(stat -c %s "$CLS") major=$MAJOR sha1=$ORIG_SHA"
[ "$MAJOR" = "69" ] || { echo "FAIL: expected class major 69, got $MAJOR (wrong jar?)"; exit 1; }

$JAVAC -nowarn -d "$BUILD/out/stub" GpuOutOfMemoryException.java || exit 1
$JAVAC -nowarn -cp "$BUILD/out/stub" -d "$BUILD/out/mod" Legacy.java LegacyRename.java || exit 1
$JAVAC -nowarn -cp "$BUILD/out/stub:$BUILD/out/mod" -d "$BUILD/out/adapter" Adapter.java || exit 1
$JAVAC -nowarn -cp "$BUILD/out/stub" -d "$BUILD/out/probe" Probe.java || exit 1
$JAVAC -nowarn -d "$BUILD/hello" Hello.java || exit 1
$JAVAC -nowarn -cp "$ROOT/lib/*" -d "$BUILD/classes" "$ROOT"/java/mcport/*.java DumpAgent.java || exit 1
echo "-- compile-time stub must live ONLY in out/stub (never on runtime cp) --"
find "$BUILD/out" -name GpuOutOfMemoryException.class -print

# fat agents: ASM must be visible to the bootstrap-loaded agent classes
for d in hostbridge mcport dump; do
  for j in "$ROOT"/lib/*.jar; do
    (cd "$BUILD/fat/$d" && jar --extract --file "$j" >/dev/null 2>&1 || true)
  done
  rm -rf "$BUILD/fat/$d/META-INF" "$BUILD/fat/$d/module-info.class"
  cp -r "$BUILD/classes/mcport" "$BUILD/fat/$d/"
  if [ "$d" = "dump" ]; then mkdir -p "$BUILD/fat/dump/demo26"; cp "$BUILD"/classes/demo26/DumpAgent*.class "$BUILD/fat/dump/demo26/"; fi
done
cd "$BUILD"
{ echo "Manifest-Version: 1.0"; echo "Premain-Class: mcport.HostBridge"; echo ""; } > MF-host.mf
{ echo "Manifest-Version: 1.0"; echo "Premain-Class: mcport.McPortRuntime"; echo ""; } > MF-mcport.mf
{ echo "Manifest-Version: 1.0"; echo "Premain-Class: demo26.DumpAgent"; echo ""; } > MF-dump.mf
jar --create --file=hostbridge-runtime.jar --manifest=MF-host.mf -C fat/hostbridge . || exit 1
jar --create --file=mcport-runtime.jar --manifest=MF-mcport.mf -C fat/mcport . || exit 1
jar --create --file=dumpagent-runtime.jar --manifest=MF-dump.mf -C fat/dump . || exit 1
cp "$ROOT"/demo/real26/bridge.tsv "$ROOT"/demo/real26/map.tsv .

CP="real:out/mod:out/adapter:out/probe:hello"
ONLY=demo26/LegacyRename   # strictest authorization: the caller class, not the whole demo26 package
FAIL=0
ok()   { echo "OK   $1"; }
bad()  { echo "FAIL $1"; FAIL=1; }

echo
echo "=== S0 default JDK rejects the real major-69 class ==="
if [ "$VSYS" -ge 25 ]; then echo "     SKIP S0 (default java is already 25)"; else
  "$JAVA_SYS" -cp "$CP" demo26.Probe > s0.out 2>&1; S0=$?
  head -2 s0.out
  if [ "$S0" -ne 0 ] && grep -q "UnsupportedClassVersionError" s0.out; then ok "S0 rc=$S0"; else bad "S0 rc=$S0"; fi
fi

echo
echo "=== S1 JRE25 loads the real 26.1 major-69 class ==="
"$JAVA25" -cp "$CP" demo26.Probe > s1.out 2>&1; S1=$?; cat s1.out
if [ "$S1" -eq 0 ] && grep -q "LOADED .* major=69" s1.out; then ok "S1"; else bad "S1 rc=$S1"; fi

echo
echo "=== S2 no agent -> NoSuchMethodError (the real class lacks legacyMessage) ==="
"$JAVA25" -cp "$CP" demo26.Legacy > s2.out 2>&1; S2=$?; head -2 s2.out
if [ "$S2" -ne 0 ] && grep -q "NoSuchMethodError" s2.out; then ok "S2 rc=$S2"; else bad "S2 rc=$S2"; fi

echo
echo "=== S3 HostBridge weaves a real 26.1 major-69 class, JVM verifies and links ==="
"$JAVA25" -javaagent:hostbridge-runtime.jar -Dmcport.bridge=bridge.tsv -cp "$CP" demo26.Legacy > s3.out 2>&1; S3=$?; cat s3.out
if [ "$S3" -eq 0 ] && grep -q "REAL-26.1-BRIDGE-OK" s3.out && grep -q "major=69" s3.out && grep -q "declared=legacyMessage" s3.out; then ok "S3"; else bad "S3 rc=$S3"; fi

echo
echo "=== S4 McPortRuntime alone rewrites the mod but host still lacks the method -> fail-loud ==="
"$JAVA25" -javaagent:mcport-runtime.jar -Dmcport.map=map.tsv -Dmcport.only="$ONLY" -cp "$CP" demo26.LegacyRename > s4.out 2>&1; S4=$?; head -3 s4.out
if [ "$S4" -ne 0 ] && grep -q "NoSuchMethodError" s4.out && grep -q "legacyMessage" s4.out; then ok "S4 rc=$S4"; else bad "S4 rc=$S4"; fi

echo
echo "=== S5 dual agent (RENAME + bridge) on a REAL 26.1 class ==="
"$JAVA25" -javaagent:mcport-runtime.jar -javaagent:hostbridge-runtime.jar -Dmcport.map=map.tsv -Dmcport.bridge=bridge.tsv -Dmcport.only="$ONLY" -cp "$CP" demo26.LegacyRename > s5.out 2>&1; S5=$?; cat s5.out
if [ "$S5" -eq 0 ] && grep -q "REAL-26.1-BRIDGE-OK" s5.out; then ok "S5"; else bad "S5 rc=$S5"; fi
if grep -q "Dynamic loading of agents" s5.out; then bad "S5 unexpected dynamic-agent warning"; else ok "S5 startup -javaagent emits no JEP 451 warning"; fi

echo
echo "=== S6 reversed agent order -> identical result ==="
"$JAVA25" -javaagent:hostbridge-runtime.jar -javaagent:mcport-runtime.jar -Dmcport.map=map.tsv -Dmcport.bridge=bridge.tsv -Dmcport.only="$ONLY" -cp "$CP" demo26.LegacyRename > s6.out 2>&1; S6=$?; cat s6.out
if [ "$S6" -eq 0 ] && grep -q "REAL-26.1-BRIDGE-OK" s6.out; then ok "S6"; else bad "S6 rc=$S6"; fi

echo
echo "=== S7 fail-loud: missing bridge spec aborts at premain (no silent start) ==="
"$JAVA25" -javaagent:hostbridge-runtime.jar -Dmcport.bridge=missing.tsv -cp "$CP" demo26.Hello > s7.out 2>&1; S7=$?; head -6 s7.out
if [ "$S7" -ne 0 ] && grep -q "cannot load bridge spec" s7.out; then ok "S7 rc=$S7 (JVM native abort, expected)"; else bad "S7 rc=$S7"; fi

echo
echo "=== S8 fail-loud: rename agent without map ==="
"$JAVA25" -javaagent:mcport-runtime.jar -Dmcport.only="$ONLY" -cp "$CP" demo26.LegacyRename > s8.out 2>&1; S8=$?; head -3 s8.out
if [ "$S8" -ne 0 ] && grep -q "NoSuchMethodError" s8.out; then ok "S8 rc=$S8"; else bad "S8 rc=$S8"; fi

echo
echo "=== S9 byte-level proof: woven class is still major 69 and gained exactly one method ==="
"$JAVA25" -javaagent:hostbridge-runtime.jar -javaagent:dumpagent-runtime.jar -Dmcport.bridge=bridge.tsv -Dmcport.dump=dump-host.class -cp "$CP" demo26.Legacy > s9.out 2>&1; S9=$?; cat s9.out
DM="$(od -An -tu1 -j7 -N1 dump-host.class | tr -d " ")"
DS="$(sha1sum dump-host.class | cut -d" " -f1)"
javap -p dump-host.class > s9.javap 2>&1; cat s9.javap
echo "woven major=$DM bytes=$(stat -c %s dump-host.class) sha1=$DS ; original sha1=$ORIG_SHA"
if [ "$S9" -eq 0 ] && [ "$DM" = "69" ] && [ "$DS" != "$ORIG_SHA" ] && grep -q "legacyMessage()" s9.javap; then ok "S9"; else bad "S9 rc=$S9"; fi

echo
echo "=== S10 McPortRuntime alone does NOT touch the host class (byte-identical dump) ==="
"$JAVA25" -javaagent:mcport-runtime.jar -javaagent:dumpagent-runtime.jar -Dmcport.map=map.tsv -Dmcport.only="$ONLY" -Dmcport.dump=dump-mcport.class -cp "$CP" demo26.LegacyRename > s10.out 2>&1; S10=$?; head -3 s10.out
DS10="$(sha1sum dump-mcport.class | cut -d" " -f1)"
echo "mcport-only dump sha1=$DS10 (expect == original $ORIG_SHA)"
if [ "$S10" -ne 0 ] && [ "$DS10" = "$ORIG_SHA" ]; then ok "S10 rc=$S10"; else bad "S10 rc=$S10"; fi

echo
echo "=== S11 -Xverify:all + dual agent + observer: full verification still passes ==="
"$JAVA25" -Xverify:all -javaagent:mcport-runtime.jar -javaagent:hostbridge-runtime.jar -javaagent:dumpagent-runtime.jar -Dmcport.map=map.tsv -Dmcport.bridge=bridge.tsv -Dmcport.only="$ONLY" -Dmcport.dump=dump-verify.class -cp "$CP" demo26.LegacyRename > s11.out 2>&1; S11=$?; cat s11.out
DV="$(od -An -tu1 -j7 -N1 dump-verify.class | tr -d " ")"
if [ "$S11" -eq 0 ] && [ "$DV" = "69" ] && grep -q "REAL-26.1-BRIDGE-OK" s11.out; then ok "S11"; else bad "S11 rc=$S11"; fi

echo
if [ "$FAIL" -eq 0 ]; then echo "REAL26_OK"; else echo "REAL26_FAILED"; fi
exit "$FAIL"
