"""Local Python release checks using the prepared resources; no user runtime jobs."""
import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-inference', action='store_true', help='Also run the historical full-song AMT inference test.')
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT:
        parser.error('Run this command from the audio-converter project root.')
    sys.path.insert(0, str(ROOT))
    discovered = unittest.TestLoader().discover(str(ROOT / 'tests'), pattern='test_*.py')
    selected = unittest.TestSuite(test for test in cases(discovered)
        if args.legacy_inference or not test.id().endswith('.test_real_cpu_inference_is_preserved_and_deterministic'))
    return 0 if unittest.TextTestRunner(verbosity=1).run(selected).wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
