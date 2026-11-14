#!/usr/bin/env python3
"""McPort Loader —— 与 MC 版本无关的装载编排机（preflight + 正确装配 + fail-loud）。

设计前提（REPORT §1 / §7 / §14）：字面意义的「全平台全版本任意 mod 都能跑」不可达。
本工具交付的是可实现的等价物：对**任意** (mod jar, 目标 client jar) 组合，
  1. 不靠版本字符串猜，靠 jar 结构 + version.json 自动分代（混淆期 / 去混淆期 / 非 JVM）；
  2. 探测 mod 的加载器、命名空间、声明的 MC/Java 版本、Mixin、native 库；
  3. 选出唯一正确的映射路线（同版 / intermediary 跨版 / 26.x 身份桥）与所需制品；
  4. 装配启动期 -javaagent JVM 参数（JEP 451 允许），并自检 Java 运行时 major；
   5. 可选调用 LinkCheck 符号预言机，把「能自动修 / 需人工」量化成退出码；
   6. 按代际选装配策略：混淆期跨版走启动期 -javaagent，26.x 身份桥走离线 RemapTool + 真实名声明表复测；
   7. 任何缺制品、版本不匹配、native/异加载器/非 JVM 目标一律拒绝并说明原因，绝不静默。

不下载、不内置、不分发任何 Mojang 字节或映射表；所有输入由使用者自备。
只用 Python 标准库；--check / --build-agents 额外需要本机 JDK（java + javac）。

退出码：0 = 全部可装配（含自动重映射）；2 = 存在需人工适配的符号；1 = 缺前置/不支持/运行失败。
"""
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, zipfile
from pathlib import Path

SCHEMA = 1
NM = "net/minecraft/"
CM = "com/mojang/"
INTER_RE = re.compile(rb"(?:class_|method_|field_)[0-9]+")
NAMED_RE = re.compile(rb"net/minecraft/[a-z][a-z0-9_]*/[A-Za-z0-9_$]+")
CLASS_MAJOR_JAVA = {61: 17, 65: 21, 69: 25}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def probe_client(path):
    """只读结构探测：返回分代、Java 需求、class major、规模。不加载任何类。"""
    out = {"path": os.path.abspath(path), "size": os.path.getsize(path),
           "sha256": sha256_file(path), "id": None, "java": None, "major": None,
           "generation": "unknown", "classes": 0, "nm_hier": 0, "cm": 0,
           "root_short": 0, "hier_ratio": 0.0, "has_version_json": False,
           "protocol": None, "world": None, "reason": ""}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "version.json" in names:
            try:
                v = json.loads(z.read("version.json"))
                out["has_version_json"] = True
                out["id"] = v.get("id") or v.get("name")
                out["java"] = v.get("java_version")
                out["protocol"] = v.get("protocol_version")
                out["world"] = v.get("world_version")
            except Exception as e:
                out["reason"] = "version.json unreadable: " + str(e)
        cls = sorted(n for n in names
                     if n.endswith(".class") and not n.startswith("META-INF/"))
        out["classes"] = len(cls)
        if cls:
            d = z.read(cls[0])[:8]
            if d[:4] == b"\xca\xfe\xba\xbe":
                out["major"] = struct.unpack(">H", d[6:8])[0]
        if out["java"] is None and out["major"] is not None:
            out["java"] = CLASS_MAJOR_JAVA.get(out["major"], out["major"] - 44)
        root = [n for n in cls if "/" not in n]
        nm = [n for n in cls if n.startswith(NM) and "/" in n[len(NM):]]
        cm = [n for n in cls if n.startswith(CM)]
        out["root_short"], out["nm_hier"], out["cm"] = len(root), len(nm), len(cm)
        out["hier_ratio"] = round(len(nm) / max(1, len(cls)), 4)
        if len(cls) == 0:
            out["generation"] = "non_jvm"
        elif out["hier_ratio"] >= 0.5:
            out["generation"] = "deobf"
        elif len(root) / max(1, len(cls)) >= 0.5:
            out["generation"] = "obf"
        else:
            out["generation"] = "unknown"
    return out


