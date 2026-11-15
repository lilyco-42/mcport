#!/usr/bin/env python3
"""McPort 0.1.9 / REPORT section 18: version capability contract + fail-loud ship gate.

纯标准库。只读取调用方自备的 decl-*.tsv / map-*.tsv / bridge-*.tsv、
loader plan JSON、LinkCheck 工单 JSON、stringsurface / bridgegen 聚合 stats.json。
不下载、不内置、不分发 Mojang 类字节、官方映射或第三方 mod 字节码。

设计约束（REPORT 7 / 12 / 13 / 14 / 15 / 16 / 17）：
  * 26.x 官方去混淆表是「命名空间身份桥」：含 C 行、逆向有碰撞，
    只能供离线 RemapTool / stringsurface 使用，绝不能当 LinkCheck --map。
  * 输出只允许 READY / NEEDS_MANUAL / UNSUPPORTED。READY 仅表示
    「静态符号证据齐备且零 SIGCHG/MISSING」，不表示能跑或行为等价。
  * 同名同签名语义漂移静态不可判定；本工具不做任何行为等价承诺。
"""

import argparse
import csv
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter

SCHEMA = 1
ALLOWED_VERDICTS = ('READY', 'NEEDS_MANUAL', 'UNSUPPORTED')
RANK = {'READY': 0, 'NEEDS_MANUAL': 1, 'UNSUPPORTED': 2}
EXIT_CODE = {'READY': 0, 'NEEDS_MANUAL': 2, 'UNSUPPORTED': 1}
DISCLAIMER = (
    'READY 仅表示静态符号证据齐备且零 SIGCHG/MISSING；'
    '不表示能在真实客户端运行，也不表示行为等价。'
)
CLAIM_POLICY = 'static-evidence-only; no runtime claim'
GEN_OBF = 'obf'
GEN_DEOBF = 'deobf'

OBJ_IN_DESC = re.compile(r'L([^;]+);')
METHOD_DESC = re.compile(r'^\([^)]*\)(?:V|\[*(?:[BCDFIJSZ]|L[^;]+;))$')
FIELD_DESC = re.compile(r'^\[*(?:[BCDFIJSZ]|L[^;]+;)$')
MEMBER_NAME = re.compile(r'^(?:<init>|<clinit>|[A-Za-z_$][A-Za-z0-9_$]*)$')


class InputError(Exception):
    """spec / 输入文件格式错误：与「证据不足」区分，但仍 fail-loud。"""


def worst(verdicts):
    out = 'READY'
    for v in verdicts:
        if v not in RANK:
            raise ValueError('unknown verdict: ' + str(v))
        if RANK[v] > RANK[out]:
            out = v
    return out


def ev_new(source, version, kind):
    return {
        'source': source,
        'version': version,
        'kind': kind,
        'verdict': 'READY',
        'reasons': [],
        'counts': {},
    }


def ev_raise(ev, verdict, code):
    if RANK[verdict] > RANK[ev['verdict']]:
        ev['verdict'] = verdict
    if code not in ev['reasons']:
        ev['reasons'].append(code)


def read_rows(path):
    """逐行读 tab 表；跳过空行与 # 注释；返回 (行号, 列列表)。"""
    with open(path, 'r', encoding='utf-8') as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            yield lineno, line.split('\t')


class Decl:
    def __init__(self, path):
        self.path = path
        self.classes = set()
        self.methods = set()
        self.fields = set()
        self.supers = {}
        self.ifaces = {}
        self.digest = ''
        self.rows = 0


def load_decl(path):
    d = Decl(path)
    cap = set()
    for lineno, p in read_rows(path):
        d.rows += 1
        if p[0] == 'C' and len(p) >= 2:
            d.classes.add(p[1])
            cap.add('C\t' + p[1])
        elif p[0] == 'M' and len(p) >= 4:
            key = (p[1], p[2], p[3])
            d.methods.add(key)
            cap.add('M\t' + p[1] + '\t' + p[2] + '\t' + p[3])
        elif p[0] == 'F' and len(p) >= 4:
            key = (p[1], p[2], p[3])
            d.fields.add(key)
            cap.add('F\t' + p[1] + '\t' + p[2] + '\t' + p[3])
        elif p[0] == 'S' and len(p) >= 4:
            d.supers[p[1]] = p[2]
            d.ifaces[p[1]] = tuple(x for x in p[3].split(',') if x)
        else:
            raise InputError('bad decl row ' + str(lineno) + ': ' + repr(p))
    if not d.classes:
        raise InputError('decl has no C rows: ' + path)
    ordered = sorted(cap)
    d.digest = hashlib.sha256(('\n'.join(ordered) + '\n').encode('utf-8')).hexdigest()
    return d


