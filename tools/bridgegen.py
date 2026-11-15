#!/usr/bin/env python3
"""McPort bridgegen — fail-loud SIGCHG/MISSING workbench (REPORT §16).

NOT an auto-fixer.  It turns LinkCheck tickets into:
  * triage.tsv              — one row per unresolved reference, with a REJECT/SKELETON status
  * bridge-candidates.tsv   — HostBridge-shaped 6-column rules for the strictly mechanical
                              subset; NEVER fed to a JVM unless a human copies it to rules
  * adapters/*.java         — compilable-shaped skeletons whose bodies throw until reviewed
  * stats.json / summary.csv— pure aggregate counts

Hard rules (see §16.2):
  * restore invoke kind from bytecode via mcport.CallKind; guessing static is forbidden
    (INVOKEVIRTUAL against a static bridge -> IncompatibleClassChangeError)
  * mirror LinkCheck's super/interface BFS when looking for same-name candidates
  * <init>/<clinit>, fields, mixed/special/interface opcodes, ambiguous candidates,
    ref-type conversions and narrowing conversions are all rejected, never guessed
  * numeric widening, identity and void-discard are still SEMANTIC changes; the 6-column
    rules are emitted only as candidates, with an adapter that throws.  auto_fixed is 0.

No network, no game jar, no Mojang mapping is read.  Runtime inputs are user-supplied.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA = 1
# REPORT section 22: one strict JVMS 4.3 reference parser for every tool.
HERE = os.path.dirname(os.path.abspath(__file__))
_cap_spec = importlib.util.spec_from_file_location(
    'mcport_capability_for_bridgegen', os.path.join(HERE, 'capability.py'))
_cap = importlib.util.module_from_spec(_cap_spec)
_cap_spec.loader.exec_module(_cap)
CTOR = {"<init>", "<clinit>"}
PRIMS = set("BCDFIJSZ")
# JLS 5.1.2 widening primitive conversion; the reverse direction is NOT allowed.
WIDEN = {"B": set("SIJFD"), "S": set("IJFD"), "C": set("IJFD"),
         "I": set("JFD"), "J": set("FD"), "F": set("D"), "D": set(), "Z": set()}
INTLIKE = set("BSCI")


def parse_ref(s: str):
    """Return (owner, name, desc, M|F) from a LinkCheck detail line.

    REPORT section 22: delegate to the one strict JVMS 4.3 parser in
    capability.py instead of maintaining a second loose regex grammar.
    The external 4-tuple shape is unchanged for all bridgegen callers.
    """
    p = _cap.parse_ref(s)
    if p is None:
        return None
    kind, owner, name, desc = p
    return owner, name, desc, kind


def split_desc(d: str):
    if not d.startswith("(") or ")" not in d:
        return None
    i = d.index(")")
    args, ret = d[1:i], d[i + 1:]
    out, j = [], 0
    while j < len(args):
        c = args[j]
        if c == "L":
            k = args.index(";", j)
            out.append(args[j:k + 1]); j = k + 1
        elif c == "[":
            k = j
            while k < len(args) and args[k] == "[":
                k += 1
            if k < len(args) and args[k] == "L":
                k = args.index(";", k)
            out.append(args[j:k + 1]); j = k + 1
        else:
            out.append(c); j += 1
    return out, ret


class Decl:
    def __init__(self, path):
        self.classes = set()
        # M and F MUST stay separate: a field and a method may share a name.
        # Only M descriptors are legal HostBridge candidates.
        self.methods = collections.defaultdict(lambda: collections.defaultdict(set))
        self.fields = collections.defaultdict(lambda: collections.defaultdict(set))
        self.sup = {}
        self.ifs = {}
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln in f:
                p = ln.rstrip("\n").split("\t")
                if not p or p[0].startswith("#"):
                    continue
                if p[0] == "C" and len(p) >= 2:
                    self.classes.add(p[1])
                elif p[0] == "S" and len(p) >= 3:
                    self.sup[p[1]] = p[2]
                    self.ifs[p[1]] = [x for x in p[3].split(",") if x] if len(p) > 3 else []
                elif len(p) >= 4 and p[0] == "M":
                    self.methods[p[1]][p[2]].add(p[3])
                elif len(p) >= 4 and p[0] == "F":
                    self.fields[p[1]][p[2]].add(p[3])
        self._cache = {}

    def cands(self, owner, name):
        """Mirror LinkCheck.findSameNameOtherDesc(): self -> super -> interfaces BFS."""
        k = (owner, name)
        if k in self._cache:
            return self._cache[k]
        q = collections.deque([owner])
        seen, out = set(), set()
        while q:
            c = q.popleft()
            if c in seen:
                continue
            seen.add(c)
            out |= self.methods.get(c, {}).get(name, set())
            if self.sup.get(c):
                q.append(self.sup[c])
            q.extend(self.ifs.get(c, []))
        r = sorted(out)
        self._cache[k] = r
        return r


def load_callkind(path):
    """owner|name|desc -> set(opcode-kind)."""
    out = collections.defaultdict(set)
    with open(path, encoding="utf-8") as f:
        for ln in f:
            p = ln.rstrip("\n").split("\t")
            if len(p) != 4 or p[0].startswith("#"):
                continue
            out[(p[0], p[1], p[2])].add(p[3])
    return out


def param_conv(old, new):
    """Mechanical conversion old -> new; None means 'needs a human'."""
    if old == new:
        return "-"
    if old in INTLIKE and new in INTLIKE:
        return "-"                        # JVM int family shares one verifier type
    if old in INTLIKE and new in WIDEN.get(old, set()):
        return {"J": "i2l", "F": "i2f", "D": "i2d"}[new]
    if old == "J" and new in ("F", "D"):
        return {"F": "l2f", "D": "l2d"}[new]
    if old == "F" and new == "D":
        return "f2d"
    return None


def return_conv(legacy, target):
    """Opcode converting the TARGET return back to the LEGACY return.

    Only identity / widening is mechanical.  Narrowing (target double ->
    legacy float) and reference conversions are never guessed.
    """
    if legacy == target:
        return "-"
    if legacy == "V":
        return "pop"                      # target returns a value; discard it
    if target == "V":
        return None                       # legacy wants a value, target has none
    if target in INTLIKE and legacy in INTLIKE:
        return "-"                        # same JVM int-family verifier type
    if target in INTLIKE and legacy in ("J", "F", "D"):
        return {"J": "i2l", "F": "i2f", "D": "i2d"}[legacy]
    if target == "J" and legacy in ("F", "D"):
        return {"F": "l2f", "D": "l2d"}[legacy]
    if target == "F" and legacy == "D":
        return "f2d"
    return None


def shape(old_desc, new_desc):
    """Return (ops, reason) or (None, rejection-reason)."""
    a, b = split_desc(old_desc), split_desc(new_desc)
    if a is None or b is None:
        return None, "UNPARSABLE_DESC"
    oa, orr = a
    na, nr = b
    if len(oa) != len(na):
        return None, "ARITY_CHANGE"
    ops = []
    for x, y in zip(oa, na):
        c = param_conv(x, y)
        if c is None:
            return None, "REF_OR_NARROWING_PARAM"
        ops.append(c)
    r = return_conv(orr, nr)
    if r is None:
        return None, "RETURN_UNCONVERTIBLE"
    return (ops, r), None


def java_type(d):
    if d in ("B", "S", "C", "I", "J", "F", "D", "Z"):
        return {"B": "byte", "S": "short", "C": "char", "I": "int", "J": "long",
                "F": "float", "D": "double", "Z": "boolean"}[d]
    if d == "V":
        return "void"
    if d.startswith("["):
        return java_type(d[1:]) + "[]"
    if d.startswith("L") and d.endswith(";"):
        return d[1:-1].replace("/", ".")
    return "Object"


def java_ident(s):
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]
    return "mcp_" + h


def adapters_for(version, owner, accepted):
    """One generated class per owner; bodies throw until a human writes semantics."""
    cls = "Adapter_" + hashlib.sha1((version + "|" + owner).encode()).hexdigest()[:12]
    lines = ["// GENERATED by tools/bridgegen.py -- DO NOT SHIP UNREVIEWED.",
             "// Every method throws until a human implements the semantic conversion.",
             "// Compile with the TARGET game jar on the classpath.",
             "package mcport.generated;", "", "public final class " + cls + " {",
             "    private " + cls + "() {}", ""]
    seen = set()
    for r in accepted:
        if r["method"] in seen:
            raise RuntimeError("duplicate adapter method: " + r["method"])
        seen.add(r["method"])
        args, ret = split_desc(r["oldDesc"])
        params = []
        if r["kind"] == "virtual":
            params.append(java_type("L" + owner + ";") + " host")
        for i, a in enumerate(args):
            params.append(java_type(a) + " a" + str(i))
        lines += ["    /** " + r["name"] + " " + r["oldDesc"] + " → " + r["newDesc"] + " */",
                  "    public static " + java_type(ret) + " " + r["method"] + "("
                  + ", ".join(params) + ") {",
                  "        throw new UnsupportedOperationException(",
                  '                "MCPORT_HUMAN_REVIEW_REQUIRED " + "'
                  + r["oldDesc"].replace("\\", "\\\\").replace('"', '\\"') + " → "
                  + r["newDesc"].replace("\\", "\\\\").replace('"', '\\"') + '");',
                  "    }", ""]
    lines.append("}")
    return cls, "\n".join(lines) + "\n"


def write_tsv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def process(target, out_root, repo, classes, java, emit_rules):
    version = target["version"]
    out = Path(out_root) / version
    out.mkdir(parents=True, exist_ok=True)
    decl = Decl(target["decl"])

    ck = target.get("callkind")
    if not ck:
        ck = str(out / "callkind.tsv")
        cp = str(classes) + os.pathsep + str(Path(repo) / "lib" / "*")
        cmd = [java, "-cp", cp, "mcport.CallKind"]
        for j in target["jars"]:
            cmd += ["--in", j]
        cmd += ["--out", ck]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError("CallKind failed: " + r.stderr[-800:])
    kinds = load_callkind(ck)

    tickets = []
    for t in target["tickets"]:
        with open(t, encoding="utf-8") as f:
            tickets.append((os.path.basename(t), json.load(f)))

    stats = collections.Counter()
    triage, accepted, seen_rules = [], [], {}
    for ticket_name, d in tickets:
        for bucket in ("SIGCHG", "MISSING"):
            for s in d.get("details", {}).get(bucket, []):
                stats["total"] += 1
                stats["bucket_" + bucket] += 1
                p = parse_ref(s)
                if p is None:
                    stats["REJECT_UNPARSED"] += 1
                    triage.append([version, bucket, s, "REJECT_UNPARSED", "", "", ""])
                    continue
                owner, name, desc, mf = p
                ops = kinds.get((owner, name, desc), set())
                op = "-".join(sorted(ops)) if ops else "unknown-by-bytecode"
                stats["opcode_" + op] += 1
                row = [version, bucket, s.split("  #")[0], "", "", "", op]
                if mf == "F":
                    status, reason = "REJECT_FIELD", "field type change is not a method bridge"
                elif name in CTOR:
                    status, reason = "REJECT_CTOR", "HostBridge cannot bridge a constructor"
                elif bucket == "MISSING":
                    status, reason = "REJECT_NO_TARGET", "target member is gone; use §15 C-line relocation or a manual adapter"
                elif not ops:
                    status, reason = "REJECT_NO_CALLKIND", "invoke opcode not observed in supplied jars"
                elif ops & {"mixed", "special", "interface", "other"}:
                    status, reason = "REJECT_OPCODE", "unsupported or mixed invoke kind"
                elif len(ops) != 1:
                    status, reason = "REJECT_OPCODE", "ambiguous invoke kind"
                else:
                    kind = next(iter(ops))
                    cands = [x for x in decl.cands(owner, name) if x != desc]
                    if not cands:
                        status, reason = "REJECT_NO_CANDIDATE", "no same-name method in target decl (BFS)"
                    elif len(cands) > 1:
                        status, reason = "REJECT_AMBIGUOUS", str(len(cands)) + " same-name target descriptors"
                    else:
                        conv, why = shape(desc, cands[0])
                        if conv is None:
                            status, reason = "REJECT_SEMANTIC_CONVERSION", why
                        else:
                            status = "SKELETON_MECHANICAL_UNSAFE"
                            reason = "numeric widening / void discard is a semantic change; adapter throws"
                            rule = dict(version=version, ticket=ticket_name,
                                        owner=owner, name=name, oldDesc=desc,
                                        newDesc=cands[0], kind=kind,
                                        method=java_ident(name + "|" + desc + "|" +
                                                          cands[0] + "|" + kind),
                                        conversions=conv)
                            key = (owner, name, desc, cands[0], kind)
                            if key in seen_rules:
                                stats["duplicate_candidates"] += 1
                            else:
                                seen_rules[key] = True
                                accepted.append(rule)
                            row[5] = cands[0]
                row[3], row[4] = status, reason
                stats[status] += 1
                triage.append(row)

    write_tsv(out / "triage.tsv",
              ["version", "bucket", "ref", "status", "reason", "targetDesc", "invokeKind"], triage)

    # HostBridge-shaped 6-column candidates.  Never auto-fed to a JVM.
    # One rule per unique (owner,name,oldDesc,newDesc,kind): the same missing
    # symbol often appears in several mod tickets; duplicate injected methods
    # would fail JVM verification.
    by_owner = collections.defaultdict(list)
    for r in sorted(accepted, key=lambda x: (x["owner"], x["name"], x["oldDesc"],
                                              x["newDesc"], x["kind"])):
        by_owner[r["owner"]].append(r)
    rules = ["# mcport bridgegen candidates -- HUMAN REVIEW REQUIRED; never auto-load",
             "# owner\toldName\toldDesc\tkind\tadapterClass\tadapterMethod"]
    adapters = out / "adapters"
    adapters.mkdir(exist_ok=True)
    for owner, rs in sorted(by_owner.items()):
        cls, src = adapters_for(version, owner, rs)
        (adapters / (cls + ".java")).write_text(src, encoding="utf-8")
        for r in rs:
            r["adapterClass"] = "mcport/generated/" + cls
            rules.append("\t".join([owner, r["name"], r["oldDesc"], r["kind"],
                                    r["adapterClass"], r["method"]]))
    (out / "bridge-candidates.tsv").write_text("\n".join(rules) + "\n", encoding="utf-8")
    if emit_rules:
        (out / "bridge-rules.tsv").write_text("\n".join(rules) + "\n", encoding="utf-8")

    stats["auto_fixed"] = 0
    stats["candidate_rules"] = len(accepted)
    stats["adapter_classes"] = len(by_owner)
    stats["duplicate_candidates"] = stats.get("duplicate_candidates", 0)
    with open(out / "stats.json", "w", encoding="utf-8") as f:
        json.dump({"schema": SCHEMA, "version": version, "stats": dict(stats),
                   "candidates": accepted}, f, ensure_ascii=False, indent=2, sort_keys=True)
    return version, dict(stats), accepted


def main():
    ap = argparse.ArgumentParser(description="McPort bridgegen: fail-loud SIGCHG/MISSING workbench")
    ap.add_argument("--spec", required=True, help="JSON: {schema, targets:[{version,decl,tickets[],jars[]|callkind}]}")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--classes", default="", help="dir containing mcport/CallKind.class")
    ap.add_argument("--java", default="java")
    ap.add_argument("--emit-rules", action="store_true",
                    help="also write bridge-rules.tsv (explicit human acknowledgement)")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    if spec.get("schema") != SCHEMA:
        raise SystemExit("unsupported spec schema: " + str(spec.get("schema")))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows, allstats = [], collections.Counter()
    for t in spec["targets"]:
        v, st, _ = process(t, out, a.repo, a.classes or str(Path(a.repo) / "build" / "mcport"),
                           a.java, a.emit_rules)
        rows.append([v, st.get("total", 0), st.get("bucket_SIGCHG", 0), st.get("bucket_MISSING", 0),
                     st.get("candidate_rules", 0), st.get("SKELETON_MECHANICAL_UNSAFE", 0),
                     st.get("REJECT_SEMANTIC_CONVERSION", 0), st.get("REJECT_OPCODE", 0),
                     st.get("REJECT_CTOR", 0), st.get("REJECT_FIELD", 0),
                     st.get("REJECT_NO_CANDIDATE", 0), st.get("REJECT_AMBIGUOUS", 0),
                     st.get("REJECT_NO_CALLKIND", 0), st.get("REJECT_UNPARSED", 0),
                     st.get("REJECT_NO_TARGET", 0),
                     st.get("duplicate_candidates", 0), st.get("auto_fixed", 0)])
        allstats.update(st)
    write_tsv(out / "summary.csv",
              ["version", "total", "sigchg", "missing", "candidate_rules",
               "skeleton_mechanical_unsafe", "reject_semantic_conversion", "reject_opcode",
               "reject_ctor", "reject_field", "reject_no_candidate", "reject_ambiguous",
               "reject_no_callkind", "reject_unparsed", "reject_no_target",
               "duplicate_candidates", "auto_fixed"], rows)
    print("RESULT", "targets=" + str(len(rows)),
          "refs=" + str(sum(r[1] for r in rows)),
          "candidate_rules=" + str(sum(r[4] for r in rows)),
          "auto_fixed=0")


if __name__ == "__main__":
    main()
