"""Independent historical-alias oracle / 独立既有别名规则参考。"""
from collections import defaultdict
from pathlib import Path
import random

import pytest

from contextproof.catalog import ModuleCatalog
from contextproof.dependencies import _Corpus


def reference(paths):
    result = defaultdict(list)
    for name in sorted(set(paths)):
        p = Path(name)
        if p.suffix.lower() not in {'.py', '.pyi'}:
            continue
        parts = list(p.with_suffix('').parts)
        if parts[-1] == '__init__':
            parts.pop()
        names = {'.'.join(parts)}
        if len(parts) > 1 and parts[0] == 'src':
            names.add('.'.join(parts[1:]))
        for alias in sorted(names - {''}):
            result[alias].append(name)
    return dict(result)


def test_seeded_path_sets_match_historical_lookup_and_namespace_rules():
    rng = random.Random(13014)
    pool = ['src/pkg/a.py', 'pkg/a.py', 'pkg/a.pyi', 'pkg/__init__.py',
            'pkg/a/__init__.py', 'src/pkg/a/b.py', '__init__.py', '.foo.py',
            'readme.txt', 'mixed.PY', 'mixed.PYI', 'src/top.py', 'top.py',
            'a/b.py', 'a/b/c.py', 'a..b.py']
    for _ in range(100):
        paths = [p for p in pool if rng.randrange(2)]
        expected = reference(paths)
        index = ModuleCatalog(paths)
        assert index.mapping() == expected
        queries = set(expected) | {'pkg', 'pkg.a', 'src.pkg', 'not_found', '', 'a', 'a.b'}
        for name in queries:
            assert index.candidates(name) == tuple(expected.get(name, ()))
            assert index.subtree_exists(name) is (name in expected or any(
                alias.startswith(name + '.') for alias in expected))


def test_candidates_include_parse_failures_and_defensive_view():
    index = ModuleCatalog(['src/pkg/a.py', 'pkg/a.pyi'])
    view = index.mapping()
    view['pkg.a'].clear()
    assert index.candidates('pkg.a') == ('pkg/a.pyi', 'src/pkg/a.py')
    with pytest.raises(TypeError):
        index._modules['pkg.a'] = ()
    assert index.matches({('exact', 'missing'): (), ('subtree', 'missing'): False})
    corpus = _Corpus.from_texts({'bad.py': 'not parseable (', 'pkg/a.py': 'pass\n'},
                               _track_catalog=True)
    assert corpus.module_candidates('bad') == ('bad.py',)
    assert 'bad.py' not in corpus.trees
    assert corpus.catalog_queries[('exact', 'bad')] == ('bad.py',)


def test_private_catalog_with_other_paths_is_rejected():
    with pytest.raises(ValueError, match='catalog/source'):
        _Corpus.from_texts({'a.py': 'pass\n'}, _catalog=ModuleCatalog(['b.py']))


def test_negative_exact_and_namespace_answers_are_distinct_inputs():
    index = ModuleCatalog(['pkg/deep/other.py'])
    assert index.candidates('pkg.deep') == ()
    assert index.subtree_exists('pkg.deep') is True
    assert index.matches({('exact', 'pkg.deep'): (), ('subtree', 'pkg.deep'): True})
    empty = ModuleCatalog([])
    assert not empty.matches({('exact', 'pkg.deep'): (), ('subtree', 'pkg.deep'): True})
    changed_sibling = ModuleCatalog(['pkg/deep/different.py'])
    assert changed_sibling.matches({('exact', 'pkg.deep'): (), ('subtree', 'pkg.deep'): True})
    assert not changed_sibling.roots_match(index.root_guards({('subtree', 'pkg.deep'): True}))
