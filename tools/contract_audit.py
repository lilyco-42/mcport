#!/usr/bin/env python3
"""McPort 0.2.2 / REPORT section 21: offline canonical-contract + coverage auditor.

纯标准库；不下载、不内置、不分发 Mojang client jar、官方映射或第三方 mod 字节码。
只读取调用方自备的 LinkGate contract TSV、mod jar、可选 LinkCheck 工单 JSON。

§19/§20 的 LinkGate 为了向后兼容接受宽松 TSV：少于 4 列静默跳过、多于 4 列忽略、
状态大小写不敏感、不校验 owner/name/desc 语法、未知引用默认 RESOLVE。§21 的工具在
出货前把契约恢复成「生成器逐字节可复现 + 每个游戏命名空间引用都有证据」的 fail-loud 前提。

它不运行游戏、不改任何字节、不判定语义等价；COVERAGE_OK 仅表示本工具可见的
常量池成员引用全部被该版本契约覆盖且契约自身合法，绝不表示能跑或行为一致。
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


LGC = _load('mcport_linkgate_contract_for_audit', 'linkgate_contract.py')
CAP = LGC.cap

SCHEMA = 1
ALLOWED_STATUS = ('RESOLVE', 'RENAME', 'SIGCHG', 'MISSING')
BLOCK_STATUS = ('MISSING', 'SIGCHG')
MANUAL_STATUS = BLOCK_STATUS + ('RENAME',)
ALLOWED_HEADERS = frozenset(('schema', 'version', 'source_tickets', 'source_sha256'))
GAME_PREFIXES = (
    'net/minecraft/', 'com/mojang/blaze3d/', 'com/mojang/math/',
    'com/mojang/realmsclient/',
)
EXTERNAL_PREFIXES = (
    'java/', 'javax/', 'jdk/', 'sun/', 'com/sun/', 'org/w3c/', 'org/xml/',
    'org/ietf/', 'com/mojang/authlib/', 'com/mojang/brigadier/',
    'com/mojang/serialization/', 'com/mojang/datafixers/', 'com/mojang/logging/',
)
OWNER_RE = re.compile(r'^[A-Za-z_$][A-Za-z0-9_$]*(?:/[A-Za-z_$][A-Za-z0-9_$]*)*$')
PRIMITIVES = frozenset('BCDFIJSZ')
DISCLAIMER = 'does NOT mean runtime-compatible; RESOLVE and coverage do NOT prove semantic equivalence'
CLAIM_POLICY = 'static-contract-coverage-only; no runtime claim'
EXIT_CODE = {
    'COVERAGE_OK': 0,
    'COVERAGE_ONLY_OK': 0,
    'NEEDS_MANUAL': 2,
    'UNSUPPORTED': 1,
}
SUMMARY_COLS = (
    'schema', 'version', 'contract', 'modjar', 'contract_rows', 'contract_sha256',
    'source_sha256', 'ticket_count', 'ticket_digest_ok', 'regenerated_bytes_match',
    'classes', 'member_refs', 'covered', 'external', 'third_party', 'array_refs',
    'unknown_game_refs', 'unclassified_refs', 'stale_contract_refs',
    'known_blockers', 'renames', 'needs_manual_refs', 'verdict', 'reasons',
)


class AuditError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def u2(b, i):
    if i < 0 or i + 2 > len(b):
        raise AuditError('BAD_CLASS_FILE', 'truncated u2 at offset ' + str(i))
    return struct.unpack_from('>H', b, i)[0]


def decode_modified_utf8(raw):
    """JVMS 4.4.7 modified UTF-8: NUL is C0 80; supplementary chars are surrogate pairs."""
    out = []
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b < 0x80:
            out.append(chr(b))
            i += 1
            continue
        if b & 0xE0 == 0xC0:
            if i + 1 >= n or raw[i + 1] & 0xC0 != 0x80:
                raise AuditError('BAD_MODIFIED_UTF8', 'bad 2-byte sequence')
            out.append(chr(((b & 0x1F) << 6) | (raw[i + 1] & 0x3F)))
            i += 2
            continue
        if b & 0xF0 == 0xE0:
            if i + 2 >= n or raw[i + 1] & 0xC0 != 0x80 or raw[i + 2] & 0xC0 != 0x80:
                raise AuditError('BAD_MODIFIED_UTF8', 'bad 3-byte sequence')
            cp = ((b & 0x0F) << 12) | ((raw[i + 1] & 0x3F) << 6) | (raw[i + 2] & 0x3F)
            if 0xD800 <= cp <= 0xDBFF:
                if i + 5 >= n or raw[i + 3] & 0xF0 != 0xE0 or raw[i + 4] & 0xC0 != 0x80 or raw[i + 5] & 0xC0 != 0x80:
                    raise AuditError('BAD_MODIFIED_UTF8', 'high surrogate without low pair')
                lo = ((raw[i + 3] & 0x0F) << 12) | ((raw[i + 4] & 0x3F) << 6) | (raw[i + 5] & 0x3F)
                if not 0xDC00 <= lo <= 0xDFFF:
                    raise AuditError('BAD_MODIFIED_UTF8', 'bad low surrogate')
                out.append(chr(0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)))
                i += 6
            elif 0xDC00 <= cp <= 0xDFFF:
                raise AuditError('BAD_MODIFIED_UTF8', 'unpaired low surrogate')
            else:
                out.append(chr(cp))
                i += 3
            continue
        raise AuditError('BAD_MODIFIED_UTF8', 'unsupported byte 0x' + format(b, '02x'))
    return ''.join(out)


def valid_owner(s):
    return bool(s) and OWNER_RE.fullmatch(s) is not None


def _parse_one_type(desc, i):
    dims = 0
    while i < len(desc) and desc[i] == '[':
        dims += 1
        i += 1
    if i >= len(desc):
        return None
    c = desc[i]
    if c in PRIMITIVES:
        return i + 1
    if c == 'L':
        j = desc.find(';', i + 1)
        if j < 0 or not valid_owner(desc[i + 1:j]):
            return None
        return j + 1
    return None


def is_field_desc(desc):
    end = _parse_one_type(desc, 0)
    return end is not None and end == len(desc)


def is_method_desc(desc):
    if not desc.startswith('('):
        return False
    i = 1
    while i < len(desc) and desc[i] != ')':
        end = _parse_one_type(desc, i)
        if end is None:
            return False
        i = end
    if i >= len(desc) or desc[i] != ')':
        return False
    i += 1
    if i < len(desc) and desc[i] == 'V':
        return i + 1 == len(desc)
    end = _parse_one_type(desc, i)
    return end is not None and end == len(desc)


def valid_desc(desc):
    return is_method_desc(desc) if desc.startswith('(') else is_field_desc(desc)


def valid_member_name(name):
    return CAP.MEMBER_NAME.fullmatch(name) is not None


def _contract_error(message):
    raise AuditError('CONTRACT_NOT_CANONICAL', message)


def parse_contract(path):
    try:
        with open(path, 'rb') as fh:
            raw = fh.read()
    except OSError as e:
        raise AuditError('CONTRACT_IO', 'cannot read contract: ' + str(e))
    if b'\r' in raw:
        _contract_error('CR/CRLF is not canonical')
    if not raw.endswith(b'\n'):
        _contract_error('missing final newline')
    if b' -> ' in raw:
        _contract_error('mapping arrow leak in contract')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        raise AuditError('CONTRACT_NOT_CANONICAL', 'contract is not UTF-8: ' + str(e))
    lines = text.split('\n')[:-1]
    if not lines or not lines[0].startswith('# mcport-linkgate-contract '):
        _contract_error('missing canonical identity header')
    headers = {}
    entries = {}
    data_started = False
    for lineno, line in enumerate(lines, 1):
        if line == '':
            _contract_error('blank line at ' + str(lineno))
        if line.startswith('#'):
            if data_started:
                _contract_error('comment after data row at line ' + str(lineno))
            for tok in line[1:].split():
                if '=' not in tok:
                    continue
                k, v = tok.split('=', 1)
                if k not in ALLOWED_HEADERS:
                    _contract_error('unknown header key ' + repr(k))
                if k in headers:
                    _contract_error('duplicate header key ' + repr(k))
                headers[k] = v
            continue
        data_started = True
        parts = line.split('\t')
        if len(parts) != 4:
            _contract_error('data row needs exactly 4 TAB columns at line ' + str(lineno))
        owner, name, desc, status = parts
        for p in parts:
            if not p or p != p.strip() or any(ch.isspace() for ch in p):
                _contract_error('whitespace in data field at line ' + str(lineno))
        if not valid_owner(owner):
            _contract_error('invalid owner at line ' + str(lineno) + ': ' + repr(owner))
        if not valid_member_name(name):
            _contract_error('invalid member name at line ' + str(lineno) + ': ' + repr(name))
        if not valid_desc(desc):
            _contract_error('invalid descriptor at line ' + str(lineno) + ': ' + repr(desc))
        if status not in ALLOWED_STATUS:
            _contract_error('status must be uppercase and known at line ' + str(lineno) + ': ' + repr(status))
        key = (owner, name, desc)
        if key in entries:
            _contract_error('duplicate contract key at line ' + str(lineno) + ': ' + repr(key))
        entries[key] = status
    if not data_started:
        _contract_error('contract has no data rows')
    joined = ['\t'.join(k) for k in entries]
    if joined != sorted(joined):
        _contract_error('contract rows are not sorted by key')
    for k in ('schema', 'version', 'source_tickets', 'source_sha256'):
        if k not in headers:
            _contract_error('missing header ' + k)
    if headers['schema'] != str(SCHEMA):
        _contract_error('unsupported schema ' + repr(headers['schema']))
    version = headers['version']
    if not version or any(ch.isspace() for ch in version) or any(c in version for c in '\r\n\t'):
        _contract_error('invalid version header')
    try:
        source_tickets = int(headers['source_tickets'])
    except ValueError:
        _contract_error('source_tickets must be an integer')
    if source_tickets < 1 or str(source_tickets) != headers['source_tickets']:
        _contract_error('source_tickets must be a canonical positive integer')
    if re.fullmatch(r'[0-9a-f]{64}', headers['source_sha256']) is None:
        _contract_error('source_sha256 must be 64 lowercase hex digits')
    status_counts = {s: sum(1 for v in entries.values() if v == s) for s in ALLOWED_STATUS}
    return {
        'path': path,
        'raw': raw,
        'sha256': hashlib.sha256(raw).hexdigest(),
        'headers': headers,
        'version': version,
        'source_tickets': source_tickets,
        'source_sha256': headers['source_sha256'],
        'entries': entries,
        'row_count': len(entries),
        'status_counts': status_counts,
    }


def parse_constant_pool(data):
    if len(data) < 10 or data[:4] != b'\xca\xfe\xba\xbe':
        raise AuditError('BAD_CLASS_FILE', 'not a class file')
    count = u2(data, 8)
    if count < 2:
        raise AuditError('BAD_CLASS_FILE', 'empty constant pool')
    entries = [None] * count
    p = 10
    i = 1
    while i < count:
        if p >= len(data):
            raise AuditError('BAD_CLASS_FILE', 'truncated constant pool')
        tag = data[p]
        if tag == 1:
            if p + 3 > len(data):
                raise AuditError('BAD_CLASS_FILE', 'truncated Utf8 length')
            ln = u2(data, p + 1)
            end = p + 3 + ln
            if end > len(data):
                raise AuditError('BAD_CLASS_FILE', 'truncated Utf8 bytes')
            raw = data[p:end]
            p = end
            width = 1
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            size = 5
            if p + size > len(data):
                raise AuditError('BAD_CLASS_FILE', 'truncated tag ' + str(tag))
            raw = data[p:p + size]
            p += size
            width = 1
        elif tag in (5, 6):
            size = 9
            if p + size > len(data):
                raise AuditError('BAD_CLASS_FILE', 'truncated long/double')
            raw = data[p:p + size]
            p += size
            width = 2
        elif tag in (7, 8, 16, 19, 20):
            size = 3
            if p + size > len(data):
                raise AuditError('BAD_CLASS_FILE', 'truncated tag ' + str(tag))
            raw = data[p:p + size]
            p += size
            width = 1
        elif tag == 15:
            size = 4
            if p + size > len(data):
                raise AuditError('BAD_CLASS_FILE', 'truncated method handle')
            raw = data[p:p + size]
            p += size
            width = 1
        else:
            raise AuditError('BAD_CLASS_FILE', 'unknown constant pool tag ' + str(tag))
        entries[i] = raw
        if width == 2:
            if i + 1 >= count:
                raise AuditError('BAD_CLASS_FILE', 'long/double at final cp slot')
            entries[i + 1] = None
        i += width
    body = data[p:]
    if len(body) < 14:
        raise AuditError('BAD_CLASS_FILE', 'truncated class body')
    return count, entries, body


def class_member_refs(data):
    count, entries, _body = parse_constant_pool(data)

    def entry(idx, tag):
        if idx <= 0 or idx >= count or entries[idx] is None:
            raise AuditError('BAD_CLASS_FILE', 'bad cp index ' + str(idx))
        e = entries[idx]
        if e[0] != tag:
            raise AuditError('BAD_CLASS_FILE', 'cp index ' + str(idx) + ' is tag ' + str(e[0]) + ', expected ' + str(tag))
        return e

    def utf8(idx):
        e = entry(idx, 1)
        return decode_modified_utf8(e[3:])

    refs = set()
    for i in range(1, count):
        e = entries[i]
        if e is None or e[0] not in (9, 10, 11):
            continue
        ci, ni = u2(e, 1), u2(e, 3)
        cls = entry(ci, 7)
        nat = entry(ni, 12)
        owner = utf8(u2(cls, 1))
        name = utf8(u2(nat, 1))
        desc = utf8(u2(nat, 3))
        refs.add((owner, name, desc))
    return refs


def scan_jar(path):
    if not os.path.isfile(path):
        raise AuditError('JAR_IO', 'mod jar not found: ' + os.path.basename(path))
    try:
        with zipfile.ZipFile(path) as z:
            names = sorted(n for n in z.namelist() if not n.endswith('/') and n.endswith('.class'))
            if not names:
                raise AuditError('NO_CLASS_ENTRIES', 'mod jar contains no class entries')
            if len(names) != len(set(names)):
                raise AuditError('DUPLICATE_CLASS_ENTRY', 'duplicate .class entry names')
            refs = set()
            for name in names:
                try:
                    data = z.read(name)
                except (OSError, RuntimeError, zipfile.BadZipFile) as e:
                    raise AuditError('JAR_IO', 'cannot read ' + name + ': ' + str(e))
                refs |= class_member_refs(data)
    except AuditError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as e:
        raise AuditError('JAR_IO', 'cannot scan mod jar: ' + str(e))
    return len(names), refs


def collect_external_refs(paths):
    out = set()
    for path in paths:
        try:
            det = LGC.read_ticket(path)
        except LGC.ContractError as e:
            raise AuditError('TICKET_READ_ERROR', str(e))
        for raw in det.get('EXTERNAL', []):
            ref = CAP.parse_ref(raw)
            if ref is None:
                raise AuditError('BAD_EXTERNAL_REF', 'unparseable EXTERNAL ref: ' + repr(raw))
            _kind, owner, name, desc = ref
            out.add((owner, name, desc))
    return out


def owner_namespace(owner):
    if not owner.startswith('['):
        return owner
    end = _parse_one_type(owner, 0)
    if end is None or end != len(owner):
        raise AuditError('BAD_ARRAY_OWNER', 'invalid array class name: ' + repr(owner))
    i = 0
    while i < len(owner) and owner[i] == '[':
        i += 1
    if i < len(owner) and owner[i] == 'L':
        return owner[i + 1:-1]
    return 'java/lang/Object'


def ref_label(key):
    return key[0] + '|' + key[1] + '|' + key[2]


def classify_refs(refs, contract_entries, external_refs, game_prefixes, allow_third_party):
    covered = Counter()
    unknown = []
    unclassified = []
    stale = sorted(set(contract_entries) - refs)
    external_count = 0
    third_party_count = 0
    array_count = 0
    for key in sorted(refs):
        owner, name, desc = key
        ns = owner_namespace(owner)
        if owner.startswith('['):
            array_count += 1
        ns_key = (ns, name, desc)
        if key in external_refs or ns_key in external_refs or ns.startswith(EXTERNAL_PREFIXES):
            external_count += 1
            continue
        if ns.startswith(tuple(game_prefixes)):
            if key in contract_entries:
                covered[contract_entries[key]] += 1
            else:
                unknown.append(key)
        else:
            third_party_count += 1
            if not allow_third_party:
                unclassified.append(key)
    known_blockers = sum(covered[s] for s in BLOCK_STATUS)
    renames = covered['RENAME']
    needs_manual = sum(covered[s] for s in MANUAL_STATUS)
    return {
        'covered': sum(covered.values()),
        'covered_by_status': {s: covered[s] for s in ALLOWED_STATUS},
        'external': external_count,
        'third_party': third_party_count,
        'array_refs': array_count,
        'unknown_game_refs': len(unknown),
        'unknown_game_ref_samples': [ref_label(k) for k in unknown[:20]],
        'unclassified_refs': len(unclassified),
        'unclassified_ref_samples': [ref_label(k) for k in unclassified[:20]],
        'stale_contract_refs': len(stale),
        'stale_ref_samples': [ref_label(k) for k in stale[:20]],
        'known_blockers': known_blockers,
        'renames': renames,
        'needs_manual_refs': needs_manual,
    }


def base_report(args):
    return {
        'schema': SCHEMA,
        'claim_policy': CLAIM_POLICY,
        'disclaimer': DISCLAIMER,
        'contract': os.path.basename(args.contract),
        'modjar': os.path.basename(args.modjar),
        'version': args.version or '',
        'tickets': [os.path.basename(p) for p in (args.ticket or [])],
        'contract_rows': 0,
        'contract_sha256': '',
        'source_sha256': '',
        'ticket_count': 0,
        'ticket_source_sha256': None,
        'ticket_digest_ok': None,
        'regenerated_bytes_match': None,
        'external_refs_from_tickets': 0,
        'classes': 0,
        'member_refs': 0,
        'covered': 0,
        'covered_by_status': {s: 0 for s in ALLOWED_STATUS},
        'external': 0,
        'third_party': 0,
        'array_refs': 0,
        'unknown_game_refs': 0,
        'unknown_game_ref_samples': [],
        'unclassified_refs': 0,
        'unclassified_ref_samples': [],
        'stale_contract_refs': 0,
        'stale_ref_samples': [],
        'known_blockers': 0,
        'renames': 0,
        'needs_manual_refs': 0,
        'third_party_waived': bool(args.allow_third_party),
        'coverage_only': bool(args.coverage_only),
        'fail_stale': bool(args.fail_stale),
        'verdict': 'UNSUPPORTED',
        'reasons': [],
    }


def audit(args):
    report = base_report(args)
    contract = parse_contract(args.contract)
    version = contract['version']
    report.update({
        'version': version,
        'contract_rows': contract['row_count'],
        'contract_sha256': contract['sha256'],
        'source_sha256': contract['source_sha256'],
        'status_counts': contract['status_counts'],
        'expected_version': args.version or '',
    })
    reasons = []
    if args.version and args.version != version:
        reasons.append('VERSION_MISMATCH')
    external_refs = set()
    if args.ticket:
        try:
            ticket_paths = LGC.collect(args.ticket)
        except LGC.ContractError as e:
            reasons.append('TICKET_GLOB_ERROR')
            report['ticket_error'] = str(e)
        else:
            report['ticket_count'] = len(ticket_paths)
            report['tickets'] = sorted(os.path.basename(p) for p in ticket_paths)
            digest = LGC.source_digest(ticket_paths)
            report['ticket_source_sha256'] = digest
            report['ticket_digest_ok'] = digest == contract['source_sha256']
            if not report['ticket_digest_ok']:
                reasons.append('TICKET_DIGEST_MISMATCH')
            if len(ticket_paths) != contract['source_tickets']:
                reasons.append('TICKET_COUNT_MISMATCH')
            try:
                regen, stats, _conflicts = LGC.build(ticket_paths, version)
                regen_bytes = regen.encode('utf-8')
                report['regenerated_bytes_match'] = regen_bytes == contract['raw']
                report['regenerated_unique_refs'] = stats['unique']
                if not report['regenerated_bytes_match']:
                    reasons.append('REGENERATION_MISMATCH')
                external_refs = collect_external_refs(ticket_paths)
            except LGC.ContractError as e:
                reasons.append('TICKET_REGEN_ERROR')
                report['regenerated_bytes_match'] = False
                report['ticket_error'] = str(e)
            except AuditError as e:
                reasons.append(e.code)
                report['regenerated_bytes_match'] = False
                report['ticket_error'] = str(e)
    report['external_refs_from_tickets'] = len(external_refs)
    bad_prefixes = [p for p in args.game_prefix if not p or any(c.isspace() for c in p) or '.' in p or p.startswith('/')]
    prefixes = list(GAME_PREFIXES) + [p for p in args.game_prefix if p not in bad_prefixes]
    report['game_prefixes'] = sorted(set(prefixes))
    if bad_prefixes:
        reasons.append('BAD_GAME_PREFIX')
        report['bad_game_prefixes'] = sorted(bad_prefixes)
    try:
        classes, refs = scan_jar(args.modjar)
    except AuditError as e:
        reasons.append(e.code)
        report['jar_error'] = str(e)
        classes, refs = 0, set()
    report['classes'] = classes
    report['member_refs'] = len(refs)
    if classes > 0 and not refs:
        reasons.append('NO_MEMBER_REFS')
    if refs:
        cov = classify_refs(refs, contract['entries'], external_refs, prefixes, args.allow_third_party)
        report.update(cov)
        if cov['unknown_game_refs']:
            reasons.append('UNKNOWN_GAME_REFS')
        if cov['unclassified_refs']:
            reasons.append('UNCLASSIFIED_REFS')
        if cov['covered'] + cov['unknown_game_refs'] == 0:
            reasons.append('NO_GAME_REFS')
        if args.fail_stale and cov['stale_contract_refs']:
            reasons.append('STALE_CONTRACT_REFS')
    else:
        reasons.append('NO_SCANNABLE_REFS')
    reasons = sorted(set(reasons))
    report['reasons'] = reasons
    if reasons:
        report['verdict'] = 'UNSUPPORTED'
    elif args.coverage_only:
        report['verdict'] = 'COVERAGE_ONLY_OK'
    elif report['needs_manual_refs']:
        report['verdict'] = 'NEEDS_MANUAL'
    else:
        report['verdict'] = 'COVERAGE_OK'
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
    row['reasons'] = '|'.join(report.get('reasons', []))
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(SUMMARY_COLS), lineterminator='\n')
        w.writeheader()
        w.writerow(row)


def stdout_line(report):
    line = (
        'contract_audit: verdict=' + report.get('verdict', 'UNSUPPORTED')
        + ' contract_rows=' + str(report.get('contract_rows', 0))
        + ' classes=' + str(report.get('classes', 0))
        + ' member_refs=' + str(report.get('member_refs', 0))
        + ' covered=' + str(report.get('covered', 0))
        + ' external=' + str(report.get('external', 0))
        + ' third_party=' + str(report.get('third_party', 0))
        + ' unknown=' + str(report.get('unknown_game_refs', 0))
        + ' unclassified=' + str(report.get('unclassified_refs', 0))
        + ' stale=' + str(report.get('stale_contract_refs', 0))
        + ' needs_manual=' + str(report.get('needs_manual_refs', 0))
    )
    reasons = report.get('reasons', [])
    if reasons:
        line += ' reasons=' + '|'.join(reasons)
    if report.get('verdict') in ('COVERAGE_OK', 'COVERAGE_ONLY_OK'):
        line += '; ' + DISCLAIMER
    return line


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--contract', required=True, help='canonical LinkGate contract TSV')
    ap.add_argument('--modjar', required=True, help='mod jar whose .class constant pools are audited')
    ap.add_argument('--version', help='expected target version; binds contract header')
    ap.add_argument('--ticket', action='append', default=[],
                    help='LinkCheck ticket glob for exact regeneration and EXTERNAL classification; repeatable')
    ap.add_argument('--game-prefix', action='append', default=[],
                    help='additional internal-name prefix requiring contract coverage; repeatable')
    ap.add_argument('--allow-third-party', action='store_true',
                    help='explicitly waive unclassified non-game refs; they are NOT assumed stable')
    ap.add_argument('--coverage-only', action='store_true',
                    help='explicitly waive NEEDS_MANUAL; still reports every MISSING/SIGCHG/RENAME')
    ap.add_argument('--fail-stale', action='store_true',
                    help='fail when contract keys are absent from this jar (per-mod contracts only)')
    ap.add_argument('--out', help='write deterministic JSON report')
    ap.add_argument('--summary', help='write deterministic one-row CSV summary')
    a = ap.parse_args(argv)
    try:
        report = audit(a)
    except AuditError as e:
        report = base_report(a)
        report['verdict'] = 'UNSUPPORTED'
        report['reasons'] = [e.code]
        report['error'] = str(e)
        report['disclaimer'] = DISCLAIMER
    except (OSError, ValueError, TypeError) as e:
        report = base_report(a)
        report['verdict'] = 'UNSUPPORTED'
        report['reasons'] = ['INTERNAL_ERROR']
        report['error'] = str(e)
        report['disclaimer'] = DISCLAIMER
    if a.out:
        write_json(a.out, report)
    if a.summary:
        write_summary(a.summary, report)
    print(stdout_line(report))
    if report['verdict'] not in ('COVERAGE_OK', 'COVERAGE_ONLY_OK'):
        detail = '; '.join(report['reasons'])
        if not detail and report.get('verdict') == 'NEEDS_MANUAL':
            detail = 'NEEDS_MANUAL refs=' + str(report.get('needs_manual_refs', 0))
        if report.get('error'):
            detail += ' - ' + str(report['error'])
        print('contract_audit: FAIL: ' + detail, file=sys.stderr)
    return EXIT_CODE.get(report['verdict'], 1)


if __name__ == '__main__':
    sys.exit(main())
