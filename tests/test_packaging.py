"""A lazy-loader stub is runtime data, even though its extension looks optional."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from scripts.package_portable import archive_bundle

class PortableArchiveTests(unittest.TestCase):
    def test_archive_preserves_runtime_stubs_and_licenses_but_omits_development_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);bundle=root/'bundle';bundle.mkdir()
            (bundle/'bundle-manifest.json').write_text(json.dumps({'version':'test','files':{}}))
            files={'runtime/Lib/site-packages/librosa/__init__.pyi':'from .core import load',
                   'runtime/Lib/site-packages/librosa/tests/test_audio.py':'test',
                   'runtime/Lib/site-packages/example/include/api.h':'header',
                   'runtime/Lib/site-packages/example/licenses/include/LICENSE.txt':'license'}
            for name,text in files.items():
                path=bundle/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            archive=root/'portable.zip';archive_bundle(bundle,archive)
            with zipfile.ZipFile(archive) as zipped:
                names=['/'.join(name.split('/')[1:]) for name in zipped.namelist()]
                self.assertIn('runtime/Lib/site-packages/librosa/__init__.pyi',names)
                self.assertIn('runtime/Lib/site-packages/example/licenses/include/LICENSE.txt',names)
                self.assertNotIn('runtime/Lib/site-packages/librosa/tests/test_audio.py',names)
                self.assertNotIn('runtime/Lib/site-packages/example/include/api.h',names)

if __name__=='__main__':unittest.main()
