#!/usr/bin/env python3
"""McPort StringSurface: fail-loud auditor/rewriter for the non-bytecode name surface.

Why this exists
---------------
ASM ClassRemapper rewrites CONSTANT_Class / NameAndType / descriptors / Type / Handle
constant-pool values, but org.objectweb.asm.commons.Remapper.mapValue() returns plain
String constants unchanged.  RemapTool also copies every non-.class jar entry verbatim.
Mixin refmaps (*.refmap.json), mixin configs and Class.forName-style LDC strings therefore
live on a second name surface that the symbol预言机 never sees.  This tool makes that
surface explicit and can apply only exact, target-verified renames.

It never guesses a semantic mapping.  An old class token is rewritten only when:
  1) it is absent from the target declaration table,
  2) a unique C line maps it to a new owner present in that target table,
  3) for member-like strings, the exact (oldOwner, oldDesc, oldName) M/F line exists
     (optionally via S-line inheritance) and the (newOwner, newName, mappedDesc)
     member is declared/inherited by the target table.

Everything else is fail-loud: left byte-identical and written to triage.tsv.
"""
import argparse
import collections
import io
import json
import os
import re
import struct
import sys
import zipfile
from pathlib import Path

SCHEMA = 1
SLASH_TOKEN = r'(?:net/minecraft|com/mojang)/[A-Za-z0-9_/$]+'
DOT_TOKEN = r'(?:net\.minecraft|com\.mojang)\.[A-Za-z0-9_.$]+'
TOKEN_RE = re.compile(r'(?P<slash>' + SLASH_TOKEN + r')|(?P<dot>' + DOT_TOKEN + r')')
MEMBER_RE = re.compile(
    r'^L(?P<owner>' + SLASH_TOKEN + r');(?P<name>[A-Za-z0-9_$<>]+)'
    r'(?:(?P<mdesc>\([^)]*\).+)|:(?P<fdesc>.+))$')
BARE_MEMBER_RE = re.compile(r'^L(' + SLASH_TOKEN + r');(method_\d+|field_\d+)$')
NO_OWNER_INTER_RE = re.compile(r'^(?:method_\d+|field_\d+)(?:\(.*\)|.+)$')
EXTERNAL_PREFIXES = (
    'com/mojang/authlib/', 'com/mojang/brigadier/', 'com/mojang/serialization/',
    'com/mojang/datafixers/', 'com/mojang/logging/', 'com/mojang/authlib/',
)
REWRITABLE = {'EXACT_REMAP', 'MEMBER_EXACT_REMAP'}
UNRESOLVED = {
    'UNRESOLVED', 'MAPPED_TARGET_MISSING', 'MEMBER_TARGET_MISSING',
    'NO_OWNER_MEMBER', 'NAMED_NO_OWNER', 'MEMBER_MISSING_DESC',
    'INVALID_JSON', 'DECODE_FAIL', 'CP_PARSE_FAIL', 'AMBIGUOUS',
}


def load_rows(path):
    with open(path, encoding='utf-8') as f:
        for line in f:
            if not line or line[0] == '#':
                continue
            yield line.rstrip('\n').split('\t')


