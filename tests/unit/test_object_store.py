from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.object_store import (
    FilesystemObjectStore,
    ObjectStoreError,
    S3ObjectStore,
    backup_epoch,
    epoch_backup_from_dict,
    restore_epoch,
)
from taedri_codegraph.storage import GraphStore


class MissingObject(KeyError):
    pass


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, dict[str, object]]] = {}

    def head_object(self, *, Bucket: str, Key: str):
        try:
            body, metadata = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise MissingObject(Key) from exc
        return {"ContentLength": len(body), **metadata}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **metadata):
        self.objects[(Bucket, Key)] = (bytes(Body), metadata)
        return {"ETag": "fixture"}

    def get_object(self, *, Bucket: str, Key: str):
        try:
            body, metadata = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise MissingObject(Key) from exc
        return {"Body": io.BytesIO(body), "ContentLength": len(body), **metadata}


class ObjectStoreTests(unittest.TestCase):
    def test_filesystem_objects_are_content_addressed_and_fail_on_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FilesystemObjectStore(temporary, prefix="tenant-a")
            first = store.put_bytes(b"stable", media_type="text/plain")
            second = store.put_bytes(b"stable", media_type="text/plain")
            self.assertEqual(first, second)
            self.assertEqual(store.get_bytes(first.digest), b"stable")
            path = Path(temporary).joinpath(*first.key.split("/"))
            path.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ObjectStoreError, "digest mismatch"):
                store.get_bytes(first.digest)

    def test_s3_adapter_uses_the_same_keys_and_validates_reads(self) -> None:
        client = FakeS3()
        store = S3ObjectStore(client, "fixture", prefix="tenant-a")
        stored = store.put_bytes(b"remote", media_type="application/octet-stream")
        self.assertTrue(store.contains(stored.digest))
        self.assertEqual(store.get_bytes(stored.digest), b"remote")
        key = ("fixture", stored.key)
        _, metadata = client.objects[key]
        client.objects[key] = (b"tampered", metadata)
        with self.assertRaisesRegex(ObjectStoreError, "digest mismatch"):
            store.get_bytes(stored.digest)

    def test_published_epoch_round_trips_through_portable_object_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "address.py").write_text(
                "def normalize(value: str) -> str:\n    return value.strip().lower()\n",
                "utf-8",
            )
            analyzer = PythonSyntaxAnalyzer()
            bundle = analyzer.analyze(source, package_name="address")
            graph = GraphStore(root / "graph")
            epoch = graph.write_candidate(bundle, analyzer.registry)
            graph.publish_epoch(epoch)
            objects = FilesystemObjectStore(root / "objects", prefix="tenant-a")
            backup, backup_ref = backup_epoch(graph, objects)
            self.assertTrue(objects.contains(backup_ref.digest))
            decoded = epoch_backup_from_dict(backup.to_dict())
            restored = GraphStore(root / "restored")
            self.assertEqual(restore_epoch(restored, objects, decoded, publish=True), epoch)
            self.assertEqual(restored.current_epoch_id(), epoch)
            self.assertIsNotNone(restored.index().resolve_entity("address.normalize"))


if __name__ == "__main__":
    unittest.main()
