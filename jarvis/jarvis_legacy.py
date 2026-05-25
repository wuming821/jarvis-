# -*- coding: utf-8 -*-
import speech_recognition as sr
import pyttsx3
from openai import OpenAI
import httpx
import sys
import socket
import subprocess
import webbrowser
import winsound
import difflib
from datetime import datetime
import json
import os
import time
import re
import pyautogui

# --- 长期记忆系统 ---
MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_memory.json")
PERSONALITY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_personality.txt")


def load_personality():
    """读取人格文件（借鉴1号.txt）"""
    if os.path.exists(PERSONALITY_FILE):
        with open(PERSONALITY_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return "你是贾维斯(Jarvis)，一个AI助手。"


class JarvisMemory:
    def __init__(self, filepath):
        self.filepath = filepath
        self.facts = []
        self.profile = {}  # 用户档案（键值对，借鉴1号.txt）
        self.reflections = []  # 反思记录 [{task, reflection, lessons, created_at}]

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.facts = data.get('facts', [])
                self.profile = data.get('profile', {})
                self.reflections = data.get('reflections', [])
                for f in self.facts:
                    f.setdefault('importance', 'medium')
                    f.setdefault('access_count', 0)
                    f.setdefault('last_accessed', f.get('created_at', ''))
                return data.get('conversations', []), data.get('emotion', {}), data.get('scheduler', {}), data.get('brain', {})
            except Exception:
                return [], {}, {}, {}
        return [], {}, {}, {}

    def save(self, conversations=None):
        data = {'facts': self.facts, 'profile': self.profile, 'reflections': self.reflections, 'emotion': emotion.to_dict(), 'scheduler': scheduler.to_dict(), 'brain': brain.to_dict()}
        if conversations is not None:
            data['conversations'] = conversations
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_reflection(self, task, content, lessons=""):
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.reflections.append({
            'task': task,
            'content': content,
            'lessons': lessons,
            'created_at': now,
        })
        if len(self.reflections) > 50:
            self.reflections = self.reflections[-50:]

    def get_reflections_context(self):
        if not self.reflections:
            return ""
        recent = self.reflections[-5:]
        lines = ["\n## 历史反思与经验教训"]
        for r in recent:
            lines.append(f"- [{r['created_at']}] 任务「{r['task'][:40]}」→ {r['lessons'][:120]}")
        return "\n".join(lines)

    def set_profile(self, key, value):
        self.profile[key] = value

    def get_profile_text(self):
        if not self.profile:
            return ""
        lines = ["\n## 用户档案"]
        for k, v in self.profile.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)

    def add_fact(self, content, importance="medium"):
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        # 冲突检测：新信息与旧记忆矛盾时标记旧记忆
        conflict_msg = ""
        for f in self.facts:
            if self._is_contradiction(content, f['content']):
                f['importance'] = 'low'
                f['content'] = f['content'] + " [已过时]"
                conflict_msg = f"（已标记旧记忆「{f['content'][:30]}...」为过时）"
        self.facts.append({
            'content': content,
            'importance': importance,
            'created_at': now,
            'last_accessed': now,
            'access_count': 0,
        })
        return conflict_msg

    def _is_contradiction(self, new_fact, old_fact):
        """简单冲突检测：关键词相似但包含否定/改变含义"""
        contradict_words = ["不是", "改了", "换", "不再是", "现在是", "变成了", "更新", "不", "别"]
        return any(w in new_fact for w in contradict_words) and \
            any(w in new_fact for w in old_fact.split() if len(w) >= 2)

    def remove_fact(self, index):
        if 0 <= index < len(self.facts):
            del self.facts[index]
            return True
        return False

    def search_facts(self, query):
        """按关键词搜索记忆，返回匹配列表"""
        results = []
        for i, f in enumerate(self.facts):
            if query.lower() in f['content'].lower():
                f['access_count'] += 1
                f['last_accessed'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                results.append((i, f))
        return results

    # 本地关键词→档案字段映射（借鉴1号.txt，快速免API）
    _PROFILE_KEYWORDS = {
        "名字": "名字", "叫": "名字", "称呼": "名字", "姓名": "名字", "名称": "名字",
        "生日": "生日", "出生": "生日", "几岁": "年龄", "年龄": "年龄",
        "爱好": "爱好", "喜欢": "爱好", "兴趣": "爱好", "爱": "爱好",
        "工作": "工作", "上班": "工作", "公司": "工作", "职业": "工作",
        "学校": "学校", "上学": "学校", "大学": "学校", "读书": "学校",
        "住址": "住址", "住在": "住址", "家": "住址", "地址": "住址",
        "电话": "电话", "手机": "电话", "号码": "电话", "联系": "电话",
        "目标": "目标", "梦想": "目标", "计划": "目标",
    }

    def retrieve_local(self, query):
        """本地关键词检索：匹配关键词→档案字段→相关记忆，速度快且免费"""
        results = []
        # 1. 关键词→档案匹配
        for kw, field in self._PROFILE_KEYWORDS.items():
            if kw in query and field in self.profile:
                results.append(f"[档案] {field}: {self.profile[field]}")
        # 2. 关键词→记忆匹配（简单包含）
        active = [f for f in self.facts if '[已过时]' not in f['content']]
        for f in active:
            # 取查询中长度≥2的词做匹配
            for word in query.replace("，", " ").replace("。", " ").split():
                if len(word) >= 2 and word in f['content']:
                    if f['content'] not in results:
                        results.append(f"[记忆] {f['content']}")
                        f['access_count'] += 1
                        f['last_accessed'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        return "\n".join(results[:5]) if results else ""

    def retrieve_relevant(self, query):
        """混合检索：先本地关键词，无结果时AI语义检索"""
        local = self.retrieve_local(query)
        if local:
            return local
        # AI 语义检索
        active = [f for i, f in enumerate(self.facts) if '[已过时]' not in f['content']]
        if not active:
            return ""
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": "你是记忆检索器。根据用户当前问题，从记忆列表中找到最相关的条目。返回最相关的3条（编号），格式：相关:#编号,#编号,#编号。若都不相关返回：相关:无"},
                    {"role": "user", "content": f"问题：{query}\n\n记忆列表：\n{indexed}\n\n哪些记忆与问题最相关？"},
                ],
                temperature=0.3,
                max_tokens=100,
            )
            answer = resp.choices[0].message.content
        except Exception:
            return ""
        # 解析编号
        ids = re.findall(r'#(\d+)', answer)
        if not ids:
            return ""
        lines = []
        for sid in ids[:3]:
            idx = int(sid)
            if 0 <= idx < len(active):
                f = active[idx]
                f['access_count'] += 1
                f['last_accessed'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                lines.append(f"- {f['content']}")
        return "\n".join(lines) if lines else ""

    def mark_accessed(self, index):
        if 0 <= index < len(self.facts):
            self.facts[index]['access_count'] += 1
            self.facts[index]['last_accessed'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    def get_facts_context(self):
        """注入重要记忆 + 用户档案到系统提示"""
        parts = []
        # 用户档案（始终注入）
        profile_text = self.get_profile_text()
        if profile_text:
            parts.append(profile_text)
        # 重要记忆
        important = [f for f in self.facts
                     if f.get('importance', 'medium') in ('high', 'medium')
                     and '[已过时]' not in f['content']]
        if important:
            important.sort(key=lambda f: (0 if f.get('importance') == 'high' else 1, f.get('created_at', '')))
            lines = ["\n## 用户长期记忆"]
            for f in important:
                tag = "⭐" if f.get('importance') == 'high' else ""
                lines.append(f"- {tag}{f['content']}")
            parts.append("\n".join(lines))
        return "\n".join(parts) if parts else ""

    def get_all_facts_text(self):
        """列出全部记忆 + 档案"""
        lines = []
        # 档案
        if self.profile:
            lines.append("═══ 用户档案 ═══")
            for k, v in self.profile.items():
                lines.append(f"  {k}: {v}")
            lines.append("")
        # 记忆
        if self.facts:
            lines.append("═══ 长期记忆 ═══")
            for i, f in enumerate(self.facts):
                imp = f.get('importance', 'medium')
                icon = {'high': '⭐', 'medium': '  ', 'low': '  '}.get(imp, '  ')
                stale = ' [已过时]' if '[已过时]' in f['content'] else ''
                lines.append(f"{i+1}. {icon}{f['content']}{stale}")
        return "\n".join(lines) if lines else "暂无记忆或档案"


memory = JarvisMemory(MEMORY_FILE)


# ======================================================
#  情绪系统
# ======================================================
class EmotionSystem:
    def __init__(self):
        self.valence = 0.0   # -1(负面) ~ +1(正面)
        self.energy = 0.0    # -1(疲惫) ~ +1(活力)

    @property
    def mood(self):
        v, e = self.valence, self.energy
        if v > 0.3 and e > 0.3:
            return "轻松愉快，活力满满"
        elif v > 0.3:
            return "心情不错，温和放松"
        elif v < -0.3 and e < -0.3:
            return "有点低落，没什么精神"
        elif v < -0.3:
            return "有点担心或在意"
        elif e > 0.5:
            return "精神很好，很清醒"
        elif e < -0.5:
            return "有点疲惫，需要休息"
        elif abs(v) < 0.15 and abs(e) < 0.15:
            return "平静如水"
        return "一切正常"

    def update(self, valence_delta=0.0, energy_delta=0.0):
        self.valence = max(-1.0, min(1.0, self.valence + valence_delta))
        self.energy = max(-1.0, min(1.0, self.energy + energy_delta))

    def decay(self):
        self.valence *= 0.97
        self.energy *= 0.97

    def get_context(self):
        return (f"\n\n## 你当前的情绪状态\n"
                f"你现在的感受：{self.mood}。"
                f"在回复中自然地流露这个情绪——高兴时语气轻快一点，"
                f"疲惫时话少一点，担心时温柔一点。但不要直接说'我心情xxx'。")

    def to_dict(self):
        return {"valence": round(self.valence, 3), "energy": round(self.energy, 3)}

    @classmethod
    def from_dict(cls, d):
        e = cls()
        if d:
            e.valence = d.get("valence", 0.0)
            e.energy = d.get("energy", 0.0)
        return e


emotion = EmotionSystem()


# 情绪触发词库
_EMOTION_TRIGGERS = {
    # (关键词列表, valence_delta, energy_delta)
    "positive": (["开心", "哈哈", "太棒了", "厉害", "谢谢", "不错", "喜欢", "爱", "太好了", "赞", "牛", "帅", "完美", "成功了", "恭喜", "快乐", "幸福", "感恩", "好耶", "nice", "great"], 0.1, 0.06),
    "praise": (["你真好", "你真棒", "聪明", "靠谱", "厉害啊", "帮大忙", "有你在", "全靠你"], 0.15, 0.1),
    "negative": (["难过", "伤心", "烦", "生气", "讨厌", "糟糕", "失败", "不行", "无聊", "郁闷", "绝望", "崩了", "坏了", "惨", "完了", "shit", "fuck"], -0.1, -0.1),
    "tired": (["累", "困", "疲惫", "没睡好", "熬夜", "通宵", "加班", "好倦"], -0.03, -0.2),
    "energetic": (["加油", "开始", "搞起来", "冲", "来吧", "开工", "干", "走起"], 0.05, 0.15),
    "late_night": ([], 0.0, 0.0),  # 时间触发，见下方
    "greeting": (["早", "早安", "早上好", "新的一天"], 0.05, 0.12),
    "goodbye": (["晚安", "再见", "拜拜", "睡了"], 0.02, -0.08),
}


def analyze_emotion_triggers(text):
    """分析用户输入，返回 (valence_delta, energy_delta)"""
    v, e = 0.0, 0.0

    # 时间触发
    hour = datetime.now().hour
    if hour >= 23 or hour < 5:
        e -= 0.1  # 深夜，自然疲惫
    elif 5 <= hour < 8:
        e += 0.08  # 清晨，自然清醒

    for category, (keywords, vd, ed) in _EMOTION_TRIGGERS.items():
        if category == "late_night":
            continue
        for kw in keywords:
            if kw in text:
                v += vd
                e += ed
                break  # 每类只触发一次

    return v, e


def update_emotion_from_input(user_text):
    """根据用户输入更新情绪并返回变化描述"""
    vd, ed = analyze_emotion_triggers(user_text)
    emotion.update(vd, ed)
    emotion.decay()
    return vd, ed


# 用户情绪检测（借鉴1号.txt）
_USER_EMOTION_KEYWORDS = {
    "happy":   ["开心", "哈哈", "爽", "高兴", "嘿嘿", "太好了", "nice", "棒", "快乐", "兴奋", "激动"],
    "tired":   ["累", "困", "疲惫", "没睡好", "熬夜", "加班", "乏了", "不想动", "没精神"],
    "sad":     ["难受", "伤心", "难过", "哭", "失落", "失望", "郁闷", "心累", "破防"],
    "angry":   ["气死", "无语", "烦死", "生气", "火大", "受不了", "恶心", "离谱", "有病", "恶心"],
}

_USER_EMOTION_PROMPTS = {
    "happy":  "\n用户现在心情不错。你语气可以轻松一点，甚至可以开个小玩笑。",
    "tired":  "\n用户现在比较疲惫。说话温柔一点，简短一点，别啰嗦。可以关心一句。",
    "sad":    "\n用户现在可能有些低落。语气温柔、包容一点，别开玩笑，认真倾听。",
    "angry":  "\n用户现在比较烦躁。语气冷静、理性，别争辩，先安抚情绪。",
    "normal": "",
}

_user_emotion_state = "normal"


def detect_user_emotion(text):
    """分析用户输入，检测用户当前情绪状态"""
    global _user_emotion_state
    for emo, keywords in _USER_EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                _user_emotion_state = emo
                return emo
    # 没有触发词时保持上一轮状态，但逐渐回正常
    _user_emotion_state = "normal"
    return "normal"


def get_user_emotion_context():
    return _USER_EMOTION_PROMPTS.get(_user_emotion_state, "")


# ======================================================
#  自主任务系统
# ======================================================
class TaskManager:
    def __init__(self):
        self.tasks = []
        self.last_interaction = time.time()
        self._last_autocheck = 0  # 自主关注计时

    def add_reminder(self, message, time_str):
        tid = str(int(time.time() * 1000))[-6:]
        self.tasks.append({"type": "reminder", "message": message, "time": time_str, "id": tid, "created": datetime.now().strftime('%m-%d %H:%M')})
        return tid

    def add_timer(self, message, seconds):
        tid = str(int(time.time() * 1000))[-6:]
        self.tasks.append({"type": "timer", "message": message, "fire_at": time.time() + seconds, "id": tid, "created": datetime.now().strftime('%m-%d %H:%M')})
        return tid

    def add_periodic(self, message, interval_minutes):
        tid = str(int(time.time() * 1000))[-6:]
        self.tasks.append({"type": "periodic", "message": message, "interval": interval_minutes * 60, "last_fired": 0, "id": tid, "created": datetime.now().strftime('%m-%d %H:%M')})
        return tid

    def check(self):
        """检查到期任务，返回通知列表"""
        now = datetime.now()
        ct = now.strftime("%H:%M")
        notifications = []
        for task in self.tasks[:]:
            if task["type"] == "reminder" and task["time"] == ct:
                notifications.append(f"⏰ {task['message']}")
                self.tasks.remove(task)
            elif task["type"] == "timer" and time.time() >= task.get("fire_at", 0):
                notifications.append(f"⏰ {task['message']}")
                self.tasks.remove(task)
            elif task["type"] == "periodic" and time.time() - task["last_fired"] >= task["interval"]:
                notifications.append(f"{task['message']}")
                task["last_fired"] = time.time()
        return notifications

    def check_autonomous(self):
        """自主关注：长时间没说话时主动问候"""
        idle = time.time() - self.last_interaction
        since_last = time.time() - self._last_autocheck
        hour = datetime.now().hour
        # 超过30分钟没说话 + 距上次自主关注>1小时 + 非深夜
        if idle > 1800 and since_last > 3600 and 8 <= hour < 23:
            self._last_autocheck = time.time()
            return "还在吗？有什么需要帮忙的随时叫我。"
        return None

    def touch(self):
        self.last_interaction = time.time()

    def get_pending(self):
        return self.tasks

    def cancel(self, task_id):
        for t in self.tasks:
            if t["id"].startswith(task_id):
                self.tasks.remove(t)
                return t["message"]
        return None

    def to_dict(self):
        return {"tasks": self.tasks, "last_interaction": self.last_interaction, "last_autocheck": self._last_autocheck}

    @classmethod
    def from_dict(cls, d):
        tm = cls()
        if d:
            tm.tasks = d.get("tasks", [])
            tm.last_interaction = d.get("last_interaction", time.time())
            tm._last_autocheck = d.get("last_autocheck", 0)
        return tm


scheduler = TaskManager()

# ======================================================
#  Agent Brain — 元认知决策层
# ======================================================
class AgentBrain:
    """中央决策大脑：分析输入→分类意图→选择最优策略→记录结果"""

    INTENTS = {
        "action": "执行操作（打开程序/点击/输入/截图/搜索等电脑操作）",
        "query": "信息查询（时间/日期/记忆/档案/知识问答）",
        "planning": "需要制定计划再执行的复杂任务",
        "reflection": "回顾分析已完成的任务，总结经验",
        "memory_mgmt": "记忆管理（记住/忘记/搜索记忆）",
        "chat": "闲聊/问候/情绪表达，无需工具",
    }

    STRATEGIES = {
        "local": "本地指令匹配，最快最省",
        "tool_single": "AI + 单个工具调用",
        "tool_chain": "AI + 多工具链式协作",
        "agent_spawn": "派遣专门子Agent处理",
        "autonomous": "自主规划→逐步执行→反思，全自动管道",
        "direct": "AI直接回复，不调工具",
    }

    def __init__(self):
        self.log = []
        self.stats = {k: {"total": 0, "success": 0} for k in self.STRATEGIES}

    def think(self, user_input):
        """分析用户输入，返回最优策略决策"""
        c = user_input.lower()

        # 快速规则判断（免API）
        # 本地指令匹配
        local_patterns = ["打开", "搜索", "截图", "几点", "时间", "日期", "音量", "静音",
                          "锁屏", "记事本", "计算器", "命令行", "任务管理器", "你好",
                          "指令列表", "能做什么", "记住", "忘记", "记忆", "档案"]
        if any(p in c for p in local_patterns):
            return {"intent": "mixed", "strategy": "local", "confidence": 0.9,
                    "reason": f"匹配本地指令关键词"}

        # AI 分类（轻量调用）
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": f"你是Jarvis的大脑决策器。分析用户输入，输出JSON：\n"
                     f"意图类型({', '.join(self.INTENTS.keys())})\n"
                     f"最优策略({', '.join(self.STRATEGIES.keys())})\n"
                     f"置信度(0-1)\n原因(一句话)\n\n规则：\n"
                     f"- 闲聊/问候→direct\n- 简单操作→tool_single\n"
                     f"- 复杂多步操作→tool_chain 或 autonomous\n"
 f"- 需要搜索研究→agent_spawn:researcher\n- 需要反思→agent_spawn:reflector\n"
                     f"只输出JSON: {{\"intent\":\"...\",\"strategy\":\"...\",\"confidence\":0.X,\"reason\":\"...\"}}"},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.3,
                max_tokens=150,
            )
            text = resp.choices[0].message.content.strip()
            # 解析 JSON
            import re as _re
            json_match = _re.search(r'\{[^}]+\}', text)
            if json_match:
                decision = json.loads(json_match.group())
            else:
                # JSON 解析失败，用 AI 文本推理
                decision = {"intent": "chat", "strategy": "direct", "confidence": 0.5,
                            "reason": "无法解析决策JSON，默认直接回复"}
        except Exception as e:
            decision = {"intent": "chat", "strategy": "direct", "confidence": 0.3,
                        "reason": f"决策出错: {e}"}

        return decision

    def log_decision(self, user_input, decision, result_summary, success=True):
        """记录决策及结果，用于统计优化"""
        strategy = decision.get("strategy", "unknown")
        self.log.append({
            "time": datetime.now().strftime('%m-%d %H:%M'),
            "input": user_input[:80],
            "intent": decision.get("intent", "?"),
            "strategy": strategy,
            "confidence": decision.get("confidence", 0),
            "success": success,
            "result": result_summary[:100],
        })
        if len(self.log) > 100:
            self.log = self.log[-100:]
        # 更新统计
        if strategy in self.stats:
            self.stats[strategy]["total"] += 1
            if success:
                self.stats[strategy]["success"] += 1

    def get_summary(self):
        """返回决策统计摘要"""
        lines = ["═══ Brain决策统计 ═══"]
        total = sum(s["total"] for s in self.stats.values())
        lines.append(f"总决策: {total}次")
        for name, s in sorted(self.stats.items(), key=lambda x: -x[1]["total"]):
            if s["total"] > 0:
                rate = s["success"] / s["total"] * 100
                lines.append(f"  {name}: {s['total']}次 成功率{rate:.0f}%")
        recent = self.log[-3:] if self.log else []
        if recent:
            lines.append("最近决策:")
            for r in recent:
                icon = "✅" if r["success"] else "❌"
                lines.append(f"  {icon} [{r['strategy']}] {r['input'][:50]}")
        return "\n".join(lines)

    def to_dict(self):
        return {"log": self.log[-20:], "stats": self.stats}

    @classmethod
    def from_dict(cls, d):
        b = cls()
        if d:
            b.log = d.get("log", [])
            b.stats = d.get("stats", {k: {"total": 0, "success": 0} for k in cls.STRATEGIES})
            if b.stats:
                for k, v in d.get("stats", {}).items():
                    if k in b.stats:
                        b.stats[k] = v
        return b


