# -*- coding: utf-8 -*-
"""Jarvis 快捷入口 — 委托给 jarvis/jarvis_main.py"""
import sys
import os

# 确保 jarvis 包可导入
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis"))

from jarvis_main import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[贾维斯已关闭]")
        sys.exit(0)
