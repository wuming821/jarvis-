# -*- coding: utf-8 -*-
"""Jarvis 电脑控制底层 — 鼠标/键盘/截图/程序"""
import time
import os
from datetime import datetime
import pyautogui
from jarvis_logger import get_logger

log = get_logger("computer")


def get_screen_size():
    s = pyautogui.size()
    return s.width, s.height


def screenshot(filepath=None):
    if filepath is None:
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    pyautogui.screenshot(filepath)
    log.debug(f"截图已保存: {filepath}")
    return filepath


def get_mouse_pos():
    p = pyautogui.position()
    return p.x, p.y


def move_mouse(x, y):
    pyautogui.moveTo(x, y)


def click(x=None, y=None):
    pyautogui.click(x, y)


def double_click(x=None, y=None):
    pyautogui.doubleClick(x, y)


def right_click(x=None, y=None):
    pyautogui.rightClick(x, y)


def mouse_scroll(amount):
    pyautogui.scroll(int(amount))


def type_unicode(text):
    pyautogui.write(text)


def press_key(key):
    pyautogui.press(key)


def hotkey(*keys):
    pyautogui.hotkey(*keys)


def open_windows_search():
    pyautogui.press('win')
    time.sleep(0.3)


def run_program(program_name):
    open_windows_search()
    time.sleep(0.2)
    pyautogui.write(program_name)
    time.sleep(0.3)
    pyautogui.press('enter')
    log.info(f"已运行程序: {program_name}")


def open_url(url, browser):
    browser.open(url)
    log.debug(f"已打开URL: {url}")
