# -*- coding: utf-8 -*-
"""Jarvis GUI — Claude Code 终端风格聊天界面"""
import tkinter as tk
import queue

# ── Claude Code 终端风配色 ──────────────────────────────────
BG      = "#0d1117"   # 主背景 — 极深蓝黑
BG2     = "#161b22"   # 次级背景 — 输入区/状态栏
BG3     = "#21262d"   # 三级背景 — 按钮常态
BORDER  = "#30363d"   # 边框/分隔线
FG      = "#e6edf3"   # 主文字 — 柔和白

ACCENT     = "#d97706"  # 琥珀橙 — Claude 品牌强调色
ACCENT_DIM = "#9a6700"  # 暗琥珀 — 悬停/次级
BLUE       = "#58a6ff"  # 蓝 — 助手消息
GREEN      = "#7ee787"  # 绿 — 用户消息
GRAY       = "#8b949e"  # 灰 — 系统消息/占位
RED        = "#f85149"  # 红 — 语音激活提示
RED_BG     = "#490202"  # 暗红 — 语音按钮激活背景

# ── 字体 ────────────────────────────────────────────────────
FONT_NAME = "Cascadia Code"
FONT      = (FONT_NAME, 10)
FONT_BOLD = (FONT_NAME, 10, "bold")
FONT_SM   = (FONT_NAME, 9)


