"""StorageClient indirmeleri: dataset kapsamlı presign + içerik-hash doğrulaması."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from src.cloud import storage as storage_module
from src.cloud.storage import StorageClient, StorageError


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", payload=None):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("latin-1")
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHttp:
    def __init__(self, blob: bytes):
        self.blob = blob
        self.presign_payloads = []

    def post(self, url, json=None, headers=None):
        self.presign_payloads.append(json)
        return _FakeResponse(payload={"url": "https://r2.example/obj", "key": "k"})

    def get(self, url):
        return _FakeResponse(content=self.blob)

    def close(self):
        pass


def _client(http, dataset_id=None):
    session = SimpleNamespace(access_token="token")
    supabase = SimpleNamespace(auth=SimpleNamespace(get_session=lambda: session))
    config = SimpleNamespace(url="https://proj.supabase.co", anon_key="anon")
    client = StorageClient(client=supabase, config=config, dataset_id=dataset_id)
    client._http.close()
    client._http = http
    return client


class StorageDownloadSecurityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(storage_module, "CACHE_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_download_sends_dataset_id_and_caches_verified_blob(self):
        blob = b"image-bytes"
        digest = hashlib.sha256(blob).hexdigest()
        http = _FakeHttp(blob)
        path = _client(http, dataset_id="ds-1").download_to_cache(digest)
        self.assertEqual(path.read_bytes(), blob)
        self.assertEqual(http.presign_payloads[0]["dataset_id"], "ds-1")
        self.assertEqual(http.presign_payloads[0]["op"], "get")
        self.assertEqual(list(Path(self._tmp.name).glob("*.part")), [])

    def test_explicit_dataset_id_overrides_default(self):
        blob = b"x"
        http = _FakeHttp(blob)
        _client(http, dataset_id="default").download_to_cache(
            hashlib.sha256(blob).hexdigest(), "explicit")
        self.assertEqual(http.presign_payloads[0]["dataset_id"], "explicit")

    def test_rejects_blob_whose_hash_does_not_match(self):
        digest = hashlib.sha256(b"expected").hexdigest()
        client = _client(_FakeHttp(b"poisoned"), dataset_id="ds-1")
        with self.assertRaises(StorageError):
            client.download_to_cache(digest)
        self.assertIsNone(client.cached_path(digest))

    def test_requires_dataset_id_for_uncached_download(self):
        with self.assertRaises(StorageError):
            _client(_FakeHttp(b"x")).download_to_cache(hashlib.sha256(b"x").hexdigest())


if __name__ == "__main__":
    unittest.main()
