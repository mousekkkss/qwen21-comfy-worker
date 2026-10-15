import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('qwen21_r2_models_test', Path(__file__).parents[1] / 'r2_models.py')
r2 = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'requests': types.SimpleNamespace(get=None)}):
    spec.loader.exec_module(r2)

HOST = 'https://acct.r2.cloudflarestorage.com'
LORA = 'loras/Qwen Image/FlatAnime_Qwen_2.1.safetensors'


def signed(relative, bucket='rat-image-ai-models', prefix='models'):
    return f"{HOST}/{bucket}/{prefix}/{relative.replace(' ', '%20')}?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc"


def plan(blob, relative=LORA, **row):
    item = {'relativePath': relative, 'url': signed(relative), 'sizeBytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
    item.update(row)
    return {'provider': 'cloudflare-r2', 'bucket': 'rat-image-ai-models', 'prefix': 'models', 'required': [item]}


class FakeResponse:
    def __init__(self, blob, headers):
        start, end = map(int, headers['Range'][6:].split('-'))
        self.status_code = 206
        self.body = blob[start:end + 1]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size):
        for i in range(0, len(self.body), 3):
            yield self.body[i:i + 3]


class ValidatePlanTest(unittest.TestCase):
    def test_accepts_signed_r2_object(self):
        rows = r2.validate_plan(plan(b'abc'))
        self.assertEqual(rows[0]['relativePath'], LORA)

    def test_rejects_unsafe_or_unsigned_plans(self):
        cases = {
            'other host': {'url': 'https://evil.example.com/rat-image-ai-models/models/' + LORA + '?X-Amz-Signature=a'},
            'http': {'url': signed(LORA).replace('https', 'http')},
            'unsigned': {'url': signed(LORA).split('?')[0]},
            'path mismatch': {'url': signed('loras/Qwen Image/other.safetensors')},
            'traversal': {'relativePath': 'loras/../../etc/passwd.safetensors'},
            'root': {'relativePath': 'vae/x.safetensors'},
            'extension': {'relativePath': 'loras/x.ckpt'},
            'no sha': {'sha256': ''},
            'no size': {'sizeBytes': 0},
        }
        for name, row in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                r2.validate_plan(plan(b'abc', **row))
        with self.assertRaises(ValueError):
            r2.validate_plan({**plan(b'abc'), 'bucket': 'someone-else'})


class HydrateTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.blob = bytes(range(256)) * 41

    def run_hydrate(self, request_plan, blob=None):
        calls = []

        def get(url, headers, stream, timeout):
            calls.append(headers['Range'])
            return FakeResponse(blob or self.blob, headers)
        with patch.object(r2.requests, 'get', side_effect=get), patch.object(r2, 'RANGE_THRESHOLD', 1024), patch.object(r2, 'CHUNK', 1000):
            return r2.hydrate(request_plan, self.root), calls

    def test_ranged_download_is_verified_then_cached(self):
        summary, calls = self.run_hydrate(plan(self.blob))
        self.assertEqual((self.root / LORA).read_bytes(), self.blob)
        self.assertGreater(len(calls), 1)
        self.assertFalse(summary[0]['cached'])
        summary, calls = self.run_hydrate(plan(self.blob))
        self.assertTrue(summary[0]['cached'])
        self.assertEqual(calls, [])

    def test_hash_mismatch_leaves_no_model(self):
        with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
            self.run_hydrate(plan(self.blob), blob=b'x' * len(self.blob))
        self.assertEqual([p for p in self.root.rglob('*') if p.is_file()], [])

    def test_changed_hash_downloads_again(self):
        self.run_hydrate(plan(self.blob))
        newer = self.blob[::-1]
        summary, calls = self.run_hydrate(plan(newer), blob=newer)
        self.assertFalse(summary[0]['cached'])
        self.assertEqual((self.root / LORA).read_bytes(), newer)

    def test_evicts_unused_r2_files_when_disk_is_short(self):
        old = 'loras/Qwen Image/old.safetensors'
        self.run_hydrate(plan(self.blob, old, url=signed(old)))
        # The disk is "full" until the earlier, unused LoRA is evicted.
        free = lambda _: types.SimpleNamespace(free=0 if (self.root / old).exists() else 10 ** 12)
        with patch.object(r2.shutil, 'disk_usage', side_effect=free):
            self.run_hydrate(plan(self.blob))
        self.assertFalse((self.root / old).exists())
        self.assertTrue((self.root / LORA).exists())


if __name__ == '__main__':
    unittest.main()
