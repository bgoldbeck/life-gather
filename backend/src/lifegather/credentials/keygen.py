"""Generate a new vault key without printing or overwriting it."""

import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def generate(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(AESGCM.generate_key(bit_length=256))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m lifegather.credentials.keygen OUTPUT_PATH")
    generate(Path(sys.argv[1]))
    print("Created key file. Back it up securely; never overwrite an in-use key.")
