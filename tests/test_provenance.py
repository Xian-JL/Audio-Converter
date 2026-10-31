"""A source checkout must preserve pinned upstream and vocabulary bytes."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProvenanceTests(unittest.TestCase):
    def test_pinned_source_and_vocabulary_bytes_survive_checkout(self):
        for folder in ('anticipation', 'emo-disentanger', 'midi-emotion'):
            base = ROOT / 'vendor' / folder
            manifest = json.loads((base / 'SOURCE.json').read_text(encoding='utf-8'))
            for name, expected in manifest['files'].items():
                with self.subTest(source=folder, file=name):
                    self.assertEqual(hashlib.sha256((base / name).read_bytes()).hexdigest(), expected)
        manifest = json.loads((ROOT / 'models/emotion-models-manifest.json').read_text(encoding='utf-8'))
        for name, entry in manifest['files'].items():
            if name.startswith('server/data/'):
                with self.subTest(vocabulary=name):
                    raw = (ROOT / name).read_bytes()
                    self.assertEqual(len(raw), entry['bytes'])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['sha256'])


if __name__ == '__main__':
    unittest.main()
