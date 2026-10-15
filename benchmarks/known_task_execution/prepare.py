"""Rebuild fixed known-task source without executing it. / 只重建源码，不执行上游内容。"""
import argparse
import ast
import csv
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath
DATASET_SHA256 = '20961b616b404875adead16dd456adc4cf583035436fc0d7e9c3f2adf8322e0c'
SOURCES = Path(__file__).parents[1] / 'external_context/sources.json'
MAX_CSV_BYTES = 32 * 1024 ** 2
MAX_ARCHIVE_BYTES = 500 * 1024 ** 2

def read_verified_bytes(path, expected_sha, limit, label):
    """Bound and hash the exact bytes subsequently parsed. / 限量读取并解析同一份核验字节。"""
    if type(limit) is not int or limit <= 0:
        raise ValueError('invalid source read byte cap')
    if path.is_symlink():
        raise ValueError(label + ' symlink refused')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(label + ' byte cap exceeded')
    if digest(raw) != expected_sha:
        raise ValueError(label + ' hash differs')
    return raw

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def safe_path(name):
    """Reject escapes and ambiguous identities. / 拒绝越界或含糊路径。"""
    if not isinstance(name, str) or not name or name.startswith('/') or ('\\' in name) or ('\x00' in name) or (':' in name) or any((x in {'', '.', '..'} or x.casefold() == '.git' for x in name.split('/'))):
        raise ValueError('unsafe source path / 不安全源码路径')
    return PurePosixPath(name)

def split_patch(patch):
    groups = []
    for block in re.split('(?=^diff --git )', patch, flags=re.M):
        if not block.startswith('diff --git '):
            continue
        m = re.match('diff --git a/(.+?) b/(.+?)\\n', block)
        if not m:
            raise ValueError('noncanonical patch header')
        groups.append((m.group(2), block))
    return groups