def probe_mod(path):
    out = {"path": os.path.abspath(path), "file": os.path.basename(path),
           "size": os.path.getsize(path), "sha256": sha256_file(path),
           "loader": "unknown", "id": None, "version": None, "environment": None,
           "declared_mc": [], "declared_java": None, "namespace": "none",
           "inter_tokens": 0, "named_tokens": 0, "mixin": False,
           "natives": [], "classes": 0, "reason": ""}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "fabric.mod.json" in names:
            out["loader"] = "fabric"
        elif "META-INF/neoforge.mods.toml" in names:
            out["loader"] = "neoforge"
        elif "META-INF/mods.toml" in names:
            out["loader"] = "forge"
        if "fabric.mod.json" in names:
            try:
                d = json.loads(z.read("fabric.mod.json"))
                out["id"], out["version"] = d.get("id"), d.get("version")
                out["environment"] = d.get("environment")
                dep = d.get("depends") or {}
                mc = dep.get("minecraft", "")
                if isinstance(mc, (list, tuple)):
                    mc = " ".join(str(x) for x in mc)
                out["declared_mc"] = sorted(set(re.findall(r"\d+\.\d+(?:\.\d+)?", str(mc))))
                j = str(dep.get("java", ""))
                m = re.search(r"(?:>=|>)\s*(\d+)", j)
                out["declared_java"] = int(m.group(1)) if m else None
            except Exception as e:
                out["reason"] = "fabric.mod.json unreadable: " + str(e)
        out["natives"] = sorted(n for n in names
                                if n.lower().endswith((".dll", ".so", ".dylib", ".jnilib", ".exe")))
        inter, named = set(), set()
        cls = [n for n in names if n.endswith(".class") and not n.startswith("META-INF/")]
        out["classes"] = len(cls)
        for n in cls:
            d = z.read(n)
            inter.update(INTER_RE.findall(d))
            for x in NAMED_RE.findall(d):
                if not INTER_RE.search(x):
                    named.add(x)
            if b"org/spongepowered/asm/mixin" in d:
                out["mixin"] = True
        out["inter_tokens"], out["named_tokens"] = len(inter), len(named)
        if inter:
            out["namespace"] = "intermediary"
        elif named:
            out["namespace"] = "named"
        else:
            out["namespace"] = "none"
    return out


def probe_java(exe):
    try:
        r = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=30)
        s = (r.stdout or "") + (r.stderr or "")
        m = re.search(r'version\s+"(\d+)(?:\.(\d+))?', s)
        if not m:
            return {"exe": exe, "major": None, "raw": s.strip().splitlines()[:1]}
        a = int(m.group(1))
        major = int(m.group(2)) if a == 1 and m.group(2) else a
        return {"exe": exe, "major": major, "raw": s.strip().splitlines()[:1]}
    except Exception as e:
        return {"exe": exe, "major": None, "error": str(e)}


def decide(client, mod, runtime, platform):
    """纯结构决策：不查版本号白名单，路由由 generation / namespace / metadata 推出。"""
    reasons = []
    if client["generation"] == "non_jvm" or client["classes"] == 0:
        return "UNSUPPORTED_NON_JVM", reasons + [
            "目标没有 JVM 字节码（Bedrock/C++ 或纯资源包）；javaagent/ClassLoader 无附着点"], []
    if client["generation"] == "unknown":
        return "UNKNOWN_GENERATION", reasons + [
            "jar 结构既不像混淆期也不像去混淆期，拒绝猜测"], []
    if mod["loader"] != "fabric":
        return "UNSUPPORTED_LOADER", reasons + [
            "加载器=" + mod["loader"] + "；本机器只对 Fabric 字节码路线做过实证明，"
            "Forge/NeoForge 需各自加载器，跨加载器方案（Connector）不跨版本"], []
    if mod["natives"]:
        return "NATIVE_BOUND", reasons + [
            "mod 内含 native 库 " + ", ".join(mod["natives"][:4]) +
            "；JVM 抽象不覆盖 native，跨 OS 必须逐平台构建"], []
    need_java = client["java"]
    if need_java and runtime.get("major") and runtime["major"] < need_java:
        return "RUNTIME_JAVA_MISMATCH", reasons + [
            "目标需要 Java >= " + str(need_java) + "，当前 -java 是 " + str(runtime["major"]) +
            "；请用 --java 指向匹配 JDK（26.x 需 Java 25）"], []
    if mod["declared_java"] and need_java and mod["declared_java"] > need_java:
        return "RUNTIME_JAVA_MISMATCH", reasons + [
            "mod 声明 Java >= " + str(mod["declared_java"]) + "，目标只运行在 Java " +
            str(need_java) + "；不可装配"], []
    artifacts = []
    if mod["namespace"] == "none":
        route = "NO_GAME_REFS"
        reasons.append("字节码内 0 条游戏符号（纯运行库/资源 mod），无需重映射；仍受加载器与 Java 版本约束")
    elif mod["declared_mc"] and client["id"] in mod["declared_mc"]:
        route = "SAME_VERSION"
        reasons.append("mod 声明的 MC 版本包含目标 " + str(client["id"]) + "，原样装载")
    elif client["generation"] == "obf":
        route = "OBF_CROSS"
        artifacts.append("map-<src>-" + str(client["id"]) + ".tsv")
        reasons.append("混淆期跨版本：以 Fabric intermediary 为身份，按 (owner,desc) 生成成员改名表")
    elif client["generation"] == "deobf":
        route = "DEOBF_BREAK"
        artifacts.append("bridge-" + str(client["id"]) + ".tsv")
        reasons.append("26.x 去混淆断代：intermediary 空表，必须用官方 ProGuard × intermediary 重建身份桥")
    else:
        route = "UNKNOWN_GENERATION"
        reasons.append("无法判定目标代际")
    if mod["mixin"]:
        reasons.append("含 Mixin：注解字符串/@Shadow 声明名需 MixinRewriter + MixinCheck 复核")
    if client["generation"] == "deobf":
        reasons.append("目标 class major=" + str(client["major"]) + "，需 Java 25 运行时")
    return route, reasons, artifacts


