"""Regression: pure backend tests must not initialize PostgreSQL."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DatabaseFixturesTest(unittest.TestCase):
    def test_pure_date_tests_never_start_postgresql(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "no_postgres.py"
            plugin.write_text(
                "def pytest_configure(config):\n"
                " import database_support\n"
                " def refuse():\n"
                "  raise AssertionError('Pure tests attempted PostgreSQL setup')\n"
                " database_support.start = refuse\n",
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "PYTHONPATH": directory + os.pathsep + str(ROOT / "backend/tests"),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no_postgres",
                    "tests/test_assistant_maintenance_dates.py",
                ],
                cwd=ROOT / "backend",
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("14 passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
