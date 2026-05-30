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
from jarvis_logger import get_logger

log = get_logger("config")


def sanitize_text(text):
    """清理字符串中的非法 surrogate 字符，防止 UTF-8 编码失败"""
    if not isinstance(text, str):
        return text
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _sanitize_recursive(obj):
    """递归清理对象中所有字符串的 surrogate 字符"""
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_recursive(v) for v in obj]
    return obj

# --- 加载 .env ---
def _load_env():
    """从 .env 文件加载环境变量（不依赖 python-dotenv）"""
    env_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key, value = key.strip(), value.strip().strip("\"'")
                        if key not in os.environ:
                            os.environ[key] = value
            log.info(f"已加载环境变量: {env_path}")
            return
    log.warning("未找到 .env 文件，使用系统环境变量")

# --- 路径常量 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "jarvis_memory.json")
PERSONALITY_FILE = os.path.join(BASE_DIR, "jarvis_personality.txt")

# --- 加载环境变量 ---
_load_env()

# --- API 配置 ---
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

if not DEEPSEEK_API_KEY:
    log.error("未设置 DEEPSEEK_API_KEY！请在 .env 文件中配置")
    DEEPSEEK_API_KEY = "sk-placeholder"  # 避免启动崩溃

# --- 模式 ---
TEXT_MODE = '--text' in sys.argv
GUI_MODE = '--gui' in sys.argv
_gui_queue = None  # GUI 模式时由 jarvis_main 设置

# --- 麦克风设备索引 (None=系统默认设备) ---
MIC_DEVICE_INDEX = None

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
class _SafeChatCompletions:
    """包装 chat.completions.create，自动清理所有输入中的 surrogate 字符"""
    def __init__(self, original):
        self._orig = original

    def create(self, **kwargs):
        if "messages" in kwargs:
            kwargs["messages"] = _sanitize_recursive(kwargs["messages"])
        return self._orig.create(**kwargs)


class _SafeClient:
    """包装 OpenAI client，拦截 chat.completions 调用"""
    def __init__(self, raw_client):
        self._raw = raw_client
        self.chat = type(self)._SafeChat(self._raw.chat)

    class _SafeChat:
        def __init__(self, raw_chat):
            self._raw_chat = raw_chat
            self.completions = _SafeChatCompletions(raw_chat.completions)

    def __getattr__(self, name):
        return getattr(self._raw, name)


def _create_client():
    proxy_url = "http://127.0.0.1:7897"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    proxy_alive = s.connect_ex(('127.0.0.1', 7897)) == 0
    s.close()
    if proxy_alive:
        log.info("代理在线，通过代理连接 DeepSeek")
        http_client = httpx.Client(proxy=proxy_url)
    else:
        log.info("代理离线，直连模式")
        http_client = httpx.Client()
    raw = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        http_client=http_client,
    )
    return _SafeClient(raw)

client = _create_client()

# --- TTS 引擎 (pyttsx3 本地回退) ---
engine = pyttsx3.init()
engine.setProperty('rate', 180)
engine.setProperty('volume', 1.0)
voices = engine.getProperty('voices')
for voice in voices:
    if 'chinese' in voice.name.lower() or 'zh' in voice.id.lower():
        engine.setProperty('voice', voice.id)
        break

# --- Edge TTS (在线高质量语音) ---
EDGE_VOICE = "zh-CN-XiaoxiaoNeural"  # 默认：晓晓（女，温暖）
EDGE_VOICES = [
    ("zh-CN-XiaoxiaoNeural", "晓晓 (女·温暖)"),
    ("zh-CN-YunxiNeural",     "云希 (男·阳光)"),
    ("zh-CN-YunyangNeural",   "云扬 (男·专业)"),
    ("zh-CN-YunjianNeural",   "云健 (男·激情)"),
    ("zh-CN-YunxiaNeural",    "云夏 (男·可爱)"),
    ("zh-CN-XiaoyiNeural",    "晓伊 (女·活泼)"),
]
EDGE_ENABLED = True  # 是否启用 Edge TTS（离线时自动回退 pyttsx3）

import asyncio as _asyncio
import edge_tts as _edge_tts
import tempfile as _tempfile
import pygame.mixer as _pygame_mixer
import time as _time


def speak_tts(text, voice=None):
    """统一的 TTS 输出：Edge TTS 优先，pyttsx3 回退"""
    global EDGE_ENABLED
    if voice is None:
        voice = EDGE_VOICE

    if EDGE_ENABLED:
        try:
            # 静音/空白文本 跳过
            clean = text.strip()
            if not clean or clean.startswith("<<silent"):
                return

            async def _gen():
                comm = _edge_tts.Communicate(clean, voice)
                with _tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    tmp = f.name
                await comm.save(tmp)
                return tmp

            tmp_path = _asyncio.run(_gen())

            _pygame_mixer.init()
            _pygame_mixer.music.load(tmp_path)
            _pygame_mixer.music.play()
            while _pygame_mixer.music.get_busy():
                _time.sleep(0.05)
            _pygame_mixer.quit()

            os.unlink(tmp_path)
            return
        except Exception as e:
            log.warning(f"Edge TTS 失败，回退 pyttsx3: {e}")
            EDGE_ENABLED = False  # 自动回退

    # pyttsx3 回退
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception:
        EDGE_ENABLED = False

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
