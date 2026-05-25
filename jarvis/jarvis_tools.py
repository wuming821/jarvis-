# -*- coding: utf-8 -*-
"""Jarvis 工具注册表 + 工具调度中心"""
import json
import os
import re
import time
from datetime import datetime
import pyautogui
from jarvis_config import client, browser, BASE_DIR
from jarvis_computer import (screenshot, get_mouse_pos, get_screen_size, run_program)
from jarvis_agents import _run_agent, _execute_single_step, _reflect_on_execution
from jarvis_logger import get_logger

log = get_logger("tools")


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
#  execute_tool — 工具调度中心
# ======================================================
def execute_tool(tool_name, arguments):
    from jarvis_config import memory as _memory, scheduler as _scheduler, brain as _brain
    from jarvis_computer import (open_url as _open_url, click, double_click,
                                  right_click, move_mouse, type_unicode,
                                  press_key, hotkey, mouse_scroll, screenshot)

    if tool_name == "open_website":
        _open_url(arguments.get("url", ""), browser)
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
        click(arguments["x"], arguments["y"])
        return f"已点击 ({arguments['x']}, {arguments['y']})"

    elif tool_name == "computer_double_click":
        double_click(arguments["x"], arguments["y"])
        return f"已双击 ({arguments['x']}, {arguments['y']})"

    elif tool_name == "computer_right_click":
        right_click(arguments["x"], arguments["y"])
        return f"已右键 ({arguments['x']}, {arguments['y']})"

    elif tool_name == "computer_move":
        move_mouse(arguments["x"], arguments["y"])
        return f"鼠标已移至 ({arguments['x']}, {arguments['y']})"

    elif tool_name == "computer_type":
        type_unicode(arguments["text"])
        return f"已输入「{arguments['text']}」"

    elif tool_name == "computer_press":
        press_key(arguments["key"])
        return f"已按 {arguments['key']} 键"

    elif tool_name == "computer_hotkey":
        keys = arguments["keys"]
        hotkey(*keys)
        return f"组合键 {'+'.join(keys)}"

    elif tool_name == "computer_scroll":
        mouse_scroll(arguments["amount"])
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
            log.error(f"规划失败: {e}")
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
        log.info(f"\n  [自主执行] {goal}")
        # 阶段1: Planner Agent
        log.info(f"  [阶段1] Planner Agent 规划中...")
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
                log.error(f"规划失败: {e}")
                return f"规划失败: {e}"
        steps = re.findall(r'^\d+\.\s*(.+)', plan_text, re.MULTILINE)
        if not steps:
            return f"无法解析计划步骤:\n{plan_text}"
        log.info(f"  [计划] {len(steps)} 个步骤:")
        for i, s in enumerate(steps):
            log.info(f"    {i+1}. {s}")
        # 阶段2: 逐步执行
        log.info(f"  [阶段2] 开始执行...")
        results = []
        for i, step in enumerate(steps):
            log.info(f"  [执行 {i+1}/{len(steps)}] {step[:60]}...")
            result = _execute_single_step(step, goal, i + 1, len(steps))
            results.append(f"✓步骤{i+1}: {step}\n  → {result}")
        summary = "\n".join(results)
        # 阶段3: 反思
        log.info(f"  [阶段3] Reflector Agent 反思中...")
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
        log.info(f"\n  [派发Agent] {agent_type} ← {task[:60]}...")
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
            log.error(f"AI查询失败: {e}")
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
            log.error(f"总结生成失败: {e}")
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

    log.warning(f"未知工具调用: {tool_name}")
    return f"未知工具: {tool_name}"