class MapFile:
    def __init__(self, path, kind):
        self.path = path
        self.kind = kind
        self.cmap = {}
        self.mrows = []
        self.frows = []
        self.srows = []
        self.c_rev_collisions = 0
        self.c_old_dupes = 0


def load_map(path, kind):
    if kind not in ('map', 'bridge'):
        raise InputError('unknown map kind: ' + str(kind))
    m = MapFile(path, kind)
    cnew = Counter()
    cold = Counter()
    for lineno, p in read_rows(path):
        if p[0] == 'C' and len(p) >= 3:
            cold[p[1]] += 1
            cnew[p[2]] += 1
            if p[1] in m.cmap and m.cmap[p[1]] != p[2]:
                raise InputError('conflicting C row ' + str(lineno) + ': ' + p[1])
            m.cmap[p[1]] = p[2]
        elif p[0] == 'M' and len(p) >= 5:
            m.mrows.append((p[1], p[2], p[3], p[4]))
        elif p[0] == 'F' and len(p) >= 5:
            m.frows.append((p[1], p[2], p[3], p[4]))
        elif p[0] == 'S' and len(p) >= 4:
            m.srows.append((p[1], p[2], p[3]))
        else:
            raise InputError('bad map row ' + str(lineno) + ': ' + repr(p))
    m.c_rev_collisions = sum(1 for v in cnew.values() if v > 1)
    m.c_old_dupes = sum(1 for v in cold.values() if v > 1)
    m.reversed = False
    return m


def reverse_map(m):
    """严格 map 的逆向自证：old/new 名互换，源/目标 decl 也须互换。

    只允许无 C 行、无逆向碰撞的 map（实测 1.20.1 / 1.21.11 方向满足）。
    26.x bridge 含 C 行且官方名合并不可逆，绝不参与 reverse。
    """
    if m.kind != 'map':
        raise InputError('reverse is only allowed for a strict map')
    if m.cmap:
        raise InputError('reverse requires a map without C rows')
    _, m_amb = map_lookup(m, 'M')
    _, f_amb = map_lookup(m, 'F')
    if m_amb or f_amb:
        raise InputError('reverse requires unambiguous map keys')
    r = MapFile(m.path, 'map')
    r.c_rev_collisions = m.c_rev_collisions
    r.c_old_dupes = m.c_old_dupes
    r.mrows = [(o, d, nn, on) for o, d, on, nn in m.mrows]
    r.frows = [(o, d, nn, on) for o, d, on, nn in m.frows]
    r.srows = list(m.srows)
    r.reversed = True
    return r


def remap_desc(desc, cmap):
    if not cmap:
        return desc
    return OBJ_IN_DESC.sub(
        lambda mo: 'L' + cmap.get(mo.group(1), mo.group(1)) + ';', desc)


def map_lookup(m, kind):
    """返回 (owner, oldName, desc) -> newName；同一键多值记歧义。"""
    rows = m.mrows if kind == 'M' else m.frows
    out = {}
    ambiguous = 0
    for owner, desc, oldn, newn in rows:
        k = (owner, oldn, desc)
        if k in out and out[k] != newn:
            ambiguous += 1
        out[k] = newn
    return out, ambiguous