brain = AgentBrain()

# --- 注册联想浏览器为 Jarvis 专属浏览器 ---
SLBROWSER_PATH = r"C:\Program Files (x86)\Lenovo\SLBrowser\SLBrowser.exe"
webbrowser.register("slbrowser", None, webbrowser.BackgroundBrowser(SLBROWSER_PATH))
browser = webbrowser.get("slbrowser")
# 注意：后续所有 open_url(...) 替换为 browser.open(...)

# --- 代理检测 ---
def _create_client():
    proxy_url = "http://127.0.0.1:7897"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    proxy_alive = s.connect_ex(('127.0.0.1', 7897)) == 0
    s.close()

    if proxy_alive:
        print('[启动] 代理在线，通过代理连接 DeepSeek')
        http_client = httpx.Client(proxy=proxy_url)
    else:
        print('[启动] 代理离线，直连模式')
        http_client = httpx.Client()

    return OpenAI(
        api_key="sk-placeholder",
        base_url="https://api.deepseek.com",
        http_client=http_client,
    )

client = _create_client()

# --- TTS 引擎 ---
engine = pyttsx3.init()
engine.setProperty('rate', 180)
engine.setProperty('volume', 1.0)
voices = engine.getProperty('voices')
for voice in voices:
    if 'chinese' in voice.name.lower() or 'zh' in voice.id.lower():
        engine.setProperty('voice', voice.id)
        break

