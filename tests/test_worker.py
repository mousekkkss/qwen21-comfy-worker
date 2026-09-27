import base64
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class OutputTransportTest(unittest.TestCase):
    def setUp(self):
        self.blob = b'PNG fixture with exact bytes and alpha'
        self.requests = types.SimpleNamespace(put=Mock(return_value=Mock()), get=Mock())
        self.official = types.SimpleNamespace(handler=Mock(return_value={
            'images': [{'filename': 'image.png', 'type': 'base64', 'data': base64.b64encode(self.blob).decode()}]
        }))
        spec = importlib.util.spec_from_file_location('qwen_worker_test', Path(__file__).parents[1] / 'worker.py')
        self.worker = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'handler': self.official, 'requests': self.requests, 'runpod': types.SimpleNamespace()}):
            spec.loader.exec_module(self.worker)

    def job(self, uploads):
        return {'input': {'qwen21_output_uploads': uploads}}

    def test_upload_preserves_png_bytes_and_returns_url(self):
        grant = {'put_url': 'https://example.com/bucket/image.png?put=signature', 'get_url': 'https://example.com/bucket/image.png?get=signature'}
        result = self.worker.handler(self.job([grant]))
        self.requests.put.assert_called_once_with(grant['put_url'], data=self.blob, headers={'Content-Type': 'image/png'}, timeout=180)
        self.assertEqual(result['images'][0]['data'], grant['get_url'])
        self.assertEqual(result['images'][0]['size'], len(self.blob))

    def test_large_output_without_grant_fails_explicitly(self):
        self.official.handler.return_value['images'][0]['data'] = 'A' * (5 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, 'signed output upload'):
            self.worker.handler(self.job([]))
        self.requests.put.assert_not_called()

    def test_mismatched_output_objects_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'same HTTPS object'):
            self.worker.handler(self.job([{'put_url': 'https://example.com/a.png', 'get_url': 'https://example.com/b.png'}]))
        self.requests.put.assert_not_called()


if __name__ == '__main__':
    unittest.main()
