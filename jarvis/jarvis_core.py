# -*- coding: utf-8 -*-
"""Jarvis Runtime — 语音/对话/系统提示/指令处理"""
import json
import os
import re
import time
import difflib
import subprocess
from datetime import datetime
import winsound
import pyautogui
import jarvis_config as cfg
from jarvis_config import (client, engine, recognizer, browser, TEXT_MODE, BASE_DIR,
                            WAKE_WORDS, ACK_BEEP, load_personality)
from jarvis_emotion import (EmotionSystem, update_emotion_from_input,
                             detect_user_emotion, get_user_emotion_context)
from jarvis_scheduler import TaskManager
from jarvis_brain import AgentBrain
from jarvis_tools import execute_tool, TOOLS
from jarvis_agents import _run_agent
from jarvis_computer import screenshot, get_mouse_pos, get_screen_size
from jarvis_logger import get_logger, retry_on_failure

log = get_logger("core")


# ======================================================
#  系统提示
# ======================================================
BASE_FUNCTIONAL_PROMPT = (
    "\n\n## 工具使用原则"
    "\n你拥有操作电脑和获取信息的工具。"
    "\n当用户要求实际操作时，直接调用工具完成任务，而不是告诉用户'请点击xxx'。"
    "\n\n## 长期记忆（重要！）"
    "\n每次对话开始时会自动语义检索相关记忆并注入上下文。"
    "\n你也可以手动调用 retrieve_memories 获取与话题最相关的记忆。"
    "\n用户在对话中透露的个人信息，你必须主动调用 remember_fact 保存，"
    "\n不要等用户说'记住xxx'。需要记住的信息包括："
    "\n- 个人信息：生日、年龄、职业、所在城市、学校/公司"
    "\n- 偏好习惯：喜欢/讨厌什么、常用工具、作息习惯"
    "\n- 计划事件：约定、日程、待办事项"
    "\n- 人际关系：家人、朋友、同事的名字和关系"
    "\n如果用户说的事情和旧记忆矛盾，用 importance='high' 保存新信息（会自动标记旧记忆过时）。"
    "\n一般信息用 importance='medium'，特别重要的用 importance='high'。"
    "\n\n## 多工具协作"
    "\n复杂任务需要链式调用多个工具。你要主动把任务拆成步骤："
    "\n- 例如'帮我在记事本写今天的日期'：run_program_tool(记事本)→wait→get_time→computer_type(日期)→汇报"
    "\n- 例如'搜索Python教程并截图'：search_web(Python教程)→wait→take_screenshot→汇报"
    "\n- 如果上一步失败了，尝试其他方式，不要放弃"
    "\n- 每轮可以同时调用多个互不依赖的工具（如同时截图+获取时间）"
    "\n调用完所有工具后简洁汇报结果，不要啰嗦。"
    "\n\n## 自主执行"
    "\n当用户说'帮我完成xxx'或'直接帮我把xxx做了'这类需要实际操作的任务时，"
    "\n使用 autonomous_execute 工具。它会自动规划步骤并逐步执行，无需用户逐一确认。"
    "\n如果是只需要规划不需要执行的，用 make_plan。"
    "\n\n## 反思与自我改进"
    "\n每次通过 autonomous_execute 自主执行完任务后，系统会自动反思。"
    "\n你也可以手动调用 reflect 工具对任意任务进行反思。"
    "\n反思会提炼经验教训并存入长期记忆，帮助你在未来做得更好。"
    "\n\n## 多Agent协作"
    "\n你有4个专门的子Agent可以派遣："
    "\n- researcher(研究员)：搜索信息、收集资料、总结报告"
    "\n- executor(执行者)：操控电脑，打开程序、点击、输入、截图"
    "\n- reflector(反思者)：分析结果、提炼教训、更新记忆"
    "\n- planner(规划师)：拆解复杂目标为详细步骤"
    "\n遇到复杂任务时，用 spawn_agent 派遣多个子Agent并行工作。"
    "\n例如：同时派遣researcher查资料+executor打开记事本准备记录。"
)


def build_system_prompt():
    personality = load_personality()
    facts = cfg.memory.get_facts_context()
    reflections = cfg.memory.get_reflections_context()
    mood = cfg.emotion.get_context()
    user_emo = get_user_emotion_context()
    return personality + mood + user_emo + BASE_FUNCTIONAL_PROMPT + "\n" + facts + reflections


