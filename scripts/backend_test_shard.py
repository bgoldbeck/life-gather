"""Collection and execution inside the isolated Linux test image."""

import argparse
import contextlib
import io
import json
import os
import time
from collections import Counter
from pathlib import Path

import pytest


def collect(root: Path) -> dict:
    files = Counter()

    class Collection:
        def pytest_collection_finish(self, session):
            for item in session.items:
                files[Path(item.path).relative_to(root).as_posix()] += 1

    with contextlib.redirect_stdout(io.StringIO()) as output:
        code = pytest.main(["--collect-only", "-q"], plugins=[Collection()])
    if code != 0:
        raise RuntimeError("Collection failed:\n" + output.getvalue())
    return {
        "files": [{"path": p, "count": n} for p, n in sorted(files.items())],
        "total": sum(files.values()),
    }


def run_selection(selection: dict, root: Path) -> int:
    files = selection["files"]
    expected = selection["expected"]

    class Progress:
        done = 0
        updated = 0.0

        def pytest_collection_finish(self, session):
            selected = {
                Path(item.path).relative_to(root).as_posix() for item in session.items
            }
            if len(session.items) != expected or selected != set(files):
                raise pytest.UsageError(
                    "Shard collection differs from the complete-suite manifest"
                )

        def pytest_runtest_logreport(self, report):
            if report.when == "teardown":
                self.done += 1
                now = time.monotonic()
                if now - self.updated >= 15 or self.done == expected:
                    print(
                        f"\n[progress] {self.done}/{expected} tests finished",
                        flush=True,
                    )
                    self.updated = now

    previous = Path.cwd()
    os.chdir(root)
    try:
        return int(
            pytest.main(
                [
                    "-q",
                    "--durations=25",
                    "-o",
                    "cache_dir="
                    + str(
                        root / ".pytest-cache"
                        if os.name == "nt"
                        else Path("/tmp/pytest-cache")
                    ),
                    "--junitxml="
                    + str(
                        root / "results.xml"
                        if os.name == "nt"
                        else Path("/tmp/results.xml")
                    ),
                    *files,
                ],
                plugins=[Progress()],
            )
        )
    finally:
        os.chdir(previous)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--selection")
    args = parser.parse_args()
    if args.collect:
        print(json.dumps(collect(Path.cwd())))
    else:
        raise SystemExit(run_selection(json.loads(args.selection), Path.cwd()))
