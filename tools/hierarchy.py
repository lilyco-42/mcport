#!/usr/bin/env python3
"""McPort 0.2.6 / REPORT section 25: decl inheritance-hierarchy reconciliation.

Pure standard library, offline, fail-loud. Reads one caller-supplied LinkCheck
decl TSV (C/S/M/F rows), an optional second decl for a digest-collision proof,
and an optional C-rename map. It reconciles how capability.py, LinkCheck.java
and classref.py interpret the SAME decl, and checks every explicit super /
interface target against that decl.

Three concrete defects are made visible:
  * capability.load_decl() keeps only C owners; LinkCheck.loadDecl() and
    classref.parse_decl() keep owners of ALL C/S/M/F rows.
  * capability.digest hashes only sorted C/M/F rows, so two decls with
    different S rows can share one capability digest.
  * S rows silently overwrite SUPER/IFACES (duplicate / conflicting rows),
    and a game super or interface deleted in the target decl makes
    JVMS 5.4.3.3 / 5.4.3.4 method resolution walk into an undeclared class.

It does NOT run the game, rewrite bytes, attach to a JVM, or claim runtime
compatibility. HIERARCHY_OK only means explicit hierarchy edges are statically
covered by that exact decl and no cross-tool class-surface divergence remains.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CAP = _load('mcport_capability_for_hierarchy', 'capability.py')
CR = _load('mcport_classref_for_hierarchy', 'classref.py')
AUD = _load('mcport_contract_audit_for_hierarchy', 'contract_audit.py')

SCHEMA = 1
TOOL = 'mcport.hierarchy'
LINKAGE_SPEC = 'JVMS 5.4.3.1 / 5.4.3.3 / 5.4.3.4'
CLAIM_POLICY = 'static-hierarchy-only; no runtime claim'
DISCLAIMER = 'does NOT mean runtime-compatible; hierarchy coverage does NOT prove semantic equivalence'
GAME_PREFIXES = AUD.GAME_PREFIXES
EXTERNAL_PREFIXES = AUD.EXTERNAL_PREFIXES
ALLOWED_STATUS = ('RESOLVE', 'RENAME', 'MISSING', 'EXTERNAL', 'THIRD_PARTY')
BLOCK_STATUS = ('MISSING', 'RENAME')
EXIT_CODE = {
    'HIERARCHY_OK': 0,
    'HIERARCHY_ONLY_OK': 0,
    'NEEDS_MANUAL': 2,
    'UNSUPPORTED': 1,
}
HARD_REASONS = frozenset((
    'DECL_BAD_ROW', 'DECL_BAD_OWNER', 'DECL_BAD_DESC',
    'DECL_BAD_HIERARCHY_NAME', 'DECL_NO_CLASSES', 'DECL_IO',
    'DECL_BAD_UTF8', 'BAD_VERSION', 'BAD_DECL_SHA256',
    'DECL_DIGEST_MISMATCH', 'BAD_GAME_PREFIX', 'MAP_BAD_ROW',
    'MAP_BAD_OWNER', 'MAP_CONFLICT', 'HIERARCHY_CYCLE',
    'S_ROW_CONFLICT', 'DUPLICATE_S_ROWS', 'CAPABILITY_VIEW_CONFLICT',
    'CAPABILITY_DIGEST_CONFLICT', 'CLASSREF_VIEW_CONFLICT',
    'CLASSREF_DECL_REJECTED', 'COMPARE_DECL_BAD', 'NO_DECL',
    'UNCLASSIFIED_REFS', 'MAP_TARGET_MISSING', 'MAPPED_TARGET_MISSING',
    'MAP_IO', 'MAP_BAD_UTF8', 'INTERNAL_ERROR',
))
TOOL_VIEWS = {
    'capability': 'tools/capability.py:98 load_decl (C owners only; S needs 4 cols; digest is C/M/F only)',
    'linkcheck': 'java/mcport/LinkCheck.java:297 loadDecl (C/S/M/F owners all classes; S 2-4 cols; SUPER/IFACES)',
    'classref': 'tools/classref.py:282 parse_decl (C/S/M/F owners all classes; S 2-4 cols; strict desc)',
}
SCOPE = {
    'covers': [
        'explicit S-row super and interface targets',
        'C/S/M/F owner semantics across capability, LinkCheck and classref',
        'capability C/M/F-only digest collisions caused by changed S rows',
        'duplicate / conflicting S rows and inheritance cycles',
        'optional exact C-rename map targets',
    ],
    'does_not_cover': [
        'implicit java/lang/Object inheritance when no S row exists',
        'runtime ClassLoader / Mixin / Fabric behaviour',
        'reflective or JSON string class names (see REPORT section 17)',
        'member resolution itself (see REPORT sections 19-24)',
        'same-name same-signature semantic drift',
    ],
}
SUMMARY_COLS = (
    'schema', 'tool', 'version', 'decl', 'decl_sha256', 'decl_digest_ok',
    'compare_decl', 'compare_decl_sha256', 'compare_capability_digest',
    'compare_hierarchy_digest', 'capability_digest', 'hierarchy_digest',
    'capability_digest_collision', 'map', 'map_sha256', 'map_rows',
    'map_ignored_rows', 'map_target_missing', 'rows', 'row_kinds',
    'c_class_count', 'java_class_count', 'classref_class_count',
    'divergent_owner_count', 'divergent_owners', 's_rows', 'super_edges',
    'iface_edges', 'resolve', 'rename', 'missing', 'external',
    'third_party', 'needs_manual', 'verdict', 'reasons',
)


class HierarchyError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def read_text(path, code):
    try:
        with open(path, 'rb') as fh:
            raw = fh.read()
    except OSError as e:
        raise HierarchyError(code + '_IO', 'cannot read ' + os.path.basename(path) + ': ' + str(e))
    try:
        return raw, raw.decode('utf-8')
    except UnicodeDecodeError as e:
        raise HierarchyError(code + '_BAD_UTF8', str(e))


def parse_decl_text(text):
    rows = []
    kinds = Counter()
    c_classes = set()
    all_classes = set()
    s_seen = {}
    duplicate_s = []
    conflicting_s = []
    for lineno, line in enumerate(text.split('\n'), 1):
        line = line.rstrip('\r')
        if not line or line[0] == '#':
            continue
        p = line.split('\t')
        if p[0] not in ('C', 'S', 'M', 'F'):
            raise HierarchyError('DECL_BAD_ROW', 'bad decl row ' + str(lineno))
        if len(p) < 2 or not AUD.valid_owner(p[1]):
            raise HierarchyError('DECL_BAD_OWNER', 'bad decl owner at row ' + str(lineno))
        if p[0] == 'C' and len(p) != 2:
            raise HierarchyError('DECL_BAD_ROW', 'C row needs 2 columns at line ' + str(lineno))
        if p[0] == 'S' and len(p) not in (2, 3, 4):
            raise HierarchyError('DECL_BAD_ROW', 'S row needs 2-4 columns at line ' + str(lineno))
        if p[0] in ('M', 'F'):
            if len(p) != 4:
                raise HierarchyError('DECL_BAD_ROW', p[0] + ' row needs 4 columns at line ' + str(lineno))
            if not (AUD.is_method_desc(p[3]) if p[0] == 'M' else AUD.is_field_desc(p[3])):
                raise HierarchyError('DECL_BAD_DESC', 'bad ' + p[0] + ' desc at line ' + str(lineno))
        owner = p[1]
        all_classes.add(owner)
        if p[0] == 'C':
            c_classes.add(owner)
        elif p[0] == 'S':
            sup = p[2] if len(p) >= 3 else ''
            iface_text = p[3] if len(p) >= 4 else ''
            if sup and not AUD.valid_owner(sup):
                raise HierarchyError('DECL_BAD_HIERARCHY_NAME', 'bad super at line ' + str(lineno))
            ifaces = tuple(x for x in iface_text.split(',') if x)
            for x in ifaces:
                if not AUD.valid_owner(x):
                    raise HierarchyError('DECL_BAD_HIERARCHY_NAME', 'bad interface at line ' + str(lineno))
            key = (sup, ifaces)
            if owner in s_seen:
                duplicate_s.append(owner)
                if s_seen[owner] != key:
                    conflicting_s.append(owner)
            s_seen[owner] = key
        rows.append((lineno, p))
        kinds[p[0]] += 1
    if not all_classes:
        raise HierarchyError('DECL_NO_CLASSES', 'decl contains no class rows')
    return {
        'rows': rows,
        'kinds': dict(kinds),
        'c_classes': c_classes,
        'all_classes': all_classes,
        'divergent': sorted(all_classes - c_classes),
        's_seen': s_seen,
        'duplicate_s': sorted(set(duplicate_s)),
        'conflicting_s': sorted(set(conflicting_s)),
    }


def capability_digest(rows):
    """Byte-for-byte mirror of tools/capability.py:98 load_decl().digest."""
    cap = set()
    for _lineno, p in rows:
        if p[0] == 'C' and len(p) >= 2:
            cap.add('C\t' + p[1])
        elif p[0] == 'M' and len(p) >= 4:
            cap.add('M\t' + p[1] + '\t' + p[2] + '\t' + p[3])
        elif p[0] == 'F' and len(p) >= 4:
            cap.add('F\t' + p[1] + '\t' + p[2] + '\t' + p[3])
    return hashlib.sha256(('\n'.join(sorted(cap)) + '\n').encode('utf-8')).hexdigest()


def hierarchy_digest(rows):
    """Full-row digest: unlike capability_digest, S rows and extra cols matter."""
    return hashlib.sha256(
        ('\n'.join(sorted('\t'.join(p) for _lineno, p in rows)) + '\n').encode('utf-8')
    ).hexdigest()


def tool_views(path, parsed):
    views = {}
    try:
        d = CAP.load_decl(path)
        views['capability'] = {
            'ok': True, 'classes': sorted(d.classes), 'digest': d.digest, 'error': '',
        }
    except CAP.InputError as e:
        views['capability'] = {'ok': False, 'classes': [], 'digest': '', 'error': str(e)}
    try:
        cr = CR.parse_decl(path)
        views['classref'] = {'ok': True, 'classes': sorted(cr['classes']), 'error': ''}
    except CR.ClassRefError as e:
        views['classref'] = {'ok': False, 'classes': [], 'error': str(e)}
    views['linkcheck'] = {
        'ok': True,
        'classes': sorted(parsed['all_classes']),
        'error': '',
        'note': 'derived from LinkCheck.loadDecl semantics; Java is not executed here',
    }
    return views


def find_cycles(s_seen):
    graph = defaultdict(list)
    for owner, (sup, ifaces) in s_seen.items():
        graph.setdefault(owner, [])
        if sup:
            graph[owner].append(sup)
        graph[owner].extend(ifaces)
    for targets in list(graph.values()):
        for t in targets:
            graph.setdefault(t, [])
    adj = {k: sorted(set(v)) for k, v in graph.items()}
    color = {}
    cycles = set()
    for start in sorted(adj):
        if color.get(start):
            continue
        color[start] = 1
        path = [start]
        onpath = set([start])
        stack = [(start, iter(adj[start]))]
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                color[node] = 2
                onpath.discard(node)
                path.pop()
                stack.pop()
                continue
            if color.get(nxt) == 1 and nxt in onpath:
                cycles.add(tuple(sorted(path[path.index(nxt):])))
                continue
            if color.get(nxt, 0) == 0:
                color[nxt] = 1
                path.append(nxt)
                onpath.add(nxt)
                stack.append((nxt, iter(adj[nxt])))
    return [list(c) for c in sorted(cycles)]


def classify_edges(parsed, cmap, bad_targets, prefixes, allow_third_party):
    edges = []
    mapped_to = {}
    reasons = set()
    counts = Counter()
    game = tuple(prefixes)
    for owner in sorted(parsed['s_seen']):
        sup, ifaces = parsed['s_seen'][owner]
        targets = [('SUPER', sup)] if sup else []
        targets += [('INTERFACE', x) for x in ifaces]
        for kind, target in targets:
            st = ''
            if target in parsed['all_classes']:
                st = 'RESOLVE'
            elif target in cmap:
                if cmap[target] in parsed['all_classes']:
                    st = 'RENAME'
                    mapped_to[target] = cmap[target]
                else:
                    st = 'MISSING'
                    reasons.add('MAPPED_TARGET_MISSING')
            elif target.startswith(EXTERNAL_PREFIXES):
                st = 'EXTERNAL'
            elif target.startswith(game):
                st = 'MISSING'
            else:
                st = 'THIRD_PARTY'
            counts[st] += 1
            edges.append({
                'owner': owner, 'kind': kind, 'target': target,
                'status': st, 'mapped_to': mapped_to.get(target, ''),
            })
    if bad_targets:
        reasons.add('MAP_TARGET_MISSING')
    if counts['MISSING']:
        reasons.add('MISSING_HIERARCHY_TARGET')
    if counts['THIRD_PARTY']:
        if not allow_third_party:
            reasons.add('UNCLASSIFIED_REFS')
        else:
            reasons.add('THIRD_PARTY_WAIVED')
    if not edges:
        reasons.add('NO_HIERARCHY_ROWS')
    return {
        'edges': edges,
        'mapped_to': dict(sorted(mapped_to.items())),
        'counts': {s: counts.get(s, 0) for s in ALLOWED_STATUS},
        'reasons': reasons,
    }


def base_report(args):
    return {
        'schema': SCHEMA,
        'tool': TOOL,
        'claim_policy': CLAIM_POLICY,
        'linkage_spec': LINKAGE_SPEC,
        'scope': SCOPE,
        'tool_views_spec': TOOL_VIEWS,
        'disclaimer': DISCLAIMER,
        'version': args.version or '',
        'decl': args.decl or '',
        'decl_sha256': '',
        'expected_decl_sha256': args.decl_sha256 or '',
        'decl_digest_ok': None,
        'decl_rows': 0,
        'decl_row_kinds': {},
        'c_classes': [],
        'java_classes': [],
        'classref_classes': [],
        'divergent_owners': [],
        's_rows': 0,
        'duplicate_s_rows': [],
        'conflicting_s_rows': [],
        'cycles': [],
        'tool_views': {},
        'compare_decl': args.compare_decl or '',
        'compare_decl_sha256': '',
        'compare_capability_digest': '',
        'compare_hierarchy_digest': '',
        'capability_digest': '',
        'hierarchy_digest': '',
        'capability_digest_collision': False,
        'map': args.map or '',
        'map_sha256': '',
        'map_rows': 0,
        'map_ignored_rows': 0,
        'map_target_missing': [],
        'super_edges': 0,
        'iface_edges': 0,
        'counts_by_status': {s: 0 for s in ALLOWED_STATUS},
        'samples_by_status': {s: [] for s in ALLOWED_STATUS},
        'mapped_to': {},
        'edges': [],
        'game_prefixes': [],
        'allow_third_party': bool(args.allow_third_party),
        'coverage_only': bool(args.coverage_only),
        'verdict': 'UNSUPPORTED',
        'reasons': [],
        'needs_manual': 0,
        'error': '',
    }


def audit(args):
    report = base_report(args)
    reasons = set()
    if args.version and any(c.isspace() for c in args.version):
        reasons.add('BAD_VERSION')
    if args.decl_sha256 and not re.fullmatch(r'[0-9a-f]{64}', args.decl_sha256):
        reasons.add('BAD_DECL_SHA256')
    bad_prefixes = [p for p in args.game_prefix if not p or any(c.isspace() for c in p)
                    or '.' in p or p.startswith('/')]
    prefixes = sorted(set(list(GAME_PREFIXES) + [p for p in args.game_prefix if p not in bad_prefixes]))
    report['game_prefixes'] = prefixes
    if bad_prefixes:
        reasons.add('BAD_GAME_PREFIX')
    parsed = None
    raw = b''
    try:
        raw, text = read_text(args.decl, 'DECL')
        parsed = parse_decl_text(text)
    except HierarchyError as e:
        reasons.add(e.code)
        report['error'] = str(e)
    if parsed is not None:
        report['decl_sha256'] = hashlib.sha256(raw).hexdigest()
        report['decl_rows'] = len(parsed['rows'])
        report['decl_row_kinds'] = parsed['kinds']
        report['c_classes'] = sorted(parsed['c_classes'])
        report['java_classes'] = sorted(parsed['all_classes'])
        report['classref_classes'] = sorted(parsed['all_classes'])
        report['divergent_owners'] = parsed['divergent']
        report['s_rows'] = len(parsed['s_seen'])
        report['duplicate_s_rows'] = parsed['duplicate_s']
        report['conflicting_s_rows'] = parsed['conflicting_s']
        if args.decl_sha256:
            report['decl_digest_ok'] = args.decl_sha256 == report['decl_sha256']
            if not report['decl_digest_ok']:
                reasons.add('DECL_DIGEST_MISMATCH')
        report['capability_digest'] = capability_digest(parsed['rows'])
        report['hierarchy_digest'] = hierarchy_digest(parsed['rows'])
        views = tool_views(args.decl, parsed)
        report['tool_views'] = views
        if views['capability']['ok']:
            if views['capability']['classes'] != report['c_classes']:
                reasons.add('CAPABILITY_VIEW_CONFLICT')
            if views['capability']['digest'] != report['capability_digest']:
                reasons.add('CAPABILITY_DIGEST_CONFLICT')
        else:
            reasons.add('CAPABILITY_DECL_REJECTED')
            if not parsed['c_classes']:
                reasons.add('CAPABILITY_NO_C_ROWS')
        if views['classref']['ok']:
            if views['classref']['classes'] != report['java_classes']:
                reasons.add('CLASSREF_VIEW_CONFLICT')
        else:
            reasons.add('CLASSREF_DECL_REJECTED')
        if parsed['divergent']:
            reasons.add('CAPABILITY_CLASS_SURFACE_GAP')
        if parsed['duplicate_s']:
            reasons.add('DUPLICATE_S_ROWS')
        if parsed['conflicting_s']:
            reasons.add('S_ROW_CONFLICT')
        cycles = find_cycles(parsed['s_seen'])
        report['cycles'] = cycles
        if cycles:
            reasons.add('HIERARCHY_CYCLE')
        try:
            mp = CR.parse_map(args.map, parsed['all_classes'])
        except CR.ClassRefError as e:
            reasons.add(e.code)
            report['error'] = str(e)
            mp = {'cmap': {}, 'bad_targets': [], 'ignored': 0, 'sha256': '', 'rows': 0}
        report['map_sha256'] = mp['sha256']
        report['map_rows'] = mp['rows']
        report['map_ignored_rows'] = mp['ignored']
        report['map_target_missing'] = mp['bad_targets']
        cls = classify_edges(parsed, mp['cmap'], mp['bad_targets'],
                             prefixes, args.allow_third_party)
        reasons |= cls['reasons']
        report['counts_by_status'] = cls['counts']
        report['samples_by_status'] = {
            s: sorted(set(e['target'] for e in cls['edges'] if e['status'] == s))[:20]
            for s in ALLOWED_STATUS
        }
        report['mapped_to'] = cls['mapped_to']
        report['edges'] = cls['edges']
        report['super_edges'] = sum(1 for e in cls['edges'] if e['kind'] == 'SUPER')
        report['iface_edges'] = sum(1 for e in cls['edges'] if e['kind'] == 'INTERFACE')
        if args.compare_decl:
            try:
                craw, ctext = read_text(args.compare_decl, 'COMPARE_DECL')
                cparsed = parse_decl_text(ctext)
            except HierarchyError:
                reasons.add('COMPARE_DECL_BAD')
                cparsed = None
            if cparsed is not None:
                report['compare_decl_sha256'] = hashlib.sha256(craw).hexdigest()
                report['compare_capability_digest'] = capability_digest(cparsed['rows'])
                report['compare_hierarchy_digest'] = hierarchy_digest(cparsed['rows'])
                if (report['capability_digest'] == report['compare_capability_digest']
                        and report['hierarchy_digest'] != report['compare_hierarchy_digest']):
                    report['capability_digest_collision'] = True
                    reasons.add('HIERARCHY_DIGEST_COLLISION')
    else:
        reasons.add('NO_DECL')
    report['reasons'] = sorted(reasons)
    counts = report['counts_by_status']
    needs_manual = (counts['MISSING'] + counts['RENAME']
                    + len(report['divergent_owners'])
                    + (1 if 'HIERARCHY_DIGEST_COLLISION' in reasons else 0)
                    + (1 if 'CAPABILITY_DECL_REJECTED' in reasons else 0))
    report['needs_manual'] = needs_manual
    if any(r in HARD_REASONS for r in reasons):
        report['verdict'] = 'UNSUPPORTED'
    elif args.coverage_only:
        report['verdict'] = 'HIERARCHY_ONLY_OK'
    elif needs_manual or reasons:
        report['verdict'] = 'NEEDS_MANUAL'
    else:
        report['verdict'] = 'HIERARCHY_OK'
    return report


def write_json(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def _csv_value(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, dict):
        return '|'.join(k + '=' + str(v[k]) for k in sorted(v))
    if isinstance(v, (list, tuple)):
        return '|'.join(str(x) for x in v)
    return v


def write_summary(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    row = {
        'schema': report['schema'], 'tool': report['tool'],
        'version': report['version'], 'decl': report['decl'],
        'decl_sha256': report['decl_sha256'], 'decl_digest_ok': report['decl_digest_ok'],
        'compare_decl': report['compare_decl'],
        'compare_decl_sha256': report['compare_decl_sha256'],
        'compare_capability_digest': report['compare_capability_digest'],
        'compare_hierarchy_digest': report['compare_hierarchy_digest'],
        'capability_digest': report['capability_digest'],
        'hierarchy_digest': report['hierarchy_digest'],
        'capability_digest_collision': report['capability_digest_collision'],
        'map': report['map'], 'map_sha256': report['map_sha256'],
        'map_rows': report['map_rows'], 'map_ignored_rows': report['map_ignored_rows'],
        'map_target_missing': report['map_target_missing'],
        'rows': report['decl_rows'], 'row_kinds': report['decl_row_kinds'],
        'c_class_count': len(report['c_classes']),
        'java_class_count': len(report['java_classes']),
        'classref_class_count': len(report['classref_classes']),
        'divergent_owner_count': len(report['divergent_owners']),
        'divergent_owners': report['divergent_owners'],
        's_rows': report['s_rows'], 'super_edges': report['super_edges'],
        'iface_edges': report['iface_edges'],
        'resolve': report['counts_by_status']['RESOLVE'],
        'rename': report['counts_by_status']['RENAME'],
        'missing': report['counts_by_status']['MISSING'],
        'external': report['counts_by_status']['EXTERNAL'],
        'third_party': report['counts_by_status']['THIRD_PARTY'],
        'needs_manual': report['needs_manual'],
        'verdict': report['verdict'], 'reasons': report['reasons'],
    }
    row = {k: _csv_value(row[k]) for k in SUMMARY_COLS}
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(SUMMARY_COLS), lineterminator='\n')
        w.writeheader()
        w.writerow(row)


def stdout_line(report):
    c = report['counts_by_status']
    line = (
        'hierarchy: verdict=' + report['verdict']
        + ' rows=' + str(report['decl_rows'])
        + ' c_classes=' + str(len(report['c_classes']))
        + ' java_classes=' + str(len(report['java_classes']))
        + ' divergent=' + str(len(report['divergent_owners']))
        + ' s_rows=' + str(report['s_rows'])
        + ' edges=' + str(report['super_edges'] + report['iface_edges'])
        + ' resolve=' + str(c['RESOLVE'])
        + ' rename=' + str(c['RENAME'])
        + ' missing=' + str(c['MISSING'])
        + ' external=' + str(c['EXTERNAL'])
        + ' third_party=' + str(c['THIRD_PARTY'])
        + ' needs_manual=' + str(report['needs_manual'])
    )
    if report['reasons']:
        line += ' reasons=' + '|'.join(report['reasons'])
    if report['verdict'] in ('HIERARCHY_OK', 'HIERARCHY_ONLY_OK', 'NEEDS_MANUAL'):
        line += '; ' + DISCLAIMER
    return line


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--decl', required=True, help='target LinkCheck decl TSV (C/S/M/F rows)')
    ap.add_argument('--compare-decl', help='second decl for capability-digest collision proof')
    ap.add_argument('--map', help='optional C-rename map TSV')
    ap.add_argument('--version', help='target version label; no runtime meaning')
    ap.add_argument('--decl-sha256', help='bind the decl to an exact sha256 digest')
    ap.add_argument('--game-prefix', action='append', default=[],
                    help='additional internal-name prefix requiring decl coverage; repeatable')
    ap.add_argument('--allow-third-party', action='store_true',
                    help='acknowledge third-party namespaces; still reports THIRD_PARTY_WAIVED unless --coverage-only')
    ap.add_argument('--coverage-only', action='store_true',
                    help='explicitly waive NEEDS_MANUAL; still reports divergence and MISSING')
    ap.add_argument('--out', help='write deterministic JSON report')
    ap.add_argument('--summary', help='write deterministic one-row CSV summary')
    a = ap.parse_args(argv)
    try:
        report = audit(a)
    except HierarchyError as e:
        report = base_report(a)
        report['verdict'] = 'UNSUPPORTED'
        report['reasons'] = [e.code]
        report['error'] = str(e)
    except (OSError, ValueError, TypeError) as e:
        report = base_report(a)
        report['verdict'] = 'UNSUPPORTED'
        report['reasons'] = ['INTERNAL_ERROR']
        report['error'] = str(e)
    if a.out:
        write_json(a.out, report)
    if a.summary:
        write_summary(a.summary, report)
    print(stdout_line(report))
    if report['verdict'] not in ('HIERARCHY_OK', 'HIERARCHY_ONLY_OK'):
        detail = '; '.join(report['reasons'])
        if not detail and report['verdict'] == 'NEEDS_MANUAL':
            detail = 'NEEDS_MANUAL refs=' + str(report['needs_manual'])
        if report.get('error'):
            detail += ' - ' + str(report['error'])
        print('hierarchy: FAIL: ' + detail, file=sys.stderr)
    return EXIT_CODE.get(report['verdict'], 1)


if __name__ == '__main__':
    sys.exit(main())