def audit_map(m, src, dst, label):
    """严格双向核对：源 decl 命中、目标 decl 命中、逆向碰撞。"""
    out = {
        'label': label,
        'path': m.path,
        'kind': m.kind,
        'reversed': bool(getattr(m, 'reversed', False)),
        'c_rows': len(m.cmap),
        'm_rows': len(m.mrows),
        'f_rows': len(m.frows),
        's_rows': len(m.srows),
        'c_rev_collisions': m.c_rev_collisions,
        'c_old_dupes': m.c_old_dupes,
        'strict': False,
        'reasons': [],
    }
    cmap = m.cmap
    for kind in ('M', 'F'):
        rows = m.mrows if kind == 'M' else m.frows
        stab = src.methods if kind == 'M' else src.fields
        dtab = dst.methods if kind == 'M' else dst.fields
        src_hit = 0
        dst_hit = 0
        rev = Counter()
        for owner, desc, oldn, newn in rows:
            if (owner, oldn, desc) in stab:
                src_hit += 1
            new_owner = cmap.get(owner, owner)
            new_desc = remap_desc(desc, cmap)
            if (new_owner, newn, new_desc) in dtab:
                dst_hit += 1
            rev[(new_owner, new_desc, newn)] += 1
        low = kind.lower()
        out[low + '_src_hit'] = src_hit
        out[low + '_dst_hit'] = dst_hit
        out[low + '_reverse_collisions'] = sum(1 for v in rev.values() if v > 1)
    _, m_amb = map_lookup(m, 'M')
    _, f_amb = map_lookup(m, 'F')
    out['m_map_ambiguous'] = m_amb
    out['f_map_ambiguous'] = f_amb
    reasons = []
    if m_amb or f_amb:
        reasons.append('MAP_KEY_AMBIGUOUS')
    if m.kind != 'map':
        reasons.append('BRIDGE_NOT_A_LINKCHECK_MAP')
    if cmap:
        reasons.append('C_ROWS_CHANGE_OWNER_NAMESPACE')
    if out['c_rev_collisions'] or out['c_old_dupes']:
        reasons.append('CLASS_IDENTITY_COLLISION')
    if out['m_reverse_collisions'] or out['f_reverse_collisions']:
        reasons.append('MEMBER_REVERSE_COLLISION')
    if out['m_src_hit'] != len(m.mrows) or out['f_src_hit'] != len(m.frows):
        reasons.append('SOURCE_DECL_MISS')
    if out['m_dst_hit'] != len(m.mrows) or out['f_dst_hit'] != len(m.frows):
        reasons.append('TARGET_DECL_MISS')
    out['reasons'] = reasons
    out['strict'] = (m.kind == 'map' and not reasons)
    return out


def surface_diff(src, dst, m, label, direction):
    """精确 API 表面差：same / lost / added / renamed / sigchg / missing。

    索引一次性预建；禁止在循环里重建全量表（§18.7 踩坑）。
    """
    row = {'label': label, 'direction': direction, 'map_kind': m.kind if m else 'none'}
    class_lost = src.classes - dst.classes
    row['classes_same'] = len(src.classes & dst.classes)
    row['classes_lost'] = len(class_lost)
    row['classes_added'] = len(dst.classes - src.classes)
    cmap = m.cmap if m else {}
    row['classes_renamed'] = sum(
        1 for owner in class_lost if cmap.get(owner) in dst.classes)
    for kind in ('M', 'F'):
        stab = src.methods if kind == 'M' else src.fields
        dtab = dst.methods if kind == 'M' else dst.fields
        same = stab & dtab
        lost = stab - dtab
        name_index = set()
        for owner, name, desc in dtab:
            name_index.add((owner, name))
        lookup, ambiguous = map_lookup(m, kind) if m else ({}, 0)
        renamed = 0
        mapped_target_absent = 0
        sigchg = 0
        missing = 0
        for owner, name, desc in lost:
            new_owner = cmap.get(owner, owner)
            new_desc = remap_desc(desc, cmap)
            newn = lookup.get((owner, name, desc))
            if newn is not None:
                if (new_owner, newn, new_desc) in dtab:
                    renamed += 1
                else:
                    mapped_target_absent += 1
            elif (new_owner, name) in name_index:
                sigchg += 1
            else:
                missing += 1
        low = 'methods' if kind == 'M' else 'fields'
        row[low + '_same'] = len(same)
        row[low + '_lost'] = len(lost)
        row[low + '_added'] = len(dtab - stab)
        row[low + '_renamed'] = renamed
        row[low + '_mapped_target_absent'] = mapped_target_absent
        row[low + '_sigchg'] = sigchg
        row[low + '_missing'] = missing
        row[low + '_map_ambiguous'] = ambiguous
    row['identity_break'] = bool(cmap)
    return row


