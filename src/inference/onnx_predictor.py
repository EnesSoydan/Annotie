"""onnxruntime tabanli YOLO predictor (ultralytics export'lari)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from src.models.annotation import AnnotationType
from src.inference.base import (
    InferenceError, ModelMeta, Prediction, Predictor, TASK_FROM_ULTRALYTICS, load_rgb,
)
from src.inference import decode


def _literal(value: Optional[str]):
    if value is None:
        return None
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value


def _open_session(path: Path):
    try:
        import onnxruntime as ort
    except ImportError:
        raise InferenceError("onnxruntime kurulu değil (pip install onnxruntime).")
    try:
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
                     if p in ort.get_available_providers()]
        return ort.InferenceSession(str(path), sess_options=opts, providers=providers)
    except Exception as exc:
        raise InferenceError(f"ONNX modeli açılamadı: {exc}")


def _meta_from_session(session) -> Tuple[ModelMeta, bool]:
    md = session.get_modelmeta().custom_metadata_map or {}
    outputs = session.get_outputs()
    task_name = md.get("task")
    if task_name not in TASK_FROM_ULTRALYTICS:
        # Metadata yoksa cikti seklinden tahmin et
        if len(outputs) >= 2:
            task_name = "segment"
        elif len(outputs[0].shape) == 2:
            task_name = "classify"
        else:
            task_name = "detect"
    task = TASK_FROM_ULTRALYTICS[task_name]

    names = _literal(md.get("names"))
    if isinstance(names, dict):
        class_names = [str(names[k]) for k in sorted(names, key=lambda k: int(k))]
    elif isinstance(names, (list, tuple)):
        class_names = [str(n) for n in names]
    else:
        class_names = []

    imgsz = _literal(md.get("imgsz"))
    if isinstance(imgsz, (list, tuple)) and imgsz:
        imgsz = int(imgsz[0])
    elif not isinstance(imgsz, int):
        imgsz = None

    kpt = _literal(md.get("kpt_shape"))
    kpt_shape = (int(kpt[0]), int(kpt[1])) if isinstance(kpt, (list, tuple)) and len(kpt) == 2 else None

    end2end = str(md.get("end2end", "")).lower() == "true"
    if not class_names:
        shape = outputs[0].shape
        nc = None
        if task == AnnotationType.CLASSIFICATION and isinstance(shape[-1], int):
            nc = shape[-1]
        elif not end2end and len(shape) == 3 and isinstance(shape[1], int):
            extra = {AnnotationType.OBB: 1,
                     AnnotationType.KEYPOINTS: kpt_shape[0] * kpt_shape[1] if kpt_shape else 0}
            nc = shape[1] - 4 - extra.get(task, 0)
            if task == AnnotationType.POLYGON and len(outputs) > 1:
                nc -= outputs[1].shape[1] if isinstance(outputs[1].shape[1], int) else 32
        class_names = [f"class_{i}" for i in range(max(nc or 0, 0))]

    return ModelMeta("onnx", task, class_names, imgsz, kpt_shape), end2end


def read_onnx_meta(path: Path) -> ModelMeta:
    return _meta_from_session(_open_session(path))[0]


class OnnxPredictor(Predictor):
    def __init__(self, path: Path):
        self._session = _open_session(path)
        self.meta, self._end2end = _meta_from_session(self._session)
        inp = self._session.get_inputs()[0]
        self._input_name = inp.name
        h, w = (inp.shape[2], inp.shape[3]) if len(inp.shape) == 4 else (None, None)
        default = self.meta.imgsz or (224 if self.meta.task_type == AnnotationType.CLASSIFICATION else 640)
        self._in_h = h if isinstance(h, int) else default
        self._in_w = w if isinstance(w, int) else default
        if self.meta.task_type == AnnotationType.KEYPOINTS and not self.meta.kpt_shape:
            raise InferenceError("Pose modelinde kpt_shape bilgisi yok (ultralytics ile export edin).")

    def predict(self, image_path: Path, conf: float = 0.25,
                iou: float = 0.45) -> List[Prediction]:
        img = load_rgb(Path(image_path))
        if self.meta.task_type == AnnotationType.CLASSIFICATION:
            x = decode.to_tensor(self._center_crop(img))
            out = self._session.run(None, {self._input_name: x})
            return decode.decode_classification(out[0], conf)

        padded, lb = decode.letterbox(img, self._in_w, self._in_h)
        outs = self._session.run(None, {self._input_name: decode.to_tensor(padded)})
        protos = next((o for o in outs[1:] if np.asarray(o).ndim == 4), None)
        return decode.decode_detections(
            outs[0], self.meta.task_type, len(self.meta.class_names), lb, conf, iou,
            self._end2end, protos=protos, kpt_shape=self.meta.kpt_shape,
            input_hw=(self._in_h, self._in_w),
        )

    def _center_crop(self, img: np.ndarray) -> np.ndarray:
        """Ultralytics classify_transforms: kisa kenari boyuta getir + ortadan kirp."""
        import cv2
        h, w = img.shape[:2]
        size = min(self._in_h, self._in_w)
        r = size / min(h, w)
        img = cv2.resize(img, (max(size, int(round(w * r))), max(size, int(round(h * r)))),
                         interpolation=cv2.INTER_LINEAR)
        h, w = img.shape[:2]
        top, left = (h - self._in_h) // 2, (w - self._in_w) // 2
        return img[top:top + self._in_h, left:left + self._in_w]

    def close(self):
        self._session = None