class Mapper:
    def __init__(self, decl_path, map_path):
        self.decl_classes = set()
        self.decl_methods = set()
        self.decl_fields = set()
        self.decl_sup = {}
        self.decl_ifs = {}
        self.cls = {}
        self.meth = {}
        self.fld = {}
        self.sup = {}
        self.ifs = {}
        self._decl_member_cache = {}
        self._map_member_cache = {}
        for p in load_rows(decl_path):
            if p[0] == 'C' and len(p) >= 2:
                self.decl_classes.add(p[1])
            elif p[0] == 'M' and len(p) >= 4:
                self.decl_methods.add((p[1], p[2], p[3]))
            elif p[0] == 'F' and len(p) >= 4:
                self.decl_fields.add((p[1], p[2], p[3]))
            elif p[0] == 'S' and len(p) >= 3:
                self.decl_sup[p[1]] = p[2]
                self.decl_ifs[p[1]] = (p[3].split(',') if len(p) > 3 and p[3] else [])
        for p in load_rows(map_path):
            if p[0] == 'C' and len(p) >= 3:
                self.cls[p[1]] = p[2]
            elif p[0] == 'M' and len(p) >= 5:
                self.meth[(p[1], p[2], p[3])] = p[4]
            elif p[0] == 'F' and len(p) >= 5:
                self.fld[(p[1], p[2], p[3])] = p[4]
            elif p[0] == 'S' and len(p) >= 3:
                self.sup[p[1]] = p[2]
                self.ifs[p[1]] = (p[3].split(',') if len(p) > 3 and p[3] else [])

    @staticmethod
    def is_external(tok):
        return tok.startswith(EXTERNAL_PREFIXES)

    def token_status(self, tok):
        """tok is an internal slash name. returns (ok, new, status, reason)."""
        if tok in self.decl_classes:
            return True, tok, 'TARGET_PRESENT', 'target class already declared'
        if tok in self.cls:
            new = self.cls[tok]
            if new in self.decl_classes:
                return True, new, 'RENAME_EXACT', 'exact class rename verified against target decl'
            return False, tok, 'MAPPED_TARGET_MISSING', 'C target class absent from target decl'
        if self.is_external(tok):
            return True, tok, 'EXTERNAL', 'independent library or JDK namespace'
        return False, tok, 'UNRESOLVED', 'no target decl and no exact C line'

    def map_tokens(self, s):
        matches = list(TOKEN_RE.finditer(s))
        if not matches:
            return s, 'NO_GAME_TOKEN', ''
        statuses, reasons, changed = [], [], False
        repl = []
        for m in matches:
            dotted = m.group('dot') is not None
            text = m.group('dot') if dotted else m.group('slash')
            core = text.replace('.', '/') if dotted else text
            ok, newcore, st, why = self.token_status(core)
            new = newcore.replace('/', '.') if dotted else newcore
            if not ok:
                return s, st, why
            if new != text:
                changed = True
            statuses.append(st)
            if why:
                reasons.append(why)
            repl.append((m.start(), m.end(), new))
        for a, b, new in reversed(repl):
            s = s[:a] + new + s[b:]
        if changed:
            return s, 'EXACT_REMAP', ';'.join(sorted(set(reasons)))
        if 'RENAME_EXACT' in statuses:
            return s, 'EXACT_REMAP', 'mapped to same spelling'
        if 'EXTERNAL' in statuses and 'TARGET_PRESENT' not in statuses:
            return s, 'EXTERNAL', 'external namespace only'
        return s, 'TARGET_PRESENT', 'all class tokens already declared'

    def _bfs(self, start, sup, ifs, table, cache, key):
        """map tables are dicts keyed (owner,desc,name) -> newName."""
        if key in cache:
            return cache[key]
        q = collections.deque([start])
        seen = set()
        found = set()
        while q:
            c = q.popleft()
            if not c or c in seen:
                continue
            seen.add(c)
            hit = table.get((c, key[1], key[2]))
            if hit is not None:
                found.add(hit)
            s0 = sup.get(c)
            if s0 and s0 != 'java/lang/Object':
                q.append(s0)
            for i0 in ifs.get(c, []):
                if i0:
                    q.append(i0)
        out = next(iter(found)) if len(found) == 1 else None
        cache[key] = out
        return out

    def map_member_name(self, kind, owner, desc, name):
        table = self.meth if kind == 'M' else self.fld
        cache = self._map_member_cache.setdefault(kind, {})
        exact = table.get((owner, desc, name))
        if exact is not None:
            return exact, 'exact M/F line'
        hit = self._bfs(owner, self.sup, self.ifs, table, cache, (owner, desc, name))
        if hit is not None:
            return hit, 'unique inherited M/F line'
        return None, 'no exact or unique inherited M/F line'

    def decl_has_member(self, kind, owner, name, desc):
        """decl tables are sets of (owner,name,desc); BFS supertypes/interfaces."""
        table = self.decl_methods if kind == 'M' else self.decl_fields
        cache = self._decl_member_cache.setdefault(kind, {})
        ck = (owner, name, desc)
        if ck in cache:
            return cache[ck]
        q = collections.deque([owner])
        seen = set()
        hit = False
        while q:
            c = q.popleft()
            if not c or c in seen:
                continue
            seen.add(c)
            if (c, name, desc) in table:
                hit = True
                break
            s0 = self.decl_sup.get(c)
            if s0 and s0 != 'java/lang/Object':
                q.append(s0)
            for i0 in self.decl_ifs.get(c, []):
                if i0:
                    q.append(i0)
        cache[ck] = hit
        return hit

    def rewrite_member(self, s):
        if BARE_MEMBER_RE.match(s):
            return s, 'MEMBER_MISSING_DESC', 'owner+name without descriptor cannot be resolved'
        m = MEMBER_RE.match(s)
        if not m:
            return None
        owner, name = m.group('owner'), m.group('name')
        kind = 'M' if m.group('mdesc') is not None else 'F'
        desc = m.group('mdesc') if kind == 'M' else m.group('fdesc')
        ok, new_owner, ost, why = self.token_status(owner)
        if not ok:
            return s, ost, why
        if ost == 'EXTERNAL':
            return s, 'EXTERNAL', 'external owner'
        intermediary_name = name.startswith('method_') or name.startswith('field_')
        if ost == 'TARGET_PRESENT' and not intermediary_name:
            new_desc, dst, dwhy = self.map_tokens(desc)
            if dst in UNRESOLVED:
                return s, dst, dwhy
            if new_desc == desc:
                return s, 'TARGET_PRESENT', 'named member already in target namespace'
            return 'L' + new_owner + ';' + name + (new_desc if kind == 'M' else ':' + new_desc), \
                'EXACT_REMAP', 'descriptor class tokens changed'
        new_name, nwhy = self.map_member_name(kind, owner, desc, name)
        if new_name is None:
            return s, 'UNRESOLVED', nwhy
        new_desc, dst, dwhy = self.map_tokens(desc)
        if dst in UNRESOLVED:
            return s, dst, dwhy
        if not self.decl_has_member(kind, new_owner, new_name, new_desc):
            return s, 'MEMBER_TARGET_MISSING', 'mapped member absent from target decl'
        sep = '' if kind == 'M' else ':'
        new_s = 'L' + new_owner + ';' + new_name + sep + new_desc
        if new_s == s:
            return s, 'TARGET_PRESENT', 'identity member mapping'
        return new_s, 'MEMBER_EXACT_REMAP', nwhy + '; ' + dwhy

    def rewrite_string(self, s):
        member = self.rewrite_member(s)
        if member is not None:
            return member
        if TOKEN_RE.search(s):
            if NO_OWNER_INTER_RE.match(s) and ('method_' in s[:16] or 'field_' in s[:16]):
                return s, 'NO_OWNER_MEMBER', 'intermediary member without owner cannot be resolved'
            if re.match(r'^[A-Za-z0-9_$]+\(.*\)$', s) and TOKEN_RE.search(s):
                return s, 'NAMED_NO_OWNER', 'named member without owner needs human confirmation'
            return self.map_tokens(s)
        return s, 'NO_GAME_TOKEN', ''


