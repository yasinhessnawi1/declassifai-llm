"""Usage: python -m eval.routing.validate_gold <gold_dir>. Exit 1 if the set is not valid."""
import sys

from .gold import validate_gold


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    rep = validate_gold(argv[1])
    for e in rep.errors:
        print(e)
    print(f"{rep.documents} documents, {rep.reviewed} reviewed, {len(rep.errors)} errors")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
