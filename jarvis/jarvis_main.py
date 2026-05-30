# -*- coding: utf-8 -*-
"""Jarvis 主入口 — 组装所有模块，运行主循环"""
import sys
import time
import queue
import threading
from datetime import datetime
import winsound
import jarvis_config as cfg
from jarvis_tools import execute_tool
from jarvis_agents import _run_agent
from jarvis_core import (messages, _init_messages, _load_conversations, _find_wake_word,
                          speak, listen_text, listen,
                          chat_with_tools, handle_command)

# GUI 通信（--gui 模式下使用）
_gui_output_queue = None
_gui_input_queue = None
_gui_voice_enabled = [False]   # 语音输入开关
_gui_sound_enabled = [True]    # TTS 声音开关


def _safe_print(*args, **kwargs):
    """Windows GBK 控制台下安全打印（处理 emoji 等非 GBK 字符）"""
    import sys as _sys
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = []
        for a in args:
            if isinstance(a, str):
                a = a.encode(_sys.stdout.encoding or 'gbk', errors='replace').decode(_sys.stdout.encoding or 'gbk', errors='replace')
            safe_args.append(a)
        print(*safe_args, **kwargs)


def _output(text, role="assistant", speak_too=True):
    """统一输出调度：控制台 + GUI队列 + TTS"""
    if role == "user":
        _safe_print(f"你: {text}")
    elif role == "system":
        _safe_print(f"[系统] {text}")
    else:
        _safe_print(f"贾维斯: {text}")

    if _gui_output_queue is not None:
        try:
            _gui_output_queue.put_nowait(("message", text, role))
        except queue.Full:
            pass

    if speak_too and role == "assistant" and text:
        # GUI 模式下检查声音开关
        if _gui_output_queue is not None and not _gui_sound_enabled[0]:
            return
        try:
            cfg.speak_tts(text)
        except Exception:
            pass


def _output_silent():
    """不输出任何内容，仅用于标记不需要响应的操作"""
    pass


def _gui_listen():
    """GUI 模式输入：根据语音开关选择文字或麦克风"""
    if _gui_voice_enabled[0]:
        try:
            text = _gui_input_queue.get_nowait()
            if text:
                return text.strip()
        except queue.Empty:
            pass
        return listen()
    else:
        text = _gui_input_queue.get()
        if text is None:
            return "退出"
        return text.strip()


def _main_loop_body(_listen):
    """主循环体，参数化输入函数"""
    while True:
        for note in cfg.scheduler.check():
            _safe_print(f'[通知] {note}')
            _output(note)

        auto_msg = cfg.scheduler.check_autonomous()
        if auto_msg:
            _safe_print(f'[自主] {auto_msg}')
            _output(auto_msg)

        cmd = _listen()
        if not cmd:
            continue

        cfg.scheduler.touch()

        if any(w in cmd for w in ['退出', '再见', '关闭', '拜拜']):
            cfg.memory.save(emotion=cfg.emotion, scheduler=cfg.scheduler, brain=cfg.brain)
            _output('再见。')
            if _gui_output_queue is not None:
                _gui_output_queue.put(("shutdown", None, None))
            return

        is_text_mode = cfg.TEXT_MODE or (cfg.GUI_MODE and not _gui_voice_enabled[0])

        if is_text_mode:
            command = cmd
        else:
            wake_word, wake_idx, wake_len = _find_wake_word(cmd)
            if wake_idx == -1:
                continue
            command = cmd[wake_idx + wake_len:].strip()
            _safe_print(f'[唤醒: {wake_word}]')
            winsound.Beep(*cfg.ACK_BEEP)
            if not command:
                _output("我在")
                continue

        if any(w in command for w in ['指令列表', '你能做什么', '有什么命令']):
            msg = "本地指令：网站/搜索/程序/系统/截图/鼠标/按键。AI工具：对话/控制电脑/搜索/记忆，你想做什么直接说就好。"
            _output(msg)
            continue

        # Brain 决策
        decision = cfg.brain.think(command)
        strategy = decision.get("strategy", "direct")
        _safe_print(f"  [Brain] {decision.get('intent','?')} → {strategy} ({decision.get('confidence',0):.0%}) {decision.get('reason','')[:50]}")

        success = True
        response_text = ""

        # 先走本地指令
        reply, handled = handle_command(command)
        if handled:
            if reply and reply != "<<silent>>":
                response_text = reply
                _output(reply)
            cfg.brain.log_decision(command, decision, response_text or "(静默)", True)
            continue

        # Brain 策略路由
        if strategy == "agent_spawn" and not handled:
            intent = decision.get("intent", "")
            agent_map = {"query": "researcher", "action": "executor",
                         "reflection": "reflector", "planning": "planner"}
            agent_type = agent_map.get(intent, "researcher")
            _safe_print(f"  [Brain路由] 派遣 {agent_type} Agent")
            response_text = _run_agent(agent_type, command)
            success = "出错" not in response_text and "失败" not in response_text
            if cfg.GUI_MODE:
                _output(response_text)
            elif cfg.TEXT_MODE:
                _safe_print(f"贾维斯: {response_text}")
            else:
                speak(response_text)
        elif strategy == "autonomous" and not handled:
            _safe_print(f"  [Brain路由] 自主执行管道")
            response_text = execute_tool("autonomous_execute", {"goal": command})
            success = "已完成" in response_text or "✅" in response_text
            if cfg.GUI_MODE:
                _output(response_text)
            elif cfg.TEXT_MODE:
                _safe_print(f"贾维斯: {response_text}")
            else:
                speak(response_text)
        else:
            if cfg.GUI_MODE:
                response_text = chat_with_tools(command)
                _output(response_text)
            elif cfg.TEXT_MODE:
                _safe_print("贾维斯: ", end="", flush=True)
                response_text = chat_with_tools(command)
                _safe_print(response_text)
            else:
                response_text = chat_with_tools(command)
                speak(response_text)
            success = "抱歉" not in response_text and "出错" not in response_text

        cfg.brain.log_decision(command, decision, response_text, success)


