"""Disposable local document parser process with no inherited application secrets."""

import sys


def worker() -> None:
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    from lifegather.documents.formats import PreviewOptions, parse_document

    raw = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
    result = parse_document(
        raw, sys.argv[1], PreviewOptions.model_validate_json(sys.argv[2])
    )
    sys.stdout.buffer.write(result.model_dump_json().encode())


if __name__ == "__main__":
    try:
        worker()
    except Exception:
        sys.exit(1)