# --- 语音识别器 ---
recognizer = sr.Recognizer()
recognizer.energy_threshold = 100
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.8

# --- AI 对话历史 ---
# 人格从 jarvis_personality.txt 加载（借鉴1号.txt），这里只放功能规则
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
    facts = memory.get_facts_context()
    reflections = memory.get_reflections_context()
    mood = emotion.get_context()
    user_emo = get_user_emotion_context()
    return personality + mood + user_emo + BASE_FUNCTIONAL_PROMPT + "\n" + facts + reflections


messages = [
    {"role": "system", "content": build_system_prompt()},
]
MAX_HISTORY = 20

# --- 唤醒词 ---
WAKE_WORDS = [
    "贾维斯", "jarvis", "hey jarvis", "嘿贾维斯",
    # 语音识别常见变体（同音/近音字）
    "甲伟斯", "家维斯", "家卫士", "贾伟斯", "贾卫士", "嘉维斯",
    "嘉卫士", "甲维斯", "贾微斯", "家伟斯", "佳维斯",
]
ACK_BEEP = (800, 100)  # 800Hz, 100ms 短促提示音


def _find_wake_word(text):
    """在文本中查找唤醒词（精确 + 模糊匹配兜底）。返回 (唤醒词, 位置, 长度) 或 (None, -1, 0)"""
    t = text.lower()

    # 1. 精确匹配（含变体白名单）
    for ww in WAKE_WORDS:
        idx = t.find(ww)
        if idx != -1:
            return ww, idx, len(ww)

    # 2. 模糊匹配兜底 — 滑动窗口比对 "贾维斯"
    TARGET = "贾维斯"
    for i in range(len(t) - len(TARGET) + 1):
        window = t[i:i + len(TARGET)]
        if difflib.SequenceMatcher(None, TARGET, window).ratio() >= 0.5:
            return TARGET, i, len(TARGET)

    return None, -1, 0