class JarvisGUI:
    def __init__(self, output_queue, input_queue, voice_enabled, sound_enabled=None):
        self.output_queue = output_queue
        self.input_queue = input_queue
        self.voice_enabled = voice_enabled
        self.sound_enabled = sound_enabled

        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S.")
        self.root.geometry("800x600")
        self.root.minsize(500, 400)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Grid 布局：行 0=header, 1=status, 2=chat(expand), 3=input
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_rowconfigure(3, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_status()
        self._build_chat()
        self._build_input()

        self._poll_output()

    # ── 顶部标题栏 + 模式切换 ──────────────────────────────
    def _build_header(self):
        header = tk.Frame(self.root, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))

        # 标题
        title = tk.Label(header, text="J.A.R.V.I.S.",
                         bg=BG, fg=FG, font=(FONT_NAME, 13, "bold"),
                         anchor="w")
        title.pack(side=tk.LEFT, pady=6)

        # 语音声色选择
        self._voice_names = [
            ("晓晓", "zh-CN-XiaoxiaoNeural"),
            ("云希", "zh-CN-YunxiNeural"),
            ("云扬", "zh-CN-YunyangNeural"),
            ("云健", "zh-CN-YunjianNeural"),
            ("云夏", "zh-CN-YunxiaNeural"),
            ("晓伊", "zh-CN-XiaoyiNeural"),
        ]
        self._voice_index = 0
        try:
            import jarvis_config as _cfg
            for i, (_, vid) in enumerate(self._voice_names):
                if vid == _cfg.EDGE_VOICE:
                    self._voice_index = i
                    break
        except Exception:
            pass

        self.btn_voice_sel = tk.Label(
            header, text=f" 🎵 {self._voice_names[self._voice_index][0]} ",
            bg=BG, fg=GRAY, font=FONT_SM, cursor="hand2", padx=4,
        )
        self.btn_voice_sel.pack(side=tk.RIGHT, pady=6)
        self.btn_voice_sel.bind("<Button-1>", lambda e: self._cycle_voice())
        self.btn_voice_sel.bind("<Enter>", lambda e: self.btn_voice_sel.configure(bg=BG3))
        self.btn_voice_sel.bind("<Leave>", lambda e: self.btn_voice_sel.configure(bg=BG))

        # 声音开关
        sound_on = self.sound_enabled[0] if self.sound_enabled else True
        self.btn_sound = tk.Label(
            header, text=" 🔊 " if sound_on else " 🔇 ", bg=BG, fg=GRAY,
            font=(FONT_NAME, 14), cursor="hand2", padx=6,
        )
        self.btn_sound.pack(side=tk.RIGHT, pady=6)
        self.btn_sound.bind("<Button-1>", lambda e: self._toggle_sound())
        self.btn_sound.bind("<Enter>", lambda e: self.btn_sound.configure(bg=BG3))
        self.btn_sound.bind("<Leave>", lambda e: self.btn_sound.configure(bg=BG))

        # 模式切换容器
        toggle_frame = tk.Frame(header, bg=BG3, bd=0, highlightthickness=0)
        toggle_frame.pack(side=tk.RIGHT, pady=6, padx=(0, 6))

        self.btn_text_mode = tk.Label(
            toggle_frame, text="  💬  文字  ", bg=ACCENT, fg="#ffffff",
            font=FONT_BOLD, cursor="hand2", padx=8, pady=2,
        )
        self.btn_text_mode.pack(side=tk.LEFT)
        self.btn_text_mode.bind("<Button-1>", lambda e: self._set_text_mode())

        self.btn_voice_mode = tk.Label(
            toggle_frame, text="  🎤  语音  ", bg=BG3, fg=GRAY,
            font=FONT_BOLD, cursor="hand2", padx=8, pady=2,
        )
        self.btn_voice_mode.pack(side=tk.LEFT)
        self.btn_voice_mode.bind("<Button-1>", lambda e: self._set_voice_mode())

        # 分隔线（header 下方）
        sep = tk.Frame(self.root, bg=BORDER, height=1)
        sep.grid(row=0, column=0, sticky="ew", padx=12, pady=(54, 0))

    # ── 状态栏 ──────────────────────────────────────────────
    def _build_status(self):
        status_bar = tk.Frame(self.root, bg=BG2)
        status_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 0))

        # 状态指示灯
        self.status_dot = tk.Canvas(status_bar, width=10, height=10,
                                     bg=BG2, highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(8, 6), pady=6)
        self._dot = self.status_dot.create_oval(1, 1, 9, 9, fill=GREEN, outline="")

        self.status_var = tk.StringVar(value="就绪")
        self.status_label = tk.Label(
            status_bar, textvariable=self.status_var,
            bg=BG2, fg=GRAY, font=FONT_SM, anchor="w",
        )
        self.status_label.pack(side=tk.LEFT, pady=6)

        # 分隔线（status 下方）
        sep = tk.Frame(self.root, bg=BORDER, height=1)
        sep.grid(row=1, column=0, sticky="ew", padx=12, pady=(30, 0))

    # ── 聊天区（终端风）────────────────────────────────────
    def _build_chat(self):
        chat_frame = tk.Frame(self.root, bg=BG, bd=0, highlightthickness=0)
        chat_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 4))

        self.chat = tk.Text(
            chat_frame,
            bg=BG, fg=FG, insertbackground=FG,
            font=FONT,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bd=0, highlightthickness=0,
            padx=10, pady=8,
            yscrollcommand=lambda *a: self._on_scroll(*a),
        )
        self.chat.pack(fill=tk.BOTH, expand=True)

        # 标签样式
        self.chat.tag_config("assistant", foreground=BLUE)
        self.chat.tag_config("user",      foreground=GREEN)
        self.chat.tag_config("system",    foreground=GRAY)
        self.chat.tag_config("prefix",    foreground=GRAY, font=FONT_SM)
        self.chat.tag_config("timestamp", foreground=GRAY, font=FONT_SM)

        # 滚动条
        from tkinter import ttk
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScrollbar",
                        background=BG3, troughcolor=BG,
                        arrowcolor=GRAY, bordercolor=BG,
                        gripcount=0, relief="flat")

        self.scrollbar = ttk.Scrollbar(
            chat_frame, orient=tk.VERTICAL, command=self.chat.yview, style="TScrollbar"
        )
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat.configure(yscrollcommand=self.scrollbar.set)

    def _on_scroll(self, *args):
        self.scrollbar.set(*args)

    # ── 输入区 ──────────────────────────────────────────────
    def _build_input(self):
        input_outer = tk.Frame(self.root, bg=BG2)
        input_outer.grid(row=3, column=0, sticky="ew")

        # 顶部分隔线
        sep = tk.Frame(input_outer, bg=BORDER, height=1)
        sep.pack(side=tk.TOP, fill=tk.X)

        # 内容
        inner = tk.Frame(input_outer, bg=BG2)
        inner.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        # > 提示符
        self.prompt_label = tk.Label(
            inner, text="  >  ", bg=BG2, fg=ACCENT,
            font=(FONT_NAME, 12, "bold"),
        )
        self.prompt_label.pack(side=tk.LEFT)

        # 输入框
        self.entry = tk.Entry(
            inner,
            bg=BG, fg=FG,
            insertbackground=FG,
            font=FONT,
            bd=1, relief=tk.SOLID,
            highlightthickness=0,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.entry.bind("<Return>", self.send_message)

        # 发送按钮
        self.send_btn = tk.Label(
            inner, text=" → ", bg=BG3, fg=FG,
            font=(FONT_NAME, 12, "bold"),
            cursor="hand2", padx=10,
        )
        self.send_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.send_btn.bind("<Button-1>", lambda e: self.send_message())
        self.send_btn.bind("<Enter>", lambda e: self.send_btn.configure(bg=ACCENT, fg="#ffffff"))
        self.send_btn.bind("<Leave>", lambda e: self.send_btn.configure(bg=BG3, fg=FG))

        # 语音按钮
        self.voice_action_btn = tk.Label(
            inner, text=" 🎤 ", bg=BG3, fg=GRAY,
            font=FONT_BOLD, cursor="hand2", padx=8,
        )
        self.voice_action_btn.pack(side=tk.RIGHT, padx=(0, 4))
        self.voice_action_btn.bind("<Button-1>", lambda e: self._toggle_mic())
        self.voice_action_btn.bind("<Enter>", lambda e: self._mic_hover_enter())
        self.voice_action_btn.bind("<Leave>", lambda e: self._mic_hover_leave())

        self.entry.focus_set()

    # ── 模式切换 ─────────────────────────────────────────────
    def _set_text_mode(self):
        self.voice_enabled[0] = False
        self.btn_text_mode.configure(bg=ACCENT, fg="#ffffff")
        self.btn_voice_mode.configure(bg=BG3, fg=GRAY)
        self.voice_action_btn.configure(text=" 🎤 ", bg=BG3, fg=GRAY)
        self.prompt_label.configure(fg=ACCENT)
        self.entry.configure(state=tk.NORMAL, fg=FG)
        self.send_btn.configure(bg=BG3, fg=FG, cursor="hand2")
        self.status_var.set("文字模式 · 输入后回车发送")
        self.status_dot.itemconfig(self._dot, fill=GREEN)
        self.entry.focus_set()

    def _set_voice_mode(self):
        self.voice_enabled[0] = True
        self.btn_text_mode.configure(bg=BG3, fg=GRAY)
        self.btn_voice_mode.configure(bg=RED, fg="#ffffff")
        self.voice_action_btn.configure(text=" 🎤 语音待命中 ", bg=RED_BG, fg=RED)
        self.prompt_label.configure(fg=RED)
        self.entry.configure(state=tk.DISABLED, fg=GRAY)
        self.send_btn.configure(bg=BG3, fg=GRAY, cursor="X_cursor")
        self.status_var.set("语音模式 · 说「贾维斯」唤醒")
        self.status_dot.itemconfig(self._dot, fill=RED)

    def _cycle_voice(self):
        self._voice_index = (self._voice_index + 1) % len(self._voice_names)
        name, voice_id = self._voice_names[self._voice_index]
        self.btn_voice_sel.configure(text=f" 🎵 {name} ")
        try:
            import jarvis_config as _cfg
            _cfg.EDGE_VOICE = voice_id
        except Exception:
            pass
        self.status_var.set(f"声色切换至 {name} · " +
                          ("语音模式" if self.voice_enabled[0] else "文字模式"))

    def _toggle_sound(self):
        if not self.sound_enabled:
            return
        self.sound_enabled[0] = not self.sound_enabled[0]
        if self.sound_enabled[0]:
            self.btn_sound.configure(text=" 🔊 ", fg=GRAY)
            self.status_var.set("声音已开启 · " +
                              ("语音模式" if self.voice_enabled[0] else "文字模式"))
        else:
            self.btn_sound.configure(text=" 🔇 ", fg=RED)
            self.status_var.set("声音已静音 · " +
                              ("语音模式" if self.voice_enabled[0] else "文字模式"))

    def _toggle_mic(self):
        if self.voice_enabled[0]:
            self._set_text_mode()
        else:
            self._set_voice_mode()

    def _mic_hover_enter(self):
        if not self.voice_enabled[0]:
            self.voice_action_btn.configure(bg=RED_BG, fg=RED)

    def _mic_hover_leave(self):
        if not self.voice_enabled[0]:
            self.voice_action_btn.configure(bg=BG3, fg=GRAY)

    # ── 发送消息 ─────────────────────────────────────────────
    def send_message(self, event=None):
        if self.voice_enabled[0]:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self._add_to_chat(text, "user")
        self.input_queue.put(text)

    # ── 消息渲染 ─────────────────────────────────────────────
    def _add_to_chat(self, text, role):
        self.chat.configure(state=tk.NORMAL)

        if role == "assistant":
            prefix = "贾维斯 > "
            tag = "assistant"
        elif role == "user":
            prefix = "你 > "
            tag = "user"
        else:
            prefix = "  ·  "
            tag = "system"

        self.chat.insert(tk.END, prefix, ("prefix", tag))
        self.chat.insert(tk.END, text + "\n", ("message", tag))

        self.chat.see(tk.END)
        self.chat.configure(state=tk.DISABLED)

    # ── 轮询输出队列 ────────────────────────────────────────
    def _poll_output(self):
        try:
            while True:
                msg = self.output_queue.get_nowait()
                msg_type, text, role = msg
                if msg_type == "shutdown":
                    self.root.quit()
                    return
                elif msg_type == "message":
                    self._add_to_chat(text, role or "assistant")
                elif msg_type == "status":
                    self.status_var.set(text)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_output)

    # ── 关闭 ─────────────────────────────────────────────────
    def _on_close(self):
        self.input_queue.put("退出")
        self.root.after(500, self.root.quit)

    def run(self):
        self.root.mainloop()
