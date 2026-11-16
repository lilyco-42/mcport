#!/usr/bin/env python3
"""McPort 0.2.7 / REPORT section 26: annotation + bootstrap/MethodHandle linkage surface audit.

Pure standard library and offline. Reads a caller-supplied LinkCheck decl TSV,
an optional C-rename map TSV and one mod jar. It recovers three surfaces that
the historical member scanner cannot see:

1. LINKAGE: every CONSTANT_MethodHandle (tag 15) is a potential
   Fieldref / Methodref / InterfaceMethodref resolution (JVMS 4.4.8 / 5.4.3.5).
   CONSTANT_Dynamic (17) / CONSTANT_InvokeDynamic (18) add a BootstrapMethods
   resolution path (JVMS 5.4.3.6). Unused constant-pool entries are included
   conservatively; the tool cannot prove whether a LDC is ever executed.
2. CLASS_SURFACE: loadable bootstrap arguments of tag 7 / 16 / 17 and dynamic
   descriptors carry object class names that the JVM must resolve too.
3. FRAMEWORK: annotation element_value tag c stores a class literal as a Utf8
   return descriptor (JVMS 4.7.16.1). Mixin-style annotations are resolved by
   the framework / refmap, NOT by JVMS 5.4.3.1 link-time, so this tool never
   silently marks them compatible.

It does NOT run the game, rewrite bytes, attach to a JVM, or claim runtime or
semantic compatibility. SURFACE_OK only means the visible JVM link symbols are
declared and no framework-resolved class literal or unproven bootstrap call
site was found.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import struct
import sys
import zipfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AUD = _load('mcport_audit_for_linkage_surface', 'contract_audit.py')
CR = _load('mcport_classref_for_linkage_surface', 'classref.py')

SCHEMA = 1
TOOL = 'mcport.linkage_surface'
ALLOWED_STATUS = ('RESOLVE', 'RENAME', 'MISSING', 'EXTERNAL', 'THIRD_PARTY',
                  'SELF', 'FRAMEWORK_UNRESOLVED')
BLOCK_STATUS = ('MISSING', 'RENAME', 'FRAMEWORK_UNRESOLVED')
GAME_PREFIXES = AUD.GAME_PREFIXES
EXTERNAL_PREFIXES = AUD.EXTERNAL_PREFIXES
DISCLAIMER = 'does NOT mean runtime-compatible; static linkage does NOT prove semantic equivalence'
CLAIM_POLICY = 'static-linkage-surface-only; no runtime claim'
LINKAGE_SPEC = 'JVMS 5.4.3.5 / 5.4.3.6'
FRAMEWORK_SPEC = 'JVMS 4.7.16.1 class literals are framework-resolved, NOT JVMS link-time'
SCOPE = {
    'covers': [
        'CONSTANT_MethodHandle tag 15 to tag 9/10/11 member refs (JVMS 4.4.8 kind constraints)',
        'CONSTANT_Dynamic tag 17 and CONSTANT_InvokeDynamic tag 18 bootstrap edges',
        'BootstrapMethods attribute method refs and loadable arguments',
        'RuntimeVisible/InvisibleAnnotations, ParameterAnnotations, TypeAnnotations and AnnotationDefault tag c class literals',
    ],
    'does_not_cover': [
        'reflective or JSON string class names (see REPORT section 17)',
        'runtime ClassLoader / Mixin / Fabric / bootstrap behaviour',
        'same-name same-signature semantic drift',
        'rewriting annotation bytes or Mixin refmap files',
    ],
}
EXIT_CODE = {
    'SURFACE_OK': 0,
    'SURFACE_ONLY_OK': 0,
    'NEEDS_MANUAL': 2,
    'UNSUPPORTED': 1,
}
HARD_REASONS = frozenset((
    'BAD_VERSION', 'BAD_DECL_SHA256', 'DECL_DIGEST_MISMATCH', 'BAD_GAME_PREFIX',
    'DECL_BAD_ROW', 'DECL_BAD_OWNER', 'DECL_BAD_DESC', 'DECL_BAD_MEMBER',
    'DECL_NO_CLASSES', 'DECL_IO', 'DECL_BAD_UTF8', 'DECL_VIEW_CONFLICT',
    'MAP_BAD_ROW', 'MAP_BAD_OWNER', 'MAP_CONFLICT', 'MAP_IO', 'MAP_BAD_UTF8',
    'MAP_TARGET_MISSING', 'MAPPED_TARGET_MISSING', 'BAD_MAPPED_DESCRIPTOR',
    'JAR_IO', 'NO_CLASS_ENTRIES', 'DUPLICATE_CLASS_ENTRY', 'NO_SCANNABLE_CLASSES',
    'BAD_CLASS_FILE', 'BAD_METHOD_HANDLE', 'BAD_DYNAMIC_DESCRIPTOR',
    'BAD_BOOTSTRAP', 'BAD_BOOTSTRAP_METHOD_REF', 'BAD_BOOTSTRAP_ARG_TAG',
    'BAD_BOOTSTRAP_INDEX', 'BAD_BOOTSTRAP_DUPLICATE', 'BOOTSTRAP_MISSING',
    'BAD_ANNOTATION', 'BAD_ANNOTATION_ELEMENT', 'BAD_ANNOTATION_LENGTH',
    'BAD_TYPE_ANNOTATION_TARGET', 'BAD_CODE_ATTRIBUTE', 'BAD_RETURN_DESCRIPTOR',
    'OWN_GAME_NAMESPACE', 'OWN_EXTERNAL_NAMESPACE', 'UNCLASSIFIED_REFS',
    'NO_DECL', 'INTERNAL_ERROR', 'BAD_MODIFIED_UTF8', 'BAD_ARRAY_CLASS',
    'BAD_CLASS_NAME', 'BAD_DESCRIPTOR', 'BAD_ARRAY_OWNER',
    'NO_SURFACE_REFS',
))
LOADABLE_TAGS = frozenset((3, 4, 5, 6, 7, 8, 15, 16, 17))
ANNOTATION_SIMPLE = frozenset(('RuntimeVisibleAnnotations', 'RuntimeInvisibleAnnotations'))
ANNOTATION_PARAM = frozenset(('RuntimeVisibleParameterAnnotations',
                              'RuntimeInvisibleParameterAnnotations'))
ANNOTATION_TYPE = frozenset(('RuntimeVisibleTypeAnnotations',
                             'RuntimeInvisibleTypeAnnotations'))
ANNOTATION_DEFAULT = frozenset(('AnnotationDefault',))
ANNOTATION_ATTRS = ANNOTATION_SIMPLE | ANNOTATION_PARAM | ANNOTATION_TYPE | ANNOTATION_DEFAULT
SUMMARY_COLS = (
    'schema', 'tool', 'version', 'decl', 'decl_sha256', 'decl_digest_ok',
    'decl_rows', 'decl_members', 'decl_view_conflict',
    'map', 'map_sha256', 'map_rows', 'map_ignored_rows', 'map_target_missing',
    'modjar', 'classes', 'member_refs', 'member_unique', 'method_handles',
    'bootstrap_methods', 'bootstrap_args', 'dynamic_constants',
    'nested_dynamic_args', 'framework_literals', 'framework_unique',
    'class_surface_refs', 'annotation_attributes',
    'resolve', 'rename', 'missing', 'external', 'third_party', 'self_count',
    'framework_unresolved', 'needs_manual', 'verdict', 'reasons',
)


class SurfaceError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _need(b, p, n, code='BAD_CLASS_FILE'):
    if p < 0 or n < 0 or p + n > len(b):
        raise SurfaceError(_strict_code(code), 'truncated structure at offset ' + str(p))
    return p + n


def _u1(b, p, code='BAD_CLASS_FILE'):
    _need(b, p, 1, code)
    return b[p]


def _u2(b, p, code='BAD_CLASS_FILE'):
    _need(b, p, 2, code)
    return struct.unpack_from('>H', b, p)[0]


def _u4(b, p, code='BAD_CLASS_FILE'):
    _need(b, p, 4, code)
    return struct.unpack_from('>I', b, p)[0]


def _cp(entries, count, idx, code='BAD_CLASS_FILE'):
    if idx <= 0 or idx >= count or entries[idx] is None:
        raise SurfaceError(_strict_code(code), 'bad constant pool index ' + str(idx))
    return entries[idx]


def _strict_code(code):
    """Never let a caller-supplied code hide a hard class-file / input failure."""
    return code if code in HARD_REASONS else 'BAD_CLASS_FILE'


def _utf8(entries, count, idx, code='BAD_CLASS_FILE'):
    e = _cp(entries, count, idx, code)
    if e[0] != 1:
        raise SurfaceError(_strict_code(code), 'cp index ' + str(idx) + ' is not Utf8')
    try:
        return AUD.decode_modified_utf8(e[3:])
    except AUD.AuditError as ex:
        raise SurfaceError(_strict_code(ex.code), str(ex))


def _class_name(entries, count, idx, code='BAD_CLASS_FILE'):
    e = _cp(entries, count, idx, code)
    if e[0] != 7:
        raise SurfaceError(_strict_code(code), 'cp index ' + str(idx) + ' is not Class')
    raw = _utf8(entries, count, _u2(e, 1, code), code)
    try:
        return CR.normalize_class_name(raw)
    except CR.ClassRefError as ex:
        raise SurfaceError(_strict_code(ex.code), str(ex))


def _nat(entries, count, idx, code='BAD_CLASS_FILE'):
    e = _cp(entries, count, idx, code)
    if e[0] != 12:
        raise SurfaceError(_strict_code(code), 'cp index ' + str(idx) + ' is not NameAndType')
    return (_utf8(entries, count, _u2(e, 1, code), code),
            _utf8(entries, count, _u2(e, 3, code), code))


def _desc_object_types(desc):
    try:
        return CR.desc_object_types(desc)
    except CR.ClassRefError as e:
        raise SurfaceError(_strict_code(e.code), str(e))


def _return_desc_class(desc):
    """Return the class named by a JVMS 4.3.3 return descriptor, or None."""
    if desc == 'V' or desc in AUD.PRIMITIVES:
        return None
    if desc.startswith('['):
        try:
            return AUD.owner_namespace(desc)
        except AUD.AuditError as e:
            raise SurfaceError(_strict_code(e.code), str(e))
    if desc.startswith('L') and desc.endswith(';') and AUD.is_field_desc(desc):
        inner = desc[1:-1]
        if not AUD.valid_owner(inner):
            raise SurfaceError('BAD_RETURN_DESCRIPTOR', 'bad class literal: ' + repr(desc))
        return inner
    raise SurfaceError('BAD_RETURN_DESCRIPTOR', 'invalid return descriptor: ' + repr(desc))


def _member_refs(entries, count, out):
    refs = set()
    handles = 0
    for i in range(1, count):
        e = entries[i]
        if e is None or e[0] != 15:
            continue
        handles += 1
        kind = e[1]
        idx = _u2(e, 2)
        if kind < 1 or kind > 9:
            raise SurfaceError('BAD_METHOD_HANDLE', 'reference_kind out of range: ' + str(kind))
        t = _cp(entries, count, idx, 'BAD_METHOD_HANDLE')
        if t[0] not in (9, 10, 11):
            raise SurfaceError('BAD_METHOD_HANDLE',
                               'tag 15 points at tag ' + str(t[0]))
        expected = ({1: (9,), 2: (9,), 3: (9,), 4: (9,),
                     5: (10,), 6: (10, 11), 7: (10, 11),
                     8: (10,), 9: (11,)})[kind]
        if t[0] not in expected:
            raise SurfaceError('BAD_METHOD_HANDLE',
                               'reference_kind ' + str(kind) + ' cannot point at tag ' + str(t[0]))
        owner = _class_name(entries, count, _u2(t, 1, 'BAD_METHOD_HANDLE'),
                            'BAD_METHOD_HANDLE')
        name, desc = _nat(entries, count, _u2(t, 3, 'BAD_METHOD_HANDLE'),
                          'BAD_METHOD_HANDLE')
        field = t[0] == 9
        if not AUD.valid_member_name(name):
            raise SurfaceError('BAD_METHOD_HANDLE', 'bad member name: ' + repr(name))
        if not (AUD.is_field_desc(desc) if field else AUD.is_method_desc(desc)):
            raise SurfaceError('BAD_METHOD_HANDLE', 'bad member descriptor: ' + repr(desc))
        refs.add(('F' if field else 'M', owner, name, desc))
        for cls in _desc_object_types(desc):
            out['class_refs'].add((cls, 'METHOD_HANDLE_DESCRIPTOR'))
    return refs, handles


def _dynamic_entries(entries, count, out):
    total = 0
    for i in range(1, count):
        e = entries[i]
        if e is None or e[0] not in (17, 18):
            continue
        total += 1
        bsm = _u2(e, 1, 'BAD_DYNAMIC_DESCRIPTOR')
        name, desc = _nat(entries, count, _u2(e, 3, 'BAD_DYNAMIC_DESCRIPTOR'),
                          'BAD_DYNAMIC_DESCRIPTOR')
        if e[0] == 17 and not AUD.is_field_desc(desc):
            raise SurfaceError('BAD_DYNAMIC_DESCRIPTOR',
                               'CONSTANT_Dynamic needs a field descriptor: ' + repr(desc))
        if e[0] == 18 and not AUD.is_method_desc(desc):
            raise SurfaceError('BAD_DYNAMIC_DESCRIPTOR',
                               'CONSTANT_InvokeDynamic needs a method descriptor: ' + repr(desc))
        if not AUD.valid_member_name(name):
            raise SurfaceError('BAD_DYNAMIC_DESCRIPTOR', 'bad dynamic name: ' + repr(name))
        out['dynamic'].append((i, e[0], bsm, name, desc))
        for cls in _desc_object_types(desc):
            out['class_refs'].add((cls, 'DYNAMIC_DESCRIPTOR'))
    return total


def _target_info_len(b, p, target):
    if target in (0x00, 0x01, 0x16):
        size = 1
    elif target in (0x10, 0x11, 0x12, 0x17, 0x42, 0x43, 0x44, 0x45, 0x46):
        size = 2
    elif target in (0x13, 0x14, 0x15):
        size = 0
    elif target in (0x40, 0x41):
        n = _u2(b, p, 'BAD_TYPE_ANNOTATION_TARGET')
        size = 2 + 6 * n
    elif 0x47 <= target <= 0x4B:
        size = 3
    else:
        raise SurfaceError('BAD_TYPE_ANNOTATION_TARGET',
                           'unknown target_type ' + hex(target))
    _need(b, p, size, 'BAD_TYPE_ANNOTATION_TARGET')
    return size


def _read_element_value(b, p, entries, count, out, attr, antype, elem):
    tag = chr(_u1(b, p, 'BAD_ANNOTATION'))
    p += 1
    if tag in 'BCDFIJSZs':
        idx = _u2(b, p, 'BAD_ANNOTATION')
        p += 2
        expected = {'B': 3, 'C': 3, 'I': 3, 'S': 3, 'Z': 3,
                    'D': 6, 'F': 4, 'J': 5, 's': 1}[tag]
        ce = _cp(entries, count, idx, 'BAD_ANNOTATION')
        if ce[0] != expected:
            raise SurfaceError('BAD_ANNOTATION_ELEMENT',
                               'element_value tag ' + repr(tag) + ' points at cp tag ' + str(ce[0]))
        if tag == 's':
            _utf8(entries, count, idx, 'BAD_ANNOTATION')
    elif tag == 'e':
        ti = _u2(b, p, 'BAD_ANNOTATION')
        ci = _u2(b, p + 2, 'BAD_ANNOTATION')
        tdesc = _utf8(entries, count, ti, 'BAD_ANNOTATION')
        _utf8(entries, count, ci, 'BAD_ANNOTATION')
        if not AUD.is_field_desc(tdesc):
            raise SurfaceError('BAD_ANNOTATION_ELEMENT',
                               'enum type_name_index is not a field descriptor: ' + repr(tdesc))
        p += 4
    elif tag == 'c':
        idx = _u2(b, p, 'BAD_ANNOTATION')
        raw = _utf8(entries, count, idx, 'BAD_ANNOTATION')
        cls = _return_desc_class(raw)
        if cls is not None:
            out['framework'].append((cls, raw, attr, antype, elem))
        p += 2
    elif tag == '@':
        p = _read_annotation(b, p, entries, count, out, attr, False)
    elif tag == '[':
        n = _u2(b, p, 'BAD_ANNOTATION')
        p += 2
        for _ in range(n):
            p = _read_element_value(b, p, entries, count, out, attr, antype, elem)
    else:
        raise SurfaceError('BAD_ANNOTATION_ELEMENT', 'unknown element_value tag ' + repr(tag))
    return p


def _read_annotation(b, p, entries, count, out, attr, type_annotation):
    if type_annotation:
        target = _u1(b, p, 'BAD_ANNOTATION')
        p += 1
        p += _target_info_len(b, p, target)
        path_len = _u1(b, p, 'BAD_ANNOTATION')
        p += 1
        p = _need(b, p, 2 * path_len, 'BAD_ANNOTATION')
    ti = _u2(b, p, 'BAD_ANNOTATION')
    antype = _utf8(entries, count, ti, 'BAD_ANNOTATION')
    p += 2
    if not AUD.is_field_desc(antype):
        raise SurfaceError('BAD_ANNOTATION', 'annotation type is not a field descriptor: ' + repr(antype))
    n = _u2(b, p, 'BAD_ANNOTATION')
    p += 2
    for _ in range(n):
        ei = _u2(b, p, 'BAD_ANNOTATION')
        elem = _utf8(entries, count, ei, 'BAD_ANNOTATION')
        p += 2
        p = _read_element_value(b, p, entries, count, out, attr, antype, elem)
    return p


def _parse_annotation_attr(name, body, entries, count, out):
    p = 0
    if name in ANNOTATION_DEFAULT:
        p = _read_element_value(body, p, entries, count, out, name, '', '')
    elif name in ANNOTATION_PARAM:
        nparams = _u1(body, p, 'BAD_ANNOTATION')
        p += 1
        for _ in range(nparams):
            n = _u2(body, p, 'BAD_ANNOTATION')
            p += 2
            for _ in range(n):
                p = _read_annotation(body, p, entries, count, out, name, False)
    else:
        typ = name in ANNOTATION_TYPE
        n = _u2(body, p, 'BAD_ANNOTATION')
        p += 2
        for _ in range(n):
            p = _read_annotation(body, p, entries, count, out, name, typ)
    if p != len(body):
        raise SurfaceError('BAD_ANNOTATION_LENGTH', name + ' consumed ' + str(p)
                           + ' of ' + str(len(body)) + ' bytes')
    out['annotation_attrs'].append(name)


def _parse_bootstrap_methods(body, entries, count, out):
    p = 0
    n = _u2(body, p, 'BAD_BOOTSTRAP')
    p += 2
    for k in range(n):
        ref = _u2(body, p, 'BAD_BOOTSTRAP')
        nargs = _u2(body, p + 2, 'BAD_BOOTSTRAP')
        p += 4
        e = _cp(entries, count, ref, 'BAD_BOOTSTRAP_METHOD_REF')
        if e[0] != 15:
            raise SurfaceError('BAD_BOOTSTRAP_METHOD_REF',
                               'bootstrap_method_ref is tag ' + str(e[0]))
        out['bootstrap_refs'].add(ref)
        for _ in range(nargs):
            idx = _u2(body, p, 'BAD_BOOTSTRAP')
            p += 2
            a = _cp(entries, count, idx, 'BAD_BOOTSTRAP_ARG_TAG')
            if a[0] not in LOADABLE_TAGS:
                raise SurfaceError('BAD_BOOTSTRAP_ARG_TAG',
                                   'bootstrap argument tag ' + str(a[0]))
            out['bootstrap_args'].append((k, idx, a[0]))
            if a[0] == 7:
                cls = _class_name(entries, count, idx, 'BAD_BOOTSTRAP')
                out['class_refs'].add((cls, 'BOOTSTRAP_CLASS'))
            elif a[0] == 16:
                desc = _utf8(entries, count, _u2(a, 1, 'BAD_BOOTSTRAP'), 'BAD_BOOTSTRAP')
                for cls in _desc_object_types(desc):
                    out['class_refs'].add((cls, 'BOOTSTRAP_METHODTYPE'))
            elif a[0] == 17:
                out['nested_dynamic_args'] += 1
    if p != len(body):
        raise SurfaceError('BAD_BOOTSTRAP', 'BootstrapMethods consumed ' + str(p)
                           + ' of ' + str(len(body)) + ' bytes')
    return n


def _walk_code(body, entries, count, out):
    p = 0
    _need(body, p, 8, 'BAD_CODE_ATTRIBUTE')
    code_len = _u4(body, p + 4, 'BAD_CODE_ATTRIBUTE')
    p = 8 + code_len
    ex_len = _u2(body, p, 'BAD_CODE_ATTRIBUTE')
    p += 2 + 8 * ex_len
    n = _u2(body, p, 'BAD_CODE_ATTRIBUTE')
    p += 2
    p = _walk_attrs(body, p, n, entries, count, out, False)
    if p != len(body):
        raise SurfaceError('BAD_CODE_ATTRIBUTE', 'Code consumed ' + str(p)
                           + ' of ' + str(len(body)) + ' bytes')
    return p


def _walk_attrs(b, p, n, entries, count, out, allow_code=True):
    for _ in range(n):
        name_idx = _u2(b, p)
        length = _u4(b, p + 2)
        start = p + 6
        end = start + length
        if end > len(b):
            raise SurfaceError('BAD_CLASS_FILE', 'truncated attribute body')
        name = _utf8(entries, count, name_idx)
        body = b[start:end]
        if name == 'BootstrapMethods':
            if out['bootstrap_seen']:
                raise SurfaceError('BAD_BOOTSTRAP_DUPLICATE', 'duplicate BootstrapMethods')
            out['bootstrap_seen'] = True
            out['bootstrap_methods'] = _parse_bootstrap_methods(body, entries, count, out)
        elif name in ANNOTATION_ATTRS:
            _parse_annotation_attr(name, body, entries, count, out)
        elif name == 'Code' and allow_code:
            _walk_code(body, entries, count, out)
        p = end
    return p


def parse_class(data):
    """Parse one class file into MethodHandle / bootstrap / annotation surfaces."""
    try:
        count, entries, body = AUD.parse_constant_pool(data)
    except AUD.AuditError as e:
        raise SurfaceError(_strict_code(e.code), str(e))
    out = {
        'own': '', 'member_refs': set(), 'class_refs': set(), 'framework': [],
        'method_handles': 0, 'dynamic': [], 'dynamic_constants': 0,
        'bootstrap_methods': 0, 'bootstrap_args': [], 'bootstrap_refs': set(),
        'nested_dynamic_args': 0, 'annotation_attrs': [], 'bootstrap_seen': False,
    }
    if len(body) < 8:
        raise SurfaceError('BAD_CLASS_FILE', 'truncated class body')
    this_idx = _u2(body, 2)
    out['own'] = _class_name(entries, count, this_idx)
    out['member_refs'], out['method_handles'] = _member_refs(entries, count, out)
    out['dynamic_constants'] = _dynamic_entries(entries, count, out)
    iface_count = _u2(body, 6)
    p = 8 + 2 * iface_count
    fields_count = _u2(body, p)
    p += 2
    for _ in range(fields_count):
        if p + 8 > len(body):
            raise SurfaceError('BAD_CLASS_FILE', 'truncated field info')
        p = _walk_attrs(body, p + 8, _u2(body, p + 6), entries, count, out)
    methods_count = _u2(body, p)
    p += 2
    for _ in range(methods_count):
        if p + 8 > len(body):
            raise SurfaceError('BAD_CLASS_FILE', 'truncated method info')
        p = _walk_attrs(body, p + 8, _u2(body, p + 6), entries, count, out)
    attrs_count = _u2(body, p)
    p += 2
    p = _walk_attrs(body, p, attrs_count, entries, count, out)
    if p != len(body):
        raise SurfaceError('BAD_CLASS_FILE', 'class body consumed ' + str(p)
                           + ' of ' + str(len(body)) + ' bytes')
    if out['dynamic_constants'] and not out['bootstrap_seen']:
        raise SurfaceError('BOOTSTRAP_MISSING',
                           'dynamic constants without BootstrapMethods attribute')
    for _i, _tag, bsm, _name, _desc in out['dynamic']:
        if bsm < 0 or bsm >= out['bootstrap_methods']:
            raise SurfaceError('BAD_BOOTSTRAP_INDEX',
                               'bootstrap_method_attr_index out of range: ' + str(bsm))
    return out


def scan_jar(path):
    if not os.path.isfile(path):
        raise SurfaceError('JAR_IO', 'mod jar not found: ' + os.path.basename(path))
    try:
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist()
                           if not n.endswith('/') and n.endswith('.class'))
            if not names:
                raise SurfaceError('NO_CLASS_ENTRIES', 'mod jar contains no class entries')
            if len(names) != len(set(names)):
                raise SurfaceError('DUPLICATE_CLASS_ENTRY', 'duplicate .class entry names')
            per = []
            for name in names:
                try:
                    data = z.read(name)
                except (OSError, RuntimeError, zipfile.BadZipFile) as e:
                    raise SurfaceError('JAR_IO', 'cannot read ' + name + ': ' + str(e))
                try:
                    per.append((name, parse_class(data)))
                except SurfaceError as e:
                    raise SurfaceError(e.code, name + ': ' + str(e))
    except SurfaceError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as e:
        raise SurfaceError('JAR_IO', 'cannot scan mod jar: ' + str(e))
    return per


def aggregate(per):
    own = set(info['own'] for _, info in per)
    members = Counter()
    member_origins = {}
    classes = Counter()
    class_origins = {}
    framework = Counter()
    framework_raw = {}
    framework_attrs = {}
    annotation_attrs = Counter()
    method_handles = 0
    bootstrap_methods = 0
    bootstrap_args = 0
    dynamic_constants = 0
    nested_dynamic_args = 0
    for _entry, info in per:
        method_handles += info['method_handles']
        bootstrap_methods += info['bootstrap_methods']
        bootstrap_args += len(info['bootstrap_args'])
        dynamic_constants += info['dynamic_constants']
        nested_dynamic_args += info['nested_dynamic_args']
        for a in info['annotation_attrs']:
            annotation_attrs[a] += 1
        for key in info['member_refs']:
            members[key] += 1
            member_origins.setdefault(key, set()).add('METHOD_HANDLE')
        for cls, origin in info['class_refs']:
            classes[cls] += 1
            class_origins.setdefault(cls, set()).add(origin)
        for cls, raw, attr, _antype, _elem in info['framework']:
            framework[cls] += 1
            framework_raw.setdefault(cls, set()).add(raw)
            framework_attrs.setdefault(cls, set()).add(attr)
    return {
        'own': own, 'members': members, 'member_origins': member_origins,
        'classes': classes, 'class_origins': class_origins,
        'framework': framework, 'framework_raw': framework_raw,
        'framework_attrs': framework_attrs, 'annotation_attrs': annotation_attrs,
        'method_handles': method_handles, 'bootstrap_methods': bootstrap_methods,
        'bootstrap_args': bootstrap_args, 'dynamic_constants': dynamic_constants,
        'nested_dynamic_args': nested_dynamic_args,
    }


def read_text(path, code):
    try:
        with open(path, 'rb') as fh:
            raw = fh.read()
    except OSError as e:
        raise SurfaceError(code + '_IO', 'cannot read ' + os.path.basename(path) + ': ' + str(e))
    try:
        return raw, raw.decode('utf-8')
    except UnicodeDecodeError as e:
        raise SurfaceError(code + '_BAD_UTF8', str(e))


def parse_decl(path):
    raw, text = read_text(path, 'DECL')
    classes = set()
    members = set()
    rows = 0
    kinds = Counter()
    for lineno, line in enumerate(text.split('\n'), 1):
        line = line.rstrip('\r')
        if not line or line[0] == '#':
            continue
        p = line.split('\t')
        if p[0] not in ('C', 'S', 'M', 'F'):
            raise SurfaceError('DECL_BAD_ROW', 'bad decl row ' + str(lineno))
        if len(p) < 2 or not AUD.valid_owner(p[1]):
            raise SurfaceError('DECL_BAD_OWNER', 'bad decl owner at row ' + str(lineno))
        if p[0] == 'C' and len(p) != 2:
            raise SurfaceError('DECL_BAD_ROW', 'C row needs 2 columns at line ' + str(lineno))
        if p[0] == 'S' and len(p) not in (2, 3, 4):
            raise SurfaceError('DECL_BAD_ROW', 'S row needs 2-4 columns at line ' + str(lineno))
        if p[0] in ('M', 'F'):
            if len(p) != 4:
                raise SurfaceError('DECL_BAD_ROW', p[0] + ' row needs 4 columns at line ' + str(lineno))
            if not AUD.valid_member_name(p[2]):
                raise SurfaceError('DECL_BAD_MEMBER', 'bad member name at line ' + str(lineno))
            if not (AUD.is_method_desc(p[3]) if p[0] == 'M' else AUD.is_field_desc(p[3])):
                raise SurfaceError('DECL_BAD_DESC', 'bad ' + p[0] + ' desc at line ' + str(lineno))
            members.add((p[0], p[1], p[2], p[3]))
        rows += 1
        kinds[p[0]] += 1
        classes.add(p[1])
    if not classes:
        raise SurfaceError('DECL_NO_CLASSES', 'decl contains no class rows')
    return {
        'classes': classes, 'members': members, 'rows': rows,
        'kinds': dict(kinds), 'sha256': hashlib.sha256(raw).hexdigest(),
    }


def parse_map(path, decl_classes):
    if not path:
        return {'cmap': {}, 'bad_targets': [], 'ignored': 0, 'sha256': '', 'rows': 0}
    try:
        mp = CR.parse_map(path, decl_classes)
    except CR.ClassRefError as e:
        raise SurfaceError(_strict_code(e.code), str(e))
    return mp


def map_descriptor(desc, cmap):
    def one(m):
        inner = m.group(1)
        return 'L' + cmap.get(inner, inner) + ';'
    new = re.sub(r'L([^;]+);', one, desc)
    if not (AUD.is_field_desc(new) or AUD.is_method_desc(new)):
        raise SurfaceError('BAD_MAPPED_DESCRIPTOR', 'invalid mapped descriptor: ' + repr(new))
    return new


def classify_owner(owner, own, decl_classes, cmap, prefixes):
    if owner in own:
        return 'SELF', '', '', ''
    if owner.startswith(EXTERNAL_PREFIXES):
        return 'EXTERNAL', '', '', ''
    if owner.startswith(tuple(prefixes)):
        if owner in decl_classes:
            return 'RESOLVE', '', '', ''
        target = cmap.get(owner, '')
        if target and target in decl_classes:
            return 'RENAME', target, '', 'MAPPED_CLASS'
        return 'MISSING', target, '', ''
    return 'THIRD_PARTY', '', '', ''


def classify(agg, decl, mp, prefixes, allow_third_party):
    refs = []
    status = []
    reasons = set()
    mapped_to = {}
    samples = {s: [] for s in ALLOWED_STATUS}
    cmap = mp['cmap']
    for key in sorted(agg['members']):
        kind, owner, name, desc = key
        mapped_owner = cmap.get(owner, '')
        try:
            mapped_desc = map_descriptor(desc, cmap) if mapped_owner else ''
        except SurfaceError:
            raise
        st = ''
        reason = ''
        if owner in agg['own']:
            st = 'SELF'
        elif owner.startswith(EXTERNAL_PREFIXES):
            st = 'EXTERNAL'
        elif owner.startswith(tuple(prefixes)):
            if key in decl['members']:
                st = 'RESOLVE'
            elif mapped_owner and (kind, mapped_owner, name, mapped_desc) in decl['members']:
                st = 'RENAME'
                mapped_to[owner] = mapped_owner
            else:
                st = 'MISSING'
                if mapped_owner:
                    reason = 'MAPPED_TARGET_MISSING'
        else:
            st = 'THIRD_PARTY'
        if reason:
            reasons.add(reason)
        label = kind + '|' + owner + '|' + name + '|' + desc
        status.append(st)
        samples[st].append(label)
        refs.append({
            'bucket': 'LINKAGE', 'kind': kind, 'owner': owner, 'name': name,
            'desc': desc, 'status': st, 'occurrences': agg['members'][key],
            'origins': sorted(agg['member_origins'].get(key, set())),
            'mapped_owner': mapped_owner, 'mapped_desc': mapped_desc,
        })
    for cls in sorted(agg['classes']):
        st, target, _d, reason = classify_owner(
            cls, agg['own'], decl['classes'], cmap, prefixes)
        if reason:
            reasons.add(reason)
        if target:
            mapped_to[cls] = target
        status.append(st)
        samples[st].append('C|' + cls)
        refs.append({
            'bucket': 'CLASS_SURFACE', 'kind': 'C', 'owner': cls, 'name': '',
            'desc': '', 'status': st, 'occurrences': agg['classes'][cls],
            'origins': sorted(agg['class_origins'].get(cls, set())),
            'mapped_owner': target, 'mapped_desc': '',
        })
    for cls in sorted(agg['framework']):
        if cls in agg['own']:
            st = 'SELF'
        elif cls.startswith(EXTERNAL_PREFIXES):
            st = 'EXTERNAL'
        elif cls.startswith(tuple(prefixes)):
            st = 'FRAMEWORK_UNRESOLVED'
        else:
            st = 'THIRD_PARTY'
        status.append(st)
        samples[st].append('FRAMEWORK|' + cls)
        refs.append({
            'bucket': 'FRAMEWORK', 'kind': 'C', 'owner': cls, 'name': '',
            'desc': '|'.join(sorted(agg['framework_raw'].get(cls, set()))),
            'status': st, 'occurrences': agg['framework'][cls],
            'origins': sorted(agg['framework_attrs'].get(cls, set())),
            'mapped_owner': '', 'mapped_desc': '',
        })
    if mp['bad_targets']:
        reasons.add('MAP_TARGET_MISSING')
    if 'THIRD_PARTY' in status:
        if allow_third_party:
            reasons.add('THIRD_PARTY_WAIVED')
        else:
            reasons.add('UNCLASSIFIED_REFS')
    if agg['framework']:
        reasons.add('FRAMEWORK_CLASS_LITERALS')
    if agg['dynamic_constants']:
        reasons.add('DYNAMIC_BOOTSTRAP_UNPROVEN')
    if agg['nested_dynamic_args']:
        reasons.add('NESTED_DYNAMIC_ARGUMENT')
    game_labels = [r for r in refs
                   if r['owner'].startswith(tuple(prefixes)) and r['bucket'] != 'FRAMEWORK']
    if not game_labels:
        reasons.add('NO_GAME_REFS')
    if not refs:
        reasons.add('NO_SURFACE_REFS')
    refs.sort(key=lambda r: (r['bucket'], r['kind'], r['owner'], r['name'], r['desc']))
    return {
        'refs': refs, 'status': status, 'samples': samples, 'reasons': reasons,
        'mapped_to': dict(sorted(mapped_to.items())),
    }


def base_report(args):
    return {
        'schema': SCHEMA, 'tool': TOOL, 'claim_policy': CLAIM_POLICY,
        'linkage_spec': LINKAGE_SPEC, 'framework_spec': FRAMEWORK_SPEC,
        'scope': SCOPE, 'disclaimer': DISCLAIMER,
        'version': args.version or '',
        'decl': os.path.basename(args.decl), 'decl_sha256': '',
        'expected_decl_sha256': args.decl_sha256 or '', 'decl_digest_ok': None,
        'decl_rows': 0, 'decl_row_kinds': {}, 'decl_members': 0,
        'decl_view_conflict': False,
        'map': os.path.basename(args.map) if args.map else '',
        'map_sha256': '', 'map_rows': 0, 'map_ignored_rows': 0,
        'map_target_missing': [],
        'modjar': os.path.basename(args.modjar), 'classes': 0,
        'member_refs': 0, 'member_unique': 0, 'method_handles': 0,
        'bootstrap_methods': 0, 'bootstrap_args': 0, 'dynamic_constants': 0,
        'nested_dynamic_args': 0, 'framework_literals': 0,
        'framework_unique': 0, 'class_surface_refs': 0,
        'annotation_attributes': {},
        'own_classes': 0, 'own_game_classes': [], 'own_external_classes': [],
        'counts_by_status': {s: 0 for s in ALLOWED_STATUS},
        'samples_by_status': {s: [] for s in ALLOWED_STATUS},
        'mapped_to': {}, 'refs': [], 'game_prefixes': [],
        'allow_third_party': bool(args.allow_third_party),
        'coverage_only': bool(args.coverage_only),
        'verdict': 'UNSUPPORTED', 'reasons': [], 'error': '',
    }


def audit(args):
    report = base_report(args)
    reasons = set()
    if args.version and any(c.isspace() for c in args.version):
        reasons.add('BAD_VERSION')
    if args.decl_sha256 and not re.fullmatch(r'[0-9a-f]{64}', args.decl_sha256):
        reasons.add('BAD_DECL_SHA256')
    bad_prefixes = [p for p in args.game_prefix if not p or any(c.isspace() for c in p)
                    or '.' in p or p.startswith('/')]
    prefixes = sorted(set(list(GAME_PREFIXES) + [p for p in args.game_prefix if p not in bad_prefixes]))
    report['game_prefixes'] = prefixes
    if bad_prefixes:
        reasons.add('BAD_GAME_PREFIX')
    decl = None
    mp = {'cmap': {}, 'bad_targets': [], 'ignored': 0, 'sha256': '', 'rows': 0}
    per = []
    try:
        decl = parse_decl(args.decl)
        report['decl_sha256'] = decl['sha256']
        report['decl_rows'] = decl['rows']
        report['decl_row_kinds'] = decl['kinds']
        report['decl_members'] = len(decl['members'])
        if args.decl_sha256:
            report['decl_digest_ok'] = args.decl_sha256 == decl['sha256']
            if not report['decl_digest_ok']:
                reasons.add('DECL_DIGEST_MISMATCH')
        try:
            view = CR.parse_decl(args.decl)
            if view['classes'] != decl['classes']:
                reasons.add('DECL_VIEW_CONFLICT')
                report['decl_view_conflict'] = True
        except CR.ClassRefError as e:
            reasons.add('DECL_VIEW_CONFLICT')
            report['decl_view_conflict'] = True
            report['error'] = str(e)
        mp = parse_map(args.map, decl['classes'])
        report['map_sha256'] = mp['sha256']
        report['map_rows'] = mp['rows']
        report['map_ignored_rows'] = mp['ignored']
        report['map_target_missing'] = mp['bad_targets']
        if mp['bad_targets']:
            reasons.add('MAP_TARGET_MISSING')
        per = scan_jar(args.modjar)
        report['classes'] = len(per)
        agg = aggregate(per)
        report['member_refs'] = sum(agg['members'].values())
        report['member_unique'] = len(agg['members'])
        report['method_handles'] = agg['method_handles']
        report['bootstrap_methods'] = agg['bootstrap_methods']
        report['bootstrap_args'] = agg['bootstrap_args']
        report['dynamic_constants'] = agg['dynamic_constants']
        report['nested_dynamic_args'] = agg['nested_dynamic_args']
        report['framework_literals'] = sum(agg['framework'].values())
        report['framework_unique'] = len(agg['framework'])
        report['class_surface_refs'] = len(agg['classes'])
        report['annotation_attributes'] = dict(sorted(agg['annotation_attrs'].items()))
        report['own_classes'] = len(agg['own'])
        own_game = sorted(o for o in agg['own'] if o.startswith(tuple(prefixes)))
        own_external = sorted(o for o in agg['own'] if o.startswith(EXTERNAL_PREFIXES))
        report['own_game_classes'] = own_game
        report['own_external_classes'] = own_external
        if own_game:
            reasons.add('OWN_GAME_NAMESPACE')
        if own_external:
            reasons.add('OWN_EXTERNAL_NAMESPACE')
        cls = classify(agg, decl, mp, prefixes, args.allow_third_party)
        reasons |= cls['reasons']
        counts = Counter(cls['status'])
        report['counts_by_status'] = {s: counts.get(s, 0) for s in ALLOWED_STATUS}
        report['samples_by_status'] = {s: sorted(cls['samples'][s])[:20] for s in ALLOWED_STATUS}
        report['mapped_to'] = cls['mapped_to']
        report['refs'] = cls['refs']
    except SurfaceError as e:
        reasons.add(e.code)
        report['error'] = str(e)
    if decl is None:
        reasons.add('NO_DECL')
    if not per and not any(r in reasons for r in ('JAR_IO', 'NO_CLASS_ENTRIES',
                                                  'DUPLICATE_CLASS_ENTRY', 'NO_DECL')):
        reasons.add('NO_SCANNABLE_CLASSES')
    report['reasons'] = sorted(reasons)
    c = report['counts_by_status']
    report['needs_manual'] = c['MISSING'] + c['RENAME'] + c['FRAMEWORK_UNRESOLVED']
    hard = any(r in HARD_REASONS for r in reasons)
    soft = bool(reasons - HARD_REASONS)
    if hard:
        report['verdict'] = 'UNSUPPORTED'
    elif args.coverage_only:
        report['verdict'] = 'SURFACE_ONLY_OK'
    elif report['needs_manual'] or soft:
        report['verdict'] = 'NEEDS_MANUAL'
    else:
        report['verdict'] = 'SURFACE_OK'
    return report


def write_json(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def _csv_value(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return '1' if v else '0'
    return v


def write_summary(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    row = {c: _csv_value(report.get(c, '')) for c in SUMMARY_COLS}
    c = report['counts_by_status']
    row['resolve'] = c['RESOLVE']
    row['rename'] = c['RENAME']
    row['missing'] = c['MISSING']
    row['external'] = c['EXTERNAL']
    row['third_party'] = c['THIRD_PARTY']
    row['self_count'] = c['SELF']
    row['framework_unresolved'] = c['FRAMEWORK_UNRESOLVED']
    row['map_target_missing'] = '|'.join(report.get('map_target_missing', []))
    row['reasons'] = '|'.join(report.get('reasons', []))
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(SUMMARY_COLS), lineterminator='\n')
        w.writeheader()
        w.writerow(row)


def stdout_line(report):
    c = report['counts_by_status']
    line = (
        'linkage_surface: verdict=' + report['verdict']
        + ' classes=' + str(report['classes'])
        + ' member_refs=' + str(report['member_refs'])
        + ' method_handles=' + str(report['method_handles'])
        + ' bootstraps=' + str(report['bootstrap_methods'])
        + ' dynamic=' + str(report['dynamic_constants'])
        + ' framework_literals=' + str(report['framework_literals'])
        + ' resolve=' + str(c['RESOLVE'])
        + ' rename=' + str(c['RENAME'])
        + ' missing=' + str(c['MISSING'])
        + ' external=' + str(c['EXTERNAL'])
        + ' third_party=' + str(c['THIRD_PARTY'])
        + ' self=' + str(c['SELF'])
        + ' framework_unresolved=' + str(c['FRAMEWORK_UNRESOLVED'])
        + ' needs_manual=' + str(report.get('needs_manual', 0))
    )
    reasons = report.get('reasons', [])
    if reasons:
        line += ' reasons=' + '|'.join(reasons)
    if report['verdict'] in ('SURFACE_OK', 'SURFACE_ONLY_OK', 'NEEDS_MANUAL'):
        line += '; ' + DISCLAIMER
    return line


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--decl', required=True, help='target LinkCheck decl TSV (C/S/M/F rows)')
    ap.add_argument('--modjar', required=True, help='mod jar whose .class files are audited')
    ap.add_argument('--map', help='optional C-rename map TSV')
    ap.add_argument('--version', help='target version label; no runtime meaning')
    ap.add_argument('--decl-sha256', help='bind the decl to an exact sha256 digest')
    ap.add_argument('--game-prefix', action='append', default=[],
                    help='additional internal-name prefix requiring decl coverage; repeatable')
    ap.add_argument('--allow-third-party', action='store_true',
                    help='explicitly waive third-party namespaces; they are NOT assumed stable')
    ap.add_argument('--coverage-only', action='store_true',
                    help='explicitly waive NEEDS_MANUAL; still reports every unresolved reference')
    ap.add_argument('--out', help='write deterministic JSON report')
    ap.add_argument('--summary', help='write deterministic one-row CSV summary')
    a = ap.parse_args(argv)
    try:
        report = audit(a)
    except SurfaceError as e:
        report = base_report(a)
        report['verdict'] = 'UNSUPPORTED'
        report['reasons'] = [e.code]
        report['error'] = str(e)
    except (OSError, ValueError, TypeError, re.error) as e:
        report = base_report(a)
        report['verdict'] = 'UNSUPPORTED'
        report['reasons'] = ['INTERNAL_ERROR']
        report['error'] = str(e)
    if a.out:
        write_json(a.out, report)
    if a.summary:
        write_summary(a.summary, report)
    print(stdout_line(report))
    if report['verdict'] not in ('SURFACE_OK', 'SURFACE_ONLY_OK'):
        detail = '; '.join(report['reasons'])
        if not detail and report['verdict'] == 'NEEDS_MANUAL':
            detail = 'NEEDS_MANUAL refs=' + str(report.get('needs_manual', 0))
        if report.get('error'):
            detail += ' - ' + str(report['error'])
        print('linkage_surface: FAIL: ' + detail, file=sys.stderr)
    return EXIT_CODE.get(report['verdict'], 1)


if __name__ == '__main__':
    sys.exit(main())