# ======================================================
#  对话历史
# ======================================================
messages = []
MAX_HISTORY = 20


def _init_messages():
    """确保 messages[0] 始终是系统提示（等 memory/emotion 就绪后调用）"""
    global messages
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": build_system_prompt()})


def _save_conversations():
    saved = []
    for m in messages[1:]:
        if m["role"] == "user":
            saved.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant" and m.get("content"):
            saved.append({"role": "assistant", "content": m["content"]})
    cfg.memory.save(conversations=saved, emotion=cfg.emotion, scheduler=cfg.scheduler, brain=cfg.brain)


def _load_conversations():
    saved, emo_data, sch_data, brain_data = cfg.memory.load()
    cfg.emotion = EmotionSystem.from_dict(emo_data)
    cfg.scheduler = TaskManager.from_dict(sch_data)
    cfg.brain = AgentBrain.from_dict(brain_data)
    if saved:
        messages.extend(saved)


# ======================================================
#  唤醒词检测
# ======================================================
def _find_wake_word(text):
    t = text.lower()
    for ww in WAKE_WORDS:
        idx = t.find(ww)
        if idx != -1:
            return ww, idx, len(ww)
    TARGET = "贾维斯"
    for i in range(len(t) - len(TARGET) + 1):
        window = t[i:i + len(TARGET)]
        if difflib.SequenceMatcher(None, TARGET, window).ratio() >= 0.5:
            return TARGET, i, len(TARGET)
    return None, -1, 0


# ======================================================
#  语音 + TTS
# ======================================================
def speak(text):
    print(f'贾维斯: {text}')
    engine.say(text)
    engine.runAndWait()


def listen_text():
    try:
        text = input('\n你: ').strip()
        return text
    except (EOFError, KeyboardInterrupt):
        return "退出"


def listen():
    import speech_recognition as sr
    with sr.Microphone(device_index=cfg.MIC_DEVICE_INDEX) as source:
        print('\n[正在听...]')
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return ""
    for method, name in [
        (lambda a: recognizer.recognize_whisper(a, model="small", language="zh"), "Whisper"),
        (lambda a: recognizer.recognize_google(a, language="zh-CN"), "Google"),
    ]:
        try:
            text = method(audio).strip()
            print(f'你: {text}')
            return text
        except Exception as e:
            print(f'[{name} 识别失败: {e}]')
    return ""


# ======================================================
#  AI 工具对话引擎
# ======================================================
MAX_TOOL_ROUNDS = 8


def _auto_retrieve_context(user_input):
    retrieved = cfg.memory.retrieve_relevant(user_input)
    if retrieved:
        return f"\n[相关记忆]\n{retrieved}"
    return ""