# Strict JVMS 4.3 descriptor grammar (REPORT section 21).
# The legacy FIELD_DESC/METHOD_DESC used L[^;]+;, which accepts an embedded
# '[' and a second 'L' inside the class name.  LinkCheck.toString() emits
# owner + "." + name + desc with NO delimiter, so a loose grammar picks the
# FIRST legal split and can emit a descriptor that exists in no class file
# (e.g. name='shader', desc='LightDirections[Lorg/joml/Vector3f;').  Such a
# contract key never matches a constant-pool member and LinkGate's unknown-ref
# default RESOLVE silently passes a known SIGCHG.  Strict grammar rejects it.
# Where the source text is genuinely ambiguous (an object-typed field whose
# name contains 'L'), all legal splits are collected and the LONGEST legal
# member name wins; that residual is documented, never claimed as a proof.
_STRICT_IDENT = r'[A-Za-z_$][A-Za-z0-9_$]*'
_STRICT_OBJ = r'L' + _STRICT_IDENT + r'(?:/' + _STRICT_IDENT + r')*;'
STRICT_FIELD_DESC = re.compile(r'^\[*(?:[BCDFIJSZ]|' + _STRICT_OBJ + r')$')
STRICT_METHOD_DESC = re.compile(
    r'^\((?:\[*(?:[BCDFIJSZ]|' + _STRICT_OBJ + r'))*\)'
    r'(?:V|\[*(?:[BCDFIJSZ]|' + _STRICT_OBJ + r'))$')


def parse_ref(s):
    """解析 LinkCheck details 中的 owner.name(desc)ret / owner.name<desc> 引用。

    Strict descriptor grammar; see REPORT section 21.  Returns
    ('M'|'F', owner, name, desc) or None.  For fields, the longest legal
    member name (shortest legal descriptor) is used when several splits fit.
    """
    s = s.split('  # ', 1)[0].strip()
    s = s.split('  -> ', 1)[0].strip()
    if '.' not in s:
        return None
    owner, rest = s.split('.', 1)
    i = rest.find('(')
    if i >= 0:
        name, desc = rest[:i], rest[i:]
        if MEMBER_NAME.fullmatch(name) and STRICT_METHOD_DESC.fullmatch(desc):
            return ('M', owner, name, desc)
        return None
    best = None
    for k in range(1, len(rest)):
        name, desc = rest[:k], rest[k:]
        if MEMBER_NAME.fullmatch(name) and STRICT_FIELD_DESC.fullmatch(desc):
            best = ('F', owner, name, desc)
    return best


def gate_tickets(pattern, version):
    ev = ev_new(pattern, version, 'linkcheck_tickets')
    files = sorted(glob.glob(pattern))
    agg = Counter()
    bad = 0
    refs = 0
    if not files:
        ev_raise(ev, 'UNSUPPORTED', 'NO_TICKETS')
        ev['counts'] = {'files': 0}
        return ev
    for p in files:
        with open(p, 'r', encoding='utf-8') as fh:
            d = json.load(fh)
        det = d.get('details') or {}
        scalars = {
            'RESOLVE': d.get('resolve'),
            'RENAME': d.get('rename'),
            'SIGCHG': d.get('sigchg'),
            'MISSING': d.get('missing'),
        }
        for k, v in scalars.items():
            if v is None or len(det.get(k, [])) != v:
                bad += 1
        if sum(len(v) for v in det.values()) != d.get('total'):
            bad += 1
        for bucket, arr in det.items():
            agg[bucket] += len(arr)
            for ref in arr:
                refs += 1
                if parse_ref(ref) is None:
                    bad += 1
    ev['counts'] = {
        'files': len(files),
        'refs': refs,
        'resolve': agg.get('RESOLVE', 0),
        'rename': agg.get('RENAME', 0),
        'sigchg': agg.get('SIGCHG', 0),
        'missing': agg.get('MISSING', 0),
        'external': agg.get('EXTERNAL', 0),
        'integrity_errors': bad,
    }
    if bad:
        ev_raise(ev, 'UNSUPPORTED', 'TICKET_INTEGRITY')
    if agg.get('SIGCHG', 0) + agg.get('MISSING', 0) > 0:
        ev_raise(ev, 'NEEDS_MANUAL', 'MANUAL_REFS')
    return ev


