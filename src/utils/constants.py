"""Uygulama genelinde kullanilan sabitler."""

APP_NAME = "Annotie"
APP_VERSION = "1.1.1"
ORG_NAME = "Annotie"

SUPPORTED_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp']
LABEL_EXTENSION = '.txt'
YAML_FILENAME = 'data.yaml'

DEFAULT_AUTOSAVE_INTERVAL = 60  # saniye
INSTANT_SAVE_DEBOUNCE_MS = 200  # milisaniye

MIN_BBOX_SIZE = 5  # piksel
HANDLE_SIZE = 8  # piksel
CROSSHAIR_SIZE = 20  # piksel

DEFAULT_IMAGE_CACHE_SIZE = 50

ZOOM_IN_FACTOR = 1.25
ZOOM_OUT_FACTOR = 0.8
MIN_ZOOM = 0.05
MAX_ZOOM = 50.0

# Varsayilan split oranlari
DEFAULT_TRAIN_RATIO = 0.7
DEFAULT_VAL_RATIO = 0.2
DEFAULT_TEST_RATIO = 0.1