# ======================================================
#  工具函数
# ======================================================
def open_url(url):
    """用联想浏览器打开网址"""
    browser.open(url)


TEXT_MODE = '--text' in sys.argv


def speak(text):
    print(f'贾维斯: {text}')
    engine.say(text)
    engine.runAndWait()


def listen_text():
    """文字输入模式（--text 参数启用）"""
    try:
        text = input('\n你: ').strip()
        return text
    except (EOFError, KeyboardInterrupt):
        return "退出"


def listen():
    """录音并识别，Whisper 本地优先（不受网络影响），失败回退 Google"""
    with sr.Microphone() as source:
        print('\n[正在听...]')
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return ""

    # Whisper 本地优先，Google 在线作备胎
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


def chat(user_input):
    """AI 对话"""
    messages.append({"role": "user", "content": user_input})
    if len(messages) > MAX_HISTORY + 1:
        del messages[1:3]

    messages[0]["content"] = build_system_prompt()

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=messages,
            temperature=0.8,
            max_tokens=2000,
        )
        reply = response.choices[0].message.content
        messages.append({"role": "assistant", "content": reply})
        _save_conversations()
        return reply
    except Exception as e:
        return f"抱歉先生，系统出了点问题: {e}"


def _save_conversations():
    memory.save(conversations=messages[1:])


