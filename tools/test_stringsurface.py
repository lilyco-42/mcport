#!/usr/bin/env python3
"""Self-contained regression for tools/stringsurface.py.

No Minecraft jar, no Mojang mapping file, no third-party mod bytecode, no network.
Everything (declaration table, mapping table, class files, jar, refmap JSON) is
synthesized in tempfile so the assertions stay reproducible on any JDK 17+ box.
"""
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
sp = importlib.util.spec_from_file_location('stringsurface', REPO / 'tools' / 'stringsurface.py')
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)

COUNT = 0


def ok(cond, msg):
    global COUNT
    if not cond:
        raise AssertionError('FAIL: ' + msg)
    COUNT += 1


DECL = '\n'.join([
    '# synthetic target declaration table (real-name namespace)',
    'C\tcom/mojang/blaze3d/opengl/GlStateManager',
    'C\tnet/minecraft/client/Minecraft',
    'C\tnet/minecraft/client/Sub',
    'S\tcom/mojang/blaze3d/opengl/GlStateManager\tjava/lang/Object\t',
    'S\tnet/minecraft/client/Minecraft\tjava/lang/Object\t',
    'S\tnet/minecraft/client/Sub\tnet/minecraft/client/Minecraft\t',
    'M\tcom/mojang/blaze3d/opengl/GlStateManager\t_activeTexture\t(I)V',
    'M\tnet/minecraft/client/Minecraft\tgetInstance\t()Lnet/minecraft/client/Minecraft;',
    'F\tcom/mojang/blaze3d/opengl/GlStateManager\tBLEND\tZ',
]) + '\n'

MAP = '\n'.join([
    '# synthetic intermediary -> real mapping (M/F keys use OLD namespace desc)',
    'C\tcom/mojang/blaze3d/platform/GlStateManager\tcom/mojang/blaze3d/opengl/GlStateManager',
    'C\tnet/minecraft/class_310\tnet/minecraft/client/Minecraft',
    'C\tnet/minecraft/class_GONE\tnet/minecraft/client/NotInDecl',
    'M\tcom/mojang/blaze3d/platform/GlStateManager\t(I)V\t_activeTexture\t_activeTexture',
    'M\tnet/minecraft/class_310\t()Lnet/minecraft/class_310;\tmethod_1234\tgetInstance',
    'M\tnet/minecraft/class_310\t(I)V\tmethod_5555\tnotInDecl',
    'M\tnet/minecraft/class_310\t()I\tmethod_7777\tinheritedMethod',
    'F\tcom/mojang/blaze3d/platform/GlStateManager\tZ\tfield_9999\tBLEND',
    'S\tcom/mojang/blaze3d/platform/GlStateManager\tjava/lang/Object\t',
    'S\tnet/minecraft/class_310\tjava/lang/Object\t',
    'S\tnet/minecraft/class_310_sub\tnet/minecraft/class_310\t',
]) + '\n'


def make_mapper(root):
    d = root / 'decl.tsv'
    p = root / 'map.tsv'
    d.write_text(DECL, encoding='utf-8')
    p.write_text(MAP, encoding='utf-8')
    return m.Mapper(str(d), str(p))


