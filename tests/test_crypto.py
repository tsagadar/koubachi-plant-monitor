"""Tests for AES-128-CBC crypto (encrypt/decrypt round-trip and error cases)."""

import pytest

from custom_components.koubachi.crypto import decrypt, encrypt

KEY = bytes.fromhex("00112233445566778899aabbccddeeff")


def test_round_trip_short():
    plaintext = b"hello=world"
    assert decrypt(KEY, encrypt(KEY, plaintext)) == plaintext


def test_round_trip_empty():
    assert decrypt(KEY, encrypt(KEY, b"")) == b""


def test_round_trip_long():
    plaintext = b"a=1&b=2&c=3" * 10
    assert decrypt(KEY, encrypt(KEY, plaintext)) == plaintext


def test_encrypt_produces_different_ciphertext_each_time():
    # Random IV means two encryptions of the same plaintext differ.
    ct1 = encrypt(KEY, b"same")
    ct2 = encrypt(KEY, b"same")
    assert ct1 != ct2


def test_decrypt_wrong_key_raises():
    ciphertext = encrypt(KEY, b"secret")
    wrong_key = bytes.fromhex("ffeeddccbbaa99887766554433221100")
    with pytest.raises(ValueError):
        decrypt(wrong_key, ciphertext)


def test_decrypt_tampered_data_raises():
    ciphertext = bytearray(encrypt(KEY, b"data"))
    ciphertext[-1] ^= 0xFF  # Flip a bit in the CRC
    with pytest.raises(ValueError):
        decrypt(KEY, bytes(ciphertext))


def test_decrypt_too_short_raises():
    with pytest.raises(ValueError):
        decrypt(KEY, b"tooshort")
