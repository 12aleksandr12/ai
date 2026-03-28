#!/usr/bin/env python3
"""Ставит офлайн-модели Argos для пар из LANGUAGES (через английский как хаб). Запускается при сборке образа."""
from __future__ import annotations

import sys

import argostranslate.package as pkg


# Достаточно для Whisper(en,es,fr,de,ru) → любой из этих же кодов (не en — через en).
WANTED_PAIRS = [
    ("en", "ru"),
    ("en", "de"),
    ("en", "es"),
    ("en", "fr"),
    ("de", "en"),
    ("es", "en"),
    ("fr", "en"),
    ("ru", "en"),
]


def main() -> int:
    print("Argos: обновление индекса пакетов…", flush=True)
    pkg.update_package_index()
    avail = pkg.get_available_packages()
    by_pair = {(p.from_code, p.to_code): p for p in avail}
    ok = 0
    for pair in WANTED_PAIRS:
        p = by_pair.get(pair)
        if not p:
            print(f"Argos: пакет {pair[0]}→{pair[1]} не найден в индексе", flush=True)
            continue
        print(f"Argos: установка {pair[0]}→{pair[1]}…", flush=True)
        path = p.download()
        pkg.install_from_path(path)
        ok += 1
    if ok == 0:
        print("Argos: ни один пакет не установлен", file=sys.stderr, flush=True)
        return 1
    print(f"Argos: готово, установлено пакетов: {ok}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
