# -*- coding: utf-8 -*-
"""Jarvis GUI — 现代气泡式聊天界面（兼容原 API）"""
import tkinter as tk
from tkinter import ttk
import queue
import time

# ═══════════════════════════════════════════════════════════════════
# 配色方案 — 深空科技风（精炼版）
# ═══════════════════════════════════════════════════════════════════
BG           = "#0b1018"   # 主背景
BG2          = "#131b2a"   # 次级背景（输入栏/状态栏）
BG3          = "#1c2738"   # 三级背景（按钮常态）
BG_HOVER     = "#25334a"   # 按钮悬停
BORDER       = "#2a4a6e"   # 边框
BORDER_FOCUS = "#00c8ff"   # 聚焦边框
FG           = "#f0f4f8"   # 主文字 — 纯白偏蓝
FG_DIM       = "#aabbcc"   # 次要文字 — 更亮

# 气泡颜色
BUBBLE_ASSISTANT = "#132438"
BUBBLE_USER      = "#132e1e"
BUBBLE_SYSTEM    = "#1e1e30"
BUBBLE_BORDER_A  = "#1e4070"
BUBBLE_BORDER_U  = "#1e5038"

ACCENT     = "#00e0ff"   # 青蓝
ACCENT2    = "#8c5eff"   # 紫
GREEN      = "#00ff88"   # 亮绿
BLUE_MSG   = "#8ad4ff"   # 蓝 — 更亮
GRAY       = "#667788"
RED        = "#ff6678"
RED_BG     = "#2d1018"
RED_HOVER  = "#ff8896"

# ═══════════════════════════════════════════════════════════════════
# 字体
# ═══════════════════════════════════════════════════════════════════
FONT_MAIN = "Cascadia Code"
FONT_FALL = "Consolas"

def _font(size=10, weight="normal", family=None):
    fam = family or FONT_MAIN
    if weight == "bold":
        return (fam, size, "bold")
    return (fam, size)


