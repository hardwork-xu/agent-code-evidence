#!/usr/bin/env python3
"""Run the frozen catalog study / 运行冻结目录实验；不执行上游源码。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from benchmarks.catalog_reuse.suite import rss_worker, run_study  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True,
                        help='ready-manifest.json from source preparation / 已准备源码清单')
    parser.add_argument('--protocol', type=Path, required=True,
                        help='frozen protocol JSON / 已冻结协议 JSON')
    parser.add_argument('--output', type=Path,
                        help='new exclusive result directory / 新的独占结果目录')
    parser.add_argument('--repeats', type=int, help='must equal frozen count / 必须等于冻结次数')
    parser.add_argument('--memory-repeats', type=int,
                        help='must equal frozen memory count / 必须等于冻结内存次数')
    parser.add_argument('--rss-worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--repository', help=argparse.SUPPRESS)
    parser.add_argument('--method', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.rss_worker:
        if not args.repository or not args.method or args.output is not None:
            parser.error('RSS worker requires repository and method only / 内存子进程参数无效')
        print(json.dumps(rss_worker(args.inputs, args.protocol, args.repository, args.method),
                         sort_keys=True, ensure_ascii=False))
    else:
        if args.output is None:
            parser.error('--output is required / 必须提供结果目录')
        run_study(args.inputs, args.protocol, args.output, repetitions=args.repeats,
                  memory_repetitions=args.memory_repeats,
                  progress=lambda row: print(json.dumps(row, sort_keys=True), flush=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'Study failed; retained rows are not successful research results. / '
              f'实验失败；已保留记录不能称为成功研究结果。 '
              f'{type(error).__name__}', file=sys.stderr)
        raise SystemExit(2) from error
