# -*- coding: utf-8 -*-
"""Jarvis 共享状态 — 所有模块从此导入全局实例"""
import os
import sys
import json
import time
import re
import socket
import subprocess
import webbrowser
import difflib
from datetime import datetime
from openai import OpenAI
import httpx
import speech_recognition as sr
import pyttsx3
import winsound
import pyautogui

# --- 路径常量 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "jarvis_memory.json")
PERSONALITY_FILE = os.path.join(BASE_DIR, "jarvis_personality.txt")

# --- 模式 ---
TEXT_MODE = '--text' in sys.argv

# --- 唤醒词 ---
WAKE_WORDS = [
    "贾维斯", "jarvis", "hey jarvis", "嘿贾维斯",
    "甲伟斯", "家维斯", "家卫士", "贾伟斯", "贾卫士", "嘉维斯",
    "嘉卫士", "甲维斯", "贾微斯", "家伟斯", "佳维斯",
]
ACK_BEEP = (800, 100)

# --- 人格加载 ---
def load_personality():
    if os.path.exists(PERSONALITY_FILE):
        with open(PERSONALITY_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return "你是贾维斯(Jarvis)，一个AI助手。"

# --- OpenAI 客户端 ---
def _create_client():
    proxy_url = "http://127.0.0.1:7897"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    proxy_alive = s.connect_ex(('127.0.0.1', 7897)) == 0
    s.close()
    if proxy_alive:
        print('[启动] 代理在线，通过代理连接 DeepSeek')
        http_client = httpx.Client(proxy=proxy_url)
    else:
        print('[启动] 代理离线，直连模式')
        http_client = httpx.Client()
    return OpenAI(
        api_key="sk-placeholder",
        base_url="https://api.deepseek.com",
        http_client=http_client,
    )

client = _create_client()

# --- TTS 引擎 ---
engine = pyttsx3.init()
engine.setProperty('rate', 180)
engine.setProperty('volume', 1.0)
voices = engine.getProperty('voices')
for voice in voices:
    if 'chinese' in voice.name.lower() or 'zh' in voice.id.lower():
        engine.setProperty('voice', voice.id)
        break

# --- 语音识别器 ---
recognizer = sr.Recognizer()
recognizer.energy_threshold = 100
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.8

# --- 浏览器 ---
SLBROWSER_PATH = r"C:\Program Files (x86)\Lenovo\SLBrowser\SLBrowser.exe"
webbrowser.register("slbrowser", None, webbrowser.BackgroundBrowser(SLBROWSER_PATH))
browser = webbrowser.get("slbrowser")

# --- pyautogui 安全 ---
pyautogui.FAILSAFE = True

# --- 延迟导入（在 jarvis_memory 等模块加载后初始化） ---
# jarvis_main 会调用 _init_globals() 完成初始化
memory = None
emotion = None
scheduler = None
brain = None
TOOLS = None


def _init_globals():
    """在所有模块加载后初始化全局实例"""
    from jarvis_memory import JarvisMemory
    from jarvis_emotion import EmotionSystem
    from jarvis_scheduler import TaskManager
    from jarvis_brain import AgentBrain
    global memory, emotion, scheduler, brain
    memory = JarvisMemory(MEMORY_FILE)
    emotion = EmotionSystem()
    scheduler = TaskManager()
    brain = AgentBrain()
