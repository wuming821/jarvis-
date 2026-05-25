# -*- coding: utf-8 -*-
"""Jarvis 多Agent系统 + 自主执行引擎"""
import json
import os
import re
import time
from datetime import datetime
from jarvis_config import client, browser, BASE_DIR
from jarvis_logger import get_logger, retry_on_failure

log = get_logger("agents")


# ======================================================
#  Agent 定义
# ======================================================
AGENT_TYPES = {
    "researcher": {
        "name": "研究员",
        "description": "专门负责搜索、收集信息、总结内容。擅长联网查找资料并整理成报告。",
        "system_prompt": "你是Jarvis的研究子Agent。你的任务是用工具搜集信息并整理成简洁的汇报。用中文回复，简洁有力。完成后说'研究完成'。",
        "tools": ["search_web", "search_and_summarize", "ai_query", "open_website",
                  "save_text_file", "open_file", "wait", "get_time"],
    },
    "executor": {
        "name": "执行者",
        "description": "专门负责操控电脑：打开程序、点击、输入、截图、按键。精确执行每一步操作。",
        "system_prompt": "你是Jarvis的执行子Agent。你的任务是精确操控电脑完成操作。每一步操作后汇报结果，完成后说'执行完成'。",
        "tools": ["run_program_tool", "computer_click", "computer_double_click",
                  "computer_right_click", "computer_move", "computer_type",
                  "computer_press", "computer_hotkey", "computer_scroll",
                  "take_screenshot", "get_mouse_info", "wait", "open_file"],
    },
    "reflector": {
        "name": "反思者",
        "description": "专门负责分析任务结果、总结经验教训、更新记忆。从已完成的任务中提炼可复用的经验。",
        "system_prompt": "你是Jarvis的反思子Agent。分析任务执行结果，提炼经验教训。调用remember_fact保存重要经验，完成后说'反思完成'。",
        "tools": ["ai_query", "search_memory", "recall_memories", "remember_fact",
                  "save_text_file", "get_profile", "update_profile", "get_time"],
    },
    "planner": {
        "name": "规划师",
        "description": "专门负责将复杂目标拆解为可执行的详细步骤计划。",
        "system_prompt": "你是Jarvis的规划Agent。把目标拆成可执行的步骤，严格按格式输出：\n1.第一步描述\n2.第二步描述\n...\n每步一行，以编号开头。每步描述要具体、可执行。用 save_text_file 保存计划。完成后说'规划完成'。",
        "tools": ["ai_query", "save_text_file", "open_file", "search_memory", "get_time"],
    },
}


# ======================================================
#  Agent 运行
# ======================================================
@retry_on_failure(max_retries=2, delay=1.0, exceptions=(Exception,))
def _agent_api_call(messages, tools):
    """带重试的 Agent API 调用"""
    return client.chat.completions.create(
        model="deepseek-v4-pro", messages=messages,
        tools=tools, temperature=0.7, max_tokens=1200,
    )


def _run_agent(agent_type, task):
    from jarvis_tools import execute_tool, TOOLS
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
            resp = _agent_api_call(agent_msgs, agent_tools)
        except Exception as e:
            log.error(f"[{agent_cfg['name']}] API调用失败: {e}")
            return f"[{agent_cfg['name']}] 出错: {e}"
        choice = resp.choices[0]
        msg = choice.message
        if msg.tool_calls:
            tool_called = True
            agent_msgs.append({
                "role": "assistant", "content": msg.content,
                "tool_calls": [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                try:
                    r = execute_tool(tc.function.name, args)
                    log.debug(f"      [{agent_cfg['name']}:{tc.function.name}] → {r[:50]}")
                except Exception as e:
                    r = f"工具出错: {e}"
                    log.error(f"      [{agent_cfg['name']}:{tc.function.name}] 工具错误: {e}")
                agent_msgs.append({"role": "tool", "tool_call_id": tc.id, "content": r})
            continue
        reply = msg.content or "任务已完成"
        return f"[{agent_cfg['name']}]{' 🔧' if tool_called else ''}\n{reply}"
    return f"[{agent_cfg['name']}] 达到最大轮次，任务可能未完成"


# ======================================================
#  自主执行管道
# ======================================================
def _execute_single_step(step_desc, goal, step_num, total):
    from jarvis_tools import execute_tool, TOOLS

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
                    "tool_calls": [{"id": tc.id, "type": "function",
                                    "function": {"name": tc.function.name,
                                                 "arguments": tc.function.arguments}}
                                   for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    try:
                        r = execute_tool(tc.function.name, args)
                        log.debug(f"      [{tc.function.name}] → {r[:50]}")
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
    log.warning(f"      [验证失败，自动重试步骤{step_num}...]")
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
    except Exception as e:
        log.warning(f"步骤验证异常: {e}")
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
        log.error(f"反思生成失败: {e}")
    lesson_match = re.search(r'教训[：:]\s*(.+?)(?:\n|$)', reflection)
    lessons = lesson_match.group(1).strip() if lesson_match else reflection[:120]
    _memory.add_reflection(goal, reflection, lessons)
    _memory.save(emotion=None, scheduler=None, brain=None)
    log.info(f"  [反思] {lessons[:80]}")
    return reflection, lessons
