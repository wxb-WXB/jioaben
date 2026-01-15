# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ('folder.db', '.'),
]

datas += collect_data_files('pyfiglet')


binaries = []

hiddenimports = [
    'peewee',
    'pyfiglet',
    'fitz',
    'LingyanEmptyAi',
    'models',
    'utils',

    # requests 相关
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
]

a = Analysis(
    ['autoUploadsApp.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='autoUploadsApp',
    console=True,
)
