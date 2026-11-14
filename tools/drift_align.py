#!/usr/bin/env python3
"""drift_align.py - 用稳定身份对齐 BodyHash 输出, 量化"同名同签名方法"的实现变化。

身份口径(关键, 别用混淆短名当身份):
  * 1.21.1 / 1.21.11 的 client jar 里类名/成员名是混淆短名(a, fgi$a ...),
    同一个短名跨版本会被复用给完全无关的类, 绝不能当身份。本脚本用该版本
    官方 ProGuard 映射, 把 (obfOwner, obfName, obfDesc) 反解成
    (真实类内部名, 真实成员名, 真实描述符) 作为身份。
  * 26.1 / 26.3 起官方去混淆, (owner, name, desc) 本身就是真实身份。
  * 两版都落到"真实命名"空间, 因此 1.21.11 <-> 26.1 可跨断代直接对齐。
  * 本口径只依赖官方 ProGuard 映射, 不需要 Fabric intermediary。

输出只有两类: 聚合计数 JSON(可安全分发, 纯数字) 与匿名身份哈希 TSV
(sha256(真实身份)[:16], 前 N 条)。不输出任何真实类名/方法名, 不复制
任何 Mojang 映射文本或 client jar 字节。BodyHash 的中间 tsv 含真实成员名,
属测量中间产物, 不得分发(见 data/NOTICE-mappings.md)。

用法:
  python3 tools/drift_align.py --repo <repo_root> --spec <spec.json> --out-dir <dir>
spec 结构见 data/drift-spec.example.json; 所有输入路径由使用者自备,
脚本不下载、不硬编码任何本机路径。
"""
import argparse, hashlib, json, os, sys


def obf_identity_tables(proguard, parse_proguard, remapdesc):
    """返回 (obf2real, offmem, stats).
    obf2real : {混淆短类名 -> 真实类内部名(斜杠)}
    offmem   : {(混淆类名, 混淆成员名, 混淆描述符) -> 真实成员名}
    """
    pcls, pmem = parse_proguard(proguard)
    obf2real = {v: k.replace('.', '/') for k, v in pcls.items()}
    pcls_slash = {k.replace('.', '/'): v for k, v in pcls.items()}
    offmem = {}
    for (ro, rn, rd), obf in pmem.items():
        oo = pcls.get(ro)
        if oo is None:
            continue
        offmem[(oo, obf, remapdesc(rd, pcls_slash))] = rn
    stats = dict(proguard_classes=len(pcls), proguard_members=len(pmem),
                 official_members=len(offmem))
    return obf2real, offmem, stats


def load(path, tables, remapdesc):
    rows, skipped = {}, 0
    with open(path, 'r', encoding='utf-8') as f:
        for ln in f:
            if not ln or ln[0] == '#':
                continue
            p = ln.rstrip('\n').split('\t')
            if len(p) < 7:
                continue
            owner, name, desc, sk, op, call, n = p[0], p[1], p[2], p[3], p[4], p[5], int(p[6])
            if tables is None:
                rid = (owner, name, desc)
            else:
                obf2real, offmem, _ = tables
                rn = offmem.get((owner, name, desc))
                ro = obf2real.get(owner)
                if rn is None or ro is None:
                    skipped += 1
                    continue
                rid = (ro, rn, remapdesc(desc, obf2real))
            rows[rid] = (sk, op, call, n)
    return rows, skipped


def compare(tag, a, sa, b, sb, calls_comparable, out_dir, anon_limit):
    common = set(a) & set(b)
    opcode_diff = operand_diff = call_diff = identical = 0
    anon = []
    for k in sorted(common):
        s1, o1, c1, n1 = a[k]
        s2, o2, c2, n2 = b[k]
        h = hashlib.sha256(('\x00'.join(k)).encode()).hexdigest()[:16]
        if o1 != o2:
            opcode_diff += 1
            kind = 'OPCODE_DIFF'
        elif s1 != s2:
            operand_diff += 1
            kind = 'OPERAND_DIFF'
        elif calls_comparable and c1 != c2:
            call_diff += 1
            kind = 'CALL_TARGET_DIFF'
        else:
            identical += 1
            continue
        if len(anon) < anon_limit:
            anon.append((h, kind, n1, n2))
    detectable = opcode_diff + operand_diff + call_diff
    out = dict(pair=tag, old_methods=len(a), new_methods=len(b),
               old_unmapped=sa, new_unmapped=sb,
               aligned_same_real_identity=len(common),
               opcode_diff=opcode_diff, operand_diff=operand_diff,
               call_target_diff=call_diff,
               detectable_impl_change=detectable,
               detectable_pct=round(100.0 * detectable / max(1, len(common)), 2),
               identical_all_fingerprints=identical,
               identical_pct=round(100.0 * identical / max(1, len(common)), 2),
               calls_comparable=calls_comparable)
    with open(os.path.join(out_dir, 'drift-anon-' + tag.replace('->', '_') + '.tsv'), 'w', encoding='utf-8') as f:
        f.write('# sha256(realIdentity)[:16]\tkind\toldInsn\tnewInsn\n')
        for h, kind, n1, n2 in anon:
            f.write('%s\t%s\t%d\t%d\n' % (h, kind, n1, n2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', required=True, help='仓库根(用于 import tools/bridge.py)')
    ap.add_argument('--spec', required=True, help='版本/映射/pair 配置 JSON')
    ap.add_argument('--out-dir', required=True, help='聚合 JSON 与匿名样例输出目录')
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(a.repo, 'tools'))
    from bridge import parse_proguard, remapdesc

    spec = json.load(open(a.spec, encoding='utf-8'))
    os.makedirs(a.out_dir, exist_ok=True)
    anon_limit = int(spec.get('anon_limit', 4000))

    bodies = {}
    for ver, cfg in spec['versions'].items():
        if cfg.get('obfuscated'):
            tables = obf_identity_tables(cfg['proguard'], parse_proguard, remapdesc)
            print('OBF_TABLES %s %s' % (ver, json.dumps(tables[2])), file=sys.stderr)
        else:
            tables = None
        bodies[ver] = load(cfg['body'], tables, remapdesc)
        print('BODY %s methods=%d skip=%d' % (ver, len(bodies[ver][0]), bodies[ver][1]), file=sys.stderr)

    res = []
    for pair in spec['pairs']:
        old, new, calls = pair['old'], pair['new'], bool(pair.get('calls', False))
        tag = old + '->' + new
        res.append(compare(tag, bodies[old][0], bodies[old][1],
                           bodies[new][0], bodies[new][1], calls, a.out_dir, anon_limit))
    for o in res:
        print(json.dumps(o, ensure_ascii=False))
    with open(os.path.join(a.out_dir, 'drift-summary.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