# ═══════════════════════════════════════════════════════════════════
# 绘图工具
# ═══════════════════════════════════════════════════════════════════
def _round_rect(canvas, x1, y1, x2, y2, r=14, **kw):
    """在 Canvas 上绘制圆角矩形（smooth 多边形法）"""
    pts = [
        x1+r, y1,   x2-r, y1,
        x2, y1,     x2, y1+r,
        x2, y2-r,   x2, y2,
        x2-r, y2,   x1+r, y2,
        x1, y2,     x1, y2-r,
        x1, y1+r,   x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _shadow_rect(canvas, x1, y1, x2, y2, r=14, color="#000000",
                 alpha_hex="20"):
    """绘制半透明阴影层（用 stipple 模拟 + dark fill）"""
    return _round_rect(canvas, x1, y1, x2, y2, r=r,
                       fill="#030a14", outline="")


# ═══════════════════════════════════════════════════════════════════
# RoundedFrame — 带 Canvas 圆角背景的 Frame
# ═══════════════════════════════════════════════════════════════════
class RoundedFrame(tk.Canvas):
    """圆角气泡 Canvas：绘制圆角背景 + 内嵌 Label 文字"""

    def __init__(self, parent, bg_color, border_color=None,
                 corner_r=14, shadow=False, **kw):
        super().__init__(parent, bg=parent["bg"], bd=0,
                         highlightthickness=0, **kw)
        self._bg = bg_color
        self._border = border_color or bg_color
        self._r = corner_r
        self._shadow = shadow
        self._label = None
        self._label_win = None
        self.bind("<Configure>", self._redraw)

    def set_label(self, label_widget):
        """嵌入 Label widget"""
        self._label = label_widget
        self._label_win = self.create_window(
            0, 0, window=label_widget, anchor="nw")

    def _redraw(self, event=None):
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 2 or h <= 2:
            return
        self.delete("bg")
        if self._shadow:
            _shadow_rect(self, 3, 4, w-2, h-2, r=self._r+2)
        _round_rect(self, 1, 1, w-2, h-2, r=self._r,
                     fill=self._bg, outline=self._border,
                     width=1, tags="bg")
        self.lower("bg")
        # Label 填满整个 Canvas
        if self._label_win:
            self.coords(self._label_win, 0, 0)
            self.itemconfig(self._label_win, width=w, height=h)


# ═══════════════════════════════════════════════════════════════════
# 主 GUI 类
# ═══════════════════════════════════════════════════════════════════
class JarvisGUI:
    def __init__(self, output_queue, input_queue, voice_enabled,
                 sound_enabled=None):
        self.output_queue = output_queue
        self.input_queue  = input_queue
        self.voice_enabled = voice_enabled
        self.sound_enabled = sound_enabled

        # 打字机动画状态
        self._typing_after  = None
        self._typing_text   = ""
        self._typing_index  = 0
        self._typing_label  = None
        self._typing_bubble = None

        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S.")
        self.root.geometry("840x600")
        self.root.minsize(560, 420)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        try:
            self.root.attributes("-alpha", 0.97)
        except Exception:
            pass

        # 网格布局
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_rowconfigure(3, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_status()
        self._build_chat()
        self._build_input()

        self.root.after(400, self._startup_animation)
        self._poll_output()

    # ═══════════════════════════════════════════════════════════
    # Header
    # ═══════════════════════════════════════════════════════════
    def _build_header(self):
        header = tk.Frame(self.root, bg=BG, bd=0, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")

        # 底部发光分隔线
        glow = tk.Frame(self.root, bg=ACCENT, height=2)
        glow.grid(row=0, column=0, sticky="sew")

        # 左侧：Reactor + 标题
        left = tk.Frame(header, bg=BG)
        left.pack(side=tk.LEFT, padx=(14, 0), pady=(8, 7))

        # Arc Reactor
        self._reactor_cvs = tk.Canvas(left, width=26, height=26,
                                       bg=BG, highlightthickness=0)
        self._reactor_cvs.pack(side=tk.LEFT, padx=(0, 10))
        # 外环
        self._reactor_cvs.create_oval(1, 1, 25, 25, fill="#00152e",
                                       outline=ACCENT, width=1.5)
        # 中环
        self._reactor_cvs.create_oval(4, 4, 22, 22, fill="",
                                       outline="#005577", width=1)
        # 发光核心
        self._r_core = self._reactor_cvs.create_oval(
            6, 6, 20, 20, fill=ACCENT, outline="")
        # 中心高亮
        self._reactor_cvs.create_oval(9, 9, 17, 17, fill="#d0f4ff",
                                       outline="")
        self._reactor_glow = True
        self._reactor_pulse_dir = 1
        self._blink_reactor()

        # 标题
        tk.Label(left, text="J.A.R.V.I.S.",
                 bg=BG, fg=ACCENT,
                 font=_font(13, "bold")).pack(side=tk.LEFT)
        tk.Label(left, text="  ·  Just A Rather Very Intelligent System",
                 bg=BG, fg=FG_DIM,
                 font=_font(8)).pack(side=tk.LEFT)

        # 右侧控件
        right = tk.Frame(header, bg=BG)
        right.pack(side=tk.RIGHT, padx=(0, 10), pady=(8, 7))

        # 声色选择
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

        self.btn_voice_sel = self._mk_pill_btn(
            right, f"♪ {self._voice_names[self._voice_index][0]}",
            cmd=self._cycle_voice
        )
        self.btn_voice_sel.pack(side=tk.RIGHT, padx=(4, 0))

        # 声音开关
        sound_on = self.sound_enabled[0] if self.sound_enabled else True
        self.btn_sound = self._mk_pill_btn(
            right, "♪ ON" if sound_on else "♪ OFF",
            active_color=ACCENT if sound_on else RED,
            cmd=self._toggle_sound
        )
        self.btn_sound.pack(side=tk.RIGHT, padx=(4, 0))

        tk.Label(right, text="│", bg=BG, fg=BORDER,
                 font=_font(9)).pack(side=tk.RIGHT, padx=(6, 4))

        # 模式切换
        self.btn_text_mode = self._mk_mode_btn(right, "💬 文字",
                                                active=True)
        self.btn_text_mode.pack(side=tk.RIGHT, padx=(4, 0))
        for w in self.btn_text_mode.winfo_children():
            w.bind("<Button-1>", lambda e: self._set_text_mode())
        self.btn_text_mode.bind("<Button-1>", lambda e: self._set_text_mode())

        self.btn_voice_mode = self._mk_mode_btn(right, "🎤 语音",
                                                 active=False)
        self.btn_voice_mode.pack(side=tk.RIGHT, padx=(4, 0))
        for w in self.btn_voice_mode.winfo_children():
            w.bind("<Button-1>", lambda e: self._set_voice_mode())
        self.btn_voice_mode.bind("<Button-1>",
                                 lambda e: self._set_voice_mode())

    # ── 胶囊按钮 ──────────────────────────────────────────
    def _mk_pill_btn(self, parent, text, active_color=None, cmd=None):
        frm = tk.Frame(parent, bg=BG3, bd=0, highlightthickness=1,
                       highlightbackground=BORDER)
        lbl = tk.Label(frm, text=text, bg=BG3,
                       fg=active_color or FG_DIM,
                       font=_font(8), padx=8, pady=3, cursor="hand2")
        lbl.pack()

        def on_enter(e):
            lbl.configure(bg=BG_HOVER)
            frm.configure(bg=BG_HOVER)

        def on_leave(e):
            lbl.configure(bg=BG3)
            frm.configure(bg=BG3)

        if cmd:
            lbl.bind("<Button-1>", lambda e: cmd())
            frm.bind("<Button-1>", lambda e: cmd())
        lbl.bind("<Enter>", on_enter)
        lbl.bind("<Leave>", on_leave)
        frm.bind("<Enter>", on_enter)
        frm.bind("<Leave>", on_leave)
        return frm

    # ── 模式按钮 ──────────────────────────────────────────
    def _mk_mode_btn(self, parent, text, active=False):
        bg = ACCENT if active else BG3
        fg = "#000e1a" if active else FG_DIM
        frm = tk.Frame(parent, bg=bg, bd=0, highlightthickness=0)
        lbl = tk.Label(frm, text=text, bg=bg, fg=fg,
                       font=_font(9, "bold"), padx=10, pady=4,
                       cursor="hand2")
        lbl.pack()

        if not active:
            def on_enter(e):
                lbl.configure(bg=BG_HOVER)
                frm.configure(bg=BG_HOVER)

            def on_leave(e):
                lbl.configure(bg=BG3)
                frm.configure(bg=BG3)

            lbl.bind("<Enter>", on_enter)
            lbl.bind("<Leave>", on_leave)
            frm.bind("<Enter>", on_enter)
            frm.bind("<Leave>", on_leave)
        return frm

    # ── Reactor 呼吸动画 ──────────────────────────────────
    def _blink_reactor(self):
        # 核心脉动
        import random
        r = random.randint(0, 20)
        if self._reactor_glow:
            self._reactor_cvs.itemconfig(self._r_core, fill=ACCENT)
            # 中环随机微亮
            try:
                self._reactor_cvs.itemconfig(2, outline="#006688")
            except Exception:
                pass
        else:
            self._reactor_cvs.itemconfig(self._r_core, fill="#006688")
            try:
                self._reactor_cvs.itemconfig(2, outline="#003344")
            except Exception:
                pass
        self._reactor_glow = not self._reactor_glow
        self.root.after(900, self._blink_reactor)

    # ═══════════════════════════════════════════════════════════
    # 状态栏
    # ═══════════════════════════════════════════════════════════
    def _build_status(self):
        bar = tk.Frame(self.root, bg=BG2, bd=0, highlightthickness=0)
        bar.grid(row=1, column=0, sticky="ew")

        inner = tk.Frame(bar, bg=BG2)
        inner.pack(side=tk.LEFT, padx=(14, 0), pady=3)

        # 状态指示灯（带脉冲外圈）
        self._status_cvs = tk.Canvas(inner, width=14, height=14,
                                      bg=BG2, highlightthickness=0)
        self._status_cvs.pack(side=tk.LEFT, padx=(0, 8))
        # 外圈（脉冲）
        self._s_outer = self._status_cvs.create_oval(
            1, 1, 13, 13, fill="", outline=GREEN, width=1)
        # 内核
        self._s_dot = self._status_cvs.create_oval(
            4, 4, 10, 10, fill=GREEN, outline="")
        self._pulse_alpha = 1.0
        self._pulse_dir = -0.05
        self._animate_pulse()

        self.status_var = tk.StringVar(value="系统就绪")
        tk.Label(inner, textvariable=self.status_var,
                 bg=BG2, fg=FG_DIM, font=_font(8)).pack(side=tk.LEFT)

        # 右侧版本
        tk.Label(bar, text="v2.1 ", bg=BG2, fg=GRAY,
                 font=_font(8)).pack(side=tk.RIGHT, padx=14)

        # 底部分隔线
        tk.Frame(self.root, bg=BORDER, height=1).grid(
            row=1, column=0, sticky="sew")

    def _animate_pulse(self):
        """状态指示灯脉冲动画"""
        self._pulse_alpha += self._pulse_dir
        if self._pulse_alpha <= 0.2:
            self._pulse_dir = 0.05
        elif self._pulse_alpha >= 1.0:
            self._pulse_dir = -0.05

        # 调整外圈颜色强度
        try:
            r = int(int(GREEN[1:3], 16) * self._pulse_alpha)
            g = int(int(GREEN[3:5], 16) * self._pulse_alpha)
            b = int(int(GREEN[5:7], 16) * self._pulse_alpha)
            c = f"#{r:02x}{g:02x}{b:02x}"
            self._status_cvs.itemconfig(self._s_outer, outline=c)
        except Exception:
            pass
        self.root.after(80, self._animate_pulse)

    def _set_status_dot(self, color):
        """更新状态灯颜色"""
        try:
            self._status_cvs.itemconfig(self._s_dot, fill=color)
            self._status_cvs.itemconfig(self._s_outer, outline=color)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # 聊天区
    # ═══════════════════════════════════════════════════════════
    def _build_chat(self):
        outer = tk.Frame(self.root, bg=BG, bd=0, highlightthickness=0)
        outer.grid(row=2, column=0, sticky="nsew")
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        # Canvas
        self._chat_canvas = tk.Canvas(outer, bg=BG, bd=0,
                                       highlightthickness=0)
        self._chat_canvas.grid(row=0, column=0, sticky="nsew")

        self._vsb = tk.Scrollbar(outer, orient="vertical",
                                  bg=BG3, troughcolor=BG,
                                  activebackground=BORDER,
                                  bd=0, highlightthickness=0,
                                  width=10,
                                  command=self._chat_canvas.yview)
        self._vsb.grid(row=0, column=1, sticky="ns")
        self._chat_canvas.configure(yscrollcommand=self._vsb.set)

        # 气泡容器
        self._chat_inner = tk.Frame(self._chat_canvas, bg=BG, bd=0,
                                     highlightthickness=0)
        self._chat_window = self._chat_canvas.create_window(
            (0, 0), window=self._chat_inner, anchor="nw", tags="inner"
        )
        self._chat_inner.bind("<Configure>", self._on_inner_resize)
        self._chat_canvas.bind("<Configure>", self._on_canvas_resize)
        self._chat_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._chat_inner.bind("<MouseWheel>", self._on_mousewheel)

    def _on_inner_resize(self, event):
        self._chat_canvas.configure(
            scrollregion=self._chat_canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        self._chat_canvas.itemconfig(self._chat_window,
                                     width=event.width)

    def _on_mousewheel(self, event):
        self._chat_canvas.yview_scroll(
            int(-1 * (event.delta / 120)), "units")

    # ── 添加气泡 ──────────────────────────────────────────
    def _add_bubble(self, text, role):
        """添加气泡消息（圆角 + 时间戳）"""
        is_assistant = (role == "assistant")
        is_user      = (role == "user")
        is_system    = (role == "system")

        pad_x = 12
        pad_y = 6

        row_frame = tk.Frame(self._chat_inner, bg=BG, bd=0)
        row_frame.pack(fill=tk.X, padx=10, pady=(4, 0))

        now = time.strftime("%H:%M")

        if is_user:
            inner = tk.Frame(row_frame, bg=BG)
            inner.pack(side=tk.RIGHT)
            tk.Label(inner, text=now, bg=BG, fg=GRAY,
                     font=_font(7), anchor="e").pack(
                anchor="e", padx=(0, 34), pady=(0, 1))
            brow = tk.Frame(inner, bg=BG)
            brow.pack(anchor="e")
            self._mk_avatar(brow, "你", GREEN).pack(
                side=tk.RIGHT, padx=(8, 0), pady=(4, 0))
            bub = RoundedFrame(brow, BUBBLE_USER,
                               border_color=BUBBLE_BORDER_U,
                               corner_r=12, shadow=True)
            bub.pack(side=tk.RIGHT)
            lbl = tk.Label(bub, text=text, bg=BUBBLE_USER, fg=GREEN,
                           font=_font(11), wraplength=440,
                           justify=tk.LEFT, padx=pad_x, pady=pad_y,
                           anchor="w")
            bub.set_label(lbl)
            return None

        elif is_assistant:
            inner = tk.Frame(row_frame, bg=BG)
            inner.pack(side=tk.LEFT)
            tk.Label(inner, text=now, bg=BG, fg=GRAY,
                     font=_font(7), anchor="w").pack(
                anchor="w", padx=(34, 0), pady=(0, 1))
            brow = tk.Frame(inner, bg=BG)
            brow.pack(anchor="w")
            self._mk_avatar(brow, "J", ACCENT, fg="#000e1a").pack(
                side=tk.LEFT, padx=(0, 8), pady=(4, 0))
            bub = RoundedFrame(brow, BUBBLE_ASSISTANT,
                               border_color=BUBBLE_BORDER_A,
                               corner_r=12, shadow=True)
            bub.pack(side=tk.LEFT)
            lbl = tk.Label(bub, text=text, bg=BUBBLE_ASSISTANT,
                           fg=BLUE_MSG, font=_font(11),
                           wraplength=460, justify=tk.LEFT,
                           padx=pad_x, pady=pad_y, anchor="w")
            bub.set_label(lbl)
            return lbl

        else:
            # 系统消息居中
            inner = tk.Frame(row_frame, bg=BG)
            inner.pack(anchor="center")
            tk.Label(inner, text=f"· {text} ·",
                     bg=BG, fg=FG_DIM,
                     font=_font(8), padx=8, pady=2).pack()
            return None

    def _mk_avatar(self, parent, letter, color, fg="#000e1a"):
        """圆形头像 Canvas"""
        size = 24
        cvs = tk.Canvas(parent, width=size, height=size,
                        bg=BG, highlightthickness=0)
        cvs.create_oval(1, 1, size-1, size-1,
                        fill=color, outline="")
        cvs.create_text(size//2, size//2, text=letter,
                        fill=fg, font=_font(8, "bold"))
        return cvs

    # ── 打字机效果 ────────────────────────────────────────
    def _add_to_chat(self, text, role):
        if role == "assistant":
            self._typewriter_start(text)
        else:
            self._add_bubble(text, role)

    def _typewriter_start(self, text):
        if self._typing_after:
            self.root.after_cancel(self._typing_after)
            self._typing_after = None

        self._typing_text  = text
        self._typing_index = 0

        pad_x = 12
        pad_y = 6

        row_frame = tk.Frame(self._chat_inner, bg=BG, bd=0)
        row_frame.pack(fill=tk.X, padx=10, pady=(4, 0))
        inner = tk.Frame(row_frame, bg=BG)
        inner.pack(side=tk.LEFT)

        # 时间戳
        now = time.strftime("%H:%M")
        tk.Label(inner, text=now, bg=BG, fg=GRAY,
                 font=_font(7), anchor="w").pack(
            anchor="w", padx=(40, 0), pady=(0, 1))

        # 头像 + 气泡
        bubble_row = tk.Frame(inner, bg=BG)
        bubble_row.pack(anchor="w")

        ava = self._mk_avatar(bubble_row, "J", ACCENT, fg="#000e1a")
        ava.pack(side=tk.LEFT, padx=(0, 8), pady=(4, 0))

        bub = RoundedFrame(bubble_row, BUBBLE_ASSISTANT,
                           border_color=BUBBLE_BORDER_A,
                           corner_r=12, shadow=True)
        bub.pack(side=tk.LEFT)
        self._typing_label = tk.Label(
            bub, text="", bg=BUBBLE_ASSISTANT, fg=BLUE_MSG,
            font=_font(11), wraplength=460,
            justify=tk.LEFT, padx=pad_x, pady=pad_y, anchor="w")
        bub.set_label(self._typing_label)
        self._typing_bubble = bub

        self._typewriter_tick()

    def _typewriter_tick(self):
        if self._typing_index <= len(self._typing_text):
            chunk = self._typing_text[:self._typing_index]
            cursor = "│" if (int(time.time() * 5) % 2 == 0) else " "
            try:
                self._typing_label.configure(text=chunk + cursor)
            except Exception:
                return
            self._typing_index += 2
            self._scroll_to_bottom()
            self._typing_after = self.root.after(16,
                                                 self._typewriter_tick)
        else:
            try:
                self._typing_label.configure(text=self._typing_text)
            except Exception:
                pass
            self._typing_after = None
            self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """平滑滚动到底部"""
        self._chat_canvas.yview_moveto(1.0)

    # ═══════════════════════════════════════════════════════════
    # 输入区（Pill 圆角输入框）
    # ═══════════════════════════════════════════════════════════
    def _build_input(self):
        outer = tk.Frame(self.root, bg=BG2, bd=0, highlightthickness=0)
        outer.grid(row=3, column=0, sticky="ew")

        # 顶部分隔线
        tk.Frame(outer, bg=BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        inner = tk.Frame(outer, bg=BG2)
        inner.pack(side=tk.TOP, fill=tk.X, padx=12, pady=8)

        # 提示符
        self.prompt_label = tk.Label(
            inner, text="❯", bg=BG2, fg=ACCENT,
            font=_font(12, "bold"))
        self.prompt_label.pack(side=tk.LEFT, padx=(0, 8))

        # 发送按钮（圆角 Pill）
        self.send_btn = tk.Canvas(inner, width=56, height=30,
                                   bg=BG2, highlightthickness=0,
                                   cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, padx=(8, 0))
        b_w, b_h = 54, 28
        _round_rect(self.send_btn, 1, 1, b_w-1, b_h-1, r=14,
                     fill=ACCENT, outline="")
        self._send_txt = self.send_btn.create_text(
            b_w//2, b_h//2, text="发送", fill="#000e1a",
            font=_font(8, "bold"))
        self.send_btn.bind("<Button-1>", lambda e: self.send_message())
        self.send_btn.bind("<Enter>",
                           lambda e: self._send_btn_hover(True))
        self.send_btn.bind("<Leave>",
                           lambda e: self._send_btn_hover(False))

        # 麦克风按钮
        self._mic_cvs = tk.Canvas(inner, width=36, height=30,
                                   bg=BG2, highlightthickness=0,
                                   cursor="hand2")
        self._mic_cvs.pack(side=tk.RIGHT, padx=(4, 0))
        m_w, m_h = 34, 28
        self._mic_bg_id = _round_rect(self._mic_cvs, 1, 1, m_w-1, m_h-1,
                                       r=14, fill=BG3, outline=BORDER)
        self._mic_txt_id = self._mic_cvs.create_text(
            m_w//2, m_h//2, text="🎤", fill=GRAY,
            font=_font(11))
        self._mic_cvs.bind("<Button-1>", lambda e: self._toggle_mic())
        self._mic_cvs.bind("<Enter>",
                           lambda e: self._mic_hover_enter())
        self._mic_cvs.bind("<Leave>",
                           lambda e: self._mic_hover_leave())

        # 输入框（Frame 容器 + Entry）
        entry_frame = tk.Frame(inner, bg=BG3, bd=0,
                                highlightthickness=2,
                                highlightbackground=BORDER)
        entry_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.entry = tk.Entry(
            entry_frame,
            bg=BG3, fg=FG,
            insertbackground=ACCENT,
            insertwidth=2,
            font=_font(11),
            bd=0, relief=tk.FLAT,
            highlightthickness=0,
        )
        self.entry.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        self.entry.bind("<Return>", self.send_message)
        self.entry.bind("<FocusIn>",
                        lambda e: entry_frame.configure(
                            highlightbackground=BORDER_FOCUS))
        self.entry.bind("<FocusOut>",
                        lambda e: entry_frame.configure(
                            highlightbackground=BORDER))

        # 快捷键提示
        tk.Label(outer, text="Enter 发送 · Esc 清空",
                 bg=BG2, fg=GRAY, font=_font(7)).pack(pady=(0, 3))

        self.root.bind("<Escape>", lambda e: self.entry.delete(0, tk.END))
        self.entry.focus_set()

    def _send_btn_hover(self, entering):
        c = "#00aacc" if entering else ACCENT
        try:
            self.send_btn.delete("all")
            b_w, b_h = 54, 28
            _round_rect(self.send_btn, 1, 1, b_w-1, b_h-1, r=14,
                         fill=c, outline="")
            self._send_txt = self.send_btn.create_text(
                b_w//2, b_h//2, text="发送", fill="#000e1a",
                font=_font(8, "bold"))
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    # 模式切换
    # ═══════════════════════════════════════════════════════════
    def _set_text_mode(self):
        self.voice_enabled[0] = False
        self._update_mode_btn(self.btn_text_mode, True)
        self._update_mode_btn(self.btn_voice_mode, False)
        self._update_mic_btn(active=False)
        self.prompt_label.configure(fg=ACCENT)
        self.entry.configure(state=tk.NORMAL, fg=FG)
        self.status_var.set("文字模式 · 输入后回车发送")
        self._set_status_dot(GREEN)
        self.entry.focus_set()

    def _set_voice_mode(self):
        self.voice_enabled[0] = True
        self._update_mode_btn(self.btn_text_mode, False)
        self._update_mode_btn(self.btn_voice_mode, True, is_voice=True)
        self._update_mic_btn(active=True)
        self.prompt_label.configure(fg=RED)
        self.entry.configure(state=tk.DISABLED, fg=GRAY)
        self.status_var.set("语音模式 · 说「贾维斯」唤醒")
        self._set_status_dot(RED)

    def _update_mode_btn(self, frm, active, is_voice=False):
        bg = RED if (active and is_voice) else (ACCENT if active else BG3)
        fg = "#000e1a" if active else FG_DIM
        try:
            frm.configure(bg=bg)
            for w in frm.winfo_children():
                w.configure(bg=bg, fg=fg)
        except Exception:
            pass

    def _update_mic_btn(self, active):
        try:
            self._mic_cvs.delete("all")
            m_w, m_h = 34, 28
            if active:
                bg_c = RED_BG
                out_c = RED
                txt   = "🎤"
                txt_c = RED
            else:
                bg_c = BG3
                out_c = BORDER
                txt   = "🎤"
                txt_c = GRAY
            self._mic_bg_id = _round_rect(self._mic_cvs, 1, 1,
                                           m_w-1, m_h-1,
                                           r=14, fill=bg_c,
                                           outline=out_c)
            self._mic_txt_id = self._mic_cvs.create_text(
                m_w//2, m_h//2, text=txt, fill=txt_c,
                font=_font(11))
        except Exception:
            pass

    def _cycle_voice(self):
        self._voice_index = (self._voice_index + 1) % len(
            self._voice_names)
        name, voice_id = self._voice_names[self._voice_index]
        child = self.btn_voice_sel.winfo_children()
        if child:
            child[0].configure(text=f"♪ {name}")
        try:
            import jarvis_config as _cfg
            _cfg.EDGE_VOICE = voice_id
        except Exception:
            pass
        self.status_var.set(f"声色 → {name} · " +
                            ("语音" if self.voice_enabled[0]
                             else "文字") + "模式")

    def _toggle_sound(self):
        if not self.sound_enabled:
            return
        self.sound_enabled[0] = not self.sound_enabled[0]
        on = self.sound_enabled[0]
        child = self.btn_sound.winfo_children()
        if child:
            child[0].configure(
                text="♪ ON" if on else "♪ OFF",
                fg=ACCENT if on else RED)
        self.status_var.set(
            "声音" + ("已开启" if on else "已静音") + " · " +
            ("语音" if self.voice_enabled[0] else "文字") + "模式")

    def _toggle_mic(self):
        if self.voice_enabled[0]:
            self._set_text_mode()
        else:
            self._set_voice_mode()

    def _mic_hover_enter(self):
        if not self.voice_enabled[0]:
            self._update_mic_btn(active=True)

    def _mic_hover_leave(self):
        if not self.voice_enabled[0]:
            self._update_mic_btn(active=False)

    # ═══════════════════════════════════════════════════════════
    # 发送 / 轮询
    # ═══════════════════════════════════════════════════════════
    def send_message(self, event=None):
        if self.voice_enabled[0]:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self._add_bubble(text, "user")
        self.input_queue.put(text)
        self.status_var.set("处理中...")
        self._set_status_dot(ACCENT)

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
                    if role == "assistant":
                        self.status_var.set("文字模式 · 就绪")
                        self._set_status_dot(GREEN)
                elif msg_type == "status":
                    self.status_var.set(text)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_output)

    # ═══════════════════════════════════════════════════════════
    # 启动 / 关闭
    # ═══════════════════════════════════════════════════════════
    def _startup_animation(self):
        msgs = [
            ("SYSTEM ONLINE  ·  ALL MODULES LOADED", "system"),
        ]
        for i, (m, r) in enumerate(msgs):
            self.root.after(i * 400,
                           lambda t=m, role=r: self._add_bubble(t, role))

    def _on_close(self):
        self.input_queue.put("退出")
        self.root.after(500, self.root.quit)

    def run(self):
        self.root.mainloop()
