"""Serialized, source-inclusive replay study / 串行、包含源码读取成本的回放实验。

No upstream code is imported or executed. Replay equality is a same-resolver
check, not evidence of Python semantics, novelty, or downstream task benefit.
不导入或执行上游代码；同解析器回放一致性不证明 Python 语义、新颖性或任务效果。
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import resource
import re
import statistics
import subprocess
import sys
import tarfile
import time
import tokenize
import uuid

from contextproof.dependencies import _Corpus
from contextproof.evidence import sha256 as text_hash
from contextproof.graph import build_graph, canonical_graph_bytes
from contextproof.index import source_lines
from contextproof.reuse import GraphSession

METHODS = (
    'incremental_read_set',
    'incremental_catalog_coarse_guard',
    'incremental_catalog_root_guard',
    'incremental_catalog_read_set',
)
ROOT = Path(__file__).resolve().parents[2]
PIN_PATH = ROOT / 'benchmarks/catalog_reuse/inputs.json'
EXCLUDED_COMPONENTS = {'test', 'tests', 'testing', '__pycache__'}
CAPS = {'source_bytes': 16 * 1024**2, 'source_files': 1500,
        'single_file_bytes': 2 * 1024**2, 'archive_download_bytes': 32 * 1024**2}
# The sole archived run is fixed here, rather than selected by result assertions.
# 唯一历史运行在此固定，不由结果文件自行选择可信归档。
FROZEN_CATALOG_REFERENCE = 'frozen_catalog_20261014'
FROZEN_CATALOG_COMMIT = 'affa59024f70cde86d2549b690204aa73ddccc7d'
FROZEN_CATALOG_ARCHIVE = 'research/frozen-catalog-20261014-source'
FROZEN_CATALOG_LEDGER_SHA256 = '0573ba3055d75eec2aa9fe7691048e3df2c7779ca94533a6a210101c5c77c715'
FROZEN_CATALOG_PROTOCOL_SHA256 = 'a335536a0344c02e539361920d3c14ce33e5b4b2155dcd7726d2e4d2d33afd6c'
FROZEN_CATALOG_RUN_SHA256 = '667dbee3726034cf40b3733ff4da3a60c34bdab80959d2671a2758795bbcc5a1'


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def write_new(path: Path, value) -> None:
    """Never replace a result, including a symlink / 不覆盖已有结果或符号链接。"""
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def safe_path(value: str) -> str:
    if (not isinstance(value, str) or not value or '\\' in value or '\x00' in value
            or value.startswith('/') or ':' in value
            or any(part in {'', '.', '..'} for part in value.split('/'))):
        raise ValueError('unsafe relative input path / 不安全的输入相对路径')
    return value


def local_asset(root: Path, relative: str) -> Path:
    """Resolve only ordinary files beneath the input directory / 仅解析输入目录内普通文件。"""
    relative = safe_path(relative)
    path = root / relative
    # Checking every component prevents an apparently relative path escaping via
    # a symlink. The input root itself may be the user's chosen resolved directory.
    # 逐级拒绝符号链接，防止相对路径借链接越界。
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('input asset symlink is not permitted / 不允许输入符号链接')
    if not path.is_file():
        raise ValueError('input asset is missing / 输入文件缺失')
    return path


def read_json_asset(root: Path, relative: str, expected: str):
    raw = local_asset(root, relative).read_bytes()
    if digest(raw) != expected:
        raise ValueError('input metadata checksum mismatch / 输入元数据校验失败')
    return json.loads(raw)


def implementation_fingerprint() -> dict[str, str]:
    """Bind the actual core and measurement code / 绑定实际核心与测量代码。"""
    files = [*sorted((ROOT / 'src/contextproof').glob('*.py')),
             ROOT / 'benchmarks/catalog_reuse/suite.py', ROOT / 'scripts/run_catalog_study.py']
    return {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in files}


def _validate_frozen_catalog_archive(protocol: dict) -> dict:
    """Verify fixed historical bytes; never execute them / 核验固定历史字节，不执行。

    Only the sealed 2026-10-14 protocol is eligible. A self-edited protocol or
    ledger cannot create another trusted source reference.
    仅接受已封存协议；自行修改协议或清单不能建立另一个可信源码版本。
    """
    if digest(canonical(protocol)) != FROZEN_CATALOG_PROTOCOL_SHA256:
        raise ValueError('protocol is not the fixed historical catalog protocol')
    raw = local_asset(ROOT, FROZEN_CATALOG_ARCHIVE + '/SOURCE_MAP.json').read_bytes()
    if digest(raw) != FROZEN_CATALOG_LEDGER_SHA256:
        raise ValueError('historical catalog archive ledger checksum mismatch')
    ledger = json.loads(raw)
    if (ledger['source_commit'] != FROZEN_CATALOG_COMMIT
            or ledger['protocol_canonical_sha256'] != FROZEN_CATALOG_PROTOCOL_SHA256
            or ledger['run_canonical_sha256'] != FROZEN_CATALOG_RUN_SHA256
            or ledger['implementation_sha256'] != protocol['implementation_sha256']):
        raise ValueError('historical catalog source binding mismatch')
    expected, actual = protocol['implementation_sha256'], {}
    for file in ledger['files']:
        relative = safe_path(file['original_path'])
        if file['archive_path'] != relative or relative in actual:
            raise ValueError('historical catalog archive source map differs')
        content = local_asset(ROOT, FROZEN_CATALOG_ARCHIVE + '/' + relative).read_bytes()
        actual[relative] = digest(content)
        if len(content) != file['bytes'] or actual[relative] != file['sha256']:
            raise ValueError('historical catalog source checksum mismatch')
    if actual != expected:
        raise ValueError('historical catalog implementation fingerprint mismatch')
    archive = ROOT / FROZEN_CATALOG_ARCHIVE
    assets = list(archive.rglob('*'))
    if (any(path.is_symlink() for path in assets)
            or {path.relative_to(archive).as_posix() for path in assets if path.is_file()}
            != set(expected) | {'SOURCE_MAP.json'}):
        raise ValueError('historical catalog archive contains unexpected assets')
    return ledger


def source_pins(protocol: dict) -> dict:
    """Authoritative public definitions, not mutable result assertions.

    使用冻结公开输入定义，而非结果文件自行声称的样本集合。
    """
    expected = protocol.get('sources_pin_sha256')
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('protocol must bind a source-pin SHA256')
    if PIN_PATH.is_symlink():
        raise ValueError('source-pin blueprint cannot be a symlink')
    raw = PIN_PATH.read_bytes()
    if digest(raw) != expected:
        raise ValueError('source-pin blueprint differs from frozen protocol')
    pins = json.loads(raw)
    if (pins.get('schema_version') != 1 or pins.get('status') != 'pinned_input_definitions'
            or pins.get('input_rule_sha256') != protocol.get('input_rule_sha256')):
        raise ValueError('source-pin schema or input-rule binding mismatch')
    wanted = protocol['sources']
    if ([r['repo'] for r in pins['repositories']] != wanted['repositories']
            or any(repo['fixed_head'] != wanted['fixed_heads'][repo['repo']]
                   or repo['source_prefix'] != wanted['source_prefixes'][repo['repo']]
                   or len(repo['primary_snapshots']) != wanted['snapshots_per_repository']
                   or [s['ancestor_offset'] for s in repo['primary_snapshots']]
                   != wanted['ancestor_offsets_oldest_to_newest']
                   or len(repo['anchors']['anchors']) != wanted['anchors_per_repository']
                   for repo in pins['repositories'])):
        raise ValueError('source blueprint selection differs from frozen protocol')
    return pins


def subset_equal(actual, expected) -> bool:
    """Native metadata may retain additional audited AST fields.

    原始元数据可保留额外 AST 审核字段；公开精简字段必须逐项相同。
    """
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset_equal(actual[k], v)
                                                for k, v in expected.items()
                                                if k != 'historical_snapshot_metadata_sha256')
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            subset_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def production(path: str, prefix: str) -> bool:
    prefixes = prefix.split(';')
    return (path.endswith(('.py', '.pyi'))
            and any(path.startswith(p) if p.endswith('/') else path == p for p in prefixes)
            and not EXCLUDED_COMPONENTS.intersection(path.split('/')))


@dataclass(frozen=True)
class Snapshot:
    """Frozen metadata; source bytes are opened on every update / 元数据固定，每次更新读取源码。"""
    root: Path
    metadata: dict

    @property
    def commit(self) -> str:
        return self.metadata['commit']

    def load(self) -> dict[str, str]:
        """Verify the complete filtered catalog and bytes, then decode Python.

        Archives are read into memory and never extracted. Every declared source
        and root license must match its size, SHA256, and Git blob when supplied.
        Additional eligible paths fail instead of silently disappearing.
        不解压到磁盘；逐个核对源码与根许可证。额外合格路径使整次读取失败。
        """
        meta = self.metadata
        archive_path = local_asset(self.root, meta['archive_path'])
        if archive_path.stat().st_size > CAPS['archive_download_bytes']:
            raise ValueError('archive resource limit exceeded')
        raw = archive_path.read_bytes()
        if len(raw) != meta['archive_bytes'] or digest(raw) != meta['archive_sha256']:
            raise ValueError('source archive checksum mismatch')
        expected = {file['path']: file for file in meta['files']}
        licenses = {file['path']: file for file in meta['root_licenses']}
        if len(expected) != len(meta['files']) or len(licenses) != len(meta['root_licenses']):
            raise ValueError('duplicate declared source or license')
        if not expected or not licenses:
            raise ValueError('source and root license records must be nonempty')
        if len(expected) > CAPS['source_files']:
            raise ValueError('source file resource limit exceeded')
        seen, observed, seen_licenses, texts = set(), {}, set(), {}
        roots = set()
        total = 0
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            for member in archive:
                name = member.name.rstrip('/')
                safe_path(name)
                parts = PurePosixPath(name).parts
                roots.add(parts[0])
                if len(roots) != 1:
                    raise ValueError('archive must have exactly one root')
                if len(parts) == 1:
                    if not member.isdir():
                        raise ValueError('archive root must be a directory')
                    continue
                relative = PurePosixPath(*parts[1:]).as_posix()
                if relative in seen:
                    raise ValueError('duplicate archive member')
                seen.add(relative)
                eligible = production(relative, meta['source_prefix'])
                root_license = (len(parts) == 2
                                and relative.upper().startswith(('LICENSE', 'COPYING', 'COPYRIGHT')))
                if not eligible and not root_license:
                    continue
                if not member.isfile():
                    raise ValueError('eligible archive member is not a regular file')
                records = expected if eligible else licenses
                if relative not in records:
                    raise ValueError('archive source or license catalog differs from manifest')
                record = records[relative]
                if member.size != record['bytes'] or member.size > CAPS['single_file_bytes']:
                    raise ValueError('archive member size mismatch or file cap exceeded')
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('archive member could not be read')
                with stream:
                    content = stream.read(CAPS['single_file_bytes'] + 1)
                if len(content) != member.size or digest(content) != record['sha256']:
                    raise ValueError('source or license content checksum mismatch')
                blob = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
                if record.get('git_blob_oid', blob) != blob:
                    raise ValueError('source or license Git blob mismatch')
                if not eligible:
                    seen_licenses.add(relative)
                    continue
                total += len(content)
                if total > CAPS['source_bytes']:
                    raise ValueError('source byte resource limit exceeded')
                encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
                texts[relative] = content.decode(encoding)
                observed[relative] = [relative, len(content), digest(content)]
        if set(observed) != set(expected) or seen_licenses != set(licenses):
            raise ValueError('archive is missing declared source or license')
        tree_hash = digest(json.dumps([observed[p] for p in sorted(observed)],
                                     ensure_ascii=False, separators=(',', ':')).encode())
        if (tree_hash != meta['source_tree_sha256'] or total != meta['source_bytes']
                or len(texts) != meta['source_files']):
            raise ValueError('source tree checksum or counts mismatch')
        return texts


@dataclass(frozen=True)
class Repository:
    name: str
    fixed_head: str
    snapshots: dict[str, Snapshot]
    primary: tuple[str, ...]
    secondary: tuple[dict, ...]
    selected_anchors: tuple[dict, ...]

    def anchors(self, initial_texts: dict[str, str]) -> list[dict]:
        """Derive exact initial spans from fixed identities; never replace anchors.

        This work belongs to initial capture for every timed method. Decorators
        are included, and later missing/ambiguous declarations remain in scope.
        固定身份的首次精确片段含装饰器；后续缺失或歧义不替换锚点。
        """
        parsed = {}
        anchors = []
        for selected in self.selected_anchors:
            path, symbol = selected['path'], selected['symbol']
            if path not in parsed:
                parsed[path] = ast.parse(initial_texts[path], filename=path)
            matches = [node for node in parsed[path].body
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name == symbol]
            if not matches:
                raise ValueError('frozen initial anchor is absent')
            # A syntactically ambiguous initial key is retained: the resolver
            # sees every definition; this source witness uses the first occurrence.
            # 初始歧义保留，解析器仍看到全部定义；片段使用第一处定义。
            node = matches[0]
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            end = node.end_lineno
            text = ''.join(source_lines(initial_texts[path])[start - 1:end])
            identity = path + ':' + symbol
            if digest(identity.encode()) != selected['selection_sha256']:
                raise ValueError('anchor identity hash mismatch')
            anchors.append({'id': digest(identity.encode()), 'path': path, 'symbol': symbol,
                            'kind': 'function', 'start_line': start, 'end_line': end,
                            'text': text, 'text_sha256': text_hash(text),
                            'file_sha256': text_hash(initial_texts[path])})
        return anchors


def load_inputs(path: Path, protocol: dict) -> tuple[dict, list[Repository]]:
    """Verify pinned metadata before timing; no source graph is built here.

    元数据在计时前校验；本函数不创建源码图。
    """
    root = path.parent.resolve()
    raw = path.read_bytes()
    manifest = json.loads(raw)
    pins = source_pins(protocol)
    if manifest.get('schema_version') != 1 or manifest.get('status') != 'input_assets_ready':
        raise ValueError('inputs are not ready')
    if manifest.get('sources_pin_sha256') != protocol['sources_pin_sha256']:
        raise ValueError('ready manifest is not bound to frozen public input definitions')
    if protocol.get('input_manifest_sha256') not in {None, digest(raw)}:
        raise ValueError('input manifest differs from frozen protocol')
    rule = read_json_asset(root, manifest['input_rule_path'], manifest['input_rule_sha256'])
    if protocol.get('input_rule_sha256') not in {None, manifest['input_rule_sha256']}:
        raise ValueError('input rule differs from frozen protocol')
    wanted = protocol.get('sources', {})
    names = [r['repo'] for r in manifest['repositories']]
    if len(names) != len(set(names)) or names != rule['repositories']:
        raise ValueError('duplicate or reordered repositories')
    if wanted.get('repositories', names) != names:
        raise ValueError('repository selection drift')
    repositories = []
    if len(manifest['repositories']) != len(pins['repositories']):
        raise ValueError('ready manifest repository denominator differs from source pins')
    for entry, pinned in zip(manifest['repositories'], pins['repositories']):
        for field in ['repo', 'fixed_head', 'source_prefix', 'primary_snapshots',
                      'all_secondary_event_pairs', 'anchors_path', 'anchors_sha256']:
            if entry.get(field) != pinned.get(field):
                raise ValueError('ready repository or fixed sample panel differs from source pins')
        if [s['commit'] for s in entry['snapshots']] != [s['commit'] for s in pinned['snapshots']]:
            raise ValueError('ready snapshot denominator differs from source pins')
        pinned_snapshots = {s['commit']: s for s in pinned['snapshots']}
        if (wanted.get('fixed_heads', {}).get(entry['repo'], entry['fixed_head']) != entry['fixed_head']
                or wanted.get('source_prefixes', {}).get(entry['repo'], entry['source_prefix']) != entry['source_prefix']):
            raise ValueError('fixed head or source prefix drift')
        snapshot_map = {}
        for record in entry['snapshots']:
            metadata = read_json_asset(root, record['metadata_path'], record['metadata_sha256'])
            pin = pinned_snapshots[record['commit']]
            metadata_hashes = {pin['metadata_sha256'],
                               pin['metadata'].get('historical_snapshot_metadata_sha256')}
            if (record['metadata_sha256'] not in metadata_hashes
                    or not subset_equal(metadata, pin['metadata'])
                    or any(record.get(k) != pin.get(k) for k in ['metadata_path', 'archive_path',
                          'archive_sha256', 'source_tree_sha256', 'source_files', 'source_bytes'])):
                raise ValueError('ready snapshot contents or hashes differ from source pins')
            required = ['commit', 'archive_path', 'archive_sha256', 'source_tree_sha256',
                        'source_files', 'source_bytes']
            if (metadata.get('repo') != entry['repo']
                    or metadata.get('source_prefix') != entry['source_prefix']
                    or any(metadata.get(k) != record.get(k) for k in required)
                    or metadata.get('schema_version') != 2):
                raise ValueError('snapshot metadata disagrees with source pins')
            if (record['commit'] in snapshot_map or not all(metadata['gates'].values())
                    or not metadata['files'] or not metadata['root_licenses']):
                raise ValueError('duplicate or incomplete snapshot')
            for file in metadata['files']:
                if not production(safe_path(file['path']), entry['source_prefix']):
                    raise ValueError('declared source outside frozen production scope')
            snapshot_map[record['commit']] = Snapshot(root, metadata)
        primary_records = entry['primary_snapshots']
        if ([r['order'] for r in primary_records] != list(range(len(primary_records)))
                or [r['ancestor_offset'] for r in primary_records]
                != rule['primary_sampling']['ancestor_offsets_oldest_to_newest']
                or [r['ancestor_offset'] for r in primary_records]
                != wanted.get('ancestor_offsets_oldest_to_newest', rule['primary_sampling']['ancestor_offsets_oldest_to_newest'])
                or len(primary_records) != wanted.get('snapshots_per_repository', len(primary_records))):
            raise ValueError('primary source trajectory drift')
        primary = tuple(r['commit'] for r in primary_records)
        if (len(primary) != len(set(primary)) or any(c not in snapshot_map for c in primary)
                or primary[-1] != entry['fixed_head']):
            raise ValueError('primary source pins incomplete')
        anchor_data = read_json_asset(root, entry['anchors_path'], entry['anchors_sha256'])
        if anchor_data != pinned['anchors']:
            raise ValueError('ready anchor definitions differ from source pins')
        selected = anchor_data['anchors']
        identities = [a['path'] + ':' + a['symbol'] for a in selected]
        if (anchor_data.get('repo') != entry['repo']
                or anchor_data.get('initial_commit') != primary[0]
                or len(selected) != wanted.get('anchors_per_repository', rule['anchors_per_repo'])
                or len(identities) != len(set(identities))
                or identities != sorted(identities, key=lambda x: (digest(x.encode()), x))
                or any(a['identity'] != identity or a['selection_sha256'] != digest(identity.encode())
                       for a, identity in zip(selected, identities))):
            raise ValueError('fixed anchor selection drift')
        secondary = entry['all_secondary_event_pairs']
        if ([e['order'] for e in secondary] != list(range(len(secondary)))
                or len(secondary) != rule['expected_secondary_event_pairs'][entry['repo']]
                or any(e[role] not in snapshot_map for e in secondary for role in ['parent', 'commit'])):
            raise ValueError('secondary event panel incomplete')
        repositories.append(Repository(entry['repo'], entry['fixed_head'], snapshot_map,
                                       primary, tuple(secondary), tuple(selected)))
    return manifest, repositories


def _validate_protocol_contract(protocol: dict) -> None:
    if (type(protocol.get('schema_version')) is not int or protocol['schema_version'] != 1
            or protocol.get('status') != 'frozen'
            or protocol.get('methods') != list(METHODS)):
        raise ValueError('protocol must freeze the exact four methods')
    measurement = protocol.get('measurement', {})
    for field, minimum in [('warmup', 0), ('repetitions', 1), ('memory_repetitions', 0)]:
        if type(measurement.get(field)) is not int or measurement[field] < minimum:
            raise ValueError('invalid frozen measurement count')
    policy = protocol.get('graph_policy', {})
    if set(policy) != {'max_depth', 'max_nodes'} or any(type(v) is not int or v < 1 for v in policy.values()):
        raise ValueError('invalid fixed graph policy')
    source_pins(protocol)
    target = protocol.get('performance_target', {})
    gate = protocol.get('resource_gate', {})
    if (type(target.get('minimum_reduction_fraction')) not in {int, float}
            or not 0 <= target['minimum_reduction_fraction'] < 1
            or type(target.get('minimum_repositories_meeting_target')) is not int
            or not 1 <= target['minimum_repositories_meeting_target'] <= len(protocol['sources']['repositories'])
            or type(gate.get('absolute_peak_rss_bytes')) is not int
            or gate['absolute_peak_rss_bytes'] < 1
            or type(gate.get('maximum_candidate_to_primary_baseline_peak_rss_ratio')) not in {int, float}
            or not math.isfinite(gate['maximum_candidate_to_primary_baseline_peak_rss_ratio'])
            or gate['maximum_candidate_to_primary_baseline_peak_rss_ratio'] <= 0):
        raise ValueError('invalid frozen performance/resource targets')


def validate_protocol(protocol: dict) -> None:
    """Measurement always binds current code / 测量始终绑定当前代码，无历史回退。"""
    _validate_protocol_contract(protocol)
    fingerprint = protocol.get('implementation_sha256')
    if not isinstance(fingerprint, dict) or fingerprint != implementation_fingerprint():
        raise ValueError('measurement/core implementation differs from frozen protocol')


def method_order(repository_index: int, repetition: int) -> tuple[str, ...]:
    """Rotate whole trajectories, never interleave timed updates / 轮转整段轨迹，不交错计时。"""
    shift = (repository_index + repetition) % len(METHODS)
    return METHODS[shift:] + METHODS[:shift]


def fresh_graphs(texts: dict[str, str], snapshot_id: str, anchors: list[dict], policy: dict) -> tuple[bytes, ...]:
    """Fresh corpus and no candidate/session cache / 全新语料，无候选或会话缓存。"""
    corpus = _Corpus.from_texts(dict(texts))
    return tuple(canonical_graph_bytes(build_graph(texts, snapshot_id, [anchor],
                 _corpus=corpus, **policy)) for anchor in anchors)


def graph_counts(graphs: list[dict]) -> dict:
    return {'complete_graphs': sum(not g['frontier'] for g in graphs),
            'frontier_entries': sum(len(g['frontier']) for g in graphs),
            'frontier_kinds': dict(sorted(Counter(f['kind'] for g in graphs for f in g['frontier']).items())),
            'anchor_statuses': dict(sorted(Counter(a['status'] for g in graphs for a in g['anchors']).items())),
            'source_statuses': dict(sorted(Counter(a['source_status'] for g in graphs for a in g['anchors']).items())),
            'per_graph': [{'frontier_count': len(g['frontier']),
                           'frontier_kinds': dict(sorted(Counter(f['kind'] for f in g['frontier']).items())),
                           'anchors': [{'status': a['status'], 'source_status': a['source_status']}
                                       for a in g['anchors']]} for g in graphs]}


def certificate_counts(session: GraphSession) -> dict:
    """Diagnostic counts only, without exporting a reusable certificate.

    只记录诊断计数，不导出可复用证书。
    """
    counts = []
    for index, trace in enumerate(session._catalog_footprints):
        valid = session._catalog_trace_valid(index)
        counts.append({'available': valid,
                       'exact_queries': sum(key[0] == 'exact' for key in trace) if valid else 0,
                       'negative_exact_queries': sum(key[0] == 'exact' and not answer
                                                     for key, answer in trace.items()) if valid else 0,
                       'subtree_queries': sum(key[0] == 'subtree' for key in trace) if valid else 0,
                       'false_subtree_queries': sum(key[0] == 'subtree' and not answer
                                                    for key, answer in trace.items()) if valid else 0})
    return {'per_graph': counts,
            'negative_exact_queries': sum(c['negative_exact_queries'] for c in counts),
            'false_subtree_queries': sum(c['false_subtree_queries'] for c in counts)}


def replay_trajectory(repository: Repository, commits: tuple[str, ...], mode: str,
                      policy: dict, *, repetition: int, panel: str, oracle: dict,
                      emit, fixed_anchors: list[dict] | None = None,
                      measured: bool = True) -> None:
    """One complete method trajectory; equality checks happen after each timer.

    单个方法完整轨迹；每步在计时结束后检查字节一致性。
    """
    session, anchors, previous = None, fixed_anchors, None
    anchor_key = None if anchors is None else digest(canonical(anchors))
    for index, commit in enumerate(commits):
        snap = repository.snapshots[commit]
        row = {'repository': repository.name, 'panel': panel, 'method': mode,
               'repetition': repetition, 'version_index': index, 'snapshot_id': commit,
               'phase': 'capture' if index == 0 else 'replay', 'measured': measured,
               'source_tree_sha256': snap.metadata['source_tree_sha256'],
               'archive_sha256': snap.metadata['archive_sha256'], 'status': 'running'}
        try:
            started = time.perf_counter_ns()
            texts = snap.load()
            loaded = time.perf_counter_ns()
            if session is None:
                if anchors is None:
                    anchors = repository.anchors(texts)
                session = GraphSession(anchors, mode=mode, **policy)
            initialized = time.perf_counter_ns()
            replay = session.update(texts, commit)
            stopped = time.perf_counter_ns()
            # Oracle construction, output hashing, metadata and serialization are
            # outside the timer. All source verification and graph work are inside.
            # 基准/输出哈希/记录不计时；源码验证、初始化与图更新全部计时。
            if anchor_key is None:
                anchor_key = digest(canonical(anchors))
            key = (commit, snap.metadata['source_tree_sha256'], anchor_key)
            if key not in oracle:
                oracle[key] = fresh_graphs(texts, commit, anchors, policy)
            actual = tuple(canonical_graph_bytes(g) for g in replay.graphs)
            expected = oracle[key]
            mismatches = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
            if len(actual) != len(expected):
                mismatches.append(-1)
            changed = ([] if previous is None else sorted(p for p in previous.keys() | texts.keys()
                       if previous.get(p) != texts.get(p)))
            row.update({'elapsed_ns': stopped - started, 'load_ns': loaded - started,
                        'initialize_ns': initialized - loaded, 'graph_ns': stopped - initialized,
                        'source_changed': bool(changed), 'changed_paths': changed,
                        'catalog_changed': previous is not None and previous.keys() != texts.keys(),
                        'source_files': len(texts), 'source_bytes': snap.metadata['source_bytes'],
                        'reused': replay.reused, 'rebuilt': replay.rebuilt, 'reasons': replay.reasons,
                        'index_stats': session.index_stats, 'catalog_stats': session.catalog_stats,
                        'catalog_query_diagnostics': certificate_counts(session),
                        'actual_graph_sha256': [digest(g) for g in actual],
                        'expected_graph_sha256': [digest(g) for g in expected],
                        'mismatch_anchor_indices': mismatches, 'canonical_equal': not mismatches,
                        'status': 'failed' if mismatches else 'passed', **graph_counts(replay.graphs)})
            # Secondary rows are mechanism checks only: no timing measurements
            # are reported or summarized for the event-conditioned panel.
            # 次级事件面板只检验机制，不报告时间或用其宣称总体加速。
            if not measured:
                for field in ['elapsed_ns', 'load_ns', 'initialize_ns', 'graph_ns']:
                    row.pop(field)
            emit(row)
            if mismatches:
                raise RuntimeError('fresh canonical graph mismatch')
            previous = texts
        except Exception as error:
            if row['status'] == 'running':
                row.update(status='failed', error_type=type(error).__name__,
                           error_code='snapshot_load_or_graph_execution_failed')
                emit(row)
            raise


def environment() -> dict:
    """Public-safe hardware/runtime record / 可公开的硬件与运行时记录。"""
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    cpu = platform.processor()
    memory = None
    if sys.platform == 'darwin':
        cpu = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip()
        memory = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True))
    thread_fields = ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                     'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']
    return {'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'system': platform.system(), 'release': platform.release(), 'architecture': platform.machine(),
            'cpu': cpu, 'logical_cpus': os.cpu_count(), 'memory_bytes': memory, 'workers': 1,
            'thread_environment': {k: os.environ[k] if os.environ[k].isdigit() else 'set-nonnumeric'
                                   for k in thread_fields if k in os.environ},
            'source_commit': git('rev-parse', 'HEAD'), 'source_dirty': bool(git('status', '--porcelain')),
            'runner_sha256': digest(Path(__file__).read_bytes()),
            'implementation_sha256': implementation_fingerprint()}


def peak_rss_bytes(value: int | float, system: str | None = None) -> int:
    """macOS ru_maxrss is bytes; Linux is KiB / macOS 为字节，Linux 为 KiB。"""
    system = platform.system() if system is None else system
    if system not in {'Darwin', 'Linux'}:
        raise ValueError('RSS normalization is supported only on macOS and Linux')
    return int(value if system == 'Darwin' else value * 1024)


def rss_worker(inputs: Path, protocol_path: Path, repository_name: str, method: str) -> dict:
    """Fresh process trajectory; no timers, oracle or candidate graph cache.

    全新进程运行完整轨迹，不与计时并行，不构造基准图。
    """
    protocol = json.loads(protocol_path.read_bytes())
    validate_protocol(protocol)
    if method not in METHODS:
        raise ValueError('unknown RSS method')
    _, repositories = load_inputs(inputs, protocol)
    matches = [repo for repo in repositories if repo.name == repository_name]
    if len(matches) != 1:
        raise ValueError('unknown RSS repository')
    repository = matches[0]
    def worker_provenance():
        return {'environment': environment(), 'implementation_sha256': implementation_fingerprint(),
                'protocol_sha256': digest(protocol_path.read_bytes()),
                'input_manifest_sha256': digest(inputs.read_bytes()),
                'sources_pin_sha256': digest(PIN_PATH.read_bytes())}
    before = worker_provenance()
    session = None
    graph_digests = []
    for commit in repository.primary:
        texts = repository.snapshots[commit].load()
        if session is None:
            session = GraphSession(repository.anchors(texts), mode=method, **protocol['graph_policy'])
        replay = session.update(texts, commit)
        graph_digests.append([digest(canonical_graph_bytes(g)) for g in replay.graphs])
    after = worker_provenance()
    if after != before:
        raise ValueError('RSS worker source or input provenance changed during execution')
    return {'repository': repository_name, 'method': method, 'status': 'passed',
            'peak_rss_bytes': peak_rss_bytes(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            'normalization': 'Darwin bytes; Linux KiB multiplied by1024',
            'graph_digests': graph_digests, 'snapshots': len(repository.primary),
            **after,
            'scope': 'whole fresh worker process, including imports, metadata, source verification and replay'}


def measure_rss(inputs: Path, protocol_path: Path, repository: Repository, method: str,
                repetition: int) -> dict:
    command = [sys.executable, str(ROOT / 'scripts/run_catalog_study.py'), '--rss-worker',
               '--inputs', str(inputs.resolve()), '--protocol', str(protocol_path.resolve()),
               '--repository', repository.name, '--method', method]
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return {'repository': repository.name, 'method': method, 'repetition': repetition,
                'status': 'failed', 'error_code': 'rss_worker_timed_out', 'timeout_seconds': 1800}
    if process.returncode:
        return {'repository': repository.name, 'method': method, 'repetition': repetition,
                'status': 'failed', 'returncode': process.returncode,
                'stderr_sha256': digest(process.stderr.encode()), 'error_code': 'rss_worker_failed'}
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {'repository': repository.name, 'method': method, 'repetition': repetition,
                'status': 'failed', 'error_code': 'rss_worker_invalid_json',
                'stdout_sha256': digest(process.stdout.encode())}
    result['repetition'] = repetition
    if (result.get('repository') != repository.name or result.get('method') != method
            or result.get('status') != 'passed' or result.get('snapshots') != len(repository.primary)
            or not isinstance(result.get('graph_digests'), list)
            or len(result['graph_digests']) != len(repository.primary)
            or any(not isinstance(vector, list) or len(vector) != len(repository.selected_anchors)
                   or any(not isinstance(h, str) or not re.fullmatch(r'[0-9a-f]{64}', h) for h in vector)
                   for vector in result['graph_digests'])
            or type(result.get('peak_rss_bytes')) is not int or result['peak_rss_bytes'] < 1):
        raise ValueError('invalid RSS worker result')
    return result


def validate_results(result: dict, *, source_reference: str = 'current') -> None:
    """Reject missing/duplicate/failed rows before any positive report.

    报告前拒绝缺失、重复、失败或不一致的原始记录。
    """
    if type(result.get('schema_version')) is not int or result['schema_version'] != 1:
        raise ValueError('unsupported result schema version')
    if result.get('status') != 'passed':
        raise ValueError('cannot summarize an incomplete or failed run')
    protocol = result['protocol']
    if source_reference == 'current':
        validate_protocol(protocol)
    elif source_reference == FROZEN_CATALOG_REFERENCE:
        ledger = _validate_frozen_catalog_archive(protocol)
        _validate_protocol_contract(protocol)
        if (result['environment'].get('source_commit') != FROZEN_CATALOG_COMMIT
                or result['environment'].get('source_dirty') is not False
                or result.get('run_id') != ledger['run_id']
                or digest(canonical(result)) != FROZEN_CATALOG_RUN_SHA256):
            raise ValueError('result is not the sealed historical catalog run')
    else:
        raise ValueError('unsupported result source reference; no automatic archive fallback')
    pins = source_pins(protocol)
    expected_sources = [{'repository': r['repo'], 'fixed_head': r['fixed_head'],
                         'primary_commits': [s['commit'] for s in r['primary_snapshots']],
                         'secondary_pairs': [{'order': e['order'], 'parent': e['parent'], 'commit': e['commit']}
                                             for e in r['all_secondary_event_pairs']],
                         'anchor_identities': [a['identity'] for a in r['anchors']['anchors']],
                         'source_tree_sha256': {s['commit']: s['source_tree_sha256'] for s in r['snapshots']}}
                        for r in pins['repositories']]
    if result.get('sources') != expected_sources or not expected_sources:
        raise ValueError('result source denominator or pins differ from frozen source definitions')
    if (result.get('sources_pin_sha256') != protocol['sources_pin_sha256']
            or result.get('protocol_canonical_sha256') != digest(canonical(protocol))
            or result['environment'].get('implementation_sha256') != protocol['implementation_sha256']):
        raise ValueError('result source/protocol/implementation binding differs from frozen definitions')
    expected, rows = set(), result['rows']
    measurement = result['protocol']['measurement']
    for repo in result['sources']:
        for repetition in range(-measurement['warmup'], measurement['repetitions']):
            expected.update((repo['repository'], 'primary', method, repetition, index)
                            for method in METHODS for index in range(len(repo['primary_commits'])))
        for event in repo['secondary_pairs']:
            panel = f"secondary:{event['order']}"
            expected.update((repo['repository'], panel, method, 0, index)
                            for method in METHODS for index in range(2))
    keys = [(r['repository'], r['panel'], r['method'], r['repetition'], r['version_index']) for r in rows]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError('missing or duplicate trajectory row')
    source_map = {r['repository']: r for r in expected_sources}
    snapshot_map = {r['repo']: {s['commit']: s for s in r['snapshots']} for r in pins['repositories']}
    invariant_rows = {}
    for row in rows:
        source = source_map[row['repository']]
        nanchors = len(source['anchor_identities'])
        sid = (source['primary_commits'][row['version_index']] if row['panel'] == 'primary'
               else next(e for e in source['secondary_pairs']
                         if row['panel'] == f"secondary:{e['order']}")[
                             'parent' if row['version_index'] == 0 else 'commit'])
        pin = snapshot_map[row['repository']][sid]
        if (row.get('snapshot_id') != sid
                or row.get('phase') != ('capture' if row['version_index'] == 0 else 'replay')
                or row.get('measured') is not (row['panel'] == 'primary')
                or row.get('source_tree_sha256') != pin['source_tree_sha256']
                or row.get('archive_sha256') != pin['archive_sha256']
                or row.get('source_files') != pin['source_files']
                or row.get('source_bytes') != pin['source_bytes']
                or row.get('source_commit') != result['environment']['source_commit']
                or row.get('protocol_sha256') != result['protocol_sha256']):
            raise ValueError('row source, phase, measurement or implementation provenance drift')
        for field in ['actual_graph_sha256', 'expected_graph_sha256']:
            vector = row.get(field)
            if (not isinstance(vector, list) or len(vector) != nanchors
                    or any(not isinstance(h, str) or not re.fullmatch(r'[0-9a-f]{64}', h) for h in vector)):
                raise ValueError('row graph digest vector has wrong shape')
        counters = ['reused', 'rebuilt', 'complete_graphs', 'frontier_entries']
        if (any(type(row.get(k)) is not int or row[k] < 0 for k in counters)
                or row['complete_graphs'] > nanchors or not isinstance(row.get('reasons'), dict)
                or any(type(v) is not int or v < 0 for v in row['reasons'].values())):
            raise ValueError('row replay counters must be nonnegative integers')
        if (row['status'] != 'passed' or not row['canonical_equal']
                or row['actual_graph_sha256'] != row['expected_graph_sha256']
                or row['mismatch_anchor_indices'] or row['reused'] + row['rebuilt'] != len(row['actual_graph_sha256'])
                or sum(row['reasons'].values()) != len(row['actual_graph_sha256'])):
            raise ValueError('failed or inconsistent replay row')
        if row['measured']:
            parts = [row[k] for k in ['load_ns', 'initialize_ns', 'graph_ns']]
            if any(type(v) is not int or v < 0 for v in parts) or row['elapsed_ns'] != sum(parts):
                raise ValueError('invalid source-inclusive timing row')
        elif any(k in row for k in ['elapsed_ns', 'load_ns', 'initialize_ns', 'graph_ns']):
            raise ValueError('secondary mechanism rows cannot carry timing claims')
        if (not isinstance(row.get('per_graph'), list) or len(row['per_graph']) != nanchors
                or sum(g['frontier_count'] for g in row['per_graph']) != row['frontier_entries']
                or sum(row['frontier_kinds'].values()) != row['frontier_entries']
                or sum(row['anchor_statuses'].values()) != nanchors
                or sum(row['source_statuses'].values()) != nanchors):
            raise ValueError('row graph-status counters disagree with fixed anchor scope')
        invariant = {k: row[k] for k in ['actual_graph_sha256', 'complete_graphs', 'frontier_entries',
                     'frontier_kinds', 'anchor_statuses', 'source_statuses', 'per_graph']}
        key = row['repository'], sid
        if key in invariant_rows and invariant != invariant_rows[key]:
            raise ValueError('same frozen snapshot output/status drift across methods or repetitions')
        invariant_rows[key] = invariant
    wanted_memory = {(repo['repository'], method, rep)
                     for repo in result['sources'] for method in METHODS
                     for rep in range(measurement['memory_repetitions'])}
    memory_keys = [(r['repository'], r['method'], r['repetition']) for r in result['memory_rows']]
    if (set(memory_keys) != wanted_memory or len(memory_keys) != len(set(memory_keys))
            or any(r['status'] != 'passed' or not r.get('canonical_equal')
                   for r in result['memory_rows'])):
        raise ValueError('missing, duplicate or failed memory result')
    for row in result['memory_rows']:
        source = source_map[row['repository']]
        expected_vectors = [invariant_rows[row['repository'], sid]['actual_graph_sha256']
                            for sid in source['primary_commits']]
        if (row.get('snapshots') != len(source['primary_commits'])
                or row.get('graph_digests') != expected_vectors
                or row.get('protocol_sha256') != result['protocol_sha256']
                or row.get('input_manifest_sha256') != result['input_manifest_sha256']
                or row.get('sources_pin_sha256') != protocol['sources_pin_sha256']
                or row.get('environment', {}).get('source_commit') != result['environment']['source_commit']
                or row.get('implementation_sha256') != protocol['implementation_sha256']
                or type(row.get('peak_rss_bytes')) is not int or row['peak_rss_bytes'] < 1):
            raise ValueError('RSS worker source, implementation, sample shape or output differs from parent')


def summarize(result: dict, *, source_reference: str = 'current') -> dict:
    validate_results(result, source_reference=source_reference)
    groups = {}
    targets = result['protocol']['performance_target']
    resource_gate = result['protocol']['resource_gate']
    for source in result['sources']:
        repository = source['repository']
        methods = {}
        for method in METHODS:
            selected = [r for r in result['rows'] if r['repository'] == repository
                        and r['panel'] == 'primary' and r['method'] == method and r['repetition'] >= 0]
            stats = {}
            for phase in ['capture', 'replay', 'total']:
                totals = [sum(r['elapsed_ns'] for r in selected if r['repetition'] == repetition
                              and (phase == 'total' or r['phase'] == phase)) / 1e6
                          for repetition in range(result['protocol']['measurement']['repetitions'])]
                stats[phase] = {'trials_ms': totals, 'median_ms': statistics.median(totals),
                                'min_ms': min(totals), 'max_ms': max(totals)}
            stats['reused_per_trial'] = [sum(r['reused'] for r in selected if r['repetition'] == rep
                                           and r['phase'] == 'replay')
                                         for rep in range(result['protocol']['measurement']['repetitions'])]
            memory = [r['peak_rss_bytes'] for r in result['memory_rows']
                      if r['repository'] == repository and r['method'] == method]
            stats['peak_rss_trials_bytes'] = memory
            stats['max_peak_rss_bytes'] = max(memory) if memory else None
            stats['median_peak_rss_bytes'] = statistics.median(memory) if memory else None
            methods[method] = stats
        root, fine, original = (methods[METHODS[i]] for i in [2, 3, 0])
        reduction = 1 - fine['replay']['median_ms'] / root['replay']['median_ms']
        original_reduction = 1 - fine['replay']['median_ms'] / original['replay']['median_ms']
        memory_ratio = (fine['median_peak_rss_bytes'] / root['median_peak_rss_bytes']
                        if fine['median_peak_rss_bytes'] is not None else None)
        groups[repository] = {'methods': methods, 'primary_replay_reduction_D_vs_C': reduction,
                              'secondary_replay_reduction_D_vs_A': original_reduction,
                              'median_peak_rss_ratio_D_vs_C': memory_ratio,
                              'replay_target_met': reduction >= targets['minimum_reduction_fraction'],
                              'memory_target_met': memory_ratio is not None
                                  and memory_ratio <= resource_gate['maximum_candidate_to_primary_baseline_peak_rss_ratio']
                                  and fine['max_peak_rss_bytes'] <= resource_gate['absolute_peak_rss_bytes']}
    wins = sum(group['replay_target_met'] for group in groups.values())
    return {'schema_version': 1, 'run_id': result['run_id'], 'groups': groups,
            'canonical_mismatches': 0, 'repositories_meeting_replay_target': wins,
            'replay_target_met': wins >= targets['minimum_repositories_meeting_target'],
            'memory_target_met': all(g['memory_target_met'] for g in groups.values()),
            'interpretation': 'Descriptive fixed-source replay equality and cost; no semantic or downstream-quality conclusion.',
            'timing_scope': 'warm filesystem cache; archive read/hash/decompress/decode/file-hash verification + initial anchor extraction/session creation + update; oracle and result serialization excluded',
            'secondary_scope': 'all retained catalog-event pairs, mechanism diagnostics only; not representative overall speed evidence'}


def run_study(inputs: Path, protocol_path: Path, output: Path, *,
              repetitions: int | None = None, memory_repetitions: int | None = None,
              progress=None) -> dict:
    """Create an exclusive run, retain failures, and serialize every measurement.

    新建独占结果目录；保留失败；所有测量串行执行。
    """
    if output.exists() or output.is_symlink():
        raise FileExistsError('run output already exists; never overwrite historical results')
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 1,
              'run_id': 'catalog-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8],
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'running', 'rows': [], 'memory_rows': [], 'sources': [],
              'command': 'python scripts/run_catalog_study.py --inputs INPUTS --protocol PROTOCOL --output NEW_RUN_DIRECTORY',
              'timing_method': 'time.perf_counter_ns; one process/worker; whole-method trajectories rotated',
              'research_maturity': 'not_established'}
    row_file = output / 'rows.jsonl'
    row_file.touch(exist_ok=False)
    def emit(row):
        if 'environment' in result:
            row['source_commit'] = result['environment']['source_commit']
            row['protocol_sha256'] = result['protocol_sha256']
            row['run_id'] = result['run_id']
        result['rows'].append(row)
        with row_file.open('ab') as stream:
            stream.write(canonical(row) + b'\n')
            stream.flush()
        if progress:
            progress({k: row[k] for k in ['repository', 'panel', 'method', 'repetition', 'version_index', 'status']})
    try:
        protocol_raw = protocol_path.read_bytes()
        protocol = json.loads(protocol_raw)
        validate_protocol(protocol)
        measurement = protocol['measurement']
        if (repetitions not in {None, measurement['repetitions']}
                or memory_repetitions not in {None, measurement['memory_repetitions']}):
            raise ValueError('CLI counts differ from frozen protocol')
        manifest, repositories = load_inputs(inputs, protocol)
        result.update(protocol=protocol, protocol_sha256=digest(protocol_raw),
                      protocol_canonical_sha256=digest(canonical(protocol)),
                      sources_pin_sha256=protocol['sources_pin_sha256'],
                      input_manifest_sha256=digest(inputs.read_bytes()),
                      input_rule_sha256=manifest['input_rule_sha256'], environment=environment())
        for repository in repositories:
            result['sources'].append({'repository': repository.name, 'fixed_head': repository.fixed_head,
                                      'primary_commits': list(repository.primary),
                                      'secondary_pairs': [{'order': e['order'], 'parent': e['parent'], 'commit': e['commit']}
                                                          for e in repository.secondary],
                                      'anchor_identities': [a['identity'] for a in repository.selected_anchors],
                                      'source_tree_sha256': {c: s.metadata['source_tree_sha256'] for c, s in repository.snapshots.items()}})
        for repo_index, repository in enumerate(repositories):
            oracle = {}
            for repetition in range(-measurement['warmup'], measurement['repetitions']):
                order = method_order(repo_index, repetition)
                for method in order:
                    replay_trajectory(repository, repository.primary, method, protocol['graph_policy'],
                                      repetition=repetition, panel='primary', oracle=oracle, emit=emit)
            # Event-conditioned diagnostics retain the original earliest anchors,
            # rather than replacing missing keys with favorable new declarations.
            # 事件诊断沿用最早固定锚点，缺失时不换成新声明。
            fixed = repository.anchors(repository.snapshots[repository.primary[0]].load())
            for event in repository.secondary:
                for method in method_order(repo_index, event['order']):
                    replay_trajectory(repository, (event['parent'], event['commit']), method,
                                      protocol['graph_policy'], repetition=0,
                                      panel=f"secondary:{event['order']}", oracle=oracle, emit=emit,
                                      fixed_anchors=fixed, measured=False)
            del oracle
        # Memory workers run after all timed work, not alongside it. They are
        # independent fresh processes, so previous timed caches do not count.
        # 所有计时结束后才运行独立内存进程，先前计时缓存不计入其 RSS。
        for repo_index, repository in enumerate(repositories):
            for repetition in range(measurement['memory_repetitions']):
                for method in method_order(repo_index, repetition):
                    row = measure_rss(inputs, protocol_path, repository, method, repetition)
                    if row['status'] == 'passed':
                        expected = [next(r['expected_graph_sha256'] for r in result['rows']
                                         if r['repository'] == repository.name and r['panel'] == 'primary'
                                         and r['snapshot_id'] == commit)
                                    for commit in repository.primary]
                        provenance_equal = (
                            row.get('protocol_sha256') == result['protocol_sha256']
                            and row.get('input_manifest_sha256') == result['input_manifest_sha256']
                            and row.get('sources_pin_sha256') == protocol['sources_pin_sha256']
                            and row.get('implementation_sha256') == protocol['implementation_sha256']
                            and row.get('environment', {}).get('source_commit') == result['environment']['source_commit']
                            and row.get('environment', {}).get('source_dirty') == result['environment']['source_dirty'])
                        row['canonical_equal'] = row['graph_digests'] == expected
                        if not row['canonical_equal']:
                            row.update(status='failed', error_code='rss_fresh_graph_mismatch')
                        if not provenance_equal:
                            row.update(status='failed', error_code='rss_worker_provenance_drift')
                    result['memory_rows'].append(row)
                    write_new(output / f'memory-{repo_index}-{repetition}-{METHODS.index(method)}.json', row)
                    if progress:
                        progress({'repository': repository.name, 'panel': 'memory', 'method': method,
                                  'repetition': repetition, 'status': row['status']})
                    if row['status'] != 'passed':
                        raise RuntimeError('fresh memory worker failed')
        result['status'] = 'passed'
        result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        summary = summarize(result)
        write_new(output / 'summary.json', summary)
        write_new(output / 'run.json', result)
        return result
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__,
                      error_code='study_incomplete_or_failed',
                      finished_at_utc=datetime.now(timezone.utc).isoformat())
        write_new(output / 'run.json', result)
        raise