def unit(mp):
    # ---- token_status: the five decision branches ----
    r = mp.token_status('com/mojang/blaze3d/platform/GlStateManager')
    ok(r[0] is True and r[1] == 'com/mojang/blaze3d/opengl/GlStateManager' and r[2] == 'RENAME_EXACT', 'token_status RENAME_EXACT')
    ok(mp.token_status('net/minecraft/client/Minecraft')[2] == 'TARGET_PRESENT', 'token_status TARGET_PRESENT')
    ok(mp.token_status('net/minecraft/class_GONE')[2] == 'MAPPED_TARGET_MISSING', 'token_status MAPPED_TARGET_MISSING')
    ok(mp.token_status('net/minecraft/class_404')[2] == 'UNRESOLVED', 'token_status UNRESOLVED')
    ok(mp.token_status('com/mojang/brigadier/Command')[2] == 'EXTERNAL', 'token_status EXTERNAL')
    ok(mp.token_status('com/mojang/brigadier/Command')[0] is True, 'EXTERNAL is not a hard error')

    # ---- map_tokens: exact substitution, atomic fail-loud, dot form ----
    ok(mp.map_tokens('net/minecraft/class_310') == ('net/minecraft/client/Minecraft', 'EXACT_REMAP', mp.map_tokens('net/minecraft/class_310')[2]), 'map_tokens exact')
    ok(mp.map_tokens('x net/minecraft/class_310 y')[0] == 'x net/minecraft/client/Minecraft y', 'map_tokens embedded')
    a = mp.map_tokens('net/minecraft/class_310 net/minecraft/class_404')
    ok(a[0] == 'net/minecraft/class_310 net/minecraft/class_404' and a[1] == 'UNRESOLVED', 'map_tokens atomic fail-loud')
    ok(mp.map_tokens('hello')[1] == 'NO_GAME_TOKEN', 'map_tokens no token')
    ok(mp.map_tokens('net.minecraft.class_310')[0] == 'net.minecraft.client.Minecraft', 'map_tokens dotted')
    ok(mp.map_tokens('net/minecraft/client/Minecraft')[1] == 'TARGET_PRESENT', 'map_tokens already present')
    ok(mp.map_tokens('com/mojang/brigadier/Command')[1] == 'EXTERNAL', 'map_tokens external only')

    # ---- rewrite_member: method / field / inherited / reject branches ----
    r = mp.rewrite_member('Lnet/minecraft/class_310;method_1234()Lnet/minecraft/class_310;')
    ok(r[1] == 'MEMBER_EXACT_REMAP', 'rewrite_member method status ' + str(r))
    ok(r[0] == 'Lnet/minecraft/client/Minecraft;getInstance()Lnet/minecraft/client/Minecraft;', 'rewrite_member method value ' + str(r))
    r = mp.rewrite_member('Lcom/mojang/blaze3d/platform/GlStateManager;field_9999:Z')
    ok(r[1] == 'MEMBER_EXACT_REMAP' and r[0] == 'Lcom/mojang/blaze3d/opengl/GlStateManager;BLEND:Z', 'rewrite_member field ' + str(r))
    ok(mp.rewrite_member('Lnet/minecraft/class_310;method_1234')[1] == 'MEMBER_MISSING_DESC', 'rewrite_member bare member rejected')
    ok(mp.rewrite_member('Lcom/mojang/blaze3d/platform/GlStateManager;method_9999(I)V')[1] == 'UNRESOLVED', 'rewrite_member no M line')
    ok(mp.rewrite_member('Lnet/minecraft/class_310;method_5555(I)V')[1] == 'MEMBER_TARGET_MISSING', 'rewrite_member target member absent')
    ok(mp.rewrite_member('Lnet/minecraft/class_GONE;method_1234()I')[1] == 'MAPPED_TARGET_MISSING', 'rewrite_member owner absent')
    ok(mp.rewrite_string('method_1234(Lnet/minecraft/class_310;)V')[1] == 'NO_OWNER_MEMBER', 'rewrite_string no-owner member')
    ok(mp.rewrite_string('just text')[1] == 'NO_GAME_TOKEN', 'rewrite_string plain')
    ok(mp.rewrite_string('Lnet/minecraft/client/Minecraft;')[1] == 'TARGET_PRESENT', 'rewrite_string bare owner class')

    # ---- BFS with the two different tuple orders ----
    ok(mp.decl_has_member('M', 'net/minecraft/client/Sub', 'getInstance', '()Lnet/minecraft/client/Minecraft;') is True,
       'decl BFS finds inherited member (owner,name,desc order)')
    ok(mp.decl_has_member('M', 'net/minecraft/client/Sub', 'nope', '()I') is False, 'decl BFS misses unknown member')
    ok(mp.map_member_name('M', 'net/minecraft/class_310_sub', '()Lnet/minecraft/class_310;', 'method_1234')[0] == 'getInstance',
       'map BFS finds inherited member (owner,desc,name order)')
    ok(mp.map_member_name('M', 'net/minecraft/class_310', '()I', 'method_7777')[0] == 'inheritedMethod',
       'map exact M line')
    ok(mp.map_member_name('F', 'net/minecraft/class_310', '()I', 'method_7777')[0] is None,
       'M and F tables stay separate')


# ---- minimal, structurally valid class file with a controllable constant pool ----