UNSUPPORTED_ROUTES = (
    'UNSUPPORTED_NON_JVM', 'UNKNOWN_GENERATION', 'UNSUPPORTED_LOADER',
    'NATIVE_BOUND', 'RUNTIME_JAVA_MISMATCH',
)
KNOWN_VERDICTS = (
    'AUTO', 'NEEDS_MANUAL', 'UNSUPPORTED', 'PLAN_ONLY',
    'MISSING_ARTIFACT', 'CHECK_FAILED',
)


def gate_plan(entry, version, generation, source):
    ev = ev_new(source, version, 'loader_plan')
    verdict = entry.get('verdict')
    route = entry.get('route') or ''
    strategy = entry.get('strategy') or ''
    mode = entry.get('checkMode') or ''
    check = entry.get('check')
    ev['counts'] = {
        'route': route,
        'verdict': verdict,
        'strategy': strategy,
        'sigchg': (check or {}).get('sigchg', 0),
        'missing': (check or {}).get('missing', 0),
        'total': (check or {}).get('total', 0),
        'resolve': (check or {}).get('resolve', 0),
        'mod': (entry.get('mod') or {}).get('file', ''),
    }
    if verdict == 'UNSUPPORTED' or route in UNSUPPORTED_ROUTES or route.startswith('UNSUPPORTED'):
        ev_raise(ev, 'UNSUPPORTED', 'LOADER_UNSUPPORTED')
    if verdict == 'MISSING_ARTIFACT':
        ev_raise(ev, 'UNSUPPORTED', 'MISSING_ARTIFACT')
    if verdict == 'CHECK_FAILED':
        ev_raise(ev, 'UNSUPPORTED', 'CHECK_FAILED')
    if verdict == 'PLAN_ONLY':
        ev_raise(ev, 'UNSUPPORTED', 'PLAN_ONLY_NOT_SYMBOL_CHECKED')
    if verdict not in KNOWN_VERDICTS:
        ev_raise(ev, 'UNSUPPORTED', 'UNKNOWN_VERDICT')
    if generation == GEN_DEOBF and route == 'DEOBF_BREAK' and strategy == 'startup':
        ev_raise(ev, 'UNSUPPORTED', 'DEOBF_STARTUP_AGENT_FORBIDDEN')
    # 26.x 身份桥只能走「离线 RemapTool + 无 --map 复测」；任何用桥表直接喂
    # LinkCheck --map 的计划（REPORT 14 的 C5 反例）一律拒绝。
    if generation == GEN_DEOBF and entry.get('bridge') and check is not None:
        checked_jar = check.get('checkedJar')
        offline_ok = bool(checked_jar) and (
            'no --map' in mode or 'RemapTool' in mode)
        if not offline_ok:
            ev_raise(ev, 'UNSUPPORTED', 'BRIDGE_AS_LINKCHECK_MAP')
    if verdict == 'NEEDS_MANUAL':
        ev_raise(ev, 'NEEDS_MANUAL', 'MANUAL_ADAPTERS_REQUIRED')
    if verdict == 'AUTO':
        if check is None:
            ev_raise(ev, 'UNSUPPORTED', 'AUTO_WITHOUT_SYMBOL_CHECK')
        elif not check.get('ok') or check.get('rc') not in (0, None):
            ev_raise(ev, 'UNSUPPORTED', 'AUTO_CHECK_FAILED')
        elif check.get('sigchg', 0) + check.get('missing', 0) > 0:
            ev_raise(ev, 'NEEDS_MANUAL', 'AUTO_BUT_MANUAL_REFS')
    return ev


def load_stats(path):
    with open(path, 'r', encoding='utf-8') as fh:
        d = json.load(fh)
    if d.get('schema') != SCHEMA:
        raise InputError('bad stats schema: ' + path)
    st = d.get('stats')
    if not isinstance(st, dict):
        raise InputError('bad stats object: ' + path)
    return st


