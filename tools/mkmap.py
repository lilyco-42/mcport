#!/usr/bin/env python3
"""mkmap.py - 生成 McPort 重映射表.

用法: python3 mkmap.py <src-intermediary.jar> <dst-intermediary.jar> <out.tsv>

为什么以 intermediary 名为桥:
  官方混淆名在不同版本会被复用给完全无关的类, 不能当身份;
  class_XXXX / method_XXXXX 才是跨版本稳定身份。
  因此不产生类改名, 只产生 (owner, descriptor) 在源/目标两侧均唯一的成员改名。

输出:
  M\t<owner>\t<desc>\t<oldName>\t<newName>
  F\t<owner>\t<desc>\t<oldName>\t<newName>
"""
import sys, zipfile, re

def parse_tiny_ids(path):
    """解析 Fabric intermediary 的 mappings.tiny, 返回 (cls, methods, fields)。

    cls     : {officialName -> intermediaryName}
    methods : set of (ownerInter, nameInter, descInter)
    fields  : 同上

    tiny v1 的列顺序是: METHOD <owner> <desc> <official> <intermediary>
    (注意: 第 3 列是描述符, 第 4 列才是 official 名 —— 早期版本这里写反过,
     导致名字与描述符互换, 所有解析全部失败。)
    tiny v2 是缩进层级: c / \tm / \tf, 列序为 <srcName> <dstName> <desc>。
    """
    z = zipfile.ZipFile(path)
    txt = z.read('mappings/mappings.tiny').decode('utf-8')
    lines = txt.split('\n')
    hdr = lines[0].split('\t')
    cls, raw = {}, []
    if hdr[0] == 'v1':
        for ln in lines[1:]:
            if not ln: continue
            p = ln.split('\t')
            if p[0] == 'CLASS':
                cls[p[1]] = p[2]
            elif p[0] in ('METHOD', 'FIELD'):
                raw.append((p[0][0], p[1], p[2], p[4]))   # (M/F, owner, desc, interName)
    else:
        cur = None; kind = None
        for ln in lines[1:]:
            if not ln: continue
            if ln.startswith('c\t'):
                p = ln.split('\t'); cur = p[1]; cls[cur] = p[2]
            elif ln.startswith('\tm\t'):
                p = ln.split('\t'); raw.append(('M', cur, p[2], p[4]))
            elif ln.startswith('\tf\t'):
                p = ln.split('\t'); raw.append(('F', cur, p[2], p[4]))
    def rdesc(d):
        return re.sub(r'L([^;]+);', lambda m: 'L' + cls.get(m.group(1), m.group(1)) + ';', d)
    M, F = set(), set()
    for (kind, o, desc, name) in raw:
        if not o: continue
        rec = (cls.get(o, o), name, rdesc(desc))
        (M if kind == 'M' else F).add(rec)
    return cls, M, F


def by_od(entries):
    d = {}
    for (o, n, ds) in entries:
        d.setdefault((o, ds), set()).add(n)
    return d


def main():
    src, dst, out = sys.argv[1], sys.argv[2], sys.argv[3]
    sm, sf = parse_tiny_ids(src)[1], parse_tiny_ids(src)[2]
    dm, df = parse_tiny_ids(dst)[1], parse_tiny_ids(dst)[2]
    lines = ['# mcport map %s -> %s (intermediary identity, no class renames)'
             % (src.split('/')[-1], dst.split('/')[-1])]
    nm = nf = 0
    for kind, s, d in (('M', sm, dm), ('F', sf, df)):
        sod, dod = by_od(s), by_od(d)
        for k, v in sod.items():
            if len(v) == 1 and k in dod and len(dod[k]) == 1:
                lines.append('%s\t%s\t%s\t%s\t%s' % (kind, k[0], k[1], list(v)[0], list(dod[k])[0]))
                if kind == 'M': nm += 1
                else: nf += 1
    open(out, 'w').write('\n'.join(lines) + '\n')
    tot = len(sm) + len(sf)
    print('%s: M=%d F=%d  (src members: M=%d F=%d)  rename coverage %.1f%%'
          % (out, nm, nf, len(sm), len(sf), 100.0 * (nm + nf) / max(1, tot)))


if __name__ == '__main__':
    main()
