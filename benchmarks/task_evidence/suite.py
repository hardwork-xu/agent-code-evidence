"""Source-integrity checks and witness scoring, separate from the static resolver."""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import tarfile


def physical_lines(source: str) -> list[str]:
    """Python line locations advance on CR/LF, not Unicode/form-feed separators."""
    pieces = re.split(r'(\r\n|\r|\n)', source)
    lines = [pieces[i] + pieces[i + 1] for i in range(0, len(pieces) - 1, 2)]
    if pieces[-1]:
        lines.append(pieces[-1])
    return lines


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, data: object) -> None:
    serialized = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n'
    pending = path.with_name('.' + path.name + '.tmp')
    try:
        pending.write_text(serialized)
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def safe_extract(archive: Path, destination: Path, expected_sha256: str) -> None:
    """Extract regular archive members only, after authenticating archive bytes."""
    if digest(archive.read_bytes()) != expected_sha256:
        raise ValueError('archive checksum mismatch')
    if destination.exists():
        raise ValueError('destination already exists')
    with tarfile.open(archive) as tf:
        members = tf.getmembers()
        prefixes = {Path(m.name).parts[0] for m in members if Path(m.name).parts}
        if len(prefixes) != 1:
            raise ValueError('archive must contain one top-level directory')
        for member in members:
            parts = Path(member.name).parts
            if (Path(member.name).is_absolute() or '..' in parts
                    or not (member.isfile() or member.isdir())):
                raise ValueError('unsafe archive member')
        destination.mkdir(parents=True)
        for member in members:
            relative = Path(*Path(member.name).parts[1:])
            if relative == Path('.'):
                continue
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(member) as stream:
                    target.write_bytes(stream.read())


def verified_texts(root: Path, pin: dict) -> dict[str, str]:
    source_root = root / 'src'
    if any(parent.is_symlink() for parent in [source_root, *source_root.parents]):
        raise ValueError('source symlinks are not allowed')
    members = list(source_root.rglob('*'))
    if any(p.is_symlink() for p in members):
        raise ValueError('source symlinks are not allowed')
    if any(p.name == '__pycache__' or p.suffix in {'.pyc', '.pyo', '.so', '.dylib', '.pyd'}
           for p in members):
        raise ValueError('unverified bytecode or native import artifact')
    paths = sorted(p for p in members if p.is_file() and p.suffix == '.py')
    raw = {p.relative_to(root).as_posix(): p.read_bytes() for p in paths}
    observed = {path: digest(data) for path, data in raw.items()}
    if observed != pin['source_files']:
        raise ValueError('upstream source catalog or file bytes changed')
    return {path: data.decode('utf-8') for path, data in raw.items()}


def declarations(path: str, source: str) -> list[dict]:
    """AST spans only: independent of graph's dependency analysis and resolver."""
    lines = physical_lines(source)
    result = []

    def visit(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbol = prefix + node.name
                first = min([node.lineno, *[d.lineno for d in node.decorator_list]])
                text = ''.join(lines[first - 1:node.end_lineno])
                row = dict(path=path, symbol=symbol,
                           kind='class' if isinstance(node, ast.ClassDef) else 'function',
                           start_line=first, end_line=node.end_lineno, text=text,
                           text_sha256=digest(text.encode()))
                row['id'] = digest(json.dumps(row, sort_keys=True).encode())
                result.append(row)
                visit(node.body, symbol + '.')
    visit(ast.parse(source).body)
    return result


def anchors_for(texts: dict[str, str], hints: list[dict]) -> tuple[list[dict], list[dict]]:
    result, missing = [], []
    for hint in hints:
        matches = [r for r in declarations(hint['path'], texts.get(hint['path'], ''))
                   if r['symbol'] == hint['symbol']]
        if not matches:
            missing.append(hint)
        # Preserve duplicate properties; ambiguity belongs to the static graph.
        result.extend(matches)
    return result, missing


def record_lines(records) -> set[tuple[str, int]]:
    return {(r['path'], line) for r in records
            for line in range(r['start_line'], r['end_line'] + 1)}


def stale_current_lines(records, current: dict[str, str]) -> tuple[set, dict]:
    """Credit old bytes only if the entire span has one exact current occurrence.

    This is textual source identity, not semantic equivalence or edit mapping.
    Duplicate matches abstain, even when one might be the right declaration.
    """
    covered = set()
    counts = Counter()
    for record in records:
        haystack = physical_lines(current.get(record['path'], ''))
        needle = physical_lines(record['text'])
        matches = [i for i in range(len(haystack) - len(needle) + 1)
                   if haystack[i:i + len(needle)] == needle] if needle else []
        if len(matches) == 1:
            counts['uniquely_unchanged_spans'] += 1
            covered.update((record['path'], i + 1)
                           for i in range(matches[0], matches[0] + len(needle)))
        elif matches:
            counts['ambiguous_spans'] += 1
        else:
            counts['changed_or_missing_spans'] += 1
    return covered, dict(counts)


def terms(text: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', re.sub(r'([a-z])([A-Z])', r'\1 \2', text).lower())


def lexical_lines(texts: dict[str, str], query: str, budget: int,
                  width: int = 20) -> set[tuple[str, int]]:
    """Independent BM25 over disjoint physical-line windows; no AST or labels."""
    docs = []
    for path, source in sorted(texts.items()):
        lines = physical_lines(source)
        for i in range(0, len(lines), width):
            docs.append((path, i + 1, len(lines[i:i + width]),
                         Counter(terms(path + ' ' + ''.join(lines[i:i + width])))))
    if not docs or not budget:
        return set()
    lengths = [sum(row[3].values()) for row in docs]
    average = sum(lengths) / len(lengths) or 1
    df = Counter(term for row in docs for term in row[3])
    ranked = []
    for row, length in zip(docs, lengths):
        score = 0.0
        for term in set(terms(query)):
            frequency = row[3][term]
            if frequency:
                idf = math.log(1 + (len(docs) - df[term] + .5) / (df[term] + .5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / average))
        # Zero-score windows fill a still-unused budget in stable path order.
        ranked.append((-score, row[0], row[1], row[2]))
    selected = set()
    for _, path, first, length in sorted(ranked):
        take = min(length, budget - len(selected))
        selected.update((path, line) for line in range(first, first + take))
        if len(selected) == budget:
            break
    return selected


def score(context: set, witness: set) -> dict:
    overlap = len(context & witness)
    return {'context_lines': len(context), 'witness_lines': len(witness),
            'covered_witness_lines': overlap,
            'recall': overlap / len(witness) if witness else None,
            # A density statistic, NOT gold-context precision: unexecuted context may matter.
            'execution_density': overlap / len(context) if context else None}


def aggregate(rows: list[dict]) -> dict:
    valid = [r for r in rows if r['eligible']]
    methods = list(valid[0]['metrics']) if valid else []
    groups = {'all': valid}
    groups.update({name: [r for r in valid if r['repository'] == name]
                   for name in sorted({r['repository'] for r in rows})})
    return {group: {'cases': len(subset), 'methods': {
        method: {'macro_recall': sum(r['metrics'][method]['recall'] for r in subset) / len(subset),
                 'mean_context_lines': sum(r['metrics'][method]['context_lines'] for r in subset) / len(subset)}
        for method in methods} if subset else {}}
        for group, subset in groups.items()}
