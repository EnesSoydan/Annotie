"""Koordinat normalizasyonu ve geometri islemleri."""

import math
import numpy as np
from typing import List, Tuple


def normalize_point(x: float, y: float, img_w: int, img_h: int) -> Tuple[float, float]:
    """Piksel koordinatini normalize eder (0-1)."""
    return x / img_w, y / img_h


def denormalize_point(nx: float, ny: float, img_w: int, img_h: int) -> Tuple[float, float]:
    """Normalize koordinati piksele cevirir."""
    return nx * img_w, ny * img_h


def normalize_bbox(x: float, y: float, w: float, h: float,
                   img_w: int, img_h: int) -> Tuple[float, float, float, float]:
    """Piksel bbox'i normalize eder. Girdi: x_center, y_center, w, h piksel."""
    return x / img_w, y / img_h, w / img_w, h / img_h


def denormalize_bbox(nx: float, ny: float, nw: float, nh: float,
                     img_w: int, img_h: int) -> Tuple[float, float, float, float]:
    """Normalize bbox'i piksele cevirir."""
    return nx * img_w, ny * img_h, nw * img_w, nh * img_h


def normalize_points(points: List[Tuple[float, float]],
                     img_w: int, img_h: int) -> List[Tuple[float, float]]:
    """Piksel noktalarini normalize eder."""
    return [(x / img_w, y / img_h) for x, y in points]


def denormalize_points(points: List[Tuple[float, float]],
                       img_w: int, img_h: int) -> List[Tuple[float, float]]:
    """Normalize noktalari piksele cevirir."""
    return [(x * img_w, y * img_h) for x, y in points]


def rect_to_center_wh(x1: float, y1: float, x2: float, y2: float) -> Tuple[float, float, float, float]:
    """Sol-ust/sag-alt koselerden merkez+boyut formatina cevirir."""
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    return cx, cy, w, h


def center_wh_to_rect(cx: float, cy: float, w: float, h: float) -> Tuple[float, float, float, float]:
    """Merkez+boyut formatindan sol-ust/sag-alt koselere cevirir."""
    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2
    return x1, y1, x2, y2


def obb_from_3_points(p1: Tuple[float, float], p2: Tuple[float, float],
                      p3: Tuple[float, float]) -> List[Tuple[float, float]]:
    """3 noktadan OBB'nin 4 kosesini hesaplar.
    p1-p2: bir kenar, p3: genislik yonunu belirler.
    """
    # p1-p2 kenar vektoru
    edge_x = p2[0] - p1[0]
    edge_y = p2[1] - p1[1]

    # Kenar uzunlugu
    edge_len = math.sqrt(edge_x ** 2 + edge_y ** 2)
    if edge_len < 1e-10:
        return [p1, p1, p1, p1]

    # Birim kenar vektoru
    ux = edge_x / edge_len
    uy = edge_y / edge_len

    # Dik vektor
    nx = -uy
    ny = ux

    # p3'un kenar dogrusuna dik mesafesi
    v3x = p3[0] - p1[0]
    v3y = p3[1] - p1[1]
    width = v3x * nx + v3y * ny

    # 4 kose
    c1 = p1
    c2 = p2
    c3 = (p2[0] + nx * width, p2[1] + ny * width)
    c4 = (p1[0] + nx * width, p1[1] + ny * width)

    return [c1, c2, c3, c4]


def polygon_area(points: List[Tuple[float, float]]) -> float:
    """Shoelace formulu ile polygon alanini hesaplar."""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return abs(area) / 2.0


def point_in_polygon(point: Tuple[float, float],
                     polygon: List[Tuple[float, float]]) -> bool:
    """Ray casting ile noktanin polygon icinde olup olmadigini kontrol eder."""
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def clip_point_to_bounds(x: float, y: float,
                         img_w: int, img_h: int) -> Tuple[float, float]:
    """Noktayi gorsel sinirlari icinde tutar."""
    return max(0, min(x, img_w)), max(0, min(y, img_h))


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Iki nokta arasi mesafe."""
    return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
