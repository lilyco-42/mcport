#!/usr/bin/env python3
"""McPort 0.2.4 / REPORT section 23: structured-reference integrity checker.

Pure standard library, offline. LinkCheck --json renders every member ref as
owner + "." + name + desc with NO delimiter.  For an object-typed field whose
name contains L, that text has several strictly legal JVMS 4.3 splits; the
heuristic longest-name split in capability.parse_ref cannot know which tuple
came from the class file.  LinkCheck --refs-json emits the exact tuples.
This tool cross-checks the two outputs and fails loud when legacy text alone
is ambiguous or cannot be reconciled with the structured refs.

It does NOT run the game, does NOT rewrite bytes and does NOT prove that
RESOLVE means runtime-compatible or semantically equivalent.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CAP = _load('mcport_capability_for_refcheck', 'capability.py')
AUD = _load('mcport_contract_audit_for_refcheck', 'contract_audit.py')
LGC = AUD.LGC

REF_KEYS = ('kind', 'owner', 'name', 'desc', 'status')
ALLOWED_STATUS = ('RESOLVE', 'RENAME', 'SIGCHG', 'MISSING', 'EXTERNAL')
SCHEMA = 1
TOOL = 'mcport.LinkCheck'
DISCLAIMER = 'does NOT mean runtime-compatible; exact refs do NOT prove semantic equivalence'


class RefError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _bad(code, message):
    raise RefError(code, message)


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bytes(path, label):
    try:
        with open(path, 'rb') as fh:
            return fh.read()
    except OSError as e:
        _bad('IO_ERROR', 'cannot read ' + label + ': ' + str(e))


def load_json(path, label):
    raw = read_bytes(path, label)
    try:
        obj = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as e:
        _bad('BAD_JSON', label + ' is not valid UTF-8 JSON: ' + str(e))
    if not isinstance(obj, dict):
        _bad('BAD_JSON', label + ' root is not an object')
    return raw, obj


def read_structured(path):
    raw, obj = load_json(path, 'structured refs')
    if obj.get('schema') != SCHEMA or isinstance(obj.get('schema'), bool):
        _bad('BAD_SCHEMA', 'structured refs schema must be 1')
    if obj.get('tool') != TOOL:
        _bad('BAD_TOOL', 'structured refs tool must be ' + TOOL)
    if not isinstance(obj.get('mod'), str) or not obj['mod']:
        _bad('BAD_MOD', 'structured refs mod must be a non-empty string')
    refs = obj.get('refs')
    if not isinstance(refs, list):
        _bad('BAD_REFS', 'refs must be an array')
    declared = obj.get('ref_count')
    if not isinstance(declared, int) or isinstance(declared, bool) or declared != len(refs):
        _bad('COUNT_MISMATCH', 'ref_count does not equal refs length')
    exact = []
    prev = None
    for i, item in enumerate(refs):
        if not isinstance(item, dict) or tuple(sorted(item.keys())) != tuple(sorted(REF_KEYS)):
            _bad('BAD_REF', 'ref #' + str(i) + ' must have exactly kind/owner/name/desc/status')
        for k in REF_KEYS:
            if not isinstance(item[k], str) or not item[k]:
                _bad('BAD_REF', 'ref #' + str(i) + ' field ' + k + ' must be a non-empty string')
        if item['kind'] not in ('M', 'F'):
            _bad('BAD_KIND', 'ref #' + str(i) + ' has unknown kind')
        if item['status'] not in ALLOWED_STATUS:
            _bad('BAD_STATUS', 'ref #' + str(i) + ' has unknown status')
        if not AUD.valid_owner(item['owner']):
            _bad('BAD_OWNER', 'ref #' + str(i) + ' has invalid internal owner')
        if not AUD.valid_member_name(item['name']):
            _bad('BAD_NAME', 'ref #' + str(i) + ' has invalid member name')
        desc = item['desc']
        if item['kind'] == 'M':
            if not desc.startswith('(') or not AUD.is_method_desc(desc):
                _bad('BAD_DESC', 'ref #' + str(i) + ' is not a strict method descriptor')
        elif desc.startswith('(') or not AUD.is_field_desc(desc):
            _bad('BAD_DESC', 'ref #' + str(i) + ' is not a strict field descriptor')
        key = tuple(item[k] for k in REF_KEYS)
        if prev is not None and key <= prev:
            _bad('NOT_SORTED', 'refs are not deterministic-sorted and unique')
        prev = key
        exact.append(key)
    return raw, exact, obj['mod']


def read_ticket(path):
    raw, obj = load_json(path, 'legacy ticket')
    if not isinstance(obj.get('mod'), str) or not obj['mod']:
        _bad('BAD_TICKET', 'ticket mod must be a non-empty string')
    det = obj.get('details')
    if not isinstance(det, dict) or set(det) != set(ALLOWED_STATUS):
        _bad('BAD_TICKET', 'ticket details must have exactly five status buckets')
    scalars = {'RESOLVE': 'resolve', 'RENAME': 'rename',
               'SIGCHG': 'sigchg', 'MISSING': 'missing'}
    for bucket, scalar in scalars.items():
        arr = det.get(bucket, [])
        if not isinstance(arr, list):
            _bad('BAD_TICKET', 'details ' + bucket + ' is not an array')
        v = obj.get(scalar)
        if not isinstance(v, int) or isinstance(v, bool) or v != len(arr):
            _bad('BAD_TICKET', 'scalar/details mismatch ' + scalar)
    lines = []
    for status in ALLOWED_STATUS:
        arr = det.get(status, [])
        if not isinstance(arr, list):
            _bad('BAD_TICKET', 'details ' + status + ' is not an array')
        for s in arr:
            if not isinstance(s, str):
                _bad('BAD_TICKET', 'details ' + status + ' has non-string entry')
            lines.append((status, s))
    total = obj.get('total')
    if not isinstance(total, int) or isinstance(total, bool) or total != len(lines):
        _bad('BAD_TICKET', 'total/details mismatch')
    return raw, lines, obj.get('mod')


def separate(text):
    """Cut the legacy trailing annotation before using strict descriptor grammar."""
    return text.split('  # ', 1)[0].split('  -> ', 1)[0].strip()


def strict_splits(text):
    """All legal (kind,owner,name,desc) tuples for one legacy detail line."""
    s = separate(text)
    if '.' not in s:
        return []
    owner, rest = s.split('.', 1)
    if not AUD.valid_owner(owner):
        return []
    i = rest.find('(')
    if i >= 0:
        name, desc = rest[:i], rest[i:]
        if AUD.valid_member_name(name) and AUD.is_method_desc(desc):
            return [('M', owner, name, desc)]
        return []
    out = []
    for k in range(1, len(rest)):
        name, desc = rest[:k], rest[k:]
        if AUD.valid_member_name(name) and AUD.is_field_desc(desc):
            out.append(('F', owner, name, desc))
    return out


def render(kind, owner, name, desc):
    return owner + '.' + name + desc


def reconcile(exact, lines):
    """Index-structured multiset matching; never silently pick a heuristic winner."""
    by_text = {}
    for kind, owner, name, desc, status in exact:
        by_text.setdefault((status, render(kind, owner, name, desc)), []).append((owner, name, desc))
    bad_lines = []
    ambiguous_lines = []
    result = Counter()
    for status, text in lines:
        base = separate(text)
        pool = by_text.get((status, base))
        if not pool:
            bad_lines.append((status, text))
            continue
        splits = strict_splits(text)
        if not splits:
            bad_lines.append((status, text))
            continue
        tuples = [(owner, name, desc) for _, owner, name, desc in splits]
        if len(tuples) > 1:
            ambiguous_lines.append((status, text, len(tuples)))
        # Iterate the deterministic split order, never hash-set order: PYTHONHASHSEED
        # must not change which exact tuple a legacy line consumes.
        candidates = [t for t in tuples if t in pool]
        if not candidates:
            bad_lines.append((status, text))
            continue
        chosen = candidates[0]
        pool.remove(chosen)
        result[status] += 1
        if len(candidates) > 1:
            result['AMBIGUOUS_RESOLVED'] += 1
        heuristic = CAP.parse_ref(text)
        if heuristic is not None and tuple(heuristic[1:]) != chosen:
            result['HEURISTIC_DIVERGED'] += 1
    leftover = sum(len(v) for v in by_text.values())
    if leftover or bad_lines:
        _bad('TICKET_REF_MISMATCH',
             'unmatched structured refs=' + str(leftover) + ' bad legacy lines=' + str(len(bad_lines)))
    result['TOTAL'] = len(lines)
    result['AMBIGUOUS_LINES'] = len(ambiguous_lines)
    return result, ambiguous_lines


def report_payload(struct_raw, ticket_raw, exact, lines, result, ambiguous):
    collisions = sorted(set((status, text, n) for status, text, n in ambiguous))
    return {
        'schema': SCHEMA,
        'tool': 'mcport.refcheck',
        'structured_sha256': sha256_bytes(struct_raw),
        'ticket_sha256': sha256_bytes(ticket_raw),
        'structured_ref_count': len(exact),
        'legacy_line_count': len(lines),
        'status_counts': {k: result[k] for k in ALLOWED_STATUS},
        'ambiguous_legacy_lines': result['AMBIGUOUS_LINES'],
        'ambiguous_resolved_by_structured': result['AMBIGUOUS_RESOLVED'],
        'heuristic_diverged_lines': result['HEURISTIC_DIVERGED'],
        'ambiguous_collisions': [
            {'status': a, 'text': b, 'splits': c} for a, b, c in collisions
        ],
        'verdict': 'STRUCTURED_REFS_OK',
        'disclaimer': DISCLAIMER,
    }


def stdout_line(p):
    return (p['verdict'] + ' schema=' + str(p['schema']) +
            ' structured=' + str(p['structured_ref_count']) +
            ' legacy=' + str(p['legacy_line_count']) +
            ' ambiguous=' + str(p['ambiguous_legacy_lines']) +
            ' resolved=' + str(p['ambiguous_resolved_by_structured']) +
            ' diverged=' + str(p['heuristic_diverged_lines']) +
            ' ' + DISCLAIMER)


def main(argv=None):
    ap = argparse.ArgumentParser(description='McPort 0.2.4 structured-reference integrity checker')
    ap.add_argument('--refs-json', required=True, help='LinkCheck --refs-json output')
    ap.add_argument('--ticket', required=True, help='LinkCheck --json legacy ticket')
    ap.add_argument('--golden', help='optional byte-identical legacy ticket baseline')
    ap.add_argument('--out', help='write JSON report even on failure')
    args = ap.parse_args(argv)
    payload = None
    try:
        struct_raw, exact, struct_mod = read_structured(args.refs_json)
        ticket_raw, lines, ticket_mod = read_ticket(args.ticket)
        if struct_mod != ticket_mod:
            _bad('MOD_MISMATCH', 'structured refs and legacy ticket describe different mod paths')
        golden_match = None
        if args.golden:
            golden_match = read_bytes(args.golden, 'golden ticket') == ticket_raw
            if not golden_match:
                _bad('GOLDEN_MISMATCH', 'legacy --json bytes differ from golden baseline')
        result, ambiguous = reconcile(exact, lines)
        payload = report_payload(struct_raw, ticket_raw, exact, lines, result, ambiguous)
        if golden_match is not None:
            payload['golden_bytes_match'] = golden_match
        if args.out:
            with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
                json.dump(payload, fh, ensure_ascii=False, sort_keys=True, indent=2)
                fh.write('\n')
        print(stdout_line(payload))
        return 0
    except RefError as e:
        payload = {'schema': SCHEMA, 'tool': 'mcport.refcheck',
                   'verdict': 'UNSUPPORTED', 'reason': e.code,
                   'message': str(e), 'disclaimer': DISCLAIMER}
        if args.out:
            with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
                json.dump(payload, fh, ensure_ascii=False, sort_keys=True, indent=2)
                fh.write('\n')
        print('UNSUPPORTED ' + e.code + ' ' + str(e), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