# ---- constant pool: parse CONSTANT_String values and safely clone shared Utf8 ----

def u2(b, i):
    return struct.unpack_from('>H', b, i)[0]


def cp_parse(data):
    if len(data) < 10 or data[:4] != b'\xca\xfe\xba\xbe':
        raise ValueError('not a class file')
    n = u2(data, 8)
    entries = [None] * n
    p = 10
    i = 1
    while i < n:
        tag = data[p]
        if tag == 1:
            ln = u2(data, p + 1)
            raw = data[p:p + 3 + ln]
            p += 3 + ln
            width = 1
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            raw = data[p:p + 5]
            p += 5
            width = 1
        elif tag in (5, 6):
            raw = data[p:p + 9]
            p += 9
            width = 2
        elif tag in (7, 8, 16, 19, 20):
            raw = data[p:p + 3]
            p += 3
            width = 1
        elif tag == 15:
            raw = data[p:p + 4]
            p += 4
            width = 1
        else:
            raise ValueError('unknown constant pool tag ' + str(tag))
        entries[i] = raw
        i += width
    return n, entries, data[p:]


def cp_refs(raw):
    if raw is None:
        return []
    tag = raw[0]
    if tag in (7, 8, 16, 19, 20):
        return [u2(raw, 1)]
    if tag == 15:
        return [u2(raw, 2)]
    if tag in (9, 10, 11, 12, 17, 18):
        return [u2(raw, 1), u2(raw, 3)]
    return []


def cp_utf8(raw):
    return raw[3:].decode('utf-8', 'replace')


def cp_write(entries, body):
    out = bytearray(b'\xca\xfe\xba\xbe\x00\x00\x00\x00')
    out += struct.pack('>H', len(entries))
    for e in entries[1:]:
        if e is not None:
            out += e
    out += body
    # minor=0, major copied from the original class header at bytes 6..8
    return bytes(out)


