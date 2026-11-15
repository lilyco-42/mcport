#!/usr/bin/env python3
"""McPort 0.2.0 / REPORT section 19: startup capability-gate contract generator regression.

Pure standard library. Self-contained (tempfile-synthesised tickets) + an optional
real-ticket aggregation over the already-distributed data/hotmods/*.json.
The agent's runtime 53 assertions live in demo/gate/run.sh.
"""

import glob
import importlib.util
import json
import os
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("linkgate_contract", os.path.join(HERE, "linkgate_contract.py"))
lg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lg)

COUNT = 0
TAB = chr(9)
NL = chr(10)


def ok(cond, msg):
    global COUNT
    if not cond:
        raise AssertionError("assert #" + str(COUNT + 1) + ": " + msg)
    COUNT += 1


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def write_obj(path, obj):
    return write(path, json.dumps(obj, ensure_ascii=False, indent=2) + NL)


def empty_details():
    return {"RESOLVE": [], "RENAME": [], "SIGCHG": [], "MISSING": [], "EXTERNAL": []}


def ticket_obj(mod, det, resolve=None, rename=None, sigchg=None, missing=None, total=None, bad_scalar=False):
    resolve = len(det["RESOLVE"]) if resolve is None else resolve
    rename = len(det["RENAME"]) if rename is None else rename
    sigchg = len(det["SIGCHG"]) if sigchg is None else sigchg
    missing = len(det["MISSING"]) if missing is None else missing
    total = sum(len(v) for v in det.values()) if total is None else total
    if bad_scalar:
        resolve = resolve + 1
    return {"mod": mod, "total": total, "resolve": resolve, "rename": rename,
            "sigchg": sigchg, "missing": missing, "autoFixCeiling": 100.0,
            "details": det}


def ticket_file(root, name, resolve, rename, sigchg, missing, external=0, bad_scalar=False, bad_total=False):
    det = empty_details()
    for i in range(resolve):
        det["RESOLVE"].append("com/example/A.m" + str(i) + "()V")
    for i in range(rename):
        det["RENAME"].append("com/example/A.r" + str(i) + "()V")
    for i in range(sigchg):
        det["SIGCHG"].append("com/example/A.s" + str(i) + "()V")
    for i in range(missing):
        det["MISSING"].append("com/example/A.g" + str(i) + "()V")
    for i in range(external):
        det["EXTERNAL"].append("com/mojang/lib/L.field" + str(i) + "Ljava/lang/String;  # external")
    total = sum(len(v) for v in det.values())
    if bad_total:
        total = total + 1
    obj = ticket_obj("/tmp/" + name + ".jar", det, total=total, bad_scalar=bad_scalar)
    return write_obj(os.path.join(root, name + ".json"), obj)


def unit():
    d = tempfile.mkdtemp(prefix="linkgate-contract-")
    p = ticket_file(d, "t1", 3, 2, 1, 1, external=2)
    text, stats, conflicts = lg.build([p], "26.1")
    ok(text.endswith(NL), "output ends with newline")
    lines = text.splitlines()
    ok(lines[0].startswith("# mcport-linkgate-contract schema=1 version=26.1"), "schema header")
    ok("source_sha256=" in lines[1], "source sha header")
    ok("default to RESOLVE" in lines[2], "resolve-default note")
    ok("owner" in lines[3] and "name" in lines[3] and "desc" in lines[3] and "status" in lines[3], "column note")
    data = [l for l in lines if not l.startswith("#")]
    ok(len(data) == 7, "7 unique refs (3+2+1+1, external ignored)")
    ok(stats["raw_external"] == 2, "external ignored count")
    ok(stats["contract_sigchg"] == 1 and stats["contract_missing"] == 1, "sigchg/missing counts")
    ok(stats["contract_resolve"] == 3 and stats["contract_rename"] == 2, "resolve/rename counts")
    ok(all(len(l.split(TAB)) == 4 for l in data), "4 tab columns")
    ok(all(l.split(TAB)[3] in ("RESOLVE", "RENAME", "SIGCHG", "MISSING") for l in data), "status set")
    ok(data == sorted(data), "rows sorted")

    pb = ticket_file(d, "bad1", 3, 0, 0, 0, bad_scalar=True)
    try:
        lg.build([pb], "26.1")
        ok(False, "should reject bad scalar")
    except lg.ContractError:
        ok(True, "reject bad scalar")
    pt = ticket_file(d, "bad2", 3, 0, 0, 0, bad_total=True)
    try:
        lg.build([pt], "26.1")
        ok(False, "should reject bad total")
    except lg.ContractError:
        ok(True, "reject bad total")

    det_a = empty_details()
    det_a["RESOLVE"].append("com/example/A.same()V")
    a = write_obj(os.path.join(d, "ca.json"), ticket_obj("/tmp/ca.jar", det_a))
    det_b = empty_details()
    det_b["SIGCHG"].append("com/example/A.same()V  # same key, different status")
    b = write_obj(os.path.join(d, "cb.json"), ticket_obj("/tmp/cb.jar", det_b))
    try:
        lg.build([a, b], "26.1")
        ok(False, "should reject conflict")
    except lg.ContractError as e:
        ok("contradictory" in str(e), "reject conflict")

    q = ticket_file(d, "tq", 5, 4, 3, 2, external=1)
    t1, s1, _ = lg.build([q], "26.1")
    t2, s2, _ = lg.build([q], "26.1")
    ok(t1 == t2, "deterministic build")
    ok(s1 == s2, "deterministic stats")
    ok(lg.source_digest([q]) == lg.source_digest([q]), "deterministic digest")
    row = lg.summary_row("26.1", [q], s1)
    ok(row["version"] == "26.1", "summary version")
    ok(row["unique_contract_refs"] == s1["unique"], "summary unique")
    ok(row["source_sha256"] == lg.source_digest([q]), "summary digest")

    try:
        lg.collect([os.path.join(d, "nope*.json")])
        ok(False, "should reject no-match")
    except lg.ContractError:
        ok(True, "reject no-match glob")
    return d


def real_tickets():
    pat = os.path.join(HERE, "..", "data", "hotmods", "26.1__*.json")
    hits = sorted(glob.glob(pat))
    if not hits:
        print("linkgate_contract: skip real-ticket check (no 26.1 tickets)")
        return
    ext = 0
    for h in hits:
        with open(h, "r", encoding="utf-8") as fh:
            ext += len(json.load(fh)["details"].get("EXTERNAL", []))
    text, stats, conflicts = lg.build(hits, "26.1")
    ok(conflicts == 0, "no conflicting statuses across 26.1 tickets")
    ok(stats["raw_external"] == ext, "external count matches recomputed")
    ok(stats["contract_resolve"] + stats["contract_rename"] + stats["contract_sigchg"] + stats["contract_missing"] == stats["unique"], "status counts sum to unique")
    ok(stats["tickets"] == len(hits), "ticket count")
    text2, _, _ = lg.build(hits, "26.1")
    ok(text == text2, "real-ticket build deterministic")
    print("linkgate_contract: 26.1 real tickets -> unique=" + str(stats["unique"]) + " resolve=" + str(stats["contract_resolve"]) + " rename=" + str(stats["contract_rename"]) + " sigchg=" + str(stats["contract_sigchg"]) + " missing=" + str(stats["contract_missing"]) + " external=" + str(ext))


def main():
    unit()
    real_tickets()
    print("RESULT ALL_OK assertions=" + str(COUNT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
