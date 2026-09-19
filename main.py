# -*- coding: utf-8 -*-
"""
Pristmax Desktop Application Entry Point
"""
import sys
import os

# 获取运行目录（PyInstaller 打包后是 exe 所在目录）
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 添加项目根目录到 Python 路径
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)  # 切换到 exe 所在目录，确保相对路径正确

if __name__ == '__main__':
    # 直接运行 server
    from src.pristmax.api import server
    server.main()