def _main_loop():
    """启动主循环（决定使用哪个 listen 函数）"""
    if cfg.GUI_MODE:
        _listen = _gui_listen
    else:
        _listen = listen_text if cfg.TEXT_MODE else listen
    _main_loop_body(_listen)


def main():
    _safe_print('=' * 50)
    _safe_print('  J.A.R.V.I.S.')
    _safe_print('  Just A Rather Very Intelligent System')
    _safe_print('=' * 50)
    if cfg.GUI_MODE:
        _safe_print("  GUI 模式 | tkinter 聊天界面 | 文字输入 + 语音切换")
    elif cfg.TEXT_MODE:
        _safe_print("  文字模式 | 直接输入对话，无需唤醒词 | 输入 退出 关闭")
    else:
        _safe_print("  语音模式 | 唤醒词: 贾维斯 / Hey Jarvis | 指令优先 | AI 兜底")
    cfg._init_globals()
    _load_conversations()
    _init_messages()
    pending = len(cfg.scheduler.get_pending())
    total_decisions = sum(s["total"] for s in cfg.brain.stats.values())
    _safe_print(f'  [记忆 {len(cfg.memory.facts)}条 | 对话 {len(messages)-1}轮 | 情绪 {cfg.emotion.mood} | 任务 {pending}个 | Brain决策 {total_decisions}次]')
    _safe_print('=' * 50)

    if cfg.GUI_MODE:
        global _gui_output_queue, _gui_input_queue
        _gui_output_queue = queue.Queue()
        _gui_input_queue = queue.Queue()
        cfg._gui_queue = _gui_output_queue
        from jarvis_gui import JarvisGUI
        gui = JarvisGUI(_gui_output_queue, _gui_input_queue, _gui_voice_enabled, _gui_sound_enabled)
        _output('贾维斯系统已就绪。')
        _gui_output_queue.put(("status", "就绪 | 文字模式 | 情绪: " + cfg.emotion.mood, None))
        thread = threading.Thread(target=_main_loop, daemon=True)
        thread.start()
        gui.run()
    else:
        if not cfg.TEXT_MODE:
            speak('贾维斯系统已就绪。')
        else:
            _safe_print('贾维斯系统已就绪。')
            cfg.engine.say('贾维斯系统已就绪')
            cfg.engine.runAndWait()
        _main_loop_body(listen_text if cfg.TEXT_MODE else listen)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        _safe_print('\n[贾维斯已关闭]')
        sys.exit(0)
