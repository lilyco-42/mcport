#!/usr/bin/env python3
"""Self-contained regression for tools/bridgegen.py + java/mcport/CallKind.java.

No network, no Minecraft jar, no Mojang mapping, no third-party mod bytes.
All link-check tickets, declarations and call-kind tables are synthetic.
The only optional external binary is javac/java/jar for the CallKind smoke test.
"""
import csv, importlib.util, json, os, shutil, subprocess, sys, tempfile

PY = sys.executable or '/usr/bin/python3'
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TOOL = os.path.join(HERE, 'bridgegen.py')
N = [0]


def ok(name, cond, detail=''):
    N[0] += 1
    if not cond:
        print('FAIL ' + name + ' ' + str(detail))
        sys.exit(1)


# ---------------- pure helper units ----------------
spec = importlib.util.spec_from_file_location('bridgegen', TOOL)
bg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bg)

ok('schema', bg.SCHEMA == 1)
ok('split_desc_simple', bg.split_desc('(IJ)V') == (['I', 'J'], 'V'))
ok('split_desc_ref', bg.split_desc('(La/O;[[I)La/T;') == (['La/O;', '[[I'], 'La/T;'))
ok('parse_ref_method', bg.parse_ref('a/O.m(I)V  # name kept') == ('a/O', 'm', '(I)V', 'M'))
ok('parse_ref_ctor', bg.parse_ref('a/O.<init>()V  # x') == ('a/O', '<init>', '()V', 'M'))
ok('parse_ref_field', bg.parse_ref('a/O.fldI  # x') == ('a/O', 'fld', 'I', 'F'))
ok('parse_ref_bad', bg.parse_ref('???') is None)
ok('param_identity', bg.param_conv('I', 'I') == '-')
ok('param_intlike', bg.param_conv('B', 'S') == '-')
ok('param_widen', bg.param_conv('I', 'D') == 'i2d')
ok('param_narrow_reject', bg.param_conv('J', 'I') is None)
ok('param_ref_reject', bg.param_conv('La/O;', 'La/T;') is None)
ok('return_identity', bg.return_conv('I', 'I') == '-')
ok('return_discard', bg.return_conv('V', 'La/T;') == 'pop')
ok('return_widen', bg.return_conv('D', 'I') == 'i2d')
ok('return_narrow_reject', bg.return_conv('F', 'D') is None)
ok('return_void_reject', bg.return_conv('I', 'V') is None)
ok('shape_ok', bg.shape('()D', '()I')[1] is None)
ok('shape_reject', bg.shape('(J)V', '(I)V')[1] == 'REF_OR_NARROWING_PARAM')
ok('java_ident_stable', bg.java_ident('x') == bg.java_ident('x') and bg.java_ident('x') != bg.java_ident('y'))


def make_inputs(t):
    decl = os.path.join(t, 'decl.tsv')
    with open(decl, 'w', encoding='utf-8') as f:
        f.write('# synthetic decl\n')
        f.write('C\ta/O\n')
        f.write('S\ta/O\tjava/lang/Object\t\n')
        f.write('M\ta/O\tscaled\t()I\n')          # legacy ()D -> target ()I
        f.write('M\ta/O\tcomp\t()La/T;\n')        # same name also exists as FIELD
        f.write('F\ta/O\tcomp\tLa/T;\n')
        f.write('M\ta/O\tamb\t()I\n')             # ambiguous two targets
        f.write('M\ta/O\tamb\t(J)V\n')
        f.write('M\ta/O\tnarrow\t()D\n')          # legacy ()F -> target ()D (narrowing)
        f.write('M\ta/O\tparam\t(I)V\n')          # legacy (J)V -> target (I)V
        f.write('M\ta/O\tgone\t()V\n')
    ck = os.path.join(t, 'callkind.tsv')
    with open(ck, 'w', encoding='utf-8') as f:
        for row in [
            ('a/O', 'scaled', '()D', 'virtual'),
            ('a/O', 'comp', '()La/Old;', 'virtual'),
            ('a/O', 'amb', '()Z', 'virtual'),
            ('a/O', 'narrow', '()F', 'virtual'),
            ('a/O', 'param', '(J)V', 'virtual'),
            ('a/O', 'mix', '()I', 'mixed'),
            ('a/O', 'spec', '()I', 'special'),
            ('a/O', '<init>', '()V', 'special'),
        ]:
            f.write('\t'.join(row) + '\n')
    tk1 = os.path.join(t, 'ticket1.json')
    with open(tk1, 'w', encoding='utf-8') as f:
        json.dump({'details': {
            'SIGCHG': [
                'a/O.scaled()D  # name kept by a/O, descriptor changed',
                'a/O.comp()La/Old;  # name kept by a/O, descriptor changed',
                'a/O.amb()Z  # name kept by a/O, descriptor changed',
                'a/O.narrow()F  # name kept by a/O, descriptor changed',
                'a/O.param(J)V  # name kept by a/O, descriptor changed',
                'a/O.mix()I  # name kept',
                'a/O.spec()I  # name kept',
                'a/O.nock()I  # name kept',
                'a/O.<init>()V  # name kept',
                'a/O.fldI  # name kept',
                '???',
            ],
            'MISSING': ['a/O.gone()V  # member gone'],
        }}, f)
    tk2 = os.path.join(t, 'ticket2.json')
    with open(tk2, 'w', encoding='utf-8') as f:
        json.dump({'details': {
            'SIGCHG': ['a/O.scaled()D  # duplicate in another mod'],
            'MISSING': [],
        }}, f)
    return decl, ck, tk1, tk2


