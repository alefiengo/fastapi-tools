"""The evidence inventory must cover the shipped components without efficacy claims."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ComponentInventoryTests(unittest.TestCase):
    def test_complete_inventory_tracks_current_sources_and_existing_evidence(self):
        inventory = json.loads((ROOT / 'docs/component-evidence.json').read_text())
        actual = {p.relative_to(ROOT).as_posix(): p for p in (
            *ROOT.glob('skills/*/SKILL.md'), *ROOT.glob('agents/*.md'))}
        entries = inventory['components']
        self.assertEqual(len(entries), len({e['id'] for e in entries}))
        self.assertEqual({e['path'] for e in entries}, set(actual))
        self.assertEqual(inventory['paidEvaluationsRun'], 0)
        for entry in entries:
            with self.subTest(component=entry['id']):
                path = actual[entry['path']]
                self.assertEqual(entry['sourceSha256'], hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'Refresh evidence after changing the component')
                self.assertTrue(entry['trigger'].strip())
                self.assertEqual(entry['behavioralEvidence']['status'], 'not-measured')
                self.assertEqual(entry['behavioralEvidence']['observedGenerations'], 0)
                self.assertIsNone(entry['behavioralEvidence']['effectSize'])
                for evidence in entry['functionalEvidence']['paths']:
                    self.assertTrue((ROOT / evidence).is_file(), evidence)
                for case in entry['behavioralEvidence']['cases']:
                    self.assertTrue((ROOT / 'evals' / case / 'prompt.md').is_file(), case)
                    self.assertTrue(list((ROOT / 'evals' / case / 'graders').glob('*.md')), case)
        groups = {g['id']: g for g in inventory['redundancyReview']}
        for entry in entries:
            for name in entry['redundancyGroups']:
                self.assertIn(entry['id'], groups[name]['members'])

    def test_roles_preserve_product_tool_boundaries(self):
        for path in ROOT.glob('agents/*.md'):
            header = path.read_text().split('---', 2)[1]
            tools = set(re.search(r'^tools: (.+)$', header, re.M)[1].split(', '))
            expected = {'Read', 'Glob', 'Grep'}
            if path.stem in {'fastapi-architect', 'fastapi-api-designer', 'fastapi-test-writer'}:
                expected |= {'Write', 'Edit'}
            self.assertEqual(tools, expected, path.name)

    def test_every_skill_and_agent_has_separate_activation_criterion(self):
        entries = json.loads((ROOT / 'docs/component-evidence.json').read_text())['components']
        for entry in entries:
            paths = [p for case in entry['behavioralEvidence']['cases']
                     for p in (ROOT / 'evals' / case / 'graders').glob('*.md')]
            self.assertTrue(any('type: tool_used' in p.read_text() and entry['id'] in p.read_text()
                                for p in paths), entry['id'])


if __name__ == '__main__':
    unittest.main()
