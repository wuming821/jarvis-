# -*- coding: utf-8 -*-
"""Jarvis 情绪系统 — EmotionSystem + 用户情绪检测"""
from datetime import datetime


class EmotionSystem:
    def __init__(self):
        self.valence = 0.0
        self.energy = 0.0

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


# 情绪触发词库
_EMOTION_TRIGGERS = {
    "positive": (["开心", "哈哈", "太棒了", "厉害", "谢谢", "不错", "喜欢", "爱", "太好了", "赞", "牛", "帅", "完美", "成功了", "恭喜", "快乐", "幸福", "感恩", "好耶", "nice", "great"], 0.1, 0.06),
    "praise": (["你真好", "你真棒", "聪明", "靠谱", "厉害啊", "帮大忙", "有你在", "全靠你"], 0.15, 0.1),
    "negative": (["难过", "伤心", "烦", "生气", "讨厌", "糟糕", "失败", "不行", "无聊", "郁闷", "绝望", "崩了", "坏了", "惨", "完了", "shit", "fuck"], -0.1, -0.1),
    "tired": (["累", "困", "疲惫", "没睡好", "熬夜", "通宵", "加班", "好倦"], -0.03, -0.2),
    "energetic": (["加油", "开始", "搞起来", "冲", "来吧", "开工", "干", "走起"], 0.05, 0.15),
    "late_night": ([], 0.0, 0.0),
    "greeting": (["早", "早安", "早上好", "新的一天"], 0.05, 0.12),
    "goodbye": (["晚安", "再见", "拜拜", "睡了"], 0.02, -0.08),
}


def analyze_emotion_triggers(text):
    v, e = 0.0, 0.0
    hour = datetime.now().hour
    if hour >= 23 or hour < 5:
        e -= 0.1
    elif 5 <= hour < 8:
        e += 0.08
    for category, (keywords, vd, ed) in _EMOTION_TRIGGERS.items():
        if category == "late_night":
            continue
        for kw in keywords:
            if kw in text:
                v += vd
                e += ed
                break
    return v, e


def update_emotion_from_input(emotion, user_text):
    vd, ed = analyze_emotion_triggers(user_text)
    emotion.update(vd, ed)
    emotion.decay()
    return vd, ed


# 用户情绪检测
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
    global _user_emotion_state
    for emo, keywords in _USER_EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                _user_emotion_state = emo
                return emo
    _user_emotion_state = "normal"
    return "normal"


def get_user_emotion_context():
    return _USER_EMOTION_PROMPTS.get(_user_emotion_state, "")
