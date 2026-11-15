#!/usr/bin/env python3
"""McPort 0.2.2 / REPORT section 21: self-contained regression for tools/contract_audit.py.

Pure standard library. All tickets, contracts, class files and jars are synthesized in
tempfile. The optional real-ticket integration only reads the already-distributed
data/hotmods/26.1__*.json aggregate numbers: no Mojang bytes, no mod binaries, no network.
"""
import csv
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / 'tools'
_spec = importlib.util.spec_from_file_location('contract_audit', TOOLS / 'contract_audit.py')
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
LG = m.LGC
PY = sys.executable if sys.executable else 'python3'
ENV = dict(os.environ)
ENV['LANG'] = 'C.utf8'
ENV['LC_ALL'] = 'C.utf8'

COUNT = 0
TAB = chr(9)


def ok(cond, msg):
    global COUNT
    if not cond:
        raise AssertionError('assert #' + str(COUNT + 1) + ': ' + msg)
    COUNT += 1


def utf8(s):
    b = s.encode('utf-8')
    return b'\x01' + struct.pack('>H', len(b)) + b


def mkclass(refs):
    """refs: list of (owner, name, desc, tag) with tag in (9, 10, 11)."""
    ents = [None]
    def add(e):
        ents.append(e)
        return len(ents) - 1
    i_this_name = add(utf8('t/Audit'))
    i_this = add(b'\x07' + struct.pack('>H', i_this_name))
    i_obj_name = add(utf8('java/lang/Object'))
    i_obj = add(b'\x07' + struct.pack('>H', i_obj_name))
    for owner, name, desc, tag in refs:
        io = add(utf8(owner))
        ic = add(b'\x07' + struct.pack('>H', io))
        inm = add(utf8(name))
        ids = add(utf8(desc))
        inat = add(b'\x0c' + struct.pack('>HH', inm, ids))
        add(bytes([tag]) + struct.pack('>HH', ic, inat))
    count = len(ents)
    body = struct.pack('>HHHHHHH', 0x0021, i_this, i_obj, 0, 0, 0, 0)
    head = b'\xca\xfe\xba\xbe' + b'\x00\x00' + b'\x00\x3d' + struct.pack('>H', count)
    return head + b''.join(ents[1:]) + body


def mkjar(path, entries):
    with zipfile.ZipFile(str(path), 'w') as z:
        for name, data in sorted(entries.items()):
            z.writestr(name, data)


def ticket_obj(refs):
    det = {b: list(refs.get(b, [])) for b in
           ('RESOLVE', 'RENAME', 'SIGCHG', 'MISSING', 'EXTERNAL')}
    return {
        'mod': '/tmp/synthetic.jar',
        'total': sum(len(v) for v in det.values()),
        'resolve': len(det['RESOLVE']),
        'rename': len(det['RENAME']),
        'sigchg': len(det['SIGCHG']),
        'missing': len(det['MISSING']),
        'autoFixCeiling': 100.0,
        'details': det,
    }