def build_agents(repo, work):
    """自包含编译两个启动期 fat agent；不依赖预先构建好的 demo jar。"""
    lib = Path(repo) / "lib"
    src = Path(repo) / "java" / "mcport"
    classes = Path(work) / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    cp = str(lib / "*")
    r = subprocess.run(["javac", "-nowarn", "-cp", cp, "-d", str(classes)]
                       + [str(x) for x in sorted(src.glob("*.java"))],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("javac failed: " + r.stderr[-2000:])
    payload = {}
    for p in classes.rglob("*.class"):
        payload[p.relative_to(classes).as_posix()] = p.read_bytes()
    for j in sorted(lib.glob("asm-*.jar")):
        with zipfile.ZipFile(j) as z:
            for n in z.namelist():
                if n.startswith("META-INF/") or n.endswith("module-info.class") or not n.endswith(".class"):
                    continue
                payload.setdefault(n, z.read(n))
    out = {}
    for name, premain, extra in [
            ("mcport-runtime.jar", "mcport.McPortRuntime", "Can-Retransform-Classes: true\n"),
            ("hostbridge-runtime.jar", "mcport.HostBridge", "")]:
        mf = "Manifest-Version: 1.0\nPremain-Class: " + premain + "\n" + extra
        p = Path(work) / name
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("META-INF/MANIFEST.MF", mf)
            for k in sorted(payload):
                z.writestr(k, payload[k])
        out[name] = str(p)
    return out, str(classes)


def strategy_for(route, requested):
    """auto: 混淆期跨版走启动期 agent；26.x 身份桥走已验证的离线重映射。"""
    if requested != "auto":
        return requested
    if route == "OBF_CROSS":
        return "startup"
    if route == "DEOBF_BREAK":
        return "offline"
    return "none"


def jvm_args(route, agents, map_path, bridge_path, only, strategy):
    """返回应注入真实启动器的 JVM 参数；只装配不伪造游戏启动命令。

    offline 策略不挂 -javaagent：字节码已在构建期被 RemapTool 改好，
    再挂一次会把真实名当 intermediary 二次改写（REPORT §14）。
    """
    if strategy != "startup" or route not in ("OBF_CROSS", "DEOBF_BREAK"):
        return []
    m = map_path or bridge_path
    if not m:
        return []
    out = ["-javaagent:" + agents.get("mcport-runtime.jar", "mcport-runtime.jar"),
           "-Dmcport.map=" + m]
    if only:
        out.append("-Dmcport.only=" + only)
    return out


def remap_mod(repo, classes, map_path, mod, out_dir, java="java"):
    """离线重映射：与 pipeline-26.sh 的 7/9 步、RemapTool 同一条路线。"""
    out = Path(out_dir) / Path(mod["file"]).name
    out.parent.mkdir(parents=True, exist_ok=True)
    cp = classes + os.pathsep + str(Path(repo) / "lib" / "*")
    cmd = [java, "-cp", cp, "mcport.RemapTool", "--map", map_path,
           "--in", mod["path"], "--out", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not out.exists():
        return {"ok": False, "rc": r.returncode, "stderr": r.stderr[-800:], "out": str(out)}
    return {"ok": True, "rc": 0, "out": str(out), "stderr": r.stderr[-400:]}


def run_linkcheck(repo, classes, decl, mod, map_path, tickets_dir, java="java",
                  checked_jar=None, ticket_suffix=""):
    cp = classes + os.pathsep + str(Path(repo) / "lib" / "*")
    ticket = None
    if tickets_dir:
        Path(tickets_dir).mkdir(parents=True, exist_ok=True)
        ticket = str(Path(tickets_dir) / (Path(mod["file"]).stem + ticket_suffix + ".json"))
    jar = checked_jar or mod["path"]
    cmd = [java, "-cp", cp, "mcport.LinkCheck", "--decl", decl, "--mod", jar]
    if map_path:
        cmd += ["--map", map_path]
    if ticket:
        cmd += ["--json", ticket]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    d = None
    if ticket and os.path.exists(ticket):
        try:
            with open(ticket, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = None
    if d is None:
        return {"ok": False, "rc": r.returncode, "stderr": r.stderr[-800:],
                "stdout": r.stdout[-800:], "ticket": ticket, "checkedJar": jar}
    return {"ok": True, "rc": r.returncode, "total": d.get("total"),
            "resolve": d.get("resolve"), "rename": d.get("rename"),
            "sigchg": d.get("sigchg"), "missing": d.get("missing"),
            "autoFixCeiling": d.get("autoFixCeiling"), "ticket": ticket,
            "checkedJar": jar}


def main():
    ap = argparse.ArgumentParser(description="McPort Loader: version-agnostic mod loading preflight/assembly")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent), help="McPort checkout root")
    ap.add_argument("--target", required=True, help="target client jar (user supplied)")
    ap.add_argument("--mod", action="append", default=[], help="mod jar; repeatable")
    ap.add_argument("--mods-dir", help="directory of mod jars (alternative to repeated --mod)")
    ap.add_argument("--artifacts", help="dir with decl-<ver>.tsv / map-*.tsv / bridge-*.tsv")
    ap.add_argument("--source", help="source MC version for OBF_CROSS map lookup")
    ap.add_argument("--java", default="java", help="java executable to validate/use")
    ap.add_argument("--platform", default="jvm", help="windows|linux|macos|jvm (informational)")
    ap.add_argument("--only", default="", help="-Dmcport.only prefix, e.g. com/example/mymod/")
    ap.add_argument("--strategy", choices=["auto", "startup", "offline"], default="auto",
                    help="auto=OBF_CROSS startup / DEOBF_BREAK offline; startup=-javaagent; offline=RemapTool")
    ap.add_argument("--remap-dir", help="offline RemapTool output dir (default: <work>/remapped)")
    ap.add_argument("--check", action="store_true", help="run LinkCheck symbol oracle")
    ap.add_argument("--build-agents", action="store_true", help="compile the two startup agents")
    ap.add_argument("--agents-dir", help="where to put built agents (default: <work>/agents)")
    ap.add_argument("--tickets", help="dir to write LinkCheck JSON tickets")
    ap.add_argument("--emit-script", help="write a fail-loud launch wrapper shell script")
    ap.add_argument("--out", help="write full plan JSON here")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    repo = str(Path(a.repo).resolve())
    work = str(Path(a.agents_dir or "/tmp/mcport-loader-work").resolve())
    Path(work).mkdir(parents=True, exist_ok=True)
    remap_dir = str(Path(a.remap_dir).resolve()) if a.remap_dir else str(Path(work) / "remapped")
    client = probe_client(a.target)
    runtime = probe_java(a.java)
    mods = list(a.mod)
    if a.mods_dir:
        mods += [str(p) for p in sorted(Path(a.mods_dir).glob("*.jar"))]
    if not mods:
        print("no mods given", file=sys.stderr)
        return 1

    agents, classes = {}, None
    if a.build_agents:
        try:
            agents, classes = build_agents(repo, str(Path(work) / "agents"))
        except Exception as e:
            print("AGENT_BUILD_FAILED " + str(e), file=sys.stderr)
            return 1
    else:
        classes = str(Path(repo) / "build")
        if not Path(classes, "mcport", "LinkCheck.class").exists():
            classes = str(Path(work) / "agents" / "classes")
        # 复用上一次 --build-agents 产出的 fat agent，避免每次重编译
        for name in ("mcport-runtime.jar", "hostbridge-runtime.jar"):
            p = Path(work) / "agents" / name
            if p.exists():
                agents[name] = str(p)

    plan, summary = [], {"mods": 0, "auto": 0, "manual": 0, "unsupported": 0,
                         "missing_artifacts": 0, "sigchg": 0, "missing": 0}
    for mp in mods:
        mod = probe_mod(mp)
        route, reasons, needed = decide(client, mod, runtime, a.platform)
        strategy = strategy_for(route, a.strategy)
        e = {"mod": mod, "route": route, "strategy": strategy, "reasons": reasons,
             "needed_artifacts": needed, "verdict": "NOT_CHECKED", "jvmArgs": [],
             "checkMode": None, "check": None, "remap": None, "map": None,
             "bridge": None, "decl": None}
        art = Path(a.artifacts) if a.artifacts else None
        decl = None
        if art:
            d = art / ("decl-" + str(client["id"]) + ".tsv")
            if d.exists():
                decl = str(d)
                e["decl"] = decl
        mpath = None
        if route in ("OBF_CROSS", "SAME_VERSION", "NO_GAME_REFS"):
            if art:
                src = a.source or (mod["declared_mc"][0] if mod["declared_mc"] else "")
                for cand in [art / ("map-" + src + "-" + str(client["id"]) + ".tsv"),
                             art / ("map-" + str(client["id"]) + "-" + str(client["id"]) + ".tsv")]:
                    if cand.exists():
                        mpath = str(cand)
                        break
        bpath = None
        if route == "DEOBF_BREAK" and art:
            for cand in [art / ("bridge-" + str(client["id"]) + ".tsv"),
                         art / ("bridge-" + str(client["id"]) + "-news.tsv")]:
                if cand.exists():
                    bpath = str(cand)
                    break
        e["map"], e["bridge"] = mpath, bpath
        e["jvmArgs"] = jvm_args(route, agents, mpath, bpath, a.only, strategy)
        if strategy == "offline":
            reasons.append("离线策略：RemapTool 先改好 mod 字节码，真实启动器不挂 -javaagent（避免二次改写）")
        if strategy == "startup" and route == "DEOBF_BREAK":
            reasons.append("启动期 agent 加载 26.x 桥表未经真实客户端端到端验证；--check 请用 --strategy offline")

        if (strategy == "startup" and route == "DEOBF_BREAK") or \
           route.startswith("UNSUPPORTED") or \
           route in ("UNKNOWN_GENERATION", "NATIVE_BOUND", "RUNTIME_JAVA_MISMATCH"):
            if strategy == "startup" and route == "DEOBF_BREAK":
                e["jvmArgs"] = []
                reasons.append("拒绝装配 26.x 身份桥的启动期 -javaagent：桥表改的是整类命名空间，"
                               "只跑过离线 RemapTool + 真实名声明表复测；请 --strategy offline（REPORT §14）")
            e["verdict"] = "UNSUPPORTED"
            summary["unsupported"] += 1
        elif a.check:
            if not decl:
                e["verdict"] = "MISSING_ARTIFACT"
                reasons.append("缺 decl-" + str(client["id"]) + ".tsv；--artifacts 未提供")
                summary["missing_artifacts"] += 1
            elif route in ("OBF_CROSS", "DEOBF_BREAK") and not (mpath or bpath):
                e["verdict"] = "MISSING_ARTIFACT"
                reasons.append("缺 " + "/".join(needed) + "；拒绝无映射表启动")
                summary["missing_artifacts"] += 1
            else:
                lc = None
                if strategy == "offline" and route in ("OBF_CROSS", "DEOBF_BREAK"):
                    rp = remap_mod(repo, classes, mpath or bpath, mod, remap_dir, a.java)
                    e["remap"] = rp
                    e["checkMode"] = "RemapTool + LinkCheck(no --map) [pipeline-26.sh 口径]"
                    if rp.get("ok"):
                        lc = run_linkcheck(repo, classes, decl, mod, None, a.tickets, a.java,
                                           checked_jar=rp["out"], ticket_suffix=".offline")
                    else:
                        reasons.append("RemapTool 失败：" + str(rp.get("stderr"))[-200:])
                else:
                    e["checkMode"] = "LinkCheck --map [pipeline.sh 工单口径]" if mpath or bpath else "LinkCheck(no --map)"
                    lc = run_linkcheck(repo, classes, decl, mod, mpath or bpath, a.tickets, a.java)
                e["check"] = lc
                if lc is None or not lc.get("ok"):
                    e["verdict"] = "CHECK_FAILED"
                    summary["unsupported"] += 1
                else:
                    sg, ms = lc.get("sigchg") or 0, lc.get("missing") or 0
                    summary["sigchg"] += sg
                    summary["missing"] += ms
                    if sg + ms > 0:
                        e["verdict"] = "NEEDS_MANUAL"
                        summary["manual"] += 1
                        reasons.append("需人工 " + str(sg) + " 条 SIGCHG + " + str(ms) +
                                       " 条 MISSING；静态可解析率 != 能跑")
                    else:
                        e["verdict"] = "AUTO"
                        summary["auto"] += 1
        else:
            if route in ("OBF_CROSS", "DEOBF_BREAK") and not (mpath or bpath):
                e["verdict"] = "MISSING_ARTIFACT"
                reasons.append("缺 " + "/".join(needed) + "；拒绝无映射表装配（fail-loud）")
                summary["missing_artifacts"] += 1
            else:
                e["verdict"] = "PLAN_ONLY"
        summary["mods"] += 1
        plan.append(e)

    result = {"schema": SCHEMA, "tool": "mcport-loader", "platform": a.platform,
              "strategy": a.strategy, "remapDir": remap_dir, "target": client,
              "runtime": runtime, "agents": agents, "summary": summary, "plan": plan}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if a.emit_script:
        allargs = []
        for e in plan:
            if e["verdict"] not in ("AUTO", "PLAN_ONLY"):
                continue
            for x in e["jvmArgs"]:
                if x not in allargs:
                    allargs.append(x)
        db = chr(36) + "{"
        lines = ["#!/usr/bin/env bash",
                 "# Generated by mcport-loader. NOT a Minecraft launcher: it only supplies JVM args.",
                 "# Set MCPORT_LAUNCH_CMD to your real launcher command (Fabric/Quilt/...).",
                 "# Unquoted $MCPORT_LAUNCH_CMD below is intentional: it is a shell command string.",
                 "set -euo pipefail",
                 "MC_JAVA=" + json.dumps(a.java),
                 "JVM_ARGS=(" + " ".join(json.dumps(x) for x in allargs) + ")",
                 ": \"" + db + "MCPORT_LAUNCH_CMD:?set MCPORT_LAUNCH_CMD to the real game launcher}\"",
                 "if [ -z \"$MCPORT_LAUNCH_CMD\" ]; then echo 'refusing to guess launcher' >&2; exit 1; fi"]
        if any(e["strategy"] == "offline" for e in plan):
            lines.insert(4, "# offline-remap: put " + remap_dir + "/*.jar into the launcher mods folder; no -javaagent is used.")
        hard = (summary["manual"] or summary["unsupported"] or summary["missing_artifacts"] or
                any(e["verdict"] not in ("AUTO", "PLAN_ONLY") for e in plan))
        if hard:
            lines += ["echo 'REFUSE: " + str(summary["manual"]) + " mod(s) need manual adapters, " +
                      str(summary["unsupported"]) + " unsupported, " +
                      str(summary["missing_artifacts"]) + " missing artifacts' >&2",
                      "echo 'see the plan JSON / LinkCheck tickets' >&2",
                      "exit 2"]
        elif not a.check:
            lines += ["echo 'REFUSE: plan-only output was not symbol-checked; rerun loader.py with --check' >&2",
                      "echo 'see the plan JSON / LinkCheck tickets' >&2",
                      "exit 2"]
        else:
            lines += ["exec \"$MC_JAVA\" \"" + db + "JVM_ARGS[@]}\" $MCPORT_LAUNCH_CMD"]
        Path(a.emit_script).write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(a.emit_script, 0o755)

    if not a.quiet:
        print("target: id=" + str(client["id"]) + " gen=" + client["generation"] +
              " java=" + str(client["java"]) + " major=" + str(client["major"]) +
              " classes=" + str(client["classes"]) + " hier_ratio=" + str(client["hier_ratio"]))
        print("runtime: " + str(runtime.get("major")) + " (" + a.java + ")")
        for e in plan:
            print("  " + e["mod"]["file"][:40].ljust(40) + " " + e["route"].ljust(22) +
                  " " + e["strategy"].ljust(9) + " " + e["verdict"].ljust(18) +
                  (" sg=" + str(e["check"]["sigchg"]) + " ms=" + str(e["check"]["missing"])
                   if e["check"] and e["check"].get("ok") else ""))
        print("summary: " + json.dumps(summary, ensure_ascii=False))
    if summary["unsupported"] or summary["missing_artifacts"]:
        return 1
    if summary["manual"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
