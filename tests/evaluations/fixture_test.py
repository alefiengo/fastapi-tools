"""Guard against an evaluator demanding context its model never receives."""

import ast
import gc
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
import warnings


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "evals" / "test-writer-behavior"


class SuppliedFixtureTests(unittest.TestCase):
    def test_prompt_supplies_every_versioned_fixture_without_drift(self):
        prompt = (CASE / "prompt.md").read_text()
        sections = re.findall(
            r"### Fixture: (fixtures/[^\n]+)\n\n```[^\n]*\n(.*?)\n```",
            prompt,
            re.DOTALL,
        )
        self.assertEqual(len(sections), len(dict(sections)), "duplicate context file")
        supplied = dict(sections)
        actual = {
            f"fixtures/{file.name}": file.read_text().rstrip()
            for file in (CASE / "fixtures").iterdir()
            if file.is_file()
        }
        self.assertTrue(actual, "the grader cannot demand nonexistent fixtures")
        self.assertEqual(supplied, actual, "regenerate prompt context after changing fixtures")

    def test_persistence_failure_is_after_write_and_has_real_constraint(self):
        source = (CASE / "fixtures" / "order_service.py").read_text()
        self.assertLess(source.index("UPDATE orders"), source.index("INSERT INTO events"))
        schema = (CASE / "fixtures" / "schema.sql").read_text()
        self.assertIn("CHECK (event_id <> 'FAIL_DB')", schema)
        self.assertIn("VALUES (101, 'alice', 'PENDING')", schema)
        prompt = (CASE / "prompt.md").read_text()
        self.assertIn("separate transaction", prompt)
        self.assertIn("deliberately not supplied", prompt)

    def test_expected_error_is_the_full_existing_contract(self):
        error = json.loads((CASE / "fixtures" / "ownership-error.json").read_text())
        self.assertEqual(error, {
            "status": 403,
            "code": "ORDER_ACCESS_DENIED",
            "message": "You cannot access this order",
            "path": "/orders/101/approve",
        })
        self.assertEqual(len([p for p in (CASE / "graders").glob("*.md")
                              if p.read_text().startswith("---\ntype: llm\n---")]), 5)

    def test_fixtures_close_every_sqlite_connection(self):
        # sqlite3's context manager commits or rolls back but never closes;
        # Python 3.13+ reports the leaked connection as a ResourceWarning.
        for name in ("fixture_data.py", "order_service.py"):
            tree = ast.parse((CASE / "fixtures" / name).read_text())
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            connects = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute) and node.func.attr == "connect"]
            self.assertTrue(connects, name)
            for call in connects:
                wrapper = parents.get(call)
                with self.subTest(fixture=name, line=call.lineno):
                    self.assertTrue(isinstance(wrapper, ast.Call) and getattr(wrapper.func, "id", None) == "closing",
                                    "wrap sqlite3.connect in contextlib.closing")

    def test_fixtures_keep_rollback_ownership_and_success_semantics(self):
        def load(name):
            spec = importlib.util.spec_from_file_location(name, CASE / "fixtures" / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        data, service = load("fixture_data"), load("order_service")
        with tempfile.TemporaryDirectory() as directory, warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            database = str(Path(directory) / "orders.db")
            data.seed(database)
            orders = service.OrderService(database)
            with self.assertRaises(LookupError):
                orders.approve(999, "alice", "e0")
            with self.assertRaises(service.OrderAccessDenied):
                orders.approve(101, "mallory", "e0")
            with self.assertRaises(sqlite3.IntegrityError):
                orders.approve(101, "alice", "FAIL_DB")
            self.assertEqual(data.status(database), "PENDING")
            orders.approve(101, "alice", "e1")
            self.assertEqual(data.status(database), "APPROVED")
            gc.collect()
        self.assertEqual([str(w.message) for w in caught if issubclass(w.category, ResourceWarning)], [])


if __name__ == "__main__":
    unittest.main()