def _load_conversations():
    saved, emo_data, sch_data, brain_data = memory.load()
    global emotion, scheduler, brain
    emotion = EmotionSystem.from_dict(emo_data)
    scheduler = TaskManager.from_dict(sch_data)
    brain = AgentBrain.from_dict(brain_data)
    if saved:
        messages.extend(saved)


# ======================================================
#  电脑控制（pyautogui）
# ======================================================
pyautogui.FAILSAFE = True  # 鼠标移到屏幕左上角可紧急中止


# --- 屏幕 ---
def get_screen_size():
    s = pyautogui.size()
    return s.width, s.height


def screenshot(filepath=None):
    if filepath is None:
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    pyautogui.screenshot(filepath)
    return filepath


# --- 鼠标 ---
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


# --- 键盘 ---
def type_unicode(text):
    pyautogui.write(text)


def press_key(key):
    pyautogui.press(key)


def hotkey(*keys):
    pyautogui.hotkey(*keys)


# --- 组合动作 ---
def open_windows_search():
    pyautogui.press('win')
    time.sleep(0.3)


def run_program(program_name):
    open_windows_search()
    time.sleep(0.2)
    pyautogui.write(program_name)
    time.sleep(0.3)
    pyautogui.press('enter')


# ======================================================
#  AI 工具系统
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
#  多 Agent 系统
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


def _run_agent(agent_type, task):
    """启动一个子Agent执行专项任务，最多5轮工具调用"""
    agent_cfg = AGENT_TYPES.get(agent_type)
    if not agent_cfg:
        return f"未知Agent类型: {agent_type}，可选: {', '.join(AGENT_TYPES.keys())}"

    # 筛选该Agent可用的工具
    agent_tools = [t for t in TOOLS if t["function"]["name"] in agent_cfg["tools"]]

    agent_msgs = [
        {"role": "system", "content": agent_cfg["system_prompt"]},
        {"role": "user", "content": task},
    ]

    tool_called = False
    for round_idx in range(5):
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=agent_msgs,
                tools=agent_tools,
                temperature=0.7,
                max_tokens=1200,
            )
        except Exception as e:
            return f"[{agent_cfg['name']}] 出错: {e}"

        choice = resp.choices[0]
        msg = choice.message

        if msg.tool_calls:
            tool_called = True
            agent_msgs.append({
                "role": "assistant",
                "content": msg.content,
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
    """执行单个步骤，最多3轮工具调用，含验证和一次自动重试"""

    def _try_execute():
        step_msgs = [
            {"role": "system", "content": f"你正在执行一个多步骤任务。目标是：「{goal}」\n"
             f"当前第{step_num}/{total}步：{step_desc}\n"
             "用工具完成这一步，完成后汇报结果。不需要工具就直接回复完成。"},
        ]
        for _ in range(3):
            try:
                resp = client.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=step_msgs,
                    tools=TOOLS,
                    temperature=0.7,
                    max_tokens=1000,
                )
            except Exception as e:
                return False, f"出错: {e}"
            choice = resp.choices[0]
            msg = choice.message
            if msg.tool_calls:
                step_msgs.append({
                    "role": "assistant",
                    "content": msg.content,
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
            # 验证：问 AI 这一步是否真的成功了
            ok, verify_text = _verify_step(step_desc, result_text)
            return ok, (result_text + "\n" + verify_text) if not ok else result_text
        return False, f"步骤{step_num}达到最大轮次"

    ok, text = _try_execute()
    if ok:
        return f"✅ {text}"
    # 自动重试一次
    print(f"      [验证失败，自动重试...]")
    ok2, text2 = _try_execute()
    return f"{'✅' if ok2 else '❌'} {text2}"


def _verify_step(step_desc, result_text):
    """让 AI 验证步骤是否真的成功（借鉴1号.txt的反思检查）"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": "你是任务验证器。判断这一步是否真正完成了。如果结果中提到'已完成''已打开''已保存''已输入'等明确完成词，就是成功。如果提到'失败''出错''无法''未找到'等，就是失败。只回答：成功 或 失败，并一句话说明。"},
                {"role": "user", "content": f"步骤: {step_desc}\n执行结果: {result_text}\n\n这一步成功了吗？"},
            ],
            temperature=0.3,
            max_tokens=100,
        )
        answer = resp.choices[0].message.content
        if "失败" in answer:
            return False, answer
        return True, answer
    except Exception:
        return True, ""  # 验证本身失败时默认信任原结果


def _reflect_on_execution(goal, plan_text, results_text):
    """执行后反思：分析成败，提炼经验教训，存入长期记忆"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": "你是反思分析器。回顾刚才执行的任务，分析：1)哪些步骤成功了？2)哪些可以改进？3)下次遇到类似任务应该怎么做？请简洁输出，重点是一句话经验教训（以'教训：'开头）。"},
                {"role": "user", "content": f"目标：{goal}\n\n计划：\n{plan_text}\n\n执行结果：\n{results_text}"},
            ],
            temperature=0.6,
            max_tokens=400,
        )
        reflection = resp.choices[0].message.content
    except Exception as e:
        reflection = f"反思生成失败: {e}"

    # 提取教训
    lesson_match = re.search(r'教训[：:]\s*(.+?)(?:\n|$)', reflection)
    lessons = lesson_match.group(1).strip() if lesson_match else reflection[:120]

    memory.add_reflection(goal, reflection, lessons)
    memory.save()
    print(f"  [反思] {lessons[:80]}")
    return reflection, lessons


