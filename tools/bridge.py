#!/usr/bin/env python3
"""bridge.py - 用官方 ProGuard 映射 + Fabric intermediary 建立
   intermediary 名 <-> Mojang 真实名 的桥接表。

背景 / 为什么需要它:
  26.1 起 Mojang 不再混淆游戏 jar, 官方也不再发布 obfuscation map,
  Fabric intermediary 的 mappings.tiny 变成 572 字节空表, yarn 返回 []。
  于是所有引用 net/minecraft/class_XXXX 的旧 mod 对 26.1 直接 0% 可解析。
  但 1.21.11 及以前每个版本都有官方 ProGuard 映射(真实名 -> 混淆短名),
  又有 intermediary(混淆短名 -> class_XXXX)。两者拼起来就能得到
  class_XXXX / method_YYYYY -> Mojang 真实名, 而 26.1 用的正是真实名。

用法:
  python3 bridge.py --proguard map-<ver>.txt --intermediary i-<ver>.jar --out bridge-<ver>.pkl
  python3 bridge.py --proguard ... --intermediary ... --out bridge-<ver>.tsv --tsv

输出 pkl: (i2r_cls, i2r_mem)
  i2r_cls : {interClassInternal -> realClassInternal}
  i2r_mem : {(interOwner, interName, interDesc) -> realMemberName}
            interDesc 以 '(' 开头者是方法, 否则是字段。

关键踩坑:
  * ProGuard 映射左侧是 **点分真实名**, 右侧是混淆短名; 拼描述符时必须
    先把左侧换成斜杠内部名再替换, 否则 Lnet.minecraft.X; 与 Lnet/minecraft/X;
    对不上 —— 第一次实现没做这层, 成员对齐率只有 40%, 修好后 99%。
  * tiny v2 行序是 \tm\t<desc>\t<officialName>\t<interName>; v1 是
    METHOD <owner> <desc> <officialName> <interName>。列序写反会让 0% 命中。
  * 官方映射里同一个真实类会出现多次(类的不同部分被拆到多个块), 解析时
    要按 "当前类头" 累积, 不能用 dict 去重后丢掉后续块。
  * ProGuard 成员行的行号前缀形如 9:10: 或 128:128:, 要先剥掉。
  * 输出必须 sorted(cls.items()) / sorted(mem.items()): 中间经过 set 求交,
    迭代顺序受 PYTHONHASHSEED 影响, 不排序会语义相同但 sha256 每次不同
    (CI 无法校验产物)。2026-11-14 实测 3 个 seed 修复后字节一致。
"""
import argparse, pickle, re, zipfile

PRIM = {'void':'V','boolean':'Z','byte':'B','char':'C','short':'S',
        'int':'I','long':'J','float':'F','double':'D'}
LNR = re.compile(r'^(?:\d+:\d+:)+')
TYPEREF = re.compile(r'L([^;]+);')

def typ2desc_real(t):
    """ProGuard 行里的 Java 类型 -> JVM 描述符(真实名, 斜杠内部名)."""
    t = t.strip()
    dim = 0
    while t.endswith('[]'):
        t = t[:-2]; dim += 1
    base = PRIM[t] if t in PRIM else 'L' + t.replace('.', '/') + ';'
    return '[' * dim + base

def parse_proguard(path):
    """返回 cls{realDotName -> obfShort}, mem{(realOwnerDot, realMember, realDesc) -> obfName}."""
    cls, mem = {}, {}
    cur = None
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for ln in f:
            ln = ln.rstrip('\n')
            if not ln:
                continue
            if not ln[0].isspace():
                if ' -> ' in ln and not ln.startswith('#'):
                    left, right = ln.split(' -> ')
                    cur = left.strip()
                    cls[cur] = right.strip().rstrip(':')
                continue
            if cur is None:
                continue
            s = LNR.sub('', ln.strip())
            if ' -> ' not in s or s.startswith('#'):
                continue
            left, obf = s.rsplit(' -> ', 1)
            left, obf = left.strip(), obf.strip()
            if left.endswith(')'):
                i = left.index('(')
                head, args = left[:i].strip(), left[i+1:-1]
                if ' ' not in head:
                    continue
                ret, mname = head.rsplit(' ', 1)
                parts = [a for a in args.split(',') if a.strip()]
                d = '(' + ''.join(typ2desc_real(a) for a in parts) + ')' + typ2desc_real(ret)
                mem[(cur, mname, d)] = obf
            else:
                if ' ' not in left:
                    continue
                ftype, fname = left.rsplit(' ', 1)
                mem[(cur, fname, typ2desc_real(ftype))] = obf
    return cls, mem

