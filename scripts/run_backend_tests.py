"""Full backend verification in bounded Linux shards; stdlib host dependencies."""

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LABEL = "lifegather.test-run"


def allocate(files: list[dict], workers: int) -> list[dict]:
    if not files or not 1 <= workers <= 8:
        raise ValueError("Need a nonempty collection and 1-8 workers")
    paths = [f["path"] for f in files]
    if (
        len(set(paths)) != len(paths)
        or any(
            not p.startswith("tests/") or ".." in PurePosixPath(p).parts or "\\" in p
            for p in paths
        )
        or any(not isinstance(f["count"], int) or f["count"] < 1 for f in files)
    ):
        raise ValueError("Unsafe, duplicate or empty test file")
    groups = [{"files": [], "expected": 0} for _ in range(min(workers, len(files)))]
    for item in sorted(files, key=lambda f: (-f["count"], f["path"])):
        group = min(enumerate(groups), key=lambda g: (g[1]["expected"], g[0]))[1]
        group["files"].append(item["path"])
        group["expected"] += item["count"]
    for group in groups:
        group["files"].sort()
    return groups


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode:
        # Do not include argv: database credentials are passed in environment args.
        raise RuntimeError(f"Docker {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


class Resources:
    def __init__(self, command=docker):
        self.command = command
        self.containers = []
        self.networks = []
        self.waiters = []
        self.cleanup_success = True

    def __enter__(self):
        return self

    def container(self, *args: str) -> str:
        identifier = self.command("create", *args)
        self.containers.append(identifier)
        self.command("start", identifier)
        return identifier

    def __exit__(self, *_):
        for waiter in self.waiters:
            if waiter.poll() is None:
                waiter.terminate()
                try:
                    waiter.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    waiter.kill()
        commands = []
        if self.containers:
            commands.append(("rm", "--force", "--volumes", *self.containers))
        commands.extend(("network", "rm", network) for network in self.networks)
        for command in commands:
            try:
                self.command(*command)
            except RuntimeError as error:
                self.cleanup_success = False
                print(f"Cleanup failed: {error}", file=sys.stderr)


def fingerprint() -> str:
    paths = [
        ROOT / name
        for name in [
            "README.md",
            "backend/pyproject.toml",
            "backend/uv.lock",
            "backend/Dockerfile.tests",
            "backend/Dockerfile.tests.dockerignore",
            "scripts/backend_test_shard.py",
            "deploy/cloudflare/container-settings.json",
        ]
    ]
    for name in ["backend/src", "backend/tests"]:
        paths.extend(
            p
            for p in (ROOT / name).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and ".pytest_cache" not in p.parts
            and p.suffix != ".pyc"
        )
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def cached_image(image: str, source: str, command=docker) -> str | None:
    raw = command("image", "inspect", image, check=False)
    if not raw:
        return None
    rows = json.loads(raw)
    if not rows:
        return None
    metadata = rows[0]
    if (metadata["Config"].get("Labels") or {}).get("lifegather.test-inputs") == source:
        return metadata["Id"]
    return None


def run(workers: int, output: Path) -> None:
    started = time.monotonic()
    source = fingerprint()
    image = "lifegather-backend-tests:inputs-" + source[:16]
    output.mkdir(parents=True, exist_ok=True)
    print(
        f"Building cached Linux backend test image ({workers} isolated shards)...",
        flush=True,
    )
    image_id = cached_image(image, source)
    if image_id:
        print(
            "Reusing the local test image with matching input fingerprint.", flush=True
        )
    else:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--load",
                "--progress=plain",
                "--platform",
                "linux/amd64",
                "--build-arg",
                "TEST_INPUTS=" + source,
                "-f",
                "backend/Dockerfile.tests",
                "-t",
                image,
                ".",
            ],
            cwd=ROOT,
        )
        if result.returncode:
            raise RuntimeError("Linux test image build failed")
    if fingerprint() != source:
        raise RuntimeError("Test inputs changed during image build; retry")
    image_id = cached_image(image, source)
    if image_id is None:
        raise RuntimeError("Test image input label mismatch; release stopped")
    collection = json.loads(
        docker("run", "--rm", "--network", "none", image_id, "--collect")
    )
    groups = allocate(collection["files"], workers)
    if sum(g["expected"] for g in groups) != collection["total"]:
        raise RuntimeError("Incomplete collection allocation")
    manifest = {
        "status": "running",
        "input_sha256": source,
        "image_id": image_id,
        "total": collection["total"],
        "shards": groups,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        f"Collected {collection['total']} tests; whole files assigned once "
        f"across {len(groups)} shards.",
        flush=True,
    )
    suffix = secrets.token_hex(5)
    with Resources() as owned:
        running = {}
        try:
            for index, group in enumerate(groups):
                prefix = f"lifegather-tests-{suffix}-{index}"
                network, database, tests = (
                    prefix + "-net",
                    prefix + "-db",
                    prefix + "-tests",
                )
                password = secrets.token_hex(16)
                docker(
                    "network",
                    "create",
                    "--internal",
                    "--label",
                    f"{LABEL}={suffix}",
                    network,
                )
                owned.networks.append(network)
                owned.container(
                    "--pull=never",
                    "--name",
                    database,
                    "--network",
                    network,
                    "--network-alias",
                    "db",
                    "--label",
                    f"{LABEL}={suffix}",
                    "--env",
                    f"POSTGRES_PASSWORD={password}",
                    "--env",
                    "POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=C",
                    "pgvector/pgvector:pg17",
                )
                for _ in range(45):
                    ready = subprocess.run(
                        [
                            "docker",
                            "exec",
                            database,
                            "pg_isready",
                            "-h",
                            "127.0.0.1",
                            "-U",
                            "postgres",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if ready.returncode == 0:
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError(f"Shard {index + 1} PostgreSQL did not start")
                owned.container(
                    "--pull=never",
                    "--name",
                    tests,
                    "--network",
                    network,
                    "--label",
                    f"{LABEL}={suffix}",
                    "--env",
                    f"LIFEGATHER_TEST_DATABASE_URL=postgresql://postgres:{password}@db:5432/postgres",
                    image_id,
                    "--selection",
                    json.dumps(group),
                )
                waiter = subprocess.Popen(
                    ["docker", "wait", tests],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                owned.waiters.append(waiter)
                running[index] = (tests, waiter)
                print(
                    f"Shard {index + 1}: started {group['expected']} tests "
                    "on its own PostgreSQL server",
                    flush=True,
                )
            updated = 0.0
            while running:
                for index, (tests, waiter) in list(running.items()):
                    if waiter.poll() is None:
                        continue
                    stdout, _ = waiter.communicate()
                    logs = subprocess.run(
                        ["docker", "logs", tests],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    (output / f"shard-{index + 1}.log").write_text(
                        logs.stdout + logs.stderr, encoding="utf-8"
                    )
                    docker(
                        "cp",
                        f"{tests}:/tmp/results.xml",
                        str(output / f"shard-{index + 1}.xml"),
                        check=False,
                    )
                    if waiter.returncode != 0 or stdout.strip() != "0":
                        print(logs.stdout + logs.stderr, flush=True)
                        raise RuntimeError(
                            f"Shard {index + 1} failed; release stopped. Logs: {output}"
                        )
                    groups[index]["status"] = "passed"
                    print(
                        f"Shard {index + 1}: PASSED "
                        f"({groups[index]['expected']} tests); "
                        f"slow-test report: {output / f'shard-{index + 1}.log'}",
                        flush=True,
                    )
                    del running[index]
                now = time.monotonic()
                if now - updated >= 15:
                    for index, (tests, _) in running.items():
                        tail = docker(
                            "logs", "--tail", "2", tests, check=False
                        ).replace("\n", " ")[-220:]
                        print(
                            f"[{now - started:.0f}s] Shard {index + 1} running: {tail}",
                            flush=True,
                        )
                    updated = now
                if running:
                    time.sleep(1)
            if fingerprint() != source:
                raise RuntimeError("Test inputs changed during verification; retry")
            manifest["status"] = "passed"
        except BaseException:
            manifest["status"] = "failed_or_canceled"
            # Preserve partial logs before the owned containers are removed.
            for index, (tests, _) in running.items():
                logs = subprocess.run(
                    ["docker", "logs", tests],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                (output / f"shard-{index + 1}.log").write_text(
                    logs.stdout + logs.stderr, encoding="utf-8"
                )
            raise
        finally:
            manifest["elapsed_seconds"] = round(time.monotonic() - started, 2)
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not owned.cleanup_success:
        manifest["status"] = "cleanup_failed"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        raise RuntimeError("Tests passed but cleanup failed; release stopped")
    print(
        f"PASS: all {collection['total']} tests in "
        f"{manifest['elapsed_seconds']}s. Manifest/logs: {output}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "test-results" / (
        "backend-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    )
    try:
        run(args.workers, output.resolve())
    except KeyboardInterrupt:
        print(
            "Canceled: owned test environments removed; release stopped.",
            file=sys.stderr,
        )
        raise SystemExit(130) from None
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
