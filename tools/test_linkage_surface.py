#!/usr/bin/env python3
"""McPort 0.2.7 / REPORT section 26: pure-stdlib regression for linkage_surface.py.

The fixtures are synthetic class files. No Mojang jar, official mapping, third-party
mod binary, Java compiler, network access or non-stdlib dependency is used here.
A separate gate scenario compares the tool against a real javac 17 class file.
"""

import argparse
import contextlib
import csv
import hashlib
import importlib.util
import io
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
PY = sys.executable if sys.executable else '/usr/bin/python3'
ENV = dict(os.environ)
ENV.update(PATH='/home/lilyco/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
           HOME='/home/lilyco', LANG='C.utf8', LC_ALL='C.utf8', PYTHONHASHSEED='0')
_spec = importlib.util.spec_from_file_location('test_linkage_surface_module', TOOLS / 'linkage_surface.py')
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
AUD = m.AUD
CR = m.CR
COUNT = 0


def ok(label, cond):
    global COUNT
    COUNT += 1
    if not cond:
        raise AssertionError(f'#{COUNT}: {label}')


def raises_any(label, code, fn):
    try:
        fn()
    except Exception as ex:
        ok(label + ' raises', True)
        ok(label + ' code', getattr(ex, 'code', None) == code)
    else:
        ok(label + ' raises', False)


def u1p(i):
    return struct.pack('>B', i)


def u2p(i):
    return struct.pack('>H', i)


def u4p(i):
    return struct.pack('>I', i)


def cu(s):
    b = s.encode('utf-8') if isinstance(s, str) else s
    return b'\x01' + u2p(len(b)) + b


class CP:
    def __init__(self):
        self.ents = [None]

    def add(self, e):
        self.ents.append(e)
        return len(self.ents) - 1

    def wide(self, e):
        i = self.add(e)
        self.ents.append(None)
        return i

    def utf(self, s):
        return self.add(cu(s))

    def cls(self, name):
        return self.add(b'\x07' + u2p(self.utf(name)))

    def nat(self, name, desc):
        return self.add(b'\x0c' + u2p(self.utf(name)) + u2p(self.utf(desc)))

    def ref(self, tag, owner, name, desc):
        c = self.cls(owner)
        n = self.nat(name, desc)
        return self.add(bytes([tag]) + u2p(c) + u2p(n))

    def handle(self, kind, ref_idx):
        return self.add(b'\x0f' + bytes([kind]) + u2p(ref_idx))

    def dynamic(self, tag, bsm, name, desc):
        return self.add(bytes([tag]) + u2p(bsm) + u2p(self.nat(name, desc)))

    def methodtype(self, desc):
        return self.add(b'\x10' + u2p(self.utf(desc)))

    def string(self, s):
        return self.add(b'\x08' + u2p(self.utf(s)))

    def integer(self, n=0):
        return self.add(b'\x03' + struct.pack('>i', n))

    def float(self, n=0.0):
        return self.add(b'\x04' + struct.pack('>f', n))

    def longint(self, n=0):
        return self.wide(b'\x05' + struct.pack('>q', n))

    def double(self, n=0.0):
        return self.wide(b'\x06' + struct.pack('>d', n))

    def count(self):
        return len(self.ents)


def assemble(ents, body):
    return bytes([0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 61]) + u2p(len(ents)) \
        + b''.join(e for e in ents[1:] if e is not None) + body


def attr(cp, name, body):
    return u2p(cp.utf(name)) + u4p(len(body)) + body


def annotation(cp, antype, pairs):
    body = u2p(cp.utf(antype)) + u2p(len(pairs))
    for name, ev in pairs:
        body += u2p(cp.utf(name)) + ev
    return body


def ev_class(cp, raw_desc):
    return b'c' + u2p(cp.utf(raw_desc))


def ev_const(cp, tag, idx):
    return bytes([ord(tag)]) + u2p(idx)


def ev_enum(cp, tdesc, cname):
    return b'e' + u2p(cp.utf(tdesc)) + u2p(cp.utf(cname))


def ev_nested(body):
    return b'@' + body


def ev_array(items):
    return b'[' + u2p(len(items)) + b''.join(items)


def type_annotation(cp, target, info, antype, pairs, path=()):
    body = bytes([target]) + info + bytes([len(path)])
    for kind, arg in path:
        body += bytes([kind, arg])
    return body + annotation(cp, antype, pairs)


def mkfield(cp, name, desc, attrs=()):
    return struct.pack('>HHHH', 1, cp.utf(name), cp.utf(desc), len(attrs)) + b''.join(attrs)


def mkmethod(cp, name, desc, attrs=()):
    return struct.pack('>HHHH', 1, cp.utf(name), cp.utf(desc), len(attrs)) + b''.join(attrs)


def mkclass(cp, own, class_attrs=(), methods=(), fields=(), super_name='java/lang/Object'):
    c_own = cp.cls(own)
    c_sup = cp.cls(super_name)
    body = struct.pack('>HHHHH', 0x21, c_own, c_sup, 0, len(fields))
    for f in fields:
        body += f
    body += u2p(len(methods))
    for mm in methods:
        body += mm
    body += u2p(len(class_attrs)) + b''.join(class_attrs)
    return assemble(cp.ents, body)


def blank_out():
    return {
        'own': '', 'member_refs': set(), 'class_refs': set(), 'framework': [],
        'method_handles': 0, 'dynamic': [], 'dynamic_constants': 0,
        'bootstrap_methods': 0, 'bootstrap_args': [], 'bootstrap_refs': set(),
        'nested_dynamic_args': 0, 'annotation_attrs': [], 'bootstrap_seen': False,
    }


