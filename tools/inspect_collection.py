"""Sonde de diagnostic d'un export XML Rekordbox.

Ne fait partie ni du paquet ni des tests : sert une seule fois, à vérifier que les
My Tags sont exploitables depuis le XML avant d'écrire le lecteur.

Usage : python3 tools/inspect_collection.py ~/rekordbox.xml
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

TAGS_RE = re.compile(r"/\*(.+?)\*/", re.DOTALL)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1]).expanduser()
    root = ElementTree.parse(path).getroot()
    tracks = root.findall(".//COLLECTION/TRACK")
    print(f"Fichier      : {path}")
    print(f"Morceaux     : {len(tracks)}")

    with_comments = [t for t in tracks if (t.get("Comments") or "").strip()]
    with_tags = [t for t in with_comments if TAGS_RE.search(t.get("Comments", ""))]
    print(f"Comments non vides : {len(with_comments)}")
    print(f"Comments avec /* ... */ : {len(with_tags)}")

    print("\n--- 10 valeurs brutes de Comments ---")
    for track in with_comments[:10]:
        print(f"  {track.get('Comments')!r}")

    tags: Counter[str] = Counter()
    for track in with_tags:
        inner = TAGS_RE.search(track.get("Comments", "")).group(1)
        for tag in inner.split("/"):
            if tag.strip():
                tags[tag.strip()] += 1
    print(f"\n--- Tags distincts : {len(tags)} ---")
    for tag, count in tags.most_common():
        print(f"  {count:5d}  {tag!r}")

    print("\n--- Formats de Tonality ---")
    tonalities = Counter((t.get("Tonality") or "").strip() for t in tracks)
    for value, count in tonalities.most_common(25):
        print(f"  {count:5d}  {value!r}")

    print("\n--- Attributs présents sur le premier TRACK ---")
    if tracks:
        for key, value in sorted(tracks[0].attrib.items()):
            print(f"  {key} = {value!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
