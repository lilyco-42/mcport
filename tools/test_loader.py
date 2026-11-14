#!/usr/bin/env python3
"""McPort loader 自包含回归：零外部数据、零 Mojang 字节、零网络。

用临时目录合成 client jar / mod jar / decl / map / bridge，验证分代、
路由、策略、jvm 参数、LinkCheck 工单解析、--check 与 --emit-script 的
fail-loud。仅在给定 --real 环境变量（REAL=1）时增加真实 jar 冒烟。
"""
import argparse, importlib.util, json, os, struct, subprocess, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("mcport_loader", ROOT / "tools" / "loader.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)
PY = sys.executable or "/usr/bin/python3"
FAIL = []
COUNT = 0

def ok(name, cond, detail=""):
    global COUNT
    COUNT += 1
    if not cond:
        FAIL.append(name + ": " + str(detail))
        print("FAIL " + name + " " + str(detail))
    else:
        print("ok   " + name)

def cls_bytes(major=65, body=b""):
    # 最小合法 class 头；loader.py 只读前 8 字节 magic/minor/major
    return b"\xca\xfe\xba\xbe\x00\x00" + struct.pack(">H", major) + body

def make_client(path, gen, vid="9.9", java=21, major=65):
    names = []
    if gen == "obf":
        names = ["a.class", "b.class", "c.class", "net/minecraft/ChatFormatting.class"]
    elif gen == "deobf":
        names = ["net/minecraft/world/level/Block.class",
                 "net/minecraft/world/entity/Player.class",
                 "com/mojang/blaze3d/systems/RenderSystem.class"]
    elif gen == "none":
        names = []
    version = {"id": vid, "java_version": java, "protocol_version": 1, "world_version": 1}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("version.json", json.dumps(version))
        for n in names:
            z.writestr(n, cls_bytes(major, b"net/minecraft/class_1234"))

def make_mod(path, *, loader="fabric", mc="", java="", namespace="none", natives=False, mixin=False):
    dep = {}
    if mc:
        dep["minecraft"] = mc
    if java:
        dep["java"] = java
    meta = {"id": "synthetic", "version": "1.0", "depends": dep, "environment": "*"}
    with zipfile.ZipFile(path, "w") as z:
        if loader == "fabric":
            z.writestr("fabric.mod.json", json.dumps(meta))
        elif loader == "neoforge":
            z.writestr("META-INF/neoforge.mods.toml", "modLoader='javafml'\n")
        body = b"plain"
        if namespace == "intermediary":
            body += b"net/minecraft/class_1234 method_42 field_9"
        elif namespace == "named":
            body += b"net/minecraft/world/level/Block"
        if mixin:
            body += b"org/spongepowered/asm/mixin/Mixin"
        z.writestr("demo/Mod.class", cls_bytes(65, body))
        if natives:
            z.writestr("natives/libdemo.so", b"\x7fELF")

def cli(*args, expect=None, major=21):
    env = dict(os.environ, FAKE_JAVA_MAJOR=str(major))
    r = subprocess.run([PY, str(ROOT / "tools" / "loader.py"), *map(str, args)],
                       capture_output=True, text=True, timeout=120, env=env)
    if expect is not None:
        ok("cli rc " + " ".join(map(str, args[-3:])), r.returncode == expect,
           "got " + str(r.returncode) + " want " + str(expect) + " stderr=" + r.stderr[-200:])
    return r

def plan_of(out):
    return json.loads(Path(out).read_text(encoding="utf-8"))

with tempfile.TemporaryDirectory(prefix="mcport-loader-test-") as td:
    T = Path(td)
    c_obf, c_deobf, c_empty = T / "c-obf.jar", T / "c-deobf.jar", T / "c-empty.jar"
    make_client(c_obf, "obf", "1.21.11")
    make_client(c_deobf, "deobf", "26.1", 25, 69)
    make_client(c_empty, "none", "bedrock", 21, 65)
    mod = {}
    for k, kw in {
        "plain": dict(), "obf": dict(namespace="intermediary"),
        "same": dict(namespace="intermediary", mc="=1.21.11"),
        "neoforge": dict(loader="neoforge", namespace="intermediary"),
        "native": dict(namespace="intermediary", natives=True),
        "mixin": dict(namespace="intermediary", mixin=True),
        "java21": dict(namespace="intermediary", java=">=21"),
        "java25": dict(namespace="intermediary", java=">=25"),
    }.items():
        mod[k] = T / ("m-" + k + ".jar")
        make_mod(mod[k], **kw)

    # 单元：结构探测
    o, d, e = L.probe_client(str(c_obf)), L.probe_client(str(c_deobf)), L.probe_client(str(c_empty))
    ok("probe obf generation", o["generation"] == "obf" and o["major"] == 65, o)
    ok("probe deobf generation", d["generation"] == "deobf" and d["major"] == 69 and d["java"] == 25, d)
    ok("probe non_jvm", e["generation"] == "non_jvm" and e["classes"] == 0, e)
    ok("probe mod namespace", L.probe_mod(str(mod["obf"]))["namespace"] == "intermediary")
    ok("probe mod native", len(L.probe_mod(str(mod["native"]))["natives"]) == 1)
    ok("probe mod mixin", L.probe_mod(str(mod["mixin"]))["mixin"] is True)

    # 单元：纯决策（不查版本白名单）
    r = {"major": 21}
    ok("route obf cross", L.decide(o, L.probe_mod(str(mod["obf"])), r, "jvm")[0] == "OBF_CROSS")
    ok("route same version", L.decide(o, L.probe_mod(str(mod["same"])), r, "jvm")[0] == "SAME_VERSION")
    ok("route no refs", L.decide(d, L.probe_mod(str(mod["plain"])), {"major": 25}, "jvm")[0] == "NO_GAME_REFS")
    ok("route deobf break", L.decide(d, L.probe_mod(str(mod["obf"])), {"major": 25}, "jvm")[0] == "DEOBF_BREAK")
    ok("route non jvm", L.decide(e, L.probe_mod(str(mod["obf"])), r, "jvm")[0] == "UNSUPPORTED_NON_JVM")
    ok("route other loader", L.decide(o, L.probe_mod(str(mod["neoforge"])), r, "jvm")[0] == "UNSUPPORTED_LOADER")
    ok("route native", L.decide(o, L.probe_mod(str(mod["native"])), r, "jvm")[0] == "NATIVE_BOUND")
    ok("route java mismatch", L.decide(d, L.probe_mod(str(mod["obf"])), r, "jvm")[0] == "RUNTIME_JAVA_MISMATCH")
    ok("route mod java mismatch", L.decide(o, L.probe_mod(str(mod["java25"])), r, "jvm")[0] == "RUNTIME_JAVA_MISMATCH")
    ok("strategy auto", [L.strategy_for(x, "auto") for x in ("OBF_CROSS", "DEOBF_BREAK", "SAME_VERSION")] == ["startup", "offline", "none"])
    agents = {"mcport-runtime.jar": "/x/a.jar"}
    ok("jvm args startup", L.jvm_args("OBF_CROSS", agents, "/m.tsv", None, "demo/", "startup") ==
       ["-javaagent:/x/a.jar", "-Dmcport.map=/m.tsv", "-Dmcport.only=demo/"])
    ok("jvm args offline empty", L.jvm_args("DEOBF_BREAK", agents, None, "/b.tsv", "", "offline") == [])
    ok("jvm args none empty", L.jvm_args("SAME_VERSION", agents, None, None, "", "none") == [])

    # 集成：合成制品 + 伪 java 输出确定性 LinkCheck 工单。
    art = T / "art"; art.mkdir()
    (art / "decl-1.21.11.tsv").write_text("# synthetic\nC\tnet/minecraft/class_1234\n", encoding="utf-8")
    (art / "decl-1.21.1.tsv").write_text("# synthetic\n", encoding="utf-8")
    (art / "decl-26.1.tsv").write_text("# synthetic\n", encoding="utf-8")
    (art / "map-1.21.1-1.21.11.tsv").write_text("# synthetic\n", encoding="utf-8")
    (art / "bridge-26.1.tsv").write_text("# synthetic\n", encoding="utf-8")
    java = T / "fake-java"
    java.write_text("#!/usr/bin/env python3\n" +
        "import json,os,sys\n" +
        "a=sys.argv[1:]\n" +
        "if a and a[0]=='-version':\n" +
        "    v=os.environ.get('FAKE_JAVA_MAJOR','21')\n" +
        "    print('openjdk version \"'+v+'.0.0\"',file=sys.stderr); sys.exit(0)\n" +
        "i=a.index('--json'); p=a[i+1]\n" +
        "if any('m-plain' in x for x in a):\n" +
        "    d={'mod':'synthetic','total':0,'resolve':0,'rename':0,'sigchg':0,'missing':0,'autoFixCeiling':0.0,'details':{}}\n" +
        "    open(p,'w').write(json.dumps(d)); sys.exit(0)\n" +
        "d={'mod':'synthetic','total':2,'resolve':1,'rename':0,'sigchg':1,'missing':0,'autoFixCeiling':50.0,'details':{}}\n" +
        "open(p,'w').write(json.dumps(d))\n" +
        "sys.exit(2)\n", encoding="utf-8")
    java.chmod(0o755)
    common = ["--repo", ROOT, "--java", java, "--source", "1.21.1", "--artifacts", art, "--quiet"]

    # I1: PLAN_ONLY + emit-script 必须拒绝执行
    p1, s1 = T / "p1.json", T / "s1.sh"
    cli("--target", c_obf, "--mod", mod["obf"], *common, "--out", p1, "--emit-script", s1, expect=0)
    j = plan_of(p1)["plan"][0]
    ok("I1 plan_only", j["verdict"] == "PLAN_ONLY" and j["strategy"] == "startup" and len(j["jvmArgs"]) == 2, j)
    ok("I1 plan-only script refuses", "not symbol-checked" in s1.read_text() and "exec " not in s1.read_text())

    # I2: --check 有 SIGCHG -> NEEDS_MANUAL，生成脚本硬拒绝
    p2, s2, tk2 = T / "p2.json", T / "s2.sh", T / "tk2"
    cli("--target", c_obf, "--mod", mod["obf"], *common, "--check", "--tickets", tk2,
        "--out", p2, "--emit-script", s2, expect=2)
    j = plan_of(p2)["plan"][0]
    ok("I2 needs manual", j["verdict"] == "NEEDS_MANUAL" and j["checkMode"].startswith("LinkCheck --map"), j)
    ok("I2 ticket parsed", j["check"]["total"] == 2 and j["check"]["sigchg"] == 1, j["check"])
    ok("I2 script hard refuse", "REFUSE: 1 mod(s) need manual" in s2.read_text())

    # I3: 26.x startup 一律拒绝且无 jvmArgs；--check 也不改判
    for n, chk in (("I3a", []), ("I3b", ["--check"])):
        p, s = T / (n + ".json"), T / (n + ".sh")
        cli("--target", c_deobf, "--mod", mod["obf"], *common, "--strategy", "startup", *chk,
            "--out", p, "--emit-script", s, expect=1, major=25)
        j = plan_of(p)["plan"][0]
        ok(n + " unsupported", j["verdict"] == "UNSUPPORTED" and j["jvmArgs"] == [] and j["check"] is None, j)
        ok(n + " startup-bridge reason", any("拒绝装配 26.x 身份桥" in x for x in j["reasons"]), j["reasons"])
        ok(n + " script hard refuse", "REFUSE: 0 mod(s) need manual adapters, 1 unsupported" in s.read_text())

    # I4: 缺制品 fail-loud（plan 与 check 两条路径）
    for n, chk in (("I4a", []), ("I4b", ["--check"])):
        p = T / (n + ".json")
        cli("--target", c_deobf, "--mod", mod["obf"], "--repo", ROOT, "--java", java,
            "--source", "1.21.1", "--quiet", *chk, "--out", p, expect=1, major=25)
        ok(n + " missing artifact", plan_of(p)["plan"][0]["verdict"] == "MISSING_ARTIFACT")

    # I5: NO_GAME_REFS -> AUTO + 可执行（MCPORT_LAUNCH_CMD 由使用者给）
    p5, s5, tk5 = T / "p5.json", T / "s5.sh", T / "tk5"
    cli("--target", c_deobf, "--mod", mod["plain"], *common, "--check", "--tickets", tk5,
        "--out", p5, "--emit-script", s5, expect=0, major=25)
    ok("I5 auto", plan_of(p5)["plan"][0]["verdict"] == "AUTO")
    ok("I5 script exec", 'exec "$MC_JAVA"' in s5.read_text())

    # I6: 非 JVM 目标 / native / 异加载器 / Java 不匹配均 unsupported
    for n, target, m, jv in (("I6a", c_empty, mod["obf"], java), ("I6b", c_obf, mod["native"], java),
                             ("I6c", c_obf, mod["neoforge"], java), ("I6d", c_deobf, mod["obf"], java)):
        p = T / (n + ".json")
        cli("--target", target, "--mod", m, "--repo", ROOT, "--java", jv, "--source", "1.21.1",
            "--artifacts", art, "--quiet", "--out", p, expect=1)
        ok(n + " unsupported", plan_of(p)["plan"][0]["verdict"] == "UNSUPPORTED")

print("RESULT " + ("ALL_OK " + str(COUNT) if not FAIL else "FAILED " + str(len(FAIL)) + "/" + str(COUNT)))
sys.exit(1 if FAIL else 0)
