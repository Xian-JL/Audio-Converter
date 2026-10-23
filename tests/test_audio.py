"""Small release regression suite for validation and real FLAC/MP3 handling."""
import json
from pathlib import Path
import tempfile
import unittest
from server import app as service
from server.audio import probe,convert,AudioError
from server.game import model_directory,FILES,signature
from server.melody_score import generate_melody_score

class AudioTests(unittest.TestCase):
    def test_runtime_assets_and_version(self):
        directory=model_directory()
        self.assertEqual(directory,service.ROOT/'models/game-small')
        self.assertTrue(all((directory/f'{part}.onnx').is_file() for part in FILES))
        health=service.app.test_client().get('/api/health').json
        self.assertTrue(health['ready']);self.assertTrue(health['textureReady']);self.assertEqual(health['appVersion'],'0.3.2')

    def test_real_flac_conversion(self):
        source=Path('tests/fixtures/ui-upload.flac');info=probe(source)
        self.assertEqual(info['format'],'FLAC')
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'test.mp3';convert(source,target,info,lambda p:None)
            actual=probe(target);self.assertEqual(actual['format'],'MP3');self.assertAlmostEqual(actual['duration'],1,delta=.2)

    def test_invalid_media_and_untrusted_origins(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'damaged.flac';path.write_bytes(b'not audio')
            with self.assertRaises(AudioError):probe(path)
        client=service.app.test_client()
        self.assertEqual(client.get('/api/health',headers={'Origin':'https://example.com'}).status_code,403)
        for name in ('../bad','','not-a-job'):
            with self.assertRaises(ValueError):service.owned_dir(name)

    def test_full_song_first_melody_downbeat_preserves_all_performance(self):
        source=json.loads(Path('tests/fixtures/ember-full-analysis.json').read_text(encoding='utf-8'))
        self.assertEqual(signature(),source['engineSignature'])
        before=generate_melody_score(source,68,'4/4','C major')
        after=generate_melody_score(source,68,'4/4','C major','gf-000001')
        self.assertEqual(after['noteCount'],430);self.assertEqual(before['events'],after['events'])
        self.assertEqual(after['downbeat']['time'],15.37)
        self.assertEqual(after['measures'][after['downbeat']['measureNumber']-1]['start'],15.37)

if __name__=='__main__':unittest.main()
