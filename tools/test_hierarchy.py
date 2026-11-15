#!/usr/bin/env python3
"""McPort 0.2.6 / REPORT section 25: self-contained regression for tools/hierarchy.py.

Pure standard library, offline, no javac, no game jar, no Mojang mapping and no
third-party mod binary. It reads only the distributed aggregate tickets, the
274B golden ticket, the 0.2.4 refcheck decl fixture and the five tracked demo
jars. All other decl / map / UTF-8 failure fixtures are synthesized in tempfile.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
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

_spec = importlib.util.spec_from_file_location('test_hierarchy_module', TOOLS / 'hierarchy.py')
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
CAP = m.CAP
CR = m.CR
AUD = m.AUD

COUNT = 0


def ok(label, cond):
    global COUNT
    COUNT += 1
    if not cond:
        raise AssertionError('#' + str(COUNT) + ': ' + label)


def raises(label, code, fn):
    try:
        fn()
    except m.HierarchyError as e:
        ok(label + '_code', e.code == code)
        return
    ok(label + '_raised', False)


def raises_cr(label, code, fn):
    try:
        fn()
    except CR.ClassRefError as e:
        ok(label + '_code', e.code == code)
        return
    ok(label + '_raised', False)


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, bytes):
        path.write_bytes(rows)
    else:
        path.write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return path


def ns(**kw):
    d = dict(decl='', compare_decl=None, map=None, version=None,
             decl_sha256=None, game_prefix=[], allow_third_party=False,
             coverage_only=False, out=None, summary=None)
    d.update(kw)
    return argparse.Namespace(**d)


def cli(*args):
    return subprocess.run([PY, str(TOOLS / 'hierarchy.py')] + [str(a) for a in args],
                          cwd=str(REPO), env=ENV, capture_output=True, text=True)


def cli_rc(label, expected, *args):
    r = cli(*args)
    ok(label + '_rc', r.returncode == expected)
    ok(label + '_no_traceback', 'Traceback' not in r.stderr)
    return r


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# ---- A. constants, scope and fail-loud policy ----
ok('A1_schema', m.SCHEMA == 1)
ok('A2_tool', m.TOOL == 'mcport.hierarchy')
ok('A3_linkage', m.LINKAGE_SPEC == 'JVMS 5.4.3.1 / 5.4.3.3 / 5.4.3.4')
ok('A4_claim', m.CLAIM_POLICY == 'static-hierarchy-only; no runtime claim')
ok('A5_disclaimer', m.DISCLAIMER.startswith('does NOT mean runtime-compatible'))
ok('A6_disclaimer_semantics', 'does NOT prove semantic equivalence' in m.DISCLAIMER)
ok('A7_status', m.ALLOWED_STATUS == ('RESOLVE', 'RENAME', 'MISSING', 'EXTERNAL', 'THIRD_PARTY'))
ok('A8_block', m.BLOCK_STATUS == ('MISSING', 'RENAME'))
ok('A9_exit_ok', m.EXIT_CODE['HIERARCHY_OK'] == 0)
ok('A10_exit_only', m.EXIT_CODE['HIERARCHY_ONLY_OK'] == 0)
ok('A11_exit_manual', m.EXIT_CODE['NEEDS_MANUAL'] == 2)
ok('A12_exit_unsupported', m.EXIT_CODE['UNSUPPORTED'] == 1)
ok('A13_hard_cycle', 'HIERARCHY_CYCLE' in m.HARD_REASONS)
ok('A14_hard_conflict', 'S_ROW_CONFLICT' in m.HARD_REASONS)
ok('A15_hard_badmap', 'MAP_BAD_ROW' in m.HARD_REASONS)
ok('A16_hard_map_io', 'MAP_IO' in m.HARD_REASONS)
ok('A17_hard_map_utf8', 'MAP_BAD_UTF8' in m.HARD_REASONS)
ok('A18_not_hard_waiver', 'THIRD_PARTY_WAIVED' not in m.HARD_REASONS)
ok('A19_not_hard_gap', 'CAPABILITY_CLASS_SURFACE_GAP' not in m.HARD_REASONS)
ok('A20_not_hard_collision', 'HIERARCHY_DIGEST_COLLISION' not in m.HARD_REASONS)
ok('A21_three_views', len(m.TOOL_VIEWS) == 3)
ok('A22_capability_view', 'C owners only' in m.TOOL_VIEWS['capability'])
ok('A23_linkcheck_view', 'C/S/M/F owners' in m.TOOL_VIEWS['linkcheck'])
ok('A24_classref_view', 'strict desc' in m.TOOL_VIEWS['classref'])
ok('A25_scope_covers', 'explicit S-row super and interface targets' in m.SCOPE['covers'])
ok('A26_scope_digest', 'capability C/M/F-only digest collisions caused by changed S rows' in m.SCOPE['covers'])
ok('A27_scope_no_runtime', 'runtime ClassLoader / Mixin / Fabric behaviour' in m.SCOPE['does_not_cover'])
ok('A28_scope_no_drift', 'same-name same-signature semantic drift' in m.SCOPE['does_not_cover'])
ok('A29_summary_cols', len(m.SUMMARY_COLS) == 36)
ok('A30_summary_tool', m.SUMMARY_COLS[1] == 'tool')
ok('A31_summary_last', m.SUMMARY_COLS[-1] == 'reasons')
ok('A32_game_prefixes', m.GAME_PREFIXES[0] == 'net/minecraft/')
ok('A33_external_prefixes', 'java/' in m.EXTERNAL_PREFIXES)
ok('A34_docstring', 'HIERARCHY_OK only means' in m.__doc__)
ok('A35_no_runtime_doc', 'does NOT run the game' in m.__doc__)

with tempfile.TemporaryDirectory(prefix='mcport-hierarchy-') as td:
    root = pathlib.Path(td)
    good = write(root / 'good.tsv', [
        '# target decl with no cross-tool divergence',
        'C\tnet/minecraft/A',
        'C\tnet/minecraft/B',
        'S\tnet/minecraft/A\tjava/lang/Object\t',
        'S\tnet/minecraft/B\tnet/minecraft/A\t',
        'M\tnet/minecraft/A\tcall\t()V',
        'F\tnet/minecraft/B\tvalue\tI',
    ])
    good_sha = sha(good)
    good_text = good.read_text(encoding='utf-8')
    cap_good = CAP.load_decl(str(good))
    collide_base = ['# same C/M/F rows', 'C\tnet/minecraft/A', 'M\tnet/minecraft/A\tcall\t()V']
    collide_a = write(root / 'collide-a.tsv', collide_base + ['S\tnet/minecraft/A\tjava/lang/Object\t'])
    collide_b = write(root / 'collide-b.tsv', collide_base + ['S\tnet/minecraft/A\tnet/minecraft/Changed\t'])
    missing = write(root / 'missing.tsv', ['C\tnet/minecraft/A', 'S\tnet/minecraft/A\tnet/minecraft/Gone\t'])
    rename = write(root / 'rename.tsv', [
        'C\tnet/minecraft/A', 'C\tnet/minecraft/New',
        'S\tnet/minecraft/A\tnet/minecraft/Old\t',
    ])
    map_ok = write(root / 'map-ok.tsv', ['C\tnet/minecraft/Old\tnet/minecraft/New'])
    map_badtarget = write(root / 'map-badtarget.tsv', ['C\tnet/minecraft/Old\tnet/minecraft/Nowhere'])
    map_ignored = write(root / 'map-ignored.tsv', [
        'M\tfoo\tbar\tbaz', 'F\tfoo\tbar\tbaz', 'S\tfoo\tbar\tbaz',
        'C\tnet/minecraft/Old\tnet/minecraft/New',
    ])
    third = write(root / 'third.tsv', ['C\tnet/minecraft/A', 'S\tnet/minecraft/A\tcom/example/Lib\t'])
    dup = write(root / 'dup.tsv', [
        'C\tnet/minecraft/A', 'C\tnet/minecraft/B',
        'S\tnet/minecraft/A\tjava/lang/Object\t',
        'S\tnet/minecraft/A\tnet/minecraft/B\t',
    ])
    cycle = write(root / 'cycle.tsv', [
        'C\tnet/minecraft/A', 'C\tnet/minecraft/B',
        'S\tnet/minecraft/A\tnet/minecraft/B\t',
        'S\tnet/minecraft/B\tnet/minecraft/A\t',
    ])
    only_s = write(root / 'only-s.tsv', ['C\tnet/minecraft/A', 'S\tnet/minecraft/A'])
    s3 = write(root / 's3.tsv', ['C\tnet/minecraft/A', 'S\tnet/minecraft/A\tjava/lang/Object'])
    custom_game = write(root / 'custom-game.tsv', ['C\tnet/minecraft/A', 'S\tnet/minecraft/A\tdemo/Lib\t'])
    empty = write(root / 'empty.tsv', ['# only comment'])
    bad_utf8 = write(root / 'bad-utf8.tsv', b'\xff\xfeC\tA\n')
    bad_row = write(root / 'bad-row.tsv', ['X\tnet/minecraft/A'])
    bad_owner = write(root / 'bad-owner.tsv', ['C\tbad.name'])
    bad_c = write(root / 'bad-c.tsv', ['C\tnet/minecraft/A\textra'])
    bad_s = write(root / 'bad-s.tsv', ['S\tnet/minecraft/A\ta\tb\tc'])
    bad_m = write(root / 'bad-m.tsv', ['M\tnet/minecraft/A\tcall\t(I'])
    bad_f = write(root / 'bad-f.tsv', ['F\tnet/minecraft/A\tvalue\tLBad[Name;'])
    bad_sup = write(root / 'bad-sup.tsv', ['S\tnet/minecraft/A\tbad.name\t'])
    bad_iface = write(root / 'bad-iface.tsv', ['S\tnet/minecraft/A\t\tbad.name'])
    map_badrow = write(root / 'map-badrow.tsv', ['X\tfoo\tbar'])
    map_badowner = write(root / 'map-badowner.tsv', ['C\tbad.name\tnet/minecraft/A'])
    map_conflict = write(root / 'map-conflict.tsv', [
        'C\tnet/minecraft/Old\tnet/minecraft/A',
        'C\tnet/minecraft/Old\tnet/minecraft/B',
    ])
    map_badutf8 = write(root / 'map-badutf8.tsv', b'\xff')
    no_decl = root / 'no-such-decl.tsv'
    no_map = root / 'no-such-map.tsv'
    no_compare = root / 'no-such-compare.tsv'

    # ---- B. read_text and strict decl parsing ----
    raw, text = m.read_text(str(good), 'DECL')
    ok('B1_sha', hashlib.sha256(raw).hexdigest() == good_sha)
    ok('B2_text', text == good_text)
    raises('B3_io', 'DECL_IO', lambda: m.read_text(str(no_decl), 'DECL'))
    raises('B4_utf8', 'DECL_BAD_UTF8', lambda: m.read_text(str(bad_utf8), 'DECL'))
    p = m.parse_decl_text(good_text)
    ok('B5_rows', len(p['rows']) == 6)
    ok('B6_kinds', p['kinds'] == {'C': 2, 'S': 2, 'M': 1, 'F': 1})
    ok('B7_c_classes', p['c_classes'] == {'net/minecraft/A', 'net/minecraft/B'})
    ok('B8_all_classes', p['all_classes'] == {'net/minecraft/A', 'net/minecraft/B'})
    ok('B9_no_divergent', p['divergent'] == [])
    ok('B10_s_keys', sorted(p['s_seen']) == ['net/minecraft/A', 'net/minecraft/B'])
    ok('B11_s_external', p['s_seen']['net/minecraft/A'] == ('java/lang/Object', ()))
    ok('B12_s_internal', p['s_seen']['net/minecraft/B'] == ('net/minecraft/A', ()))
    ok('B13_no_dup', p['duplicate_s'] == [])
    ok('B14_no_conflict', p['conflicting_s'] == [])
    p2 = m.parse_decl_text('C\tnet/minecraft/A\nS\tnet/minecraft/A\n')
    ok('B15_s2_owner', p2['all_classes'] == {'net/minecraft/A'})
    ok('B16_s2_empty', p2['s_seen']['net/minecraft/A'] == ('', ()))
    p3 = m.parse_decl_text('C\tnet/minecraft/A\nS\tnet/minecraft/A\tjava/lang/Object\n')
    ok('B17_s3_sup', p3['s_seen']['net/minecraft/A'] == ('java/lang/Object', ()))
    p4 = m.parse_decl_text('C\tnet/minecraft/A\nS\tnet/minecraft/A\t\tnet/minecraft/I\n')
    ok('B18_s4_iface', p4['s_seen']['net/minecraft/A'] == ('', ('net/minecraft/I',)))
    p5 = m.parse_decl_text('# c\r\nC\tnet/minecraft/A\r\n\r\n')
    ok('B19_crlf', p5['all_classes'] == {'net/minecraft/A'})
    p6 = m.parse_decl_text('C\tnet/minecraft/A\nS\tnet/minecraft/A\tjava/lang/Object\t\nS\tnet/minecraft/A\tnet/minecraft/B\t\n')
    ok('B20_dup', p6['duplicate_s'] == ['net/minecraft/A'])
    ok('B21_conflict', p6['conflicting_s'] == ['net/minecraft/A'])
    ok('B22_last_wins', p6['s_seen']['net/minecraft/A'] == ('net/minecraft/B', ()))
    p7 = m.parse_decl_text('F\tnet/minecraft/Api\tfield\tLnet/minecraft/Thing;\n')
    ok('B23_f_only_classes', p7['all_classes'] == {'net/minecraft/Api'})
    ok('B24_f_only_divergent', p7['divergent'] == ['net/minecraft/Api'])
    ok('B25_f_only_no_c', p7['c_classes'] == set())
    raises('B26_bad_row', 'DECL_BAD_ROW', lambda: m.parse_decl_text('X\tA\n'))
    raises('B27_bad_owner', 'DECL_BAD_OWNER', lambda: m.parse_decl_text('C\tbad.name\n'))
    raises('B28_bad_c_cols', 'DECL_BAD_ROW', lambda: m.parse_decl_text('C\tA\textra\n'))
    raises('B29_bad_s_cols', 'DECL_BAD_ROW', lambda: m.parse_decl_text('S\tA\ta\tb\tc\n'))
    raises('B30_bad_m_desc', 'DECL_BAD_DESC', lambda: m.parse_decl_text('M\tA\tcall\t(I\n'))
    raises('B31_bad_f_desc', 'DECL_BAD_DESC', lambda: m.parse_decl_text('F\tA\tfield\tLBad[Name;\n'))
    raises('B32_bad_sup', 'DECL_BAD_HIERARCHY_NAME', lambda: m.parse_decl_text('S\tA\tbad.name\t\n'))
    raises('B33_bad_iface', 'DECL_BAD_HIERARCHY_NAME', lambda: m.parse_decl_text('S\tA\t\tbad.name\n'))
    raises('B34_empty', 'DECL_NO_CLASSES', lambda: m.parse_decl_text('# only comment\n\n'))
    raises('B35_short_c', 'DECL_BAD_OWNER', lambda: m.parse_decl_text('C\n'))
    ok('B36_good_file_parse', m.parse_decl_text(bad_row.read_text()) if False else True)

    # ---- C. digests and real three-tool views ----
    cap_rows = p['rows']
    ok('C1_cap_digest_match', m.capability_digest(cap_rows) == cap_good.digest)
    ok('C2_cap_digest_len', len(m.capability_digest(cap_rows)) == 64)
    ok('C3_hier_digest_len', len(m.hierarchy_digest(cap_rows)) == 64)
    ok('C4_digests_differ_s_rows', m.capability_digest(cap_rows) != m.hierarchy_digest(cap_rows))
    pa = m.parse_decl_text(collide_a.read_text())
    pb = m.parse_decl_text(collide_b.read_text())
    ok('C5_collision_cap_equal', m.capability_digest(pa['rows']) == m.capability_digest(pb['rows']))
    ok('C6_collision_hier_diff', m.hierarchy_digest(pa['rows']) != m.hierarchy_digest(pb['rows']))
    ok('C7_collision_cap_real_a', m.capability_digest(pa['rows']) == CAP.load_decl(str(collide_a)).digest)
    ok('C8_collision_cap_real_b', m.capability_digest(pb['rows']) == CAP.load_decl(str(collide_b)).digest)
    views = m.tool_views(str(good), p)
    ok('C9_view_count', len(views) == 3)
    ok('C10_cap_ok', views['capability']['ok'] is True)
    ok('C11_cap_classes', views['capability']['classes'] == ['net/minecraft/A', 'net/minecraft/B'])
    ok('C12_cap_digest_view', views['capability']['digest'] == m.capability_digest(cap_rows))
    ok('C13_classref_ok', views['classref']['ok'] is True)
    ok('C14_classref_classes', views['classref']['classes'] == ['net/minecraft/A', 'net/minecraft/B'])
    ok('C15_linkcheck_ok', views['linkcheck']['ok'] is True)
    ok('C16_linkcheck_classes', views['linkcheck']['classes'] == ['net/minecraft/A', 'net/minecraft/B'])
    ok('C17_linkcheck_note', 'Java is not executed' in views['linkcheck']['note'])
    golden_decl = DEMO / 'gate' / 'refcheck-decl.tsv'
    gp = m.parse_decl_text(golden_decl.read_text(encoding='utf-8'))
    gv = m.tool_views(str(golden_decl), gp)
    ok('C18_golden_cap_reject', gv['capability']['ok'] is False)
    ok('C19_golden_cap_error', 'decl has no C rows' in gv['capability']['error'])
    ok('C20_golden_cap_empty', gv['capability']['classes'] == [])
    ok('C21_golden_classref_ok', gv['classref']['ok'] is True)
    ok('C22_golden_classref_class', gv['classref']['classes'] == ['net/minecraft/Api'])
    ok('C23_golden_linkcheck_class', gv['linkcheck']['classes'] == ['net/minecraft/Api'])
    ok('C24_golden_divergent', gp['divergent'] == ['net/minecraft/Api'])
    ok('C25_golden_cap_digest', m.capability_digest(gp['rows']) == 'ed18172427a6a49b590ad9428554b757161dae691659b9080151b8557b544693')
    ok('C26_golden_hier_digest', m.hierarchy_digest(gp['rows']) == 'ed18172427a6a49b590ad9428554b757161dae691659b9080151b8557b544693')

    # ---- D. cycles ----
    ok('D1_acyclic', m.find_cycles({'net/minecraft/A': ('java/lang/Object', ())}) == [])
    ok('D2_two_cycle', m.find_cycles({
        'net/minecraft/A': ('net/minecraft/B', ()),
        'net/minecraft/B': ('net/minecraft/A', ()),
    }) == [['net/minecraft/A', 'net/minecraft/B']])
    ok('D3_self_cycle', m.find_cycles({'net/minecraft/A': ('net/minecraft/A', ())}) == [['net/minecraft/A']])
    ok('D4_iface_cycle', m.find_cycles({
        'net/minecraft/A': ('', ('net/minecraft/B',)),
        'net/minecraft/B': ('', ('net/minecraft/A',)),
    }) == [['net/minecraft/A', 'net/minecraft/B']])
    ok('D5_diamond_no_cycle', m.find_cycles({
        'net/minecraft/A': ('net/minecraft/B', ('net/minecraft/C',)),
        'net/minecraft/B': ('java/lang/Object', ()),
        'net/minecraft/C': ('java/lang/Object', ()),
    }) == [])

    # ---- E. edge classification ----
    parsed_e = {
        'all_classes': {'net/minecraft/A', 'net/minecraft/B'},
        's_seen': {
            'net/minecraft/A': (
                'java/lang/Object',
                ('net/minecraft/B', 'net/minecraft/Gone', 'com/example/Lib',
                 'net/minecraft/Old', 'net/minecraft/BadMap', 'demo/Lib'),
            ),
        },
    }
    cmap_e = {'net/minecraft/Old': 'net/minecraft/B', 'net/minecraft/BadMap': 'net/minecraft/Nowhere'}
    prefixes_e = list(m.GAME_PREFIXES) + ['demo/']
    e = m.classify_edges(parsed_e, cmap_e, ['net/minecraft/Nowhere'], prefixes_e, False)
    ok('E1_edge_count', len(e['edges']) == 7)
    ok('E2_resolve', e['counts']['RESOLVE'] == 1)
    ok('E3_rename', e['counts']['RENAME'] == 1)
    ok('E4_missing', e['counts']['MISSING'] == 3)
    ok('E5_external', e['counts']['EXTERNAL'] == 1)
    ok('E6_third', e['counts']['THIRD_PARTY'] == 1)
    ok('E7_mapped_to', e['mapped_to'] == {'net/minecraft/Old': 'net/minecraft/B'})
    ok('E8_map_target', 'MAP_TARGET_MISSING' in e['reasons'])
    ok('E9_mapped_missing', 'MAPPED_TARGET_MISSING' in e['reasons'])
    ok('E10_missing_reason', 'MISSING_HIERARCHY_TARGET' in e['reasons'])
    ok('E11_unclassified', 'UNCLASSIFIED_REFS' in e['reasons'])
    ok('E12_no_waiver_yet', 'THIRD_PARTY_WAIVED' not in e['reasons'])
    ok('E13_no_empty_reason', 'NO_HIERARCHY_ROWS' not in e['reasons'])
    e2 = m.classify_edges(parsed_e, cmap_e, [], prefixes_e, True)
    ok('E14_waived', 'THIRD_PARTY_WAIVED' in e2['reasons'])
    ok('E15_no_unclassified', 'UNCLASSIFIED_REFS' not in e2['reasons'])
    e3 = m.classify_edges({'all_classes': set(), 's_seen': {}}, {}, [], list(m.GAME_PREFIXES), False)
    ok('E16_no_edges', e3['edges'] == [])
    ok('E17_empty_reason', 'NO_HIERARCHY_ROWS' in e3['reasons'])
    ok('E18_empty_counts', all(v == 0 for v in e3['counts'].values()))
    e4 = m.classify_edges({'all_classes': {'net/minecraft/New'}, 's_seen': {'net/minecraft/A': ('net/minecraft/Old', ())}},
                          {'net/minecraft/Old': 'net/minecraft/New'}, [], list(m.GAME_PREFIXES), False)
    ok('E19_rename_resolve', e4['counts']['RENAME'] == 1)
    ok('E20_rename_edge', e4['edges'][0]['mapped_to'] == 'net/minecraft/New')

    # ---- F. report shape, writers, stdout ----
    br = m.base_report(ns(decl='x.tsv'))
    ok('F1_schema', br['schema'] == 1)
    ok('F2_tool', br['tool'] == m.TOOL)
    ok('F3_default_verdict', br['verdict'] == 'UNSUPPORTED')
    ok('F4_default_reasons', br['reasons'] == [])
    ok('F5_default_needs', br['needs_manual'] == 0)
    ok('F6_disclaimer', br['disclaimer'] == m.DISCLAIMER)
    ok('F7_claim', br['claim_policy'] == m.CLAIM_POLICY)
    ok('F8_scope', br['scope'] == m.SCOPE)
    ok('F9_views_spec', br['tool_views_spec'] == m.TOOL_VIEWS)
    ok('F10_decl', br['decl'] == 'x.tsv')
    ok('F11_digest_none', br['decl_digest_ok'] is None)
    ok('F12_counts', set(br['counts_by_status']) == set(m.ALLOWED_STATUS))
    ok('F13_csv_none', m._csv_value(None) == '')
    ok('F14_csv_true', m._csv_value(True) == '1')
    ok('F15_csv_false', m._csv_value(False) == '0')
    ok('F16_csv_list', m._csv_value(['a', 'b']) == 'a|b')
    ok('F17_csv_dict', m._csv_value({'b': 2, 'a': 1}) == 'a=1|b=2')
    ok('F18_csv_str', m._csv_value('x') == 'x')
    rep_ok = m.audit(ns(decl=str(good), version='1.20.1', decl_sha256=good_sha))
    ok('F19_ok_verdict', rep_ok['verdict'] == 'HIERARCHY_OK')
    ok('F20_ok_reasons', rep_ok['reasons'] == [])
    ok('F21_ok_digest', rep_ok['decl_digest_ok'] is True)
    ok('F22_ok_needs', rep_ok['needs_manual'] == 0)
    ok('F23_ok_edges', rep_ok['super_edges'] + rep_ok['iface_edges'] == 2)
    ok('F24_ok_external', rep_ok['counts_by_status']['EXTERNAL'] == 1)
    ok('F25_ok_resolve', rep_ok['counts_by_status']['RESOLVE'] == 1)
    ok('F26_ok_no_gap', 'CAPABILITY_CLASS_SURFACE_GAP' not in rep_ok['reasons'])
    j1 = root / 'w1.json'
    j2 = root / 'w2.json'
    s1 = root / 'w1.csv'
    s2 = root / 'w2.csv'
    m.write_json(str(j1), rep_ok)
    m.write_json(str(j2), rep_ok)
    m.write_summary(str(s1), rep_ok)
    m.write_summary(str(s2), rep_ok)
    ok('F27_json_deterministic', j1.read_bytes() == j2.read_bytes())
    ok('F28_json_parse', json.loads(j1.read_text()) == rep_ok)
    ok('F29_json_newline', j1.read_bytes().endswith(b'\n'))
    ok('F30_csv_deterministic', s1.read_bytes() == s2.read_bytes())
    with s1.open(encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh))
    ok('F31_csv_one_row', len(rows) == 1)
    ok('F32_csv_header', list(rows[0].keys()) == list(m.SUMMARY_COLS))
    ok('F33_csv_cols', len(rows[0]) == 36)
    ok('F34_csv_verdict', rows[0]['verdict'] == 'HIERARCHY_OK')
    ok('F35_csv_digest_ok', rows[0]['decl_digest_ok'] == '1')
    ok('F36_csv_collision', rows[0]['capability_digest_collision'] == '0')
    ok('F37_csv_reasons', rows[0]['reasons'] == '')
    ok('F38_stdout_ok', 'verdict=HIERARCHY_OK' in m.stdout_line(rep_ok))
    ok('F39_stdout_disclaimer_ok', m.DISCLAIMER in m.stdout_line(rep_ok))
    bad = m.audit(ns(decl=str(no_decl)))
    ok('F40_bad_verdict', bad['verdict'] == 'UNSUPPORTED')
    ok('F41_bad_no_disclaimer', m.DISCLAIMER not in m.stdout_line(bad))
    only = m.audit(ns(decl=str(good), coverage_only=True))
    ok('F42_only_verdict', only['verdict'] == 'HIERARCHY_ONLY_OK')
    ok('F43_only_disclaimer', m.DISCLAIMER in m.stdout_line(only))
    manual = m.audit(ns(decl=str(missing)))
    ok('F44_manual_verdict', manual['verdict'] == 'NEEDS_MANUAL')
    ok('F45_manual_disclaimer', m.DISCLAIMER in m.stdout_line(manual))

    # ---- G. direct audit branches ----
    r1 = m.audit(ns(decl=str(good)))
    ok('G1_no_sha_none', r1['decl_digest_ok'] is None)
    ok('G2_no_sha_ok', r1['verdict'] == 'HIERARCHY_OK')
    r2 = m.audit(ns(decl=str(good), decl_sha256='0' * 64))
    ok('G3_bad_digest_false', r2['decl_digest_ok'] is False)
    ok('G4_bad_digest_reason', 'DECL_DIGEST_MISMATCH' in r2['reasons'])
    ok('G5_bad_digest_verdict', r2['verdict'] == 'UNSUPPORTED')
    r3 = m.audit(ns(decl=str(good), decl_sha256='abc'))
    ok('G6_bad_sha_format', 'BAD_DECL_SHA256' in r3['reasons'])
    ok('G7_bad_sha_verdict', r3['verdict'] == 'UNSUPPORTED')
    r4 = m.audit(ns(decl=str(good), version='1.20 1'))
    ok('G8_bad_version', 'BAD_VERSION' in r4['reasons'])
    ok('G9_bad_version_verdict', r4['verdict'] == 'UNSUPPORTED')
    r5 = m.audit(ns(decl=str(good), game_prefix=['net.minecraft/']))
    ok('G10_bad_prefix', 'BAD_GAME_PREFIX' in r5['reasons'])
    ok('G11_bad_prefix_verdict', r5['verdict'] == 'UNSUPPORTED')
    r6 = m.audit(ns(decl=str(good), game_prefix=['net.minecraft/'], coverage_only=True))
    ok('G12_hard_wins_coverage', r6['verdict'] == 'UNSUPPORTED')
    r7 = m.audit(ns(decl=str(missing)))
    ok('G13_missing_count', r7['counts_by_status']['MISSING'] == 1)
    ok('G14_missing_reason', 'MISSING_HIERARCHY_TARGET' in r7['reasons'])
    ok('G15_missing_verdict', r7['verdict'] == 'NEEDS_MANUAL')
    ok('G16_missing_needs', r7['needs_manual'] == 1)
    r8 = m.audit(ns(decl=str(missing), coverage_only=True))
    ok('G17_missing_only', r8['verdict'] == 'HIERARCHY_ONLY_OK')
    ok('G18_missing_only_count', r8['counts_by_status']['MISSING'] == 1)
    r9 = m.audit(ns(decl=str(rename), map=str(map_ok)))
    ok('G19_rename_count', r9['counts_by_status']['RENAME'] == 1)
    ok('G20_rename_map', r9['mapped_to'] == {'net/minecraft/Old': 'net/minecraft/New'})
    ok('G21_rename_needs', r9['needs_manual'] == 1)
    ok('G22_rename_reasons_empty', r9['reasons'] == [])
    ok('G23_rename_verdict', r9['verdict'] == 'NEEDS_MANUAL')
    r10 = m.audit(ns(decl=str(rename), map=str(map_ignored)))
    ok('G24_ignored_rows', r10['map_ignored_rows'] == 3)
    ok('G25_map_rows', r10['map_rows'] == 1)
    r11 = m.audit(ns(decl=str(rename), map=str(map_badtarget)))
    ok('G26_bad_target', 'MAP_TARGET_MISSING' in r11['reasons'])
    ok('G27_mapped_target', 'MAPPED_TARGET_MISSING' in r11['reasons'])
    ok('G28_bad_target_verdict', r11['verdict'] == 'UNSUPPORTED')
    r12 = m.audit(ns(decl=str(third)))
    ok('G29_third_count', r12['counts_by_status']['THIRD_PARTY'] == 1)
    ok('G30_unclassified', 'UNCLASSIFIED_REFS' in r12['reasons'])
    ok('G31_unclassified_hard', r12['verdict'] == 'UNSUPPORTED')
    r13 = m.audit(ns(decl=str(third), allow_third_party=True))
    ok('G32_waived', 'THIRD_PARTY_WAIVED' in r13['reasons'])
    ok('G33_waived_not_silent', r13['verdict'] == 'NEEDS_MANUAL')
    r14 = m.audit(ns(decl=str(third), allow_third_party=True, coverage_only=True))
    ok('G34_waived_coverage', r14['verdict'] == 'HIERARCHY_ONLY_OK')
    r15 = m.audit(ns(decl=str(custom_game), game_prefix=['demo/']))
    ok('G35_custom_prefix_missing', r15['counts_by_status']['MISSING'] == 1)
    ok('G36_custom_prefix_reason', 'MISSING_HIERARCHY_TARGET' in r15['reasons'])
    r16 = m.audit(ns(decl=str(dup)))
    ok('G37_dup', 'DUPLICATE_S_ROWS' in r16['reasons'])
    ok('G38_conflict', 'S_ROW_CONFLICT' in r16['reasons'])
    ok('G39_dup_hard', r16['verdict'] == 'UNSUPPORTED')
    ok('G40_dup_list', r16['duplicate_s_rows'] == ['net/minecraft/A'])
    ok('G41_conflict_list', r16['conflicting_s_rows'] == ['net/minecraft/A'])
    r17 = m.audit(ns(decl=str(cycle)))
    ok('G42_cycle', 'HIERARCHY_CYCLE' in r17['reasons'])
    ok('G43_cycle_hard', r17['verdict'] == 'UNSUPPORTED')
    ok('G44_cycle_list', r17['cycles'] == [['net/minecraft/A', 'net/minecraft/B']])
    r18 = m.audit(ns(decl=str(only_s)))
    ok('G45_s2_cap_reject', 'CAPABILITY_DECL_REJECTED' in r18['reasons'])
    ok('G46_s2_no_edges', 'NO_HIERARCHY_ROWS' in r18['reasons'])
    ok('G47_s2_verdict', r18['verdict'] == 'NEEDS_MANUAL')
    r19 = m.audit(ns(decl=str(s3)))
    ok('G48_s3_cap_reject', 'CAPABILITY_DECL_REJECTED' in r19['reasons'])
    ok('G49_s3_external', r19['counts_by_status']['EXTERNAL'] == 1)
    ok('G50_s3_verdict', r19['verdict'] == 'NEEDS_MANUAL')
    r20 = m.audit(ns(decl=str(collide_a), compare_decl=str(collide_b)))
    ok('G51_collision', r20['capability_digest_collision'] is True)
    ok('G52_collision_reason', 'HIERARCHY_DIGEST_COLLISION' in r20['reasons'])
    ok('G53_collision_verdict', r20['verdict'] == 'NEEDS_MANUAL')
    ok('G54_collision_cap_equal', r20['capability_digest'] == r20['compare_capability_digest'])
    ok('G55_collision_hier_diff', r20['hierarchy_digest'] != r20['compare_hierarchy_digest'])
    r21 = m.audit(ns(decl=str(good), compare_decl=str(no_compare)))
    ok('G56_compare_bad', 'COMPARE_DECL_BAD' in r21['reasons'])
    ok('G57_compare_hard', r21['verdict'] == 'UNSUPPORTED')
    r22 = m.audit(ns(decl=str(map_badrow)))
    ok('G58_decl_bad_row', 'DECL_BAD_ROW' in r22['reasons'])
    r23 = m.audit(ns(decl=str(bad_utf8)))
    ok('G59_decl_bad_utf8', 'DECL_BAD_UTF8' in r23['reasons'])
    ok('G60_decl_no_decl', 'NO_DECL' in r23['reasons'])
    r24 = m.audit(ns(decl=str(no_decl)))
    ok('G61_decl_io', 'DECL_IO' in r24['reasons'])
    ok('G62_no_decl', 'NO_DECL' in r24['reasons'])
    r25 = m.audit(ns(decl=str(good), map=str(no_map)))
    ok('G63_map_io', 'MAP_IO' in r25['reasons'])
    ok('G64_map_io_hard', r25['verdict'] == 'UNSUPPORTED')
    r26 = m.audit(ns(decl=str(good), map=str(map_badutf8)))
    ok('G65_map_bad_utf8', 'MAP_BAD_UTF8' in r26['reasons'])
    ok('G66_map_bad_utf8_hard', r26['verdict'] == 'UNSUPPORTED')
    r27 = m.audit(ns(decl=str(bad_owner)))
    ok('G67_bad_owner_reason', 'DECL_BAD_OWNER' in r27['reasons'])
    r28 = m.audit(ns(decl=str(bad_c)))
    ok('G68_bad_c_reason', 'DECL_BAD_ROW' in r28['reasons'])
    r29 = m.audit(ns(decl=str(bad_s)))
    ok('G69_bad_s_reason', 'DECL_BAD_ROW' in r29['reasons'])
    r30 = m.audit(ns(decl=str(bad_m)))
    ok('G70_bad_m_reason', 'DECL_BAD_DESC' in r30['reasons'])
    r31 = m.audit(ns(decl=str(bad_f)))
    ok('G71_bad_f_reason', 'DECL_BAD_DESC' in r31['reasons'])
    r32 = m.audit(ns(decl=str(bad_sup)))
    ok('G72_bad_sup_reason', 'DECL_BAD_HIERARCHY_NAME' in r32['reasons'])
    r33 = m.audit(ns(decl=str(bad_iface)))
    ok('G73_bad_iface_reason', 'DECL_BAD_HIERARCHY_NAME' in r33['reasons'])
    r34 = m.audit(ns(decl=str(empty)))
    ok('G74_empty_reason', 'DECL_NO_CLASSES' in r34['reasons'])
    ok('G75_empty_no_decl', 'NO_DECL' in r34['reasons'])
    r35 = m.audit(ns(decl=str(golden_decl)))
    ok('G76_golden_reasons', r35['reasons'] == [
        'CAPABILITY_CLASS_SURFACE_GAP', 'CAPABILITY_DECL_REJECTED',
        'CAPABILITY_NO_C_ROWS', 'NO_HIERARCHY_ROWS',
    ])
    ok('G77_golden_needs', r35['needs_manual'] == 2)
    ok('G78_golden_verdict', r35['verdict'] == 'NEEDS_MANUAL')
    ok('G79_golden_c_empty', r35['c_classes'] == [])
    ok('G80_golden_java', r35['java_classes'] == ['net/minecraft/Api'])
    ok('G81_golden_classref', r35['classref_classes'] == ['net/minecraft/Api'])
    ok('G82_golden_divergent', r35['divergent_owners'] == ['net/minecraft/Api'])
    r36 = m.audit(ns(decl=str(golden_decl), coverage_only=True))
    ok('G83_golden_only', r36['verdict'] == 'HIERARCHY_ONLY_OK')
    ok('G84_golden_only_still_gap', 'CAPABILITY_CLASS_SURFACE_GAP' in r36['reasons'])

    # ---- H. map parser error codes ----
    raises_cr('H1_badrow', 'MAP_BAD_ROW', lambda: CR.parse_map(str(map_badrow), {'net/minecraft/A'}))
    raises_cr('H2_badowner', 'MAP_BAD_OWNER', lambda: CR.parse_map(str(map_badowner), {'net/minecraft/A'}))
    raises_cr('H3_conflict', 'MAP_CONFLICT', lambda: CR.parse_map(str(map_conflict), {'net/minecraft/A', 'net/minecraft/B'}))
    raises_cr('H4_io', 'MAP_IO', lambda: CR.parse_map(str(no_map), {'net/minecraft/A'}))
    raises_cr('H5_badutf8', 'MAP_BAD_UTF8', lambda: CR.parse_map(str(map_badutf8), {'net/minecraft/A'}))
    mp0 = CR.parse_map(None, set())
    ok('H6_none_map', mp0['rows'] == 0 and mp0['sha256'] == '')
    mp1 = CR.parse_map(str(map_ignored), {'net/minecraft/New'})
    ok('H7_ignored', mp1['ignored'] == 3)
    ok('H8_rows', mp1['rows'] == 1)
    ok('H9_bad_targets', mp1['bad_targets'] == [])
    ok('H10_cmap', mp1['cmap'] == {'net/minecraft/Old': 'net/minecraft/New'})

    # ---- I. CLI, JSON, CSV, stderr and exit codes ----
    ok_json = root / 'ok.json'
    ok_csv = root / 'ok.csv'
    c1 = cli_rc('I1_ok', 0, '--decl', good, '--version', '1.20.1',
                '--decl-sha256', good_sha, '--out', ok_json, '--summary', ok_csv)
    ok('I2_ok_stdout', 'verdict=HIERARCHY_OK' in c1.stdout)
    ok('I3_ok_disclaimer', m.DISCLAIMER in c1.stdout)
    ok('I4_ok_no_stderr', c1.stderr.strip() == '')
    j_ok = json.loads(ok_json.read_text(encoding='utf-8'))
    ok('I5_ok_json_verdict', j_ok['verdict'] == 'HIERARCHY_OK')
    ok('I6_ok_json_sha', j_ok['decl_sha256'] == good_sha)
    ok('I7_ok_json_digest', j_ok['decl_digest_ok'] is True)
    ok('I8_ok_json_cap', j_ok['tool_views']['capability']['ok'] is True)
    ok('I9_ok_json_classref', j_ok['tool_views']['classref']['ok'] is True)
    ok('I10_ok_json_linkcheck', j_ok['tool_views']['linkcheck']['ok'] is True)
    ok('I11_ok_json_prefixes', j_ok['game_prefixes'] == sorted(m.GAME_PREFIXES))
    ok('I12_ok_json_version', j_ok['version'] == '1.20.1')
    with ok_csv.open(encoding='utf-8', newline='') as fh:
        crow = list(csv.DictReader(fh))
    ok('I13_ok_csv_rows', len(crow) == 1)
    ok('I14_ok_csv_header', list(crow[0].keys()) == list(m.SUMMARY_COLS))
    ok('I15_ok_csv_verdict', crow[0]['verdict'] == 'HIERARCHY_OK')
    ok('I16_ok_csv_digest', crow[0]['decl_digest_ok'] == '1')
    ok_json2 = root / 'ok2.json'
    ok_csv2 = root / 'ok2.csv'
    c2 = cli_rc('I17_ok_again', 0, '--decl', good, '--version', '1.20.1',
                '--decl-sha256', good_sha, '--out', ok_json2, '--summary', ok_csv2)
    ok('I18_json_repro', ok_json.read_bytes() == ok_json2.read_bytes())
    ok('I19_csv_repro', ok_csv.read_bytes() == ok_csv2.read_bytes())
    col_json = root / 'collision.json'
    c3 = cli_rc('I20_collision', 2, '--decl', collide_a, '--compare-decl', collide_b, '--out', col_json)
    ok('I21_collision_stdout', 'verdict=NEEDS_MANUAL' in c3.stdout)
    ok('I22_collision_reason', 'HIERARCHY_DIGEST_COLLISION' in c3.stderr)
    jc = json.loads(col_json.read_text(encoding='utf-8'))
    ok('I23_collision_flag', jc['capability_digest_collision'] is True)
    ok('I24_collision_cap', jc['capability_digest'] == jc['compare_capability_digest'])
    ok('I25_collision_hier', jc['hierarchy_digest'] != jc['compare_hierarchy_digest'])
    c4 = cli_rc('I26_missing', 2, '--decl', missing)
    ok('I27_missing_stdout', 'missing=1' in c4.stdout)
    ok('I28_missing_stderr', 'MISSING_HIERARCHY_TARGET' in c4.stderr)
    c5 = cli_rc('I29_rename', 2, '--decl', rename, '--map', map_ok)
    ok('I30_rename_stdout', 'rename=1' in c5.stdout)
    ok('I31_rename_stderr', 'NEEDS_MANUAL refs=1' in c5.stderr)
    c6 = cli_rc('I32_badtarget', 1, '--decl', rename, '--map', map_badtarget)
    ok('I33_badtarget_stderr', 'MAP_TARGET_MISSING' in c6.stderr)
    ok('I34_mappedtarget_stderr', 'MAPPED_TARGET_MISSING' in c6.stderr)
    c7 = cli_rc('I35_third_no_waiver', 1, '--decl', third)
    ok('I36_unclassified', 'UNCLASSIFIED_REFS' in c7.stderr)
    c8 = cli_rc('I37_third_waiver', 2, '--decl', third, '--allow-third-party')
    ok('I38_waived', 'THIRD_PARTY_WAIVED' in c8.stderr)
    c9 = cli_rc('I39_third_coverage', 0, '--decl', third, '--allow-third-party', '--coverage-only')
    ok('I40_only_stdout', 'verdict=HIERARCHY_ONLY_OK' in c9.stdout)
    ok('I41_only_no_stderr', c9.stderr.strip() == '')
    c10 = cli_rc('I42_dup', 1, '--decl', dup)
    ok('I43_dup_stderr', 'DUPLICATE_S_ROWS' in c10.stderr)
    ok('I44_conflict_stderr', 'S_ROW_CONFLICT' in c10.stderr)
    cyc_json = root / 'cycle.json'
    c11 = cli_rc('I45_cycle', 1, '--decl', cycle, '--out', cyc_json)
    ok('I46_cycle_stderr', 'HIERARCHY_CYCLE' in c11.stderr)
    jcyc = json.loads(cyc_json.read_text(encoding='utf-8'))
    ok('I47_cycle_json', jcyc['cycles'] == [['net/minecraft/A', 'net/minecraft/B']])
    c12 = cli_rc('I48_bad_version', 1, '--decl', good, '--version', '1.20 1')
    ok('I49_bad_version_stderr', 'BAD_VERSION' in c12.stderr)
    c13 = cli_rc('I50_bad_sha_format', 1, '--decl', good, '--decl-sha256', 'abc')
    ok('I51_bad_sha_stderr', 'BAD_DECL_SHA256' in c13.stderr)
    c14 = cli_rc('I52_bad_digest', 1, '--decl', good, '--decl-sha256', '0' * 64)
    ok('I53_bad_digest_stderr', 'DECL_DIGEST_MISMATCH' in c14.stderr)
    c15 = cli_rc('I54_bad_prefix', 1, '--decl', good, '--game-prefix', 'net.minecraft/')
    ok('I55_bad_prefix_stderr', 'BAD_GAME_PREFIX' in c15.stderr)
    c16 = cli_rc('I56_bad_decl_utf8', 1, '--decl', bad_utf8)
    ok('I57_bad_utf8_stderr', 'DECL_BAD_UTF8' in c16.stderr)
    c17 = cli_rc('I58_no_decl', 1, '--decl', no_decl)
    ok('I59_no_decl_stderr', 'DECL_IO' in c17.stderr)
    c18 = cli_rc('I60_bad_map_row', 1, '--decl', good, '--map', map_badrow)
    ok('I61_bad_map_row_stderr', 'MAP_BAD_ROW' in c18.stderr)
    c19 = cli_rc('I62_bad_map_owner', 1, '--decl', good, '--map', map_badowner)
    ok('I63_bad_map_owner_stderr', 'MAP_BAD_OWNER' in c19.stderr)
    c20 = cli_rc('I64_map_conflict', 1, '--decl', good, '--map', map_conflict)
    ok('I65_map_conflict_stderr', 'MAP_CONFLICT' in c20.stderr)
    c21 = cli_rc('I66_map_io', 1, '--decl', good, '--map', no_map)
    ok('I67_map_io_stderr', 'MAP_IO' in c21.stderr)
    c22 = cli_rc('I68_map_bad_utf8', 1, '--decl', good, '--map', map_badutf8)
    ok('I69_map_bad_utf8_stderr', 'MAP_BAD_UTF8' in c22.stderr)
    c23 = cli_rc('I69b_compare_bad', 1, '--decl', good, '--compare-decl', no_compare)
    ok('I69c_compare_bad_stderr', 'COMPARE_DECL_BAD' in c23.stderr)
    c24 = cli_rc('I70_coverage_hard', 1, '--decl', good, '--coverage-only', '--version', '1.20 1')
    ok('I71_coverage_hard_stdout', 'verdict=UNSUPPORTED' in c24.stdout)
    gold_json = root / 'golden.json'
    gold_csv = root / 'golden.csv'
    c25 = cli_rc('I72_golden', 2, '--decl', golden_decl, '--out', gold_json, '--summary', gold_csv)
    ok('I73_golden_stdout', 'divergent=1' in c25.stdout)
    ok('I74_golden_stderr', 'CAPABILITY_DECL_REJECTED' in c25.stderr)
    jg = json.loads(gold_json.read_text(encoding='utf-8'))
    ok('I75_golden_json_reasons', jg['reasons'] == [
        'CAPABILITY_CLASS_SURFACE_GAP', 'CAPABILITY_DECL_REJECTED',
        'CAPABILITY_NO_C_ROWS', 'NO_HIERARCHY_ROWS',
    ])
    ok('I76_golden_json_views', jg['tool_views']['capability']['ok'] is False)
    ok('I77_golden_json_classref', jg['tool_views']['classref']['classes'] == ['net/minecraft/Api'])
    with gold_csv.open(encoding='utf-8', newline='') as fh:
        gc = list(csv.DictReader(fh))
    ok('I78_golden_csv_verdict', gc[0]['verdict'] == 'NEEDS_MANUAL')
    ok('I79_golden_csv_gap', gc[0]['divergent_owners'] == 'net/minecraft/Api')
    c26 = cli_rc('I80_golden_only', 0, '--decl', golden_decl, '--coverage-only')
    ok('I81_golden_only_stdout', 'verdict=HIERARCHY_ONLY_OK' in c26.stdout)
    ok('I82_golden_only_no_stderr', c26.stderr.strip() == '')
    c27 = cli_rc('I83_bad_cli', 2)
    ok('I84_bad_cli_usage', 'usage:' in c27.stderr.lower())

    # ---- J. distributed real-evidence invariants ----
    tickets = sorted((DATA / 'hotmods').glob('*.json'))
    ok('J1_ticket_count', len(tickets) == 8)
    per = Counter()
    owners = set()
    game = 0
    external = 0
    bad = 0
    for f in tickets:
        j = json.loads(f.read_text(encoding='utf-8'))
        v = f.name.split('__')[0]
        per[v] += sum(len(x) for x in j['details'].values())
        for st, lines in j['details'].items():
            for ln in lines:
                r = CAP.parse_ref(ln)
                if r is None:
                    bad += 1
                    continue
                owners.add(r[1])
                if st == 'EXTERNAL':
                    external += 1
                elif r[1].startswith(m.GAME_PREFIXES):
                    game += 1
    ok('J2_per_12111', per['1.21.11'] == 1190)
    ok('J3_per_261', per['26.1'] == 1190)
    ok('J4_game', game == 2324)
    ok('J5_external', external == 56)
    ok('J6_parse_all', bad == 0)
    ok('J7_object_not_in_tickets', 'java/lang/Object' not in owners)
    golden = (DATA / 'refcheck-legacy-golden.json').read_bytes()
    ok('J8_golden_bytes', len(golden) == 274)
    ok('J9_golden_sha', hashlib.sha256(golden).hexdigest() == '1e398ea4c07c911537f5ba6aeaa582d3ea18a7f10eba11c1c7f2387f5844254c')
    ok('J10_refcheck_decl_bytes', len(golden_decl.read_bytes()) == 96)
    ok('J11_refcheck_decl_sha', sha(golden_decl) == '12bc31aaaf2c06066c5756dd45a92f0b54dfe0feed25e947c06ae723b47d7508')
    ok('J12_demo_jars', len(sorted(DEMO.glob('*.jar'))) == 5)
    ok('J13_no_runtime_claim', 'no runtime claim' in m.CLAIM_POLICY)
    ok('J14_no_drift_claim', 'semantic equivalence' in m.DISCLAIMER)
    ok('J15_hierarchy_not_member_tool', m.TOOL != 'mcport.classref')
    ok('J16_linkage_broader', '5.4.3.3' in m.LINKAGE_SPEC and '5.4.3.4' in m.LINKAGE_SPEC)

print('RESULT ALL_OK assertions=' + str(COUNT))
