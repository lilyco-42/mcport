#!/usr/bin/env python3
"""mkdecl.py - 导出目标版本的 API 声明表(intermediary 命名空间, 含继承关系).

用法:
  python3 mkdecl.py --intermediary i-<ver>.jar --client client-<ver>.jar --out decl-<ver>.tsv

输出:
  C\t<class>
  S\t<class>\t<super>\t<iface,...>
  M\t<owner>\t<name>\t<desc>
  F\t<owner>\t<name>\t<desc>

设计要点(踩过的坑):
  * 成员声明必须以**目标版本真实字节码**为准, 不能用 tiny 映射当声明表。
    tiny 只映射被混淆的名字, 编译器合成成员(<init>, values(), ordinal(),
    桥接方法)根本不在里面 —— 用 tiny 当声明表会把 8.5% 的合法引用误判成
    "member gone", 连"目标==源版本"的控制组都跑不到 100%。
  * this_class/super_class/interfaces 都是 CONSTANT_Class(tag=7) 索引,
    必须再经 name_index 才拿到 Utf8 名。
  * 26.1 起官方不再混淆, tiny 几乎为空, 此时 decl 直接以 official 名呈现 ——
    这本身就是 26.1 断代的事实。
"""
import argparse, struct, zipfile


def parse_tiny(path):
    """返回 classMap {official -> intermediary}, 以及 memberMap {(officialOwner, officialName, desc) -> interName}."""
    z = zipfile.ZipFile(path)
    txt = z.read('mappings/mappings.tiny').decode('utf-8')
    lines = txt.split('\n')
    hdr = lines[0].split('\t')
    cls, mem = {}, {}
    if hdr[0] == 'v1':
        # v1: METHOD <owner> <desc> <official> <intermediary>
        for ln in lines[1:]:
            if not ln: continue
            p = ln.split('\t')
            if p[0] == 'CLASS':
                cls[p[1]] = p[2]
            elif p[0] in ('METHOD', 'FIELD'):
                mem[(p[1], p[3], p[2])] = p[4]
    else:
        # v2: <indent>m <desc> <official> <intermediary>
        cur = None
        for ln in lines[1:]:
            if not ln: continue
            if ln.startswith('c\t'):
                p = ln.split('\t'); cur = p[1]; cls[cur] = p[2]
            elif ln.startswith('\tm\t'):
                p = ln.split('\t'); mem[(cur, p[3], p[2])] = p[4]
            elif ln.startswith('\tf\t'):
                p = ln.split('\t'); mem[(cur, p[3], p[2])] = p[4]
    return cls, mem


def parse_class(data):
    """返回 (thisName, superName, [ifaces], [(kind,'name','desc',flags)]), 全部为 jar 内 official 名."""
    n = struct.unpack('>H', data[8:10])[0]
    utf, clsref = {}, {}
    pos, i = 10, 1
    while i < n:
        tag = data[pos]; pos += 1
        if tag == 1:
            ln = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
            utf[i] = data[pos:pos + ln].decode('utf-8', 'replace'); pos += ln
        elif tag == 7:
            clsref[i] = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
        elif tag in (8, 16, 19, 20): pos += 2
        elif tag == 15: pos += 3
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18): pos += 4
        elif tag in (5, 6): pos += 8; i += 1
        else: raise ValueError('tag %d' % tag)
        i += 1

    def cn(idx):
        ni = clsref.get(idx)
        return None if ni is None else utf.get(ni)

    pos += 2  # access_flags
    ti = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
    si = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
    ic = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
    ifs = []
    for _ in range(ic):
        ifs.append(struct.unpack('>H', data[pos:pos + 2])[0]); pos += 2
    members = []
    for kind in ('f', 'm'):
        cnt = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
        for _ in range(cnt):
            flags = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
            ni, di = struct.unpack('>HH', data[pos:pos + 4]); pos += 4
            members.append((kind, utf.get(ni, ''), utf.get(di, ''), flags))
            # field_info 与 method_info 一样都有 attributes_count + attributes,
            # 早期版本这里给 field 直接 pos += 2 是错的, 会让后续所有成员解析错位。
            ac = struct.unpack('>H', data[pos:pos + 2])[0]; pos += 2
            for _a in range(ac):
                pos += 2
                ln = struct.unpack('>I', data[pos:pos + 4])[0]; pos += 4 + ln
    return cn(ti), cn(si), [cn(x) for x in ifs if x is not None], members


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--intermediary', required=True)
    ap.add_argument('--client', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    cls, mem = parse_tiny(a.intermediary)

    def rdesc(d):
        out, i = [], 0
        while i < len(d):
            if d[i] == 'L':
                j = d.index(';', i)
                nm = d[i + 1:j]
                out.append('L' + cls.get(nm, nm) + ';')
                i = j + 1
            else:
                out.append(d[i]); i += 1
        return ''.join(out)

    z = zipfile.ZipFile(a.client)
    classes, supers, methods, fields = set(), {}, set(), set()
    for e in z.namelist():
        if not e.endswith('.class') or e.startswith('META-INF/'): continue
        try:
            tn, sn, ifs, members = parse_class(z.read(e))
        except Exception:
            continue
        if not tn: continue
        # 注意: 混淆版 jar 里的类名是 'a'/'b' 这类短名, 必须先查映射再判断包名,
        # 否则会把整个 net/minecraft 过滤掉(只剩十几个非混淆的辅助类)。
        io = cls.get(tn, tn)
        if not (io.startswith('net/minecraft/') or io.startswith('com/mojang/')): continue
        classes.add(io)
        supers[io] = (cls.get(sn, sn) if sn else None,
                      [cls.get(x, x) for x in ifs])
        for (kind, nm, d, flags) in members:
            io2 = cls.get(tn, tn)
            if kind == 'm':
                ni = mem.get((tn, nm, d), nm)
                methods.add((io2, ni, rdesc(d)))
            else:
                ni = mem.get((tn, nm, d), nm)
                fields.add((io2, ni, rdesc(d)))

    with open(a.out, 'w') as f:
        f.write('# mcport decl table (intermediary namespace) %s + %s\n'
                % (a.intermediary.split('/')[-1], a.client.split('/')[-1]))
        for c in sorted(classes): f.write('C\t%s\n' % c)
        for c, (s, ifs) in sorted(supers.items()):
            f.write('S\t%s\t%s\t%s\n' % (c, s or '', ','.join(ifs)))
        for t in sorted(methods): f.write('M\t%s\t%s\t%s\n' % t)
        for t in sorted(fields): f.write('F\t%s\t%s\t%s\n' % t)
    print('%s: %d classes, %d supers, %d methods, %d fields'
          % (a.out, len(classes), len(supers), len(methods), len(fields)))


if __name__ == '__main__':
    main()