def parse_tiny(path):
    """返回 clsm{obf -> inter}, mem{(obfOwner, obfName, obfDesc) -> interName}."""
    z = zipfile.ZipFile(path)
    txt = z.read('mappings/mappings.tiny').decode('utf-8')
    lines = txt.split('\n')
    hdr = lines[0].split('\t')
    clsm, mem = {}, {}
    if hdr[0] == 'v1':
        for ln in lines[1:]:
            if not ln: continue
            p = ln.split('\t')
            if p[0] == 'CLASS':
                clsm[p[1]] = p[2]
            elif p[0] in ('METHOD', 'FIELD'):
                mem[(p[1], p[3], p[2])] = p[4]
    else:
        cur = None
        for ln in lines[1:]:
            if not ln: continue
            if ln.startswith('c\t'):
                p = ln.split('\t'); cur = p[1]; clsm[cur] = p[2]
            elif ln.startswith('\tm\t') or ln.startswith('\tf\t'):
                p = ln.split('\t'); mem[(cur, p[3], p[2])] = p[4]
    return clsm, mem

def remapdesc(d, m):
    return TYPEREF.sub(lambda x: 'L' + m.get(x.group(1), x.group(1)) + ';', d)

def build(proguard, intermediary):
    pcls, pmem = parse_proguard(proguard)
    tcls, tmem = parse_tiny(intermediary)
    # 斜杠内部名版本的 real -> obf, 用于替换描述符里的类型
    pcls_slash = {k.replace('.', '/'): v for k, v in pcls.items()}
    offmem = {}
    for (ro, rn, rd), obf in pmem.items():
        oo = pcls.get(ro)
        if oo is None: continue
        offmem[(oo, obf, remapdesc(rd, pcls_slash))] = rn
    aligned = set(offmem) & set(tmem)
    i2r_cls, i2r_mem = {}, {}
    for real, obf in pcls.items():
        i = tcls.get(obf)
        if i: i2r_cls[i] = real.replace('.', '/')
    for (oo, obf, od) in aligned:
        io = tcls.get(oo, oo)
        ii = tmem[(oo, obf, od)]
        i2r_mem[(io, ii, remapdesc(od, tcls))] = offmem[(oo, obf, od)]
    stat = dict(proguard_classes=len(pcls), tiny_classes=len(tcls),
                proguard_members=len(pmem), tiny_members=len(tmem),
                aligned_members=len(aligned),
                align_pct=round(100.0 * len(aligned) / max(1, len(tmem)), 2),
                i2r_classes=len(i2r_cls), i2r_members=len(i2r_mem))
    return stat, i2r_cls, i2r_mem

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--proguard', required=True)
    ap.add_argument('--intermediary', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--tsv', action='store_true', help='输出 TSV 而非 pkl')
    a = ap.parse_args()
    stat, cls, mem = build(a.proguard, a.intermediary)
    import json
    print(json.dumps(stat, ensure_ascii=False))
    if a.tsv:
        with open(a.out, 'w', encoding='utf-8') as f:
            # 确定性输出: 中间经过 set 求交, 迭代顺序受 PYTHONHASHSEED 影响。
            # 不排序会让两次运行语义相同但字节不同, CI 无法用 sha256 校验产物。
            for k, v in sorted(cls.items()):
                f.write('C\t%s\t%s\n' % (k, v))
            for (o, n, d), v in sorted(mem.items()):
                f.write('%s\t%s\t%s\t%s\t%s\n' % ('M' if d.startswith('(') else 'F', o, d, n, v))
    else:
        with open(a.out, 'wb') as f:
            pickle.dump((cls, mem), f)

if __name__ == '__main__':
    main()