def gate_stats_stringsurface(entry):
    ev = ev_new(entry['path'], entry['version'], 'stringsurface_stats')
    st = load_stats(entry['path'])
    unresolved = st.get('unresolved', 0)
    ev['counts'] = {
        'string_occurrences': st.get('string_occurrences', 0),
        'unique_strings': st.get('unique_strings', 0),
        'unresolved': unresolved,
        'rewritten_entries': st.get('rewritten_entries', 0),
    }
    if unresolved > 0:
        ev_raise(ev, 'NEEDS_MANUAL', 'UNRESOLVED_STRING_SURFACE')
    return ev


def gate_stats_bridgegen(entry):
    ev = ev_new(entry['path'], entry['version'], 'bridgegen_stats')
    st = load_stats(entry['path'])
    auto_fixed = st.get('auto_fixed', 0)
    candidates = st.get('candidate_rules', 0)
    ev['counts'] = {
        'total': st.get('total', 0),
        'candidate_rules': candidates,
        'auto_fixed': auto_fixed,
    }
    if auto_fixed != 0:
        ev_raise(ev, 'UNSUPPORTED', 'UNSAFE_AUTO_BRIDGE_FIX')
    if candidates > 0:
        ev_raise(ev, 'NEEDS_MANUAL', 'UNREVIEWED_BRIDGE_CANDIDATES')
    return ev


def assert_no_claims(result):
    """输出自检：verdict 必须三选一，禁止出现兼容/能跑承诺。"""
    if result['verdict'] not in ALLOWED_VERDICTS:
        raise AssertionError('invalid overall verdict')
    for ev in result['evidence']:
        if ev['verdict'] not in ALLOWED_VERDICTS:
            raise AssertionError('invalid evidence verdict')
    for word in ('兼容', '能跑', '可运行', 'runnable', 'compatible'):
        if word in result['claim_policy']:
            raise AssertionError('claim policy contains forbidden word')
    return True


def write_csv(path, rows, columns, delimiter=','):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction='ignore',
                           delimiter=delimiter, lineterminator='\n')
        w.writeheader()
        for row in rows:
            w.writerow(row)