def execute_tool(tool_name, arguments):
    """执行工具调用，返回结果字符串"""
    if tool_name == "open_website":
        url = arguments.get("url", "")
        name = arguments.get("name", url)
        browser.open(url)
        return f"已打开 {name}"

    elif tool_name == "search_web":
        query = arguments.get("query", "")
        url = f"https://www.google.com/search?q={query}"
        browser.open(url)
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
        tid = scheduler.add_reminder(arguments["message"], arguments["time"])
        memory.save()
        return f"已设置提醒 [{tid}]：{arguments['time']} — {arguments['message']}"

    elif tool_name == "schedule_timer":
        minutes = arguments.get("minutes", 5)
        tid = scheduler.add_timer(arguments["message"], minutes * 60)
        memory.save()
        return f"已设置倒计时 [{tid}]：{minutes}分钟后提醒「{arguments['message']}」"

    elif tool_name == "list_tasks":
        tasks = scheduler.get_pending()
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
        # 创建 plans 文件夹
        plans_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plans")
        os.makedirs(plans_dir, exist_ok=True)
        # 用 AI 生成计划
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": "你是一个AI任务规划助手。把用户的目标拆成简洁明确的步骤。用编号列表输出，每一步一行。格式：1. xxx\n2. xxx\n3. xxx\n不要额外解释，直接输出步骤。"},
                    {"role": "user", "content": goal},
                ],
                temperature=0.7,
                max_tokens=1000,
            )
            plan = resp.choices[0].message.content
        except Exception as e:
            return f"规划失败: {e}"
        # 保存
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

        # 阶段1: Planner Agent 生成计划
        print(f"  [阶段1] Planner Agent 规划中...")
        plan_text = _run_agent("planner", f"为以下目标生成详细步骤计划，每步一行，编号格式 1.xxx\n2.xxx：\n\n{goal}")
        if "出错" in plan_text or "达到最大轮次" in plan_text:
            # 回退：直接调 AI
            try:
                resp = client.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=[
                        {"role": "system", "content": "把用户目标拆成编号步骤。格式：1. xxx\n2. xxx"},
                        {"role": "user", "content": goal},
                    ],
                    temperature=0.7, max_tokens=1000,
                )
                plan_text = resp.choices[0].message.content
            except Exception as e:
                return f"规划失败: {e}"

        # 解析步骤（从 Agent 回复或 AI 回复中提取）
        steps = re.findall(r'^\d+\.\s*(.+)', plan_text, re.MULTILINE)
        if not steps:
            return f"无法解析计划步骤:\n{plan_text}"

        print(f"  [计划] {len(steps)} 个步骤:")
        for i, s in enumerate(steps):
            print(f"    {i+1}. {s}")

        # 阶段2: Executor 逐步执行
        print(f"  [阶段2] 开始执行...")
        results = []
        for i, step in enumerate(steps):
            print(f"  [执行 {i+1}/{len(steps)}] {step[:60]}...")
            result = _execute_single_step(step, goal, i + 1, len(steps))
            results.append(f"✓步骤{i+1}: {step}\n  → {result}")

        summary = "\n".join(results)

        # 阶段3: Reflector Agent 反思
        print(f"  [阶段3] Reflector Agent 反思中...")
        refl_input = f"目标：{goal}\n\n计划：\n{plan_text}\n\n执行结果：\n{summary}"
        reflection = _run_agent("reflector", f"分析以下任务执行情况，提炼经验教训，重要经验调用 remember_fact 保存：\n\n{refl_input}")
        # 提取教训存入记忆
        lesson_match = re.search(r'教训[：:]\s*(.+?)(?:\n|$)', reflection)
        lessons = lesson_match.group(1).strip() if lesson_match else reflection[:120]
        memory.add_reflection(goal, reflection, lessons)
        memory.save()

        # 保存
        plans_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plans")
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
        result = _run_agent(agent_type, task)
        return result

    elif tool_name == "brain_summary":
        return brain.get_summary()

    elif tool_name == "cancel_task":
        msg = scheduler.cancel(arguments["task_id"])
        memory.save()
        return f"已取消「{msg}」" if msg else "未找到该任务"

    elif tool_name == "update_profile":
        key = arguments.get("key", "")
        value = arguments.get("value", "")
        memory.set_profile(key, value)
        memory.save()
        return f"档案已更新: {key} → {value}"

    elif tool_name == "get_profile":
        if not memory.profile:
            return "暂无档案信息"
        return "\n".join(f"{k}: {v}" for k, v in memory.profile.items())

    elif tool_name == "remember_fact":
        importance = arguments.get("importance", "medium")
        conflict = memory.add_fact(arguments["fact"], importance)
        memory.save()
        base = f"已记住「{arguments['fact']}」[重要性:{importance}]"
        return base + " " + conflict if conflict else base

    elif tool_name == "search_memory":
        query = arguments.get("query", "")
        results = memory.search_facts(query)
        if not results:
            return f"记忆中未找到关于「{query}」的信息"
        lines = [f"搜索「{query}」结果:"]
        for i, f in results:
            lines.append(f"#{i+1} {f['content']}")
        return "\n".join(lines)

    elif tool_name == "retrieve_memories":
        topic = arguments.get("topic", "")
        result = memory.retrieve_relevant(topic)
        if not result:
            return f"未找到与「{topic}」相关的记忆"
        return f"与「{topic}」最相关的记忆:\n{result}"

    elif tool_name == "recall_memories":
        text = memory.get_all_facts_text()
        return text

    elif tool_name == "forget_memory":
        target = arguments.get("target", "")
        if target.isdigit():
            idx = int(target) - 1
            if memory.remove_fact(idx):
                memory.save()
                return "已删除"
            return "序号不存在"
        for i, f in enumerate(memory.facts):
            if target in f["content"]:
                memory.remove_fact(i)
                memory.save()
                return f"已忘记「{f['content']}」"
        return "未找到匹配的记忆"

    elif tool_name == "ai_query":
        prompt = arguments.get("prompt", "")
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000,
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"AI查询失败: {e}"

    elif tool_name == "search_and_summarize":
        topic = arguments.get("topic", "")
        # 1. 搜索
        browser.open(f"https://www.google.com/search?q={topic}")
        time.sleep(0.5)
        # 2. AI 生成总结
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{"role": "user", "content": f"请用中文简洁介绍：{topic}（200字以内）"}],
                temperature=0.7,
                max_tokens=500,
            )
            summary = resp.choices[0].message.content
        except Exception as e:
            summary = f"总结生成失败: {e}"
        # 3. 保存文件
        safe_name = "".join(c for c in topic if c not in r'\/:*?"<>|')[:30]
        filename = f"{safe_name}.txt"
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# {topic}\n\n{summary}")
        # 4. 打开文件
        os.startfile(filepath)
        return f"已搜索「{topic}」→ AI总结 → 保存到 {filename} → 已打开"

    elif tool_name == "save_text_file":
        filename = arguments.get("filename", "output.txt")
        content = arguments.get("content", "")
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
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


