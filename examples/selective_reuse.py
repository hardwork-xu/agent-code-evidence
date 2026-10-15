"""Offline source-evidence replay / 离线源码证据复用，不执行被分析代码。"""
import hashlib
import json
from contextproof.reuse import GraphSession

source = 'def answer():\n    return 42\n'
anchor = {'id': 'example-answer', 'path': 'main.py', 'symbol': 'answer',
          'kind': 'function', 'start_line': 1, 'end_line': 2, 'text': source,
          'text_sha256': hashlib.sha256(source.encode()).hexdigest()}
session = GraphSession([anchor])
first = session.update({'main.py': source, 'other.py': 'N = 1\n'}, 'revision-a')
second = session.update({'main.py': source, 'other.py': 'N = 2\n'}, 'revision-b')
third = session.update({'main.py': source.replace('42', '43'), 'other.py': 'N = 2\n'},
                       'revision-c')
print(json.dumps({'说明 / note': 'Static evidence only; 不证明程序语义',
                  'initial_rebuilt': first.rebuilt, 'unrelated_edit_reused': second.reused,
                  'relevant_edit_rebuilt': third.rebuilt}, ensure_ascii=False, indent=2))