def build_result(spec):
    if spec.get('schema') != SCHEMA:
        raise InputError('spec.schema must be 1')
    versions = spec.get('versions') or []
    if not versions:
        raise InputError('spec.versions is empty')
    decls = {}
    contracts = []
    for v in versions:
        name = v['version']
        gen = v.get('generation')
        if gen not in (GEN_OBF, GEN_DEOBF):
            raise InputError('bad generation for ' + str(name))
        if name in decls:
            raise InputError('duplicate version ' + str(name))
        decls[name] = load_decl(v['decl'])
        d = decls[name]
        contracts.append({
            'version': name,
            'generation': gen,
            'decl': v['decl'],
            'rows': d.rows,
            'classes': len(d.classes),
            'methods': len(d.methods),
            'fields': len(d.fields),
            'supers': len(d.supers),
            'ifaces': len(d.ifaces),
            'capability_digest': d.digest,
        })
    gen_by_version = {v['version']: v.get('generation') for v in versions}

    map_audits = []
    surface_rows = []
    evidence = []
    for mspec in spec.get('maps') or []:
        src_name = mspec['from']
        dst_name = mspec['to']
        if src_name not in decls or dst_name not in decls:
            raise InputError('map references unknown version')
        kind = mspec.get('kind', 'map')
        m = load_map(mspec['path'], kind)
        if mspec.get('reverse'):
            m = reverse_map(m)
        label = src_name + '_to_' + dst_name
        if getattr(m, 'reversed', False):
            label += '_reverse'
        audit = audit_map(m, decls[src_name], decls[dst_name], label)
        audit['from'] = src_name
        audit['to'] = dst_name
        audit['direction'] = mspec.get('direction', 'forward')
        map_audits.append(audit)
        surface_rows.append(surface_diff(
            decls[src_name], decls[dst_name], m, label,
            audit['direction']))
        ev = ev_new(mspec['path'], dst_name, 'map_audit')
        ev['counts'] = {
            'kind': kind, 'strict': audit['strict'],
            'c_rows': audit['c_rows'],
            'm_dst_hit': audit['m_dst_hit'],
            'f_dst_hit': audit['f_dst_hit'],
            'm_reverse_collisions': audit['m_reverse_collisions'],
            'f_reverse_collisions': audit['f_reverse_collisions'],
        }
        if kind == 'map' and not audit['strict']:
            ev_raise(ev, 'UNSUPPORTED', 'MAP_NOT_STRICT')
        if kind == 'bridge' and audit['strict']:
            ev_raise(ev, 'UNSUPPORTED', 'BRIDGE_INCONSISTENTLY_STRICT')
        if kind == 'bridge' and audit['c_rows'] == 0:
            ev_raise(ev, 'UNSUPPORTED', 'BRIDGE_WITHOUT_CLASS_IDENTITY')
        evidence.append(ev)

    deobf_versions = [v['version'] for v in versions
                      if v.get('generation') == GEN_DEOBF]
    bridged = [m['to'] for m in (spec.get('maps') or [])
               if m.get('kind') == 'bridge']
    for name in deobf_versions:
        ev = ev_new('deobf_contract', name, 'identity_bridge')
        ev['counts'] = {'bridged': name in bridged}
        if name not in bridged:
            ev_raise(ev, 'UNSUPPORTED', 'DEOBF_IDENTITY_BRIDGE_MISSING')
        evidence.append(ev)

    for plan_path in spec.get('plans') or []:
        with open(plan_path, 'r', encoding='utf-8') as fh:
            plan = json.load(fh)
        target = plan.get('target') or {}
        version = target.get('id') or 'unknown'
        gen = target.get('generation') or gen_by_version.get(version)
        if gen not in (GEN_OBF, GEN_DEOBF):
            ev = ev_new(plan_path, version, 'loader_plan')
            ev_raise(ev, 'UNSUPPORTED', 'UNKNOWN_TARGET_GENERATION')
            evidence.append(ev)
            continue
        for entry in plan.get('plan') or []:
            evidence.append(gate_plan(entry, version, gen, plan_path))

    for tspec in spec.get('tickets') or []:
        evidence.append(gate_tickets(tspec['glob'], tspec['version']))
    for entry in (spec.get('stats') or {}).get('stringsurface') or []:
        evidence.append(gate_stats_stringsurface(entry))
    for entry in (spec.get('stats') or {}).get('bridgegen') or []:
        evidence.append(gate_stats_bridgegen(entry))

    if not any(e['kind'] in ('loader_plan', 'linkcheck_tickets')
               for e in evidence):
        ev = ev_new('spec', 'all', 'evidence_coverage')
        ev_raise(ev, 'UNSUPPORTED', 'NO_SYMBOL_EVIDENCE')
        evidence.append(ev)

    verdicts = Counter(e['verdict'] for e in evidence)
    overall = worst(e['verdict'] for e in evidence)
    result = {
        'schema': SCHEMA,
        'tool': 'mcport-capability',
        'disclaimer': DISCLAIMER,
        'claim_policy': CLAIM_POLICY,
        'verdict': overall,
        'contracts': contracts,
        'map_audits': map_audits,
        'surface_diffs': surface_rows,
        'evidence': evidence,
        'counts': {
            'versions': len(contracts),
            'maps': len(map_audits),
            'surface_diffs': len(surface_rows),
            'evidence_items': len(evidence),
            'verdict_READY': verdicts.get('READY', 0),
            'verdict_NEEDS_MANUAL': verdicts.get('NEEDS_MANUAL', 0),
            'verdict_UNSUPPORTED': verdicts.get('UNSUPPORTED', 0),
        },
    }
    assert_no_claims(result)
    return result


