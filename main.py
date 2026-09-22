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
    import argparse
    parser = argparse.ArgumentParser(description='Pristmax - 智能存储管家')
    parser.add_argument('--port', type=int, default=5001, help='端口')
    parser.add_argument('--host', default='0.0.0.0', help='主机')
    args = parser.parse_args()

    print(f"\n[Pristmax] Starting Storage Agent...")
    print(f"   Web UI: http://localhost:{args.port}/")
    print(f"   Press Ctrl+C to stop\n")

    # 使用 CLI API（简单版本，带 Web UI）
    from src.pristmax.agent.api import app
    app.run(host=args.host, port=args.port, debug=False)
