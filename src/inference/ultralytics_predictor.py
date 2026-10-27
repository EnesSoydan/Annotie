""".pt modelleri icin opsiyonel ultralytics arka ucu.

ultralytics (ve torch) uygulamanin zorunlu bagimliligi DEGILDIR; yalnizca
kuruluysa .pt modeller dogrudan calistirilir. Aksi halde kullaniciya modeli
ONNX'e export etmesi soylenir.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np

from src.models.annotation import (
    AnnotationType, BBoxAnnotation, ClassificationAnnotation,
    KeypointsAnnotation, OBBAnnotation, PolygonAnnotation,
)
from src.inference.base import (
    InferenceError, ModelMeta, Prediction, Predictor, TASK_FROM_ULTRALYTICS, load_rgb,
)

PT_HINT = ("ultralytics kurulu değil — .pt modelleri çalıştırılamıyor. "
           "Modeli `yolo export model=model.pt format=onnx` ile ONNX'e çevirip "
           ".onnx dosyasını yükleyin.")


def ultralytics_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("ultralytics") is not None
    except Exception:
        return False


def _load(path: Path):
    try:
        from ultralytics import YOLO
    except ImportError:
        raise InferenceError(PT_HINT)
    try:
        return YOLO(str(path))
    except Exception as exc:
        raise InferenceError(f".pt modeli açılamadı: {exc}")


def _meta(model) -> ModelMeta:
    task = TASK_FROM_ULTRALYTICS.get(getattr(model, "task", "detect"), AnnotationType.BBOX)
    names = model.names or {}
    class_names = [str(names[k]) for k in sorted(names)] if isinstance(names, dict) else list(names)
    args = getattr(model.model, "args", {}) or {}
    imgsz = args.get("imgsz") if isinstance(args, dict) else None
    if isinstance(imgsz, (list, tuple)):
        imgsz = imgsz[0]
    kpt = getattr(model.model, "kpt_shape", None) or (
        model.model.yaml.get("kpt_shape") if hasattr(model.model, "yaml") else None)
    kpt_shape = (int(kpt[0]), int(kpt[1])) if kpt else None
    return ModelMeta("pt", task, class_names, int(imgsz) if imgsz else None, kpt_shape)


def read_pt_meta(path: Path) -> ModelMeta:
    return _meta(_load(path))


class UltralyticsPredictor(Predictor):
    def __init__(self, path: Path):
        self._model = _load(path)
        self.meta = _meta(self._model)

    def predict(self, image_path: Path, conf: float = 0.25,
                iou: float = 0.45) -> List[Prediction]:
        rgb = load_rgb(Path(image_path))
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        try:
            r = self._model.predict(bgr, conf=conf, iou=iou, verbose=False)[0]
        except Exception as exc:
            raise InferenceError(f"Tahmin başarısız: {exc}")
        return self._to_predictions(r)

    def _to_predictions(self, r) -> List[Prediction]:
        task = self.meta.task_type
        out: List[Prediction] = []
        if task == AnnotationType.CLASSIFICATION:
            if r.probs is not None:
                out.append(Prediction(ClassificationAnnotation(int(r.probs.top1)),
                                      float(r.probs.top1conf)))
            return out
        if task == AnnotationType.OBB:
            if r.obb is None:
                return out
            pts = r.obb.xyxyxyxyn.cpu().numpy()
            for p, c, s in zip(pts, r.obb.cls.cpu().numpy(), r.obb.conf.cpu().numpy()):
                out.append(Prediction(OBBAnnotation(int(c), [(float(x), float(y)) for x, y in p]),
                                      float(s)))
            return out
        if r.boxes is None:
            return out
        xywhn = r.boxes.xywhn.cpu().numpy()
        cls = r.boxes.cls.cpu().numpy().astype(int)
        conf = r.boxes.conf.cpu().numpy()
        for i in range(len(cls)):
            cx, cy, w, h = (float(v) for v in xywhn[i])
            if task == AnnotationType.POLYGON:
                if r.masks is None or i >= len(r.masks.xyn) or len(r.masks.xyn[i]) < 3:
                    continue
                ann = PolygonAnnotation(int(cls[i]), [(float(x), float(y)) for x, y in r.masks.xyn[i]])
            elif task == AnnotationType.KEYPOINTS and r.keypoints is not None:
                kxy = r.keypoints.xyn[i].cpu().numpy()
                kc = r.keypoints.conf[i].cpu().numpy() if r.keypoints.conf is not None else None
                kps = []
                for j, (x, y) in enumerate(kxy):
                    vis = 2 if kc is None or kc[j] >= 0.5 else 0
                    kps.append((float(x) if vis else 0.0, float(y) if vis else 0.0, vis))
                ann = KeypointsAnnotation(int(cls[i]), cx, cy, w, h, kps)
            else:
                ann = BBoxAnnotation(int(cls[i]), cx, cy, w, h)
            out.append(Prediction(ann, float(conf[i])))
        return out

    def close(self):
        self._model = None
