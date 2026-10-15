"""Render/check the sealed post-hoc sensitivity / 生成并核对封存的事后敏感性分析。

Recomputes scalar arithmetic from retained inputs; never executes a SUT or retrieval.
只重算保留标量，不运行上游程序、检索或模型。
"""
import argparse
import hashlib
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'benchmarks/known_task_execution/secondary/known39-20261015'
PINS = {
    'result.json': 'f9566e32e27decd3a0970a04ffe0fad04be7369e0b33cdf2e48468bf2eadbf3c',
    'protocol.json': '6d978f180ad4386416ac3cb04984e66484cd2691fa35339fa61eecd8c9c2cc56',
    'eligibility.json': 'a7e56df07d366afa8959a1fa2dead1ff3d5565ba26fc361b0f162259dae400b4',
    'analysis-seal.json': 'c86bd4a7b75e23543dfd9bbe353e26532bf08a7c1f101ec9fde082a2336ded7e',
    'analyze_sensitivity.py': 'b660d3b4aa34d9cb30905d1458a05a195ca3503970c41a6db186f555d57f25e9',
}
VIEWS = ('all39_reference_recomputed', 'latest_finite_qualified_secondary')


def load_frozen_analysis(path=None):
    """Execute the same SHA-verified own bytes / 只编译同一份已核验自主源码字节。"""
    path = Path(path) if path is not None else Path(__file__).with_name('analyze_sensitivity.py')
    with path.open('rb') as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != PINS['analyze_sensitivity.py']:
        raise ValueError('analysis source SHA256 mismatch / 分析源码摘要不同')
    module = types.ModuleType('_known39_verified_scalar_analysis')
    module.__file__ = str(path)
    # dataclasses resolves postponed annotations via sys.modules during class creation.
    # dataclasses创建类时会通过sys.modules解析延迟注解；执行后恢复原注册。
    previous = sys.modules.get(module.__name__)
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(path), 'exec'), module.__dict__)
    finally:
        if previous is None:
            sys.modules.pop(module.__name__, None)
        else:
            sys.modules[module.__name__] = previous
    return module


def verify(root=ROOT, data=DATA):
    """Verify exact inputs and recompute stored scalars / 校验精确输入并重算已存标量。"""
    analysis = load_frozen_analysis()
    inputs = {name: analysis.read_json(Path(data) / name, sha)
              for name, sha in PINS.items() if name.endswith('.json')}
    protocol, ledger, seal, result = (inputs[k] for k in
                                    ('protocol.json', 'eligibility.json', 'analysis-seal.json', 'result.json'))
    for field, name in (('protocol_sha256', 'protocol.json'),
                        ('eligibility_ledger_sha256', 'eligibility.json'),
                        ('analysis_program_sha256', 'analyze_sensitivity.py')):
        if seal[field] != PINS[name]:
            raise ValueError('sealed input differs / 封存输入不同')
    if seal['action'] != 'authorize_one_final_secondary_calculation' or seal['allow_real_inputs'] is not True:
        raise ValueError('invalid scientific input seal / 无效科学输入封存')
    bound = analysis.read_bindings(root, protocol['original_primary_immutable']['source_bindings'])
    primary = analysis.parse_verified_json(bound['protocol.json'])
    identities = {r['instance_id']: r for r in primary['selection']['tasks']}
    if len(identities) != 39 or tuple(primary['methods']) != analysis.METHODS or tuple(primary['budgets']) != analysis.BUDGETS:
        raise ValueError('original experiment differs / 原实验不同')
    tasks = analysis.validate_scores(analysis.parse_verified_json(bound['scores.json']), identities)
    selected, rows = analysis.validate_eligibility(ledger, identities, bound['protocol.json'].sha256,
                                                  bound['scores.json'].sha256, (87, 5842))
    expected = analysis.summarize(tasks, selected, rows)
    actual = {k: v for k, v in result.items() if k not in ('provenance', 'run_id')}
    if actual != expected:
        raise ValueError('saved arithmetic differs / 已存算术结果不同')
    for field, name in (('analysis_program_sha256', 'analyze_sensitivity.py'),
                        ('protocol_sha256', 'protocol.json'),
                        ('final_eligibility_sha256', 'eligibility.json'),
                        ('approval_sha256', 'analysis-seal.json')):
        if result['provenance'][field] != PINS[name]:
            raise ValueError('result provenance differs / 结果来源不同')
    return result


def percent(value):
    """An absolute fraction as percent / 绝对比例转为百分数。"""
    return 'undefined' if value is None else f'{100 * value:.6f}%'


def points(value):
    """A difference in percentage points, never relative percent / 差值使用百分点。"""
    return 'undefined' if value is None else f'{100 * value:+.6f}'


