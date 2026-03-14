<div align="center">
  <img src="icon.png" alt="Annotie Logo" width="120"/>
  <h1>Annotie</h1>
  <p>
    YOLO formatında veri seti etiketleme için ücretsiz, açık kaynaklı masaüstü uygulaması<br/>
    Free, open-source desktop annotation tool for YOLO-format datasets
  </p>

  ![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
  ![PySide6](https://img.shields.io/badge/PySide6-Qt6-green?logo=qt&logoColor=white)
  ![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey)
  ![License](https://img.shields.io/badge/License-MIT-yellow)
  ![Release](https://img.shields.io/github/v/release/EnesSoydan/Annotie?color=orange)
</div>

---

## 🇹🇷 Türkçe | 🇬🇧 [English](#-english)

---

## Annotie Nedir?

Annotie, YOLO formatında veri seti oluşturmak ve yönetmek için geliştirilmiş masaüstü görsel etiketleme uygulamasıdır. Tüm YOLO görev tiplerini tek bir araçta destekler — abonelik yok, limit yok, bulut yüklemesi yok.

---

## Özellikler

### Desteklenen Etiket Tipleri
| Tip | YOLO Görevi |
|-----|-------------|
| Bounding Box (BBox) | Detection (Nesne Tespiti) |
| Polygon | Segmentation (Segmentasyon) |
| Oriented Bounding Box (OBB) | OBB Detection |
| Keypoints | Pose Estimation (Poz Tahmini) |
| Classification | Image Classification (Görüntü Sınıflandırma) |

Aynı veri setinde farklı etiket tipleri bir arada kullanılabilir. YOLOv5, v8, v10, v11, v12 ve sonrası ile uyumludur.

### Veri Seti Yönetimi
- Standart YOLO klasör yapısını **otomatik tanır**, `data.yaml` dosyasını (sınıflar, yollar) otomatik okur
- **Train / Validation / Test / Atanmamış** split sistemi — her görsele split atanabilir
- **İki farklı görsel import modu:**
  - `Ekle (Add)` — mevcut split korunur, yeni görseller eklenir
  - `Üzerine Yaz (Replace)` — seçilen split temizlenir, yeni görseller yazılır
- **Etiket import** — başka bir klasördeki `.txt` dosyalarını dosya adı eşleştirme ile mevcut görsellere uygular
- **Export** — standart YOLO yapısında ve otomatik oluşturulan `data.yaml` ile export eder; arka planda çalışır, canlı ilerleme barı gösterir (arayüz donmaz)

### Beklenen Klasör Yapısı

```
dataset/
├── train/
│   ├── images/
│   │   └── image1.jpg
│   └── labels/
│       └── image1.txt
├── valid/
│   ├── images/
│   │   └── image2.jpg
│   └── labels/
│       └── image2.txt
├── test/
│   ├── images/
│   │   └── image3.jpg
│   └── labels/
│       └── image3.txt
└── data.yaml
```

Annotie bu yapıyı açılışta okur, export'ta aynı yapıda yazar — Ultralytics YOLO ile doğrudan kullanıma hazır.

### Etiketleme Arayüzü
- **Tıkla-bırak ile etiket çizimi** — tıkla = etiket koy, sürükle = canvas'ı kaydır
- Zoom seviyesinden bağımsız sabit boyutlu köşe tutamaçları, yalnızca hover/seçimde görünür
- Undo / Redo desteği
- **Otomatik kaydetme** — her değişiklik 200ms içinde `.txt` dosyasına otomatik yazılır

### Navigasyon
- `A` / `D` — önceki / sonraki görsel (tüm görseller)
- `←` / `→` — yalnızca **etiketli** görseller arası geçiş
- Sol panel, klavye navigasyonunda otomatik olarak highlight ve scroll takibi yapar
- Split sekmeleri **göreli numaralandırma** gösterir (Eğitim sekmesindeki 1. görsel, global indeksten bağımsızdır)

### Son Kaldığın Yer (Position Memory)
Büyük veri setlerinde çalışırken en işe yarayan özelliklerden biri:
- Konum **veri seti başına, split başına** (Tümü / Eğitim / Doğrulama / Test) ayrı ayrı kaydedilir
- Yalnızca "Tümü" sekmesinde gezseniz bile, her görselin hangi split'e ait olduğu bilindiğinden split bazlı konumlar da güncellenir
- Her veri seti geçişinde (kapatma, yeni açma, son açılanlar) otomatik kaydedilir
- Bir sonraki açılışta: *"Eğitim kategorisinde 150. frame'de kaldınız"*
- Split sekmesine tıklandığında da o kategorideki son konum gösterilir

### Arayüz / UX
- Koyu tema (Dark mode)
- Toast bildirimleri — yeşil (başarı) / kırmızı (hata), animasyonlu kaybolma
- Veri seti açılışında etiketli / etiketsiz görsel sayısı, `data.yaml` eksikse uyarı
- Son açılan veri setleri listesi, konum hafızasıyla
- Pencere durumu (boyut, panel konumları) kaydedilir ve restore edilir
- **Odak Modu** (`F12`) — tüm paneller gizlenir, yalnızca canvas kalır

---

## İndirme

Hazır kurulum dosyaları [Releases](https://github.com/EnesSoydan/Annotie/releases) sayfasında mevcuttur.

| Platform | Dosya | Gereksinim |
|----------|-------|------------|
| 🪟 Windows | `Annotie-Windows.zip` | Windows 10/11 (64-bit) |
| 🍎 macOS | `Annotie-macOS.zip` | macOS 11.0+ (Intel & Apple Silicon) |

**Windows:** ZIP'i çıkart, `Annotie.exe` dosyasını çalıştır.

**macOS:** ZIP'i çıkart, `Annotie.app` dosyasını Uygulamalar klasörüne taşı. İlk açılışta: Sağ tık → Aç → Aç.

---

## Kaynaktan Çalıştır

```bash
git clone https://github.com/EnesSoydan/Annotie.git
cd Annotie
pip install -r requirements.txt
python main.py
```

**Gereksinimler:** Python 3.10+

```
PySide6>=6.6.0
Pillow>=10.0.0
PyYAML>=6.0
numpy>=1.24.0
```

---

## Lisans

MIT Lisansı — ücretsiz kullanım, değiştirme ve dağıtım serbesttir.

---
---

## 🇬🇧 English

## What is Annotie?

Annotie is a desktop image annotation application built for creating and managing YOLO-format datasets. It supports all major YOLO task types in a single tool — no subscriptions, no limits, no cloud uploads.

---

## Features

### Annotation Types
| Type | YOLO Task |
|------|-----------|
| Bounding Box (BBox) | Detection |
| Polygon | Segmentation |
| Oriented Bounding Box (OBB) | OBB Detection |
| Keypoints | Pose Estimation |
| Classification | Image Classification |

Mixed annotations are supported — different label types can coexist in the same dataset. Compatible with all YOLO versions (v5, v8, v10, v11, v12+).

### Dataset Management
- **Auto-detects** standard YOLO folder structure and reads `data.yaml` (classes, paths) automatically
- **Train / Validation / Test / Unassigned** split system — assign any image to any split
- **Two import modes** for images:
  - `Add` — append new images while keeping existing ones
  - `Replace` — clear the selected split and write fresh
- **Label import** — apply `.txt` annotation files from any folder by matching filenames
- **Export** — produces the standard YOLO structure with an auto-generated `data.yaml`, runs in the background with a live progress bar (UI never freezes)

### Expected Folder Structure

```
dataset/
├── train/
│   ├── images/
│   │   └── image1.jpg
│   └── labels/
│       └── image1.txt
├── valid/
│   ├── images/
│   │   └── image2.jpg
│   └── labels/
│       └── image2.txt
├── test/
│   ├── images/
│   │   └── image3.jpg
│   └── labels/
│       └── image3.txt
└── data.yaml
```

Annotie reads this structure on open and writes it back on export — ready to use directly with Ultralytics YOLO.

### Annotation Interface
- **Click to annotate** — click to place points/boxes, drag to pan the canvas
- Fixed-size corner handles independent of zoom level, visible only on hover/select
- Undo / Redo support
- **Auto-save** — changes are written to `.txt` files within 200ms automatically

### Navigation
- `A` / `D` — previous / next image (all images)
- `←` / `→` — previous / next **labeled** image only
- Image list panel auto-scrolls and highlights current image on keyboard navigation
- Split tabs show **relative numbering** (e.g. image #1 in the Val tab is independent of its global index)

### Last Position Memory
One of the most useful features for large datasets:
- Saves your position **per dataset, per split** (All / Train / Val / Test)
- Even if you only browse in the **All** tab, per-split positions are tracked since each image's split is already known
- Position is saved on every dataset switch — not just on app close
- On next open: *"You left off at frame 150 in the Training split"*
- Clicking a split tab also shows where you left off in that split

### UI / UX
- Dark theme
- Toast notifications — green (success) / red (error) with fade-out animation
- On dataset open: shows labeled vs. unlabeled image count, warns if `data.yaml` is missing
- Recent files list with position memory per dataset
- Window state (size, panel positions) saved and restored
- **Focus Mode** (`F12`) — hides all panels, only the canvas remains

---

## Download

Pre-built binaries are available on the [Releases](https://github.com/EnesSoydan/Annotie/releases) page.

| Platform | File | Requirements |
|----------|------|--------------|
| 🪟 Windows | `Annotie-Windows.zip` | Windows 10/11 (64-bit) |
| 🍎 macOS | `Annotie-macOS.zip` | macOS 11.0+ (Intel & Apple Silicon) |

**Windows:** Extract the ZIP and run `Annotie.exe`

**macOS:** Extract the ZIP, move `Annotie.app` to Applications. On first launch: Right-click → Open → Open

---

## Run from Source

```bash
git clone https://github.com/EnesSoydan/Annotie.git
cd Annotie
pip install -r requirements.txt
python main.py
```

**Requirements:** Python 3.10+

```
PySide6>=6.6.0
Pillow>=10.0.0
PyYAML>=6.0
numpy>=1.24.0
```

---

## License

MIT License — free to use, modify, and distribute.