def apply_patch(original, block):
    """Exact old/new hunk positions and bytes. / 精确核验两侧hunk位置与字节。"""
    if len(patch_blocks(block)) != 1:
        raise ValueError('expected one canonical text patch block')
    def physical_lines(text):
        parts = text.split('\n')
        return [part + '\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    original_lines = physical_lines(original)
    lines = physical_lines(block)
    result = []
    cursor = 0
    i = 0
    while i < len(lines):
        m = re.match('@@ -(\\d+)(?:,(\\d+))? \\+(\\d+)(?:,(\\d+))? @@', lines[i])
        if not m:
            if lines[i].startswith('@@'):
                raise ValueError('malformed hunk header')
            i += 1
            continue
        old_start = int(m.group(1))
        old_count = int(m.group(2) or 1)
        new_start = int(m.group(3))
        new_count = int(m.group(4) or 1)
        target = old_start - 1 if old_count else old_start
        if (target < 0 or target > len(original_lines)
                or (new_count and new_start < 1)):
            raise ValueError('patch hunk starts outside source')
        if target < cursor:
            raise ValueError('overlapping patch hunks')
        result.extend(original_lines[cursor:target])
        if len(result) != (new_start - 1 if new_count else new_start):
            raise ValueError('new patch hunk position differs')
        cursor = target
        i += 1
        entries = []
        while i < len(lines) and (not lines[i].startswith('@@ ')):
            line = lines[i]
            if line.startswith('\\ No newline'):
                if not entries:
                    raise ValueError('newline marker without line')
                typ, text = entries[-1]
                entries[-1] = (typ, text.rstrip('\n'))
            elif line and line[0] in ' +-':
                entries.append((line[0], line[1:]))
            else:
                break
            i += 1
        seen_old = seen_new = 0
        for typ, text in entries:
            if typ in ' -':
                if cursor >= len(original_lines) or original_lines[cursor] != text:
                    raise ValueError('patch context differs from official base')
                cursor += 1
                seen_old += 1
            if typ in ' +':
                result.append(text)
                seen_new += 1
        if (seen_old, seen_new) != (old_count, new_count):
            raise ValueError('patch hunk count mismatch')
    result.extend(original_lines[cursor:])
    return ''.join(result)

def task_row(csv_path, task_id, expected_sha=None):
    """Parse data only, never execute fields. / 字段仅作数据解析。"""
    expected_sha = DATASET_SHA256 if expected_sha is None else expected_sha
    raw = read_verified_bytes(csv_path, expected_sha, MAX_CSV_BYTES, 'dataset')
    old = csv.field_size_limit()
    try:
        csv.field_size_limit(16 * 1024 ** 2)
        with io.StringIO(raw.decode('utf-8'), newline='') as f:
            rows = [r for r in csv.DictReader(f) if r['instance_id'] == task_id]
    finally:
        csv.field_size_limit(old)
    if len(rows) != 1:
        raise ValueError('task must have exactly one row')
    row = rows[0]
    for key in ['F2P', 'P2P']:
        v = ast.literal_eval(row[key]) if row[key].strip() else []
        if not isinstance(v, list) or not all((isinstance(x, str) for x in v)):
            raise ValueError('invalid label list')
        row[key] = v
    return row

def patch_blocks(text):
    """Exact text hunks only; no fuzzy context. / 只接受精确文本hunk。"""
    blocks = split_patch(text)
    names = set()
    if text.strip() and (not blocks):
        raise ValueError('no recognized patch')
    for name, block in blocks:
        safe_path(name)
        m = re.match('diff --git a/(.+?) b/(.+?)\\n', block)
        if not m or m[1] != m[2] or name in names or ('GIT binary patch' in block) or ('deleted file mode' in block) or (not re.search('^@@ ', block, re.M)):
            raise ValueError('unsupported or malformed text patch')
        header = block.split('\n@@ ', 1)[0]
        old_markers = re.findall(r'^--- (.*)$', header, re.M)
        new_markers = re.findall(r'^\+\+\+ (.*)$', header, re.M)
        is_new = bool(re.search(r'^new file mode [0-7]+$', header, re.M))
        if old_markers != ['/dev/null' if is_new else 'a/' + name] or new_markers != ['b/' + name]:
            raise ValueError('patch file markers differ from canonical identity')
        names.add(name)
    return blocks

def archive_files(archive, expected_sha, row, max_total=512 * 1024 ** 2):
    """Read declared regular files; retain omissions. / 读取范围内普通文件并记录省略。"""
    archive_raw = read_verified_bytes(archive, expected_sha, MAX_ARCHIVE_BYTES, 'archive')
    patch_names = {n for k in ['patch', 'test_patch'] for n, _ in patch_blocks(row[k])}
    files = {}
    omissions = []
    seen = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive_raw)) as tar:
        members = tar.getmembers()
        if len(members) > 100000:
            raise ValueError('archive member cap')
        roots = {safe_path(m.name.rstrip('/')).parts[0] for m in members}
        if len(roots) != 1:
            raise ValueError('archive must have one root')
        for m in members:
            parts = safe_path(m.name.rstrip('/')).parts[1:]
            if not parts:
                continue
            name = '/'.join(parts)
            if name in seen:
                raise ValueError('duplicate archive identity')
            seen.add(name)
            if m.isdir():
                continue
            if not m.isfile():
                if name in patch_names or row['repo'] in {'yt-dlp/yt-dlp', 'tensorflow/models'}:
                    raise ValueError('required or unsupported nonregular source member')
                omissions.append({'path': name, 'reason': 'nonregular archive member'})
                continue
            if row['repo'] == 'tensorflow/models':
                prefix = 'research/object_detection/' if row['instance_id'].endswith('-2727') else 'research/astronet/'
                if not (name == 'LICENSE' or name in patch_names or (name.startswith(prefix) and name.endswith(('.py', '.proto', 'LICENSE', 'NOTICE')))):
                    omissions.append({'path': name, 'reason': 'outside declared subsystem'})
                    continue
            if m.size > 5 * 1024 ** 2:
                if name in patch_names or row['repo'] in {'yt-dlp/yt-dlp', 'tensorflow/models'}:
                    raise ValueError('required source file cap')
                omissions.append({'path': name, 'reason': 'unmodified asset exceeds5MiB', 'bytes': m.size})
                continue
            total += m.size
            if total > max_total:
                raise ValueError('selected source byte cap')
            with tar.extractfile(m) as f:
                raw = f.read(m.size + 1)
            if len(raw) != m.size:
                raise ValueError('member size differs')
            files[name] = raw
    return (files, omissions)

