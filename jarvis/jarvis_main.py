# -*- coding: utf-8 -*-
"""Jarvis 主入口 — 组装所有模块，运行主循环"""
import sys
import time
from datetime import datetime
import winsound
import jarvis_config as cfg
from jarvis_tools import execute_tool
from jarvis_agents import _run_agent
from jarvis_core import (messages, _init_messages, _load_conversations, _find_wake_word,
                          speak, listen_text, listen,
                          chat_with_tools, handle_command)


def main():
    print('=' * 50)
    print('  J.A.R.V.I.S.')
    print('  Just A Rather Very Intelligent System')
    print('=' * 50)
    if cfg.TEXT_MODE:
        print("  文字模式 | 直接输入对话，无需唤醒词 | 输入 退出 关闭")
    else:
        print("  语音模式 | 唤醒词: 贾维斯 / Hey Jarvis | 指令优先 | AI 兜底")
    cfg._init_globals()
    _load_conversations()
    _init_messages()
    pending = len(cfg.scheduler.get_pending())
    total_decisions = sum(s["total"] for s in cfg.brain.stats.values())
    print(f'  [记忆 {len(cfg.memory.facts)}条 | 对话 {len(messages)-1}轮 | 情绪 {cfg.emotion.mood} | 任务 {pending}个 | Brain决策 {total_decisions}次]')
    print('=' * 50)
    if not cfg.TEXT_MODE:
        speak('贾维斯系统已就绪。')
    else:
        print('贾维斯系统已就绪。')
        cfg.engine.say('贾维斯系统已就绪')
        cfg.engine.runAndWait()

    _listen = listen_text if cfg.TEXT_MODE else listen

    while True:
        for note in cfg.scheduler.check():
            print(f'[通知] {note}')
            if not cfg.TEXT_MODE:
                speak(note)
            else:
                print(f'贾维斯: {note}')

        auto_msg = cfg.scheduler.check_autonomous()
        if auto_msg:
            print(f'[自主] {auto_msg}')
            if not cfg.TEXT_MODE:
                speak(auto_msg)
            else:
                print(f'贾维斯: {auto_msg}')

        cmd = _listen()
        if not cmd:
            continue

        cfg.scheduler.touch()

        if any(w in cmd for w in ['退出', '再见', '关闭', '拜拜']):
            cfg.memory.save(emotion=cfg.emotion, scheduler=cfg.scheduler, brain=cfg.brain)
            if cfg.TEXT_MODE:
                print('贾维斯: 再见。')
            else:
                speak('再见。')
            return

        if cfg.TEXT_MODE:
            command = cmd
        else:
            wake_word, wake_idx, wake_len = _find_wake_word(cmd)
            if wake_idx == -1:
                continue
            command = cmd[wake_idx + wake_len:].strip()
            print(f'[唤醒: {wake_word}]')
            winsound.Beep(*cfg.ACK_BEEP)
            if not command:
                speak("我在")
                continue

        if any(w in command for w in ['指令列表', '你能做什么', '有什么命令']):
            msg = "本地指令：网站/搜索/程序/系统/截图/鼠标/按键。AI工具：对话/控制电脑/搜索/记忆，你想做什么直接说就好。"
            if cfg.TEXT_MODE:
                print(f"贾维斯: {msg}")
            else:
                speak(msg)
            continue

        # Brain 决策
        decision = cfg.brain.think(command)
        strategy = decision.get("strategy", "direct")
        print(f"  [Brain] {decision.get('intent','?')} → {strategy} ({decision.get('confidence',0):.0%}) {decision.get('reason','')[:50]}")

        success = True
        response_text = ""

        # 先走本地指令
        reply, handled = handle_command(command)
        if handled:
            if reply and reply != "<<silent>>":
                response_text = reply
                if cfg.TEXT_MODE:
                    print(f"贾维斯: {reply}")
                else:
                    speak(reply)
            cfg.brain.log_decision(command, decision, response_text or "(静默)", True)
            continue

        # Brain 策略路由
        if strategy == "agent_spawn" and not handled:
            intent = decision.get("intent", "")
            agent_map = {"query": "researcher", "action": "executor",
                         "reflection": "reflector", "planning": "planner"}
            agent_type = agent_map.get(intent, "researcher")
            print(f"  [Brain路由] 派遣 {agent_type} Agent")
            response_text = _run_agent(agent_type, command)
            success = "出错" not in response_text and "失败" not in response_text
        elif strategy == "autonomous" and not handled:
            print(f"  [Brain路由] 自主执行管道")
            response_text = execute_tool("autonomous_execute", {"goal": command})
            success = "已完成" in response_text or "✅" in response_text
        else:
            if cfg.TEXT_MODE:
                print("贾维斯: ", end="", flush=True)
            response_text = chat_with_tools(command)
            if cfg.TEXT_MODE:
                print(response_text)
            else:
                speak(response_text)
            success = "抱歉" not in response_text and "出错" not in response_text

        cfg.brain.log_decision(command, decision, response_text, success)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n[贾维斯已关闭]')
        sys.exit(0)