def chat_with_tools(user_input):
    update_emotion_from_input(cfg.emotion, user_input)
    detect_user_emotion(user_input)

    memory_ctx = _auto_retrieve_context(user_input)
    augmented_input = user_input + memory_ctx if memory_ctx else user_input
    messages.append({"role": "user", "content": augmented_input})
    if len(messages) > MAX_HISTORY + 1:
        del messages[1:3]

    messages[0]["content"] = build_system_prompt()

    for round_idx in range(MAX_TOOL_ROUNDS):
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-pro", messages=messages,
                tools=TOOLS, temperature=0.8, max_tokens=2000,
            )
        except Exception as e:
            return f"抱歉先生，系统出了点问题: {e}"

        choice = response.choices[0]
        msg = choice.message

        if msg.tool_calls:
            tool_count = len(msg.tool_calls)
            if tool_count > 1:
                print(f"  [第{round_idx+1}轮] AI 并行调用 {tool_count} 个工具:")

            messages.append({
                "role": "assistant", "content": msg.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {
                        "name": tc.function.name, "arguments": tc.function.arguments,
                    }} for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                prefix = "    ├" if tc != msg.tool_calls[-1] else "    └"
                try:
                    result = execute_tool(tool_name, arguments)
                    print(f"  {prefix} {tool_name}({arguments}) → {result[:60]}")
                except Exception as e:
                    result = f"工具执行出错: {e}"
                    print(f"  {prefix} {tool_name}({arguments}) ✗ {e}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            continue

        reply = msg.content or ""
        messages.append({"role": "assistant", "content": reply})
        _save_conversations()
        return reply

    return "抱歉先生，这个任务步骤有点多，请拆成几个小任务让我逐步完成。"


# ======================================================
#  本地指令处理
# ======================================================
def handle_command(cmd):
    c = cmd.lower()

    # 打开网站
    site_map = [
        (["b站", "bilibili", "哔站", "哔哩哔哩"], "https://www.bilibili.com", "B站"),
        (["youtube", "油管"], "https://www.youtube.com", "YouTube"),
        (["百度", "baidu"], "https://www.baidu.com", "百度"),
        (["谷歌", "google"], "https://www.google.com", "谷歌"),
        (["github"], "https://github.com", "GitHub"),
        (["知乎"], "https://www.zhihu.com", "知乎"),
        (["淘宝"], "https://www.taobao.com", "淘宝"),
        (["京东"], "https://www.jd.com", "京东"),
        (["微博"], "https://weibo.com", "微博"),
    ]
    for keywords, url, name in site_map:
        for kw in keywords:
            if kw in c:
                speak(f"正在打开{name}")
                browser.open(url)
                return None, True

    # 搜索引擎
    for prefix in ["搜索", "搜一下", "帮我搜", "查一下"]:
        if prefix in c:
            idx = c.index(prefix) + len(prefix)
            query = cmd[idx:].strip()
            if query:
                browser.open(f"https://www.google.com/search?q={query}")
                speak(f"正在搜索{query}")
                return None, True

    # 打开程序
    if "记事本" in c or "notepad" in c:
        subprocess.Popen("notepad.exe"); speak("记事本已打开"); return None, True
    if "计算器" in c or "calculator" in c:
        subprocess.Popen("calc.exe"); speak("计算器已打开"); return None, True
    if "命令行" in c or "cmd" in c or "终端" in c:
        subprocess.Popen("cmd.exe"); speak("命令行已打开"); return None, True
    if "浏览器" in c or "上网" in c or "打开网页" in c or "browser" in c:
        browser.open("https://www.google.com"); speak("浏览器已打开"); return None, True
    if "任务管理器" in c:
        subprocess.Popen("taskmgr.exe"); speak("任务管理器已打开"); return None, True
    if "设置" in c or "settings" in c:
        subprocess.Popen("ms-settings:"); speak("设置已打开"); return None, True
    if "vs code" in c or "vscode" in c or "写代码" in c or "coding" in c:
        subprocess.Popen(r"C:\Users\sp\AppData\Local\Programs\Microsoft VS Code\Code.exe")
        speak("VS Code 已打开"); return None, True

    # 系统控制
    if "锁屏" in c or "锁定" in c:
        subprocess.Popen("rundll32.exe user32.dll,LockWorkStation"); speak("屏幕已锁定"); return None, True
    if "静音" in c or "mute" in c:
        pyautogui.press('volumemute'); speak("已静音"); return None, True
    if "音量增大" in c or "大点声" in c or "声音大" in c or "提高音量" in c:
        pyautogui.press('volumeup', presses=3); return "<<silent>>", True
    if "音量减小" in c or "小点声" in c or "声音小" in c or "降低音量" in c:
        pyautogui.press('volumedown', presses=3); return "<<silent>>", True

    # 信息查询
    if "几点" in c or "时间" in c or "日期" in c or "今天几号" in c or "星期几" in c:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        wd = weekdays[now.weekday()]
        return f"现在是{now.year}年{now.month}月{now.day}日，{wd}，{now.hour}点{now.minute}分", True

    # 电脑控制（直接指令）
    if "截图" in c or "截屏" in c:
        path = screenshot(); return f"截图已保存到桌面，先生。", True
    if "鼠标位置" in c or "鼠标在哪" in c:
        x, y = get_mouse_pos(); w, h = get_screen_size()
        return f"鼠标在 ({x}, {y})，屏幕分辨率 {w}x{h}，先生。", True
    if "滚动" in c:
        m = re.search(r'滚动.*?(-?\d+)', c)
        amount = int(m.group(1)) if m else 3
        if "下" in c: amount = -abs(amount)
        pyautogui.scroll(amount); return "<<silent>>", True

    mo = re.match(r'移动鼠标到\s*(\d+)[,，\s]+(\d+)', cmd)
    if mo:
        x, y = int(mo.group(1)), int(mo.group(2))
        pyautogui.moveTo(x, y); return f"鼠标已移到 ({x}, {y})", True

    mo = re.match(r'(?:点击|单击)\s*(\d+)[,，\s]+(\d+)', cmd)
    if mo:
        pyautogui.click(int(mo.group(1)), int(mo.group(2))); return "已点击", True

    mo = re.match(r'双击\s*(\d+)[,，\s]+(\d+)', cmd)
    if mo:
        pyautogui.doubleClick(int(mo.group(1)), int(mo.group(2))); return "已双击", True

    mo = re.match(r'右键\s*(\d+)[,，\s]+(\d+)', cmd)
    if mo:
        pyautogui.rightClick(int(mo.group(1)), int(mo.group(2))); return "已右键", True

    if "输入" in c:
        idx = c.index("输入") + 2; text = cmd[idx:].strip()
        if text: pyautogui.write(text); return f"已输入「{text}」", True

    mo = re.match(r'按(.+?)键', cmd)
    if mo: pyautogui.press(mo.group(1).strip()); return "<<silent>>", True

    if "组合键" in c:
        mo = re.search(r'组合键\s*(.+)', cmd)
        if mo:
            keys = [k.strip() for k in mo.group(1).split()]
            pyautogui.hotkey(*keys); return "<<silent>>", True

    # 用户档案（本地快速提取）
    _profile_patterns = [
        (["我叫", "我是", "我的名字"], "名字"),
        (["我喜欢", "我爱", "我爱好"], "爱好"),
        (["我生日", "我的生日"], "生日"),
        (["我住在", "我家在", "我在...住"], "住址"),
        (["我在...工作", "我的工作是", "我公司", "我在...上班"], "工作"),
        (["我在...上学", "我在...读书", "我的学校", "我大学"], "学校"),
        (["我手机", "我电话", "我的号码"], "电话"),
    ]
    for keywords, field in _profile_patterns:
        for kw in keywords:
            if kw in c:
                val = cmd[cmd.index(kw) + len(kw):].strip()
                if val: cfg.memory.set_profile(field, val); cfg.memory.save(emotion=cfg.emotion, scheduler=cfg.scheduler, brain=cfg.brain); return f"已记住你的{field}，先生。", True

    # 记忆管理
    if "记住" in c or "记下" in c:
        for prefix in ["记住", "记下"]:
            if prefix in c:
                idx = c.index(prefix) + len(prefix); fact = cmd[idx:].strip()
                if fact: cfg.memory.add_fact(fact, "high"); cfg.memory.save(emotion=cfg.emotion, scheduler=cfg.scheduler, brain=cfg.brain); return f"已记住「{fact}」[高优先级]，先生。", True

    if any(w in c for w in ["你记得什么", "我的记忆", "记忆列表", "你记了什么"]):
        text = cfg.memory.get_all_facts_text(); return text, True

    if "搜索记忆" in c:
        mo = re.search(r'搜索记忆\s*(.+)', cmd)
        if mo:
            results = cfg.memory.search_facts(mo.group(1).strip())
            if not results: return "记忆中没有相关信息，先生。", True
            lines = ["搜索结果:"]
            for i, f in results: lines.append(f"#{i+1} {f['content']}")
            return "\n".join(lines), True

    if "忘记" in c:
        num_match = re.search(r'忘记.*?第?\s*(\d+)', c)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if cfg.memory.remove_fact(idx): cfg.memory.save(emotion=cfg.emotion, scheduler=cfg.scheduler, brain=cfg.brain); return "已删除，先生。", True
            return "没有这条记忆，先生。", True
        for prefix in ["忘记"]:
            if prefix in c:
                to_forget = c[c.index(prefix) + len(prefix):].strip()
                for i, f in enumerate(cfg.memory.facts):
                    if to_forget in f['content']: cfg.memory.remove_fact(i); cfg.memory.save(emotion=cfg.emotion, scheduler=cfg.scheduler, brain=cfg.brain); return f"已忘记「{f['content']}」，先生。", True
        return "我没有找到这条记忆，先生。", True

    # 你好
    if "你好" in c or "hello" in c or "hi" in c:
        return "你好先生，有什么可以帮您的？", True

    return None, False