def rewrite_class_bytes(data, mapper, observe, apply_changes):
    n, entries, body = cp_parse(data)
    major = data[6:8]
    utf8 = {}
    utf8_raw = {}
    for i, e in enumerate(entries):
        if e and e[0] == 1:
            utf8_raw[i] = e[3:]
            utf8[i] = cp_utf8(e)
    nonstring = collections.Counter()
    for i, e in enumerate(entries):
        if e and e[0] != 8:
            for r in cp_refs(e):
                nonstring[r] += 1
    clones = {}
    changed = False
    for i, e in enumerate(entries):
        if not e or e[0] != 8:
            continue
        sidx = u2(e, 1)
        old = utf8.get(sidx)
        if old is None:
            continue
        new, status, why = mapper.rewrite_string(old)
        if utf8_raw.get(sidx) != old.encode('utf-8'):
            # Modified UTF-8 / replacement chars: never re-encode and corrupt bytes.
            if status in REWRITABLE:
                status, why = 'DECODE_FAIL', 'non-plain UTF-8 constant; refusing to rewrite'
                new = old
        elif status in REWRITABLE and not new.isascii():
            status, why = 'DECODE_FAIL', 'rewritten constant is not ASCII'
            new = old
        observe(old, 'ldc', 'CP#' + str(i), new, status, why)
        if new == old or status not in REWRITABLE or not apply_changes:
            continue
        old_bytes, new_bytes = old.encode('utf-8'), new.encode('utf-8')
        raw_new = b'\x01' + struct.pack('>H', len(new_bytes)) + new_bytes
        if nonstring.get(sidx, 0) > 0:
            key = (sidx, new)
            if key not in clones:
                entries.append(raw_new)
                clones[key] = len(entries) - 1
            entries[i] = b'\x08' + struct.pack('>H', clones[key])
        else:
            entries[sidx] = raw_new
        changed = True
    if not changed:
        return data, False
    out = cp_write(entries, body)
    # cp_write left major zeroed; restore original major (minor is always 0 here).
    out = out[:6] + major + out[8:]
    return out, True


