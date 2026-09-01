"""Qt'den bağımsız bbox ölçüm yardımcıları."""


def format_pixel_dimensions(width: float, height: float) -> str:
    """BBox genişlik ve yüksekliğini tek ondalıklı piksel değeri olarak yazar."""
    width = max(0.0, float(width))
    height = max(0.0, float(height))
    return f"{width:.1f} x {height:.1f} px"
