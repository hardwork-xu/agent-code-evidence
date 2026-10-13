# Maintenance conventions

- Preserve historical raw results, source pins and failed runs. Never overwrite a
  run to improve its appearance; record amendments before new primary runs.
- Keep source/import identity, resolver replay equality, semantic behavior and
  coding-task success as separate claims. Unknown frontiers must remain visible.
- Test public interfaces, counterexamples, failure paths and result integrity.
  Share indexing work fairly between benchmark methods; avoid parallel benchmarks.
- Retain exact third-party license bytes and run `scripts/check_attribution.py`.
  Known noncontiguous historical excerpts are explicit limitations, not exact spans.
- Maintain corresponding English/Chinese research docs and identical measurements.
- Keep `research/claims.json` and generated status pages aligned with retained
  evidence; run `scripts/check_research_claims.py`. A passing record check is
  not scientific maturity, novelty or independent validation.
- Keep local paths, account details, private learning notes and raw terminal logs
  outside Git. Run `scripts/check_publication.py` before public delivery.

维护约定：保留历史和失败；区分静态证据、回放一致性、语义与任务效果；
公平比较基线；准确保留第三方归属；中英文数字一致；私人记录始终放在仓库外。
