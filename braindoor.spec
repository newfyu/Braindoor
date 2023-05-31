# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['braindoor.py'],
    pathex=['./'],
    binaries=[],
    datas=[        
	('ui/style.css','ui/'),
    ('ui/script.js','ui/'),
    ('config.yaml','.'),
	('extra_files/gradio/*','gradio/'),
	('extra_files/gradio_client/*','gradio_client/'),
	('prompts/*','prompts/'),
	('models/*','models/'),
	('extra_files/tiktoken/*','tiktoken/'),
	('extra_files/tiktoken_ext/*','tiktoken_ext/')
],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='braindoor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='braindoor',
)
