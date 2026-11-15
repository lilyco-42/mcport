#!/usr/bin/env python3
"""McPort 0.2.4 / REPORT section 23: self-contained regression for tools/refcheck.py.

Pure standard library and offline.  All failing inputs are synthesized in
tempfile; the only repository data read are the byte-exact synthetic golden
ticket and the eight already-distributed aggregate tickets.  No Minecraft jar,
Mojang mapping, third-party mod binary or network access is required.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
DATA = REPO / 'data'
TOOLS = REPO / 'tools'
RF = TOOLS / 'refcheck.py'
GOLDEN = DATA / 'refcheck-legacy-golden.json'
PY = sys.executable if sys.executable else '/usr/bin/python3'
ENV = dict(os.environ)
ENV['LANG'] = 'C.utf8'
ENV['LC_ALL'] = 'C.utf8'

_spec = importlib.util.spec_from_file_location('test_refcheck_module', RF)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

COUNT = 0


def ok(label, cond):
    global COUNT
    COUNT += 1
    if not cond:
        raise AssertionError('#' + str(COUNT) + ': ' + label)


def wjson(path, obj):
    with open(str(path), 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(',', ':'))


def deep(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False))


def struct_obj(mod, refs):
    refs = sorted(refs)
    return {
        'schema': 1,
        'tool': 'mcport.LinkCheck',
        'mod': mod,
        'ref_count': len(refs),
        'refs': [dict(zip(m.REF_KEYS, r)) for r in refs],
    }


def ticket_obj(mod, lines_by_status):
    n = {s: len(lines_by_status.get(s, [])) for s in m.ALLOWED_STATUS}
    return {
        'mod': mod,
        'total': sum(n.values()),
        'resolve': n['RESOLVE'],
        'rename': n['RENAME'],
        'sigchg': n['SIGCHG'],
        'missing': n['MISSING'],
        'autoFixCeiling': 100.0,
        'details': {s: list(lines_by_status.get(s, [])) for s in m.ALLOWED_STATUS},
    }


def legacy_line(r):
    kind, owner, name, desc, status = r
    base = m.render(kind, owner, name, desc)
    suffix = {
        'RESOLVE': '',
        'RENAME': '  -> newerName',
        'SIGCHG': '  # name kept by net/minecraft/Api, descriptor changed',
        'MISSING': '  # member gone',
        'EXTERNAL': '  # external library, assumed stable',
    }[status]
    return base + suffix


def ticket_from_refs(mod, refs):
    buckets = {s: [] for s in m.ALLOWED_STATUS}
    for r in refs:
        buckets[r[4]].append(legacy_line(r))
    return ticket_obj(mod, buckets)


def invoke(struct=None, ticket=None, struct_raw=None, ticket_raw=None,
           golden_path=None, golden_bytes=None):
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        sfile = d / 'refs.json'
        tfile = d / 'ticket.json'
        ofile = d / 'report.json'
        if struct_raw is not None:
            sfile.write_bytes(struct_raw)
        else:
            wjson(sfile, struct)
        if ticket_raw is not None:
            tfile.write_bytes(ticket_raw)
        else:
            wjson(tfile, ticket)
        args = [PY, str(RF), '--refs-json', str(sfile), '--ticket', str(tfile), '--out', str(ofile)]
        if golden_path is not None:
            args += ['--golden', str(golden_path)]
        elif golden_bytes is not None:
            gf = d / 'golden.json'
            gf.write_bytes(golden_bytes)
            args += ['--golden', str(gf)]
        p = subprocess.run(args, cwd=str(REPO), env=ENV, capture_output=True, text=True)
        rep = json.loads(ofile.read_text(encoding='utf-8')) if ofile.exists() else None
        return p, rep


def expect_ok(label, **kw):
    p, rep = invoke(**kw)
    ok(label + '_rc0', p.returncode == 0)
    ok(label + '_report_present', rep is not None)
    ok(label + '_verdict', rep is not None and rep.get('verdict') == 'STRUCTURED_REFS_OK')
    ok(label + '_stdout', p.stdout.startswith('STRUCTURED_REFS_OK schema='))
    ok(label + '_disclaimer', m.DISCLAIMER in p.stdout)
    return p, rep


def expect_fail(label, code, **kw):
    p, rep = invoke(**kw)
    ok(label + '_rc1', p.returncode == 1)
    ok(label + '_reason', rep is not None and rep.get('reason') == code)
    ok(label + '_stderr', ('UNSUPPORTED ' + code) in p.stderr)
    return p, rep


MOD = 'build/refmod.jar'
COLLIDE_TEXT = 'net/minecraft/Api.BLENDLnet/minecraft/Thing;'
COLLIDE = [
    ('F', 'net/minecraft/Api', 'B', 'LENDLnet/minecraft/Thing;', 'RESOLVE'),
    ('F', 'net/minecraft/Api', 'BLEND', 'Lnet/minecraft/Thing;', 'RESOLVE'),
]
MORE = [
    ('F', 'net/minecraft/Api', 'B', 'LENDLnet/minecraft/Thing;', 'RESOLVE'),
    ('F', 'net/minecraft/Api', 'BLEND', 'Lnet/minecraft/Thing;', 'RESOLVE'),
    ('M', 'com/mojang/serialization/Codec', 'fieldOf',
     '(Ljava/lang/String;)Lcom/mojang/serialization/MapCodec;', 'EXTERNAL'),
    ('M', 'net/minecraft/Api', 'go', '(I)Lnet/minecraft/Thing;', 'SIGCHG'),
    ('M', 'net/minecraft/Api', 'old', '()V', 'RENAME'),
    ('M', 'net/minecraft/Api', 'vanished', '()V', 'MISSING'),
]
gbytes = GOLDEN.read_bytes()
gobj = json.loads(gbytes.decode('utf-8'))
collide_struct = struct_obj(MOD, COLLIDE)
collide_ticket = ticket_from_refs(MOD, COLLIDE)

# 1. Public contract and byte-exact golden fixture.
ok('schema_one', m.SCHEMA == 1)
ok('tool_name', m.TOOL == 'mcport.LinkCheck')
ok('five_ref_keys', m.REF_KEYS == ('kind', 'owner', 'name', 'desc', 'status'))
ok('five_statuses', m.ALLOWED_STATUS == ('RESOLVE', 'RENAME', 'SIGCHG', 'MISSING', 'EXTERNAL'))
ok('disclaimer_exact', m.DISCLAIMER == 'does NOT mean runtime-compatible; exact refs do NOT prove semantic equivalence')
ok('golden_size_274', len(gbytes) == 274)
ok('golden_sha', hashlib.sha256(gbytes).hexdigest() == m.sha256_bytes(gbytes))
ok('golden_mod', gobj['mod'] == MOD)
ok('golden_total2', gobj['total'] == 2)
ok('golden_two_identical_lines', gobj['details']['RESOLVE'] == [COLLIDE_TEXT, COLLIDE_TEXT])
with tempfile.TemporaryDirectory() as td:
    decl = (REPO / 'demo/gate/refcheck-decl.tsv').read_text(encoding='utf-8').splitlines()
    ok('decl_two_lines', len(decl) == 2)
    ok('decl_first', decl[0] == 'F\tnet/minecraft/Api\tBLEND\tLnet/minecraft/Thing;')
    ok('decl_second', decl[1] == 'F\tnet/minecraft/Api\tB\tLENDLnet/minecraft/Thing;')
    ok('decl_unchanged', (REPO / 'demo/gate/refcheck-decl.tsv').read_bytes() == '\n'.join(decl).encode('utf-8') + b'\n')

# 2. Strict grammar and the actual collision.
ok('separate_resolve', m.separate(COLLIDE_TEXT) == COLLIDE_TEXT)
ok('separate_comment', m.separate('net/minecraft/Api.go()V  # member gone') == 'net/minecraft/Api.go()V')
ok('separate_rename', m.separate('net/minecraft/Api.old()V  -> newerName') == 'net/minecraft/Api.old()V')
ok('collision_two_splits', m.strict_splits(COLLIDE_TEXT) == [
    ('F', 'net/minecraft/Api', 'B', 'LENDLnet/minecraft/Thing;'),
    ('F', 'net/minecraft/Api', 'BLEND', 'Lnet/minecraft/Thing;'),
])
ok('capability_heuristic_picks_longest', m.CAP.parse_ref(COLLIDE_TEXT) ==
   ('F', 'net/minecraft/Api', 'BLEND', 'Lnet/minecraft/Thing;'))
ok('method_split_with_comment', m.strict_splits('net/minecraft/Api.go(I)Lnet/minecraft/Thing;  # member gone') ==
   [('M', 'net/minecraft/Api', 'go', '(I)Lnet/minecraft/Thing;')])
ok('method_ctor_split', m.strict_splits('net/minecraft/Api.<init>()V') ==
   [('M', 'net/minecraft/Api', '<init>', '()V')])
ok('bad_field_desc_no_splits', m.strict_splits('net/minecraft/Api.BADLBad[Name;') == [])
ok('no_dot_no_splits', m.strict_splits('nonsense') == [])
ok('bad_owner_no_splits', m.strict_splits('net//minecraft/Api.fI') == [])
ok('render_exact', m.render('F', 'net/minecraft/Api', 'BLEND', 'Lnet/minecraft/Thing;') == COLLIDE_TEXT)

with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    sf = d / 'refs.json'
    wjson(sf, collide_struct)
    raw, exact, mod = m.read_structured(str(sf))
    ok('read_structured_raw_bytes', raw == sf.read_bytes())
    ok('read_structured_exact_tuples', exact == sorted(COLLIDE))
    ok('read_structured_mod', mod == MOD)
    tf = d / 'ticket.json'
    tf.write_bytes(gbytes)
    traw, lines, tmod = m.read_ticket(str(tf))
    ok('read_ticket_raw_bytes', traw == gbytes)
    ok('read_ticket_lines', lines == [('RESOLVE', COLLIDE_TEXT), ('RESOLVE', COLLIDE_TEXT)])
    ok('read_ticket_mod', tmod == MOD)
    missing = d / 'missing.json'
    try:
        m.read_bytes(str(missing), 'missing')
        ok('read_bytes_missing_fail_loud', False)
    except m.RefError as e:
        ok('read_bytes_missing_fail_loud', e.code == 'IO_ERROR')

# 3. Full CLI success: byte-identical legacy output and structured disambiguation.
p, rep = expect_ok('golden_success', struct=collide_struct, ticket_raw=gbytes, golden_path=GOLDEN)
ok('golden_stdout_counts', 'structured=2 legacy=2 ambiguous=2 resolved=1 diverged=1' in p.stdout)
ok('golden_bytes_match', rep.get('golden_bytes_match') is True)
ok('golden_status_counts', rep.get('status_counts')['RESOLVE'] == 2)
ok('golden_structured_count', rep.get('structured_ref_count') == 2)
ok('golden_legacy_count', rep.get('legacy_line_count') == 2)
ok('golden_ambiguous_lines', rep.get('ambiguous_legacy_lines') == 2)
ok('golden_resolved_by_structured', rep.get('ambiguous_resolved_by_structured') == 1)
ok('golden_heuristic_diverged', rep.get('heuristic_diverged_lines') == 1)
ok('golden_collision_recorded', rep.get('ambiguous_collisions') == [
    {'status': 'RESOLVE', 'text': COLLIDE_TEXT, 'splits': 2}])
ok('golden_stderr_empty', p.stderr == '')

p, rep = expect_ok('no_golden_success', struct=collide_struct, ticket=collide_ticket)
ok('no_golden_key_absent', 'golden_bytes_match' not in rep)
ok('no_golden_disambiguated', rep.get('ambiguous_resolved_by_structured') == 1)

weird_mod = 'C:\\weird "mod".jar'
weird_struct = struct_obj(weird_mod, COLLIDE)
weird_ticket = deep(gobj)
weird_ticket['mod'] = weird_mod
p, rep = expect_ok('escaped_mod_success', struct=weird_struct, ticket=weird_ticket)
ok('escaped_mod_stdout', 'structured=2 legacy=2' in p.stdout)

p, rep = expect_ok('multi_status_success', struct=struct_obj(MOD, MORE), ticket=ticket_from_refs(MOD, MORE))
ok('multi_status_counts', rep.get('status_counts') == {
    'RESOLVE': 2, 'RENAME': 1, 'SIGCHG': 1, 'MISSING': 1, 'EXTERNAL': 1})
ok('multi_status_structured6', rep.get('structured_ref_count') == 6)
ok('multi_status_legacy6', rep.get('legacy_line_count') == 6)
ok('multi_status_collision', rep.get('ambiguous_legacy_lines') == 2)
ok('multi_status_resolved', rep.get('ambiguous_resolved_by_structured') == 1)
ok('multi_status_diverged', rep.get('heuristic_diverged_lines') == 1)

p, rep = expect_ok('empty_success', struct=struct_obj(MOD, []), ticket=ticket_obj(MOD, {}))
ok('empty_structured0', rep.get('structured_ref_count') == 0)
ok('empty_legacy0', rep.get('legacy_line_count') == 0)
ok('empty_verdict_not_empty_variant', rep.get('verdict') == 'STRUCTURED_REFS_OK')
ok('empty_stdout_diverged0', 'diverged=0' in p.stdout)

# 4. Structured input fail-loud cases.
def mut_struct(pos, key, value):
    obj = deep(collide_struct)
    obj['refs'][pos][key] = value
    return obj


def mut_top(key, value):
    obj = deep(collide_struct)
    obj[key] = value
    return obj


for label, code, kw in [
    ('bad_schema_2', 'BAD_SCHEMA', {'struct': mut_top('schema', 2), 'ticket_raw': gbytes}),
    ('bad_schema_bool', 'BAD_SCHEMA', {'struct': mut_top('schema', True), 'ticket_raw': gbytes}),
    ('bad_tool', 'BAD_TOOL', {'struct': mut_top('tool', 'evil'), 'ticket_raw': gbytes}),
    ('bad_mod_empty', 'BAD_MOD', {'struct': mut_top('mod', ''), 'ticket_raw': gbytes}),
    ('bad_refs_null', 'BAD_REFS', {'struct': mut_top('refs', None), 'ticket_raw': gbytes}),
    ('count_mismatch', 'COUNT_MISMATCH', {'struct': mut_top('ref_count', 3), 'ticket_raw': gbytes}),
    ('bad_kind', 'BAD_KIND', {'struct': mut_struct(0, 'kind', 'X'), 'ticket_raw': gbytes}),
    ('bad_status', 'BAD_STATUS', {'struct': mut_struct(0, 'status', 'MISSNG'), 'ticket_raw': gbytes}),
    ('bad_owner', 'BAD_OWNER', {'struct': mut_struct(0, 'owner', 'net//minecraft/Api'), 'ticket_raw': gbytes}),
    ('bad_name', 'BAD_NAME', {'struct': mut_struct(0, 'name', '1bad'), 'ticket_raw': gbytes}),
    ('bad_field_desc', 'BAD_DESC', {'struct': mut_struct(0, 'desc', 'LBad[Name;'), 'ticket_raw': gbytes}),
    ('bad_method_desc_kind', 'BAD_DESC', {'struct': mut_struct(0, 'kind', 'M'), 'ticket_raw': gbytes}),
    ('bad_json_struct', 'BAD_JSON', {'struct_raw': b'not json', 'ticket_raw': gbytes}),
    ('bad_utf8_struct', 'BAD_JSON', {'struct_raw': b'\xff', 'ticket_raw': gbytes}),
    ('bad_json_root_struct', 'BAD_JSON', {'struct_raw': b'[]', 'ticket_raw': gbytes}),
]:
    expect_fail(label, code, **kw)

extra = deep(collide_struct)
extra['refs'][0]['extra'] = 'x'
expect_fail('extra_ref_key', 'BAD_REF', struct=extra, ticket_raw=gbytes)
missing_key = deep(collide_struct)
del missing_key['refs'][0]['desc']
expect_fail('missing_ref_key', 'BAD_REF', struct=missing_key, ticket_raw=gbytes)
unsorted = deep(collide_struct)
unsorted['refs'][0], unsorted['refs'][1] = unsorted['refs'][1], unsorted['refs'][0]
expect_fail('not_sorted', 'NOT_SORTED', struct=unsorted, ticket_raw=gbytes)

# 5. Legacy ticket shape, provenance, and reconciliation fail-loud cases.
def mut_ticket(fn):
    obj = deep(gobj)
    fn(obj)
    return obj


for label, fn in [
    ('ticket_bad_mod_empty', lambda o: o.update({'mod': ''})),
    ('ticket_bad_mod_none', lambda o: o.update({'mod': None})),
    ('ticket_missing_mod', lambda o: o.pop('mod')),
    ('ticket_details_not_dict', lambda o: o.update({'details': []})),
    ('ticket_missing_bucket', lambda o: o['details'].pop('EXTERNAL')),
    ('ticket_extra_bucket', lambda o: o['details'].update({'EXTRA': []})),
    ('ticket_nonlist_bucket', lambda o: o['details'].update({'RENAME': 'x'})),
    ('ticket_nonstring_entry', lambda o: o['details'].update({'RESOLVE': [123, COLLIDE_TEXT]})),
    ('ticket_scalar_mismatch', lambda o: o.update({'resolve': 3})),
    ('ticket_total_mismatch', lambda o: o.update({'total': 3})),
]:
    expect_fail(label, 'BAD_TICKET', struct=collide_struct, ticket=mut_ticket(fn))

expect_fail('bad_json_ticket', 'BAD_JSON', struct=collide_struct, ticket_raw=b'not json')
expect_fail('bad_utf8_ticket', 'BAD_JSON', struct=collide_struct, ticket_raw=b'\xff')
expect_fail('bad_json_root_ticket', 'BAD_JSON', struct=collide_struct, ticket_raw=b'[]')
expect_fail('mod_mismatch', 'MOD_MISMATCH', struct=struct_obj('other.jar', COLLIDE), ticket_raw=gbytes)
expect_fail('golden_mismatch', 'GOLDEN_MISMATCH', struct=collide_struct, ticket_raw=gbytes,
            golden_bytes=gbytes + b'\n')
expect_fail('leftover_structured_ref', 'TICKET_REF_MISMATCH', struct=collide_struct,
            ticket=mut_ticket(lambda o: (o['details'].update({'RESOLVE': [COLLIDE_TEXT]}),
                                         o.update({'resolve': 1, 'total': 1}))))
bad_line_ticket = deep(gobj)
bad_line_ticket['details']['RESOLVE'][0] = 'net/minecraft/Api.BADLnet/minecraft/Thing;'
expect_fail('bad_legacy_line', 'TICKET_REF_MISMATCH', struct=collide_struct, ticket=bad_line_ticket)
unresolved = struct_obj(MOD, [COLLIDE[0]])
expect_fail('ambiguous_not_resolved', 'TICKET_REF_MISMATCH', struct=unresolved, ticket=collide_ticket)

with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    t = d / 'ticket.json'
    t.write_bytes(gbytes)
    out = d / 'report.json'
    p = subprocess.run([PY, str(RF), '--refs-json', str(d / 'nope.json'),
                        '--ticket', str(t), '--out', str(out)],
                       cwd=str(REPO), env=ENV, capture_output=True, text=True)
    rep = json.loads(out.read_text(encoding='utf-8'))
    ok('io_error_rc1', p.returncode == 1)
    ok('io_error_reason', rep.get('reason') == 'IO_ERROR')
    ok('io_error_stderr', 'UNSUPPORTED IO_ERROR' in p.stderr)

# 6. Eight real aggregate tickets stay byte-identical and retain their recorded ambiguity.
real = sorted((DATA / 'hotmods').glob('*.json'))
ok('eight_real_tickets', len(real) == 8)
for path in real:
    before = path.read_bytes()
    _, lines, _ = m.read_ticket(str(path))
    ok('real_ticket_read_' + path.name, len(lines) == json.loads(before.decode('utf-8'))['total'])
    ok('real_ticket_unchanged_' + path.name, path.read_bytes() == before)


def ambiguous_count(prefix):
    n = 0
    for path in sorted((DATA / 'hotmods').glob(prefix + '__*.json')):
        _, lines, _ = m.read_ticket(str(path))
        for _, text in lines:
            if len(m.strict_splits(text)) > 1:
                n += 1
    return n


ok('legacy_ambiguity_1_21_11_is_3', ambiguous_count('1.21.11') == 3)
ok('legacy_ambiguity_26_1_is_51', ambiguous_count('26.1') == 51)

# 7. Structured refs, not heuristic text parsing, are the authority for these two tuples.
result, ambiguous = m.reconcile(sorted(COLLIDE), [('RESOLVE', COLLIDE_TEXT), ('RESOLVE', COLLIDE_TEXT)])
ok('reconcile_total2', result['TOTAL'] == 2)
ok('reconcile_resolve2', result['RESOLVE'] == 2)
ok('reconcile_ambiguous2', result['AMBIGUOUS_LINES'] == 2)
ok('reconcile_structured_resolved1', result['AMBIGUOUS_RESOLVED'] == 1)
ok('reconcile_heuristic_diverged1', result['HEURISTIC_DIVERGED'] == 1)
ok('reconcile_collision_record', ambiguous == [('RESOLVE', COLLIDE_TEXT, 2),
                                               ('RESOLVE', COLLIDE_TEXT, 2)])

print('RESULT ALL_OK assertions=' + str(COUNT))