def derive_roles(originals, row):
    """Same test patch; gold additionally gets code patch. / 同测试补丁，gold额外应用代码补丁。"""
    roles = {}
    for role, kinds in [('base_tests', ['test_patch']), ('fixed_tests', ['patch', 'test_patch'])]:
        files = dict(originals)
        for kind in kinds:
            for name, block in patch_blocks(row[kind]):
                header = block.split('\n@@ ', 1)[0]
                is_new = bool(re.search(r'^new file mode [0-7]+$', header, re.M))
                if is_new == (name in files):
                    raise ValueError('patch old/new file existence differs')
                files[name] = apply_patch(files.get(name, b'').decode('utf-8'), block).encode('utf-8')
        roles[role] = files
    return roles

def index(files):
    return [{'path': n, 'sha256': digest(b), 'bytes': len(b)} for n, b in sorted(files.items())]

def prepare(csv_path, cache, task_id, output, sources_path=SOURCES):
    """Create two immutable roles outside Git; no import/install/run. / Git外生成角色，不导入安装或运行。"""
    pins = json.loads(sources_path.read_bytes())
    pin = [r for r in pins['tasks'] if r['instance_id'] == task_id]
    if len(pin) != 1:
        raise ValueError('outside fixed known panel')
    pin = pin[0]
    row = task_row(csv_path, task_id)
    if row['repo'] != pin['repo'] or row['base_commit'] != pin['base_commit']:
        raise ValueError('fixed repository/base differs')
    if output.is_symlink():
        raise ValueError('output symlink refused')
    output = output.resolve()
    if any(((p / '.git').exists() for p in [output, *output.parents])):
        raise ValueError('source inputs must stay outside Git trees')
    if output.exists():
        raise FileExistsError('immutable output already exists')
    originals, omissions = archive_files(cache.joinpath(*safe_path(pin['archive']).parts), pin['archive_sha256'], row)
    roles = derive_roles(originals, row)
    output.mkdir(parents=True, mode=0o700)
    records = []
    for role, files in roles.items():
        root = output / role
        root.mkdir(mode=0o700)
        for name, raw in files.items():
            target = root.joinpath(*safe_path(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as f:
                f.write(raw)
            target.chmod(0o444)
        for p in sorted(root.rglob('*'), reverse=True):
            if p.is_dir():
                p.chmod(0o555)
        root.chmod(0o555)
        rows = index(files)
        records.append({'role': role, 'source_files': rows, 'source_files_index_sha256': digest(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode())})
    result = {'schema_version': 1, 'instance_id': task_id, 'base_commit': row['base_commit'], 'source_archive_sha256': pin['archive_sha256'], 'dataset_sha256': DATASET_SHA256, 'code_patch_sha256': digest(row['patch'].encode()), 'test_patch_sha256': digest(row['test_patch'].encode()), 'F2P': row['F2P'], 'P2P': row['P2P'], 'roles': records, 'omissions': omissions, 'upstream_executed': False, 'scope': 'fixed known development tasks; source preparation only'}
    with (output / 'manifest.json').open('x') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    return result

def main():
    p = argparse.ArgumentParser(description='Prepare fixed source roles / 准备固定源码角色')
    p.add_argument('--csv', type=Path, required=True, help='fixed dataset CSV / 固定数据集')
    p.add_argument('--cache', type=Path, required=True, help='verified archive cache / 已核验源码缓存')
    p.add_argument('--task', required=True, help='exact known instance_id / 精确已知任务ID')
    p.add_argument('--output', type=Path, required=True, help='new directory outside Git / Git外新目录')
    a = p.parse_args()
    try:
        r = prepare(a.csv, a.cache, a.task, a.output)
    except (ValueError, OSError, UnicodeError, csv.Error) as error:
        p.exit(2, 'Source preparation failed / 源码准备失败: ' + str(error) + '\n')
    print(json.dumps({'instance_id': r['instance_id'], 'roles_prepared': len(r['roles']), 'upstream_executed': False}))
if __name__ == '__main__':
    main()
