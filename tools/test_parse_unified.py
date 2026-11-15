#!/usr/bin/env python3
"""McPort 0.2.3: one strict JVMS 4.3 reference parser across three tools.

Self-contained regression. It reads only repository-owned synthetic lines and
the eight aggregate LinkCheck tickets in data/hotmods/*.json; no game jar,
Mojang mapping or third-party mod binary is embedded or required.
"""
import collections
import importlib.util
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
COUNT = 0


def ok(label, cond):
    global COUNT
    COUNT += 1
    if not cond:
        raise AssertionError('#' + str(COUNT) + ': ' + label)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, str(HERE / filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cap = load('pc_capability', 'capability.py')
bg = load('pc_bridgegen', 'bridgegen.py')
rel = load('pc_relocate', 'relocate.py')

# Historical loose grammars, kept here solely to prove that 0.2.3 removes the
# published 0.2.2 divergence. They are NOT used by any production tool.
OLD_METHOD = re.compile(r'^(.+?)\.([^.(]+)(\(.*\).*)$')
OLD_BG_FIELD = re.compile(r'^(.+?)\.([^.(]+)([A-Za-z\[\$;/].*)$')
OLD_REL_FIELD = re.compile(r'^(.+?)\.([A-Za-z0-9_$]+)(L[^;]*;|\[?[BCDFIJSZ])$')


def old_bg(s):
    h = s.split('  #')[0].strip()
    m = OLD_METHOD.match(h)
    if m:
        return m.group(1), m.group(2), m.group(3), 'M'
    m = OLD_BG_FIELD.match(h)
    return None if m is None else (m.group(1), m.group(2), m.group(3), 'F')


def old_rel(s):
    h = s.split('  #')[0].strip()
    m = OLD_METHOD.match(h)
    if m:
        return m.group(1), m.group(2), m.group(3), False
    m = OLD_REL_FIELD.match(h)
    return None if m is None else (m.group(1), m.group(2), m.group(3), True)


def norm(r):
    """Normalize the three historical tuple shapes to (owner,name,desc,M|F)."""
    if r is None:
        return None
    if r[0] in ('M', 'F'):
        return r[1], r[2], r[3], r[0]
    if r[3] in ('M', 'F'):
        return r[0], r[1], r[2], r[3]
    return r[0], r[1], r[2], 'F' if r[3] else 'M'


def canonical(s):
    return norm(cap.parse_ref(s))


def new_bg(s):
    return norm(bg.parse_ref(s))


def new_rel(s):
    return norm(rel.parse_ref(s))


def strict_splits(s):
    """Count intrinsically ambiguous field texts under the strict grammar."""
    t = s.split('  # ', 1)[0].strip().split('  -> ', 1)[0].strip()
    if '.' not in t or '(' in t:
        return []
    owner, rest = t.split('.', 1)
    out = []
    for k in range(1, len(rest)):
        name, desc = rest[:k], rest[k:]
        if cap.MEMBER_NAME.fullmatch(name) and cap.STRICT_FIELD_DESC.fullmatch(desc):
            out.append((owner, name, desc))
    return out


# 1. External tuple shapes are unchanged for all existing callers / tests.
ok('bridgegen shape method', bg.parse_ref('a/O.m(I)V  # name kept') ==
   ('a/O', 'm', '(I)V', 'M'))
ok('bridgegen shape ctor', bg.parse_ref('a/O.<init>()V  # x') ==
   ('a/O', '<init>', '()V', 'M'))
ok('bridgegen shape primitive field', bg.parse_ref('a/O.fldI  # x') ==
   ('a/O', 'fld', 'I', 'F'))
ok('relocate boolean isf method', rel.parse_ref('a/O.m(I)V') ==
   ('a/O', 'm', '(I)V', False))
ok('relocate boolean isf field', rel.parse_ref('a/O.fldLa/O;') ==
   ('a/O', 'fld', 'La/O;', True))
ok('wrong parse returns None bg', bg.parse_ref('???') is None)
ok('wrong parse returns None rel', rel.parse_ref('???') is None)

SYNTHETIC = [
    ('a/O.m(I)V', ('a/O', 'm', '(I)V', 'M')),
    ('a/O.m([[La/O;IJ)La/T;', ('a/O', 'm', '([[La/O;IJ)La/T;', 'M')),
    ('a/O.<init>()V', ('a/O', '<init>', '()V', 'M')),
    ('a/O.<clinit>()V', ('a/O', '<clinit>', '()V', 'M')),
    ('a/O.fldI', ('a/O', 'fld', 'I', 'F')),
    ('a/O.fldZ', ('a/O', 'fld', 'Z', 'F')),
    ('a/O.fldLa/O;', ('a/O', 'fld', 'La/O;', 'F')),
    ('a/O.fld[La/O;', ('a/O', 'fld', '[La/O;', 'F')),
    ('a/O.fld[[La/O;', ('a/O', 'fld', '[[La/O;', 'F')),
    ('a/O.fld[La/O;  # name kept by a/O, descriptor changed',
     ('a/O', 'fld', '[La/O;', 'F')),
    ('a/O.m(I)V  # name kept by a/O, descriptor changed',
     ('a/O', 'm', '(I)V', 'M')),
    ('a/O.m(I)V  -> mapped elsewhere', ('a/O', 'm', '(I)V', 'M')),
]
for s, want in SYNTHETIC:
    ok('capability canonical ' + s, canonical(s) == want)
    ok('bridgegen canonical ' + s, new_bg(s) == want)
    ok('relocate canonical ' + s, new_rel(s) == want)

REJECT = [
    '???', 'a/O.fld', 'a/O.fld  # no descriptor',
    'a/O.fldLBad[Name;', 'a/O.fldLBad;Junk;',
    'a/O.m(LBad[Name;)V', 'a/O.m(I)LBad[Name;',
    'a/O.(I)V', 'a/O.m(I)VJunk',
]
for s in REJECT:
    ok('all three reject ' + s,
       cap.parse_ref(s) is None and bg.parse_ref(s) is None and rel.parse_ref(s) is None)

# The exact 0.2.1 silent-pass bug: a SIGCHG object-array field was mis-split.
SHADER = ('com/mojang/blaze3d/systems/RenderSystem.'
          'shaderLightDirections[Lorg/joml/Vector3f;  # name kept by '
          'com/mojang/blaze3d/systems/RenderSystem, descriptor changed')
SHADER_KEY = ('com/mojang/blaze3d/systems/RenderSystem',
              'shaderLightDirections', '[Lorg/joml/Vector3f;', 'F')
ok('shader capability strict key', canonical(SHADER) == SHADER_KEY)
ok('shader bridgegen strict key', new_bg(SHADER) == SHADER_KEY)
ok('shader relocate strict key', new_rel(SHADER) == SHADER_KEY)
ok('shader old bridgegen was wrong', norm(old_bg(SHADER)) != SHADER_KEY)
ok('shader old relocate was wrong', norm(old_rel(SHADER)) != SHADER_KEY)
ok('shader old relocate name was shader',
   norm(old_rel(SHADER))[1] == 'shader')
ok('shader old bridgegen desc was semicolon',
   norm(old_bg(SHADER))[2] == ';')
ok('shader strict field descriptor', cap.STRICT_FIELD_DESC.fullmatch('[Lorg/joml/Vector3f;') is not None)
ok('shader type is boolean isf', rel.parse_ref(SHADER)[3] is True)
ok('shader type is F marker', bg.parse_ref(SHADER)[3] == 'F')

# 2. Eight real aggregate tickets: no tool may silently disagree or drop a line.
DATA = REPO / 'data' / 'hotmods'
files = sorted(DATA.glob('*.json'))
ok('eight aggregate tickets', len(files) == 8)
EXPECTED = {
    '1.21.11': {'lines': 1190, 'EXTERNAL': 28, 'RESOLVE': 843,
                'SIGCHG': 99, 'MISSING': 220, 'RENAME': 0,
                'ambiguous': 3, 'unique': 1019, 'external_keys': 27,
                'old_bg': 197, 'old_rel': 1},
    '26.1': {'lines': 1190, 'EXTERNAL': 28, 'RESOLVE': 831,
             'SIGCHG': 74, 'MISSING': 257, 'RENAME': 0,
             'ambiguous': 51, 'unique': 1019, 'external_keys': 27,
             'old_bg': 197, 'old_rel': 1},
}
for version, want in EXPECTED.items():
    vs = [p for p in files if p.name.startswith(version + '__')]
    ok(version + ' four tickets', len(vs) == 4)
    lines, buckets = [], collections.Counter()
    none = collections.Counter()
    diff = collections.Counter()
    old = collections.Counter()
    ambiguous = 0
    unique = set()
    external_keys = set()
    shader_seen = 0
    for p in vs:
        d = json.loads(p.read_text(encoding='utf-8'))['details']
        for bucket in ('EXTERNAL', 'MISSING', 'RENAME', 'RESOLVE', 'SIGCHG'):
            for s in d.get(bucket, []):
                lines.append(s)
                buckets[bucket] += 1
                c, b, r = canonical(s), new_bg(s), new_rel(s)
                if c is None:
                    none['cap'] += 1
                if b is None:
                    none['bg'] += 1
                if r is None:
                    none['rel'] += 1
                if c is None or b is None or r is None:
                    continue
                if b != c:
                    diff['bg'] += 1
                if r != c:
                    diff['rel'] += 1
                ob, orl = norm(old_bg(s)), norm(old_rel(s))
                if ob != c:
                    old['bg'] += 1
                if orl != c:
                    old['rel'] += 1
                if len(strict_splits(s)) > 1:
                    ambiguous += 1
                if bucket == 'EXTERNAL':
                    external_keys.add(c)
                else:
                    unique.add(c)
                if s == SHADER:
                    shader_seen += 1
                    ok(version + ' shader is SIGCHG', bucket == 'SIGCHG')
    ok(version + ' lines', len(lines) == want['lines'])
    for bucket in ('EXTERNAL', 'RESOLVE', 'SIGCHG', 'MISSING', 'RENAME'):
        ok(version + ' bucket ' + bucket, buckets[bucket] == want[bucket])
    ok(version + ' no capability None', none['cap'] == 0)
    ok(version + ' no bridgegen None', none['bg'] == 0)
    ok(version + ' no relocate None', none['rel'] == 0)
    ok(version + ' bridgegen divergence zero', diff['bg'] == 0)
    ok(version + ' relocate divergence zero', diff['rel'] == 0)
    ok(version + ' old bridgegen had divergence', old['bg'] == want['old_bg'])
    ok(version + ' old relocate had divergence', old['rel'] == want['old_rel'])
    ok(version + ' intrinsic ambiguity recorded', ambiguous == want['ambiguous'])
    ok(version + ' unique game refs', len(unique) == want['unique'])
    ok(version + ' external duplicate lines', buckets['EXTERNAL'] == 28)
    ok(version + ' external unique keys', len(external_keys) == want['external_keys'])
    ok(version + ' shader present once', shader_seen == 1)

# 3. Production behavior remains fail-loud: no automatic repair is introduced.
ok('bridgegen auto_fixed contract', bg.SCHEMA == 1)
ok('relocate auto_fixed contract', rel.SCHEMA == 1)
ok('bridgegen no legacy regex import', not hasattr(bg, 'METHOD_RE'))
ok('relocate no legacy regex import', not hasattr(rel, 'METHOD_RE'))
ok('bridgegen keeps CTOR', '<init>' in bg.CTOR and '<clinit>' in bg.CTOR)
ok('relocate keeps CTOR', '<init>' in rel.CTOR and '<clinit>' in rel.CTOR)
ok('strict parser is shared object', bg._cap.parse_ref is not None and rel._cap.parse_ref is not None)

# Monkeypatch the shared module entry points: both tools must delegate to it.
calls = []
orig_bg, orig_rel = bg._cap.parse_ref, rel._cap.parse_ref


def watched(s):
    calls.append(s)
    return orig_bg(s)


def watched_rel(s):
    calls.append(s)
    return orig_rel(s)


bg._cap.parse_ref = watched
rel._cap.parse_ref = watched_rel
try:
    ok('delegated bg tuple', bg.parse_ref('a/O.m(I)V') == ('a/O', 'm', '(I)V', 'M'))
    ok('delegated rel tuple', rel.parse_ref('a/O.fld[La/O;') ==
       ('a/O', 'fld', '[La/O;', True))
    ok('both tools called strict parser', len(calls) == 2)
    ok('delegation received complete text',
       calls == ['a/O.m(I)V', 'a/O.fld[La/O;'])
finally:
    bg._cap.parse_ref = orig_bg
    rel._cap.parse_ref = orig_rel

print('RESULT ALL_OK assertions=' + str(COUNT))
sys.exit(0)