def write_ticket(path, refs):
    path.write_text(json.dumps(ticket_obj(refs), ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')
    return str(path)


def build_contract(path, tickets, version='26.1'):
    text, stats, conflicts = LG.build(tickets, version)
    path.write_bytes(text.encode('utf-8'))
    return str(path), text, stats


def cli(*argv):
    return subprocess.run([PY, str(TOOLS / 'contract_audit.py'), *map(str, argv)],
                          capture_output=True, text=True, env=ENV)


def unit():
    # ---- decode_modified_utf8 ----
    ok(m.decode_modified_utf8(b'abc') == 'abc', 'decode ascii')
    ok(m.decode_modified_utf8(b'a\xc0\x80b') == 'a' + chr(0) + 'b', 'decode C0 80 NUL')
    ok(m.decode_modified_utf8(b'\xc3\xa9') == chr(0xe9), 'decode 2-byte')
    ok(m.decode_modified_utf8(b'\xe4\xb8\xad') == chr(0x4e2d), 'decode 3-byte')
    ok(m.decode_modified_utf8(b'\xed\xa0\xbd\xed\xb8\x80') == chr(0x1f600),
       'decode surrogate pair to supplementary')
    for raw, label in [(b'\x80', 'bad leading byte'), (b'\xc3', 'truncated 2-byte'),
                       (b'\xed\xb8\x80', 'unpaired low surrogate'),
                       (b'\xed\xa0\xbd', 'high surrogate without pair')]:
        try:
            m.decode_modified_utf8(raw)
            ok(False, 'decode must reject ' + label)
        except m.AuditError as e:
            ok(e.code == 'BAD_MODIFIED_UTF8', 'decode rejects ' + label)

    # ---- valid_owner ----
    for s, exp in [('net/minecraft/A', True), ('A', True), ('a/B$C', True),
                   ('', False), ('1A', False), ('/A', False), ('A/', False),
                   ('A//B', False), ('A.B', False), ('A B', False)]:
        ok(m.valid_owner(s) is exp, 'valid_owner ' + repr(s))

    # ---- valid_desc (stricter than capability.py coarse regex) ----
    for d, exp in [('()V', True), ('(I)V', True), ('()Lnet/minecraft/A;', True),
                   ('()[Lnet/minecraft/A;', True), ('I', True), ('[B', True),
                   ('Ljava/lang/String;', True), ('(Ljava/lang/String;I)Z', True),
                   ('(', False), ('()X', False), ('Lx', False), ('Lx(;', False),
                   ('()VV', False), ('(V)V', False), ('(I)', False)]:
        ok(m.valid_desc(d) is exp, 'valid_desc ' + repr(d))
    ok(m.valid_desc('Lx(;') is False, 'strict parser rejects desc that coarse regex accepts')

    # ---- member name / array owner namespace ----
    ok(m.valid_member_name('<init>') and m.valid_member_name('method_1')
       and m.valid_member_name('$x'), 'valid member names')
    ok(not m.valid_member_name('a.b') and not m.valid_member_name('')
       and not m.valid_member_name('a-b'), 'invalid member names')
    ok(m.owner_namespace('net/minecraft/A') == 'net/minecraft/A', 'namespace plain')
    ok(m.owner_namespace('[Lnet/minecraft/A;') == 'net/minecraft/A', 'namespace array object')
    ok(m.owner_namespace('[I') == 'java/lang/Object', 'namespace array primitive')

    # ---- constant pool + member refs ----
    A = ('net/minecraft/client/Minecraft', 'getInstance',
         '()Lnet/minecraft/client/Minecraft;')
    F = ('net/minecraft/client/Minecraft', 'screen',
         'Lnet/minecraft/client/gui/screens/Screen;')
    E = ('java/lang/Object', '<init>', '()V')
    data = mkclass([(A[0], A[1], A[2], 10), (E[0], E[1], E[2], 10),
                    (F[0], F[1], F[2], 9)])
    count, ents, body = m.parse_constant_pool(data)
    ok(count > 5 and len(body) == 14, 'constant pool shape')
    got = m.class_member_refs(data)
    ok(len(got) == 3, 'member refs count')
    ok(A in got, 'Methodref recovered')
    ok(F in got, 'Fieldref recovered')
    ok(E in got, 'external Methodref recovered')

    for bad, label in [(b'not a class', 'bad magic'), (data[:20], 'truncated cp')]:
        try:
            m.parse_constant_pool(bad)
            ok(False, 'must reject ' + label)
        except m.AuditError as e:
            ok(e.code == 'BAD_CLASS_FILE', 'reject ' + label)

    long_cp = (b'\xca\xfe\xba\xbe' + b'\x00\x00' + b'\x00\x3d'
               + struct.pack('>H', 3) + b'\x05' + struct.pack('>q', 7)
               + struct.pack('>HHHHHHH', 0x21, 0, 0, 0, 0, 0, 0))
    c2, e2, b2 = m.parse_constant_pool(long_cp)
    ok(c2 == 3 and e2[1][0] == 5 and e2[2] is None, 'Long/Double consumes two cp slots')
    bad_long = (b'\xca\xfe\xba\xbe' + b'\x00\x00' + b'\x00\x3d'
                + struct.pack('>H', 2) + b'\x05' + struct.pack('>q', 7)
                + struct.pack('>HHHHHHH', 0x21, 0, 0, 0, 0, 0, 0))
    try:
        m.parse_constant_pool(bad_long)
        ok(False, 'must reject Long at final cp slot')
    except m.AuditError as e:
        ok(e.code == 'BAD_CLASS_FILE' and 'final cp slot' in str(e),
           'reject Long at final cp slot')

    # ---- classify_refs ----
    entries = {A: 'RESOLVE', ('net/minecraft/client/Minecraft', 'gone', '()V'): 'MISSING'}
    jar_refs = set(entries) | {E, ('org/joml/Matrix4f', 'identity', '()Lorg/joml/Matrix4f;'),
                                ('net/minecraft/client/Minecraft', 'extra', '()V')}
    cov = m.classify_refs(jar_refs, entries, set(), list(m.GAME_PREFIXES), False)
    ok(cov['covered'] == 2 and cov['covered_by_status']['RESOLVE'] == 1
       and cov['covered_by_status']['MISSING'] == 1, 'coverage counted by status')
    ok(cov['external'] == 1, 'external by JDK prefix')
    ok(cov['unknown_game_refs'] == 1, 'unknown game ref counted')
    ok(cov['unclassified_refs'] == 1, 'unclassified third-party ref counted')
    ok(cov['needs_manual_refs'] == 1 and cov['known_blockers'] == 1, 'MANUAL = MISSING+SIGCHG+RENAME')
    ok(cov['stale_contract_refs'] == 0, 'no stale key when all present')
    cov2 = m.classify_refs(jar_refs, entries, set(), list(m.GAME_PREFIXES), True)
    ok(cov2['unclassified_refs'] == 0 and cov2['third_party'] == 1,
       '--allow-third-party waives unclassified only')
    xkey = ('net/minecraft/client/Minecraft', 'extra', '()V')
    cov3 = m.classify_refs({xkey}, {}, {xkey}, list(m.GAME_PREFIXES), False)
    ok(cov3['external'] == 1 and cov3['unknown_game_refs'] == 0,
       'exact EXTERNAL ticket ref exempts game-namespace owner')


def parse_contract_unit():
    d = Path(tempfile.mkdtemp(prefix='contract-parse-'))
    A = 'net/minecraft/client/Minecraft.getInstance()Lnet/minecraft/client/Minecraft;'
    t = write_ticket(d / 't.json', {'RESOLVE': [A]})
    c, text, stats = build_contract(d / 'c.tsv', [t])
    parsed = m.parse_contract(c)
    ok(parsed['row_count'] == 1 and parsed['version'] == '26.1', 'canonical contract parses')
    ok(parsed['sha256'] == hashlib.sha256(Path(c).read_bytes()).hexdigest(),
       'contract sha256 matches bytes')
    raw = Path(c).read_bytes()
    mutations = [
        (raw.replace(b'\n', b'\r\n'), 'CRLF'),
        (raw[:-1], 'missing final LF'),
        (raw + b' -> leak\n', 'mapping arrow'),
        (raw.replace(b'\t', b' ', 4), 'space columns'),
        (raw.replace(b'RESOLVE', b'resolve'), 'lowercase status'),
        (raw.replace(b'RESOLVE', b'MISSNG'), 'unknown status'),
        (raw + b'\n', 'blank line'),
        (raw.replace(b'# source_tickets=1 source_sha256=', b'# source_sha256='),
         'missing source_tickets'),
        (raw.replace(b'source_sha256=', b'source_sha256=Z'), 'bad digest'),
        (raw + raw.split(b'\n')[-2] + b'\n', 'duplicate key'),
    ]
    for bad, label in mutations:
        bp = d / ('bad_' + label.replace(' ', '_') + '.tsv')
        bp.write_bytes(bad)
        try:
            m.parse_contract(str(bp))
            ok(False, 'parse_contract must reject ' + label)
        except m.AuditError as e:
            ok(e.code == 'CONTRACT_NOT_CANONICAL', 'parse_contract rejects ' + label)


def cli_tests():
    d = Path(tempfile.mkdtemp(prefix='contract-audit-'))
    A = ('net/minecraft/client/Minecraft', 'getInstance',
         '()Lnet/minecraft/client/Minecraft;')
    AREF = A[0] + '.' + A[1] + A[2]
    E = ('java/lang/Object', '<init>', '()V')
    EREF = E[0] + '.' + E[1] + E[2]
    t1 = write_ticket(d / 't1.json', {'RESOLVE': [AREF], 'EXTERNAL': [EREF]})
    contract, text, stats = build_contract(d / 'c.tsv', [t1])
    jar = d / 'mod.jar'
    mkjar(jar, {'t/Audit.class': mkclass([(A[0], A[1], A[2], 10),
                                          (E[0], E[1], E[2], 10)])})

    r = cli('--contract', contract, '--modjar', jar, '--version', '26.1', '--ticket', t1)
    ok(r.returncode == 0, 'COVERAGE_OK rc=0 ' + r.stderr)
    ok('verdict=COVERAGE_OK' in r.stdout, 'stdout verdict COVERAGE_OK')
    ok(m.DISCLAIMER in r.stdout, 'success stdout always carries DISCLAIMER')
    ok('covered=1' in r.stdout and 'external=1' in r.stdout, 'covered/external counts')

    t2 = write_ticket(d / 't2.json', {'MISSING': [AREF]})
    c2, _, _ = build_contract(d / 'c2.tsv', [t2])
    r = cli('--contract', c2, '--modjar', jar, '--version', '26.1', '--ticket', t2)
    ok(r.returncode == 2 and 'verdict=NEEDS_MANUAL' in r.stdout, 'NEEDS_MANUAL rc=2')
    ok('NEEDS_MANUAL refs=1' in r.stderr, 'NEEDS_MANUAL stderr detail')
    r = cli('--contract', c2, '--modjar', jar, '--version', '26.1', '--ticket', t2,
            '--coverage-only')
    ok(r.returncode == 0 and 'verdict=COVERAGE_ONLY_OK' in r.stdout,
       '--coverage-only waives NEEDS_MANUAL')

    jar_u = d / 'unknown.jar'
    mkjar(jar_u, {'t/U.class': mkclass([
        ('net/minecraft/client/Minecraft', 'brandNew', '()V', 10)])})
    r = cli('--contract', contract, '--modjar', jar_u, '--version', '26.1', '--ticket', t1)
    ok(r.returncode == 1 and 'UNKNOWN_GAME_REFS' in r.stdout
       and 'UNKNOWN_GAME_REFS' in r.stderr, 'UNKNOWN_GAME_REFS fail-loud')

    jar_t = d / 'third.jar'
    mkjar(jar_t, {'t/T.class': mkclass([
        (A[0], A[1], A[2], 10),
        ('org/joml/Matrix4f', 'identity', '()Lorg/joml/Matrix4f;', 10)])})
    r = cli('--contract', contract, '--modjar', jar_t, '--version', '26.1', '--ticket', t1)
    ok(r.returncode == 1 and 'UNCLASSIFIED_REFS' in r.stdout,
       'UNCLASSIFIED_REFS fail-loud')
    r = cli('--contract', contract, '--modjar', jar_t, '--version', '26.1', '--ticket', t1,
            '--allow-third-party')
    ok(r.returncode == 0 and 'verdict=COVERAGE_OK' in r.stdout,
       '--allow-third-party waives')

    r = cli('--contract', contract, '--modjar', jar, '--version', '1.21.11', '--ticket', t1)
    ok(r.returncode == 1 and 'VERSION_MISMATCH' in r.stdout, 'version mismatch fail-loud')

    t3 = write_ticket(d / 't3.json', {'RESOLVE': [AREF]})
    c3, _, _ = build_contract(d / 'c3.tsv', [t3])
    obj = json.loads((d / 't3.json').read_text(encoding='utf-8'))
    obj['autoFixCeiling'] = 99.0
    (d / 't3.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
    r = cli('--contract', c3, '--modjar', jar, '--version', '26.1', '--ticket', t3)
    ok(r.returncode == 1 and 'TICKET_DIGEST_MISMATCH' in r.stdout,
       'ticket byte mutation -> TICKET_DIGEST_MISMATCH')

    row_old = A[0] + TAB + A[1] + TAB + A[2] + TAB + 'RESOLVE'
    row_new = A[0] + TAB + A[1] + TAB + A[2] + TAB + 'SIGCHG'
    ok(row_old in text, 'canonical RESOLVE row present')
    c_rg = d / 'c_rg.tsv'
    c_rg.write_bytes(text.replace(row_old, row_new).encode('utf-8'))
    r = cli('--contract', c_rg, '--modjar', jar, '--version', '26.1', '--ticket', t1)
    ok(r.returncode == 1 and 'REGENERATION_MISMATCH' in r.stdout,
       'mutated data row -> REGENERATION_MISMATCH')
    ok('TICKET_DIGEST_MISMATCH' not in r.stdout,
       'header digest still matches when only data row mutated')

    nc = d / 'nc.tsv'
    nc.write_text('# mcport-linkgate-contract schema=1 version=26.1\n'
                  '# source_tickets=1 source_sha256=' + '0' * 64 + '\n'
                  '# note\n# owner name desc status\n'
                  + A[0] + ' ' + A[1] + ' ' + A[2] + ' RESOLVE\n', encoding='utf-8')
    r = cli('--contract', nc, '--modjar', jar, '--version', '26.1')
    ok(r.returncode == 1 and 'CONTRACT_NOT_CANONICAL' in r.stdout,
       'non-canonical contract rejected')

    r = cli('--contract', str(d / 'missing.tsv'), '--modjar', jar)
    ok(r.returncode == 1 and 'CONTRACT_IO' in r.stdout, 'missing contract -> CONTRACT_IO')

    jar_empty = d / 'empty.jar'
    mkjar(jar_empty, {'readme.txt': b'hello'})
    r = cli('--contract', contract, '--modjar', jar_empty, '--version', '26.1', '--ticket', t1)
    ok(r.returncode == 1 and 'NO_CLASS_ENTRIES' in r.stdout, 'no class entries fail-loud')

    jar_nomem = d / 'nomem.jar'
    mkjar(jar_nomem, {'t/N.class': mkclass([])})
    r = cli('--contract', contract, '--modjar', jar_nomem, '--version', '26.1', '--ticket', t1)
    ok(r.returncode == 1 and ('NO_MEMBER_REFS' in r.stdout or 'NO_SCANNABLE_REFS' in r.stdout),
       'class with no member refs fails')

    jar_bad = d / 'bad.jar'
    mkjar(jar_bad, {'t/B.class': b'garbage'})
    r = cli('--contract', contract, '--modjar', jar_bad, '--version', '26.1', '--ticket', t1)
    ok(r.returncode == 1 and 'BAD_CLASS_FILE' in r.stdout, 'malformed class fails loud')

    A2REF = ('net/minecraft/client/Minecraft.getWindow()'
             'Lcom/mojang/blaze3d/platform/Window;')
    t_stale = write_ticket(d / 't_stale.json', {'RESOLVE': [AREF, A2REF]})
    c_stale, _, _ = build_contract(d / 'c_stale.tsv', [t_stale])
    jar_one = d / 'one.jar'
    mkjar(jar_one, {'t/O.class': mkclass([(A[0], A[1], A[2], 10)])})
    r = cli('--contract', c_stale, '--modjar', jar_one, '--version', '26.1',
            '--ticket', t_stale)
    ok(r.returncode == 0 and 'stale=1' in r.stdout, 'stale quantified but not blocking')
    r = cli('--contract', c_stale, '--modjar', jar_one, '--version', '26.1',
            '--ticket', t_stale, '--fail-stale')
    ok(r.returncode == 1 and 'STALE_CONTRACT_REFS' in r.stdout, '--fail-stale blocks')

    r = cli('--contract', contract, '--modjar', jar, '--version', '26.1', '--ticket', t1,
            '--game-prefix', 'net.minecraft.')
    ok(r.returncode == 1 and 'BAD_GAME_PREFIX' in r.stdout, 'dotted game prefix rejected')

    out = d / 'report.json'
    summ = d / 'summary.csv'
    r = cli('--contract', contract, '--modjar', jar, '--version', '26.1', '--ticket', t1,
            '--out', out, '--summary', summ)
    ok(r.returncode == 0, '--out/--summary rc=0')
    obj = json.loads(out.read_text(encoding='utf-8'))
    ok(obj['verdict'] == 'COVERAGE_OK' and obj['disclaimer'] == m.DISCLAIMER,
       'JSON report verdict + disclaimer')
    ok(obj['regenerated_bytes_match'] is True and obj['ticket_digest_ok'] is True,
       'JSON report provenance')
    with open(summ, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    ok(len(rows) == 2 and rows[0] == list(m.SUMMARY_COLS), 'CSV header is 25 SUMMARY_COLS')
    ok(len(rows[1]) == len(m.SUMMARY_COLS)
       and rows[1][rows[0].index('verdict')] == 'COVERAGE_OK', 'CSV row values')
    out2 = d / 'report2.json'
    cli('--contract', contract, '--modjar', jar, '--version', '26.1', '--ticket', t1,
        '--out', out2)
    ok(out.read_bytes() == out2.read_bytes(), 'JSON report byte-deterministic')


def real_tickets():
    pats = sorted((REPO / 'data' / 'hotmods').glob('26.1__*.json'))
    ok(len(pats) == 4, 'four real 26.1 LinkCheck tickets present')
    d = Path(tempfile.mkdtemp(prefix='contract-audit-real-'))
    paths = [str(x) for x in pats]
    cpath = d / 'contract-26.1.tsv'
    text, stats, conflicts = LG.build(paths, '26.1')
    cpath.write_bytes(text.encode('utf-8'))
    ok(conflicts == 0, 'real tickets have no contradictory statuses')
    BUG = ('com/mojang/blaze3d/systems/RenderSystem'
           '.shaderLightDirections[Lorg/joml/Vector3f;  # descriptor changed')
    ok(m.CAP.parse_ref(BUG) ==
       ('F', 'com/mojang/blaze3d/systems/RenderSystem',
        'shaderLightDirections', '[Lorg/joml/Vector3f;'),
       'strict parse_ref fixes the 0.2.1 silent-pass field split')
    ok(('\tshaderLightDirections\t[Lorg/joml/Vector3f;\tSIGCHG') in text,
       'canonical 26.1 contract carries the correct SIGCHG key')
    ok('LightDirections[Lorg' not in text,
       'canonical 26.1 contract has no impossible LightDirections[ descriptor')
    parsed = m.parse_contract(str(cpath))
    ok(parsed['row_count'] == 1019, 'real 26.1 contract has 1019 canonical rows')
    ok(parsed['version'] == '26.1' and parsed['source_tickets'] == 4,
       'real header identity')
    ext_refs = m.collect_external_refs(paths)
    # 28 raw EXTERNAL lines across four tickets; one canonical key is repeated
    # (different source annotations collapse to the same owner/name/desc).
    ok(len(ext_refs) == 27, '28 raw EXTERNAL lines collapse to 27 canonical keys')
    good = sorted(k for k, s in parsed['entries'].items()
                  if s == 'RESOLVE' and k[0].startswith(m.GAME_PREFIXES)
                  and k not in ext_refs)
    ok(len(good) > 0, 'real contract has RESOLVE game refs')
    GK = good[0]
    tag = 10 if GK[2].startswith('(') else 9
    E = ('java/lang/Object', '<init>', '()V')
    jar = d / 'real.jar'
    mkjar(jar, {'t/R.class': mkclass([(GK[0], GK[1], GK[2], tag),
                                      (E[0], E[1], E[2], 10)])})
    ticket_args = [x for pth in paths for x in ('--ticket', pth)]
    out = d / 'real.json'
    r = cli('--contract', cpath, '--modjar', jar, '--version', '26.1',
            '--out', out, *ticket_args)
    ok(r.returncode == 0 and 'verdict=COVERAGE_OK' in r.stdout,
       'real tickets regenerate byte-exactly and cover a real ref ' + r.stderr)
    obj = json.loads(out.read_text(encoding='utf-8'))
    ok(obj['ticket_digest_ok'] is True and obj['regenerated_bytes_match'] is True,
       'real provenance digest + regeneration')
    ok(obj['contract_rows'] == 1019 and obj['stale_contract_refs'] == 1018,
       'stale contract keys quantified without blocking')


if __name__ == '__main__':
    unit()
    parse_contract_unit()
    cli_tests()
    real_tickets()
    print('RESULT ALL_OK assertions=' + str(COUNT))
