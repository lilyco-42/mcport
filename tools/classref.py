#!/usr/bin/env python3
"""McPort 0.2.5 / REPORT section 24: offline class-level linkage surface audit.

Pure standard library. Reads a caller-supplied LinkCheck decl TSV, an optional
C-map TSV and one mod jar. It recovers the exact class names the JVM would have
to resolve (JVMS 5.4.3.1) from CONSTANT_Class entries, NameAndType / MethodType
descriptors and this class field/method descriptors, then compares every
game-namespace name against the target decl.

It does NOT run the game, rewrite any byte, attach to a JVM, or claim runtime
compatibility. CLASSREFS_OK only means every visible game class reference is
declared by that exact target decl (or by one exact verified C rename).
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import struct
import sys
import zipfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AUD = _load('mcport_contract_audit_for_classref', 'contract_audit.py')

SCHEMA = 1
TOOL = 'mcport.classref'
ALLOWED_STATUS = ('RESOLVE', 'RENAME', 'MISSING', 'EXTERNAL', 'THIRD_PARTY', 'SELF')
BLOCK_STATUS = ('MISSING', 'RENAME')
GAME_PREFIXES = AUD.GAME_PREFIXES
EXTERNAL_PREFIXES = AUD.EXTERNAL_PREFIXES
DISCLAIMER = 'does NOT mean runtime-compatible; class resolution does NOT prove semantic equivalence'
CLAIM_POLICY = 'static-class-linkage-only; no runtime claim'
LINKAGE_SPEC = 'JVMS 5.4.3.1'
SCOPE = {
    'covers': [
        'CONSTANT_Class tag 7 names including array descriptors',
        'NameAndType tag 12 and MethodType tag 16 descriptors',
        'field_info and method_info descriptors',
    ],
    'does_not_cover': [
        'reflective or JSON string class names (see REPORT section 17)',
        'runtime ClassLoader / Mixin / Fabric behaviour',
        'same-name same-signature semantic drift',
    ],
}
EXIT_CODE = {
    'CLASSREFS_OK': 0,
    'CLASSREFS_ONLY_OK': 0,
    'NEEDS_MANUAL': 2,
    'UNSUPPORTED': 1,
}
SUMMARY_COLS = (
    'schema', 'tool', 'version', 'decl', 'decl_sha256', 'decl_digest_ok',
    'map', 'map_sha256', 'map_rows', 'map_ignored_rows', 'map_target_missing',
    'modjar', 'classes', 'cp_class_refs', 'desc_type_refs', 'unique_class_refs',
    'array_refs', 'own_classes', 'resolve', 'rename', 'missing', 'external',
    'third_party', 'self_count', 'needs_manual', 'verdict', 'reasons',
)


class ClassRefError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _u2(b, i):
    if i < 0 or i + 2 > len(b):
        raise ClassRefError('BAD_CLASS_FILE', 'truncated u2 at offset ' + str(i))
    return struct.unpack_from('>H', b, i)[0]


def valid_class_name(name):
    return name in ('module-info', 'package-info') or AUD.valid_owner(name)


def normalize_class_name(raw):
    if raw.startswith('['):
        try:
            return AUD.owner_namespace(raw)
        except AUD.AuditError as e:
            raise ClassRefError('BAD_ARRAY_CLASS', str(e))
    if not valid_class_name(raw):
        raise ClassRefError('BAD_CLASS_NAME', 'invalid CONSTANT_Class name: ' + repr(raw))
    return raw


def desc_object_types(desc):
    """Return sorted object class names embedded in a field or method descriptor."""
    if not (AUD.is_field_desc(desc) or AUD.is_method_desc(desc)):
        raise ClassRefError('BAD_DESCRIPTOR', 'invalid JVMS descriptor: ' + repr(desc))
    out = set()
    i = 0
    while i < len(desc):
        c = desc[i]
        if c == 'L':
            j = desc.find(';', i + 1)
            if j < 0:
                raise ClassRefError('BAD_DESCRIPTOR', 'unterminated object type: ' + repr(desc))
            inner = desc[i + 1:j]
            if not AUD.valid_owner(inner):
                raise ClassRefError('BAD_DESCRIPTOR', 'bad object type: ' + repr(inner))
            out.add(inner)
            i = j + 1
        else:
            i += 1
    return sorted(out)


def _skip_attrs(b, p, n):
    for _ in range(n):
        if p + 6 > len(b):
            raise ClassRefError('BAD_CLASS_FILE', 'truncated attribute header')
        length = struct.unpack_from('>I', b, p + 2)[0]
        p += 6 + length
        if p > len(b):
            raise ClassRefError('BAD_CLASS_FILE', 'truncated attribute body')
    return p


def parse_class(data):
    """Parse one class file into its class-level linkage surface.

    Returns dict with keys own, cp_class_names, desc_items. desc_items is a list
    of (descriptor, sorted object names) for every descriptor we can see.
    """
    try:
        count, entries, body = AUD.parse_constant_pool(data)
    except AUD.AuditError as e:
        raise ClassRefError(e.code, str(e))

    def utf8(idx):
        if idx <= 0 or idx >= count or entries[idx] is None:
            raise ClassRefError('BAD_CLASS_FILE', 'bad cp index ' + str(idx))
        e = entries[idx]
        if e[0] != 1:
            raise ClassRefError('BAD_CLASS_FILE', 'cp index ' + str(idx) + ' is not Utf8')
        try:
            return AUD.decode_modified_utf8(e[3:])
        except AUD.AuditError as ex:
            raise ClassRefError(ex.code, str(ex))

    def class_name(idx):
        if idx <= 0 or idx >= count or entries[idx] is None:
            raise ClassRefError('BAD_CLASS_FILE', 'bad class cp index ' + str(idx))
        e = entries[idx]
        if e[0] != 7:
            raise ClassRefError('BAD_CLASS_FILE', 'cp index ' + str(idx) + ' is not Class')
        return utf8(_u2(e, 1))

    if len(body) < 8:
        raise ClassRefError('BAD_CLASS_FILE', 'truncated class body')
    this_idx = _u2(body, 2)
    iface_count = _u2(body, 6)
    own = class_name(this_idx)
    if not valid_class_name(own):
        raise ClassRefError('BAD_CLASS_NAME', 'invalid this_class name: ' + repr(own))

    cp_names = []
    for i in range(1, count):
        e = entries[i]
        if e is None or e[0] != 7:
            continue
        cp_names.append(utf8(_u2(e, 1)))

    desc_items = []
    for i in range(1, count):
        e = entries[i]
        if e is None:
            continue
        if e[0] == 12:
            di = _u2(e, 3)
            d = utf8(di)
            desc_items.append((d, desc_object_types(d)))
        elif e[0] == 16:
            di = _u2(e, 1)
            d = utf8(di)
            desc_items.append((d, desc_object_types(d)))

    p = 8 + 2 * iface_count
    fields_count = _u2(body, p)
    p += 2
    for _ in range(fields_count):
        if p + 8 > len(body):
            raise ClassRefError('BAD_CLASS_FILE', 'truncated field info')
        di = _u2(body, p + 4)
        d = utf8(di)
        desc_items.append((d, desc_object_types(d)))
        p = _skip_attrs(body, p + 8, _u2(body, p + 6))
    methods_count = _u2(body, p)
    p += 2
    for _ in range(methods_count):
        if p + 8 > len(body):
            raise ClassRefError('BAD_CLASS_FILE', 'truncated method info')
        di = _u2(body, p + 4)
        d = utf8(di)
        desc_items.append((d, desc_object_types(d)))
        p = _skip_attrs(body, p + 8, _u2(body, p + 6))
    return {'own': own, 'cp_class_names': cp_names, 'desc_items': desc_items}


def scan_jar(path):
    if not os.path.isfile(path):
        raise ClassRefError('JAR_IO', 'mod jar not found: ' + os.path.basename(path))
    try:
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist() if not n.endswith('/') and n.endswith('.class'))
            if not names:
                raise ClassRefError('NO_CLASS_ENTRIES', 'mod jar contains no class entries')
            if len(names) != len(set(names)):
                raise ClassRefError('DUPLICATE_CLASS_ENTRY', 'duplicate .class entry names')
            per = []
            for name in names:
                try:
                    data = z.read(name)
                except (OSError, RuntimeError, zipfile.BadZipFile) as e:
                    raise ClassRefError('JAR_IO', 'cannot read ' + name + ': ' + str(e))
                per.append((name, parse_class(data)))
    except ClassRefError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as e:
        raise ClassRefError('JAR_IO', 'cannot scan mod jar: ' + str(e))
    return per


def aggregate(per):
    own = set(info['own'] for _, info in per)
    occurrences = Counter()
    cp_raw = {}
    desc_raw = {}
    origins = {}
    array_occurrences = 0
    for _entry, info in per:
        for raw in info['cp_class_names']:
            norm = normalize_class_name(raw)
            occurrences[norm] += 1
            cp_raw.setdefault(norm, set()).add(raw)
            origins.setdefault(norm, set()).add('CLASS_CP')
            if raw.startswith('['):
                array_occurrences += 1
        for desc, names in info['desc_items']:
            for name in names:
                occurrences[name] += 1
                desc_raw.setdefault(name, set()).add(desc)
                origins.setdefault(name, set()).add('DESCRIPTOR')
    return {
        'own': own,
        'occurrences': occurrences,
        'cp_raw': cp_raw,
        'desc_raw': desc_raw,
        'origins': origins,
        'array_occurrences': array_occurrences,
    }


def read_text(path, code):
    try:
        with open(path, 'rb') as fh:
            raw = fh.read()
    except OSError as e:
        raise ClassRefError(code + '_IO', 'cannot read ' + os.path.basename(path) + ': ' + str(e))
    try:
        return raw, raw.decode('utf-8')
    except UnicodeDecodeError as e:
        raise ClassRefError(code + '_BAD_UTF8', str(e))


def parse_decl(path):
    raw, text = read_text(path, 'DECL')
    classes = set()
    rows = 0
    kinds = Counter()
    for lineno, line in enumerate(text.split('\n'), 1):
        line = line.rstrip('\r')
        if not line or line[0] == '#':
            continue
        p = line.split('\t')
        if p[0] not in ('C', 'S', 'M', 'F'):
            raise ClassRefError('DECL_BAD_ROW', 'bad decl row ' + str(lineno))
        if len(p) < 2 or not AUD.valid_owner(p[1]):
            raise ClassRefError('DECL_BAD_OWNER', 'bad decl owner at row ' + str(lineno))
        if p[0] == 'C' and len(p) != 2:
            raise ClassRefError('DECL_BAD_ROW', 'C row needs 2 columns at line ' + str(lineno))
        if p[0] == 'S' and len(p) not in (2, 3, 4):
            raise ClassRefError('DECL_BAD_ROW', 'S row needs 2-4 columns at line ' + str(lineno))
        if p[0] in ('M', 'F'):
            if len(p) != 4:
                raise ClassRefError('DECL_BAD_ROW', p[0] + ' row needs 4 columns at line ' + str(lineno))
            if not (AUD.is_method_desc(p[3]) if p[0] == 'M' else AUD.is_field_desc(p[3])):
                raise ClassRefError('DECL_BAD_DESC', 'bad ' + p[0] + ' desc at line ' + str(lineno))
        rows += 1
        kinds[p[0]] += 1
        classes.add(p[1])
    if not classes:
        raise ClassRefError('DECL_NO_CLASSES', 'decl contains no class rows')
    return {
        'classes': classes,
        'rows': rows,
        'kinds': dict(kinds),
        'sha256': hashlib.sha256(raw).hexdigest(),
    }


def parse_map(path, decl_classes):
    if not path:
        return {'cmap': {}, 'bad_targets': [], 'ignored': 0, 'sha256': '', 'rows': 0}
    raw, text = read_text(path, 'MAP')
    cmap = {}
    ignored = 0
    rows = 0
    for lineno, line in enumerate(text.split('\n'), 1):
        line = line.rstrip('\r')
        if not line or line[0] == '#':
            continue
        p = line.split('\t')
        if p[0] in ('M', 'F', 'S'):
            ignored += 1
            continue
        if p[0] != 'C' or len(p) != 3:
            raise ClassRefError('MAP_BAD_ROW', 'bad map row ' + str(lineno))
        old, new = p[1], p[2]
        if not AUD.valid_owner(old) or not AUD.valid_owner(new):
            raise ClassRefError('MAP_BAD_OWNER', 'bad map owner at line ' + str(lineno))
        if old in cmap and cmap[old] != new:
            raise ClassRefError('MAP_CONFLICT', 'conflicting C line for ' + old)
        cmap[old] = new
        rows += 1
    bad_targets = sorted(set(new for new in cmap.values() if new not in decl_classes))
    return {
        'cmap': cmap,
        'bad_targets': bad_targets,
        'ignored': ignored,
        'sha256': hashlib.sha256(raw).hexdigest(),
        'rows': rows,
    }


def classify(agg, decl_classes, cmap, game_prefixes, allow_third_party, bad_map_targets):
    status = {}
    mapped_to = {}
    samples = {s: [] for s in ALLOWED_STATUS}
    reasons = set()
    for norm in sorted(agg['occurrences']):
        if norm in agg['own']:
            st = 'SELF'
        elif norm.startswith(EXTERNAL_PREFIXES):
            st = 'EXTERNAL'
        elif norm.startswith(tuple(game_prefixes)):
            if norm in decl_classes:
                st = 'RESOLVE'
            elif norm in cmap:
                target = cmap[norm]
                mapped_to[norm] = target
                if target in decl_classes:
                    st = 'RENAME'
                else:
                    st = 'MISSING'
                    reasons.add('MAPPED_TARGET_MISSING')
            else:
                st = 'MISSING'
        else:
            st = 'THIRD_PARTY'
        status[norm] = st
        samples[st].append(norm)
    if bad_map_targets:
        reasons.add('MAP_TARGET_MISSING')
    if any(st == 'THIRD_PARTY' for st in status.values()) and not allow_third_party:
        reasons.add('UNCLASSIFIED_REFS')
    if not any(st in ('RESOLVE', 'RENAME', 'MISSING') for st in status.values()):
        reasons.add('NO_GAME_REFS')
    return {
        'status': status,
        'mapped_to': mapped_to,
        'samples': samples,
        'reasons': reasons,
    }


def base_report(args):
    return {
        'schema': SCHEMA,
        'tool': TOOL,
        'claim_policy': CLAIM_POLICY,
        'linkage_spec': LINKAGE_SPEC,
        'scope': SCOPE,
        'disclaimer': DISCLAIMER,
        'version': args.version or '',
        'decl': os.path.basename(args.decl),
        'decl_sha256': '',
        'expected_decl_sha256': args.decl_sha256 or '',
        'decl_digest_ok': None,
        'decl_rows': 0,
        'decl_row_kinds': {},
        'map': os.path.basename(args.map) if args.map else '',
        'map_sha256': '',
        'map_rows': 0,
        'map_ignored_rows': 0,
        'map_target_missing': [],
        'modjar': os.path.basename(args.modjar),
        'classes': 0,
        'cp_class_refs': 0,
        'desc_type_refs': 0,
        'unique_class_refs': 0,
        'array_refs': 0,
        'own_classes': 0,
        'own_game_classes': [],
        'own_external_classes': [],
        'counts_by_status': {s: 0 for s in ALLOWED_STATUS},
        'samples_by_status': {s: [] for s in ALLOWED_STATUS},
        'mapped_to': {},
        'refs': [],
        'game_prefixes': [],
        'allow_third_party': bool(args.allow_third_party),
        'coverage_only': bool(args.coverage_only),
        'verdict': 'UNSUPPORTED',
        'reasons': [],
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
    try:
        decl = parse_decl(args.decl)
    except ClassRefError as e:
        reasons.add(e.code)
        report['error'] = str(e)
        decl = None
    if decl is not None:
        report['decl_sha256'] = decl['sha256']
        report['decl_rows'] = decl['rows']
        report['decl_row_kinds'] = decl['kinds']
        if args.decl_sha256:
            report['decl_digest_ok'] = args.decl_sha256 == decl['sha256']
            if not report['decl_digest_ok']:
                reasons.add('DECL_DIGEST_MISMATCH')
        try:
            mp = parse_map(args.map, decl['classes'])
        except ClassRefError as e:
            reasons.add(e.code)
            report['error'] = str(e)
            mp = {'cmap': {}, 'bad_targets': [], 'ignored': 0, 'sha256': '', 'rows': 0}
        report['map_sha256'] = mp['sha256']
        report['map_rows'] = mp['rows']
        report['map_ignored_rows'] = mp['ignored']
        report['map_target_missing'] = mp['bad_targets']
        try:
            per = scan_jar(args.modjar)
        except ClassRefError as e:
            reasons.add(e.code)
            report['error'] = str(e)
            per = []
        report['classes'] = len(per)
        if per:
            try:
                agg = aggregate(per)
            except ClassRefError as e:
                reasons.add(e.code)
                report['error'] = str(e)
                agg = None
        else:
            agg = None
        if agg is not None:
            report['cp_class_refs'] = sum(len(info['cp_class_names']) for _, info in per)
            report['desc_type_refs'] = sum(len(names) for _, info in per for _, names in info['desc_items'])
            report['unique_class_refs'] = len(agg['occurrences'])
            report['array_refs'] = agg['array_occurrences']
            report['own_classes'] = len(agg['own'])
            own_game = sorted(o for o in agg['own'] if o.startswith(tuple(prefixes)))
            own_external = sorted(o for o in agg['own'] if o.startswith(EXTERNAL_PREFIXES))
            report['own_game_classes'] = own_game
            report['own_external_classes'] = own_external
            if own_game:
                reasons.add('OWN_GAME_NAMESPACE')
            if own_external:
                reasons.add('OWN_EXTERNAL_NAMESPACE')
            cls = classify(agg, decl['classes'], mp['cmap'], prefixes,
                           args.allow_third_party, mp['bad_targets'])
            reasons |= cls['reasons']
            counts = Counter(cls['status'].values())
            report['counts_by_status'] = {s: counts.get(s, 0) for s in ALLOWED_STATUS}
            report['samples_by_status'] = {s: sorted(cls['samples'][s])[:20] for s in ALLOWED_STATUS}
            report['mapped_to'] = dict(sorted(cls['mapped_to'].items()))
            report['refs'] = [
                {
                    'class': norm,
                    'status': cls['status'][norm],
                    'occurrences': agg['occurrences'][norm],
                    'raw_class_names': sorted(agg['cp_raw'].get(norm, set())),
                    'descriptor_samples': sorted(agg['desc_raw'].get(norm, set()))[:10],
                    'origins': sorted(agg['origins'].get(norm, set())),
                    'mapped_to': cls['mapped_to'].get(norm, ''),
                }
                for norm in sorted(agg['occurrences'])
            ]
        else:
            reasons.add('NO_SCANNABLE_CLASSES')
    else:
        reasons.add('NO_DECL')
    report['reasons'] = sorted(reasons)
    needs_manual = report['counts_by_status']['MISSING'] + report['counts_by_status']['RENAME']
    report['needs_manual'] = needs_manual
    if reasons:
        report['verdict'] = 'UNSUPPORTED'
    elif args.coverage_only:
        report['verdict'] = 'CLASSREFS_ONLY_OK'
    elif needs_manual:
        report['verdict'] = 'NEEDS_MANUAL'
    else:
        report['verdict'] = 'CLASSREFS_OK'
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
    return v


def write_summary(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    row = {c: _csv_value(report.get(c, '')) for c in SUMMARY_COLS}
    row['self_count'] = report['counts_by_status']['SELF']
    row['resolve'] = report['counts_by_status']['RESOLVE']
    row['rename'] = report['counts_by_status']['RENAME']
    row['missing'] = report['counts_by_status']['MISSING']
    row['external'] = report['counts_by_status']['EXTERNAL']
    row['third_party'] = report['counts_by_status']['THIRD_PARTY']
    row['map_target_missing'] = '|'.join(report.get('map_target_missing', []))
    row['reasons'] = '|'.join(report.get('reasons', []))
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(SUMMARY_COLS), lineterminator='\n')
        w.writeheader()
        w.writerow(row)


def stdout_line(report):
    c = report['counts_by_status']
    line = (
        'classref: verdict=' + report['verdict']
        + ' classes=' + str(report['classes'])
        + ' cp_class_refs=' + str(report['cp_class_refs'])
        + ' desc_type_refs=' + str(report['desc_type_refs'])
        + ' unique=' + str(report['unique_class_refs'])
        + ' resolve=' + str(c['RESOLVE'])
        + ' rename=' + str(c['RENAME'])
        + ' missing=' + str(c['MISSING'])
        + ' external=' + str(c['EXTERNAL'])
        + ' third_party=' + str(c['THIRD_PARTY'])
        + ' self=' + str(c['SELF'])
        + ' needs_manual=' + str(report.get('needs_manual', 0))
    )
    reasons = report.get('reasons', [])
    if reasons:
        line += ' reasons=' + '|'.join(reasons)
    if report['verdict'] in ('CLASSREFS_OK', 'CLASSREFS_ONLY_OK', 'NEEDS_MANUAL'):
        line += '; ' + DISCLAIMER
    return line


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--decl', required=True, help='target LinkCheck decl TSV (C/S/M/F rows)')
    ap.add_argument('--modjar', required=True, help='mod jar whose .class files are audited')
    ap.add_argument('--map', help='optional C-rename map TSV')
    ap.add_argument('--version', help='target version label; no runtime meaning')
    ap.add_argument('--decl-sha256', help='bind the decl to an exact sha256 digest')
    ap.add_argument('--game-prefix', action='append', default=[],
                    help='additional internal-name prefix requiring decl coverage; repeatable')
    ap.add_argument('--allow-third-party', action='store_true',
                    help='explicitly waive third-party namespaces; they are NOT assumed stable')
    ap.add_argument('--coverage-only', action='store_true',
                    help='explicitly waive NEEDS_MANUAL; still reports MISSING and RENAME')
    ap.add_argument('--out', help='write deterministic JSON report')
    ap.add_argument('--summary', help='write deterministic one-row CSV summary')
    a = ap.parse_args(argv)
    try:
        report = audit(a)
    except ClassRefError as e:
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
    if report['verdict'] not in ('CLASSREFS_OK', 'CLASSREFS_ONLY_OK'):
        detail = '; '.join(report['reasons'])
        if not detail and report['verdict'] == 'NEEDS_MANUAL':
            detail = 'NEEDS_MANUAL refs=' + str(report.get('needs_manual', 0))
        if report.get('error'):
            detail += ' - ' + str(report['error'])
        print('classref: FAIL: ' + detail, file=sys.stderr)
    return EXIT_CODE.get(report['verdict'], 1)


if __name__ == '__main__':
    sys.exit(main())
