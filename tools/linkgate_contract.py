#!/usr/bin/env python3
"""§19 启动期闸门契约生成器：把 LinkCheck 工单聚合成 LinkGate 可直接读的 TSV。

纯标准库；只读取仓库已分发的聚合工单 JSON（data/hotmods/*.json 等），不读 Mojang
client jar、不读官方映射、不读第三方 mod 字节码。输出只有 (owner,name,desc,status)
四列，绝不输出 RENAME 的目标新名（那属于映射表，不是启动期契约）。

与 §18 的差别：capability.py 回答「这批证据够不够出货」；这里把同一批证据降级成
每个进程启动时可独立校验的 per-mod/per-version 能力契约。契约是某个目标版本的
符号事实快照；未知引用默认 RESOLVE，绝不把「表里没写」当成「一定能跑」。
"""

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'mcport_capability', os.path.join(HERE, 'capability.py'))
cap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cap)

SCHEMA = 1
BUCKETS = ('RESOLVE', 'RENAME', 'SIGCHG', 'MISSING')
ALL_BUCKETS = BUCKETS + ('EXTERNAL',)


class ContractError(Exception):
    """输入不完整、票据自相矛盾或引用不可解析：一律拒绝生成契约。"""


def source_digest(paths):
    """输入内容锚点：按 basename + 原始字节排序算 SHA-256，不含绝对路径。"""
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: os.path.basename(x)):
        h.update(os.path.basename(p).encode('utf-8') + b'\0')
        with open(p, 'rb') as fh:
            h.update(fh.read())
        h.update(b'\0')
    return h.hexdigest()


def collect(patterns):
    paths = []
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        if not hits:
            raise ContractError('no ticket matches ' + repr(pattern))
        paths.extend(hits)
    uniq = sorted(set(os.path.abspath(p) for p in paths))
    if not uniq:
        raise ContractError('no tickets')
    return uniq


def read_ticket(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            d = json.load(fh)
    except (OSError, ValueError) as e:
        raise ContractError('cannot read ticket ' + os.path.basename(path) + ': ' + str(e))
    if not isinstance(d, dict) or not isinstance(d.get('details'), dict):
        raise ContractError('ticket lacks details: ' + os.path.basename(path))
    det = d['details']
    # 工单完整性：标量计数、details 长度、total 必须自洽（与 §18 gate_tickets 同纪律）。
    scalars = {'RESOLVE': 'resolve', 'RENAME': 'rename',
               'SIGCHG': 'sigchg', 'MISSING': 'missing'}
    for bucket, key in scalars.items():
        v = d.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v != len(det.get(bucket, [])):
            raise ContractError('scalar/details mismatch ' + key + ': ' + os.path.basename(path))
    total = d.get('total')
    if not isinstance(total, int) or isinstance(total, bool) or total != sum(
            len(v) for v in det.values() if isinstance(v, list)):
        raise ContractError('total/details mismatch: ' + os.path.basename(path))
    for bucket, arr in det.items():
        if not isinstance(arr, list):
            raise ContractError('details bucket is not a list: ' + bucket)
    return det


def build(paths, version):
    if not version or any(c in version for c in '\r\n\t'):
        raise ContractError('invalid version')
    entries = {}
    conflicts = []
    stats = Counter()
    for path in paths:
        det = read_ticket(path)
        stats['tickets'] += 1
        for bucket in ALL_BUCKETS:
            for raw in det.get(bucket, []):
                stats['raw_' + bucket.lower()] += 1
                if bucket == 'EXTERNAL':
                    continue  # 外部库不属于游戏目标版本契约；LinkGate 对未知引用按 RESOLVE
                if not isinstance(raw, str):
                    raise ContractError('non-string ref in ' + bucket + ': ' + os.path.basename(path))
                ref = cap.parse_ref(raw)
                if ref is None:
                    raise ContractError('unparseable ref in ' + bucket + ': ' + repr(raw))
                _kind, owner, name, desc = ref
                key = owner + '\t' + name + '\t' + desc
                if key in entries and entries[key] != bucket:
                    conflicts.append(key + ': ' + entries[key] + '/' + bucket)
                else:
                    entries[key] = bucket
    if conflicts:
        raise ContractError('contradictory statuses: ' + '; '.join(sorted(conflicts)[:3]))
    stats['unique'] = len(entries)
    stats['duplicates'] = sum(stats['raw_' + b.lower()] for b in BUCKETS) - len(entries)
    for key, status in entries.items():
        stats['contract_' + status.lower()] += 1
    lines = [
        '# mcport-linkgate-contract schema=' + str(SCHEMA) + ' version=' + version,
        '# source_tickets=' + str(len(paths)) + ' source_sha256=' + source_digest(paths),
        '# UNKNOWN refs default to RESOLVE; READY/RESOLVE does NOT mean runtime-compatible.',
        '# owner<TAB>name<TAB>desc<TAB>status',
    ]
    for key in sorted(entries):
        lines.append(key + '\t' + entries[key])
    return '\n'.join(lines) + '\n', stats, len(conflicts)


def summary_row(version, paths, stats):
    return {
        'version': version,
        'tickets': stats['tickets'],
        'raw_refs': sum(stats['raw_' + b.lower()] for b in ALL_BUCKETS),
        'external_ignored': stats['raw_external'],
        'unique_contract_refs': stats['unique'],
        'duplicate_refs': stats['duplicates'],
        'resolve': stats['contract_resolve'],
        'rename': stats['contract_rename'],
        'sigchg': stats['contract_sigchg'],
        'missing': stats['contract_missing'],
        'source_sha256': source_digest(paths),
    }


def write_summary(path, row):
    import csv
    cols = ['version', 'tickets', 'raw_refs', 'external_ignored',
           'unique_contract_refs', 'duplicate_refs', 'resolve', 'rename',
           'sigchg', 'missing', 'source_sha256']
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator='\n')
        w.writeheader()
        w.writerow(row)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ticket', action='append', required=True,
                    help='LinkCheck 工单 JSON glob，可重复')
    ap.add_argument('--version', required=True, help='目标 MC 版本标签，如 26.1')
    ap.add_argument('--out', required=True, help='输出 LinkGate contract TSV')
    ap.add_argument('--summary', help='可选：输出一行确定性聚合统计 CSV')
    a = ap.parse_args(argv)
    try:
        paths = collect(a.ticket)
        text, stats, conflicts = build(paths, a.version)
    except ContractError as e:
        print('linkgate_contract: FAIL: ' + str(e), file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    if a.summary:
        write_summary(a.summary, summary_row(a.version, paths, stats))
    print('linkgate_contract: version=' + a.version + ' tickets=' + str(stats['tickets'])
          + ' unique=' + str(stats['unique']) + ' conflicts=' + str(conflicts)
          + ' out=' + a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