def rewrite_json_bytes(data, mapper, observe, entry, apply_changes):
    try:
        text = data.decode('utf-8')
        obj = json.loads(text)
    except UnicodeDecodeError as ex:
        observe('', 'json', entry, '', 'DECODE_FAIL', str(ex)[:120])
        return data, False
    except json.JSONDecodeError as ex:
        observe('', 'json', entry, '', 'INVALID_JSON', str(ex)[:120])
        return data, False

    changed = [False]

    def walk(o, path):
        if isinstance(o, str):
            new, status, why = mapper.rewrite_string(o)
            observe(o, 'json', path, new, status, why)
            if status in REWRITABLE and new != o:
                changed[0] = True
                return new if apply_changes else o
            return o
        if isinstance(o, list):
            return [walk(v, path + '/' + str(i)) for i, v in enumerate(o)]
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                nk = walk(k, path + '/<key>') if isinstance(k, str) else k
                if nk in out:
                    raise ValueError('JSON key collision after rewrite at ' + path)
                out[nk] = walk(v, path + '/' + str(k))
            return out
        return o

    try:
        new_obj = walk(obj, '$')
    except ValueError as ex:
        observe('', 'json', entry, '', 'INVALID_JSON', str(ex)[:120])
        return data, False
    # Never re-serialize (and thus reformat) a JSON file that has no exact rename.
    # A formatting-only diff would falsely mark every fabric.mod.json as modified.
    if not apply_changes or not changed[0]:
        return data, False
    new_data = (json.dumps(new_obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    return new_data, new_data != data


def process(target, out_root, apply_changes):
    version = target['version']
    out = Path(out_root) / version
    out.mkdir(parents=True, exist_ok=True)
    fixed = out / 'fixed'
    if apply_changes:
        fixed.mkdir(exist_ok=True)
    mapper = Mapper(target['decl'], target['map'])
    stats = collections.Counter()
    rows = []
    seen_strings = set()

    def observe(old, origin, path, new, status, why):
        stats['string_occurrences'] += 1
        stats['status_' + status] += 1
        seen_strings.add((origin, old))
        if status != 'NO_GAME_TOKEN':
            rows.append([version, path, origin, old, new, status, why.replace('\t', ' ').replace('\n', ' ')])

    for jar in target['jars']:
        stats['jars'] += 1
        base = os.path.basename(jar)
        zout = zipfile.ZipFile(fixed / base, 'w') if apply_changes else None
        jar_changed = False
        try:
            with zipfile.ZipFile(jar) as zin:
                for info in zin.infolist():
                    data = zin.read(info.filename)
                    changed = False
                    if info.filename.endswith('.class'):
                        stats['class_entries'] += 1
                        try:
                            data2, changed = rewrite_class_bytes(data, mapper, observe, apply_changes)
                        except ValueError as ex:
                            observe('', 'class', info.filename, '', 'CP_PARSE_FAIL', str(ex)[:120])
                            data2 = data
                    elif info.filename.endswith('.json') and not info.filename.startswith('assets/'):
                        stats['resource_entries'] += 1
                        data2, changed = rewrite_json_bytes(data, mapper, observe, info.filename, apply_changes)
                    else:
                        data2 = data
                    if changed:
                        stats['rewritten_entries'] += 1
                        jar_changed = True
                    if zout is not None:
                        zout.writestr(info, data2)
        finally:
            if zout is not None:
                zout.close()
        if jar_changed:
            stats['rewritten_jars'] += 1
    stats['unique_strings'] = len(seen_strings)
    stats['unresolved'] = sum(v for k, v in stats.items()
                              if k.startswith('status_') and k[len('status_'):] in UNRESOLVED)
    with open(out / 'triage.tsv', 'w', encoding='utf-8', newline='') as f:
        f.write('version\tpath\torigin\told\tnew\tstatus\treason\n')
        for r in rows:
            f.write('\t'.join(x.replace('\t', ' ').replace('\n', ' ') for x in r) + '\n')
    with open(out / 'stats.json', 'w', encoding='utf-8') as f:
        json.dump({'schema': SCHEMA, 'version': version, 'stats': dict(stats)},
                  f, ensure_ascii=False, indent=2, sort_keys=True)
    return version, dict(stats)


SUMMARY_COLS = [
    'version', 'jars', 'class_entries', 'resource_entries', 'string_occurrences',
    'unique_strings', 'no_game_token', 'target_present', 'external', 'exact_remap',
    'member_exact_remap', 'unresolved', 'mapped_target_missing', 'member_target_missing',
    'no_owner_member', 'named_no_owner', 'member_missing_desc', 'invalid_json',
    'cp_parse_fail', 'rewritten_jars', 'rewritten_entries',
]


def summary_row(stats):
    s = stats
    return [
        s.get('version', ''), s.get('jars', 0), s.get('class_entries', 0),
        s.get('resource_entries', 0), s.get('string_occurrences', 0), s.get('unique_strings', 0),
        s.get('status_NO_GAME_TOKEN', 0), s.get('status_TARGET_PRESENT', 0),
        s.get('status_EXTERNAL', 0), s.get('status_EXACT_REMAP', 0),
        s.get('status_MEMBER_EXACT_REMAP', 0), s.get('unresolved', 0),
        s.get('status_MAPPED_TARGET_MISSING', 0), s.get('status_MEMBER_TARGET_MISSING', 0),
        s.get('status_NO_OWNER_MEMBER', 0), s.get('status_NAMED_NO_OWNER', 0),
        s.get('status_MEMBER_MISSING_DESC', 0), s.get('status_INVALID_JSON', 0),
        s.get('status_CP_PARSE_FAIL', 0), s.get('rewritten_jars', 0),
        s.get('rewritten_entries', 0),
    ]


def main():
    ap = argparse.ArgumentParser(description='McPort StringSurface: exact LDC/refmap name-surface auditor')
    ap.add_argument('--spec', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--rewrite', action='store_true',
                    help='write fixed/*.jar with only exact target-verified string renames')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding='utf-8'))
    if spec.get('schema') != SCHEMA:
        raise SystemExit('spec schema must be ' + str(SCHEMA))
    targets = spec.get('targets', [])
    if not targets:
        raise SystemExit('spec has no targets')
    rows = []
    total = collections.Counter()
    for t in targets:
        for k in ('version', 'decl', 'map', 'jars'):
            if k not in t:
                raise SystemExit('target missing ' + k)
        version, stats = process(t, a.out_dir, a.rewrite)
        stats['version'] = version
        rows.append(summary_row(stats))
        for k, v in stats.items():
            if isinstance(v, int):
                total[k] += v
        if not a.quiet:
            print('TARGET', version, 'strings', stats.get('string_occurrences', 0),
                  'exact', stats.get('status_EXACT_REMAP', 0) + stats.get('status_MEMBER_EXACT_REMAP', 0),
                  'unresolved', stats.get('unresolved', 0),
                  'rewritten', stats.get('rewritten_entries', 0))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'summary.csv', 'w', encoding='utf-8', newline='') as f:
        f.write(','.join(SUMMARY_COLS) + '\n')
        for r in rows:
            f.write(','.join(str(x) for x in r) + '\n')
    unresolved = sum(r[SUMMARY_COLS.index('unresolved')] for r in rows)
    exact = sum(r[SUMMARY_COLS.index('exact_remap')] + r[SUMMARY_COLS.index('member_exact_remap')] for r in rows)
    print('RESULT targets=%d strings=%d exact=%d unresolved=%d rewritten=%d' % (
        len(rows), total.get('string_occurrences', 0), exact, unresolved,
        total.get('rewritten_entries', 0)))
    return 2 if unresolved else 0


if __name__ == '__main__':
    sys.exit(main())