def write_contract_tsv(decl, path):
    """从 Decl 集合写出确定性能力清单（只写调用方 --out-dir）。"""
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('# mcport capability contract digest=' + decl.digest + '\n')
        for owner in sorted(decl.classes):
            fh.write('C\t' + owner + '\n')
        for owner, name, desc in sorted(decl.methods):
            fh.write('M\t' + owner + '\t' + name + '\t' + desc + '\n')
        for owner, name, desc in sorted(decl.fields):
            fh.write('F\t' + owner + '\t' + name + '\t' + desc + '\n')
        for owner in sorted(set(decl.supers) | set(decl.ifaces)):
            fh.write('S\t' + owner + '\t' + decl.supers.get(owner, '') +
                     '\t' + ','.join(decl.ifaces.get(owner, ())) + '\n')


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='McPort 0.1.9 capability contract + fail-loud ship gate')
    ap.add_argument('--spec', required=True, help='自备 spec JSON（路径占位符，不随包分发）')
    ap.add_argument('--out-dir', required=True, help='审计产物目录')
    ap.add_argument('--emit-contract', action='store_true',
                    help='额外写完整 capability-<version>.tsv（只写 --out-dir）')
    ap.add_argument('--no-gate', action='store_true',
                    help='无论 verdict 如何都返回 0（仅调试）')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args(argv)
    try:
        with open(args.spec, 'r', encoding='utf-8') as fh:
            spec = json.load(fh)
        result = build_result(spec)
    except (InputError, KeyError, ValueError, OSError, AssertionError,
            json.JSONDecodeError) as exc:
        print('CAPABILITY_INPUT_ERROR: ' + str(exc), file=sys.stderr)
        return 1
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, 'gate.json'), 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write('\n')
    map_cols = [
        'label', 'from', 'to', 'direction', 'kind', 'reversed',
        'c_rows', 'm_rows', 'f_rows',
        's_rows', 'c_rev_collisions', 'c_old_dupes', 'm_src_hit', 'm_dst_hit',
        'm_reverse_collisions', 'f_src_hit', 'f_dst_hit',
        'f_reverse_collisions', 'm_map_ambiguous', 'f_map_ambiguous', 'strict',
    ]
    write_csv(os.path.join(args.out_dir, 'map-audit.csv'),
              result['map_audits'], map_cols)
    surface_cols = [
        'label', 'direction', 'map_kind', 'identity_break',
        'classes_same', 'classes_lost', 'classes_added', 'classes_renamed',
        'methods_same', 'methods_lost', 'methods_added', 'methods_renamed',
        'methods_mapped_target_absent', 'methods_sigchg', 'methods_missing',
        'methods_map_ambiguous',
        'fields_same', 'fields_lost', 'fields_added', 'fields_renamed',
        'fields_mapped_target_absent', 'fields_sigchg', 'fields_missing',
        'fields_map_ambiguous',
    ]
    write_csv(os.path.join(args.out_dir, 'surface-diff.csv'),
              result['surface_diffs'], surface_cols)
    triage_rows = []
    for ev in result['evidence']:
        reasons = ev['reasons'] or ['OK']
        for code in reasons:
            triage_rows.append({
                'source': ev['source'],
                'version': ev['version'],
                'kind': ev['kind'],
                'verdict': ev['verdict'],
                'reason': code,
            })
    write_csv(os.path.join(args.out_dir, 'triage.tsv'), triage_rows,
              ['source', 'version', 'kind', 'verdict', 'reason'],
              delimiter='\t')
    with open(os.path.join(args.out_dir, 'stats.json'), 'w', encoding='utf-8') as fh:
        json.dump({'schema': SCHEMA, 'verdict': result['verdict'],
                   'counts': result['counts']}, fh,
                  ensure_ascii=False, indent=2, sort_keys=True)
        fh.write('\n')
    if args.emit_contract:
        # 完整能力清单从调用方自备 decl 重建；只写 --out-dir，不进仓库/发布包。
        for v in spec.get('versions') or []:
            decl = load_decl(v['decl'])
            write_contract_tsv(decl, os.path.join(
                args.out_dir, 'capability-' + v['version'] + '.tsv'))
    if not args.quiet:
        c = result['counts']
        print('verdict: ' + result['verdict'])
        print('versions=' + str(c['versions']) + ' maps=' + str(c['maps']) +
              ' evidence=' + str(c['evidence_items']) +
              ' READY=' + str(c['verdict_READY']) +
              ' NEEDS_MANUAL=' + str(c['verdict_NEEDS_MANUAL']) +
              ' UNSUPPORTED=' + str(c['verdict_UNSUPPORTED']))
        print(DISCLAIMER)
    if args.no_gate:
        return 0
    return EXIT_CODE[result['verdict']]


if __name__ == '__main__':
    sys.exit(main())
