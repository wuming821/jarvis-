# -*- coding: utf-8 -*-
"""Agent Brain — 元认知决策层"""
import json
import re as _re
from datetime import datetime
from jarvis_config import client


class AgentBrain:
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
        c = user_input.lower()
        local_patterns = ["打开", "搜索", "截图", "几点", "时间", "日期", "音量", "静音",
                          "锁屏", "记事本", "计算器", "命令行", "任务管理器", "你好",
                          "指令列表", "能做什么", "记住", "忘记", "记忆", "档案"]
        if any(p in c for p in local_patterns):
            return {"intent": "mixed", "strategy": "local", "confidence": 0.9,
                    "reason": "匹配本地指令关键词"}

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
                temperature=0.3, max_tokens=150,
            )
            text = resp.choices[0].message.content.strip()
            json_match = _re.search(r'\{[^}]+\}', text)
            if json_match:
                decision = json.loads(json_match.group())
            else:
                decision = {"intent": "chat", "strategy": "direct", "confidence": 0.5,
                            "reason": "无法解析决策JSON，默认直接回复"}
        except Exception as e:
            decision = {"intent": "chat", "strategy": "direct", "confidence": 0.3,
                        "reason": f"决策出错: {e}"}
        return decision

    def log_decision(self, user_input, decision, result_summary, success=True):
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
        if strategy in self.stats:
            self.stats[strategy]["total"] += 1
            if success:
                self.stats[strategy]["success"] += 1

    def get_summary(self):
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
            stored = d.get("stats", {})
            for k, v in stored.items():
                if k in b.stats:
                    b.stats[k] = v
        return b
