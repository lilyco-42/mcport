#!/usr/bin/env python3
"""Self-contained regression for tools/relocate.py (synthetic data only)."""
import json, os, subprocess, sys, tempfile

PY = sys.executable or '/usr/bin/python3'
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'relocate.py')
N = [0]


def ok(name, cond, detail=''):
    N[0] += 1
    if not cond:
        print('FAIL ' + name + ' ' + str(detail))
        sys.exit(1)


def decl(path, classes, methods, fields):
    with open(path, 'w', encoding='utf-8') as f:
        for c in sorted(classes):
            f.write('C\t' + c + '\n')
            f.write('S\t' + c + '\tjava/lang/Object\t\n')
        for o, n, d in sorted(methods):
            f.write('M\t' + o + '\t' + n + '\t' + d + '\n')
        for o, n, d in sorted(fields):
            f.write('F\t' + o + '\t' + n + '\t' + d + '\n')


def ticket(path, missing):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'total': len(missing), 'details': {'MISSING': missing}}, f)


def run(spec, out):
    with open(os.path.join(out, 'spec.json'), 'w', encoding='utf-8') as f:
        json.dump(spec, f)
    p = subprocess.run([PY, TOOL, '--spec', os.path.join(out, 'spec.json'),
                        '--out-dir', os.path.join(out, 'out')],
                       capture_output=True, text=True)
    ok('cli_rc', p.returncode == 0, p.stderr)
    with open(os.path.join(out, 'out', 'summary.csv'), encoding='utf-8') as f:
        lines = [x.rstrip('\n').split(',') for x in f]
    return lines, os.path.join(out, 'out', 'v', 'supplement.tsv'), os.path.join(out, 'out', 'v', 'accepted.tsv')


def supplement(p):
    with open(p, encoding='utf-8') as f:
        return [x.rstrip('\n').split('\t') for x in f if x.strip()]


with tempfile.TemporaryDirectory() as t:
    OLD = 'a/old/Widget'
    NEW = 'a/new/Widget'
    INNER_OLD = 'a/old/Widget$Inner'
    INNER_NEW = 'a/new/Widget$Inner'
    d = os.path.join(t, 'decl.tsv')
    tk = os.path.join(t, 'ticket.json')
    decl(d, [NEW, INNER_NEW],
         [(NEW, 'draw', '(I)V'), (NEW, 'make', '()La/new/Widget$Inner;')],
         [(NEW, 'COLOR', 'La/new/Widget$Inner;'), (INNER_NEW, 'value', 'I')])
    ticket(tk, [
        OLD + '.draw(I)V  # owner class gone',
        OLD + '.COLORLa/old/Widget$Inner;  # owner class gone',
        INNER_OLD + '.valueI  # owner class gone',
        OLD + '.gone()V  # owner class gone',
        NEW + '.draw(I)V  # member gone',
    ])
    spec = {'schema': 1, 'targets': [{'version': 'v', 'decl': d, 'tickets': [tk]}]}
    lines, sup, acc = run(spec, t)
    ok('header', lines[0][0] == 'version')
    ok('one_row', len(lines) == 2)
    row = dict(zip(lines[0], lines[1]))
    ok('missing5', row['missing'] == '5', row)
    ok('class_pairs2', row['class_pairs'] == '2', row)
    ok('accepted3', row['accepted'] == '3', row)
    ok('owner_exists1', row['owner_exists'] == '1', row)
    ok('no_exact1', row['no_exact_mapped_decl'] == '1', row)
    s = supplement(sup)
    ok('supplement_two', len(s) == 2, s)
    ok('supplement_sorted', [x[1] for x in s] == sorted(x[1] for x in s), s)
    ok('supplement_form', all(x[0] == 'C' and len(x) == 3 for x in s), s)
    ok('inner_pair', ['C', INNER_OLD, INNER_NEW] in s, s)
    with open(acc, encoding='utf-8') as f:
        a = [x.rstrip('\n').split('\t') for x in f][1:]
    ok('accepted_field_desc_remapped',
       any(x[1] == NEW and x[2] == 'COLOR' and x[4] == 'La/new/Widget$Inner;' for x in a), a)
    ok('accepted_inner', any(x[1] == INNER_NEW and x[2] == 'value' for x in a), a)
    ok('no_constructor', all(x[2] not in ('<init>', '<clinit>') for x in a), a)
    # determinism
    p2 = subprocess.run([PY, TOOL, '--spec', os.path.join(t, 'spec.json'),
                         '--out-dir', os.path.join(t, 'out2')],
                        capture_output=True, text=True)
    ok('rerun_rc', p2.returncode == 0, p2.stderr)
    ok('deterministic', open(sup, 'rb').read() ==
       open(os.path.join(t, 'out2', 'v', 'supplement.tsv'), 'rb').read())

with tempfile.TemporaryDirectory() as t:
    d = os.path.join(t, 'decl.tsv'); tk = os.path.join(t, 'ticket.json')
    decl(d, ['a/new/Other'], [('a/new/Other', 'draw', '(I)V')], [])
    ticket(tk, ['a/old/Widget.draw(I)V  # owner class gone'])
    spec = {'schema': 1, 'targets': [{'version': 'v', 'decl': d, 'tickets': [tk]}]}
    lines, sup, acc = run(spec, t)
    row = dict(zip(lines[0], lines[1]))
    ok('diff_simple_reject_pairs0', row['class_pairs'] == '0', row)
    ok('diff_simple_reject_accepted0', row['accepted'] == '0', row)
    ok('diff_simple_refs1', row['different_simple_refs'] == '1', row)
    ok('diff_simple_no_c_line', supplement(sup) == [], supplement(sup))

with tempfile.TemporaryDirectory() as t:
    d = os.path.join(t, 'decl.tsv'); tk = os.path.join(t, 'ticket.json')
    decl(d, ['a/x/Widget', 'a/y/Widget'],
         [('a/x/Widget', 'draw', '(I)V'), ('a/y/Widget', 'draw', '(I)V')], [])
    ticket(tk, ['a/old/Widget.draw(I)V  # owner class gone'])
    spec = {'schema': 1, 'targets': [{'version': 'v', 'decl': d, 'tickets': [tk]}]}
    lines, sup, acc = run(spec, t)
    row = dict(zip(lines[0], lines[1]))
    ok('ambiguous1', row['ambiguous'] == '1', row)
    ok('ambiguous_pairs0', row['class_pairs'] == '0', row)

with tempfile.TemporaryDirectory() as t:
    d = os.path.join(t, 'decl.tsv'); tk = os.path.join(t, 'ticket.json')
    decl(d, ['a/new/Widget'], [('a/new/Widget', '<init>', '()V')], [])
    ticket(tk, ['a/old/Widget.<init>()V  # owner class gone'])
    spec = {'schema': 1, 'targets': [{'version': 'v', 'decl': d, 'tickets': [tk]}]}
    lines, sup, acc = run(spec, t)
    row = dict(zip(lines[0], lines[1]))
    ok('constructor_rejected', row['constructor'] == '1' and row['accepted'] == '0', row)

print('RESULT ALL_OK ' + str(N[0]))
