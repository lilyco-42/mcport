#!/usr/bin/env python3
"""report.py - 把 LinkCheck 的 JSON 报告转成可执行的迁移工单(markdown).

用法: python3 tools/report.py report.json > MIGRATION.md

为什么需要这一步:
  LinkCheck 只回答"能不能自动修"; 真正做移植的人需要的是
  "哪些必须我手动写适配、每条对应哪个类/哪个方法"。
  这一步把 SIGCHG/MISSING 按 owner 类聚合并排出优先级。
"""
import json, sys, collections

d = json.load(open(sys.argv[1]))
det = d['details']
tot = d['total']
judged = tot - len(det.get('EXTERNAL', []))

print('# 移植工单: %s' % d['mod'])
print('')
print('| 判定 | 数量 | 占比 | 含义 |')
print('|---|---|---|---|')
for k, mean in (('RESOLVE', '零改动即可在新版本运行'),
                ('RENAME', '可由 McPort 自动重映射'),
                ('SIGCHG', '需生成桥接 shim'),
                ('MISSING', '需人工重写实现'),
                ('EXTERNAL', 'client jar 不含 / 本预言机不覆盖, 需另行验证')):
    n = len(det.get(k, []))
    print('| %s | %d | %.1f%% | %s |' % (k, n, 100.0 * n / max(1, judged), mean))
print('')
print('**自动修复上限 %.1f%% / 零改动存活 %.1f%%** (分母 %d, 已排除 EXTERNAL)'
      % (100.0 * (d['resolve'] + d['rename']) / max(1, judged),
         100.0 * d['resolve'] / max(1, judged), judged))
print('')

for bucket, title in (('SIGCHG', '需要桥接 shim(签名变了, 语义通常相近)'),
                      ('MISSING', '需要重写实现(类或成员消失)')):
    items = det.get(bucket, [])
    if not items: continue
    print('## %s —— %d 条' % (title, len(items)))
    print('')
    by = collections.OrderedDict()
    for it in items:
        owner = it.split('(')[0].rsplit('.', 1)[0]
        by.setdefault(owner, []).append(it)
    for owner, lst in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print('### `%s` (%d)' % (owner, len(lst)))
        for x in lst:
            print('- `%s`' % x)
        print('')