def cp_utf8(s):
    b = s.encode('utf-8')
    return b'\x01' + struct.pack('>H', len(b)) + b


def mkclass(const_bytes, shared):
    """CP: 1 Utf8 T, 2 Class#1, 3 Utf8 java/lang/Object, 4 Class#3,
    5 Utf8 <const_bytes>, [6 Class#5 if shared], then String#5.
    Empty but verifiable class body (PUBLIC|SUPER, no fields/methods/attrs)."""
    ents = [None, cp_utf8('t/Shared'), b'\x07' + struct.pack('>H', 1),
            cp_utf8('java/lang/Object'), b'\x07' + struct.pack('>H', 3),
            b'\x01' + struct.pack('>H', len(const_bytes)) + const_bytes]
    if shared:
        ents.append(b'\x07' + struct.pack('>H', 5))
    ents.append(b'\x08' + struct.pack('>H', 5))
    count = len(ents)
    body = struct.pack('>HHHHHHH', 0x0021, 2, 4, 0, 0, 0, 0)
    head = b'\xca\xfe\xba\xbe' + b'\x00\x00' + b'\x00\x3d' + struct.pack('>H', count)
    return head + b''.join(ents[1:]) + body


def ldc_strings(data):
    n, ents, body = m.cp_parse(data)
    out = []
    for e in ents:
        if e and e[0] == 8:
            si = struct.unpack('>H', e[1:3])[0]
            out.append(m.cp_utf8(ents[si]))
    return out


def class_names(data):
    n, ents, body = m.cp_parse(data)
    out = []
    for e in ents:
        if e and e[0] == 7:
            si = struct.unpack('>H', e[1:3])[0]
            out.append(m.cp_utf8(ents[si]))
    return out


def cp_tests(mp):
    obs = []
    def observe(old, origin, path, new, status, why):
        obs.append((old, new, status))

    old = b'com/mojang/blaze3d/platform/GlStateManager'
    new = 'com/mojang/blaze3d/opengl/GlStateManager'
    # non-shared: the Utf8 itself is rewritten in place
    d0 = mkclass(old, shared=False)
    ok(m.cp_parse(d0)[0] == 7, 'cp_parse count non-shared')
    d1, ch = m.rewrite_class_bytes(d0, mp, observe, True)
    ok(ch is True, 'non-shared rewrite changed bytes')
    ok(ldc_strings(d1) == [new], 'non-shared LDC rewritten: ' + str(ldc_strings(d1)))
    ok(d1[6:8] == b'\x00\x3d', 'class major preserved')
    ok(len(class_names(d1)) == 2, 'non-shared class entries untouched')

    # shared: must clone the Utf8, never rewrite the one CONSTANT_Class references
    d2 = mkclass(old, shared=True)
    ok(old.decode('ascii') in class_names(d2), 'fixture has shared Class ref')
    d3, ch = m.rewrite_class_bytes(d2, mp, observe, True)
    ok(ch is True, 'shared rewrite changed bytes')
    ok(ldc_strings(d3) == [new], 'shared LDC rewritten: ' + str(ldc_strings(d3)))
    ok(old.decode('ascii') in class_names(d3), 'shared CONSTANT_Class name preserved')
    ok(m.cp_parse(d3)[0] == 9, 'clone appended one CP slot (8 + 1)')
    ok(d3[6:8] == b'\x00\x3d', 'shared class major preserved')

    # audit mode: full observation but byte-identical output
    obs.clear()
    d4, ch = m.rewrite_class_bytes(d2, mp, observe, False)
    ok(ch is False and d4 == d2, 'audit mode never mutates bytes')
    ok(any(o[2] == 'EXACT_REMAP' for o in obs), 'audit still observes the rewritable LDC')

    # modified UTF-8 / non-ASCII must be refused, not re-encoded
    weird = b'com/mojang/blaze3d/platform/GlStateManager\xc3\xa9'
    d5 = mkclass(weird, shared=False)
    obs.clear()
    d6, ch = m.rewrite_class_bytes(d5, mp, observe, True)
    ok(ch is False and d6 == d5, 'non-ASCII constant refused without mutation')
    ok(any(o[2] == 'DECODE_FAIL' for o in obs), 'DECODE_FAIL recorded in triage')


