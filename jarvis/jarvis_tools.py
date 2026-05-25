# -*- coding: utf-8 -*-
"""Jarvis 工具注册表 + 多Agent系统 + 自主执行引擎"""
import json
import os
import re
import time
import subprocess
from datetime import datetime
import pyautogui
from jarvis_config import client, browser, BASE_DIR


# ======================================================
#  电脑控制底层
# ======================================================
def get_screen_size():
    s = pyautogui.size()
    return s.width, s.height


def screenshot(filepath=None):
    if filepath is None:
        filepath = os.path.join(BASE_DIR, f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    pyautogui.screenshot(filepath)
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


def open_url(url):
    browser.open(url)


# ======================================================
#  Tool Registry
# ======================================================
TOOLS = [
    {"type": "function", "function": {"name": "open_website", "description": "打开一个网站", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "完整URL（含https://）"}, "name": {"type": "string", "description": "网站名称（用于汇报）"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "search_web", "description": "在搜索引擎搜索关键词", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索关键词"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "run_program_tool", "description": "打开一个程序（通过Win键搜索程序名并回车）", "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "程序名，如 记事本/计算器/notepad/calc"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "computer_click", "description": "鼠标左键点击指定坐标", "parameters": {"type": "object", "properties": {"x": {"type": "integer", "description": "X坐标"}, "y": {"type": "integer", "description": "Y坐标"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "computer_double_click", "description": "鼠标双击指定坐标", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "computer_right_click", "description": "鼠标右键点击指定坐标", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "computer_move", "description": "移动鼠标到指定坐标（不点击）", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "computer_type", "description": "在当前光标位置输入文本（支持中英文）", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "要输入的文本"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "computer_press", "description": "按下单个键盘按键", "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "按键名: enter/esc/tab/space/backspace/delete/up/down/left/right/win/alt/ctrl/shift/home/end/f1-f12"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "computer_hotkey", "description": "按下组合键（如Ctrl+C复制）", "parameters": {"type": "object", "properties": {"keys": {"type": "array", "items": {"type": "string"}, "description": "按键列表，如['ctrl','c']"}}, "required": ["keys"]}}},
    {"type": "function", "function": {"name": "computer_scroll", "description": "滚动鼠标滚轮", "parameters": {"type": "object", "properties": {"amount": {"type": "integer", "description": "正数=上滚, 负数=下滚, 通常±3"}}, "required": ["amount"]}}},
    {"type": "function", "function": {"name": "take_screenshot", "description": "截取当前整个屏幕", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_mouse_info", "description": "获取当前鼠标位置和屏幕分辨率", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_time", "description": "获取当前日期和时间", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "remember_fact", "description": "保存一条用户个人信息到长期记忆。AI应主动调用此工具，不等用户说'记住'。", "parameters": {"type": "object", "properties": {"fact": {"type": "string", "description": "要记住的信息"}, "importance": {"type": "string", "enum": ["high", "medium", "low"], "description": "重要性：high=极重要(如生日/姓名), medium=一般信息(默认), low=临时"}}, "required": ["fact"]}}},
    {"type": "function", "function": {"name": "schedule_reminder", "description": "设置一个定时提醒（如'下午3点提醒我开会'）", "parameters": {"type": "object", "properties": {"message": {"type": "string", "description": "提醒内容"}, "time": {"type": "string", "description": "时间，格式HH:MM（如14:30）"}}, "required": ["message", "time"]}}},
    {"type": "function", "function": {"name": "schedule_timer", "description": "设置一个倒计时提醒（如'5分钟后提醒我关火'）", "parameters": {"type": "object", "properties": {"message": {"type": "string", "description": "提醒内容"}, "minutes": {"type": "integer", "description": "多少分钟后提醒"}}, "required": ["message", "minutes"]}}},
    {"type": "function", "function": {"name": "list_tasks", "description": "查看所有待执行的定时任务和提醒", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "make_plan", "description": "为一个目标生成详细的步骤计划并保存为文件。用户说'帮我规划xxx'时使用。", "parameters": {"type": "object", "properties": {"goal": {"type": "string", "description": "用户的目标或任务描述"}}, "required": ["goal"]}}},
    {"type": "function", "function": {"name": "autonomous_execute", "description": "自主规划并逐步执行一个目标。AI先拆解步骤，然后逐步调用工具完成每一步，最后汇报结果。用户说'帮我完成xxx'或'直接做xxx'时使用此工具。", "parameters": {"type": "object", "properties": {"goal": {"type": "string", "description": "要完成的目标描述"}}, "required": ["goal"]}}},
    {"type": "function", "function": {"name": "reflect", "description": "对刚完成的任务进行反思，总结经验教训。自主执行完成后应自动调用此工具。", "parameters": {"type": "object", "properties": {"goal": {"type": "string", "description": "任务目标"}, "plan": {"type": "string", "description": "执行的计划"}, "results": {"type": "string", "description": "执行结果"}}, "required": ["goal", "plan", "results"]}}},
    {"type": "function", "function": {"name": "spawn_agent", "description": "启动一个专门的子Agent来处理特定类型的任务。可用的Agent类型：researcher（搜索研究）、executor（电脑操作）、reflector（反思分析）、planner（规划拆解）。", "parameters": {"type": "object", "properties": {"agent_type": {"type": "string", "description": "Agent类型: researcher/executor/reflector/planner"}, "task": {"type": "string", "description": "交给子Agent的具体任务描述"}}, "required": ["agent_type", "task"]}}},
    {"type": "function", "function": {"name": "brain_summary", "description": "查看Agent Brain的决策统计，了解系统运行情况和策略成功率", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "cancel_task", "description": "取消一个定时任务", "parameters": {"type": "object", "properties": {"task_id": {"type": "string", "description": "任务ID（从list_tasks获取）"}}, "required": ["task_id"]}}},
    {"type": "function", "function": {"name": "update_profile", "description": "更新用户档案中的键值信息（如名字、生日、爱好等结构化数据）", "parameters": {"type": "object", "properties": {"key": {"type": "string", "description": "档案字段名（如 名字/生日/爱好/住址/工作/学校/电话）"}, "value": {"type": "string", "description": "字段值"}}, "required": ["key", "value"]}}},
    {"type": "function", "function": {"name": "get_profile", "description": "查看用户档案中的结构化信息", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search_memory", "description": "关键词搜索长期记忆中的相关信息", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "搜索关键词"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "retrieve_memories", "description": "AI语义检索：根据当前话题智能匹配最相关的记忆，比关键词搜索更准确。需要上下文时使用。", "parameters": {"type": "object", "properties": {"topic": {"type": "string", "description": "当前话题或查询"}}, "required": ["topic"]}}},
    {"type": "function", "function": {"name": "recall_memories", "description": "查看所有已保存的用户长期记忆", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "forget_memory", "description": "删除一条用户记忆（按序号或内容关键词）", "parameters": {"type": "object", "properties": {"target": {"type": "string", "description": "序号(如'3')或内容关键词"}}, "required": ["target"]}}},
    {"type": "function", "function": {"name": "wait", "description": "等待指定秒数（用于工具之间的延迟，如打开程序后等它加载）", "parameters": {"type": "object", "properties": {"seconds": {"type": "number", "description": "等待秒数，默认1.0"}}}}},
    {"type": "function", "function": {"name": "ai_query", "description": "向AI提问获取信息或总结（用于工具内部需要AI能力的场景，如总结搜索结果）", "parameters": {"type": "object", "properties": {"prompt": {"type": "string", "description": "要问AI的问题"}}, "required": ["prompt"]}}},
    {"type": "function", "function": {"name": "search_and_summarize", "description": "搜索一个话题→AI自动总结→保存为txt→打开文件。一站式信息收集。", "parameters": {"type": "object", "properties": {"topic": {"type": "string", "description": "要搜索并总结的话题"}}, "required": ["topic"]}}},
    {"type": "function", "function": {"name": "save_text_file", "description": "将文本内容保存到桌面上的.txt文件", "parameters": {"type": "object", "properties": {"filename": {"type": "string", "description": "文件名（如 note.txt）"}, "content": {"type": "string", "description": "要保存的文本内容"}}, "required": ["filename", "content"]}}},
    {"type": "function", "function": {"name": "open_file", "description": "用默认程序打开一个文件", "parameters": {"type": "object", "properties": {"filepath": {"type": "string", "description": "文件的完整路径"}}, "required": ["filepath"]}}},
]

# ======================================================
#  多Agent系统
# ======================================================
AGENT_TYPES = {
    "researcher": {
        "name": "研究员",
        "description": "专门负责搜索、收集信息、总结内容。擅长联网查找资料并整理成报告。",
        "system_prompt": "你是Jarvis的研究子Agent。你的任务是用工具搜集信息并整理成简洁的汇报。用中文回复，简洁有力。完成后说'研究完成'。",
        "tools": ["search_web", "search_and_summarize", "ai_query", "open_website", "save_text_file", "open_file", "wait", "get_time"],
    },
    "executor": {
        "name": "执行者",
        "description": "专门负责操控电脑：打开程序、点击、输入、截图、按键。精确执行每一步操作。",
        "system_prompt": "你是Jarvis的执行子Agent。你的任务是精确操控电脑完成操作。每一步操作后汇报结果，完成后说'执行完成'。",
        "tools": ["run_program_tool", "computer_click", "computer_double_click", "computer_right_click",
                  "computer_move", "computer_type", "computer_press", "computer_hotkey", "computer_scroll",
                  "take_screenshot", "get_mouse_info", "wait", "open_file"],
    },
    "reflector": {
        "name": "反思者",
        "description": "专门负责分析任务结果、总结经验教训、更新记忆。从已完成的任务中提炼可复用的经验。",
        "system_prompt": "你是Jarvis的反思子Agent。分析任务执行结果，提炼经验教训。调用remember_fact保存重要经验，完成后说'反思完成'。",
        "tools": ["ai_query", "search_memory", "recall_memories", "remember_fact", "save_text_file",
                  "get_profile", "update_profile", "get_time"],
    },
    "planner": {
        "name": "规划师",
        "description": "专门负责将复杂目标拆解为可执行的详细步骤计划。",
        "system_prompt": "你是Jarvis的规划Agent。把目标拆成可执行的步骤，严格按格式输出：\n1.第一步描述\n2.第二步描述\n...\n每步一行，以编号开头。每步描述要具体、可执行。用 save_text_file 保存计划。完成后说'规划完成'。",
        "tools": ["ai_query", "save_text_file", "open_file", "search_memory", "get_time"],
    },
}

# 这些函数需要访问 memory, scheduler, brain — 通过 execute_tool 调用时传入
# 延迟导入在函数内部完成


def _run_agent(agent_type, task):
    from jarvis_config import memory as _memory, scheduler as _scheduler, brain as _brain
    agent_cfg = AGENT_TYPES.get(agent_type)
    if not agent_cfg:
        return f"未知Agent类型: {agent_type}，可选: {', '.join(AGENT_TYPES.keys())}"
    agent_tools = [t for t in TOOLS if t["function"]["name"] in agent_cfg["tools"]]
    agent_msgs = [
        {"role": "system", "content": agent_cfg["system_prompt"]},
        {"role": "user", "content": task},
    ]
    tool_called = False
    for round_idx in range(5):
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro", messages=agent_msgs,
                tools=agent_tools, temperature=0.7, max_tokens=1200,
            )
        except Exception as e:
            return f"[{agent_cfg['name']}] 出错: {e}"
        choice = resp.choices[0]
        msg = choice.message
        if msg.tool_calls:
            tool_called = True
            agent_msgs.append({
                "role": "assistant", "content": msg.content,
                "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                try:
                    r = execute_tool(tc.function.name, args)
                    print(f"      [{agent_cfg['name']}:{tc.function.name}] → {r[:50]}")
                except Exception as e:
                    r = f"工具出错: {e}"
                agent_msgs.append({"role": "tool", "tool_call_id": tc.id, "content": r})
            continue
        reply = msg.content or "任务已完成"
        return f"[{agent_cfg['name']}]{' 🔧' if tool_called else ''}\n{reply}"
    return f"[{agent_cfg['name']}] 达到最大轮次，任务可能未完成"


def _execute_single_step(step_desc, goal, step_num, total):
    def _try_execute():
        step_msgs = [
            {"role": "system", "content": f"你正在执行一个多步骤任务。目标是：「{goal}」\n"
             f"当前第{step_num}/{total}步：{step_desc}\n"
             "用工具完成这一步，完成后汇报结果。不需要工具就直接回复完成。"},
        ]
        for _ in range(3):
            try:
                resp = client.chat.completions.create(
                    model="deepseek-v4-pro", messages=step_msgs,
                    tools=TOOLS, temperature=0.7, max_tokens=1000,
                )
            except Exception as e:
                return False, f"出错: {e}"
            choice = resp.choices[0]
            msg = choice.message
            if msg.tool_calls:
                step_msgs.append({
                    "role": "assistant", "content": msg.content,
                    "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    try:
                        r = execute_tool(tc.function.name, args)
                        print(f"      [{tc.function.name}] → {r[:50]}")
                    except Exception as e:
                        r = f"工具出错: {e}"
                    step_msgs.append({"role": "tool", "tool_call_id": tc.id, "content": r})
                continue
            result_text = msg.content or f"步骤{step_num}已完成"
            ok, verify_text = _verify_step(step_desc, result_text)
            return ok, (result_text + "\n" + verify_text) if not ok else result_text
        return False, f"步骤{step_num}达到最大轮次"

    ok, text = _try_execute()
    if ok:
        return f"✅ {text}"
    print(f"      [验证失败，自动重试...]")
    ok2, text2 = _try_execute()
    return f"{'✅' if ok2 else '❌'} {text2}"


def _verify_step(step_desc, result_text):
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": "你是任务验证器。判断这一步是否真正完成了。如果结果中提到'已完成''已打开''已保存''已输入'等明确完成词，就是成功。如果提到'失败''出错''无法''未找到'等，就是失败。只回答：成功 或 失败，并一句话说明。"},
                {"role": "user", "content": f"步骤: {step_desc}\n执行结果: {result_text}\n\n这一步成功了吗？"},
            ],
            temperature=0.3, max_tokens=100,
        )
        answer = resp.choices[0].message.content
        if "失败" in answer:
            return False, answer
        return True, answer
    except Exception:
        return True, ""


def _reflect_on_execution(goal, plan_text, results_text):
    from jarvis_config import memory as _memory
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": "你是反思分析器。回顾刚才执行的任务，分析：1)哪些步骤成功了？2)哪些可以改进？3)下次遇到类似任务应该怎么做？请简洁输出，重点是一句话经验教训（以'教训：'开头）。"},
                {"role": "user", "content": f"目标：{goal}\n\n计划：\n{plan_text}\n\n执行结果：\n{results_text}"},
            ],
            temperature=0.6, max_tokens=400,
        )
        reflection = resp.choices[0].message.content
    except Exception as e:
        reflection = f"反思生成失败: {e}"
    lesson_match = re.search(r'教训[：:]\s*(.+?)(?:\n|$)', reflection)
    lessons = lesson_match.group(1).strip() if lesson_match else reflection[:120]
    _memory.add_reflection(goal, reflection, lessons)
    _memory.save(emotion=None, scheduler=None, brain=None)
    print(f"  [反思] {lessons[:80]}")
    return reflection, lessons


# ======================================================
#  execute_tool — 工具调度中心
# ======================================================
def execute_tool(tool_name, arguments):
    from jarvis_config import memory as _memory, scheduler as _scheduler, brain as _brain
    if tool_name == "open_website":
        browser.open(arguments.get("url", ""))
        return f"已打开 {arguments.get('name', arguments.get('url', ''))}"

    elif tool_name == "search_web":
        query = arguments.get("query", "")
        browser.open(f"https://www.google.com/search?q={query}")
        return f"正在搜索「{query}」"

    elif tool_name == "run_program_tool":
        name = arguments.get("name", "")
        if name:
            run_program(name)
            return f"已启动 {name}"
        return "未指定程序名"

    elif tool_name == "computer_click":
        pyautogui.click(arguments["x"], arguments["y"])
        return f"已点击 ({arguments['x']}, {arguments['y']})"

    elif tool_name == "computer_double_click":
        pyautogui.doubleClick(arguments["x"], arguments["y"])
        return f"已双击 ({arguments['x']}, {arguments['y']})"

    elif tool_name == "computer_right_click":
        pyautogui.rightClick(arguments["x"], arguments["y"])
        return f"已右键 ({arguments['x']}, {arguments['y']})"

    elif tool_name == "computer_move":
        pyautogui.moveTo(arguments["x"], arguments["y"])
        return f"鼠标已移至 ({arguments['x']}, {arguments['y']})"

    elif tool_name == "computer_type":
        pyautogui.write(arguments["text"])
        return f"已输入「{arguments['text']}」"

    elif tool_name == "computer_press":
        pyautogui.press(arguments["key"])
        return f"已按 {arguments['key']} 键"

    elif tool_name == "computer_hotkey":
        keys = arguments["keys"]
        pyautogui.hotkey(*keys)
        return f"组合键 {'+'.join(keys)}"

    elif tool_name == "computer_scroll":
        pyautogui.scroll(arguments["amount"])
        return f"已滚动 {arguments['amount']} 格"

    elif tool_name == "take_screenshot":
        path = screenshot()
        return f"截图已保存: {path}"

    elif tool_name == "get_mouse_info":
        x, y = get_mouse_pos()
        w, h = get_screen_size()
        return f"鼠标 ({x},{y}) 屏幕 {w}x{h}"

    elif tool_name == "get_time":
        now = datetime.now()
        wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        return f"{now.year}年{now.month}月{now.day}日 {wd} {now.hour:02d}:{now.minute:02d}"

    elif tool_name == "schedule_reminder":
        tid = _scheduler.add_reminder(arguments["message"], arguments["time"])
        _memory.save(emotion=None, scheduler=_scheduler, brain=None)
        return f"已设置提醒 [{tid}]：{arguments['time']} — {arguments['message']}"

    elif tool_name == "schedule_timer":
        minutes = arguments.get("minutes", 5)
        tid = _scheduler.add_timer(arguments["message"], minutes * 60)
        _memory.save(emotion=None, scheduler=_scheduler, brain=None)
        return f"已设置倒计时 [{tid}]：{minutes}分钟后提醒「{arguments['message']}」"

    elif tool_name == "list_tasks":
        tasks = _scheduler.get_pending()
        if not tasks:
            return "目前没有待执行的任务"
        lines = ["待执行任务："]
        for t in tasks:
            if t["type"] == "reminder":
                lines.append(f"  [{t['id']}] {t['time']} ⏰ {t['message']}")
            elif t["type"] == "timer":
                remaining = max(0, int(t.get('fire_at', 0) - time.time()))
                lines.append(f"  [{t['id']}] {remaining}秒后 ⏰ {t['message']}")
            elif t["type"] == "periodic":
                lines.append(f"  [{t['id']}] 每{t.get('interval', 0)//60}分钟 🔄 {t['message']}")
        return "\n".join(lines)

    elif tool_name == "make_plan":
        goal = arguments.get("goal", "")
        plans_dir = os.path.join(BASE_DIR, "plans")
        os.makedirs(plans_dir, exist_ok=True)
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": "你是一个AI任务规划助手。把用户的目标拆成简洁明确的步骤。用编号列表输出，每一步一行。格式：1. xxx\n2. xxx\n3. xxx\n不要额外解释，直接输出步骤。"},
                    {"role": "user", "content": goal},
                ],
                temperature=0.7, max_tokens=1000,
            )
            plan = resp.choices[0].message.content
        except Exception as e:
            return f"规划失败: {e}"
        safe_name = "".join(c for c in goal if c not in r'\/:*?"<>|')[:30]
        filename = f"{safe_name}.txt"
        filepath = os.path.join(plans_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 计划：{goal}\n\n{plan}")
        os.startfile(filepath)
        return f"计划已生成并保存到 plans/{filename}，已为你打开。\n\n{plan}"

    elif tool_name == "autonomous_execute":
        goal = arguments.get("goal", "")
        print(f"\n  [自主执行] {goal}")
        # 阶段1: Planner Agent
        print(f"  [阶段1] Planner Agent 规划中...")
        plan_text = _run_agent("planner", f"为以下目标生成详细步骤计划，每步一行，编号格式 1.xxx\n2.xxx：\n\n{goal}")
        if "出错" in plan_text or "达到最大轮次" in plan_text:
            try:
                resp = client.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=[{"role": "system", "content": "把用户目标拆成编号步骤。格式：1. xxx\n2. xxx"}, {"role": "user", "content": goal}],
                    temperature=0.7, max_tokens=1000,
                )
                plan_text = resp.choices[0].message.content
            except Exception as e:
                return f"规划失败: {e}"
        steps = re.findall(r'^\d+\.\s*(.+)', plan_text, re.MULTILINE)
        if not steps:
            return f"无法解析计划步骤:\n{plan_text}"
        print(f"  [计划] {len(steps)} 个步骤:")
        for i, s in enumerate(steps):
            print(f"    {i+1}. {s}")
        # 阶段2: 逐步执行
        print(f"  [阶段2] 开始执行...")
        results = []
        for i, step in enumerate(steps):
            print(f"  [执行 {i+1}/{len(steps)}] {step[:60]}...")
            result = _execute_single_step(step, goal, i + 1, len(steps))
            results.append(f"✓步骤{i+1}: {step}\n  → {result}")
        summary = "\n".join(results)
        # 阶段3: 反思
        print(f"  [阶段3] Reflector Agent 反思中...")
        refl_input = f"目标：{goal}\n\n计划：\n{plan_text}\n\n执行结果：\n{summary}"
        reflection = _run_agent("reflector", f"分析以下任务执行情况，提炼经验教训，重要经验调用 remember_fact 保存：\n\n{refl_input}")
        lesson_match = re.search(r'教训[：:]\s*(.+?)(?:\n|$)', reflection)
        lessons = lesson_match.group(1).strip() if lesson_match else reflection[:120]
        _memory.add_reflection(goal, reflection, lessons)
        _memory.save(emotion=None, scheduler=None, brain=None)
        # 保存
        plans_dir = os.path.join(BASE_DIR, "plans")
        os.makedirs(plans_dir, exist_ok=True)
        safe_name = "".join(c for c in goal if c not in r'\/:*?"<>|')[:30]
        filepath = os.path.join(plans_dir, f"{safe_name}_result.txt")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 执行结果：{goal}\n\n## Planner Agent 计划\n{plan_text}\n\n## Executor 执行记录\n{summary}\n\n## Reflector Agent 反思\n{reflection}")
        return f"全部 {len(steps)} 步已完成 ✅\n\n{summary}\n\n📝 反思：{lessons}\n\n结果已保存: plans/{safe_name}_result.txt"

    elif tool_name == "reflect":
        goal = arguments.get("goal", "")
        plan = arguments.get("plan", "")
        results = arguments.get("results", "")
        reflection, lessons = _reflect_on_execution(goal, plan, results)
        return f"反思完成 ✅\n\n{reflection}"

    elif tool_name == "spawn_agent":
        agent_type = arguments.get("agent_type", "")
        task = arguments.get("task", "")
        print(f"\n  [派发Agent] {agent_type} ← {task[:60]}...")
        return _run_agent(agent_type, task)

    elif tool_name == "brain_summary":
        return _brain.get_summary()

    elif tool_name == "cancel_task":
        msg = _scheduler.cancel(arguments["task_id"])
        _memory.save(emotion=None, scheduler=_scheduler, brain=None)
        return f"已取消「{msg}」" if msg else "未找到该任务"

    elif tool_name == "update_profile":
        key = arguments.get("key", "")
        value = arguments.get("value", "")
        _memory.set_profile(key, value)
        _memory.save(emotion=None, scheduler=None, brain=None)
        return f"档案已更新: {key} → {value}"

    elif tool_name == "get_profile":
        if not _memory.profile:
            return "暂无档案信息"
        return "\n".join(f"{k}: {v}" for k, v in _memory.profile.items())

    elif tool_name == "remember_fact":
        importance = arguments.get("importance", "medium")
        conflict = _memory.add_fact(arguments["fact"], importance)
        _memory.save(emotion=None, scheduler=None, brain=None)
        base = f"已记住「{arguments['fact']}」[重要性:{importance}]"
        return base + " " + conflict if conflict else base

    elif tool_name == "search_memory":
        query = arguments.get("query", "")
        results = _memory.search_facts(query)
        if not results:
            return f"记忆中未找到关于「{query}」的信息"
        lines = [f"搜索「{query}」结果:"]
        for i, f in results:
            lines.append(f"#{i+1} {f['content']}")
        return "\n".join(lines)

    elif tool_name == "retrieve_memories":
        topic = arguments.get("topic", "")
        result = _memory.retrieve_relevant(topic)
        if not result:
            return f"未找到与「{topic}」相关的记忆"
        return f"与「{topic}」最相关的记忆:\n{result}"

    elif tool_name == "recall_memories":
        return _memory.get_all_facts_text()

    elif tool_name == "forget_memory":
        target = arguments.get("target", "")
        if target.isdigit():
            idx = int(target) - 1
            if _memory.remove_fact(idx):
                _memory.save(emotion=None, scheduler=None, brain=None)
                return "已删除"
            return "序号不存在"
        for i, f in enumerate(_memory.facts):
            if target in f["content"]:
                _memory.remove_fact(i)
                _memory.save(emotion=None, scheduler=None, brain=None)
                return f"已忘记「{f['content']}」"
        return "未找到匹配的记忆"

    elif tool_name == "ai_query":
        prompt = arguments.get("prompt", "")
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7, max_tokens=1000,
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"AI查询失败: {e}"

    elif tool_name == "search_and_summarize":
        topic = arguments.get("topic", "")
        browser.open(f"https://www.google.com/search?q={topic}")
        time.sleep(0.5)
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{"role": "user", "content": f"请用中文简洁介绍：{topic}（200字以内）"}],
                temperature=0.7, max_tokens=500,
            )
            summary = resp.choices[0].message.content
        except Exception as e:
            summary = f"总结生成失败: {e}"
        safe_name = "".join(c for c in topic if c not in r'\/:*?"<>|')[:30]
        filename = f"{safe_name}.txt"
        filepath = os.path.join(BASE_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# {topic}\n\n{summary}")
        os.startfile(filepath)
        return f"已搜索「{topic}」→ AI总结 → 保存到 {filename} → 已打开"

    elif tool_name == "save_text_file":
        filename = arguments.get("filename", "output.txt")
        content = arguments.get("content", "")
        filepath = os.path.join(BASE_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"文件已保存: {filename}"

    elif tool_name == "open_file":
        filepath = arguments.get("filepath", "")
        os.startfile(filepath)
        return f"已打开 {filepath}"

    elif tool_name == "wait":
        secs = arguments.get("seconds", 1.0)
        time.sleep(float(secs))
        return f"已等待 {secs}s"

    return f"未知工具: {tool_name}"