# ======================================================
#  AI 工具对话（多工具协作引擎）
# ======================================================
MAX_TOOL_ROUNDS = 8


def _auto_retrieve_context(user_input):
    """自动检索与当前输入相关的记忆，注入对话上下文"""
    retrieved = memory.retrieve_relevant(user_input)
    if retrieved:
        return f"\n[相关记忆]\n{retrieved}"
    return ""


def chat_with_tools(user_input):
    """AI 对话 + 工具调用循环，支持多工具链式协作"""
    update_emotion_from_input(user_input)
    detect_user_emotion(user_input)

    # 自动检索相关记忆并注入
    memory_ctx = _auto_retrieve_context(user_input)
    augmented_input = user_input + memory_ctx if memory_ctx else user_input
    messages.append({"role": "user", "content": augmented_input})
    if len(messages) > MAX_HISTORY + 1:
        del messages[1:3]

    messages[0]["content"] = build_system_prompt()

    for round_idx in range(MAX_TOOL_ROUNDS):
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=messages,
                tools=TOOLS,
                temperature=0.8,
                max_tokens=2000,
            )
        except Exception as e:
            return f"抱歉先生，系统出了点问题: {e}"

        choice = response.choices[0]
        msg = choice.message

        # AI 调工具
        if msg.tool_calls:
            tool_count = len(msg.tool_calls)
            if tool_count > 1:
                print(f"  [第{round_idx+1}轮] AI 并行调用 {tool_count} 个工具:")

            # 保存 assistant 消息（含 tool_calls）
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # 执行每个工具
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

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            continue

        # AI 给最终回复
        reply = msg.content or ""
        messages.append({"role": "assistant", "content": reply})
        _save_conversations()
        return reply

    return "抱歉先生，这个任务步骤有点多，请拆成几个小任务让我逐步完成。"


def _save_conversations():
    """只保存 user/assistant 有内容的对话（跳过工具调用细节）"""
    saved = []
    for m in messages[1:]:
        if m["role"] == "user":
            saved.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant" and m.get("content"):
            saved.append({"role": "assistant", "content": m["content"]})
    memory.save(conversations=saved)


def _load_conversations():
    saved = memory.load()
    if saved:
        messages.extend(saved)


# ======================================================
#  指令处理（借鉴 1号.txt 的简单 in 匹配风格）
# ======================================================
def handle_command(cmd):
    """用最朴素的 if xxx in cmd 匹配指令，返回 (响应文本或None, 是否已处理)"""
    c = cmd.lower()

    # --- 打开网站（放最前面，匹配最常用） ---
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
                open_url(url)
                return None, True

    # --- 搜索引擎 ---
    for prefix in ["搜索", "搜一下", "帮我搜", "查一下"]:
        if prefix in c:
            idx = c.index(prefix) + len(prefix)
            query = cmd[idx:].strip()
            if query:
                open_url(f"https://www.google.com/search?q={query}")
                speak(f"正在搜索{query}")
                return None, True

    # --- 打开程序 ---
    if "记事本" in c or "notepad" in c:
        subprocess.Popen("notepad.exe")
        speak("记事本已打开")
        return None, True

    if "计算器" in c or "calculator" in c:
        subprocess.Popen("calc.exe")
        speak("计算器已打开")
        return None, True

    if "命令行" in c or "cmd" in c or "终端" in c:
        subprocess.Popen("cmd.exe")
        speak("命令行已打开")
        return None, True

    if "浏览器" in c or "上网" in c or "打开网页" in c or "browser" in c:
        open_url("https://www.google.com")
        speak("浏览器已打开")
        return None, True

    if "任务管理器" in c:
        subprocess.Popen("taskmgr.exe")
        speak("任务管理器已打开")
        return None, True

    if "设置" in c or "settings" in c:
        subprocess.Popen("ms-settings:")
        speak("设置已打开")
        return None, True

    if "vs code" in c or "vscode" in c or "写代码" in c or "coding" in c:
        subprocess.Popen(r"C:\Users\sp\AppData\Local\Programs\Microsoft VS Code\Code.exe")
        speak("VS Code 已打开")
        return None, True

    # --- 系统控制 ---
    if "锁屏" in c or "锁定" in c:
        subprocess.Popen("rundll32.exe user32.dll,LockWorkStation")
        speak("屏幕已锁定")
        return None, True

    if "静音" in c or "mute" in c:
        pyautogui.press('volumemute')
        speak("已静音")
        return None, True

    if "音量增大" in c or "大点声" in c or "声音大" in c or "提高音量" in c:
        pyautogui.press('volumeup', presses=3)
        return "<<silent>>", True

    if "音量减小" in c or "小点声" in c or "声音小" in c or "降低音量" in c:
        pyautogui.press('volumedown', presses=3)
        return "<<silent>>", True

    # --- 信息查询 ---
    if "几点" in c or "时间" in c or "日期" in c or "今天几号" in c or "星期几" in c:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        wd = weekdays[now.weekday()]
        return f"现在是{now.year}年{now.month}月{now.day}日，{wd}，{now.hour}点{now.minute}分", True

    # --- 电脑控制（直接指令） ---
    if "截图" in c or "截屏" in c:
        path = screenshot()
        return f"截图已保存到桌面，先生。", True

    if "鼠标位置" in c or "鼠标在哪" in c:
        x, y = get_mouse_pos()
        w, h = get_screen_size()
        return f"鼠标在 ({x}, {y})，屏幕分辨率 {w}x{h}，先生。", True

    if "滚动" in c:
        m = re.search(r'滚动.*?(-?\d+)', c)
        amount = int(m.group(1)) if m else 3
        if "下" in c:
            amount = -abs(amount)
        mouse_scroll(amount)
        return "<<silent>>", True

    mo = re.match(r'移动鼠标到\s*(\d+)[,，\s]+(\d+)', cmd)
    if mo:
        x, y = int(mo.group(1)), int(mo.group(2))
        move_mouse(x, y)
        return f"鼠标已移到 ({x}, {y})", True

    mo = re.match(r'(?:点击|单击)\s*(\d+)[,，\s]+(\d+)', cmd)
    if mo:
        click(int(mo.group(1)), int(mo.group(2)))
        return "已点击", True

    mo = re.match(r'双击\s*(\d+)[,，\s]+(\d+)', cmd)
    if mo:
        double_click(int(mo.group(1)), int(mo.group(2)))
        return "已双击", True

    mo = re.match(r'右键\s*(\d+)[,，\s]+(\d+)', cmd)
    if mo:
        right_click(int(mo.group(1)), int(mo.group(2)))
        return "已右键", True

    if "输入" in c:
        idx = c.index("输入") + 2
        text = cmd[idx:].strip()
        if text:
            type_unicode(text)
            return f"已输入「{text}」", True

    mo = re.match(r'按(.+?)键', cmd)
    if mo:
        press_key(mo.group(1).strip())
        return "<<silent>>", True

    if "组合键" in c:
        mo = re.search(r'组合键\s*(.+)', cmd)
        if mo:
            keys = [k.strip() for k in mo.group(1).split()]
            hotkey(*keys)
            return "<<silent>>", True

    # --- 用户档案（本地快速提取，借鉴1号.txt） ---
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
                if val:
                    memory.set_profile(field, val)
                    memory.save()
                    return f"已记住你的{field}，先生。", True

    # --- 记忆管理 ---
    if "记住" in c or "记下" in c:
        for prefix in ["记住", "记下"]:
            if prefix in c:
                idx = c.index(prefix) + len(prefix)
                fact = cmd[idx:].strip()
                if fact:
                    memory.add_fact(fact, "high")
                    memory.save()
                    return f"已记住「{fact}」[高优先级]，先生。", True

    if any(w in c for w in ["你记得什么", "我的记忆", "记忆列表", "你记了什么"]):
        text = memory.get_all_facts_text()
        return text, True

    if "搜索记忆" in c:
        mo = re.search(r'搜索记忆\s*(.+)', cmd)
        if mo:
            results = memory.search_facts(mo.group(1).strip())
            if not results:
                return "记忆中没有相关信息，先生。", True
            lines = [f"搜索结果:"]
            for i, f in results:
                lines.append(f"#{i+1} {f['content']}")
            return "\n".join(lines), True

    if "忘记" in c:
        num_match = re.search(r'忘记.*?第?\s*(\d+)', c)
        if num_match:
            idx = int(num_match.group(1)) - 1
            if memory.remove_fact(idx):
                memory.save()
                return "已删除，先生。", True
            return "没有这条记忆，先生。", True
        for prefix in ["忘记"]:
            if prefix in c:
                to_forget = c[c.index(prefix) + len(prefix):].strip()
                for i, f in enumerate(memory.facts):
                    if to_forget in f['content']:
                        memory.remove_fact(i)
                        memory.save()
                        return f"已忘记「{f['content']}」，先生。", True
        return "我没有找到这条记忆，先生。", True

    # --- 你好 ---
    if "你好" in c or "hello" in c or "hi" in c:
        return "你好先生，有什么可以帮您的？", True

    # 未匹配
    return None, False


