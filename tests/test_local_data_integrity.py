"""P0-A yerel veri bütünlüğü regresyon testleri."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.io import trash as trash_module
from src.io.dataset_exporter import export_dataset
from src.io.label_reader import read_label_file
from src.io.label_writer import write_label_file
from src.io.yaml_handler import write_data_yaml
from src.models.annotation import (
    AnnotationType, BBoxAnnotation, KeypointsAnnotation, PolygonAnnotation,
    detect_annotation_type, parse_annotation_line,
)
from src.models.dataset import Dataset
from src.models.image_item import ImageItem
from src.models.label_class import LabelClass


def _structured_dataset(root: Path) -> Dataset:
    ds = Dataset(root_path=root)
    for split, folder in (("train", "train"), ("val", "valid")):
        (root / folder / "images").mkdir(parents=True)
        (root / folder / "labels").mkdir(parents=True)
        setattr(ds, f"{split}_images_path", root / folder / "images")
        setattr(ds, f"{split}_labels_path", root / folder / "labels")
    ds.classes = [LabelClass(0, "a"), LabelClass(1, "b"), LabelClass(2, "c")]
    return ds


def _add_image(ds: Dataset, split: str, name: str, label_text: str, lazy=True) -> ImageItem:
    folder = {"train": "train", "val": "valid"}[split]
    img_path = ds.root_path / folder / "images" / name
    img_path.write_bytes(b"fake")
    item = ImageItem(path=img_path, split=split)
    label = ds.get_label_path_for_image(item)
    label.write_text(label_text, encoding="utf-8")
    if lazy:
        item._pending_label_path = label
    else:
        item.annotations = read_label_file(label)
    ds.add_image(item)
    return item


class ExportTests(unittest.TestCase):
    def test_unvisited_images_keep_their_labels_and_dataset_is_not_mutated(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            ds = _structured_dataset(src)
            _add_image(ds, "train", "lazy.jpg", "1 0.5 0.5 0.2 0.2\n")
            out = Path(tmp) / "out"
            self.assertTrue(export_dataset(ds, str(out)))
            exported = (out / "train" / "labels" / "lazy.txt").read_text()
            self.assertEqual(exported.split()[0], "1")
            self.assertEqual(ds.root_path, src)
            self.assertEqual(ds.train_labels_path, src / "train" / "labels")
            data = yaml.safe_load((out / "data.yaml").read_text(encoding="utf-8"))
            self.assertEqual(data["train"], "./train/images")

    def test_same_stem_images_do_not_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _structured_dataset(Path(tmp) / "src")
            _add_image(ds, "train", "x.jpg", "0 0.5 0.5 0.1 0.1\n")
            (ds.root_path / "train" / "images" / "x.png").write_bytes(b"png")
            other = ImageItem(path=ds.root_path / "train" / "images" / "x.png", split="train")
            other.annotations = [BBoxAnnotation(2, 0.5, 0.5, 0.1, 0.1)]
            ds.add_image(other)
            out = Path(tmp) / "out"
            self.assertTrue(export_dataset(ds, str(out)))
            labels = sorted(p.name for p in (out / "train" / "labels").glob("*.txt"))
            self.assertEqual(labels, ["x.txt", "x_1.txt"])


class ClassRemovalTests(unittest.TestCase):
    def test_remove_class_remaps_loaded_and_lazy_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _structured_dataset(Path(tmp))
            lazy = _add_image(ds, "train", "l.jpg", "0 .5 .5 .1 .1\n1 .5 .5 .1 .1\n2 .5 .5 .1 .1\n")
            loaded = _add_image(ds, "val", "v.jpg", "2 .5 .5 .1 .1\n", lazy=False)
            self.assertEqual(ds.count_class_usage(1), 1)
            changed = ds.remove_class_and_remap(1)
            self.assertEqual({id(i) for i in changed}, {id(lazy), id(loaded)})
            self.assertEqual([a.class_id for a in lazy.annotations], [0, 1])
            self.assertEqual([a.class_id for a in loaded.annotations], [1])
            self.assertEqual([c.name for c in ds.classes], ["a", "c"])
            self.assertTrue(lazy.dirty and loaded.dirty)


class DataYamlTests(unittest.TestCase):
    def test_unknown_keys_preserved_and_names_not_wiped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "data.yaml"
            path.write_text(yaml.safe_dump({
                "names": {0: "person"}, "nc": 1, "kpt_shape": [17, 3],
                "flip_idx": [0, 2, 1], "download": "x",
            }), encoding="utf-8")
            empty = Dataset(root_path=root)
            self.assertTrue(write_data_yaml(path, empty))
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(data["names"], {0: "person"})
            self.assertEqual(data["flip_idx"], [0, 2, 1])
            ds = Dataset(root_path=root, classes=[LabelClass(0, "kisi")])
            write_data_yaml(path, ds)
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(data["names"], {0: "kisi"})
            self.assertEqual(data["download"], "x")


class AnnotationFormatTests(unittest.TestCase):
    def test_two_dim_keypoints_round_trip(self):
        line = "0 0.5 0.5 0.2 0.2 0.1 0.2 0.3 0.4"
        ann = parse_annotation_line(line, kpt_shape=(2, 2))
        self.assertIsInstance(ann, KeypointsAnnotation)
        self.assertEqual(ann.to_yolo_line().split(), line.split()[:1] + [
            f"{float(v):.6f}" for v in line.split()[1:]])

    def test_pose_length_wins_over_obb(self):
        parts = "0 .5 .5 .1 .1 .2 .2 .3 .3".split()
        self.assertEqual(detect_annotation_type(parts, (2, 2)), AnnotationType.KEYPOINTS)
        self.assertEqual(detect_annotation_type(parts), AnnotationType.OBB)

    def test_four_vertex_polygon_in_segmentation_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.txt"
            path.write_text("0 .1 .1 .2 .1 .2 .2 .1 .2\n"
                            "1 .1 .1 .2 .1 .3 .3 .2 .3 .1 .2\n", encoding="utf-8")
            anns = read_label_file(path)
            self.assertTrue(all(isinstance(a, PolygonAnnotation) for a in anns))


class TrashTests(unittest.TestCase):
    def test_copy_to_trash_keeps_full_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "data" / "img.jpg"
            src.parent.mkdir()
            src.write_bytes(b"x")
            batch = trash_module.copy_to_trash([src, Path(tmp) / "missing.txt"],
                                               trash_root=Path(tmp) / "trash")
            copies = list(batch.rglob("img.jpg"))
            self.assertEqual(len(copies), 1)
            self.assertEqual(copies[0].read_bytes(), b"x")


class SplitChangeTests(unittest.TestCase):
    def test_split_change_moves_image_and_label(self):
        from PySide6.QtCore import QCoreApplication
        from src.controllers.dataset_controller import DatasetController

        QCoreApplication.instance() or QCoreApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            ds = _structured_dataset(Path(tmp))
            img = _add_image(ds, "train", "m.jpg", "0 .5 .5 .1 .1\n")
            ctrl = DatasetController(SimpleNamespace(), SimpleNamespace())
            ctrl._dataset = ds
            self.assertIsNone(ctrl.change_image_split(img, "val"))
            root = Path(tmp)
            self.assertTrue((root / "valid" / "images" / "m.jpg").exists())
            self.assertTrue((root / "valid" / "labels" / "m.txt").exists())
            self.assertFalse((root / "train" / "images" / "m.jpg").exists())
            self.assertFalse((root / "train" / "labels" / "m.txt").exists())
            self.assertIs(ds.get_image(str(root / "valid" / "images" / "m.jpg")), img)

    def test_split_change_refuses_to_overwrite(self):
        from PySide6.QtCore import QCoreApplication
        from src.controllers.dataset_controller import DatasetController

        QCoreApplication.instance() or QCoreApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            ds = _structured_dataset(Path(tmp))
            img = _add_image(ds, "train", "d.jpg", "0 .5 .5 .1 .1\n")
            (Path(tmp) / "valid" / "images" / "d.jpg").write_bytes(b"other")
            ctrl = DatasetController(SimpleNamespace(), SimpleNamespace())
            ctrl._dataset = ds
            self.assertIsNotNone(ctrl.change_image_split(img, "val"))
            self.assertEqual(img.split, "train")
            self.assertTrue((Path(tmp) / "train" / "labels" / "d.txt").exists())


if __name__ == "__main__":
    unittest.main()