def json_tests(mp):
    obs = []
    def observe(old, origin, path, new, status, why):
        obs.append((old, new, status))
    obj = {
        'mappings': {'xaero/Mixin': {'renderTo': 'Lnet/minecraft/class_310;method_1234()Lnet/minecraft/class_310;'}},
        'plain': 'hello',
    }
    data = json.dumps(obj).encode('utf-8')
    out, ch = m.rewrite_json_bytes(data, mp, observe, 'x.refmap.json', True)
    ok(ch is True, 'json rewrite changed bytes')
    got = json.loads(out)
    ok(got['mappings']['xaero/Mixin']['renderTo'] == 'Lnet/minecraft/client/Minecraft;getInstance()Lnet/minecraft/client/Minecraft;',
       'json member-like value rewritten')
    ok(got['plain'] == 'hello', 'json unrelated string untouched')
    ok(out.endswith(b'\n'), 'json output has trailing newline')
    plain = b'{ "note": "hello", "n": 1 }'
    p_out, p_ch = m.rewrite_json_bytes(plain, mp, observe, 'fabric.mod.json', True)
    ok(p_ch is False and p_out == plain, 'JSON without exact rename stays byte-identical')
    obs.clear()
    out2, ch2 = m.rewrite_json_bytes(data, mp, observe, 'x.refmap.json', False)
    ok(ch2 is False and out2 == data, 'json audit mode byte-identical')
    ok(any(o[2] == 'MEMBER_EXACT_REMAP' for o in obs), 'json audit observes candidate')
    bad = b'{not json'
    out3, ch3 = m.rewrite_json_bytes(bad, mp, observe, 'bad.json', True)
    ok(ch3 is False and out3 == bad, 'invalid json left untouched')
    ok(any(o[2] == 'INVALID_JSON' for o in obs), 'INVALID_JSON recorded')
    collide = {'net/minecraft/class_310': 1, 'net/minecraft/client/Minecraft': 2}
    out4, ch4 = m.rewrite_json_bytes(json.dumps(collide).encode(), mp, observe, 'c.json', True)
    ok(ch4 is False and out4 == json.dumps(collide).encode(), 'json key collision fail-loud')
    ok(any(o[2] == 'INVALID_JSON' for o in obs), 'key collision recorded as INVALID_JSON')


def write_jar(path, class_bytes, refmap_obj):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('t/Shared.class', class_bytes)
        z.writestr('x.refmap.json', json.dumps(refmap_obj))
        z.writestr('assets/skip.json', json.dumps({'note': 'net.minecraft.class_310 ignored'}))


