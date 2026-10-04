"""Execute only reviewed upstream function bodies in a restricted child process."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import resource
import sys
import warnings


def find_function(source: str, symbol: str) -> ast.FunctionDef:
    nodes = ast.parse(source).body
    for part in symbol.split('.'):
        matches = [n for n in nodes if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                   and n.name == part]
        if len(matches) != 1:
            raise ValueError(f'nonunique upstream test: {symbol}')
        target = matches[0]
        nodes = target.body
    if not isinstance(target, ast.FunctionDef):
        raise ValueError('test must be a function')
    return target


def compile_function(source: str, symbol: str, filename: str):
    """Keep the upstream compiler flags; never inherit this worker's futures."""
    tree = ast.parse(source)
    test = copy.deepcopy(find_function(source, symbol))
    test.decorator_list = []
    futures = [copy.deepcopy(node) for node in tree.body
               if isinstance(node, ast.ImportFrom) and node.module == '__future__']
    module = ast.fix_missing_locations(ast.Module(body=[*futures, test], type_ignores=[]))
    return compile(module, filename, 'exec', dont_inherit=True), test.name


def run(payload: dict) -> dict:
    root = Path(payload['root']).resolve()
    source_root = root / 'src'
    sys.path.insert(0, str(source_root))
    case = payload['case']
    test_path = Path(payload['test_root']) / case['test_path']
    code, test_name = compile_function(test_path.read_text(), case['test_symbol'], str(test_path))
    namespace = {'__name__': 'task_evidence_case'}
    repo = case['repository']
    if repo == 'packaging':
        import packaging
        from packaging import metadata
        from packaging.specifiers import Specifier, SpecifierSet
        module = packaging
        namespace.update(metadata=metadata, Specifier=Specifier, SpecifierSet=SpecifierSet)
    elif repo == 'attrs':
        import attr
        module = attr
        namespace['attr'] = attr
    elif repo == 'pluggy':
        import pluggy
        module = pluggy
        namespace.update(PluginManager=pluggy.PluginManager,
                         hookspec=pluggy.HookspecMarker('example'))
    else:
        raise ValueError('unreviewed repository')
    if not Path(module.__file__).resolve().is_relative_to(source_root):
        raise ValueError('import did not resolve to verified upstream snapshot')
    exec(code, namespace)
    fn = namespace[test_name]
    trace_enabled = payload.get('trace_enabled', True)
    if type(trace_enabled) is not bool:
        raise ValueError('trace_enabled must be a boolean')
    rows = []
    for invocation in case['invocations']:
        kwargs = dict(invocation.get('kwargs', {}))
        if case['test_symbol'].count('.'):
            kwargs['self'] = None
        if invocation.get('fixture') == 'pm':
            kwargs['pm'] = namespace['PluginManager']('example')
        if 'validation_disabled' in invocation:
            namespace['attr'].validators.set_disabled(invocation['validation_disabled'])
        lines: set[tuple[str, int]] = set()
        generated: set[tuple[str, int]] = set()

        def trace(frame, event, arg):
            filename = frame.f_code.co_filename
            if event == 'line':
                if filename.startswith(str(source_root) + '/'):
                    lines.add((str(Path(filename).relative_to(root)), frame.f_lineno))
                elif filename.startswith('<attrs generated '):
                    # Names identify generated methods, never local absolute paths.
                    generated.add((filename, frame.f_lineno))
            return trace

        failure = None
        if trace_enabled:
            sys.settrace(trace)
        try:
            fn(**kwargs)
        except BaseException as exc:
            failure = {'type': type(exc).__name__, 'message': str(exc).replace(str(root), '<source>')}
        finally:
            sys.settrace(None)
            if 'validation_disabled' in invocation:
                namespace['attr'].validators.set_disabled(False)
        rows.append({'invocation': invocation, 'passed': failure is None, 'failure': failure,
                     'lines': [list(x) for x in sorted(lines)],
                     'generated_lines': [list(x) for x in sorted(generated)]})
    return {'case_id': case['id'], 'trace_enabled': trace_enabled,
            'invocations': rows, 'passed': all(r['passed'] for r in rows)}


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    warnings.simplefilter('ignore')
    try:
        result = run(json.loads(Path(sys.argv[1]).read_text()))
    except BaseException as exc:
        result = {'harness_error': type(exc).__name__, 'message': str(exc)}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
