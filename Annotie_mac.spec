# -*- mode: python ; coding: utf-8 -*-
# Annotie - PyInstaller Mac Spec Dosyasi

from pathlib import Path

block_cipher = None

datas = [
    ('src', 'src'),
    ('icon.png', '.'),   # macOS runtime'da gerekli
]

cloud_config = Path('cloud_config.json')
if cloud_config.exists():
    datas.append((str(cloud_config), '.'))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtPrintSupport',
        'PySide6.QtSvg',
        'PySide6.QtXml',
        'yaml',
        'PIL',
        'PIL.Image',
        'PIL.ImageQt',
        'numpy',
        'src.app',
        'src.utils.constants',
        'src.utils.colors',
        'src.utils.config',
        'src.utils.geometry',
        'src.models.annotation',
        'src.models.label_class',
        'src.models.image_item',
        'src.models.dataset',
        'src.canvas.canvas_scene',
        'src.canvas.canvas_view',
        'src.canvas.items.base_item',
        'src.canvas.items.handle_item',
        'src.canvas.items.bbox_item',
        'src.canvas.items.polygon_item',
        'src.canvas.items.obb_item',
        'src.canvas.items.keypoint_dot',
        'src.canvas.items.keypoint_item',
        'src.canvas.tools.base_tool',
        'src.canvas.tools.select_tool',
        'src.canvas.tools.bbox_tool',
        'src.canvas.tools.polygon_tool',
        'src.canvas.tools.obb_tool',
        'src.canvas.tools.keypoint_tool',
        'src.canvas.tools.classify_tool',
        'src.io.yaml_handler',
        'src.io.label_reader',
        'src.io.label_writer',
        'src.io.dataset_importer',
        'src.io.folder_importer',
        'src.io.dataset_exporter',
        'src.io.image_loader',
        'src.cloud.auth',
        'src.cloud.cloud_config',
        'src.cloud.datasets',
        'src.cloud.images',
        'src.cloud.storage',
        'src.cloud.supabase_client',
        'src.cloud.teams',
        'src.cloud.token_store',
        'src.commands.add_annotation_cmd',
        'src.commands.delete_annotation_cmd',
        'src.commands.change_class_cmd',
        'src.commands.move_annotation_cmd',
        'src.controllers.account_controller',
        'src.controllers.annotation_controller',
        'src.controllers.dataset_controller',
        'src.controllers.autosave_controller',
        'src.widgets.image_list_panel',
        'src.widgets.class_list_panel',
        'src.widgets.annotation_list_panel',
        'src.widgets.split_selector',
        'src.widgets.toolbar',
        'src.widgets.properties_panel',
        'src.widgets.settings_dialog',
        'src.widgets.new_dataset_dialog',
        'src.widgets.export_dialog',
        'src.widgets.import_dialog',
        'src.widgets.auth_dialog',
        'src.widgets.cloud_open_worker',
        'src.widgets.team_workspace_dialog',
        'src.widgets.teams_dialog',
        'src.widgets.upload_worker',
        'src.widgets.main_window',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'notebook',
        'pytest',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Annotie',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,   # macOS icin gerekli
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Annotie',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='Annotie.app',
    icon='icon.icns',
    bundle_identifier='com.annotie.app',
    info_plist={
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'Annotie',
        'CFBundleDisplayName': 'Annotie',
        'NSRequiresAquaSystemAppearance': 'False',  # Dark mode destegi
    },
)
