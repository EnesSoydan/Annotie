"""Sinif renk paleti."""

from PySide6.QtGui import QColor

CLASS_COLORS = [
    QColor(255, 0, 0),        # Kirmizi
    QColor(0, 255, 0),        # Yesil
    QColor(0, 0, 255),        # Mavi
    QColor(255, 255, 0),      # Sari
    QColor(255, 0, 255),      # Magenta
    QColor(0, 255, 255),      # Cyan
    QColor(255, 128, 0),      # Turuncu
    QColor(128, 0, 255),      # Mor
    QColor(0, 255, 128),      # Bahar Yesili
    QColor(255, 0, 128),      # Gul
    QColor(128, 255, 0),      # Lime
    QColor(0, 128, 255),      # Gok Mavisi
    QColor(255, 128, 128),    # Acik Kirmizi
    QColor(128, 255, 128),    # Acik Yesil
    QColor(128, 128, 255),    # Acik Mavi
    QColor(255, 255, 128),    # Acik Sari
    QColor(255, 128, 255),    # Acik Magenta
    QColor(128, 255, 255),    # Acik Cyan
    QColor(192, 64, 0),       # Kahverengi
    QColor(64, 0, 192),       # Indigo
]


def get_class_color(class_id: int) -> QColor:
    """Sinif ID'sine gore renk dondurur."""
    return CLASS_COLORS[class_id % len(CLASS_COLORS)]


def get_class_color_with_alpha(class_id: int, alpha: int = 77) -> QColor:
    """Sinif rengini belirli saydamlikla dondurur."""
    color = QColor(get_class_color(class_id))
    color.setAlpha(alpha)
    return color
