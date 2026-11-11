#!/usr/bin/env python3
"""Offline checks for Python code blocks shipped in skills/*/SKILL.md.

Blocks are parsed, never imported or executed. When `ruff` is on PATH, each
block is also linted in isolation with a fixed rule selection so that results
do not depend on a Ruff release's default rules. Without Ruff the lint test is
skipped with a visible notice; this suite never installs anything.
"""
import ast
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
FENCE = re.compile(r'^```python[ \t]*\n(.*?)^```[ \t]*$', re.MULTILINE | re.DOTALL)
# Ruff's long-standing default selection: syntax, statement and pyflakes errors.
RUFF_RULES = 'E4,E7,E9,F'


def python_blocks():
    blocks = []
    for skill in sorted((ROOT / 'skills').glob('*/SKILL.md')):
        text = skill.read_text(encoding='utf-8')
        for match in FENCE.finditer(text):
            line = text.count('\n', 0, match.start(1)) + 1
            blocks.append((f'{skill.relative_to(ROOT)}:{line}', match.group(1)))
    return blocks


class SkillSnippetTests(unittest.TestCase):
    def test_extractor_finds_known_blocks(self):
        names = {name.split(':')[0] for name, _ in python_blocks()}
        self.assertIn('skills/fastapi-codegen/SKILL.md', names)
        self.assertIn('skills/fastapi-testing/SKILL.md', names)

    def test_blocks_parse(self):
        for name, source in python_blocks():
            with self.subTest(block=name):
                ast.parse(source, filename=name)

    def test_blocks_pass_ruff(self):
        ruff = shutil.which('ruff')
        if ruff is None:
            print('NOTICE: ruff not on PATH; skill snippet lint skipped', file=sys.stderr)
            self.skipTest('ruff not on PATH')
        for name, source in python_blocks():
            with self.subTest(block=name):
                result = subprocess.run(
                    [ruff, 'check', '--isolated', '--no-cache', '--select', RUFF_RULES,
                     '--output-format', 'concise', '--stdin-filename', 'snippet.py', '-'],
                    input=source, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, f'{name}\n{result.stdout}{result.stderr}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