def write(path, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    path.write_bytes(data)
    return path


def write_lines(path, rows):
    return write(path, ('\n'.join(rows) + '\n').encode('utf-8') if rows else b'')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mkjar(path, classes, resources=()):
    with zipfile.ZipFile(path, 'w') as z:
        for name in sorted(classes):
            z.writestr(name, classes[name])
        for name, data in resources:
            z.writestr(name, data)
    return path


def ns(**kw):
    d = dict(decl='decl.tsv', modjar='mod.jar', map=None, version=None,
             decl_sha256=None, game_prefix=[], allow_third_party=False,
             coverage_only=False, out=None, summary=None)
    d.update(kw)
    return argparse.Namespace(**d)


def args_of(n):
    a = ['--decl', str(n.decl), '--modjar', str(n.modjar)]
    if n.map:
        a += ['--map', str(n.map)]
    if n.version:
        a += ['--version', str(n.version)]
    if n.decl_sha256:
        a += ['--decl-sha256', str(n.decl_sha256)]
    for p in n.game_prefix:
        a += ['--game-prefix', str(p)]
    if n.allow_third_party:
        a += ['--allow-third-party']
    if n.coverage_only:
        a += ['--coverage-only']
    if n.out:
        a += ['--out', str(n.out)]
    if n.summary:
        a += ['--summary', str(n.summary)]
    return a


def cli(*args):
    return subprocess.run([PY, str(TOOLS / 'linkage_surface.py'), *map(str, args)],
                          env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8')


def cli_rc(label, expected, *args):
    p = cli(*args)
    ok(label + ' rc', p.returncode == expected)
    ok(label + ' no traceback', 'Traceback' not in p.stderr)
    return p


SIMPLE_DECL = [
    'C\tnet/minecraft/Foo',
    'M\tnet/minecraft/Foo\thello\t()Ljava/lang/String;',
]


def build_simple(own='t/Fixture'):
    cp = CP()
    r = cp.ref(10, 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;')
    cp.handle(6, r)
    return mkclass(cp, own)


def build_empty():
    return mkclass(CP(), 't/Fixture')


def good_paths(T):
    decl = write_lines(T / 'decl.tsv', SIMPLE_DECL)
    jar = mkjar(T / 'good.jar', {'t/Fixture.class': build_simple()})
    return decl, jar


def good_ns(T):
    decl, jar = good_paths(T)
    return ns(decl=str(decl), modjar=str(jar), version='1.20.1', decl_sha256=sha(decl))


def build_framework():
    cp = CP()
    r = cp.ref(10, 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;')
    cp.handle(6, r)
    body = u2p(1) + annotation(cp, 'Lt/Ann;', [('value', ev_class(cp, 'Lnet/minecraft/Foo;'))])
    return mkclass(cp, 't/Fixture', [attr(cp, 'RuntimeVisibleAnnotations', body)])


def build_dynamic():
    cp = CP()
    r = cp.ref(10, 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;')
    cp.handle(6, r)
    boot = cp.handle(6, cp.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    cp.dynamic(18, 0, 'get', '()V')
    body = u2p(1) + u2p(boot) + u2p(0)
    return mkclass(cp, 't/Fixture', [attr(cp, 'BootstrapMethods', body)])


def build_third_party():
    cp = CP()
    cp.handle(6, cp.ref(10, 'vendor/lib/Api', 'call', '()V'))
    return mkclass(cp, 't/Fixture')


def build_external_only():
    cp = CP()
    cp.handle(6, cp.ref(10, 'java/lang/Object', 'toString', '()Ljava/lang/String;'))
    return mkclass(cp, 't/Fixture')


def build_self_and_game():
    cp = CP()
    cp.handle(6, cp.ref(10, 't/Fixture', 'self', '()V'))
    cp.handle(6, cp.ref(10, 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;'))
    return mkclass(cp, 't/Fixture')


def build_rename():
    cp = CP()
    cp.handle(6, cp.ref(10, 'net/minecraft/Old', 'moved', '(Lnet/minecraft/Old;)V'))
    return mkclass(cp, 't/Fixture')


def build_class_missing():
    cp = CP()
    boot = cp.handle(6, cp.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    cls = cp.cls('net/minecraft/Absent')
    body = u2p(1) + u2p(boot) + u2p(1) + u2p(cls)
    return mkclass(cp, 't/Fixture', [attr(cp, 'BootstrapMethods', body)])


def build_full():
    cp = CP()
    h_game = cp.handle(6, cp.ref(10, 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;'))
    h_boot = cp.handle(6, cp.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    cp.dynamic(18, 0, 'get', '()V')
    nested_dyn = cp.dynamic(17, 0, 'nested', 'I')
    cls_arg = cp.cls('net/minecraft/Foo')
    mt_arg = cp.methodtype('()Lnet/minecraft/Foo;')
    str_arg = cp.string('x')
    int_arg = cp.integer(0)
    long_arg = cp.longint(1)
    flt_arg = cp.float(1.0)
    dbl_arg = cp.double(2.0)
    bsm_body = u2p(1) + u2p(h_boot) + u2p(9) + u2p(cls_arg) + u2p(mt_arg) \
        + u2p(str_arg) + u2p(int_arg) + u2p(long_arg) + u2p(flt_arg) \
        + u2p(dbl_arg) + u2p(h_game) + u2p(nested_dyn)
    simple = u2p(1) + annotation(cp, 'Lt/Ann;', [('value', ev_class(cp, 'Lnet/minecraft/Foo;'))])
    invisible = u2p(1) + annotation(cp, 'Lt/Ann;', [('value', ev_class(cp, 'V'))])
    param = bytes([1]) + u2p(1) + annotation(cp, 'Lt/Ann;', [('value', ev_class(cp, 'I'))])
    typ = u2p(1) + type_annotation(cp, 0x13, b'', 'Lt/Ann;', [
        ('value', ev_array([
            ev_class(cp, '[Lnet/minecraft/Bar;'),
            ev_nested(annotation(cp, 'Lt/Ann;', [('value', ev_class(cp, 'Lnet/minecraft/Baz;'))])),
        ]))
    ], path=((0, 0),))
    default = ev_array([
        ev_class(cp, 'Lnet/minecraft/Quux;'),
        ev_enum(cp, 'Lt/E;', 'VALUE'),
        ev_const(cp, 's', cp.utf('text')),
        ev_nested(annotation(cp, 'Lt/Ann;', [('value', ev_class(cp, 'Lnet/minecraft/Quux2;'))])),
        ev_const(cp, 'I', cp.integer(7)),
    ])
    field_ann = u2p(1) + annotation(cp, 'Lt/Ann;', [('value', ev_class(cp, 'Lnet/minecraft/Field;'))])
    method_ann = u2p(1) + annotation(cp, 'Lt/Ann;', [('value', ev_class(cp, 'Lnet/minecraft/Method;'))])
    code_ann = u2p(1) + type_annotation(cp, 0x13, b'', 'Lt/Ann;', [
        ('value', ev_class(cp, 'Lnet/minecraft/Code;'))
    ])
    code_body = u2p(0) + u2p(0) + u4p(1) + b'\xb1' + u2p(0) + u2p(1) \
        + attr(cp, 'RuntimeVisibleTypeAnnotations', code_ann)
    class_attrs = [
        attr(cp, 'BootstrapMethods', bsm_body),
        attr(cp, 'RuntimeVisibleAnnotations', simple),
        attr(cp, 'RuntimeInvisibleAnnotations', invisible),
        attr(cp, 'RuntimeVisibleParameterAnnotations', param),
        attr(cp, 'RuntimeVisibleTypeAnnotations', typ),
        attr(cp, 'AnnotationDefault', default),
    ]
    methods = [mkmethod(cp, 'm', '()V', [
        attr(cp, 'Code', code_body),
        attr(cp, 'RuntimeVisibleAnnotations', method_ann),
    ])]
    fields = [mkfield(cp, 'f', 'I', [
        attr(cp, 'RuntimeInvisibleAnnotations', field_ann),
    ])]
    return mkclass(cp, 't/Fixture', class_attrs, methods, fields)


def build_bad_magic():
    return b'not a class file'


def build_truncated_body():
    cp = CP()
    cp.cls('t/T')
    cp.cls('java/lang/Object')
    return assemble(cp.ents, b'\x00' * 10)


def build_bad_utf8():
    cp = CP()
    bad = cp.add(b'\x01\x00\x01\xff')
    own = cp.add(b'\x07' + u2p(bad))
    sup = cp.cls('java/lang/Object')
    body = struct.pack('>HHHHH', 0x21, own, sup, 0, 0) + u2p(0) + u2p(0)
    return assemble(cp.ents, body)


def build_bad_handle(kind=6, target_tag=10, name='hello', desc='()Ljava/lang/String;'):
    cp = CP()
    if target_tag == 3:
        idx = cp.integer(0)
    else:
        idx = cp.ref(target_tag, 'net/minecraft/Foo', name, desc)
    cp.handle(kind, idx)
    return mkclass(cp, 't/Fixture')


def build_bad_dynamic(tag=18, desc='()V', name='get', bsm=0, with_bsm=True):
    cp = CP()
    boot = cp.handle(6, cp.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    if tag == 17 or desc.startswith('('):
        cp.dynamic(tag, bsm, name, desc)
    else:
        cp.dynamic(tag, bsm, name, desc)
    attrs = []
    if with_bsm:
        attrs = [attr(cp, 'BootstrapMethods', u2p(1) + u2p(boot) + u2p(0))]
    return mkclass(cp, 't/Fixture', attrs)


def build_bootstrap_body(cp, method_ref, args, extra=b'', duplicate=False):
    body = u2p(1) + u2p(method_ref) + u2p(len(args)) + b''.join(u2p(a) for a in args) + extra
    attrs = [attr(cp, 'BootstrapMethods', body)]
    if duplicate:
        attrs.append(attr(cp, 'BootstrapMethods', body))
    return mkclass(cp, 't/Fixture', attrs)


def build_annotation_body(cp, name, body):
    if name in m.ANNOTATION_SIMPLE:
        body = u2p(1) + body
    return mkclass(cp, 't/Fixture', [attr(cp, name, body)])


def build_code_body(cp, body):
    return mkclass(cp, 't/Fixture', [], [mkmethod(cp, 'm', '()V', [attr(cp, 'Code', body)])])


def audit_with(T, class_bytes, decl_rows=SIMPLE_DECL, **kw):
    decl = write_lines(T / ('decl_' + str(len(list(T.iterdir()))) + '.tsv'), decl_rows)
    jar = mkjar(T / ('mod_' + str(len(list(T.iterdir()))) + '.jar'), {'t/Fixture.class': class_bytes})
    return m.audit(ns(decl=str(decl), modjar=str(jar), **kw))


def main():
    ok('SCHEMA', m.SCHEMA == 1)
    ok('TOOL', m.TOOL == 'mcport.linkage_surface')
    ok('ALLOWED_STATUS', m.ALLOWED_STATUS == ('RESOLVE', 'RENAME', 'MISSING', 'EXTERNAL', 'THIRD_PARTY', 'SELF', 'FRAMEWORK_UNRESOLVED'))
    ok('BLOCK_STATUS', m.BLOCK_STATUS == ('MISSING', 'RENAME', 'FRAMEWORK_UNRESOLVED'))
    ok('EXIT_CODE', m.EXIT_CODE == {'SURFACE_OK': 0, 'SURFACE_ONLY_OK': 0, 'NEEDS_MANUAL': 2, 'UNSUPPORTED': 1})
    ok('HARD_REASONS type', isinstance(m.HARD_REASONS, frozenset))
    for code in ('BAD_METHOD_HANDLE', 'BAD_DYNAMIC_DESCRIPTOR', 'BAD_BOOTSTRAP', 'BAD_BOOTSTRAP_METHOD_REF',
                 'BAD_BOOTSTRAP_ARG_TAG', 'BOOTSTRAP_MISSING', 'BAD_ANNOTATION', 'BAD_ANNOTATION_ELEMENT',
                 'BAD_ANNOTATION_LENGTH', 'BAD_TYPE_ANNOTATION_TARGET', 'BAD_CODE_ATTRIBUTE',
                 'BAD_RETURN_DESCRIPTOR', 'BAD_MODIFIED_UTF8', 'BAD_ARRAY_CLASS', 'BAD_CLASS_NAME',
                 'BAD_DESCRIPTOR', 'BAD_ARRAY_OWNER', 'NO_SURFACE_REFS', 'UNCLASSIFIED_REFS',
                 'DECL_VIEW_CONFLICT', 'MAP_TARGET_MISSING', 'MAPPED_TARGET_MISSING', 'BAD_MAPPED_DESCRIPTOR',
                 'OWN_GAME_NAMESPACE', 'OWN_EXTERNAL_NAMESPACE', 'NO_DECL', 'INTERNAL_ERROR'):
        ok('hard ' + code, code in m.HARD_REASONS)
    for soft in ('THIRD_PARTY_WAIVED', 'FRAMEWORK_CLASS_LITERALS', 'DYNAMIC_BOOTSTRAP_UNPROVEN',
                 'NESTED_DYNAMIC_ARGUMENT', 'NO_GAME_REFS', 'MAPPED_CLASS'):
        ok('soft ' + soft, soft not in m.HARD_REASONS)
    ok('LOADABLE_TAGS', m.LOADABLE_TAGS == frozenset((3, 4, 5, 6, 7, 8, 15, 16, 17)))
    ok('ANNOTATION_SIMPLE', m.ANNOTATION_SIMPLE == frozenset(('RuntimeVisibleAnnotations', 'RuntimeInvisibleAnnotations')))
    ok('ANNOTATION_PARAM', m.ANNOTATION_PARAM == frozenset(('RuntimeVisibleParameterAnnotations', 'RuntimeInvisibleParameterAnnotations')))
    ok('ANNOTATION_TYPE', m.ANNOTATION_TYPE == frozenset(('RuntimeVisibleTypeAnnotations', 'RuntimeInvisibleTypeAnnotations')))
    ok('ANNOTATION_DEFAULT', m.ANNOTATION_DEFAULT == frozenset(('AnnotationDefault',)))
    ok('ANNOTATION_ATTRS', m.ANNOTATION_ATTRS == m.ANNOTATION_SIMPLE | m.ANNOTATION_PARAM | m.ANNOTATION_TYPE | m.ANNOTATION_DEFAULT)
    ok('SUMMARY_COLS len', len(m.SUMMARY_COLS) == 37)
    ok('SUMMARY_COLS unique', len(set(m.SUMMARY_COLS)) == 37)
    ok('LINKAGE_SPEC', m.LINKAGE_SPEC == 'JVMS 5.4.3.5 / 5.4.3.6')
    ok('FRAMEWORK_SPEC', 'framework-resolved' in m.FRAMEWORK_SPEC and 'NOT JVMS link-time' in m.FRAMEWORK_SPEC)
    ok('CLAIM_POLICY', m.CLAIM_POLICY == 'static-linkage-surface-only; no runtime claim')
    ok('DISCLAIMER', 'does NOT mean runtime-compatible' in m.DISCLAIMER)
    ok('SCOPE covers methodhandle', any('tag 15' in s for s in m.SCOPE['covers']))
    ok('SCOPE covers annotation', any('tag c class literals' in s for s in m.SCOPE['covers']))
    ok('SCOPE excludes runtime', any('runtime ClassLoader' in s for s in m.SCOPE['does_not_cover']))
    ok('GAME_PREFIXES', m.GAME_PREFIXES == AUD.GAME_PREFIXES)
    ok('EXTERNAL_PREFIXES', m.EXTERNAL_PREFIXES == AUD.EXTERNAL_PREFIXES)
    ok('docstring JVMS', 'JVMS 4.7.16.1' in m.__doc__ and '5.4.3.5' in m.__doc__)
    ok('SurfaceError code', m.SurfaceError('X', 'y').code == 'X')
    ok('SurfaceError message', str(m.SurfaceError('X', 'y')) == 'y')
    ok('u1p', u1p(255) == b'\xff')
    ok('u2p', u2p(1) == b'\x00\x01')
    ok('u4p', u4p(1) == b'\x00\x00\x00\x01')
    ok('cu', cu('x') == b'\x01\x00\x01x')
    ok('assemble magic', assemble([None], b'').startswith(bytes([0xca, 0xfe, 0xba, 0xbe])))
    ok('strict_code hard', m._strict_code('JAR_IO') == 'JAR_IO')
    ok('strict_code soft', m._strict_code('THIRD_PARTY_WAIVED') == 'BAD_CLASS_FILE')

    cp0 = CP()
    txt = cp0.utf('hello')
    cls_idx = cp0.cls('net/minecraft/Foo')
    arr_idx = cp0.cls('[Lnet/minecraft/Foo;')
    bad_cls = cp0.cls('bad.name')
    bad_arr = cp0.cls('[Lbad')
    int_idx = cp0.integer(7)
    bad_utf = cp0.add(b'\x01\x00\x01\xff')
    ents = cp0.ents
    ok('CP utf', m._utf8(ents, cp0.count(), txt) == 'hello')
    ok('CP class', m._class_name(ents, cp0.count(), cls_idx) == 'net/minecraft/Foo')
    ok('CP array class', m._class_name(ents, cp0.count(), arr_idx) == 'net/minecraft/Foo')
    nat_idx = cp0.nat('n', 'I')
    ok('CP nat', m._nat(ents, cp0.count(), nat_idx) == ('n', 'I'))
    raises_any('utf8 bad index', 'BAD_ANNOTATION', lambda: m._utf8(ents, cp0.count(), 0, 'BAD_ANNOTATION'))
    raises_any('utf8 wrong tag', 'BAD_ANNOTATION', lambda: m._utf8(ents, cp0.count(), cls_idx, 'BAD_ANNOTATION'))
    raises_any('utf8 bad bytes', 'BAD_MODIFIED_UTF8', lambda: m._utf8(ents, cp0.count(), bad_utf, 'BAD_ANNOTATION'))
    raises_any('class bad name', 'BAD_CLASS_NAME', lambda: m._class_name(ents, cp0.count(), bad_cls))
    raises_any('class bad array', 'BAD_ARRAY_CLASS', lambda: m._class_name(ents, cp0.count(), bad_arr))
    raises_any('nat bad tag', 'BAD_CLASS_FILE', lambda: m._nat(ents, cp0.count(), int_idx))
    ok('desc field types', m._desc_object_types('Lnet/minecraft/Foo;') == ['net/minecraft/Foo'])
    ok('desc method types', set(m._desc_object_types('(Lnet/minecraft/Foo;I)Ljava/lang/String;')) == {'net/minecraft/Foo', 'java/lang/String'})
    raises_any('desc invalid', 'BAD_DESCRIPTOR', lambda: m._desc_object_types('()Lbad'))
    ok('return V', m._return_desc_class('V') is None)
    ok('return primitive', m._return_desc_class('I') is None)
    ok('return object', m._return_desc_class('Lnet/minecraft/Foo;') == 'net/minecraft/Foo')
    ok('return object array', m._return_desc_class('[Lnet/minecraft/Foo;') == 'net/minecraft/Foo')
    ok('return primitive array', m._return_desc_class('[I') == 'java/lang/Object')
    raises_any('return invalid', 'BAD_RETURN_DESCRIPTOR', lambda: m._return_desc_class('Lnet/minecraft/Foo'))
    raises_any('return bad array', 'BAD_ARRAY_OWNER', lambda: m._return_desc_class('[Lbad'))

    cp1 = CP()
    r_good = cp1.ref(10, 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;')
    h_good = cp1.handle(6, r_good)
    out = blank_out()
    refs, handles = m._member_refs(cp1.ents, cp1.count(), out)
    ok('member refs set', ('M', 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;') in refs)
    ok('member handles count', handles == 1)
    ok('member desc class ref', ('java/lang/String', 'METHOD_HANDLE_DESCRIPTOR') in out['class_refs'])
    cp2 = CP()
    r_field = cp2.ref(9, 'net/minecraft/Foo', 'field', 'I')
    cp2.handle(1, r_field)
    out2 = blank_out()
    refs2, handles2 = m._member_refs(cp2.ents, cp2.count(), out2)
    ok('field handle ref', ('F', 'net/minecraft/Foo', 'field', 'I') in refs2)
    ok('field handle count', handles2 == 1)
    for label, kind, tag in [('kind0', 0, 10), ('kind10', 10, 10),
                             ('wrong target tag', 6, 3), ('kind5 interface', 5, 11),
                             ('kind8 interface', 8, 11)]:
        c = CP()
        idx = c.integer(0) if tag == 3 else c.ref(tag, 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;')
        c.handle(kind, idx)
        raises_any('member handle ' + label, 'BAD_METHOD_HANDLE',
                   lambda c=c: m._member_refs(c.ents, c.count(), blank_out()))
    for label, cp_bytes in [('bad name', build_bad_handle(name='bad-name')),
                            ('bad desc', build_bad_handle(desc='()Lbad'))]:
        raises_any('parse handle ' + label, 'BAD_METHOD_HANDLE', lambda b=cp_bytes: m.parse_class(b))

    cp3 = CP()
    cp3.dynamic(18, 0, 'get', '()Lnet/minecraft/Foo;')
    cp3.dynamic(17, 0, 'field', 'Lnet/minecraft/Foo;')
    out3 = blank_out()
    total = m._dynamic_entries(cp3.ents, cp3.count(), out3)
    ok('dynamic total', total == 2)
    ok('dynamic list', len(out3['dynamic']) == 2)
    ok('dynamic desc class', ('net/minecraft/Foo', 'DYNAMIC_DESCRIPTOR') in out3['class_refs'])
    for label, b in [('tag17 method desc', build_bad_dynamic(tag=17, desc='()V')),
                     ('tag18 field desc', build_bad_dynamic(tag=18, desc='I')),
                     ('bad name', build_bad_dynamic(tag=18, desc='()V', name='bad-name'))]:
        raises_any('dynamic ' + label, 'BAD_DYNAMIC_DESCRIPTOR', lambda b=b: m.parse_class(b))
    buf = u2p(2) + b'\x00' * 12
    for target, size in [(0x00, 1), (0x01, 1), (0x16, 1), (0x10, 2), (0x11, 2),
                         (0x12, 2), (0x17, 2), (0x42, 2), (0x43, 2), (0x46, 2),
                         (0x13, 0), (0x14, 0), (0x15, 0), (0x47, 3), (0x4B, 3)]:
        ok('target info ' + hex(target), m._target_info_len(buf, 0, target) == size)
    ok('target info localvar', m._target_info_len(buf, 0, 0x40) == 14)
    raises_any('target info unknown', 'BAD_TYPE_ANNOTATION_TARGET', lambda: m._target_info_len(buf, 0, 0x7f))

    cp4 = CP()
    ann = 'Lt/Ann;'
    elem = 'value'
    lit = cp4.utf('Lnet/minecraft/Foo;')
    arr_lit = cp4.utf('[Lnet/minecraft/Bar;')
    void_lit = cp4.utf('V')
    int_idx4 = cp4.integer(5)
    str_idx4 = cp4.utf('text')
    enum_tdesc = cp4.utf('Lt/E;')
    enum_cname = cp4.utf('VALUE')
    ents4 = cp4.ents
    out4 = {'framework': []}
    p = m._read_element_value(ev_class(cp4, 'Lnet/minecraft/Foo;'), 0, ents4, cp4.count(),
                              out4, 'RuntimeVisibleAnnotations', ann, elem)
    ok('element class p', p == 3)
    ok('element class framework', out4['framework'] == [('net/minecraft/Foo', 'Lnet/minecraft/Foo;', 'RuntimeVisibleAnnotations', ann, elem)])
    for raw in ('V', 'I'):
        o = {'framework': []}
        pp = m._read_element_value(b'c' + u2p(cp4.utf(raw)), 0, ents4, cp4.count(), o, 'A', ann, elem)
        ok('element ' + raw + ' no framework', pp == 3 and not o['framework'])
    for tag, idx in [('B', int_idx4), ('C', int_idx4), ('I', int_idx4), ('S', int_idx4),
                     ('Z', int_idx4), ('s', str_idx4)]:
        o = {'framework': []}
        pp = m._read_element_value(bytes([ord(tag)]) + u2p(idx), 0, ents4, cp4.count(), o, 'A', ann, elem)
        ok('element const ' + tag, pp == 3)
    o = {'framework': []}
    pp = m._read_element_value(ev_enum(cp4, 'Lt/E;', 'VALUE'), 0, ents4, cp4.count(), o, 'A', ann, elem)
    ok('element enum p', pp == 5)
    nested = annotation(cp4, ann, [('value', ev_class(cp4, 'Lnet/minecraft/Baz;'))])
    o = {'framework': []}
    pp = m._read_element_value(ev_nested(nested), 0, ents4, cp4.count(), o, 'A', ann, elem)
    ok('element nested framework', len(o['framework']) == 1)
    array = ev_array([ev_class(cp4, 'Lnet/minecraft/A;'), ev_class(cp4, 'Lnet/minecraft/B;')])
    o = {'framework': []}
    pp = m._read_element_value(array, 0, ents4, cp4.count(), o, 'A', ann, elem)
    ok('element array framework', len(o['framework']) == 2)
    o = {'framework': []}
    simple_ann = annotation(cp4, ann, [('value', ev_class(cp4, 'Lnet/minecraft/Foo;'))])
    pp = m._read_annotation(simple_ann, 0, ents4, cp4.count(), o, 'A', False)
    ok('read annotation p', pp == len(simple_ann))
    ok('read annotation framework', len(o['framework']) == 1)
    type_ann = type_annotation(cp4, 0x13, b'', ann, [('value', ev_class(cp4, 'Lnet/minecraft/Type;'))], path=((0, 0),))
    o = {'framework': []}
    pp = m._read_annotation(type_ann, 0, ents4, cp4.count(), o, 'A', True)
    ok('read type annotation p', pp == len(type_ann))
    ok('read type annotation framework', len(o['framework']) == 1)
    for label, body in [('bad const tag', annotation(cp4, ann, [('value', ev_const(cp4, 'I', str_idx4))])),
                        ('bad enum desc', annotation(cp4, ann, [('value', ev_enum(cp4, 'not-a-desc', 'VALUE'))])),
                        ('unknown tag', annotation(cp4, ann, [('value', b'x' + u2p(1))])),
                        ('bad class desc', annotation(cp4, ann, [('value', ev_class(cp4, 'bad'))]))]:
        code = 'BAD_RETURN_DESCRIPTOR' if label == 'bad class desc' else 'BAD_ANNOTATION_ELEMENT'
        raises_any('element ' + label, code,
                   lambda b=body: m._read_annotation(b, 0, cp4.ents, cp4.count(), {'framework': []}, 'A', False))
    bad_antype = annotation(cp4, 'not-a-desc', [])
    raises_any('annotation bad type', 'BAD_ANNOTATION',
               lambda: m._read_annotation(bad_antype, 0, cp4.ents, cp4.count(), {'framework': []}, 'A', False))

    cp5 = CP()
    simple5 = u2p(1) + annotation(cp5, ann, [('value', ev_class(cp5, 'Lnet/minecraft/Foo;'))])
    param5 = bytes([1]) + u2p(1) + annotation(cp5, ann, [('value', ev_class(cp5, 'V'))])
    type5 = u2p(1) + type_annotation(cp5, 0x13, b'', ann, [('value', ev_class(cp5, 'I'))])
    default5 = ev_array([ev_class(cp5, 'Lnet/minecraft/Default;')])
    o5 = blank_out()
    m._parse_annotation_attr('RuntimeVisibleAnnotations', simple5, cp5.ents, cp5.count(), o5)
    m._parse_annotation_attr('RuntimeInvisibleParameterAnnotations', param5, cp5.ents, cp5.count(), o5)
    m._parse_annotation_attr('RuntimeVisibleTypeAnnotations', type5, cp5.ents, cp5.count(), o5)
    m._parse_annotation_attr('AnnotationDefault', default5, cp5.ents, cp5.count(), o5)
    ok('annotation attrs count', len(o5['annotation_attrs']) == 4)
    ok('annotation framework count', len(o5['framework']) == 2)
    raises_any('annotation length mismatch', 'BAD_ANNOTATION_LENGTH',
               lambda: m._parse_annotation_attr('RuntimeVisibleAnnotations', simple5 + b'\x00', cp5.ents, cp5.count(), blank_out()))
    bad_target = u2p(1) + type_annotation(cp5, 0x7f, b'', ann, [])
    raises_any('annotation bad target', 'BAD_TYPE_ANNOTATION_TARGET',
               lambda: m._parse_annotation_attr('RuntimeVisibleTypeAnnotations', bad_target, cp5.ents, cp5.count(), blank_out()))

    cp6 = CP()
    h6 = cp6.handle(6, cp6.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    cls6 = cp6.cls('net/minecraft/Foo')
    mt6 = cp6.methodtype('()Lnet/minecraft/Foo;')
    str6 = cp6.string('x')
    int6 = cp6.integer(0)
    long6 = cp6.longint(1)
    flt6 = cp6.float(1.0)
    dbl6 = cp6.double(2.0)
    dyn6 = cp6.dynamic(17, 0, 'nested', 'I')
    args6 = [cls6, mt6, str6, int6, long6, flt6, dbl6, h6, dyn6]
    body6 = u2p(1) + u2p(h6) + u2p(len(args6)) + b''.join(u2p(a) for a in args6)
    o6 = blank_out()
    n6 = m._parse_bootstrap_methods(body6, cp6.ents, cp6.count(), o6)
    ok('bootstrap methods count', n6 == 1)
    ok('bootstrap args count', len(o6['bootstrap_args']) == len(args6))
    ok('bootstrap refs', h6 in o6['bootstrap_refs'])
    ok('bootstrap class ref', ('net/minecraft/Foo', 'BOOTSTRAP_CLASS') in o6['class_refs'])
    ok('bootstrap methodtype ref', ('net/minecraft/Foo', 'BOOTSTRAP_METHODTYPE') in o6['class_refs'])
    ok('nested dynamic args', o6['nested_dynamic_args'] == 1)
    utf6 = cp6.utf('not-a-handle')
    bad_ref_body = u2p(1) + u2p(utf6) + u2p(0)
    raises_any('bootstrap bad method ref', 'BAD_BOOTSTRAP_METHOD_REF',
               lambda: m._parse_bootstrap_methods(bad_ref_body, cp6.ents, cp6.count(), blank_out()))
    bad_arg_body = u2p(1) + u2p(h6) + u2p(1) + u2p(utf6)
    raises_any('bootstrap bad arg tag', 'BAD_BOOTSTRAP_ARG_TAG',
               lambda: m._parse_bootstrap_methods(bad_arg_body, cp6.ents, cp6.count(), blank_out()))
    bad_len_body = body6 + b'\x00'
    raises_any('bootstrap length mismatch', 'BAD_BOOTSTRAP',
               lambda: m._parse_bootstrap_methods(bad_len_body, cp6.ents, cp6.count(), blank_out()))
    indy6 = cp6.dynamic(18, 0, 'get', '()V')
    bad_loadable = u2p(1) + u2p(h6) + u2p(1) + u2p(indy6)
    raises_any('bootstrap tag18 not loadable', 'BAD_BOOTSTRAP_ARG_TAG',
               lambda: m._parse_bootstrap_methods(bad_loadable, cp6.ents, cp6.count(), blank_out()))

    cp7 = CP()
    code_ann7 = u2p(1) + type_annotation(cp7, 0x13, b'', ann, [('value', ev_class(cp7, 'Lnet/minecraft/Code;'))])
    nested7 = attr(cp7, 'RuntimeVisibleTypeAnnotations', code_ann7)
    good_code = u2p(0) + u2p(0) + u4p(1) + b'\xb1' + u2p(0) + u2p(1) + nested7
    o7 = blank_out()
    p7 = m._walk_code(good_code, cp7.ents, cp7.count(), o7)
    ok('walk code p', p7 == len(good_code))
    ok('walk code nested annotation', 'RuntimeVisibleTypeAnnotations' in o7['annotation_attrs'])
    bad_code = good_code + b'\x00'
    raises_any('walk code length mismatch', 'BAD_CODE_ATTRIBUTE',
               lambda: m._walk_code(bad_code, cp7.ents, cp7.count(), blank_out()))
    cp8 = CP()
    h8 = cp8.handle(6, cp8.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    bsm8 = u2p(1) + u2p(h8) + u2p(0)
    a8 = attr(cp8, 'BootstrapMethods', bsm8)
    o8 = blank_out()
    m._walk_attrs(a8, 0, 1, cp8.ents, cp8.count(), o8)
    ok('walk attrs bootstrap seen', o8['bootstrap_seen'] is True)
    raises_any('walk attrs duplicate bootstrap', 'BAD_BOOTSTRAP_DUPLICATE',
               lambda: m._walk_attrs(a8 + a8, 0, 2, cp8.ents, cp8.count(), blank_out()))

    full = m.parse_class(build_full())
    ok('full own', full['own'] == 't/Fixture')
    ok('full member refs', len(full['member_refs']) == 2)
    ok('full method handles', full['method_handles'] == 2)
    ok('full dynamic constants', full['dynamic_constants'] == 2)
    ok('full bootstrap methods', full['bootstrap_methods'] == 1)
    ok('full bootstrap args', len(full['bootstrap_args']) == 9)
    ok('full nested dynamic args', full['nested_dynamic_args'] == 1)
    ok('full framework literals', len(full['framework']) >= 6)
    ok('full annotation attrs', len(full['annotation_attrs']) == 8)
    ok('full annotation attr names', Counter(full['annotation_attrs']) == Counter({
        'RuntimeVisibleAnnotations': 2, 'RuntimeInvisibleAnnotations': 2,
        'RuntimeVisibleParameterAnnotations': 1, 'RuntimeVisibleTypeAnnotations': 2,
        'AnnotationDefault': 1}))
    ok('full bootstrap seen', full['bootstrap_seen'] is True)
    ok('full bootstrap refs', len(full['bootstrap_refs']) >= 1)
    ok('full class refs', any(c == 'net/minecraft/Foo' and o == 'BOOTSTRAP_CLASS' for c, o in full['class_refs']))
    ok('full framework raw array', any('[Lnet/minecraft/Bar;' == raw for _c, raw, _a, _t, _e in full['framework']))
    for label, b, code in [
        ('bad magic', build_bad_magic(), 'BAD_CLASS_FILE'),
        ('truncated body', build_truncated_body(), 'BAD_CLASS_FILE'),
        ('bad utf8', build_bad_utf8(), 'BAD_MODIFIED_UTF8'),
        ('handle bad name', build_bad_handle(name='bad-name'), 'BAD_METHOD_HANDLE'),
        ('dynamic tag17 method desc', build_bad_dynamic(tag=17, desc='()V'), 'BAD_DYNAMIC_DESCRIPTOR'),
        ('dynamic tag18 field desc', build_bad_dynamic(tag=18, desc='I'), 'BAD_DYNAMIC_DESCRIPTOR'),
        ('bootstrap missing', build_bad_dynamic(tag=18, desc='()V', with_bsm=False), 'BOOTSTRAP_MISSING'),
        ('bootstrap index', build_bad_dynamic(tag=18, desc='()V', bsm=5), 'BAD_BOOTSTRAP_INDEX'),
        ('bootstrap bad ref', build_bootstrap_body(CP(), CP().utf('x'), []) if False else None, None),
    ]:
        if b is None:
            continue
        raises_any('parse ' + label, code, lambda b=b: m.parse_class(b))
    cp9 = CP()
    bad_ref9 = cp9.utf('not-a-handle')
    raises_any('parse bootstrap bad ref', 'BAD_BOOTSTRAP_METHOD_REF',
               lambda: m.parse_class(build_bootstrap_body(cp9, bad_ref9, [])))
    cp10 = CP()
    h10 = cp10.handle(6, cp10.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    bad_arg10 = cp10.utf('x')
    raises_any('parse bootstrap bad arg', 'BAD_BOOTSTRAP_ARG_TAG',
               lambda: m.parse_class(build_bootstrap_body(cp10, h10, [bad_arg10])))
    cp11 = CP()
    h11 = cp11.handle(6, cp11.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    raises_any('parse bootstrap length', 'BAD_BOOTSTRAP',
               lambda: m.parse_class(build_bootstrap_body(cp11, h11, [], extra=b'\x00')))
    cp12 = CP()
    h12 = cp12.handle(6, cp12.ref(10, 'java/lang/invoke/Boot', 'boot', '()V'))
    raises_any('parse bootstrap duplicate', 'BAD_BOOTSTRAP_DUPLICATE',
               lambda: m.parse_class(build_bootstrap_body(cp12, h12, [], duplicate=True)))
    cp13 = CP()
    bad_ann13 = annotation(cp13, 'not-a-desc', [])
    raises_any('parse annotation bad type', 'BAD_ANNOTATION',
               lambda: m.parse_class(build_annotation_body(cp13, 'RuntimeVisibleAnnotations', bad_ann13)))
    cp14 = CP()
    unknown14 = annotation(cp14, ann, [('value', b'x' + u2p(1))])
    raises_any('parse annotation unknown tag', 'BAD_ANNOTATION_ELEMENT',
               lambda: m.parse_class(build_annotation_body(cp14, 'RuntimeVisibleAnnotations', unknown14)))
    cp15 = CP()
    bad_class15 = annotation(cp15, ann, [('value', ev_class(cp15, 'bad'))])
    raises_any('parse annotation bad class', 'BAD_RETURN_DESCRIPTOR',
               lambda: m.parse_class(build_annotation_body(cp15, 'RuntimeVisibleAnnotations', bad_class15)))
    cp16 = CP()
    length16 = annotation(cp16, ann, []) + b'\x00'
    raises_any('parse annotation length', 'BAD_ANNOTATION_LENGTH',
               lambda: m.parse_class(build_annotation_body(cp16, 'RuntimeVisibleAnnotations', length16)))
    cp17 = CP()
    bad_target17 = u2p(1) + type_annotation(cp17, 0x7f, b'', ann, [])
    raises_any('parse annotation bad target', 'BAD_TYPE_ANNOTATION_TARGET',
               lambda: m.parse_class(build_annotation_body(cp17, 'RuntimeVisibleTypeAnnotations', bad_target17)))
    cp18 = CP()
    code18 = u2p(0) + u2p(0) + u4p(1) + b'\xb1' + u2p(0) + u2p(0) + b'\x00'
    raises_any('parse code length', 'BAD_CODE_ATTRIBUTE',
               lambda: m.parse_class(build_code_body(cp18, code18)))

    with tempfile.TemporaryDirectory(prefix='mcport-linkage-surface-') as td:
        T = pathlib.Path(td)
        decl, jar = good_paths(T)
        per = m.scan_jar(str(jar))
        ok('scan_jar one class', len(per) == 1)
        ok('scan_jar sorted name', per[0][0] == 't/Fixture.class')
        agg = m.aggregate(per)
        ok('aggregate own', agg['own'] == {'t/Fixture'})
        ok('aggregate members', agg['members'][('M', 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;')] == 1)
        ok('aggregate class refs', agg['classes']['java/lang/String'] == 1)
        ok('aggregate origins', 'METHOD_HANDLE' in agg['member_origins'][('M', 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;')])
        two_jar = mkjar(T / 'two.jar', {
            't/B.class': build_simple(), 't/A.class': build_simple(),
        })
        per2 = m.scan_jar(str(two_jar))
        ok('scan_jar sorted entries', [n for n, _ in per2] == ['t/A.class', 't/B.class'])
        agg2 = m.aggregate(per2)
        ok('aggregate two own', agg2['own'] == {'t/Fixture'})
        ok('aggregate two members', agg2['members'][('M', 'net/minecraft/Foo', 'hello', '()Ljava/lang/String;')] == 2)
        no_class = mkjar(T / 'no-class.jar', {}, resources=[('META-INF/MANIFEST.MF', b'Manifest-Version: 1.0\n')])
        raises_any('scan_jar no class entries', 'NO_CLASS_ENTRIES', lambda: m.scan_jar(str(no_class)))
        dup = T / 'duplicate.jar'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(dup, 'w') as z:
                z.writestr('a.class', build_simple())
                z.writestr('a.class', build_simple())
        raises_any('scan_jar duplicate', 'DUPLICATE_CLASS_ENTRY', lambda: m.scan_jar(str(dup)))
        bad_zip = write(T / 'bad.jar', b'not a zip')
        raises_any('scan_jar bad zip', 'JAR_IO', lambda: m.scan_jar(str(bad_zip)))
        raises_any('scan_jar missing', 'JAR_IO', lambda: m.scan_jar(str(T / 'missing.jar')))

        raw, text = m.read_text(str(decl), 'DECL')
        ok('read_text raw', raw == decl.read_bytes())
        ok('read_text text', 'net/minecraft/Foo' in text)
        raises_any('read_text missing', 'DECL_IO', lambda: m.read_text(str(T / 'nope.tsv'), 'DECL'))
        bad_utf = write(T / 'bad-utf8.tsv', b'\xff')
        raises_any('read_text bad utf8', 'DECL_BAD_UTF8', lambda: m.read_text(str(bad_utf), 'DECL'))

        decl_full = write_lines(T / 'decl-full.tsv', [
            '# comment', '', 'C\tnet/minecraft/Foo',
            'S\tnet/minecraft/Foo\tjava/lang/Object',
            'M\tnet/minecraft/Foo\thello\t()Ljava/lang/String;',
            'F\tnet/minecraft/Foo\tvalue\tI',
        ])
        d = m.parse_decl(str(decl_full))
        ok('parse_decl rows', d['rows'] == 4)
        ok('parse_decl kinds', d['kinds'] == {'C': 1, 'S': 1, 'M': 1, 'F': 1})
        ok('parse_decl members', len(d['members']) == 2)
        ok('parse_decl classes', d['classes'] == {'net/minecraft/Foo'})
        ok('parse_decl sha', d['sha256'] == sha(decl_full))
        def decl_case(label, code, rows):
            p = write_lines(T / (label + '.tsv'), rows)
            raises_any('decl ' + label, code, lambda: m.parse_decl(str(p)))
        decl_case('bad-kind', 'DECL_BAD_ROW', ['X\tfoo'])
        decl_case('c-cols', 'DECL_BAD_ROW', ['C\tnet/minecraft/Foo\textra'])
        decl_case('s-cols', 'DECL_BAD_ROW', ['S\tnet/minecraft/Foo\ta\tb\tc'])
        decl_case('m-cols', 'DECL_BAD_ROW', ['M\tnet/minecraft/Foo\thello\t()V\textra'])
        decl_case('bad-owner', 'DECL_BAD_OWNER', ['C\tbad.name'])
        decl_case('bad-member', 'DECL_BAD_MEMBER', ['M\tnet/minecraft/Foo\tbad-name\t()V'])
        decl_case('bad-desc', 'DECL_BAD_DESC', ['M\tnet/minecraft/Foo\thello\t()Lbad'])
        decl_case('empty', 'DECL_NO_CLASSES', ['# only a comment'])
        raises_any('decl missing', 'DECL_IO', lambda: m.parse_decl(str(T / 'missing-decl.tsv')))
        raises_any('decl bad utf8', 'DECL_BAD_UTF8', lambda: m.parse_decl(str(bad_utf)))

        map_ok = write_lines(T / 'map-ok.tsv', [
            'C\tnet/minecraft/Old\tnet/minecraft/Foo',
            'M\tnet/minecraft/Old\tmoved\t()V',
            'F\tnet/minecraft/Old\tfield\tI',
            'S\tnet/minecraft/Old\tnet/minecraft/Foo',
        ])
        mp = m.parse_map(str(map_ok), {'net/minecraft/Foo'})
        ok('parse_map cmap', mp['cmap'] == {'net/minecraft/Old': 'net/minecraft/Foo'})
        ok('parse_map rows', mp['rows'] == 1)
        ok('parse_map ignored', mp['ignored'] == 3)
        ok('parse_map sha', mp['sha256'] == sha(map_ok))
        ok('parse_map bad targets', mp['bad_targets'] == [])
        map_missing = write_lines(T / 'map-missing.tsv', ['C\tnet/minecraft/Old\tnet/minecraft/Absent'])
        ok('parse_map missing target', m.parse_map(str(map_missing), {'net/minecraft/Foo'})['bad_targets'] == ['net/minecraft/Absent'])
        for label, code, rows in [
            ('bad-row', 'MAP_BAD_ROW', ['X\ta\tb']),
            ('bad-owner', 'MAP_BAD_OWNER', ['C\tnet/minecraft/Old\tbad.name']),
            ('conflict', 'MAP_CONFLICT', ['C\tnet/minecraft/Old\tnet/minecraft/Foo', 'C\tnet/minecraft/Old\tnet/minecraft/Bar']),
        ]:
            p = write_lines(T / ('map-' + label + '.tsv'), rows)
            raises_any('map ' + label, code, lambda: m.parse_map(str(p), {'net/minecraft/Foo', 'net/minecraft/Bar'}))
        raises_any('map missing', 'MAP_IO', lambda: m.parse_map(str(T / 'missing-map.tsv'), {'net/minecraft/Foo'}))
        raises_any('map bad utf8', 'MAP_BAD_UTF8', lambda: m.parse_map(str(bad_utf), {'net/minecraft/Foo'}))
        cmap = {'net/minecraft/Old': 'net/minecraft/Foo'}
        ok('map_descriptor method', m.map_descriptor('(Lnet/minecraft/Old;)V', cmap) == '(Lnet/minecraft/Foo;)V')
        ok('map_descriptor field', m.map_descriptor('Lnet/minecraft/Old;', cmap) == 'Lnet/minecraft/Foo;')
        ok('map_descriptor unchanged', m.map_descriptor('()V', cmap) == '()V')
        raises_any('map_descriptor invalid', 'BAD_MAPPED_DESCRIPTOR',
                   lambda: m.map_descriptor('Lnet/minecraft/Old;', {'net/minecraft/Old': 'bad.name'}))
        ok('classify_owner self', m.classify_owner('t/T', {'t/T'}, set(), {}, ['net/minecraft/'])[0] == 'SELF')
        ok('classify_owner external', m.classify_owner('java/lang/Object', set(), set(), {}, ['net/minecraft/'])[0] == 'EXTERNAL')
        ok('classify_owner resolve', m.classify_owner('net/minecraft/Foo', set(), {'net/minecraft/Foo'}, {}, ['net/minecraft/'])[0] == 'RESOLVE')
        ok('classify_owner rename', m.classify_owner('net/minecraft/Old', set(), {'net/minecraft/Foo'}, cmap, ['net/minecraft/'])[0] == 'RENAME')
        ok('classify_owner mapped reason', m.classify_owner('net/minecraft/Old', set(), {'net/minecraft/Foo'}, cmap, ['net/minecraft/'])[3] == 'MAPPED_CLASS')
        ok('classify_owner third', m.classify_owner('vendor/lib/Api', set(), set(), {}, ['net/minecraft/'])[0] == 'THIRD_PARTY')
        cls = m.classify(agg, m.parse_decl(str(decl)), {'cmap': {}, 'bad_targets': []}, list(m.GAME_PREFIXES), False)
        ok('classify reasons empty', cls['reasons'] == set())
        ok('classify refs sorted', cls['refs'] == sorted(cls['refs'], key=lambda r: (r['bucket'], r['kind'], r['owner'], r['name'], r['desc'])))
        ok('classify buckets', {r['bucket'] for r in cls['refs']} == {'CLASS_SURFACE', 'LINKAGE'})

        base = m.base_report(good_ns(T))
        ok('base report verdict', base['verdict'] == 'UNSUPPORTED')
        ok('base report reasons', base['reasons'] == [])
        ok('base report counts', set(base['counts_by_status']) == set(m.ALLOWED_STATUS))
        ok('base report scope', base['scope'] == m.SCOPE)
        ok('base report claim', base['claim_policy'] == m.CLAIM_POLICY)
        ok('base report linkage spec', base['linkage_spec'] == m.LINKAGE_SPEC)
        ok('base report framework spec', base['framework_spec'] == m.FRAMEWORK_SPEC)
        ok('base report disclaimer', base['disclaimer'] == m.DISCLAIMER)
        ok('base report error', base['error'] == '')

        good = m.audit(good_ns(T))
        ok('good verdict', good['verdict'] == 'SURFACE_OK')
        ok('good reasons', good['reasons'] == [])
        ok('good error', good['error'] == '')
        ok('good decl digest', good['decl_digest_ok'] is True)
        ok('good decl view', good['decl_view_conflict'] is False)
        ok('good decl rows', good['decl_rows'] == 2)
        ok('good decl members', good['decl_members'] == 1)
        ok('good classes', good['classes'] == 1)
        ok('good member refs', good['member_refs'] == 1)
        ok('good member unique', good['member_unique'] == 1)
        ok('good method handles', good['method_handles'] == 1)
        ok('good bootstrap methods', good['bootstrap_methods'] == 0)
        ok('good dynamic constants', good['dynamic_constants'] == 0)
        ok('good framework literals', good['framework_literals'] == 0)
        ok('good annotation attrs', good['annotation_attributes'] == {})
        ok('good class surface', good['class_surface_refs'] == 1)
        ok('good own classes', good['own_classes'] == 1)
        ok('good own game', good['own_game_classes'] == [])
        ok('good own external', good['own_external_classes'] == [])
        ok('good resolve', good['counts_by_status']['RESOLVE'] == 1)
        ok('good external', good['counts_by_status']['EXTERNAL'] == 1)
        ok('good no missing', good['counts_by_status']['MISSING'] == 0)
        ok('good no framework unresolved', good['counts_by_status']['FRAMEWORK_UNRESOLVED'] == 0)
        ok('good needs manual', good['needs_manual'] == 0)
        ok('good refs', len(good['refs']) == 2)
        ok('good samples', good['samples_by_status']['RESOLVE'] == ['M|net/minecraft/Foo|hello|()Ljava/lang/String;'])
        ok('good mapped_to', good['mapped_to'] == {})
        ok('good version', good['version'] == '1.20.1')
        ok('good flags', good['allow_third_party'] is False and good['coverage_only'] is False)
        ok('good game prefixes', good['game_prefixes'] == sorted(set(m.GAME_PREFIXES)))
        ok('good stdout disclaimer', m.DISCLAIMER in m.stdout_line(good))
        ok('good stdout verdict', 'verdict=SURFACE_OK' in m.stdout_line(good))

        bad_version = m.audit(ns(decl=str(decl), modjar=str(jar), version='1.20 1'))
        ok('bad version reason', 'BAD_VERSION' in bad_version['reasons'])
        ok('bad version verdict', bad_version['verdict'] == 'UNSUPPORTED')
        bad_sha_fmt = m.audit(ns(decl=str(decl), modjar=str(jar), decl_sha256='xyz'))
        ok('bad sha format', 'BAD_DECL_SHA256' in bad_sha_fmt['reasons'])
        bad_sha = m.audit(ns(decl=str(decl), modjar=str(jar), decl_sha256='0' * 64))
        ok('bad sha mismatch', 'DECL_DIGEST_MISMATCH' in bad_sha['reasons'])
        ok('bad sha digest false', bad_sha['decl_digest_ok'] is False)
        bad_prefix = m.audit(ns(decl=str(decl), modjar=str(jar), game_prefix=['bad.prefix']))
        ok('bad prefix dot', 'BAD_GAME_PREFIX' in bad_prefix['reasons'])
        bad_prefix2 = m.audit(ns(decl=str(decl), modjar=str(jar), game_prefix=['/abs']))
        ok('bad prefix slash', 'BAD_GAME_PREFIX' in bad_prefix2['reasons'])
        no_decl = m.audit(ns(decl=str(T / 'missing-decl.tsv'), modjar=str(jar)))
        ok('no decl io', 'DECL_IO' in no_decl['reasons'])
        ok('no decl flag', 'NO_DECL' in no_decl['reasons'])
        no_jar = m.audit(ns(decl=str(decl), modjar=str(T / 'missing.jar')))
        ok('no jar', 'JAR_IO' in no_jar['reasons'])
        empty_jar = mkjar(T / 'empty.jar', {'t/Fixture.class': build_empty()})
        empty_report = m.audit(ns(decl=str(decl), modjar=str(empty_jar)))
        ok('empty surface reason', 'NO_SURFACE_REFS' in empty_report['reasons'])
        ok('empty surface verdict', empty_report['verdict'] == 'UNSUPPORTED')
        bad_class_jar = mkjar(T / 'bad-class.jar', {'t/Bad.class': build_bad_magic()})
        bad_class_report = m.audit(ns(decl=str(decl), modjar=str(bad_class_jar)))
        ok('bad class reason', 'BAD_CLASS_FILE' in bad_class_report['reasons'])
        ok('bad class error', bad_class_report['error'] != '')

        framework_jar = mkjar(T / 'framework.jar', {'t/Fixture.class': build_framework()})
        fw = m.audit(ns(decl=str(decl), modjar=str(framework_jar)))
        ok('framework unresolved count', fw['counts_by_status']['FRAMEWORK_UNRESOLVED'] == 1)
        ok('framework literals', fw['framework_literals'] == 1)
        ok('framework reason', 'FRAMEWORK_CLASS_LITERALS' in fw['reasons'])
        ok('framework verdict', fw['verdict'] == 'NEEDS_MANUAL')
        ok('framework needs manual', fw['needs_manual'] == 1)
        fw_only = m.audit(ns(decl=str(decl), modjar=str(framework_jar), coverage_only=True))
        ok('framework coverage verdict', fw_only['verdict'] == 'SURFACE_ONLY_OK')
        ok('framework coverage still reports', fw_only['counts_by_status']['FRAMEWORK_UNRESOLVED'] == 1)
        ok('framework coverage reasons', 'FRAMEWORK_CLASS_LITERALS' in fw_only['reasons'])
        ok('framework coverage flag', fw_only['coverage_only'] is True)

        dynamic_jar = mkjar(T / 'dynamic.jar', {'t/Fixture.class': build_dynamic()})
        dyn = m.audit(ns(decl=str(decl), modjar=str(dynamic_jar)))
        ok('dynamic reason', 'DYNAMIC_BOOTSTRAP_UNPROVEN' in dyn['reasons'])
        ok('dynamic verdict', dyn['verdict'] == 'NEEDS_MANUAL')
        ok('dynamic count', dyn['dynamic_constants'] == 1)
        dyn_only = m.audit(ns(decl=str(decl), modjar=str(dynamic_jar), coverage_only=True))
        ok('dynamic coverage verdict', dyn_only['verdict'] == 'SURFACE_ONLY_OK')
        ok('dynamic coverage still reports', 'DYNAMIC_BOOTSTRAP_UNPROVEN' in dyn_only['reasons'])
        full_jar = mkjar(T / 'full.jar', {'t/Fixture.class': build_full()})
        full_report = m.audit(ns(decl=str(decl), modjar=str(full_jar)))
        ok('full report nested reason', 'NESTED_DYNAMIC_ARGUMENT' in full_report['reasons'])
        ok('full report framework reason', 'FRAMEWORK_CLASS_LITERALS' in full_report['reasons'])
        ok('full report dynamic reason', 'DYNAMIC_BOOTSTRAP_UNPROVEN' in full_report['reasons'])
        ok('full report annotation attrs', sum(full_report['annotation_attributes'].values()) == 8)
        ok('full report nested count', full_report['nested_dynamic_args'] == 1)
        ok('full report framework count', full_report['framework_unique'] >= 6)

        third_jar = mkjar(T / 'third.jar', {'t/Fixture.class': build_third_party()})
        third = m.audit(ns(decl=str(decl), modjar=str(third_jar)))
        ok('third party status', third['counts_by_status']['THIRD_PARTY'] == 1)
        ok('third party unclassified', 'UNCLASSIFIED_REFS' in third['reasons'])
        ok('third party verdict', third['verdict'] == 'UNSUPPORTED')
        third_waived = m.audit(ns(decl=str(decl), modjar=str(third_jar), allow_third_party=True))
        ok('third party waived reason', 'THIRD_PARTY_WAIVED' in third_waived['reasons'])
        ok('third party no unclassified', 'UNCLASSIFIED_REFS' not in third_waived['reasons'])
        ok('third party waived verdict', third_waived['verdict'] == 'NEEDS_MANUAL')
        third_only = m.audit(ns(decl=str(decl), modjar=str(third_jar), allow_third_party=True, coverage_only=True))
        ok('third party coverage verdict', third_only['verdict'] == 'SURFACE_ONLY_OK')
        ok('third party coverage reports', 'THIRD_PARTY_WAIVED' in third_only['reasons'])
        ext_jar = mkjar(T / 'external.jar', {'t/Fixture.class': build_external_only()})
        ext = m.audit(ns(decl=str(decl), modjar=str(ext_jar)))
        ok('external no game refs', 'NO_GAME_REFS' in ext['reasons'])
        ok('external soft verdict', ext['verdict'] == 'NEEDS_MANUAL')
        self_jar = mkjar(T / 'self.jar', {'t/Fixture.class': build_self_and_game()})
        self_report = m.audit(ns(decl=str(decl), modjar=str(self_jar)))
        ok('self status', self_report['counts_by_status']['SELF'] == 1)
        ok('self still resolve', self_report['counts_by_status']['RESOLVE'] == 1)
        ok('self verdict', self_report['verdict'] == 'SURFACE_OK')

        custom_decl = write_lines(T / 'custom-decl.tsv', ['C\tvendor/lib/Api', 'M\tvendor/lib/Api\tcall\t()V'])
        custom = m.audit(ns(decl=str(custom_decl), modjar=str(third_jar), game_prefix=['vendor/lib/']))
        ok('custom prefix resolve', custom['counts_by_status']['RESOLVE'] == 1)
        ok('custom prefix no game refs', 'NO_GAME_REFS' not in custom['reasons'])
        ok('custom prefix verdict', custom['verdict'] == 'SURFACE_OK')
        ok('custom prefix listed', 'vendor/lib/' in custom['game_prefixes'])

        rename_decl = write_lines(T / 'rename-decl.tsv', [
            'C\tnet/minecraft/Foo',
            'M\tnet/minecraft/Foo\tmoved\t(Lnet/minecraft/Foo;)V',
        ])
        rename_map = write_lines(T / 'rename-map.tsv', [
            'C\tnet/minecraft/Old\tnet/minecraft/Foo',
            'M\tnet/minecraft/Old\tmoved\t()V',
        ])
        rename_jar = mkjar(T / 'rename.jar', {'t/Fixture.class': build_rename()})
        rn = m.audit(ns(decl=str(rename_decl), modjar=str(rename_jar), map=str(rename_map)))
        ok('rename status', rn['counts_by_status']['RENAME'] >= 2)
        ok('rename mapped_to', rn['mapped_to'].get('net/minecraft/Old') == 'net/minecraft/Foo')
        ok('rename mapped class reason', 'MAPPED_CLASS' in rn['reasons'])
        ok('rename map sha', rn['map_sha256'] == sha(rename_map))
        ok('rename map rows', rn['map_rows'] == 1)
        ok('rename map ignored', rn['map_ignored_rows'] == 1)
        ok('rename verdict', rn['verdict'] == 'NEEDS_MANUAL')
        map_target_missing = write_lines(T / 'map-target-missing.tsv', ['C\tnet/minecraft/Old\tnet/minecraft/Absent'])
        mt = m.audit(ns(decl=str(rename_decl), modjar=str(rename_jar), map=str(map_target_missing)))
        ok('map target missing reason', 'MAP_TARGET_MISSING' in mt['reasons'])
        ok('map target missing field', mt['map_target_missing'] == ['net/minecraft/Absent'])
        ok('map target missing verdict', mt['verdict'] == 'UNSUPPORTED')
        mapped_target_missing_decl = write_lines(T / 'mapped-target-missing.tsv', ['C\tnet/minecraft/Foo'])
        mtm = m.audit(ns(decl=str(mapped_target_missing_decl), modjar=str(rename_jar), map=str(rename_map)))
        ok('mapped target missing reason', 'MAPPED_TARGET_MISSING' in mtm['reasons'])
        ok('mapped target missing status', mtm['counts_by_status']['MISSING'] >= 1)
        ok('mapped target missing verdict', mtm['verdict'] == 'UNSUPPORTED')
        conflict_map = write_lines(T / 'map-conflict.tsv', [
            'C\tnet/minecraft/Old\tnet/minecraft/Foo',
            'C\tnet/minecraft/Old\tnet/minecraft/Bar',
        ])
        conflict_decl = write_lines(T / 'conflict-decl.tsv', ['C\tnet/minecraft/Foo', 'C\tnet/minecraft/Bar'])
        cf = m.audit(ns(decl=str(conflict_decl), modjar=str(rename_jar), map=str(conflict_map)))
        ok('map conflict reason', 'MAP_CONFLICT' in cf['reasons'])
        ok('map conflict verdict', cf['verdict'] == 'UNSUPPORTED')
        bad_map_row = write_lines(T / 'map-bad-row.tsv', ['X\ta\tb'])
        bmr = m.audit(ns(decl=str(decl), modjar=str(jar), map=str(bad_map_row)))
        ok('map bad row reason', 'MAP_BAD_ROW' in bmr['reasons'])
        bad_map_owner = write_lines(T / 'map-bad-owner.tsv', ['C\tnet/minecraft/Old\tbad.name'])
        bmo = m.audit(ns(decl=str(decl), modjar=str(jar), map=str(bad_map_owner)))
        ok('map bad owner reason', 'MAP_BAD_OWNER' in bmo['reasons'])
        missing_map = m.audit(ns(decl=str(decl), modjar=str(jar), map=str(T / 'missing-map.tsv')))
        ok('map io reason', 'MAP_IO' in missing_map['reasons'])
        bad_map_utf = m.audit(ns(decl=str(decl), modjar=str(jar), map=str(bad_utf)))
        ok('map bad utf8 reason', 'MAP_BAD_UTF8' in bad_map_utf['reasons'])
        missing_member_decl = write_lines(T / 'missing-member-decl.tsv', ['C\tnet/minecraft/Foo'])
        mm = m.audit(ns(decl=str(missing_member_decl), modjar=str(jar)))
        ok('missing member status', mm['counts_by_status']['MISSING'] == 1)
        ok('missing member verdict', mm['verdict'] == 'NEEDS_MANUAL')
        class_missing_jar = mkjar(T / 'class-missing.jar', {'t/Fixture.class': build_class_missing()})
        cm = m.audit(ns(decl=str(decl), modjar=str(class_missing_jar)))
        ok('missing class status', cm['counts_by_status']['MISSING'] >= 1)
        ok('missing class verdict', cm['verdict'] == 'NEEDS_MANUAL')
        own_ns_jar = mkjar(T / 'own-ns.jar', {
            'net/minecraft/Foo.class': build_simple('net/minecraft/Foo'),
            'java/lang/Object.class': build_simple('java/lang/Object'),
        })
        own_ns = m.audit(ns(decl=str(decl), modjar=str(own_ns_jar)))
        ok('own game namespace', 'OWN_GAME_NAMESPACE' in own_ns['reasons'])
        ok('own external namespace', 'OWN_EXTERNAL_NAMESPACE' in own_ns['reasons'])
        ok('own game classes', 'net/minecraft/Foo' in own_ns['own_game_classes'])
        ok('own external classes', 'java/lang/Object' in own_ns['own_external_classes'])
        ok('own namespace verdict', own_ns['verdict'] == 'UNSUPPORTED')

        original_scan = m.scan_jar
        m.scan_jar = lambda p: []
        try:
            no_scan = m.audit(good_ns(T))
            ok('no scannable classes', 'NO_SCANNABLE_CLASSES' in no_scan['reasons'])
        finally:
            m.scan_jar = original_scan
        original_decl = CR.parse_decl
        def fake_decl(p):
            return {'classes': {'other/namespace/Api'}, 'rows': 0, 'kinds': {}, 'sha256': ''}
        CR.parse_decl = fake_decl
        try:
            view = m.audit(good_ns(T))
            ok('decl view conflict reason', 'DECL_VIEW_CONFLICT' in view['reasons'])
            ok('decl view conflict flag', view['decl_view_conflict'] is True)
        finally:
            CR.parse_decl = original_decl
        def boom_decl(p):
            raise CR.ClassRefError('DECL_BAD_ROW', 'patched')
        CR.parse_decl = boom_decl
        try:
            view2 = m.audit(good_ns(T))
            ok('decl view exception reason', 'DECL_VIEW_CONFLICT' in view2['reasons'])
            ok('decl view exception error', view2['error'] == 'patched')
        finally:
            CR.parse_decl = original_decl

        jout = T / 'json' / 'report.json'
        m.write_json(jout, {'z': 1, 'a': '中文'})
        jb = jout.read_bytes()
        ok('write_json trailing LF', jb.endswith(b'\n'))
        ok('write_json sorted keys', jb.index(b'"a"') < jb.index(b'"z"'))
        ok('write_json utf8', '中文'.encode('utf-8') in jb)
        m.write_json(T / 'json' / 'report2.json', {'z': 1, 'a': '中文'})
        ok('write_json deterministic', jb == (T / 'json' / 'report2.json').read_bytes())
        srep = m.base_report(good_ns(T))
        srep['decl_digest_ok'] = True
        srep['decl_view_conflict'] = False
        srep['map_target_missing'] = ['a', 'b']
        srep['annotation_attributes'] = {'RuntimeVisibleAnnotations': 2}
        srep['reasons'] = ['X', 'Y']
        srep['needs_manual'] = 1
        srep['verdict'] = 'NEEDS_MANUAL'
        sout = T / 'csv' / 'summary.csv'
        m.write_summary(sout, srep)
        with sout.open('r', encoding='utf-8', newline='') as fh:
            rows = list(csv.DictReader(fh))
        ok('write_summary one row', len(rows) == 1)
        ok('write_summary 37 cols', len(rows[0]) == 37)
        ok('write_summary bool true', rows[0]['decl_digest_ok'] == '1')
        ok('write_summary bool false', rows[0]['decl_view_conflict'] == '0')
        ok('write_summary joined reasons', rows[0]['reasons'] == 'X|Y')
        ok('write_summary joined targets', rows[0]['map_target_missing'] == 'a|b')
        ok('write_summary annotation attrs', rows[0]['annotation_attributes'] == "{'RuntimeVisibleAnnotations': 2}")
        ok('write_summary needs manual', rows[0]['needs_manual'] == '1')
        ok('write_summary verdict', rows[0]['verdict'] == 'NEEDS_MANUAL')
        ok('write_summary none empty', m._csv_value(None) == '')
        ok('write_summary bool one', m._csv_value(True) == '1')
        ok('write_summary bool zero', m._csv_value(False) == '0')
        ok('stdout unsupported no disclaimer', m.DISCLAIMER not in m.stdout_line(base))
        nr = m.base_report(good_ns(T))
        nr['verdict'] = 'NEEDS_MANUAL'
        nr['reasons'] = ['X']
        ok('stdout needs manual disclaimer', m.DISCLAIMER in m.stdout_line(nr))
        ok('stdout needs manual reasons', 'reasons=X' in m.stdout_line(nr))

        hp = cli('--help')
        ok('cli help rc', hp.returncode == 0)
        ok('cli help usage', 'usage:' in hp.stdout)
        n_good = good_ns(T)
        n_good.out = str(T / 'cli-good.json')
        n_good.summary = str(T / 'cli-good.csv')
        pg = cli_rc('cli good', 0, *args_of(n_good))
        ok('cli good stdout', 'verdict=SURFACE_OK' in pg.stdout)
        ok('cli good json', json.loads((T / 'cli-good.json').read_text(encoding='utf-8'))['verdict'] == 'SURFACE_OK')
        ok('cli good csv', 'SURFACE_OK' in (T / 'cli-good.csv').read_text(encoding='utf-8'))
        n_good.out = str(T / 'cli-good2.json')
        n_good.summary = str(T / 'cli-good2.csv')
        pg2 = cli_rc('cli good repeat', 0, *args_of(n_good))
        ok('cli good repeat rc', pg2.returncode == 0)
        ok('cli deterministic json', (T / 'cli-good.json').read_bytes() == (T / 'cli-good2.json').read_bytes())
        ok('cli deterministic csv', (T / 'cli-good.csv').read_bytes() == (T / 'cli-good2.csv').read_bytes())
        n_bad = ns(decl=str(decl), modjar=str(jar), version='1.20 1')
        pb = cli_rc('cli bad version', 1, *args_of(n_bad))
        ok('cli bad version stderr', 'BAD_VERSION' in pb.stderr)
        n_fw = ns(decl=str(decl), modjar=str(framework_jar))
        pf = cli_rc('cli framework', 2, *args_of(n_fw))
        ok('cli framework stdout', 'verdict=NEEDS_MANUAL' in pf.stdout)
        n_fw_only = ns(decl=str(decl), modjar=str(framework_jar), coverage_only=True)
        pfo = cli_rc('cli framework coverage', 0, *args_of(n_fw_only))
        ok('cli framework coverage stdout', 'verdict=SURFACE_ONLY_OK' in pfo.stdout)
        n_third = ns(decl=str(decl), modjar=str(third_jar))
        pt = cli_rc('cli third', 1, *args_of(n_third))
        ok('cli third stderr', 'UNCLASSIFIED_REFS' in pt.stderr)
        n_third_allow = ns(decl=str(decl), modjar=str(third_jar), allow_third_party=True)
        pta = cli_rc('cli third waived', 2, *args_of(n_third_allow))
        ok('cli third waived stdout', 'verdict=NEEDS_MANUAL' in pta.stdout)
        n_custom = ns(decl=str(custom_decl), modjar=str(third_jar), game_prefix=['vendor/lib/'])
        pc = cli_rc('cli custom prefix', 0, *args_of(n_custom))
        ok('cli custom prefix stdout', 'verdict=SURFACE_OK' in pc.stdout)
        n_rename = ns(decl=str(rename_decl), modjar=str(rename_jar), map=str(rename_map))
        pr = cli_rc('cli rename', 2, *args_of(n_rename))
        ok('cli rename stdout', 'verdict=NEEDS_MANUAL' in pr.stdout)
        n_sha = ns(decl=str(decl), modjar=str(jar), decl_sha256='0' * 64)
        ps = cli_rc('cli bad decl sha', 1, *args_of(n_sha))
        ok('cli bad decl sha stderr', 'DECL_DIGEST_MISMATCH' in ps.stderr)

        original_audit = m.audit
        def boom(a):
            raise OSError('boom')
        m.audit = boom
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as se:
                rc = m.main(['--decl', str(decl), '--modjar', str(jar), '--out', str(T / 'internal.json')])
            ok('main internal rc', rc == 1)
            ok('main internal no traceback', 'Traceback' not in se.getvalue())
            ir = json.loads((T / 'internal.json').read_text(encoding='utf-8'))
            ok('main internal reason', ir['reasons'] == ['INTERNAL_ERROR'])
            ok('main internal error', ir['error'] == 'boom')
        finally:
            m.audit = original_audit
        def surface_boom(a):
            raise m.SurfaceError('JAR_IO', 'patched')
        m.audit = surface_boom
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as se2:
                rc2 = m.main(['--decl', str(decl), '--modjar', str(jar), '--out', str(T / 'surface-error.json')])
            ok('main surface rc', rc2 == 1)
            ok('main surface no traceback', 'Traceback' not in se2.getvalue())
            sr = json.loads((T / 'surface-error.json').read_text(encoding='utf-8'))
            ok('main surface reason', sr['reasons'] == ['JAR_IO'])
            ok('main surface error', sr['error'] == 'patched')
        finally:
            m.audit = original_audit

    print(f'RESULT ALL_OK assertions={COUNT}')


if __name__ == '__main__':
    sys.exit(main())
