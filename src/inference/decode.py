"""YOLO ONNX ciktilarini Annotation'lara ceviren saf numpy fonksiyonlari.

Iki cikti duzeni desteklenir:
  * Klasik (YOLOv8/11):  (1, C, N) — C = 4 + nc [+ nm | + 1 (aci) | + nk],
    kutular cx,cy,w,h; NMS istemcide yapilir.
  * End-to-end (YOLO26/v10, metadata end2end=True): (1, max_det, F) —
    detect/seg/pose: x1,y1,x2,y2,conf,cls[,...]; obb: cx,cy,w,h,conf,cls,aci.
Koordinatlar letterbox'li girdi uzayindadir; Letterbox.to_norm ile orijinal
gorsele gore normalize edilir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from src.models.annotation import (
    AnnotationType, BBoxAnnotation, ClassificationAnnotation,
    KeypointsAnnotation, OBBAnnotation, PolygonAnnotation,
)
from src.inference.base import Prediction


# ─── Letterbox ─────────────────────────────────────────────────────────────
@dataclass
class Letterbox:
    ratio: float
    pad_x: float
    pad_y: float
    orig_w: int
    orig_h: int

    def to_norm_xy(self, x, y):
        """Girdi uzayi piksel -> orijinal gorsele gore [0,1]."""
        nx = (np.asarray(x, dtype=np.float64) - self.pad_x) / self.ratio / self.orig_w
        ny = (np.asarray(y, dtype=np.float64) - self.pad_y) / self.ratio / self.orig_h
        return np.clip(nx, 0.0, 1.0), np.clip(ny, 0.0, 1.0)


def letterbox(img: np.ndarray, new_w: int, new_h: int) -> Tuple[np.ndarray, Letterbox]:
    """Ultralytics LetterBox(auto=False, center=True) ile ayni on isleme."""
    import cv2
    h, w = img.shape[:2]
    r = min(new_h / h, new_w / w)
    unpad_w, unpad_h = int(round(w * r)), int(round(h * r))
    dw, dh = (new_w - unpad_w) / 2, (new_h - unpad_h) / 2
    if (w, h) != (unpad_w, unpad_h):
        img = cv2.resize(img, (unpad_w, unpad_h), interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right,
                             cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return img, Letterbox(r, left, top, w, h)


def to_tensor(img: np.ndarray) -> np.ndarray:
    """HWC uint8 RGB -> 1xCxHxW float32 [0,1]."""
    x = img.astype(np.float32) / 255.0
    return np.ascontiguousarray(x.transpose(2, 0, 1)[None])


# ─── NMS ───────────────────────────────────────────────────────────────────
def xywh_to_xyxy(b: np.ndarray) -> np.ndarray:
    out = np.empty_like(b)
    out[:, 0] = b[:, 0] - b[:, 2] / 2
    out[:, 1] = b[:, 1] - b[:, 3] / 2
    out[:, 2] = b[:, 0] + b[:, 2] / 2
    out[:, 3] = b[:, 1] + b[:, 3] / 2
    return out


def _iou_one_to_many(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    a = (box[2] - box[0]) * (box[3] - box[1])
    b = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    return inter / np.maximum(a + b - inter, 1e-9)


def _probiou_one_to_many(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """Donuk kutular icin olasiliksal IoU (ultralytics batch_probiou)."""
    def cov(b):
        a, c = b[..., 2] ** 2 / 12, b[..., 3] ** 2 / 12
        cos, sin = np.cos(b[..., 4]), np.sin(b[..., 4])
        return a * cos ** 2 + c * sin ** 2, a * sin ** 2 + c * cos ** 2, (a - c) * cos * sin
    eps = 1e-7
    a1, b1, c1 = cov(box)
    a2, b2, c2 = cov(boxes)
    dx, dy = box[0] - boxes[:, 0], box[1] - boxes[:, 1]
    denom = (a1 + a2) * (b1 + b2) - (c1 + c2) ** 2 + eps
    t1 = ((a1 + a2) * dy ** 2 + (b1 + b2) * dx ** 2) / denom * 0.25
    t2 = ((c1 + c2) * (-dx) * dy) / denom * 0.5
    t3 = np.log(denom / (4 * np.sqrt(np.clip(a1 * b1 - c1 ** 2, 0, None)
                                     * np.clip(a2 * b2 - c2 ** 2, 0, None)) + eps) + eps) * 0.5
    bd = np.clip(t1 + t2 + t3, eps, 100.0)
    hd = np.sqrt(1.0 - np.exp(-bd) + eps)
    return 1.0 - hd


def nms(boxes: np.ndarray, scores: np.ndarray, classes: np.ndarray,
        iou_thr: float, rotated: bool = False, max_det: int = 300) -> List[int]:
    """Sinif bazli greedy NMS. boxes: xyxy (veya rotated ise xywhr)."""
    order = np.argsort(-scores)
    keep: List[int] = []
    overlap = _probiou_one_to_many if rotated else _iou_one_to_many
    while order.size and len(keep) < max_det:
        i = order[0]
        keep.append(int(i))
        rest = order[1:]
        if not rest.size:
            break
        same = classes[rest] == classes[i]
        ious = overlap(boxes[i], boxes[rest])
        order = rest[~(same & (ious > iou_thr))]
    return keep


# ─── Geometri ──────────────────────────────────────────────────────────────
def xywhr_to_corners(cx, cy, w, h, r) -> np.ndarray:
    cos, sin = math.cos(r), math.sin(r)
    v1 = np.array([w / 2 * cos, w / 2 * sin])
    v2 = np.array([-h / 2 * sin, h / 2 * cos])
    c = np.array([cx, cy])
    return np.stack([c + v1 + v2, c + v1 - v2, c - v1 - v2, c - v1 + v2])


def _bbox_ann(cls_id, x1, y1, x2, y2, lb: Letterbox) -> BBoxAnnotation:
    (nx1, nx2), (ny1, ny2) = lb.to_norm_xy([x1, x2], [y1, y2])
    return BBoxAnnotation(int(cls_id), float((nx1 + nx2) / 2), float((ny1 + ny2) / 2),
                          float(nx2 - nx1), float(ny2 - ny1))


def mask_to_polygon(mask: np.ndarray, epsilon: float = 1.0) -> Optional[np.ndarray]:
    """Ikili maskenin en buyuk dis konturunu (N,2) piksel noktalari olarak dondurur."""
    import cv2
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if epsilon > 0:
        c = cv2.approxPolyDP(c, epsilon, True)
    pts = c.reshape(-1, 2).astype(np.float64)
    return pts if len(pts) >= 3 else None


# ─── Decode ────────────────────────────────────────────────────────────────
def _rows(output: np.ndarray, end2end: bool) -> np.ndarray:
    """(1,C,N) veya (1,N,F) ciktiyi (N, ozellik) satirlarina cevirir."""
    out = np.asarray(output)[0]
    return out if end2end else out.T


def decode_detections(output: np.ndarray, task: AnnotationType, nc: int,
                      lb: Letterbox, conf: float, iou: float, end2end: bool,
                      protos: Optional[np.ndarray] = None,
                      kpt_shape: Optional[Tuple[int, int]] = None,
                      input_hw: Tuple[int, int] = (640, 640)) -> List[Prediction]:
    rows = _rows(output, end2end)
    if rows.size == 0:
        return []

    if end2end:
        scores = rows[:, 4]
        classes = rows[:, 5].astype(int)
        extra = rows[:, 6:]
        if task == AnnotationType.OBB:
            boxes = np.concatenate([rows[:, :4], rows[:, 6:7]], axis=1)  # xywhr
            extra = rows[:, 7:]
        else:
            boxes = rows[:, :4]  # xyxy
        sel = scores >= conf
        boxes, scores, classes, extra = boxes[sel], scores[sel], classes[sel], extra[sel]
    else:
        cls_scores = rows[:, 4:4 + nc]
        classes = cls_scores.argmax(1)
        scores = cls_scores[np.arange(len(rows)), classes]
        extra = rows[:, 4 + nc:]
        sel = scores >= conf
        rows, scores, classes, extra = rows[sel], scores[sel], classes[sel], extra[sel]
        if task == AnnotationType.OBB:
            boxes = np.concatenate([rows[:, :4], extra[:, :1]], axis=1)  # xywhr
            extra = extra[:, 1:]
            keep = nms(boxes, scores, classes, iou, rotated=True)
        else:
            boxes = xywh_to_xyxy(rows[:, :4])
            keep = nms(boxes, scores, classes, iou)
        boxes, scores, classes, extra = boxes[keep], scores[keep], classes[keep], extra[keep]

    preds: List[Prediction] = []
    proto_flat = None
    if task == AnnotationType.POLYGON and protos is not None:
        p = np.asarray(protos)[0]
        nm, mh, mw = p.shape
        proto_flat = (p.reshape(nm, -1), nm, mh, mw)

    for i in range(len(scores)):
        cid, sc = int(classes[i]), float(scores[i])
        if task == AnnotationType.OBB:
            corners = xywhr_to_corners(*boxes[i][:5])
            nx, ny = lb.to_norm_xy(corners[:, 0], corners[:, 1])
            ann = OBBAnnotation(cid, [(float(x), float(y)) for x, y in zip(nx, ny)])
        elif task == AnnotationType.POLYGON:
            if proto_flat is None:
                continue
            ann = _decode_mask(boxes[i], extra[i], proto_flat, lb, input_hw, cid)
            if ann is None:
                continue
        elif task == AnnotationType.KEYPOINTS:
            ann = _decode_pose(boxes[i], extra[i], kpt_shape, lb, cid)
        else:
            ann = _bbox_ann(cid, *boxes[i][:4], lb)
        if task != AnnotationType.OBB and task != AnnotationType.POLYGON:
            if getattr(ann, "width", 1) <= 0 or getattr(ann, "height", 1) <= 0:
                continue
        preds.append(Prediction(ann, sc))
    return preds


def _decode_mask(box_xyxy, coeffs, proto_flat, lb: Letterbox,
                 input_hw: Tuple[int, int], cid: int) -> Optional[PolygonAnnotation]:
    import cv2
    flat, nm, mh, mw = proto_flat
    m = 1.0 / (1.0 + np.exp(-(coeffs[:nm] @ flat)))
    m = m.reshape(mh, mw)
    ih, iw = input_hw
    sx, sy = mw / iw, mh / ih
    x1, y1, x2, y2 = box_xyxy[:4]
    crop = np.zeros_like(m)
    cx1, cy1 = max(int(math.floor(x1 * sx)), 0), max(int(math.floor(y1 * sy)), 0)
    cx2, cy2 = min(int(math.ceil(x2 * sx)), mw), min(int(math.ceil(y2 * sy)), mh)
    crop[cy1:cy2, cx1:cx2] = m[cy1:cy2, cx1:cx2]
    up = cv2.resize(crop, (iw, ih), interpolation=cv2.INTER_LINEAR)
    pts = mask_to_polygon(up > 0.5)
    if pts is None:
        return None
    nx, ny = lb.to_norm_xy(pts[:, 0], pts[:, 1])
    return PolygonAnnotation(cid, [(float(x), float(y)) for x, y in zip(nx, ny)])


def _decode_pose(box_xyxy, kpts, kpt_shape, lb: Letterbox, cid: int) -> KeypointsAnnotation:
    bbox = _bbox_ann(cid, *box_xyxy[:4], lb)
    k, ndim = kpt_shape if kpt_shape else (len(kpts) // 3, 3)
    kp = np.asarray(kpts[:k * ndim]).reshape(k, ndim)
    nx, ny = lb.to_norm_xy(kp[:, 0], kp[:, 1])
    out = []
    for j in range(k):
        vis = 2 if ndim < 3 or kp[j, 2] >= 0.5 else 0
        out.append((float(nx[j]) if vis else 0.0, float(ny[j]) if vis else 0.0, vis))
    return KeypointsAnnotation(cid, bbox.x_center, bbox.y_center, bbox.width,
                               bbox.height, out)


def decode_classification(output: np.ndarray, conf: float) -> List[Prediction]:
    probs = np.asarray(output).reshape(-1)
    if probs.size == 0:
        return []
    if probs.min() < 0 or probs.max() > 1.0 + 1e-4 or abs(probs.sum() - 1.0) > 0.05:
        e = np.exp(probs - probs.max())
        probs = e / e.sum()
    top = int(probs.argmax())
    if probs[top] < conf:
        return []
    return [Prediction(ClassificationAnnotation(top), float(probs[top]))]
