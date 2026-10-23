import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


class BackendRunnerTest(unittest.TestCase):
    def runner(self):
        import run_backend_tests

        return run_backend_tests

    def test_allocation_is_complete_disjoint_balanced_and_deterministic(self):
        files = [
            {"path": f"tests/test_{i}.py", "count": n}
            for i, n in enumerate([12, 7, 6, 4, 3, 1])
        ]
        groups = self.runner().allocate(files, 4)
        self.assertEqual(groups, self.runner().allocate(list(reversed(files)), 4))
        selected = [p for group in groups for p in group["files"]]
        self.assertEqual(sorted(selected), sorted(f["path"] for f in files))
        self.assertEqual(sum(g["expected"] for g in groups), 33)
        self.assertEqual(len(selected), len(set(selected)))

    def test_empty_duplicate_or_unsafe_collection_is_refused(self):
        for files in [
            [],
            [{"path": "../other.py", "count": 1}],
            [{"path": "tests/a.py", "count": 1}] * 2,
        ]:
            with self.subTest(files=files), self.assertRaises(ValueError):
                self.runner().allocate(files, 4)

    def test_exception_cleans_only_invocation_resources(self):
        calls = []

        def command(*args, **kwargs):
            calls.append(args)
            return ""

        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            with self.runner().Resources(command) as owned:
                owned.containers.extend(["owned-test", "owned-db"])
                owned.networks.append("owned-net")
                raise RuntimeError("synthetic failure")
        self.assertEqual(
            calls,
            [
                ("rm", "--force", "--volumes", "owned-test", "owned-db"),
                ("network", "rm", "owned-net"),
            ],
        )

    def test_failed_shard_or_wrong_count_never_reports_success(self):
        spec = importlib.util.spec_from_file_location(
            "backend_test_shard", SCRIPTS / "backend_test_shard.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/test_example.py").write_text(
                "def test_failure():\n assert False\n"
            )
            self.assertNotEqual(
                module.run_selection(
                    {"files": ["tests/test_example.py"], "expected": 1}, root
                ),
                0,
            )
            (root / "tests/test_example.py").write_text(
                "def test_unexpected():\n raise RuntimeError('must not run')\n"
            )
            self.assertNotEqual(
                module.run_selection(
                    {"files": ["tests/test_example.py"], "expected": 2}, root
                ),
                0,
            )

    def test_cancellation_cleans_resources(self):
        calls = []

        def command(*args, **kwargs):
            calls.append(args)

        with self.assertRaises(KeyboardInterrupt):
            with self.runner().Resources(command) as owned:
                owned.containers.append("canceled-test")
                raise KeyboardInterrupt
        self.assertEqual(calls, [("rm", "--force", "--volumes", "canceled-test")])

    def test_cleanup_failure_is_recorded_and_other_cleanup_continues(self):
        calls = []

        def command(*args, **kwargs):
            calls.append(args)
            if args[0] == "rm":
                raise RuntimeError("synthetic cleanup failure")

        with self.runner().Resources(command) as owned:
            owned.containers.append("owned-test")
            owned.networks.append("owned-net")
        self.assertFalse(owned.cleanup_success)
        self.assertEqual(calls[-1], ("network", "rm", "owned-net"))

    def test_image_reuse_requires_the_complete_matching_input_fingerprint(self):
        def command(*args, **kwargs):
            return json.dumps(
                [
                    {
                        "Id": "frozen-image-id",
                        "Config": {
                            "Labels": {"lifegather.test-inputs": "exact-inputs"}
                        },
                    }
                ]
            )

        self.assertEqual(
            self.runner().cached_image("image", "exact-inputs", command),
            "frozen-image-id",
        )
        self.assertIsNone(
            self.runner().cached_image("image", "changed-inputs", command)
        )


class MissingImageTest(unittest.TestCase):
    def test_progress_uses_each_shards_own_count(self):
        import run_backend_tests as runner

        original = runner.Resources

        def command(*args, **kwargs):
            if "--collect" in args:
                return json.dumps(
                    {
                        "files": [
                            {"path": "tests/a.py", "count": 2},
                            {"path": "tests/b.py", "count": 1},
                        ],
                        "total": 3,
                    }
                )
            if args[0] == "create":
                return "created-id"
            return ""

        waiter = SimpleNamespace(
            poll=lambda: 0, communicate=lambda: ("0", ""), returncode=0
        )
        result = SimpleNamespace(returncode=0, stdout="log", stderr="")
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            with (
                patch.object(runner, "fingerprint", return_value="fixed"),
                patch.object(runner, "cached_image", return_value="image-id"),
                patch.object(runner, "docker", side_effect=command),
                patch.object(
                    runner, "Resources", side_effect=lambda: original(command)
                ),
                patch.object(runner.subprocess, "run", return_value=result),
                patch.object(runner.subprocess, "Popen", return_value=waiter),
            ):
                runner.run(2, Path(directory))
        self.assertIn("Shard 1: PASSED (2 tests)", output.getvalue())
        self.assertIn("Shard 2: PASSED (1 tests)", output.getvalue())

    def test_failed_start_cleans_the_newly_created_container(self):
        import run_backend_tests as runner

        removed = []

        def command(*args, **kwargs):
            if args[0] == "create":
                return "newly-created-id"
            if args[0] == "start":
                raise RuntimeError("synthetic start failure")
            if args[0] == "rm":
                removed.extend(args[3:])
            return ""

        with self.assertRaisesRegex(RuntimeError, "start failure"):
            with runner.Resources(command) as owned:
                owned.container("--name", "requested-name", "image")
        self.assertEqual(removed, ["newly-created-id"])

    def test_missing_image_is_a_cache_miss(self):
        import run_backend_tests

        for response in ("", "[]"):
            self.assertIsNone(
                run_backend_tests.cached_image(
                    "image", "inputs", lambda *a, response=response, **k: response
                )
            )

    def test_failed_creation_does_not_remove_an_existing_network(self):
        import run_backend_tests as runner

        original = runner.Resources
        deleted = []

        def command(*args, **kwargs):
            if "--collect" in args:
                return json.dumps(
                    {"files": [{"path": "tests/example.py", "count": 1}], "total": 1}
                )
            if args[:2] == ("network", "create"):
                raise RuntimeError("network name already exists")
            if args[:2] == ("network", "rm"):
                deleted.append(args[-1])
            return ""

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(runner, "fingerprint", return_value="fixed"),
                patch.object(runner, "cached_image", return_value="image-id"),
                patch.object(runner, "docker", side_effect=command),
                patch.object(
                    runner, "Resources", side_effect=lambda: original(command)
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "already exists"):
                    runner.run(1, Path(directory))
        self.assertEqual(deleted, [])


if __name__ == "__main__":
    unittest.main()
