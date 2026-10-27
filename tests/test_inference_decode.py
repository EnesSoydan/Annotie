"""YOLO ONNX cikti decode testleri (sentetik tensorler)."""

import math
import unittest

import numpy as np

from src.inference import decode
from src.inference.decode import Letterbox
from src.models.annotation import AnnotationType


IDENTITY = Letterbox(ratio=1.0, pad_x=0.0, pad_y=0.0, orig_w=640, orig_h=640)


def classic(rows):
    """(N, C) satirlarini klasik (1, C, N) cikti duzenine cevirir."""
    return np.asarray(rows, dtype=np.float32).T[None]


class LetterboxTests(unittest.TestCase):
    def test_letterbox_roundtrip_maps_back_to_original(self):
        img = np.zeros((480, 960, 3), dtype=np.uint8)
        padded, lb = decode.letterbox(img, 640, 640)
        self.assertEqual(padded.shape, (640, 640, 3))
        self.assertAlmostEqual(lb.ratio, 640 / 960)
        self.assertEqual(lb.pad_x, 0)
        self.assertEqual(lb.pad_y, 160)
        # Orijinalde (480, 240) -> girdi uzayinda (320, 320)
        nx, ny = lb.to_norm_xy([320.0], [320.0])
        self.assertAlmostEqual(float(nx[0]), 0.5, places=3)
        self.assertAlmostEqual(float(ny[0]), 0.5, places=3)


class DetectDecodeTests(unittest.TestCase):
    def test_classic_detect_applies_threshold_and_class_aware_nms(self):
        rows = [
            # cx, cy, w, h, s0, s1
            [100, 100, 50, 50, 0.9, 0.0],
            [102, 101, 50, 50, 0.8, 0.0],   # ayni sinif, cakisiyor -> elenir
            [101, 100, 50, 50, 0.0, 0.7],   # farkli sinif -> kalir
            [400, 400, 20, 20, 0.1, 0.0],   # esik alti
        ]
        preds = decode.decode_detections(classic(rows), AnnotationType.BBOX, 2,
                                         IDENTITY, conf=0.25, iou=0.5, end2end=False)
        self.assertEqual(sorted(p.annotation.class_id for p in preds), [0, 1])
        top = max(preds, key=lambda p: p.score)
        self.assertAlmostEqual(top.annotation.x_center, 100 / 640, places=5)
        self.assertAlmostEqual(top.annotation.width, 50 / 640, places=5)

    def test_end2end_detect_reads_xyxy_conf_cls(self):
        out = np.array([[[10, 20, 110, 220, 0.95, 3],
                         [0, 0, 5, 5, 0.01, 1]]], dtype=np.float32)
        preds = decode.decode_detections(out, AnnotationType.BBOX, 80, IDENTITY,
                                         conf=0.25, iou=0.5, end2end=True)
        self.assertEqual(len(preds), 1)
        a = preds[0].annotation
        self.assertEqual(a.class_id, 3)
        self.assertAlmostEqual(a.x_center, 60 / 640, places=5)
        self.assertAlmostEqual(a.height, 200 / 640, places=5)


class ObbDecodeTests(unittest.TestCase):
    def test_corners_of_rotated_box(self):
        c = decode.xywhr_to_corners(100, 100, 40, 20, math.pi / 2)
        xs, ys = sorted(c[:, 0]), sorted(c[:, 1])
        self.assertAlmostEqual(xs[0], 90, places=4)
        self.assertAlmostEqual(xs[-1], 110, places=4)
        self.assertAlmostEqual(ys[0], 80, places=4)
        self.assertAlmostEqual(ys[-1], 120, places=4)

    def test_classic_obb_with_rotated_nms(self):
        rows = [
            [200, 200, 80, 20, 0.9, 0.3],
            [201, 200, 80, 20, 0.8, 0.3],   # ayni kutu -> probiou NMS ile elenir
            [400, 400, 30, 30, 0.7, 0.0],
        ]
        preds = decode.decode_detections(classic(rows), AnnotationType.OBB, 1, IDENTITY,
                                         conf=0.25, iou=0.5, end2end=False)
        self.assertEqual(len(preds), 2)
        self.assertTrue(all(len(p.annotation.corners) == 4 for p in preds))

    def test_end2end_obb_layout(self):
        out = np.array([[[320, 320, 64, 32, 0.9, 2, 0.0]]], dtype=np.float32)
        preds = decode.decode_detections(out, AnnotationType.OBB, 3, IDENTITY,
                                         conf=0.25, iou=0.5, end2end=True)
        self.assertEqual(preds[0].annotation.class_id, 2)
        xs = [x for x, _ in preds[0].annotation.corners]
        self.assertAlmostEqual(min(xs), 288 / 640, places=4)


class PoseDecodeTests(unittest.TestCase):
    def test_keypoints_visibility_from_confidence(self):
        rows = [[100, 100, 40, 40, 0.9,
                 90, 90, 0.9,
                 110, 110, 0.2]]
        preds = decode.decode_detections(classic(rows), AnnotationType.KEYPOINTS, 1,
                                         IDENTITY, conf=0.25, iou=0.5, end2end=False,
                                         kpt_shape=(2, 3))
        kps = preds[0].annotation.keypoints
        self.assertEqual(kps[0][2], 2)
        self.assertAlmostEqual(kps[0][0], 90 / 640, places=5)
        self.assertEqual(kps[1], (0.0, 0.0, 0))


class SegmentDecodeTests(unittest.TestCase):
    def test_mask_coefficients_to_polygon(self):
        nm, mh, mw = 2, 160, 160
        protos = np.full((1, nm, mh, mw), -10.0, dtype=np.float32)
        protos[0, 0, 40:80, 40:80] = 10.0     # 1. prototip: kare nesne
        rows = [[240, 240, 160, 160, 0.9, 1.0, 0.0]]   # coeffs: [1, 0]
        preds = decode.decode_detections(classic(rows), AnnotationType.POLYGON, 1,
                                         IDENTITY, conf=0.25, iou=0.5, end2end=False,
                                         protos=protos, input_hw=(640, 640))
        self.assertEqual(len(preds), 1)
        pts = np.array(preds[0].annotation.points)
        self.assertGreaterEqual(len(pts), 4)
        self.assertAlmostEqual(pts[:, 0].min(), 160 / 640, delta=0.01)
        self.assertAlmostEqual(pts[:, 0].max(), 320 / 640, delta=0.01)


class ClassifyDecodeTests(unittest.TestCase):
    def test_top1_and_threshold(self):
        preds = decode.decode_classification(np.array([[0.1, 0.7, 0.2]]), conf=0.5)
        self.assertEqual(preds[0].annotation.class_id, 1)
        self.assertEqual(decode.decode_classification(np.array([[0.4, 0.3, 0.3]]), 0.5), [])

    def test_logits_are_softmaxed(self):
        preds = decode.decode_classification(np.array([[-1.0, 5.0]]), conf=0.5)
        self.assertEqual(preds[0].annotation.class_id, 1)
        self.assertLessEqual(preds[0].score, 1.0)


if __name__ == "__main__":
    unittest.main()
