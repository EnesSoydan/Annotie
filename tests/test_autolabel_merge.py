"""Otomatik etiketleme sinif eslemesi ve birlestirme testleri."""

import unittest

from src.inference.base import Prediction
from src.inference.merge import (
    MODE_APPEND, MODE_REPLACE, MODE_UNLABELED_ONLY, ClassTarget, auto_class_mapping,
    can_convert, finalize_predictions, merge_annotations, resolve_mapping,
)
from src.models.annotation import (
    AnnotationType, BBoxAnnotation, ClassificationAnnotation, PolygonAnnotation,
)


def box(cid, x=0.5):
    return BBoxAnnotation(cid, x, 0.5, 0.1, 0.1)


class MappingTests(unittest.TestCase):
    def test_auto_mapping_matches_names_case_insensitively(self):
        m = auto_class_mapping(["Person", "car", "dog"], ["car", "person"])
        self.assertEqual(m[0], ClassTarget.existing(1))
        self.assertEqual(m[1], ClassTarget.existing(0))
        self.assertEqual(m[2].kind, "ignore")

    def test_empty_dataset_gets_new_classes(self):
        m = auto_class_mapping(["a", "b"], [])
        self.assertEqual([t.kind for t in m.values()], ["new", "new"])

    def test_resolve_mapping_appends_new_classes_and_dedupes(self):
        mapping = {
            0: ClassTarget.existing(0),
            1: ClassTarget.new("kedi"),
            2: ClassTarget.ignore(),
            3: ClassTarget.new("Kedi"),     # ayni ad -> ayni yeni sinif
            4: ClassTarget.new("balon"),    # mevcut ada esit -> mevcut sinif
        }
        id_map, new_names = resolve_mapping(mapping, ["balon"])
        self.assertEqual(new_names, ["kedi"])
        self.assertEqual(id_map, {0: 0, 1: 1, 3: 1, 4: 0})


class FinalizeTests(unittest.TestCase):
    def test_threshold_mapping_and_fresh_uid(self):
        p_hi = Prediction(box(5), 0.9)
        p_lo = Prediction(box(5), 0.1)
        p_ignored = Prediction(box(7), 0.9)
        out = finalize_predictions([p_hi, p_lo, p_ignored], {5: 0}, conf=0.25)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].class_id, 0)
        self.assertNotEqual(out[0].uid, p_hi.annotation.uid)
        self.assertEqual(p_hi.annotation.class_id, 5)  # orijinal degismez

    def test_polygon_converted_to_bbox_for_bbox_dataset(self):
        poly = PolygonAnnotation(0, [(0.1, 0.2), (0.3, 0.2), (0.3, 0.6)])
        out = finalize_predictions([Prediction(poly, 0.9)], {0: 0}, 0.25, AnnotationType.BBOX)
        self.assertEqual(out[0].ann_type, AnnotationType.BBOX)
        self.assertAlmostEqual(out[0].width, 0.2)
        self.assertAlmostEqual(out[0].y_center, 0.4)

    def test_task_compatibility(self):
        self.assertTrue(can_convert(AnnotationType.BBOX, None))
        self.assertTrue(can_convert(AnnotationType.OBB, AnnotationType.BBOX))
        self.assertFalse(can_convert(AnnotationType.BBOX, AnnotationType.POLYGON))
        self.assertFalse(can_convert(AnnotationType.CLASSIFICATION, AnnotationType.BBOX))


class MergeTests(unittest.TestCase):
    def test_append(self):
        existing, new = [box(0)], [box(1)]
        self.assertEqual(len(merge_annotations(existing, new, MODE_APPEND)), 2)

    def test_unlabeled_only_skips_labeled_images(self):
        self.assertIsNone(merge_annotations([box(0)], [box(1)], MODE_UNLABELED_ONLY))
        self.assertEqual(len(merge_annotations([], [box(1)], MODE_UNLABELED_ONLY)), 1)

    def test_replace(self):
        out = merge_annotations([box(0), box(0)], [box(1)], MODE_REPLACE)
        self.assertEqual([a.class_id for a in out], [1])

    def test_no_predictions_never_touches_image(self):
        for mode in (MODE_APPEND, MODE_UNLABELED_ONLY, MODE_REPLACE):
            self.assertIsNone(merge_annotations([box(0)], [], mode))

    def test_append_keeps_single_classification(self):
        existing = [ClassificationAnnotation(0)]
        self.assertIsNone(merge_annotations(existing, [ClassificationAnnotation(1)], MODE_APPEND))


if __name__ == "__main__":
    unittest.main()
