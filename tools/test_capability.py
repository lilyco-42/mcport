#!/usr/bin/env python3
"""§18 自包含回归：零外部数据，只用 tempfile 合成 decl/map/工单/plan/stats。"""

import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'mcport_capability', os.path.join(HERE, 'capability.py'))
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)

COUNT = 0


def ok(cond, msg):
    global COUNT
    if not cond:
        raise AssertionError('assert ' + str(COUNT + 1) + ': ' + msg)
    COUNT += 1


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


def write_json(path, obj):
    return write(path, json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def read_json(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def decl_text(classes, methods, fields, sup):
    lines = ['# synthetic decl']
    for c in sorted(classes):
        lines.append('C\t' + c)
    for owner, name, desc in sorted(methods):
        lines.append('M\t' + owner + '\t' + name + '\t' + desc)
    for owner, name, desc in sorted(fields):
        lines.append('F\t' + owner + '\t' + name + '\t' + desc)
    for owner, parent, ifaces in sorted(sup):
        lines.append('S\t' + owner + '\t' + parent + '\t' + ','.join(ifaces))
    return '\n'.join(lines) + '\n'


def make_decl(root, name='src', classes=None, methods=None, fields=None, sup=None):
    classes = classes or ['net/minecraft/A', 'net/minecraft/B']
    methods = methods or [
        ('net/minecraft/A', 'same', '()V'),
        ('net/minecraft/A', 'renamed', '()V'),
        ('net/minecraft/A', 'sigchg', '()V'),
        ('net/minecraft/A', 'gone', '()V'),
    ]
    fields = fields or [('net/minecraft/A', 'F1', 'I')]
    sup = sup or [('net/minecraft/A', 'java/lang/Object', ())]
    return write(os.path.join(root, name + '.tsv'),
                 decl_text(classes, methods, fields, sup))


def make_ticket(root, name, resolve, rename, sigchg, missing, external=0,
                bad_scalar=False, bad_ref=False):
    details = {}
    def add(bucket, n, prefix):
        arr = []
        for i in range(n):
            arr.append(prefix + str(i) + '()V  # sample')
        details[bucket] = arr
    add('RESOLVE', resolve, 'net/minecraft/class_1.method_')
    add('RENAME', rename, 'net/minecraft/class_1.method_')
    add('SIGCHG', sigchg, 'net/minecraft/class_1.method_')
    add('MISSING', missing, 'net/minecraft/class_1.method_')
    arr = []
    for i in range(external):
        arr.append('com/mojang/authlib/GameProfile.field_' + str(i) +
                   'Ljava/lang/String;  # external')
    details['EXTERNAL'] = arr
    if bad_ref:
        details['RESOLVE'].append('!!!broken-ref')
    total = sum(len(v) for v in details.values())
    obj = {
        'mod': '/tmp/fake-' + name + '.jar',
        'total': total,
        'resolve': resolve,
        'rename': rename,
        'sigchg': sigchg,
        'missing': missing,
        'autoFixCeiling': 100.0,
        'details': details,
    }
    if bad_scalar:
        obj['resolve'] = resolve + 1
    return write_json(os.path.join(root, name + '.json'), obj)


def unit():
    ok(cap.SCHEMA == 1, 'schema')
    ok(cap.ALLOWED_VERDICTS == ('READY', 'NEEDS_MANUAL', 'UNSUPPORTED'),
       'verdict set')
    ok(cap.EXIT_CODE == {'READY': 0, 'NEEDS_MANUAL': 2, 'UNSUPPORTED': 1},
       'exit code mapping')
    ok(cap.worst([]) == 'READY', 'worst empty')
    ok(cap.worst(['READY', 'READY']) == 'READY', 'worst ready')
    ok(cap.worst(['READY', 'NEEDS_MANUAL']) == 'NEEDS_MANUAL', 'worst manual')
    ok(cap.worst(['NEEDS_MANUAL', 'UNSUPPORTED']) == 'UNSUPPORTED', 'worst unsupported')
    ok(cap.worst(['UNSUPPORTED', 'READY']) == 'UNSUPPORTED', 'worst order-free')
    try:
        cap.worst(['COMPATIBLE'])
        ok(False, 'worst rejects unknown')
    except ValueError:
        ok(True, 'worst rejects unknown')

    ok(cap.remap_desc('()V', {}) == '()V', 'remap empty cmap')
    cmap = {'net/minecraft/A': 'net/minecraft/A2',
            'net/minecraft/B': 'net/minecraft/B2'}
    ok(cap.remap_desc('(Lnet/minecraft/A;I)Lnet/minecraft/B;', cmap)
       == '(Lnet/minecraft/A2;I)Lnet/minecraft/B2;', 'remap two tokens')
    ok(cap.remap_desc('(Lnet/minecraft/C;)V', cmap)
       == '(Lnet/minecraft/C;)V', 'remap untouched token')
    ok(cap.remap_desc('[Lnet/minecraft/A;', cmap)
       == '[Lnet/minecraft/A2;', 'remap array token')

    refs = [
        ('M', 'net/minecraft/A.m()V', ('M', 'net/minecraft/A', 'm', '()V')),
        ('M', 'net/minecraft/A.<init>()V',
         ('M', 'net/minecraft/A', '<init>', '()V')),
        ('F', 'net/minecraft/A.fI', ('F', 'net/minecraft/A', 'f', 'I')),
        ('F', 'net/minecraft/A.fLnet/minecraft/B;',
         ('F', 'net/minecraft/A', 'f', 'Lnet/minecraft/B;')),
        ('N', 'net/minecraft/A.m()V  # note',
         ('M', 'net/minecraft/A', 'm', '()V')),
        ('N', 'net/minecraft/A.m()V  -> method_9',
         ('M', 'net/minecraft/A', 'm', '()V')),
        ('N', 'net/minecraft/A.f[Ljava/lang/String;',
         ('F', 'net/minecraft/A', 'f', '[Ljava/lang/String;')),
    ]
    for label, s, expected in refs:
        ok(cap.parse_ref(s) == expected, 'parse_ref ' + label + ' ' + s)
    ok(cap.parse_ref('no-dot-token') is None, 'parse_ref no dot')
    ok(cap.parse_ref('net/minecraft/A.m()Bogus') is None, 'parse_ref bad desc')
    ok(cap.parse_ref('net/minecraft/A.9bad()V') is None, 'parse_ref bad name')
    ok(cap.parse_ref('net/minecraft/A.f') is None, 'parse_ref field no desc')
    ok(cap.parse_ref('net/minecraft/A.<clinit>()V')[2] == '<clinit>',
       'parse_ref clinit')
    # REPORT section 21: strict JVMS 4.3 grammar fixes the silent-pass bug.
    ok(cap.parse_ref('net/minecraft/A.shaderLightDirections[Lorg/joml/Vector3f;')
       == ('F', 'net/minecraft/A', 'shaderLightDirections',
           '[Lorg/joml/Vector3f;'),
       'strict parse_ref rejects impossible L...[L...; descriptor')
    ok(cap.parse_ref('net/minecraft/A.fLx(;') is None,
       'strict parse_ref rejects malformed object descriptor')



def decl_and_map(root):
    src_classes = ['net/minecraft/A', 'net/minecraft/B', 'net/minecraft/Gone']
    src_methods = [
        ('net/minecraft/A', 'same', '()V'),
        ('net/minecraft/A', 'oldName', '(Lnet/minecraft/B;)V'),
        ('net/minecraft/A', 'sig', '()I'),
        ('net/minecraft/A', 'removed', '()V'),
    ]
    src_fields = [('net/minecraft/A', 'field', 'Lnet/minecraft/B;')]
    src = make_decl(root, 'src-decl', src_classes, src_methods, src_fields)
    dsrc = cap.load_decl(src)
    ok(len(dsrc.classes) == 3, 'decl classes')
    ok(len(dsrc.methods) == 4, 'decl methods')
    ok(len(dsrc.fields) == 1, 'decl fields')
    ok(dsrc.supers['net/minecraft/A'] == 'java/lang/Object', 'decl supers')
    ok(dsrc.rows == 3 + 4 + 1 + 1, 'decl rows')
    ok(len(dsrc.digest) == 64, 'decl digest shape')
    ok(cap.load_decl(src).digest == dsrc.digest, 'decl digest stable')

    dst_classes = ['net/minecraft/A', 'net/minecraft/B', 'net/minecraft/New']
    dst_methods = [
        ('net/minecraft/A', 'same', '()V'),
        ('net/minecraft/A', 'newName', '(Lnet/minecraft/B;)V'),
        ('net/minecraft/A', 'sig', '()J'),
        ('net/minecraft/A', 'fresh', '()V'),
    ]
    dst_fields = [('net/minecraft/A', 'field', 'Lnet/minecraft/B;')]
    dst = make_decl(root, 'dst-decl', dst_classes, dst_methods, dst_fields)
    ddst = cap.load_decl(dst)

    map_path = write(os.path.join(root, 'map.tsv'),
        '# strict map\n'
        'M\tnet/minecraft/A\t(Lnet/minecraft/B;)V\toldName\tnewName\n'
        'M\tnet/minecraft/A\t()V\tsame\tsame\n'
        'F\tnet/minecraft/A\tLnet/minecraft/B;\tfield\tfield\n')
    m = cap.load_map(map_path, 'map')
    ok(m.kind == 'map', 'map kind')
    ok(len(m.cmap) == 0, 'map no C rows')
    ok(len(m.mrows) == 2 and len(m.frows) == 1, 'map row counts')
    a = cap.audit_map(m, dsrc, ddst, 'src_to_dst')
    ok(a['strict'] is True, 'strict map audit')
    ok(a['m_src_hit'] == 2 and a['m_dst_hit'] == 2, 'map method hits')
    ok(a['f_src_hit'] == 1 and a['f_dst_hit'] == 1, 'map field hits')
    ok(a['m_reverse_collisions'] == 0, 'map no reverse collision')
    ok(a['reasons'] == [], 'strict map no reasons')

    sd = cap.surface_diff(dsrc, ddst, m, 'src_to_dst', 'forward')
    ok(sd['classes_same'] == 2, 'surface classes same')
    ok(sd['classes_lost'] == 1 and sd['classes_added'] == 1, 'surface class churn')
    ok(sd['classes_renamed'] == 0, 'surface no class rename')
    ok(sd['methods_same'] == 1, 'surface methods same')
    ok(sd['methods_lost'] == 3 and sd['methods_added'] == 3, 'surface method churn')
    ok(sd['methods_renamed'] == 1, 'surface methods renamed')
    ok(sd['methods_sigchg'] == 1, 'surface methods sigchg')
    ok(sd['methods_missing'] == 1, 'surface methods missing')
    ok(sd['fields_same'] == 1 and sd['fields_lost'] == 0, 'surface fields stable')
    ok(sd['identity_break'] is False, 'surface no identity break')

    # 26.x bridge：C 行换 owner + 描述符替换 + 逆向碰撞 → 绝不 strict
    bridge_classes = ['net/minecraft/RA', 'net/minecraft/RB', 'net/minecraft/RNew']
    bridge_methods = [
        ('net/minecraft/RA', 'same', '()V'),
        ('net/minecraft/RA', 'official', '(Lnet/minecraft/RB;)V'),
    ]
    bridge_fields = []
    bdecl = make_decl(root, 'bridge-decl', bridge_classes,
                      bridge_methods, bridge_fields)
    dbridge = cap.load_decl(bdecl)
    bpath = write(os.path.join(root, 'bridge.tsv'),
        '# identity bridge\n'
        'C\tnet/minecraft/A\tnet/minecraft/RA\n'
        'C\tnet/minecraft/B\tnet/minecraft/RB\n'
        'C\tnet/minecraft/Gone\tnet/minecraft/RA\n'
        'M\tnet/minecraft/A\t(Lnet/minecraft/B;)V\toldName\tofficial\n'
        'M\tnet/minecraft/A\t()V\tsame\tsame\n'
        'F\tnet/minecraft/A\tLnet/minecraft/B;\tfield\tfield\n')
    b = cap.load_map(bpath, 'bridge')
    ok(b.kind == 'bridge', 'bridge kind')
    ok(len(b.cmap) == 3, 'bridge C rows')
    ok(b.c_rev_collisions == 1, 'bridge C reverse collision')
    ba = cap.audit_map(b, dsrc, dbridge, 'src_to_deobf')
    ok(ba['strict'] is False, 'bridge is never strict')
    ok('BRIDGE_NOT_A_LINKCHECK_MAP' in ba['reasons'], 'bridge wrong-map reason')
    ok('C_ROWS_CHANGE_OWNER_NAMESPACE' in ba['reasons'], 'bridge C reason')
    ok('CLASS_IDENTITY_COLLISION' in ba['reasons'], 'bridge collision reason')
    ok(ba['m_dst_hit'] == 2, 'bridge remapped desc target hit')
    ok(ba['m_src_hit'] == 2, 'bridge source hits')
    bs = cap.surface_diff(dsrc, dbridge, b, 'src_to_deobf', 'forward')
    ok(bs['identity_break'] is True, 'bridge identity break')
    ok(bs['classes_renamed'] >= 1, 'bridge class renamed via C row')
    ok(bs['methods_renamed'] == 2, 'bridge methods renamed via desc remap')

    bad = os.path.join(root, 'bad-decl.tsv')
    write(bad, '# only comment\n')
    try:
        cap.load_decl(bad)
        ok(False, 'empty decl rejected')
    except cap.InputError:
        ok(True, 'empty decl rejected')
    badmap = os.path.join(root, 'bad-map.tsv')
    write(badmap, 'C\tX\tY\nC\tX\tZ\n')
    try:
        cap.load_map(badmap, 'map')
        ok(False, 'conflicting C row rejected')
    except cap.InputError:
        ok(True, 'conflicting C row rejected')
    lookup, amb = cap.map_lookup(b, 'M')
    ok(lookup[('net/minecraft/A', 'oldName', '(Lnet/minecraft/B;)V')]
       == 'official', 'map_lookup key order')
    ok(amb == 0, 'map_lookup no ambiguity')
    reversed_map = cap.reverse_map(m)
    ok(reversed_map.reversed is True, 'reverse_map flag')
    ok(reversed_map.mrows[0] == ('net/minecraft/A',
                                 '(Lnet/minecraft/B;)V', 'newName', 'oldName'),
       'reverse_map swaps names')
    ra = cap.audit_map(reversed_map, ddst, dsrc, 'dst_to_src_reverse')
    ok(ra['strict'] is True, 'reverse strict map audit')
    ok(ra['reversed'] is True, 'reverse audit flag')
    try:
        cap.reverse_map(b)
        ok(False, 'reverse bridge rejected')
    except cap.InputError:
        ok(True, 'reverse bridge rejected')
    dup = write(os.path.join(root, 'dup.tsv'),
        'M\tO\t()V\ta\tb\nM\tO\t()V\ta\tc\n')
    dm = cap.load_map(dup, 'map')
    _, damb = cap.map_lookup(dm, 'M')
    ok(damb == 1, 'map_lookup ambiguity counted')
    return root, src, dst, map_path, bpath, bdecl


def tickets_and_plans(root):
    clean = make_ticket(root, 'clean', 3, 0, 0, 0, 1)
    manual = make_ticket(root, 'manual', 2, 0, 1, 1)
    badscalar = make_ticket(root, 'badscalar', 3, 0, 0, 0, 0, bad_scalar=True)
    badref = make_ticket(root, 'badref', 3, 0, 0, 0, 0, bad_ref=True)
    glob_ok = os.path.join(root, 'clean*.json')
    ev = cap.gate_tickets(glob_ok, '1.21.11')
    ok(ev['verdict'] == 'READY', 'clean tickets READY')
    ok(ev['counts']['refs'] == 4, 'clean tickets ref count')
    ok(ev['counts']['integrity_errors'] == 0, 'clean tickets integrity')
    ev = cap.gate_tickets(os.path.join(root, 'manual*.json'), '1.21.11')
    ok(ev['verdict'] == 'NEEDS_MANUAL', 'manual tickets NEEDS_MANUAL')
    ok('MANUAL_REFS' in ev['reasons'], 'manual reason')
    ev = cap.gate_tickets(os.path.join(root, 'badscalar*.json'), '1.21.11')
    ok(ev['verdict'] == 'UNSUPPORTED', 'bad scalar UNSUPPORTED')
    ok('TICKET_INTEGRITY' in ev['reasons'], 'bad scalar reason')
    ev = cap.gate_tickets(os.path.join(root, 'badref*.json'), '1.21.11')
    ok(ev['verdict'] == 'UNSUPPORTED', 'bad ref UNSUPPORTED')
    ok(ev['counts']['integrity_errors'] == 2, 'bad ref integrity count')
    ev = cap.gate_tickets(os.path.join(root, 'does-not-exist*.json'), '1.21.11')
    ok(ev['verdict'] == 'UNSUPPORTED', 'no tickets UNSUPPORTED')
    ok('NO_TICKETS' in ev['reasons'], 'no tickets reason')

    def plan_entry(verdict='AUTO', route='SAME_VERSION', strategy='none',
                   check=None, mode='', bridge=None, gen='obf'):
        return {
            'mod': {'file': 'fake.jar'},
            'route': route,
            'strategy': strategy,
            'verdict': verdict,
            'checkMode': mode,
            'check': check,
            'bridge': bridge,
        }
    good_check = {'ok': True, 'rc': 0, 'total': 9, 'resolve': 9,
                  'sigchg': 0, 'missing': 0}
    ok(cap.gate_plan(plan_entry(check=good_check), '1.21.1', 'obf', 'p')['verdict']
       == 'READY', 'plan AUTO checked READY')
    ok(cap.gate_plan(plan_entry(), '1.21.1', 'obf', 'p')['verdict']
       == 'UNSUPPORTED', 'plan AUTO without check rejected')
    po = cap.gate_plan(plan_entry(verdict='PLAN_ONLY', route='OBF_CROSS',
                                  strategy='startup'), '1.21.11', 'obf', 'p')
    ok(po['verdict'] == 'UNSUPPORTED', 'plan PLAN_ONLY rejected')
    ok('PLAN_ONLY_NOT_SYMBOL_CHECKED' in po['reasons'], 'plan-only reason')
    ma = cap.gate_plan(plan_entry(verdict='NEEDS_MANUAL', route='OBF_CROSS',
                                  strategy='startup',
                                  check={'ok': True, 'rc': 2, 'sigchg': 13,
                                         'missing': 56}),
                       '1.21.11', 'obf', 'p')
    ok(ma['verdict'] == 'NEEDS_MANUAL', 'plan manual')
    us = cap.gate_plan(plan_entry(verdict='UNSUPPORTED',
                                  route='RUNTIME_JAVA_MISMATCH'),
                       '26.1', 'deobf', 'p')
    ok(us['verdict'] == 'UNSUPPORTED', 'plan unsupported route')
    ok('LOADER_UNSUPPORTED' in us['reasons'], 'plan unsupported reason')
    mi = cap.gate_plan(plan_entry(verdict='MISSING_ARTIFACT'), '26.1', 'deobf', 'p')
    ok(mi['verdict'] == 'UNSUPPORTED', 'plan missing artifact')
    ok('MISSING_ARTIFACT' in mi['reasons'], 'plan missing artifact reason')
    s3 = cap.gate_plan(plan_entry(verdict='UNSUPPORTED', route='DEOBF_BREAK',
                                  strategy='startup', bridge='/tmp/b.tsv'),
                       '26.1', 'deobf', 'p')
    ok('DEOBF_STARTUP_AGENT_FORBIDDEN' in s3['reasons'],
       'plan deobf startup forbidden')
    # §14 C5 反例：26.x bridge 当 LinkCheck --map（check 存在但没有离线复测口径）
    c5 = cap.gate_plan(plan_entry(verdict='NEEDS_MANUAL', route='DEOBF_BREAK',
                                  strategy=None, check={'ok': True, 'rc': 2,
                                                        'sigchg': 3, 'missing': 141},
                                  bridge='/tmp/bridge-26.1.tsv'),
                       '26.1', 'deobf', 'p')
    ok(c5['verdict'] == 'UNSUPPORTED', 'C5 bridge-as-map rejected')
    ok('BRIDGE_AS_LINKCHECK_MAP' in c5['reasons'], 'C5 reason')
    # §14 S2 正例：离线 RemapTool + 无 --map 复测，不触发 bridge 反例
    s2 = cap.gate_plan(plan_entry(verdict='NEEDS_MANUAL', route='DEOBF_BREAK',
                                  strategy='offline',
                                  mode='RemapTool + LinkCheck(no --map) [pipeline-26.sh]',
                                  check={'ok': True, 'rc': 2, 'sigchg': 9,
                                         'missing': 52,
                                         'checkedJar': '/tmp/remapped.jar'},
                                  bridge='/tmp/bridge-26.1.tsv'),
                       '26.1', 'deobf', 'p')
    ok(s2['verdict'] == 'NEEDS_MANUAL', 'S2 offline plan manual not unsupported')
    ok('BRIDGE_AS_LINKCHECK_MAP' not in s2['reasons'], 'S2 no bridge-as-map')
    unknown = cap.gate_plan(plan_entry(verdict='WHATEVER'), '1.21.1', 'obf', 'p')
    ok('UNKNOWN_VERDICT' in unknown['reasons'], 'unknown verdict rejected')
    return root, clean, manual


def stats_and_claims(root):
    ss_ok = write_json(os.path.join(root, 'ss-ok.json'), {
        'schema': 1, 'version': '1.21.11',
        'stats': {'string_occurrences': 3644, 'unique_strings': 2606,
                  'unresolved': 0, 'rewritten_entries': 1}})
    ss_bad = write_json(os.path.join(root, 'ss-bad.json'), {
        'schema': 1, 'version': '26.1',
        'stats': {'string_occurrences': 3644, 'unresolved': 54}})
    ok(cap.gate_stats_stringsurface(
        {'path': ss_ok, 'version': '1.21.11'})['verdict'] == 'READY',
       'stringsurface clean READY')
    ev = cap.gate_stats_stringsurface({'path': ss_bad, 'version': '26.1'})
    ok(ev['verdict'] == 'NEEDS_MANUAL', 'stringsurface unresolved manual')
    ok(ev['counts']['unresolved'] == 54, 'stringsurface unresolved count')
    ok('UNRESOLVED_STRING_SURFACE' in ev['reasons'], 'stringsurface reason')
    bg_none = write_json(os.path.join(root, 'bg-none.json'), {
        'schema': 1, 'version': '1.21.11',
        'stats': {'total': 290, 'candidate_rules': 0, 'auto_fixed': 0}})
    bg_cand = write_json(os.path.join(root, 'bg-cand.json'), {
        'schema': 1, 'version': '26.1',
        'stats': {'total': 312, 'candidate_rules': 2, 'auto_fixed': 0}})
    bg_unsafe = write_json(os.path.join(root, 'bg-unsafe.json'), {
        'schema': 1, 'version': '26.1',
        'stats': {'total': 312, 'candidate_rules': 2, 'auto_fixed': 1}})
    ok(cap.gate_stats_bridgegen(
        {'path': bg_none, 'version': '1.21.11'})['verdict'] == 'READY',
       'bridgegen clean READY')
    ev = cap.gate_stats_bridgegen({'path': bg_cand, 'version': '26.1'})
    ok(ev['verdict'] == 'NEEDS_MANUAL', 'bridgegen candidates manual')
    ok('UNREVIEWED_BRIDGE_CANDIDATES' in ev['reasons'], 'bridgegen candidate reason')
    ev = cap.gate_stats_bridgegen({'path': bg_unsafe, 'version': '26.1'})
    ok(ev['verdict'] == 'UNSUPPORTED', 'bridgegen auto_fixed unsupported')
    ok('UNSAFE_AUTO_BRIDGE_FIX' in ev['reasons'], 'bridgegen unsafe reason')
    bad_schema = write_json(os.path.join(root, 'bad-schema.json'), {
        'schema': 99, 'version': 'x', 'stats': {}})
    try:
        cap.load_stats(bad_schema)
        ok(False, 'bad stats schema rejected')
    except cap.InputError:
        ok(True, 'bad stats schema rejected')

    clean_result = {
        'schema': 1, 'verdict': 'READY', 'claim_policy': cap.CLAIM_POLICY,
        'evidence': [{'verdict': 'READY'}],
    }
    ok(cap.assert_no_claims(clean_result), 'assert_no_claims clean')
    bad_result = dict(clean_result)
    bad_result['verdict'] = 'COMPATIBLE'
    try:
        cap.assert_no_claims(bad_result)
        ok(False, 'assert_no_claims rejects bad verdict')
    except AssertionError:
        ok(True, 'assert_no_claims rejects bad verdict')
    claim_result = dict(clean_result)
    claim_result['claim_policy'] = 'compatible'
    try:
        cap.assert_no_claims(claim_result)
        ok(False, 'assert_no_claims rejects claim word')
    except AssertionError:
        ok(True, 'assert_no_claims rejects claim word')
    ev_new = cap.ev_new('x', '1', 'k')
    ok(ev_new['verdict'] == 'READY' and ev_new['reasons'] == [],
       'ev_new default')
    cap.ev_raise(ev_new, 'NEEDS_MANUAL', 'A')
    cap.ev_raise(ev_new, 'UNSUPPORTED', 'B')
    cap.ev_raise(ev_new, 'NEEDS_MANUAL', 'B')
    ok(ev_new['verdict'] == 'UNSUPPORTED', 'ev_raise worst wins')
    ok(ev_new['reasons'] == ['A', 'B'], 'ev_raise dedup')


def integration(root, src_decl, dst_decl, map_path, bridge_path, bridge_decl,
                clean_ticket):
    plan_auto = write_json(os.path.join(root, 'plan-auto.json'), {
        'schema': 1, 'tool': 'mcport-loader',
        'target': {'id': '1.21.1', 'generation': 'obf'},
        'summary': {'mods': 1, 'auto': 1},
        'plan': [{
            'mod': {'file': 'fake.jar'},
            'route': 'SAME_VERSION', 'strategy': 'none',
            'verdict': 'AUTO', 'checkMode': 'LinkCheck --map',
            'check': {'ok': True, 'rc': 0, 'total': 9, 'resolve': 9,
                      'sigchg': 0, 'missing': 0},
        }],
    })
    plan_manual = write_json(os.path.join(root, 'plan-manual.json'), {
        'schema': 1, 'tool': 'mcport-loader',
        'target': {'id': '1.21.1', 'generation': 'obf'},
        'summary': {'mods': 1, 'manual': 1},
        'plan': [{
            'mod': {'file': 'fake2.jar'},
            'route': 'SAME_VERSION', 'strategy': 'none',
            'verdict': 'NEEDS_MANUAL', 'checkMode': 'LinkCheck --map',
            'check': {'ok': True, 'rc': 2, 'total': 9, 'resolve': 3,
                      'sigchg': 2, 'missing': 4},
        }],
    })
    ss = write_json(os.path.join(root, 'ss-ready.json'), {
        'schema': 1, 'version': '1.21.1',
        'stats': {'string_occurrences': 1, 'unresolved': 0}})
    bg = write_json(os.path.join(root, 'bg-ready.json'), {
        'schema': 1, 'version': '1.21.1',
        'stats': {'total': 0, 'candidate_rules': 0, 'auto_fixed': 0}})
    base = {
        'schema': 1,
        'versions': [
            {'version': '1.21.1', 'generation': 'obf', 'decl': src_decl},
            {'version': '1.21.11', 'generation': 'obf', 'decl': dst_decl},
            {'version': '26.1', 'generation': 'deobf', 'decl': bridge_decl},
        ],
        'maps': [
            {'from': '1.21.1', 'to': '1.21.11', 'path': map_path,
             'kind': 'map', 'direction': 'forward'},
            {'from': '1.21.1', 'to': '26.1', 'path': bridge_path,
             'kind': 'bridge', 'direction': 'forward'},
        ],
        'plans': [plan_auto],
        'tickets': [{'glob': clean_ticket, 'version': '1.21.1'}],
        'stats': {
            'stringsurface': [{'path': ss, 'version': '1.21.1'}],
            'bridgegen': [{'path': bg, 'version': '1.21.1'}],
        },
    }
    r = cap.build_result(base)
    ok(r['verdict'] == 'READY', 'integration full READY')
    ok(r['counts']['versions'] == 3, 'integration versions')
    ok(r['counts']['maps'] == 2, 'integration maps')
    ok(len(r['surface_diffs']) == 2, 'integration surface rows')
    ok(r['contracts'][0]['capability_digest'] != r['contracts'][1]['capability_digest'],
       'integration contract digests differ')
    ok(all(len(c['capability_digest']) == 64 for c in r['contracts']),
       'integration digest shapes')
    strict = [a for a in r['map_audits'] if a['kind'] == 'map']
    bridges = [a for a in r['map_audits'] if a['kind'] == 'bridge']
    ok(strict[0]['strict'] is True, 'integration strict map')
    ok(bridges[0]['strict'] is False, 'integration bridge never strict')
    ok(r['claim_policy'] == cap.CLAIM_POLICY, 'integration claim policy')
    ok(r['disclaimer'] == cap.DISCLAIMER, 'integration disclaimer')
    deobf_ev = [e for e in r['evidence'] if e['kind'] == 'identity_bridge']
    ok(len(deobf_ev) == 1 and deobf_ev[0]['verdict'] == 'READY',
       'deobf bridge present READY')

    manual_spec = dict(base)
    manual_spec['plans'] = [plan_manual]
    r2 = cap.build_result(manual_spec)
    ok(r2['verdict'] == 'NEEDS_MANUAL', 'integration manual plan')
    reverse_spec = dict(base)
    reverse_maps = list(base['maps'])
    reverse_maps[0] = {
        'from': '1.21.11', 'to': '1.21.1', 'path': map_path,
        'kind': 'map', 'direction': 'backward', 'reverse': True,
    }
    reverse_spec['maps'] = reverse_maps
    rr = cap.build_result(reverse_spec)
    ok(rr['verdict'] == 'READY', 'integration reversed strict map READY')
    rev_audit = [a for a in rr['map_audits'] if a['reversed']]
    ok(len(rev_audit) == 1 and rev_audit[0]['strict'] is True,
       'integration reversed audit strict')
    no_bridge = dict(base)
    no_bridge['maps'] = [base['maps'][0]]
    r3 = cap.build_result(no_bridge)
    ok(r3['verdict'] == 'UNSUPPORTED', 'integration deobf without bridge')
    ok(any('DEOBF_IDENTITY_BRIDGE_MISSING' in e['reasons']
           for e in r3['evidence']), 'integration deobf missing reason')
    bad_map = dict(base)
    bad_map['maps'] = [dict(base['maps'][0], kind='bridge')]
    r4 = cap.build_result(bad_map)
    ok(r4['verdict'] == 'UNSUPPORTED', 'map mislabeled as bridge rejected')
    no_evidence = {'schema': 1,
                   'versions': [{'version': '1.21.1', 'generation': 'obf',
                                 'decl': src_decl}]}
    r5 = cap.build_result(no_evidence)
    ok(r5['verdict'] == 'UNSUPPORTED', 'no symbol evidence rejected')
    ok(any('NO_SYMBOL_EVIDENCE' in e['reasons'] for e in r5['evidence']),
       'no symbol evidence reason')
    try:
        cap.build_result({'schema': 99, 'versions': []})
        ok(False, 'bad schema rejected')
    except cap.InputError:
        ok(True, 'bad schema rejected')

    # CLI 端到端：READY / NEEDS_MANUAL / 输入错误 / --no-gate
    cli = os.path.join(root, 'cli')
    os.makedirs(cli, exist_ok=True)
    spec_ready = write_json(os.path.join(cli, 'spec-ready.json'), base)
    spec_manual = write_json(os.path.join(cli, 'spec-manual.json'), manual_spec)
    pyexe = sys.executable or '/usr/bin/python3'
    cap_py = os.path.join(HERE, 'capability.py')
    def run(spec_path, out_name, extra=None):
        out = os.path.join(cli, out_name)
        args = [pyexe, cap_py, '--spec', spec_path, '--out-dir', out]
        if extra:
            args += extra
        p = subprocess.run(args, capture_output=True, text=True)
        return p, out
    p, out = run(spec_ready, 'out-ready')
    ok(p.returncode == 0, 'CLI READY rc=0')
    ok('verdict: READY' in p.stdout, 'CLI READY stdout')
    ok(cap.DISCLAIMER in p.stdout, 'CLI disclaimer printed')
    g = read_json(os.path.join(out, 'gate.json'))
    ok(g['verdict'] == 'READY', 'CLI gate.json verdict')
    ok(read_json(os.path.join(out, 'stats.json'))['counts']['maps'] == 2,
       'CLI stats.json')
    for fn in ('map-audit.csv', 'surface-diff.csv', 'triage.tsv'):
        ok(os.path.isfile(os.path.join(out, fn)), 'CLI writes ' + fn)
    with open(os.path.join(out, 'triage.tsv'), 'r', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh, delimiter='\t'))
    ok(all(x['verdict'] in cap.ALLOWED_VERDICTS for x in rows),
       'CLI triage verdicts')
    p, out2 = run(spec_manual, 'out-manual')
    ok(p.returncode == 2, 'CLI NEEDS_MANUAL rc=2')
    ok('verdict: NEEDS_MANUAL' in p.stdout, 'CLI manual stdout')
    p, out3 = run(spec_manual, 'out-nogate', extra=['--no-gate'])
    ok(p.returncode == 0, 'CLI --no-gate rc=0')
    badspec = write_json(os.path.join(cli, 'spec-bad.json'),
                         {'schema': 1, 'versions': []})
    p, out4 = run(badspec, 'out-bad')
    ok(p.returncode == 1, 'CLI bad input rc=1')
    ok('CAPABILITY_INPUT_ERROR' in p.stderr, 'CLI bad input stderr')
    ok(not os.path.exists(os.path.join(out4, 'gate.json')),
       'CLI bad input writes no gate')
    p, out5 = run(spec_ready, 'out-quiet', extra=['--quiet'])
    ok(p.returncode == 0 and p.stdout.strip() == '', 'CLI quiet')
    ok(os.path.isfile(os.path.join(out5, 'gate.json')), 'CLI quiet still writes')
    p, out6 = run(spec_ready, 'out-emit', extra=['--emit-contract'])
    ok(p.returncode == 0, 'CLI emit-contract rc')
    ok(os.path.isfile(os.path.join(out6, 'capability-26.1.tsv')),
       'CLI emit-contract file')
    with open(os.path.join(out6, 'map-audit.csv'), 'r', encoding='utf-8') as fh:
        mrows = list(csv.DictReader(fh))
    ok(len(mrows) == 2 and mrows[0]['label'] == '1.21.1_to_1.21.11',
       'CLI map-audit rows')
    ok('reversed' in mrows[0] and mrows[0]['reversed'] == 'False',
       'CLI map-audit reversed column')
    with open(os.path.join(out6, 'surface-diff.csv'), 'r', encoding='utf-8') as fh:
        srows = list(csv.DictReader(fh))
    ok(len(srows) == 2 and 'identity_break' in srows[0],
       'CLI surface-diff rows')


def main():
    with tempfile.TemporaryDirectory(prefix='mcport-capability-') as root:
        unit()
        _, src_decl, dst_decl, map_path, bridge_path, bridge_decl = decl_and_map(root)
        _, clean_ticket, _ = tickets_and_plans(root)
        stats_and_claims(root)
        integration(root, src_decl, dst_decl, map_path, bridge_path,
                    bridge_decl, clean_ticket)
    print('RESULT ALL_OK ' + str(COUNT))


if __name__ == '__main__':
    main()
