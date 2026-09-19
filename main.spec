# -*- coding: utf-8 -*-
"""
Pristmax PyInstaller Spec File
"""
import sys
import os

block_cipher = None

# 项目根目录
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # 产品控制台
        ('src/pristmax/web', 'src/pristmax/web'),
        # 营销网站
        ('src/pristmax/site', 'src/pristmax/site'),
        # 图标资源
        ('unified/assets/brand', 'src/pristmax/assets/brand'),
    ],
    hiddenimports=[
        'flask', 'flask_cors', 'werkzeug', 'jinja2',
        'src.pristmax.auth', 'src.pristmax.monitor',
        'src.pristmax.scheduler', 'src.pristmax.storage',
        'src.pristmax.api.server', 'src.pristmax.api.task_processor',
        'src.pristmax.dedup',
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Pristmax',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windows GUI 模式，无黑窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
