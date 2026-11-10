"""Aufgaben für den Unterricht: Aufgabenstellung offen, Musterlösung verschlüsselt.

Eine Lehrkraft schreibt über Extras → Aufgabe stellen eine Aufgabenstellung und – wenn sie möchte – eine
Musterlösung in das Projekt und vergibt ein Passwort. Die Schülerinnen und Schüler öffnen die Datei, sehen die
Aufgabe oben über der Arbeitsfläche und zeichnen ihren Plan. Die Musterlösung steht nur verschlüsselt in der
Datei; lesen kann sie nur, wer das Passwort kennt. Dasselbe Passwort schützt die Aufgabe vor Änderungen.

Verschlüsselt wird nur mit der Standardbibliothek: Schlüssel aus dem Passwort mit PBKDF2-HMAC-SHA256
(zufälliges Salz, viele Durchläufe), Schlüsselstrom aus SHA-256 im Zählerbetrieb, Prüfsumme mit HMAC-SHA256.
Ohne Passwort lässt sich der Text nicht lesen, und ein falsches Passwort wird sicher erkannt.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

SOLUTION_PREFIX = "v1:"
LOCK_PREFIX = "v1:"
ITERATIONS = 200_000
SALT_SIZE = 16
NONCE_SIZE = 16
TAG_SIZE = 32


class WrongPassword(Exception):
    """Das Passwort passt nicht (oder die verschlüsselten Daten sind beschädigt)."""


@dataclass
class Task:
    title: str = ""
    text: str = ""
    solution: str = ""   # verschlüsselt (``encrypt``) oder leer
    lock: str = ""       # Prüfwert des Passworts (``make_lock``) oder leer = ohne Passwort änderbar

    @property
    def present(self) -> bool:
        return bool(self.title.strip() or self.text.strip())

    @property
    def has_solution(self) -> bool:
        return bool(self.solution)

    @property
    def locked(self) -> bool:
        return bool(self.lock)


def task_of(meta) -> Task:
    return Task(meta.task_title, meta.task_text, meta.task_solution, meta.task_lock)


def apply_task(meta, task: Task) -> None:
    meta.task_title, meta.task_text = task.title, task.text
    meta.task_solution, meta.task_lock = task.solution, task.lock


# ------------------------------------------------------------------ Verschlüsselung
def _keys(password: str, salt: bytes) -> tuple[bytes, bytes]:
    material = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, dklen=64)
    return material[:32], material[32:]


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = []
    for counter in range((length + 31) // 32):
        blocks.append(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
    return b"".join(blocks)[:length]


def encrypt(text: str, password: str) -> str:
    """Verschlüsselt ``text`` mit ``password``; das Ergebnis ist reiner ASCII-Text (für die Projektdatei)."""
    if not password:
        raise ValueError("Ohne Passwort wird nicht verschlüsselt.")
    salt, nonce = os.urandom(SALT_SIZE), os.urandom(NONCE_SIZE)
    enc_key, mac_key = _keys(password, salt)
    plain = text.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(plain, _stream(enc_key, nonce, len(plain))))
    tag = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
    return SOLUTION_PREFIX + base64.b64encode(salt + nonce + tag + cipher).decode("ascii")


def decrypt(data: str, password: str) -> str:
    """Entschlüsselt ``data``; wirft ``WrongPassword`` bei falschem Passwort oder beschädigten Daten."""
    if not data.startswith(SOLUTION_PREFIX):
        raise WrongPassword()
    try:
        raw = base64.b64decode(data[len(SOLUTION_PREFIX):].encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        raise WrongPassword() from None
    head = SALT_SIZE + NONCE_SIZE + TAG_SIZE
    if len(raw) < head:
        raise WrongPassword()
    salt, nonce = raw[:SALT_SIZE], raw[SALT_SIZE:SALT_SIZE + NONCE_SIZE]
    tag, cipher = raw[SALT_SIZE + NONCE_SIZE:head], raw[head:]
    enc_key, mac_key = _keys(password, salt)
    if not hmac.compare_digest(tag, hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()):
        raise WrongPassword()
    plain = bytes(a ^ b for a, b in zip(cipher, _stream(enc_key, nonce, len(cipher))))
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        raise WrongPassword() from None


def make_lock(password: str) -> str:
    """Prüfwert eines Passworts (das Passwort selbst steht nie in der Datei)."""
    salt = os.urandom(SALT_SIZE)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return LOCK_PREFIX + base64.b64encode(salt + digest).decode("ascii")


def check_lock(lock: str, password: str) -> bool:
    if not lock.startswith(LOCK_PREFIX):
        return False
    try:
        raw = base64.b64decode(lock[len(LOCK_PREFIX):].encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return False
    salt, digest = raw[:SALT_SIZE], raw[SALT_SIZE:]
    return hmac.compare_digest(digest, hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS))