def main():
    print('=' * 50)
    print('  J.A.R.V.I.S.')
    print('  Just A Rather Very Intelligent System')
    print('=' * 50)
    if TEXT_MODE:
        print("  文字模式 | 直接输入对话，无需唤醒词 | 输入 退出 关闭")
    else:
        print("  语音模式 | 唤醒词: 贾维斯 / Hey Jarvis | 指令优先 | AI 兜底")
    _load_conversations()
    pending = len(scheduler.get_pending())
    total_decisions = sum(s["total"] for s in brain.stats.values())
    print(f'  [记忆 {len(memory.facts)}条 | 对话 {len(messages)-1}轮 | 情绪 {emotion.mood} | 任务 {pending}个 | Brain决策 {total_decisions}次]')
    print('=' * 50)
    if not TEXT_MODE:
        speak('贾维斯系统已就绪。')
    else:
        print('贾维斯系统已就绪。')
        engine.say('贾维斯系统已就绪')
        engine.runAndWait()

    _listen = listen_text if TEXT_MODE else listen

    while True:
        # 检查到期任务和自主关注
        for note in scheduler.check():
            print(f'[通知] {note}')
            if not TEXT_MODE:
                speak(note)
            else:
                print(f'贾维斯: {note}')

        auto_msg = scheduler.check_autonomous()
        if auto_msg:
            print(f'[自主] {auto_msg}')
            if not TEXT_MODE:
                speak(auto_msg)
            else:
                print(f'贾维斯: {auto_msg}')

        cmd = _listen()
        if not cmd:
            continue

        scheduler.touch()

        # 退出
        if any(w in cmd for w in ['退出', '再见', '关闭', '拜拜']):
            memory.save()
            if TEXT_MODE:
                print('贾维斯: 再见。')
            else:
                speak('再见。')
            return

        # 文字模式：无需唤醒词，直接处理
        if TEXT_MODE:
            command = cmd
        else:
            wake_word, wake_idx, wake_len = _find_wake_word(cmd)
            if wake_idx == -1:
                continue
            command = cmd[wake_idx + wake_len:].strip()
            print(f'[唤醒: {wake_word}]')
            winsound.Beep(*ACK_BEEP)
            if not command:
                speak("我在")
                continue

        # 指令列表
        if any(w in command for w in ['指令列表', '你能做什么', '有什么命令']):
            msg = "本地指令：网站/搜索/程序/系统/截图/鼠标/按键。AI工具：对话/控制电脑/搜索/记忆，你想做什么直接说就好。"
            if TEXT_MODE:
                print(f"贾维斯: {msg}")
            else:
                speak(msg)
            continue

        # Brain 决策
        decision = brain.think(command)
        strategy = decision.get("strategy", "direct")
        print(f"  [Brain] {decision.get('intent','?')} → {strategy} ({decision.get('confidence',0):.0%}) {decision.get('reason','')[:50]}")

        success = True
        response_text = ""

        # 先走本地指令（最快路径）
        reply, handled = handle_command(command)
        if handled:
            if reply and reply != "<<silent>>":
                response_text = reply
                if TEXT_MODE:
                    print(f"贾维斯: {reply}")
                else:
                    speak(reply)
            brain.log_decision(command, decision, response_text or "(静默)", True)
            continue

        # Brain 策略路由
        if strategy == "agent_spawn" and not handled:
            # 预判需要哪个Agent
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
            # 走 AI 工具对话（默认）
            if TEXT_MODE:
                print("贾维斯: ", end="", flush=True)
            response_text = chat_with_tools(command)
            if TEXT_MODE:
                print(response_text)
            else:
                speak(response_text)
            success = "抱歉" not in response_text and "出错" not in response_text

        brain.log_decision(command, decision, response_text, success)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n[贾维斯已关闭]')
        sys.exit(0)
