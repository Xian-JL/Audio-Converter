"""A lazy-loader stub is runtime data, even though its extension looks optional."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from scripts.package_portable import archive_bundle, resource_copier

class PortableArchiveTests(unittest.TestCase):
    def test_reuse_links_only_identical_immutable_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);old=root/'old';new=root/'new';source=root/'source'
            for folder in (old,new,source):folder.mkdir()
            for name in ('models/same.bin','models/different.bin','server/code.py'):
                a=old/name;b=source/name;a.parent.mkdir(parents=True,exist_ok=True);b.parent.mkdir(parents=True,exist_ok=True)
                a.write_bytes(b'old');b.write_bytes(b'new' if 'different' in name else b'old')
                target=new/name;target.parent.mkdir(parents=True,exist_ok=True);resource_copier(new,old)(b,target)
                self.assertEqual(target.read_bytes(),b.read_bytes())
                self.assertEqual(target.samefile(a),name=='models/same.bin')

    def test_archive_preserves_runtime_stubs_and_licenses_but_omits_development_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);bundle=root/'bundle';bundle.mkdir()
            (bundle/'bundle-manifest.json').write_text(json.dumps({'version':'test','files':{}}))
            files={'runtime/Lib/site-packages/librosa/__init__.pyi':'from .core import load',
                   'runtime/Lib/site-packages/librosa/tests/test_audio.py':'test',
                   'runtime/Lib/site-packages/example/include/api.h':'header',
                   'runtime/Lib/site-packages/example/licenses/include/LICENSE.txt':'license',
                   '.desktop/browser/Default/History':'private browser profile',
                   '.runtime/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/analysis.json':'private analysis'}
            for name,text in files.items():
                path=bundle/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            archive=root/'portable.zip';archive_bundle(bundle,archive)
            with zipfile.ZipFile(archive) as zipped:
                names=['/'.join(name.split('/')[1:]) for name in zipped.namelist()]
                self.assertIn('runtime/Lib/site-packages/librosa/__init__.pyi',names)
                self.assertIn('runtime/Lib/site-packages/example/licenses/include/LICENSE.txt',names)
                self.assertNotIn('runtime/Lib/site-packages/librosa/tests/test_audio.py',names)
                self.assertNotIn('runtime/Lib/site-packages/example/include/api.h',names)
                self.assertFalse(any(name.startswith(('.desktop/','.runtime/')) for name in names))

if __name__=='__main__':unittest.main()
