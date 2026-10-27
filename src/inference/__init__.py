"""Otomatik etiketleme: model yukleme ve cikarim (Qt'den bagimsiz)."""

from __future__ import annotations

from pathlib import Path

from src.inference.base import (  # noqa: F401
    InferenceError, MODEL_FORMATS, ModelMeta, Prediction, Predictor,
)


def model_format(path) -> str:
    fmt = MODEL_FORMATS.get(Path(path).suffix.lower())
    if fmt is None:
        raise InferenceError("Desteklenen model formatları: .onnx, .pt")
    return fmt


def read_model_meta(path) -> ModelMeta:
    """Model dosyasindan gorev tipi / siniflar / imgsz bilgisini okur."""
    path = Path(path)
    if model_format(path) == "onnx":
        from src.inference.onnx_predictor import read_onnx_meta
        return read_onnx_meta(path)
    from src.inference.ultralytics_predictor import read_pt_meta
    return read_pt_meta(path)


def load_predictor(path) -> Predictor:
    path = Path(path)
    if model_format(path) == "onnx":
        from src.inference.onnx_predictor import OnnxPredictor
        return OnnxPredictor(path)
    from src.inference.ultralytics_predictor import UltralyticsPredictor
    return UltralyticsPredictor(path)