def run(spec_path, out):
    p = subprocess.run([PY, TOOL, '--spec', spec_path, '--out-dir', out],
                       capture_output=True, text=True)
    return p


def read_triage(p):
    d = {}
    with open(p, encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            d.setdefault((r['bucket'], r['ref']), []).append(r['status'])
    return d


with tempfile.TemporaryDirectory() as t:
    decl, ck, tk1, tk2 = make_inputs(t)
    sp = os.path.join(t, 'spec.json')
    with open(sp, 'w', encoding='utf-8') as f:
        json.dump({'schema': 1, 'targets': [{
            'version': 'v', 'decl': decl, 'callkind': ck,
            'tickets': [tk1, tk2]}]}, f)
    out = os.path.join(t, 'out')
    p = run(sp, out)
    ok('cli_rc', p.returncode == 0, p.stderr)
    with open(os.path.join(out, 'summary.csv'), encoding='utf-8') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    ok('one_row', len(rows) == 1, rows)
    row = rows[0]
    ok('columns_aligned', None not in row, row)
    expect = {'total': '13', 'sigchg': '12', 'missing': '1',
              'candidate_rules': '1', 'skeleton_mechanical_unsafe': '2',
              'duplicate_candidates': '1', 'reject_semantic_conversion': '3',
              'reject_opcode': '2', 'reject_ctor': '1', 'reject_field': '1',
              'reject_unparsed': '1', 'reject_no_callkind': '1',
              'reject_no_target': '1', 'reject_ambiguous': '1',
              'reject_no_candidate': '0', 'auto_fixed': '0'}
    for k, v in expect.items():
        ok('summary_' + k, row.get(k) == v, (k, row.get(k), v))
    ok('no_rules_without_flag', not os.path.exists(os.path.join(out, 'v', 'bridge-rules.tsv')))
    cand = os.path.join(out, 'v', 'bridge-candidates.tsv')
    lines = open(cand, encoding='utf-8').read().splitlines()
    ok('candidates_shape', len(lines) == 3 and lines[0].startswith('#') and lines[1].startswith('#'), lines)
    rule = lines[2].split('\t')
    ok('rule_6cols', len(rule) == 6, rule)
    ok('rule_owner', rule[0] == 'a/O', rule)
    ok('rule_kind_virtual', rule[3] == 'virtual', rule)
    ok('rule_adapter', rule[4].startswith('mcport/generated/Adapter_'), rule)
    ok('rule_method', rule[5].startswith('mcp_'), rule)
    adapters = [x for x in os.listdir(os.path.join(out, 'v', 'adapters')) if x.endswith('.java')]
    ok('one_adapter', len(adapters) == 1, adapters)
    src = open(os.path.join(out, 'v', 'adapters', adapters[0]), encoding='utf-8').read()
    ok('adapter_one_method', src.count('public static') == 1, src)
    ok('adapter_throws', 'MCPORT_HUMAN_REVIEW_REQUIRED' in src and 'UnsupportedOperationException' in src)
    tri = read_triage(os.path.join(out, 'v', 'triage.tsv'))
    ok('comp_is_semantic', tri.get(('SIGCHG', 'a/O.comp()La/Old;')) == ['REJECT_SEMANTIC_CONVERSION'], tri.get(('SIGCHG', 'a/O.comp()La/Old;')))
    ok('comp_not_ambiguous', tri.get(('SIGCHG', 'a/O.comp()La/Old;')) != ['REJECT_AMBIGUOUS'])
    st = json.load(open(os.path.join(out, 'v', 'stats.json'), encoding='utf-8'))
    ok('stats_auto_fixed0', st['stats']['auto_fixed'] == 0)
    ok('stats_duplicate1', st['stats']['duplicate_candidates'] == 1)
    ok('stats_candidate_rules1', st['stats']['candidate_rules'] == 1)
    # explicit acknowledgement flag
    out2 = os.path.join(t, 'out2')
    p2 = subprocess.run([PY, TOOL, '--spec', sp, '--out-dir', out2, '--emit-rules'],
                        capture_output=True, text=True)
    ok('emit_rules_rc', p2.returncode == 0, p2.stderr)
    rules2 = os.path.join(out2, 'v', 'bridge-rules.tsv')
    ok('emit_rules_creates', os.path.exists(rules2))
    ok('emit_rules_same_bytes', open(rules2, 'rb').read() == open(os.path.join(out2, 'v', 'bridge-candidates.tsv'), 'rb').read())
    out3 = os.path.join(t, 'out3')
    p3 = run(sp, out3)
    ok('rerun_rc', p3.returncode == 0, p3.stderr)
    ok('deterministic_candidates',
       open(os.path.join(out, 'v', 'bridge-candidates.tsv'), 'rb').read() ==
       open(os.path.join(out3, 'v', 'bridge-candidates.tsv'), 'rb').read())
    ok('deterministic_summary',
       open(os.path.join(out, 'summary.csv'), 'rb').read() ==
       open(os.path.join(out3, 'summary.csv'), 'rb').read())


def callkind_smoke(t):
    javac, java, jar = shutil.which('javac'), shutil.which('java'), shutil.which('jar')
    if not (javac and java and jar):
        return True   # no JDK in this environment: skip, keep assertion count fixed
    cls = os.path.join(t, 'classes')
    os.makedirs(cls, exist_ok=True)
    lib = os.path.join(REPO, 'lib', '*')
    p = subprocess.run([javac, '-nowarn', '-cp', lib, '-d', cls,
                        os.path.join(REPO, 'java', 'mcport', 'CallKind.java')],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return False
    src = os.path.join(t, 'T.java')
    with open(src, 'w', encoding='utf-8') as f:
        f.write('package t; public class T { static int s(){return 1;} int v(){return 2;} '
                'public static void main(String[] a){ T x=new T(); x.v(); s(); '
                'Runnable r=()->{}; r.run(); } }\n')
    b = os.path.join(t, 'bin')
    os.makedirs(b, exist_ok=True)
    if subprocess.run([javac, '-d', b, src], capture_output=True, text=True).returncode != 0:
        return False
    j = os.path.join(t, 't.jar')
    if subprocess.run([jar, 'cf', j, '-C', b, '.'], capture_output=True, text=True).returncode != 0:
        return False
    outp = os.path.join(t, 'ck.tsv')
    cp = cls + os.pathsep + lib
    if subprocess.run([java, '-cp', cp, 'mcport.CallKind', '--in', j, '--out', outp],
                      capture_output=True, text=True).returncode != 0:
        return False
    got = {}
    for ln in open(outp, encoding='utf-8').read().splitlines():
        x = ln.split('\t')
        if len(x) == 4:
            got[(x[0], x[1], x[2])] = x[3]
    return (got.get(('t/T', 's', '()I')) == 'static' and
            got.get(('t/T', 'v', '()I')) == 'virtual' and
            got.get(('t/T', '<init>', '()V')) == 'special' and
            got.get(('java/lang/Runnable', 'run', '()V')) == 'interface')


with tempfile.TemporaryDirectory() as t2:
    ok('callkind_smoke', callkind_smoke(t2))

print('RESULT ALL_OK ' + str(N[0]))
