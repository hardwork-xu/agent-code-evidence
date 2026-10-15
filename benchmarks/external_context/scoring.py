"""Edit-localization proxy metrics, never task-relevance or repair-success labels.

补丁编辑位置只是代理标签，不证明必要上下文、语义充分性或修复成功。
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath


def safe_path(path: str) -> str:
    """Accept repository-relative POSIX paths / 仅接受仓库内相对路径。"""
    p = PurePosixPath(path)
    if not path or p.is_absolute() or '..' in p.parts or '\\' in path or '\x00' in path:
        raise ValueError('unsafe source path')
    if str(p) != path or path == '.':
        raise ValueError('noncanonical source path')
    return path


def edit_targets(patch: str) -> dict:
    """Parse removed base lines; additions contribute file targets only.

    Deleted lines have exact coordinates in base_commit. Pure insertions have no
    removed-line target and remain explicitly unscorable for line metrics.
    删除/替换行采用旧版本真实行号；纯插入不伪造行标签，单独记录。
    """
    if not isinstance(patch, str):
        raise ValueError('patch must be text')
    removed: set[tuple[str, int]] = set()
    files: set[str] = set()
    old_path = None
    new_path = None
    old_header = new_header = False
    old_left = new_left = old_line = 0
    hunks = 0
    for raw in patch.split('\n'):
        # Header-like strings inside a hunk are still ordinary changed lines.
        if old_left or new_left:
            if raw == '\\ No newline at end of file':
                continue
            if raw.startswith(' '):
                old_left -= 1
                new_left -= 1
                old_line += 1
            elif raw.startswith('-'):
                if old_path is not None:
                    files.add(old_path)
                    removed.add((old_path, old_line))
                old_left -= 1
                old_line += 1
            elif raw.startswith('+'):
                if old_path is not None:
                    files.add(old_path)
                new_left -= 1
            else:
                raise ValueError('invalid or truncated unified diff hunk')
            if old_left < 0 or new_left < 0:
                raise ValueError('inconsistent unified diff hunk counts')
            continue
        if raw.startswith('diff --git '):
            old_path = new_path = None
            old_header = new_header = False
        elif raw.startswith('--- '):
            old_header, new_header = True, False
            name = raw[4:].split('\t', 1)[0]
            if name == '/dev/null':
                old_path = None
            elif name.startswith('a/'):
                old_path = safe_path(name[2:])
            else:
                raise ValueError('expected git diff old path')
        elif raw.startswith('+++ '):
            if not old_header or new_header:
                raise ValueError('missing or duplicate old/new file header')
            name = raw[4:].split('\t', 1)[0]
            if name == '/dev/null':
                new_path = None
            elif name.startswith('b/'):
                new_path = safe_path(name[2:])
            else:
                raise ValueError('expected git diff new path')
            new_header = True
        elif raw.startswith('@@'):
            if not old_header or not new_header:
                raise ValueError('hunk lacks old/new file headers')
            match = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)$', raw)
            if not match:
                raise ValueError('invalid unified diff header')
            old_line = int(match[1])
            old_left = int(match[2] if match[2] is not None else 1)
            new_left = int(match[4] if match[4] is not None else 1)
            if (old_path is None and old_left) or (new_path is None and new_left):
                raise ValueError('null file has nonempty hunk side')
            if old_left == new_left == 0:
                raise ValueError('empty hunk')
            if new_left and int(match[3]) < 1:
                raise ValueError('invalid new line')
            if old_left and old_line < 1:
                raise ValueError('invalid base line')
            hunks += 1
        elif raw.startswith(('+', '-')):
            raise ValueError('unexpected change line outside hunk')
    if old_left or new_left or not hunks:
        raise ValueError('incomplete or absent unified diff hunks')
    return {'removed_lines': removed, 'edited_base_files': files, 'hunks': hunks}


def overlap(predicted: set, target: set) -> dict:
    """Set-based counts with undefined labels explicit / 去重计数，空标签显式缺失。"""
    tp = len(predicted & target)
    if not target:
        return {'predicted': len(predicted), 'target': 0, 'intersection': 0,
                'precision': None, 'recall': None, 'f1': None, 'status': 'no_target'}
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(target)
    return {'predicted': len(predicted), 'target': len(target), 'intersection': tp,
            'precision': precision, 'recall': recall,
            'f1': 2 * tp / (len(predicted) + len(target)), 'status': 'scored'}


def score_prediction(predicted: set[tuple[str, int]], patch: str,
                     source_lengths: dict[str, int]) -> dict:
    """Keep out-of-corpus targets in denominator / 语料外目标保留在分母中。"""
    for path, number in predicted:
        safe_path(path)
        if type(number) is not int or not 1 <= number <= source_lengths.get(path, 0):
            raise ValueError('prediction is outside verified source')
    target = edit_targets(patch)
    # The adapter indexes Python only; report non-Python changes separately.
    py_lines = {(p, n) for p, n in target['removed_lines'] if p.endswith('.py')}
    py_files = {p for p in target['edited_base_files'] if p.endswith('.py')}
    absent = {(p, n) for p, n in py_lines if not 1 <= n <= source_lengths.get(p, 0)}
    return {'line': overlap(predicted, py_lines),
            'file': overlap({p for p, _ in predicted}, py_files),
            'out_of_corpus_target_lines': len(absent),
            'non_python_removed_lines': len(target['removed_lines'] - py_lines),
            'non_python_edited_files': len(target['edited_base_files'] - py_files),
            'target_kind': 'removed-base-lines-not-necessary-context'}