def integration(root, mp):
    old = b'com/mojang/blaze3d/platform/GlStateManager'
    refmap = {
        'mappings': {'xaero/Mixin': {'a': 'net/minecraft/class_310', 'b': 'net/minecraft/class_404'}},
        'named:intermediary': {'xaero/Mixin': {'a': 'net/minecraft/class_310'}},
    }
    jar = root / 'mod.jar'
    write_jar(jar, mkclass(old, shared=True), refmap)
    spec = {
        'schema': 1,
        'targets': [{
            'version': 'T',
            'decl': str(root / 'decl.tsv'),
            'map': str(root / 'map.tsv'),
            'jars': [str(jar)],
        }],
    }
    spath = root / 'spec.json'
    spath.write_text(json.dumps(spec), encoding='utf-8')
    tool = str(REPO / 'tools' / 'stringsurface.py')

    audit = root / 'audit'
    r = subprocess.run([sys.executable or '/usr/bin/python3', tool, '--spec', str(spath), '--out-dir', str(audit)],
                       capture_output=True, text=True, timeout=120)
    ok(r.returncode == 2, 'audit exits 2 when unresolved exists: rc=' + str(r.returncode) + ' ' + r.stderr[-200:])
    ok('RESULT targets=1' in r.stdout, 'audit RESULT line: ' + r.stdout.strip())
    ok(not (audit / 'fixed').exists(), 'audit never writes fixed jars')
    ok((audit / 'T' / 'triage.tsv').exists() and (audit / 'T' / 'stats.json').exists(), 'audit writes triage + stats')
    ok((audit / 'summary.csv').exists(), 'audit writes summary.csv')
    import csv
    with open(audit / 'summary.csv', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    ok(len(rows) == 1 and rows[0]['version'] == 'T', 'summary one row')
    ok(int(rows[0]['unresolved']) > 0, 'summary reports unresolved')
    ok(int(rows[0]['rewritten_entries']) == 0, 'audit rewrites nothing')
    tri = (audit / 'T' / 'triage.tsv').read_text(encoding='utf-8')
    ok('UNRESOLVED' in tri, 'triage contains UNRESOLVED')
    ok('net.minecraft.class_310 ignored' not in tri, 'assets/ resource excluded')

    rw = root / 'rw'
    r2 = subprocess.run([sys.executable or '/usr/bin/python3', tool, '--spec', str(spath), '--out-dir', str(rw), '--rewrite'],
                        capture_output=True, text=True, timeout=120)
    ok(r2.returncode == 2, 'rewrite also fails loud on unresolved')
    fixed = rw / 'T' / 'fixed' / 'mod.jar'
    ok(fixed.exists(), 'rewrite writes fixed jar')
    with zipfile.ZipFile(fixed) as z:
        got = json.loads(z.read('x.refmap.json'))
        cls_bytes = z.read('t/Shared.class')
        assets = z.read('assets/skip.json')
    ok(got['mappings']['xaero/Mixin']['a'] == 'net/minecraft/client/Minecraft', 'exact value rewritten in fixed jar')
    ok(got['mappings']['xaero/Mixin']['b'] == 'net/minecraft/class_404', 'unresolved value preserved in fixed jar')
    ok(got['named:intermediary']['xaero/Mixin']['a'] == 'net/minecraft/client/Minecraft', 'nested value rewritten')
    ok(ldc_strings(cls_bytes) == ['com/mojang/blaze3d/opengl/GlStateManager'], 'shared LDC rewritten in fixed jar')
    ok('com/mojang/blaze3d/platform/GlStateManager' in class_names(cls_bytes), 'shared Class ref intact in fixed jar')
    ok(b'net.minecraft.class_310 ignored' in assets, 'assets/ entry byte-identical')

    # deterministic: second rewrite produces identical jar bytes
    rw2 = root / 'rw2'
    subprocess.run([sys.executable or '/usr/bin/python3', tool, '--spec', str(spath), '--out-dir', str(rw2), '--rewrite'],
                   capture_output=True, text=True, timeout=120)
    ok(fixed.read_bytes() == (rw2 / 'T' / 'fixed' / 'mod.jar').read_bytes(), 'rewrite deterministic')

    # no unresolved => exit 0
    clean = dict(spec)
    clean['targets'] = [dict(spec['targets'][0])]
    ref2 = {'mappings': {'xaero/Mixin': {'a': 'net/minecraft/class_310'}}}
    jar2 = root / 'clean.jar'
    write_jar(jar2, mkclass(old, shared=False), ref2)
    clean['targets'][0]['jars'] = [str(jar2)]
    sp2 = root / 'spec2.json'
    sp2.write_text(json.dumps(clean), encoding='utf-8')
    out = root / 'clean'
    r3 = subprocess.run([sys.executable or '/usr/bin/python3', tool, '--spec', str(sp2), '--out-dir', str(out)],
                        capture_output=True, text=True, timeout=120)
    ok(r3.returncode == 0, 'fully resolvable spec exits 0: rc=' + str(r3.returncode) + ' ' + r3.stdout.strip())
    ok('unresolved=0' in r3.stdout, 'RESULT reports unresolved=0')

    # fixed jar class still parses with JDK javap (structural validity)
    javap = subprocess.run(['javap', '-verbose', '-cp', str(fixed), 't.Shared'],
                           capture_output=True, text=True, timeout=60)
    ok(javap.returncode == 0, 'javap parses rewritten class: ' + javap.stderr[-200:])
    ok('major version: 61' in javap.stdout, 'javap sees Java 17 major')
    ok('com/mojang/blaze3d/opengl/GlStateManager' in javap.stdout, 'javap sees rewritten String constant')


def main():
    with tempfile.TemporaryDirectory(prefix='mcport-stringsurface-') as td:
        root = Path(td)
        mp = make_mapper(root)
        unit(mp)
        cp_tests(mp)
        json_tests(mp)
        integration(root, mp)
    print('RESULT ALL_OK ' + str(COUNT))


if __name__ == '__main__':
    main()
