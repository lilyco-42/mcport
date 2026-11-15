#!/usr/bin/env python3
"""Strict class-relocation C-line supplement generator for McPort tickets.

Reads caller-supplied LinkCheck JSON tickets and a target declaration TSV.
Never contains Mojang bytes, mappings or third-party mod bytecode; all paths
are runtime inputs. Output supplement.tsv contains only class-pair C lines.
Only exact, unique, same-simple-name class moves with a directly declared
member after descriptor remapping are accepted; everything else fails loud.
"""
import argparse, collections, csv, importlib.util, json, os

SCHEMA = 1
# REPORT section 22: delegate all reference parsing to one strict grammar.
HERE = os.path.dirname(os.path.abspath(__file__))
_cap_spec = importlib.util.spec_from_file_location(
    'mcport_capability_for_relocate', os.path.join(HERE, 'capability.py'))
_cap = importlib.util.module_from_spec(_cap_spec)
_cap_spec.loader.exec_module(_cap)
CTOR = ('<init>', '<clinit>')


def parse_ref(s):
    """Return (owner, name, desc, is_field) using the shared strict parser.

    REPORT section 22: the fourth element stays a boolean (not M|F) so all
    relocation callers and their direct_f/direct_m lookups are unchanged.
    """
    p = _cap.parse_ref(s)
    if p is None:
        return None
    kind, owner, name, desc = p
    return owner, name, desc, kind == 'F'


def simple(owner):
    return owner.rsplit('/', 1)[-1]


def load_decl(path):
    classes = set()
    by_m = collections.defaultdict(set)
    by_f = collections.defaultdict(set)
    direct_m = set()
    direct_f = set()
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            q = line.rstrip('\n').split('\t')
            if not q or q[0].startswith('#'):
                continue
            if q[0] in ('C', 'S') and len(q) >= 2:
                classes.add(q[1])
            elif q[0] == 'M' and len(q) >= 4:
                classes.add(q[1])
                by_m[(q[2], q[3])].add(q[1])
                direct_m.add((q[1], q[2], q[3]))
            elif q[0] == 'F' and len(q) >= 4:
                classes.add(q[1])
                by_f[(q[2], q[3])].add(q[1])
                direct_f.add((q[1], q[2], q[3]))
    return {'classes': classes, 'by_m': by_m, 'by_f': by_f,
            'direct_m': direct_m, 'direct_f': direct_f}


def map_desc(desc, cmap):
    d = desc
    for _ in range(5):
        z = d
        for a, b in cmap.items():
            z = z.replace('L' + a + ';', 'L' + b + ';')
        if z == d:
            return z
        d = z
    return d


def build(spec, out_dir):
    if spec.get('schema') != SCHEMA:
        raise ValueError('unsupported spec schema')
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for t in spec['targets']:
        decl = load_decl(t['decl'])
        refs = []
        bad = 0
        for fn in t['tickets']:
            with open(fn, encoding='utf-8') as f:
                d = json.load(f)
            for s in d.get('details', {}).get('MISSING', []):
                p = parse_ref(s)
                if p:
                    refs.append((fn, p))
                else:
                    bad += 1
        votes = collections.defaultdict(set)
        refs_with_diff_simple = set()
        for fn, (owner, name, desc, isf) in refs:
            if owner in decl['classes']:
                continue
            tab = decl['by_f'] if isf else decl['by_m']
            for c in tab.get((name, desc), set()):
                if simple(owner) == simple(c):
                    votes[(owner, c)].add((name, desc, isf))
                else:
                    refs_with_diff_simple.add((fn, owner, name, desc, isf))
        cand = collections.defaultdict(set)
        for (o, n), v in votes.items():
            if n in decl['classes']:
                cand[o].add(n)
        cmap = {o: next(iter(sorted(ns))) for o, ns in cand.items() if len(ns) == 1}
        ambiguous = sum(1 for ns in cand.values() if len(ns) != 1)
        accepted = []
        rejected = collections.Counter()
        for fn, (owner, name, desc, isf) in refs:
            if owner in decl['classes']:
                rejected['owner_exists'] += 1
                continue
            if owner not in cmap:
                rejected['no_strict_c_line'] += 1
                continue
            if not isf and name in CTOR:
                rejected['constructor'] += 1
                continue
            new = cmap[owner]
            nd = map_desc(desc, cmap)
            direct = decl['direct_f'] if isf else decl['direct_m']
            if (new, name, nd) in direct:
                accepted.append((owner, new, name, desc, nd,
                                 'F' if isf else 'M', os.path.basename(fn)))
                rejected['accepted'] += 1
            else:
                rejected['no_exact_mapped_decl'] += 1
        vdir = os.path.join(out_dir, t['version'])
        os.makedirs(vdir, exist_ok=True)
        with open(os.path.join(vdir, 'supplement.tsv'), 'w', encoding='utf-8') as f:
            for o in sorted(cmap):
                f.write('C\t' + o + '\t' + cmap[o] + '\n')
        with open(os.path.join(vdir, 'accepted.tsv'), 'w', encoding='utf-8') as f:
            f.write('oldOwner\tnewOwner\tname\tdesc\tmappedDesc\tkind\tticket\n')
            for a in sorted(accepted):
                f.write('\t'.join(a) + '\n')
        stats = {
            'version': t['version'], 'tickets': len(t['tickets']),
            'missing': len(refs), 'parse_fail': bad,
            'class_pairs': len(cmap), 'ambiguous': ambiguous,
            'different_simple_refs': len(refs_with_diff_simple),
            'accepted': len(accepted),
            'rejected': {k: v for k, v in rejected.items() if k != 'accepted'},
        }
        with open(os.path.join(vdir, 'stats.json'), 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2, sort_keys=True)
        rows.append(stats)
    with open(os.path.join(out_dir, 'summary.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['version', 'tickets', 'missing', 'parse_fail', 'class_pairs',
                    'ambiguous', 'different_simple_refs', 'accepted',
                    'owner_exists', 'no_strict_c_line', 'no_exact_mapped_decl', 'constructor'])
        for s in rows:
            r = s['rejected']
            w.writerow([s['version'], s['tickets'], s['missing'], s['parse_fail'],
                        s['class_pairs'], s['ambiguous'], s['different_simple_refs'],
                        s['accepted'], r.get('owner_exists', 0),
                        r.get('no_strict_c_line', 0),
                        r.get('no_exact_mapped_decl', 0), r.get('constructor', 0)])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spec', required=True)
    ap.add_argument('--out-dir', required=True)
    a = ap.parse_args()
    with open(a.spec, encoding='utf-8') as f:
        spec = json.load(f)
    rows = build(spec, a.out_dir)
    print('RESULT targets=' + str(len(rows)) +
          ' accepted=' + str(sum(r['accepted'] for r in rows)) +
          ' class_pairs=' + str(sum(r['class_pairs'] for r in rows)))


if __name__ == '__main__':
    main()
