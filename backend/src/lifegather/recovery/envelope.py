"""Versioned authenticated streaming envelope for operator recovery bundles."""

import os
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives.ciphers import (
    Cipher,
    algorithms,
    modes,
)
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

MAGIC = b"LIFEGATHER-RECOVERY\x00\x01"
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
HEADER_BYTES = len(MAGIC) + SALT_BYTES + NONCE_BYTES
CHUNK_BYTES = 1024 * 1024
# NIST SP 800-38D section 5.2.1.1: 2^39 - 256 bits per GCM invocation.
MAX_PLAINTEXT_BYTES = (1 << 36) - 32


class RecoveryError(ValueError):
    """A safe explanation without source content, passphrases or secret values."""


def _key(password: bytes, salt: bytes) -> bytes:
    if not isinstance(password, bytes) or not 12 <= len(password) <= 1024:
        raise RecoveryError("Use a passphrase containing 12 to 1024 UTF-8 bytes")
    # Parameters are part of version 1, not values supplied by an input file.
    try:
        return Argon2id(
            salt=salt, length=32, iterations=3, lanes=1, memory_cost=65536
        ).derive(password)
    except (UnsupportedAlgorithm, MemoryError):
        raise RecoveryError("This runtime cannot derive the recovery key") from None


def _write(output: BinaryIO, data: bytes) -> None:
    if output.write(data) != len(data):
        raise RecoveryError("Unable to write the complete recovery bundle")


def encrypt_file(source: Path, output: BinaryIO, password: bytes) -> None:
    """Encrypt a private staged archive into an already exclusive output file."""
    with source.open("rb") as raw:
        if os.fstat(raw.fileno()).st_size > MAX_PLAINTEXT_BYTES:
            raise RecoveryError("Recovery payload exceeds the format size limit")
        salt = os.urandom(SALT_BYTES)
        nonce = os.urandom(NONCE_BYTES)
        header = MAGIC + salt + nonce
        cipher = Cipher(
            algorithms.AES256(_key(password, salt)), modes.GCM(nonce)
        ).encryptor()
        cipher.authenticate_additional_data(header)
        _write(output, header)
        count = 0
        while block := raw.read(CHUNK_BYTES):
            count += len(block)
            if count > MAX_PLAINTEXT_BYTES:
                raise RecoveryError("Recovery payload exceeds the format size limit")
            _write(output, cipher.update(block))
    _write(output, cipher.finalize())
    _write(output, cipher.tag)


def decrypt_file(source: Path, destination: Path, password: bytes) -> None:
    """Authenticate into a new private staging file; failures remove only that file.

    Callers must not parse or publish plaintext until this function returns.
    The staging directory must be private. Existing destinations are never removed.
    """
    if not source.is_file():
        raise RecoveryError("Choose a regular recovery bundle file")
    with source.open("rb") as encrypted:
        size = os.fstat(encrypted.fileno()).st_size
        header = encrypted.read(HEADER_BYTES)
        if size < HEADER_BYTES + TAG_BYTES or len(header) != HEADER_BYTES:
            raise RecoveryError("Recovery bundle is incomplete")
        if size - HEADER_BYTES - TAG_BYTES > MAX_PLAINTEXT_BYTES:
            raise RecoveryError("Recovery payload exceeds the format size limit")
        if not header.startswith(MAGIC):
            raise RecoveryError("Unsupported recovery bundle format")
        salt = header[len(MAGIC) : len(MAGIC) + SALT_BYTES]
        nonce = header[-NONCE_BYTES:]
        encrypted.seek(size - TAG_BYTES)
        tag = encrypted.read(TAG_BYTES)
        if len(tag) != TAG_BYTES:
            raise RecoveryError("Recovery bundle is incomplete")
        cipher = Cipher(
            algorithms.AES256(_key(password, salt)), modes.GCM(nonce, tag)
        ).decryptor()
        cipher.authenticate_additional_data(header)
        encrypted.seek(HEADER_BYTES)
        descriptor = os.open(
            destination,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as output:
                remaining = size - HEADER_BYTES - TAG_BYTES
                while remaining:
                    block = encrypted.read(min(CHUNK_BYTES, remaining))
                    if not block:
                        raise RecoveryError("Recovery bundle is incomplete")
                    remaining -= len(block)
                    _write(output, cipher.update(block))
                try:
                    _write(output, cipher.finalize())
                except InvalidTag:
                    raise RecoveryError(
                        "Incorrect passphrase or damaged recovery bundle"
                    ) from None
                if os.fstat(encrypted.fileno()).st_size != size:
                    raise RecoveryError("Recovery bundle changed while reading")
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
