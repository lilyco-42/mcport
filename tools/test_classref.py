#!/usr/bin/env python3
"""McPort 0.2.5 / REPORT section 24: self-contained regression for tools/classref.py.

Pure standard library and offline. All failing inputs and bytecode are
synthesized in tempfile; the only repository bytes read are the eight already
distributed aggregate tickets, the 274B golden ticket and five tracked demo
jars. No Minecraft jar, Mojang mapping, third-party mod binary, network access
or Java compiler invocation is required.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import warnings
import zipfile
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
TOOLS = REPO / 'tools'
DATA = REPO / 'data'
DEMO = REPO / 'demo'
PY = sys.executable if sys.executable else '/usr/bin/python3'
ENV = dict(os.environ)
ENV['LANG'] = 'C.utf8'
ENV['LC_ALL'] = 'C.utf8'

_spec = importlib.util.spec_from_file_location('test_classref_module', TOOLS / 'classref.py')
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
_cap_spec = importlib.util.spec_from_file_location('test_classref_capability', TOOLS / 'capability.py')
cap = importlib.util.module_from_spec(_cap_spec)
_cap_spec.loader.exec_module(cap)

COUNT = 0


def ok(label, cond):
    global COUNT
    COUNT += 1
    if not cond:
        raise AssertionError('#' + str(COUNT) + ': ' + label)


def raises(label, code, fn):
    try:
        fn()
    except m.ClassRefError as e:
        ok(label + '_code', e.code == code)
        return
    ok(label + '_raised', False)


def u2p(i):
    return struct.pack('>H', i)


def cu(s):
    b = s.encode('utf-8') if isinstance(s, str) else s
    return b'\x01' + u2p(len(b)) + b


def assemble(ents, body):
    return bytes([0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 61]) + struct.pack('>H', len(ents)) + b''.join(ents[1:]) + body


def mkclass(own='t/T', names=(), extra=(), fields=(), methods=(), super_name='java/lang/Object'):
    ents = [None]

    def add(e):
        ents.append(e)
        return len(ents) - 1

    i_own = add(cu(own))
    c_own = add(b'\x07' + u2p(i_own))
    i_sup = add(cu(super_name))
    c_sup = add(b'\x07' + u2p(i_sup))
    for n in names:
        i = add(cu(n))
        add(b'\x07' + u2p(i))
    for kind, val in extra:
        if kind == 'utf8':
            add(cu(val))
        elif kind == 'nat':
            di = add(cu(val))
            add(b'\x0c' + struct.pack('>HH', 1, di))
        elif kind == 'mt':
            di = add(cu(val))
            add(b'\x10' + u2p(di))
        elif kind == 'raw':
            add(val)
    fdesc = []
    mdesc = []
    for desc, attrs in fields:
        di = add(cu(desc))
        fdesc.append((di, attrs))
    for desc, attrs in methods:
        di = add(cu(desc))
        mdesc.append((di, attrs))
    body = struct.pack('>HHHHH', 0x21, c_own, c_sup, 0, len(fdesc))
    for di, attrs in fdesc:
        body += struct.pack('>HHHH', 1, 1, di, len(attrs))
        for a in attrs:
            body += struct.pack('>HI', 1, len(a)) + a
    body += struct.pack('>H', len(mdesc))
    for di, attrs in mdesc:
        body += struct.pack('>HHHH', 1, 1, di, len(attrs))
        for a in attrs:
            body += struct.pack('>HI', 1, len(a)) + a
    body += struct.pack('>H', 0)
    return assemble(ents, body)


def mkclass_bad_utf8():
    ents = [None]

    def add(e):
        ents.append(e)
        return len(ents) - 1

    i_own = add(cu('t/T'))
    c_own = add(b'\x07' + u2p(i_own))
    i_sup = add(cu('java/lang/Object'))
    c_sup = add(b'\x07' + u2p(i_sup))
    bad = add(b'\x01\x00\x01\x80')
    add(b'\x07' + u2p(bad))
    body = struct.pack('>HHHHH', 0x21, c_own, c_sup, 0, 0) + struct.pack('>H', 0) + struct.pack('>H', 0)
    return assemble(ents, body)


def mkjar(path, classes, resources=()):
    with zipfile.ZipFile(str(path), 'w') as z:
        for name, data in classes:
            z.writestr(name, data)
        for name, data in resources:
            z.writestr(name, data)


def write_lines(path, rows):
    with open(str(path), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(rows) + '\n')


def ns(**kw):
    base = dict(decl='decl.tsv', modjar='mod.jar', map=None, version=None,
                decl_sha256=None, game_prefix=[], allow_third_party=False,
                coverage_only=False, out=None, summary=None)
    base.update(kw)
    return m.argparse.Namespace(**base)


def fake_agg(own, occ):
    return {'own': set(own), 'occurrences': Counter(occ), 'cp_raw': {},
            'desc_raw': {}, 'origins': {}, 'array_occurrences': 0}


def cli(args, env=ENV):
    return subprocess.run([PY, str(TOOLS / 'classref.py')] + list(args),
                          capture_output=True, text=True, env=env)


# ---- A. constants and declared scope ----
ok('A1_schema', m.SCHEMA == 1)
ok('A2_tool', m.TOOL == 'mcport.classref')
ok('A3_linkage', m.LINKAGE_SPEC == 'JVMS 5.4.3.1')
ok('A4_policy', m.CLAIM_POLICY == 'static-class-linkage-only; no runtime claim')
ok('A5_disclaimer', 'does NOT mean runtime-compatible' in m.DISCLAIMER)
ok('A6_semantic', 'semantic equivalence' in m.DISCLAIMER)
ok('A7_status', set(m.ALLOWED_STATUS) == {'RESOLVE', 'RENAME', 'MISSING', 'EXTERNAL', 'THIRD_PARTY', 'SELF'})
ok('A8_block', set(m.BLOCK_STATUS) == {'MISSING', 'RENAME'})
ok('A9_game', m.GAME_PREFIXES == ('net/minecraft/', 'com/mojang/blaze3d/', 'com/mojang/math/', 'com/mojang/realmsclient/'))
ok('A10_external', 'java/' in m.EXTERNAL_PREFIXES and 'com/mojang/authlib/' in m.EXTERNAL_PREFIXES)
ok('A11_exit_ok', m.EXIT_CODE['CLASSREFS_OK'] == 0)
ok('A12_exit_only', m.EXIT_CODE['CLASSREFS_ONLY_OK'] == 0)
ok('A13_exit_manual', m.EXIT_CODE['NEEDS_MANUAL'] == 2)
ok('A14_exit_bad', m.EXIT_CODE['UNSUPPORTED'] == 1)
ok('A15_summary_cols', len(m.SUMMARY_COLS) == 27)
ok('A16_summary_verdict', 'verdict' in m.SUMMARY_COLS)
ok('A17_summary_digest', 'decl_digest_ok' in m.SUMMARY_COLS)
ok('A18_scope_cover', 'CONSTANT_Class tag 7 names including array descriptors' in m.SCOPE['covers'])
ok('A19_scope_not', any('semantic drift' in x for x in m.SCOPE['does_not_cover']))
ok('A20_scope_mixin', any('Mixin' in x for x in m.SCOPE['does_not_cover']))

# ---- B. class name validation and array normalization ----
ok('B1_owner', m.valid_class_name('net/minecraft/Api'))
ok('B2_module', m.valid_class_name('module-info'))
ok('B3_package', m.valid_class_name('package-info'))
ok('B4_dot_bad', not m.valid_class_name('net.minecraft/Api'))
ok('B5_array_bad', not m.valid_class_name('[Lnet/minecraft/Api;'))
ok('B6_empty_bad', not m.valid_class_name(''))
ok('B7_norm_plain', m.normalize_class_name('net/minecraft/Api') == 'net/minecraft/Api')
ok('B8_norm_array_obj', m.normalize_class_name('[Lnet/minecraft/Thing;') == 'net/minecraft/Thing')
ok('B9_norm_array_prim', m.normalize_class_name('[I') == 'java/lang/Object')
raises('B10_norm_bad_name', 'BAD_CLASS_NAME', lambda: m.normalize_class_name('net.minecraft/Api'))
raises('B11_bad_array', 'BAD_ARRAY_CLASS', lambda: m.normalize_class_name('[Lnet/minecraft/Thing'))
raises('B12_bad_empty_array', 'BAD_ARRAY_CLASS', lambda: m.normalize_class_name('['))

# ---- C. descriptor object types ----
ok('C1_method', m.desc_object_types('(Ljava/lang/String;I[Lnet/minecraft/Thing;)V') == ['java/lang/String', 'net/minecraft/Thing'])
ok('C2_field', m.desc_object_types('[Lnet/minecraft/Thing;') == ['net/minecraft/Thing'])
ok('C3_dedup', m.desc_object_types('(Lnet/minecraft/Thing;Lnet/minecraft/Thing;)V') == ['net/minecraft/Thing'])
ok('C4_void', m.desc_object_types('()V') == [])
ok('C5_prim', m.desc_object_types('(IDJ)V') == [])
raises('C6_trunc_method', 'BAD_DESCRIPTOR', lambda: m.desc_object_types('(I'))
raises('C7_bad_obj', 'BAD_DESCRIPTOR', lambda: m.desc_object_types('LBad[Name;'))
raises('C8_void_field', 'BAD_DESCRIPTOR', lambda: m.desc_object_types('V'))
raises('C9_empty', 'BAD_DESCRIPTOR', lambda: m.desc_object_types(''))
raises('C10_unterminated', 'BAD_DESCRIPTOR', lambda: m.desc_object_types('Lnet/minecraft/Thing'))
raises('C11_bad_owner', 'BAD_DESCRIPTOR', lambda: m.desc_object_types('Lnet.minecraft/Thing;'))
raises('C12_bad_ret', 'BAD_DESCRIPTOR', lambda: m.desc_object_types('()Q'))

# ---- D. attribute skipping ----
ok('D1_valid', m._skip_attrs(struct.pack('>HI', 1, 2) + b'ab', 0, 1) == 8)
raises('D2_short_header', 'BAD_CLASS_FILE', lambda: m._skip_attrs(b'', 0, 1))
raises('D3_short_body', 'BAD_CLASS_FILE', lambda: m._skip_attrs(struct.pack('>HI', 1, 100) + b'x', 0, 1))

# ---- E. parse_class ----
minc = mkclass(names=['net/minecraft/Api'])
p = m.parse_class(minc)
ok('E1_own', p['own'] == 't/T')
ok('E2_cp_names', sorted(set(p['cp_class_names'])) == ['java/lang/Object', 'net/minecraft/Api', 't/T'])
ok('E3_no_desc', p['desc_items'] == [])
raises('E4_not_class', 'BAD_CLASS_FILE', lambda: m.parse_class(b'not a class'))
raises('E5_bad_utf8', 'BAD_MODIFIED_UTF8', lambda: m.parse_class(mkclass_bad_utf8()))
raises('E6_bad_this', 'BAD_CLASS_NAME', lambda: m.parse_class(mkclass(own='net.minecraft/Bad')))
raises('E7_bad_cp_index', 'BAD_CLASS_FILE', lambda: m.parse_class(mkclass(extra=[('raw', b'\x07' + u2p(99))])))
raises('E8_trunc_body', 'BAD_CLASS_FILE', lambda: m.parse_class(assemble([None, cu('t/T'), b'\x07' + u2p(1), cu('java/lang/Object'), b'\x07' + u2p(3)], b'\x00' * 8)))

natc = mkclass(names=['net/minecraft/Api'],
               extra=[('nat', '(Lnet/minecraft/Thing;)V'), ('mt', '[Lnet/minecraft/Gone;')])
np = m.parse_class(natc)
ok('E9_nat_count', len(np['desc_items']) == 2)
ok('E10_nat_method', ('(Lnet/minecraft/Thing;)V', ['net/minecraft/Thing']) in np['desc_items'])
ok('E11_mt_field', ('[Lnet/minecraft/Gone;', ['net/minecraft/Gone']) in np['desc_items'])

fmc = mkclass(names=['net/minecraft/Api'],
              fields=[('Lnet/minecraft/Api;', []), ('[Lnet/minecraft/Thing;', [b'xx'])],
              methods=[('()Ljava/lang/String;', [])])
fp = m.parse_class(fmc)
ok('E12_field_desc', ('Lnet/minecraft/Api;', ['net/minecraft/Api']) in fp['desc_items'])
ok('E13_field_array', ('[Lnet/minecraft/Thing;', ['net/minecraft/Thing']) in fp['desc_items'])
ok('E14_method_desc', ('()Ljava/lang/String;', ['java/lang/String']) in fp['desc_items'])
ok('E15_attr_payload', len(fp['desc_items']) == 3)

with tempfile.TemporaryDirectory() as td:
    T = pathlib.Path(td)

    # ---- F. scan_jar and aggregate ----
    j1 = T / 'one.jar'
    mkjar(j1, [('z/Z.class', mkclass(own='z/Z')), ('a/A.class', mkclass(own='a/A'))],
          [('readme.txt', b'hello')])
    per = m.scan_jar(str(j1))
    ok('F1_sort', [e for e, _ in per] == ['a/A.class', 'z/Z.class'])
    ok('F2_ignore_resource', len(per) == 2)
    ok('F3_own_a', per[0][1]['own'] == 'a/A')

    jempty = T / 'empty.jar'
    mkjar(jempty, [], [('readme.txt', b'no class')])
    raises('F4_no_class', 'NO_CLASS_ENTRIES', lambda: m.scan_jar(str(jempty)))

    jdup = T / 'dup.jar'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(str(jdup), 'w') as z:
            z.writestr('a/A.class', mkclass(own='a/A'))
            z.writestr('a/A.class', mkclass(own='a/A'))
    raises('F5_dup', 'DUPLICATE_CLASS_ENTRY', lambda: m.scan_jar(str(jdup)))

    jbad = T / 'bad.jar'
    with open(str(jbad), 'wb') as fh:
        fh.write(b'not a zip')
    raises('F6_bad_zip', 'JAR_IO', lambda: m.scan_jar(str(jbad)))
    raises('F7_missing_jar', 'JAR_IO', lambda: m.scan_jar(str(T / 'missing.jar')))

    c1 = mkclass(own='c/C1', names=['[Lnet/minecraft/Thing;'],
                 extra=[('nat', '(Lnet/minecraft/Thing;)V')])
    c2 = mkclass(own='c/C2', names=['net/minecraft/Thing'])
    jagg = T / 'agg.jar'
    mkjar(jagg, [('c/C1.class', c1), ('c/C2.class', c2)])
    agg = m.aggregate(m.scan_jar(str(jagg)))
    ok('F8_own', agg['own'] == {'c/C1', 'c/C2'})
    ok('F9_thing_occ', agg['occurrences']['net/minecraft/Thing'] == 3)
    ok('F10_array_occ', agg['array_occurrences'] == 1)
    ok('F11_cp_raw', '[Lnet/minecraft/Thing;' in agg['cp_raw']['net/minecraft/Thing'])
    ok('F12_desc_raw', '(Lnet/minecraft/Thing;)V' in agg['desc_raw']['net/minecraft/Thing'])
    ok('F13_origins', agg['origins']['net/minecraft/Thing'] == {'CLASS_CP', 'DESCRIPTOR'})
    ok('F14_object_external', 'java/lang/Object' in agg['occurrences'])

    # ---- G. parse_decl ----
    d_ok = T / 'decl_ok.tsv'
    write_lines(d_ok, ['# decl', 'C\tnet/minecraft/Api',
                       'S\tnet/minecraft/Api\tjava/lang/Object',
                       'M\tnet/minecraft/Api\tm\t()V',
                       'F\tnet/minecraft/Api\tf\tLnet/minecraft/Thing;'])
    dp = m.parse_decl(str(d_ok))
    ok('G1_classes', dp['classes'] == {'net/minecraft/Api'})
    ok('G2_rows', dp['rows'] == 4)
    ok('G3_kinds', dp['kinds'] == {'C': 1, 'S': 1, 'M': 1, 'F': 1})
    ok('G4_sha', dp['sha256'] == hashlib.sha256(d_ok.read_bytes()).hexdigest())

    d_s2 = T / 'decl_s2.tsv'
    write_lines(d_s2, ['S\tnet/minecraft/OnlyS'])
    ok('G5_s2', m.parse_decl(str(d_s2))['classes'] == {'net/minecraft/OnlyS'})

    for label, row, code in [
        ('G6_unknown', 'X\tnet/minecraft/Api', 'DECL_BAD_ROW'),
        ('G7_c3', 'C\tnet/minecraft/Api\textra', 'DECL_BAD_ROW'),
        ('G8_s5', 'S\ta\tb\tc\td', 'DECL_BAD_ROW'),
        ('G9_m3', 'M\tnet/minecraft/Api\tm\t()V\textra', 'DECL_BAD_ROW'),
        ('G10_bad_owner', 'C\tnet.minecraft/Api', 'DECL_BAD_OWNER'),
        ('G11_bad_desc', 'M\tnet/minecraft/Api\tm\t(I', 'DECL_BAD_DESC'),
    ]:
        f = T / (label + '.tsv')
        write_lines(f, [row])
        raises(label, code, lambda f=f: m.parse_decl(str(f)))

    d_empty = T / 'decl_empty.tsv'
    write_lines(d_empty, ['# comment', ''])
    raises('G12_no_classes', 'DECL_NO_CLASSES', lambda: m.parse_decl(str(d_empty)))
    raises('G13_io', 'DECL_IO', lambda: m.parse_decl(str(T / 'no_decl.tsv')))
    d_badutf = T / 'decl_badutf.tsv'
    with open(str(d_badutf), 'wb') as fh:
        fh.write(b'\xff\xfe')
    raises('G14_bad_utf8', 'DECL_BAD_UTF8', lambda: m.parse_decl(str(d_badutf)))

    # ---- H. parse_map ----
    ok('H1_none', m.parse_map(None, dp['classes'])['cmap'] == {})
    mp_ok = T / 'map_ok.tsv'
    write_lines(mp_ok, ['C\tnet/minecraft/Old\tnet/minecraft/Api',
                        'M\tnet/minecraft/Old\tm\t()V',
                        'F\tnet/minecraft/Old\tf\tI',
                        'S\tnet/minecraft/Old\tjava/lang/Object'])
    mp = m.parse_map(str(mp_ok), dp['classes'])
    ok('H2_cmap', mp['cmap'] == {'net/minecraft/Old': 'net/minecraft/Api'})
    ok('H3_ignored', mp['ignored'] == 3)
    ok('H4_rows', mp['rows'] == 1)
    ok('H5_sha', mp['sha256'] == hashlib.sha256(mp_ok.read_bytes()).hexdigest())
    ok('H6_no_bad_target', mp['bad_targets'] == [])

    mp_badtarget = T / 'map_badtarget.tsv'
    write_lines(mp_badtarget, ['C\tnet/minecraft/Old\tnet/minecraft/Nowhere'])
    ok('H7_bad_target', m.parse_map(str(mp_badtarget), dp['classes'])['bad_targets'] == ['net/minecraft/Nowhere'])

    for label, rows, code in [
        ('H8_c2', ['C\tnet/minecraft/Old'], 'MAP_BAD_ROW'),
        ('H9_unknown', ['X\tnet/minecraft/Old\tnet/minecraft/Api'], 'MAP_BAD_ROW'),
        ('H10_bad_owner', ['C\tnet.minecraft/Old\tnet/minecraft/Api'], 'MAP_BAD_OWNER'),
        ('H11_conflict', ['C\tnet/minecraft/Old\tnet/minecraft/Api', 'C\tnet/minecraft/Old\tnet/minecraft/Other'], 'MAP_CONFLICT'),
    ]:
        f = T / (label + '.tsv')
        write_lines(f, rows)
        raises(label, code, lambda f=f: m.parse_map(str(f), dp['classes']))

    mp_same = T / 'map_same.tsv'
    write_lines(mp_same, ['C\tnet/minecraft/Old\tnet/minecraft/Api', 'C\tnet/minecraft/Old\tnet/minecraft/Api'])
    ok('H12_same_ok', m.parse_map(str(mp_same), dp['classes'])['rows'] == 2)
    raises('H13_io', 'MAP_IO', lambda: m.parse_map(str(T / 'no_map.tsv'), dp['classes']))
    mp_badutf = T / 'map_badutf.tsv'
    with open(str(mp_badutf), 'wb') as fh:
        fh.write(b'\xff\xfe')
    raises('H14_bad_utf8', 'MAP_BAD_UTF8', lambda: m.parse_map(str(mp_badutf), dp['classes']))

    # ---- I. classify ----
    GP = tuple(m.GAME_PREFIXES)
    cl = m.classify(fake_agg(['t/T'], {'t/T': 1, 'java/lang/Object': 1, 'net/minecraft/Api': 1}),
                    dp['classes'], {}, GP, False, [])
    ok('I1_self', cl['status']['t/T'] == 'SELF')
    ok('I2_external', cl['status']['java/lang/Object'] == 'EXTERNAL')
    ok('I3_resolve', cl['status']['net/minecraft/Api'] == 'RESOLVE')
    ok('I4_no_reasons', cl['reasons'] == set())

    cl2 = m.classify(fake_agg(['t/T'], {'t/T': 1, 'org/example/Lib': 1, 'net/minecraft/Api': 1}),
                     dp['classes'], {}, GP, False, [])
    ok('I5_third', cl2['status']['org/example/Lib'] == 'THIRD_PARTY')
    ok('I6_unclassified', 'UNCLASSIFIED_REFS' in cl2['reasons'])
    cl3 = m.classify(fake_agg(['t/T'], {'t/T': 1, 'org/example/Lib': 1, 'net/minecraft/Api': 1}),
                     dp['classes'], {}, GP, True, [])
    ok('I7_waived', 'UNCLASSIFIED_REFS' not in cl3['reasons'])

    cl4 = m.classify(fake_agg(['t/T'], {'t/T': 1, 'java/lang/Object': 1}),
                     dp['classes'], {}, GP, True, [])
    ok('I8_no_game', 'NO_GAME_REFS' in cl4['reasons'])

    cl5 = m.classify(fake_agg(['t/T'], {'net/minecraft/Gone': 1}),
                     dp['classes'], {}, GP, False, [])
    ok('I9_missing', cl5['status']['net/minecraft/Gone'] == 'MISSING')

    cl6 = m.classify(fake_agg(['t/T'], {'net/minecraft/Old': 1}),
                     {'net/minecraft/New'}, {'net/minecraft/Old': 'net/minecraft/New'}, GP, False, [])
    ok('I10_rename', cl6['status']['net/minecraft/Old'] == 'RENAME')
    ok('I11_mapped', cl6['mapped_to'] == {'net/minecraft/Old': 'net/minecraft/New'})

    cl7 = m.classify(fake_agg(['t/T'], {'net/minecraft/Old': 1}),
                     {'net/minecraft/New'}, {'net/minecraft/Old': 'net/minecraft/Nowhere'}, GP, False,
                     ['net/minecraft/Nowhere'])
    ok('I12_mapped_missing', cl7['status']['net/minecraft/Old'] == 'MISSING')
    ok('I13_mapped_reason', 'MAPPED_TARGET_MISSING' in cl7['reasons'])
    ok('I14_global_map_reason', 'MAP_TARGET_MISSING' in cl7['reasons'])

    cl8 = m.classify(fake_agg(['t/T'], {'net/minecraft/Api': 1}),
                     dp['classes'], {'net/minecraft/Unused': 'net/minecraft/Nowhere'}, GP, False,
                     ['net/minecraft/Nowhere'])
    ok('I15_unused_bad_target', 'MAP_TARGET_MISSING' in cl8['reasons'])
    ok('I16_samples', 'net/minecraft/Api' in cl8['samples']['RESOLVE'])

    # ---- J. base_report, audit, writers, stdout, CLI ----
    br = m.base_report(ns())
    ok('J1_tool', br['tool'] == m.TOOL)
    ok('J2_scope', br['scope'] == m.SCOPE)
    ok('J3_linkage', br['linkage_spec'] == m.LINKAGE_SPEC)
    ok('J4_disclaimer', br['disclaimer'] == m.DISCLAIMER)
    ok('J5_status_zero', all(br['counts_by_status'][s] == 0 for s in m.ALLOWED_STATUS))
    ok('J6_verdict', br['verdict'] == 'UNSUPPORTED')

    jar_ok = T / 'jar_ok.jar'
    mkjar(jar_ok, [('t/T.class', mkclass(names=['net/minecraft/Api']))])
    jar_missing = T / 'jar_missing.jar'
    mkjar(jar_missing, [('t/T.class', mkclass(names=['net/minecraft/Api', 'net/minecraft/Gone']))])
    jar_nogame = T / 'jar_nogame.jar'
    mkjar(jar_nogame, [('t/T.class', mkclass())])
    jar_third = T / 'jar_third.jar'
    mkjar(jar_third, [('t/T.class', mkclass(names=['net/minecraft/Api', 'org/example/Lib']))])
    jar_own_game = T / 'jar_own_game.jar'
    mkjar(jar_own_game, [('net/minecraft/Mod.class', mkclass(own='net/minecraft/Mod', names=['net/minecraft/Api']))])
    jar_own_ext = T / 'jar_own_ext.jar'
    mkjar(jar_own_ext, [('java/lang/Mod.class', mkclass(own='java/lang/Mod', names=['net/minecraft/Api']))])
    jar_empty = T / 'jar_empty.jar'
    mkjar(jar_empty, [], [('readme.txt', b'x')])

    decl_rename = T / 'decl_rename.tsv'
    write_lines(decl_rename, ['C\tnet/minecraft/Api'])
    jar_old = T / 'jar_old.jar'
    mkjar(jar_old, [('t/T.class', mkclass(names=['net/minecraft/Old']))])

    r_ok = m.audit(ns(decl=str(d_ok), modjar=str(jar_ok)))
    ok('J7_ok_verdict', r_ok['verdict'] == 'CLASSREFS_OK')
    ok('J8_ok_resolve', r_ok['counts_by_status']['RESOLVE'] == 1)
    ok('J9_ok_classes', r_ok['classes'] == 1)
    ok('J10_ok_cp', r_ok['cp_class_refs'] == 3)
    ok('J11_ok_unique', r_ok['unique_class_refs'] == 3)
    ok('J12_ok_reasons', r_ok['reasons'] == [])
    ok('J13_ok_needs', r_ok['needs_manual'] == 0)
    ok('J14_ok_refs_sorted', [x['class'] for x in r_ok['refs']] == sorted(x['class'] for x in r_ok['refs']))
    ok('J15_ok_scope', r_ok['scope'] == m.SCOPE)

    r_ok_sha = m.audit(ns(decl=str(d_ok), modjar=str(jar_ok), decl_sha256=r_ok['decl_sha256']))
    ok('J16_digest_ok', r_ok_sha['decl_digest_ok'] is True)
    ok('J17_digest_no_reason', 'DECL_DIGEST_MISMATCH' not in r_ok_sha['reasons'])
    r_bad_sha = m.audit(ns(decl=str(d_ok), modjar=str(jar_ok), decl_sha256='0' * 64))
    ok('J18_digest_bad', r_bad_sha['decl_digest_ok'] is False)
    ok('J19_digest_reason', 'DECL_DIGEST_MISMATCH' in r_bad_sha['reasons'])
    r_bad_sha2 = m.audit(ns(decl=str(d_ok), modjar=str(jar_ok), decl_sha256='abc'))
    ok('J21_bad_sha_reason', 'BAD_DECL_SHA256' in r_bad_sha2['reasons'])

    r_manual = m.audit(ns(decl=str(d_ok), modjar=str(jar_missing)))
    ok('J22_manual_verdict', r_manual['verdict'] == 'NEEDS_MANUAL')
    ok('J23_manual_missing', r_manual['counts_by_status']['MISSING'] == 1)
    ok('J24_manual_needs', r_manual['needs_manual'] == 1)
    ok('J25_manual_no_reasons', r_manual['reasons'] == [])
    ok('J26_manual_disclaimer', m.DISCLAIMER in m.stdout_line(r_manual))

    r_only = m.audit(ns(decl=str(d_ok), modjar=str(jar_missing), coverage_only=True))
    ok('J27_only_verdict', r_only['verdict'] == 'CLASSREFS_ONLY_OK')
    ok('J28_only_missing', r_only['counts_by_status']['MISSING'] == 1)

    r_rename = m.audit(ns(decl=str(decl_rename), modjar=str(jar_old), map=str(mp_ok), coverage_only=True))
    ok('J29_rename', r_rename['counts_by_status']['RENAME'] == 1)
    ok('J30_rename_mapped', r_rename['mapped_to'] == {'net/minecraft/Old': 'net/minecraft/Api'})
    ok('J31_rename_verdict', r_rename['verdict'] == 'CLASSREFS_ONLY_OK')

    r_badtarget = m.audit(ns(decl=str(decl_rename), modjar=str(jar_old), map=str(mp_badtarget)))
    ok('J32_badtarget', 'MAP_TARGET_MISSING' in r_badtarget['reasons'])
    ok('J33_badtarget_mapped', 'MAPPED_TARGET_MISSING' in r_badtarget['reasons'])
    ok('J34_badtarget_verdict', r_badtarget['verdict'] == 'UNSUPPORTED')

    r_nogame = m.audit(ns(decl=str(d_ok), modjar=str(jar_nogame)))
    ok('J35_nogame', 'NO_GAME_REFS' in r_nogame['reasons'])
    r_third = m.audit(ns(decl=str(d_ok), modjar=str(jar_third)))
    ok('J36_third', 'UNCLASSIFIED_REFS' in r_third['reasons'])
    r_third_ok = m.audit(ns(decl=str(d_ok), modjar=str(jar_third), allow_third_party=True))
    ok('J37_third_waived', r_third_ok['verdict'] == 'CLASSREFS_OK')
    ok('J38_third_count', r_third_ok['counts_by_status']['THIRD_PARTY'] == 1)

    r_custom = m.audit(ns(decl=str(d_ok), modjar=str(jar_third), game_prefix=['org/example/']))
    ok('J39_custom_game', r_custom['counts_by_status']['MISSING'] == 1)
    ok('J40_custom_verdict', r_custom['verdict'] == 'NEEDS_MANUAL')

    r_badprefix = m.audit(ns(decl=str(d_ok), modjar=str(jar_ok), game_prefix=['net.minecraft/']))
    ok('J41_bad_prefix', 'BAD_GAME_PREFIX' in r_badprefix['reasons'])
    r_badversion = m.audit(ns(decl=str(d_ok), modjar=str(jar_ok), version='bad version'))
    ok('J42_bad_version', 'BAD_VERSION' in r_badversion['reasons'])

    r_owngame = m.audit(ns(decl=str(d_ok), modjar=str(jar_own_game)))
    ok('J43_own_game', 'OWN_GAME_NAMESPACE' in r_owngame['reasons'])
    ok('J44_own_game_list', r_owngame['own_game_classes'] == ['net/minecraft/Mod'])
    r_ownext = m.audit(ns(decl=str(d_ok), modjar=str(jar_own_ext)))
    ok('J45_own_ext', 'OWN_EXTERNAL_NAMESPACE' in r_ownext['reasons'])

    d_bad = T / 'decl_bad.tsv'
    write_lines(d_bad, ['X\tnet/minecraft/Api'])
    r_db = m.audit(ns(decl=str(d_bad), modjar=str(jar_ok)))
    ok('J46_decl_bad', 'DECL_BAD_ROW' in r_db['reasons'])
    ok('J47_no_decl', 'NO_DECL' in r_db['reasons'])

    mp_bad = T / 'map_bad.tsv'
    write_lines(mp_bad, ['C\tnet/minecraft/Old'])
    r_mb = m.audit(ns(decl=str(d_ok), modjar=str(jar_ok), map=str(mp_bad)))
    ok('J48_map_bad', 'MAP_BAD_ROW' in r_mb['reasons'])

    r_empty = m.audit(ns(decl=str(d_ok), modjar=str(jar_empty)))
    ok('J49_no_class', 'NO_CLASS_ENTRIES' in r_empty['reasons'])
    ok('J50_no_scan', 'NO_SCANNABLE_CLASSES' in r_empty['reasons'])
    r_nojar = m.audit(ns(decl=str(d_ok), modjar=str(T / 'missing.jar')))
    ok('J51_jar_io', 'JAR_IO' in r_nojar['reasons'])

    # deterministic writers
    o1 = T / 'r1.json'
    o2 = T / 'r2.json'
    m.write_json(str(o1), r_ok)
    m.write_json(str(o2), r_ok)
    ok('J52_json_deterministic', o1.read_bytes() == o2.read_bytes())
    j = json.loads(o1.read_text(encoding='utf-8'))
    ok('J53_json_verdict', j['verdict'] == 'CLASSREFS_OK')
    ok('J54_json_scope', j['scope'] == m.SCOPE)
    ok('J55_json_linkage', j['linkage_spec'] == m.LINKAGE_SPEC)
    ok('J56_json_refs', len(j['refs']) == 3)

    s1 = T / 'r1.csv'
    m.write_summary(str(s1), r_ok)
    lines = s1.read_text(encoding='utf-8').splitlines()
    ok('J57_csv_lines', len(lines) == 2)
    ok('J58_csv_header', lines[0].split(',') == list(m.SUMMARY_COLS))
    with open(str(s1), newline='', encoding='utf-8') as fh:
        import csv as _csv
        row = next(_csv.DictReader(fh))
    ok('J59_csv_verdict', row['verdict'] == 'CLASSREFS_OK')
    ok('J60_csv_resolve', row['resolve'] == '1')
    ok('J61_csv_missing', row['missing'] == '0')
    ok('J62_csv_reasons', row['reasons'] == '')

    ok('J63_stdout_ok', 'CLASSREFS_OK' in m.stdout_line(r_ok))
    ok('J64_stdout_disclaimer', m.DISCLAIMER in m.stdout_line(r_ok))
    ok('J65_stdout_bad_no_disclaimer', m.DISCLAIMER not in m.stdout_line(r_db))
    ok('J66_stdout_manual_disclaimer', m.DISCLAIMER in m.stdout_line(r_manual))

    # CLI end to end
    out_ok = T / 'cli_ok.json'
    sum_ok = T / 'cli_ok.csv'
    c = cli(['--decl', str(d_ok), '--modjar', str(jar_ok), '--out', str(out_ok), '--summary', str(sum_ok)])
    ok('J67_cli_rc', c.returncode == 0)
    ok('J68_cli_stdout', 'CLASSREFS_OK' in c.stdout)
    ok('J69_cli_disclaimer', m.DISCLAIMER in c.stdout)
    ok('J70_cli_no_fail', 'classref: FAIL:' not in c.stderr)
    ok('J71_cli_json', json.loads(out_ok.read_text(encoding='utf-8'))['verdict'] == 'CLASSREFS_OK')
    ok('J72_cli_csv', 'CLASSREFS_OK' in sum_ok.read_text(encoding='utf-8'))

    c_manual = cli(['--decl', str(d_ok), '--modjar', str(jar_missing), '--out', str(T / 'manual.json')])
    ok('J73_manual_rc', c_manual.returncode == 2)
    ok('J74_manual_stderr', 'NEEDS_MANUAL refs=1' in c_manual.stderr)
    ok('J75_manual_json', json.loads((T / 'manual.json').read_text(encoding='utf-8'))['verdict'] == 'NEEDS_MANUAL')

    c_only = cli(['--decl', str(d_ok), '--modjar', str(jar_missing), '--coverage-only'])
    ok('J76_only_rc', c_only.returncode == 0)
    ok('J77_only_stdout', 'CLASSREFS_ONLY_OK' in c_only.stdout)

    c_bad = cli(['--decl', str(d_ok), '--modjar', str(jar_ok), '--version', 'bad version', '--out', str(T / 'bad.json')])
    ok('J78_bad_rc', c_bad.returncode == 1)
    ok('J79_bad_stderr', 'classref: FAIL:' in c_bad.stderr)
    jb = json.loads((T / 'bad.json').read_text(encoding='utf-8'))
    ok('J80_bad_json', jb['verdict'] == 'UNSUPPORTED')
    ok('J81_bad_reason', 'BAD_VERSION' in jb['reasons'])

    c_digest = cli(['--decl', str(d_ok), '--modjar', str(jar_ok), '--decl-sha256', '0' * 64])
    ok('J82_digest_rc', c_digest.returncode == 1)
    ok('J83_digest_stderr', 'DECL_DIGEST_MISMATCH' in c_digest.stderr)

    c_third = cli(['--decl', str(d_ok), '--modjar', str(jar_third), '--allow-third-party'])
    ok('J84_third_rc', c_third.returncode == 0)
    ok('J85_third_stdout', 'CLASSREFS_OK' in c_third.stdout)

    # ---- K. real distributed evidence and blind-spot proof ----
    tickets = sorted((DATA / 'hotmods').glob('*.json'))
    ok('K1_ticket_count', len(tickets) == 8)
    per = Counter()
    owners = set()
    game = 0
    external = 0
    bad = 0
    for f in tickets:
        d = json.loads(f.read_text(encoding='utf-8'))
        v = f.name.split('__')[0]
        per[v] += sum(len(x) for x in d['details'].values())
        for st, lines in d['details'].items():
            for ln in lines:
                r = cap.parse_ref(ln)
                if r is None:
                    bad += 1
                    continue
                owners.add(r[1])
                if st == 'EXTERNAL':
                    external += 1
                elif r[1].startswith(m.GAME_PREFIXES):
                    game += 1
    ok('K2_per_12111', per['1.21.11'] == 1190)
    ok('K3_per_261', per['26.1'] == 1190)
    ok('K4_game', game == 2324)
    ok('K5_external', external == 56)
    ok('K6_parse_all', bad == 0)
    ok('K7_object_not_in_tickets', 'java/lang/Object' not in owners)

    golden = (DATA / 'refcheck-legacy-golden.json').read_bytes()
    ok('K8_golden_bytes', len(golden) == 274)
    ok('K9_golden_sha', hashlib.sha256(golden).hexdigest() == '1e398ea4c07c911537f5ba6aeaa582d3ea18a7f10eba11c1c7f2387f5844254c')

    demo_jars = sorted(DEMO.glob('*.jar'))
    ok('K10_demo_jars', len(demo_jars) == 5)
    for f in demo_jars:
        try:
            ok('K11_scan_' + f.name, len(m.scan_jar(str(f))) > 0)
        except Exception:
            ok('K11_scan_' + f.name, False)

    agg_mod = m.aggregate(m.scan_jar(str(DEMO / 'mod-1.20.1.jar')))
    ok('K12_mod_own', 'demo/MyMod' in agg_mod['own'])
    ok('K13_mod_object', 'java/lang/Object' in agg_mod['occurrences'])
    ok('K14_blindspot', 'java/lang/Object' not in owners)
    agg_rt = m.aggregate(m.scan_jar(str(DEMO / 'mcport-runtime.jar')))
    ok('K15_runtime_array', agg_rt['array_occurrences'] >= 1)
    ok('K16_runtime_external', 'java/lang/Object' in agg_rt['occurrences'])
    ok('K17_no_game_ticket_claim', m.DISCLAIMER.startswith('does NOT mean runtime-compatible'))

print('RESULT ALL_OK assertions=' + str(COUNT))