def render(result, language):
    """Both languages share every value and input pin / 双语共享全部数字和输入摘要。"""
    zh = language == 'zh'
    def tr(en, cn):
        return cn if zh else en
    lines = [
        '# ' + tr('Post-hoc execution-qualified sensitivity', '事后执行资格敏感性分析'), '',
        tr('This is a descriptive reanalysis of the already observed pilot. No new SUT, retrieval, model, '
           'holdout or generated repair was run. The original 39-task primary results and failed advancement gates remain unchanged.',
           '这是对已观测pilot的描述性重算，没有新运行上游测试、检索、模型、留出集或生成修复。原39任务主结果和未通过的推进门槛保持不变。'), '',
        f"Run ID: `{result['run_id']}`. UTC: `{result['provenance']['recorded_utc']}`.", '',
        tr('The secondary protocol was frozen before this subset calculation, after the original scores and '
           'execution outcomes were known. It is not a pre-data preregistration. The input seal binds author-written '
           'scientific inputs; it is not a signature, external approval or independent authentication.',
           '次级协议在本次子集计算前冻结，但原始分数和执行结果已经可见；它不是数据观察前预注册。输入封存绑定自主编写的科学输入，不是签名、外部审批或独立认证。'), '',
        tr('Eligibility uses the latest approved started condition, including closed failures and partial attempts; '
           'it never selects the best environment. There are 51 complete conditions and one closed partial attempt. '
           'All 87 F2P / 5842 P2P labels remain in the execution ledger; labels and retries are not independent samples.',
           '资格采用最新的已批准且已启动条件，包含已闭合失败和不完整尝试，不挑选最好环境。共51完整条件与1个闭合不完整条件。执行清单保留全部87 F2P / 5842 P2P标签；标签及重试不是独立样本。'), '',
        tr('| Repository | Original tasks | Finite-qualified | Qualified line-targetable | Qualified undefined | Original prediction failures |',
           '| 仓库 | 原任务数 | 有限合格 | 合格且有行目标 | 合格但行指标未知 | 原始预测失败数 |'),
        '|---|---:|---:|---:|---:|---:|',
    ]
    for row in result['per_repository_denominators']:
        lines.append(f"| `{row['repo']}` | {row['original_tasks']} | {row['finite_qualified_tasks']} | "
                     f"{row['qualified_line_targetable_tasks']} | {row['qualified_no_target_tasks']} | "
                     f"{row['prediction_failure_tasks_retained']} |")
    lines += ['', tr('The subset contains 30 tasks: 24 line-targetable and six undefined, versus 32/7 in the original 39. '
                    'The last column refers to all original tasks, not subset failures. Original source-cap failures '
                    'retain conservative zero scores; no predictions were regenerated or rescored. Undefined labels stay null.',
                    '子集共30项：24项有行目标、6项未知；原39项对应32/7。末列统计原始全部任务的预测失败，不是子集失败数。原源码上限失败保留保守零分，没有重新生成预测或修改评分；未知标签仍为null。'), '',
              '## ' + tr('16,000-byte focus', '16000字节重点结果'), '',
              tr('Differences are graph expansion minus baseline in percentage points (pp), not relative percent.',
                 '差值均为图扩展减基线，单位为百分点（pp），不是相对百分比。'), '',
              tr('| Population | Baseline | F1 difference (pp) | Recall difference (pp) | F1 repo wins/ties/losses/undefined |',
                 '| 样本 | 基线 | F1差值（pp） | 召回差值（pp） | F1仓库胜/平/负/未知 |'),
              '|---|---|---:|---:|---|']
    for name, label in zip(VIEWS, ('all39', 'qualified30')):
        for row in result[name]['focus_16000']:
            counts = row['f1_repo_sign_counts']
            signs = '/'.join(str(counts.get(k, 0)) for k in ('positive', 'tie', 'negative', 'undefined'))
            lines.append(f"| {label} | `{row['baseline']}` | {points(row['f1_difference'])} | "
                         f"{points(row['recall_difference'])} | {signs} |")
    lines += ['', tr('F1 ordering against declaration BM25 flips on the selected subset; this positive observation '
                    'is retained. Recall remains lower than both baselines, by 13.650599 and 14.300790 pp respectively. '
                    'The selection changes within-repository task composition. All six repositories still contribute, '
                    'so the common-contributing-repository diagnostic equals the original all39 result.',
                    '对子集，F1相对声明BM25的排序翻转；保留这一正面观测。召回仍低于两种基线，分别低13.650599和14.300790个百分点。筛选改变了仓库内任务组成；六个仓库仍全部贡献，因此共同贡献仓库诊断等于原all39结果。'), '',
              tr('The joint strict-negative F1-and-recall flag is false in both populations: the original graph F1 '
                 'was already above window BM25. This flag is not evidence of overall superiority. No p-values or '
                 'confidence intervals treating nodes/retries as independent samples are reported.',
                 '两组的“F1与召回相对两基线均严格为负”标志都为false：原图F1本来已高于窗口BM25。此标志不证明全面优越。不报告将节点或重试当独立样本的p值或置信区间。'), '',
              '## ' + tr('All methods and budgets', '全部方法和预算'), '',
              tr('Task means are computed within each repository, then defined repository means receive equal weight. '
                 'The exact ratios, every per-repository comparison, membership and exclusions are retained in result.json.',
                 '先在仓库内按任务求均值，再对有定义的仓库均值等权汇总。精确有理数差值、逐仓库对照、成员和排除理由均保留在result.json。'), '',
              tr('| Method | Byte budget | All39 F1 | All39 recall | Qualified30 F1 | Qualified30 recall |',
                 '| 方法 | 字节预算 | All39 F1 | All39召回 | Qualified30 F1 | Qualified30召回 |'),
              '|---|---:|---:|---:|---:|---:|']
    subset = {(r['method'], r['budget']): r['repo_macro'] for r in result[VIEWS[1]]['method_budget_cells']}
    for row in result[VIEWS[0]]['method_budget_cells']:
        all_metrics, chosen = row['repo_macro'], subset[row['method'], row['budget']]
        lines.append(f"| `{row['method']}` | {row['budget']} | {percent(all_metrics['f1'])} | "
                     f"{percent(all_metrics['recall'])} | {percent(chosen['f1'])} | {percent(chosen['recall'])} |")
    lines += ['', '## ' + tr('Reproduce and check', '复算与核对'), '',
              tr('From a checkout of this branch, Python 3.11+ is sufficient; no third-party package, dataset '
                 'download, model or API key is needed for scalar reanalysis. The saved result includes the original '
                 'measurement timestamp, platform and analysis duration. A replay has different provenance; compare '
                 'scientific fields, not wall-clock bytes or execution speed.',
                 '在本分支检出目录中使用Python 3.11+；标量重算无需第三方包、数据下载、模型或密钥。已存结果含原计算时间、平台及分析耗时；复算来源会变化，应比较科学字段，不比较墙钟字节或将分析耗时当性能结果。'), '',
              '```sh', 'python -m benchmarks.known_task_execution.secondary_report --check',
              'WORK="$(mktemp -d)"', 'DATA=benchmarks/known_task_execution/secondary/known39-20261015',
              'python -m benchmarks.known_task_execution.analyze_sensitivity \\',
              '  --protocol "$DATA/protocol.json" \\',
              f"  --protocol-sha256 {PINS['protocol.json']} \\",
              '  --pilot-repository-root . --eligibility-ledger "$DATA/eligibility.json" \\',
              f"  --eligibility-sha256 {PINS['eligibility.json']} \\",
              '  --approval "$DATA/analysis-seal.json" \\',
              f"  --approval-sha256 {PINS['analysis-seal.json']} \\",
              '  --run-id known39-secondary-replay --output "$WORK/result.json"', '```', '',
              tr('The report checker verifies the published SHA pins, reloads the exact verified original inputs, '
                 'and recomputes the scalar result using the frozen analysis program. This detects inconsistency '
                 'with this artifact; it is not independent replication of private upstream executions.',
                 '报告检查器核验公开SHA摘要、解析同一份已校验输入，并用冻结分析程序重算标量结果。它检查此制品的一致性，不是私有上游执行的独立复验。'), '',
              '| File | SHA256 |', '|---|---|']
    lines += [f'| `{name}` | `{sha}` |' for name, sha in PINS.items()]
    lines += ['', '## ' + tr('Research boundary and next gates', '研究边界与后续门槛'), '',
              tr('Local platform, available dependencies, original test strength and execution feasibility select '
                 'this subset. Known-data filtering is neither causal identification nor a new holdout. Reference '
                 'edit overlap is not necessary context, semantic correctness or coding-agent repair benefit. '
                 'The current evidence supports an auditable measurement artifact and a negative/mixed pilot, '
                 'not a mature positive research claim.',
                 '本地平台、可用依赖、原测试强度及可执行性共同筛选了子集。已知数据筛选不是因果识别或新留出验证。参考编辑重叠不等于必要上下文、语义正确或编程智能体修复收益。当前证据支持可审计测量制品及负面/混合pilot，不支持成熟正向研究结论。'), '',
              tr('Advancement requires a separately frozen unseen task set, fair strong retrieval and whole-corpus '
                 'invalidation/cost baselines, an executable semantic endpoint, and independent replay under declared '
                 'budgets. Those are uncompleted gates, not promised outcomes. No release or paper acceptance is implied.',
                 '继续推进需要单独冻结未见任务集、公平的强检索及全语料失效/成本基线、可执行语义终点和明确预算下独立复验。这些门槛尚未完成，不是承诺结果；不暗示正式发布或论文接收。'), '',
              '[Execution protocol / 执行协议](KNOWN_TASK_EXECUTION.md) · '
              '[Original pilot / 原pilot](EXTERNAL_PILOT_RESULTS.md)', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='check both saved documents / 核对双语文档')
    args = parser.parse_args()
    result = verify()
    for language in ('en', 'zh'):
        target = ROOT / 'docs' / language / 'KNOWN_TASK_SENSITIVITY.md'
        content = render(result, language)
        if args.check:
            if not target.exists() or target.read_text() != content:
                raise ValueError('sensitivity report differs / 敏感性报告不同')
        else:
            target.write_text(content)
    print('passed: sealed scalar arithmetic and bilingual reports / 封存标量与双语报告通过')


if __name__ == '__main__':
    main()
