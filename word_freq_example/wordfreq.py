"""Count words from standard input using Python 3.12 or newer."""

import argparse
import json
import sys
from collections import Counter


def count_words(text: str) -> Counter[str]:
    """Count runs of Unicode letters, treating other characters as separators."""
    separated = "".join(char if char.isalpha() else " " for char in text)
    return Counter(word.casefold() for word in separated.split())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--json", action="store_true", help="print counts as a JSON object"
    )
    args = parser.parse_args()

    counts = count_words(sys.stdin.read())
    if args.json:
        print(json.dumps(counts, sort_keys=True))
    else:
        for word in sorted(counts):
            print(f"{word} {counts[word]}")


if __name__ == "__main__":
    main()
