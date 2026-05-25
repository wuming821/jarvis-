# -*- coding: utf-8 -*-
"""Jarvis 长期记忆系统 — JarvisMemory 类"""
import json
import os
import re
from datetime import datetime
from jarvis_config import client, _sanitize_recursive, sanitize_text


class JarvisMemory:
    def __init__(self, filepath):
        self.filepath = filepath
        self.facts = []
        self.profile = {}
        self.reflections = []

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
                return (data.get('conversations', []), data.get('emotion', {}),
                        data.get('scheduler', {}), data.get('brain', {}))
            except Exception:
                return [], {}, {}, {}
        return [], {}, {}, {}

    def save(self, conversations=None, emotion=None, scheduler=None, brain=None):
        data = {'facts': self.facts, 'profile': self.profile, 'reflections': self.reflections}
        if emotion:
            data['emotion'] = emotion.to_dict()
        if scheduler:
            data['scheduler'] = scheduler.to_dict()
        if brain:
            data['brain'] = brain.to_dict()
        if conversations is not None:
            data['conversations'] = conversations
        data = _sanitize_recursive(data)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_reflection(self, task, content, lessons=""):
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.reflections.append({
            'task': task, 'content': content,
            'lessons': lessons, 'created_at': now,
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
        conflict_msg = ""
        for f in self.facts:
            if self._is_contradiction(content, f['content']):
                f['importance'] = 'low'
                f['content'] = f['content'] + " [已过时]"
                conflict_msg = f"（已标记旧记忆「{f['content'][:30]}...」为过时）"
        self.facts.append({
            'content': content, 'importance': importance,
            'created_at': now, 'last_accessed': now, 'access_count': 0,
        })
        return conflict_msg

    def _is_contradiction(self, new_fact, old_fact):
        contradict_words = ["不是", "改了", "换", "不再是", "现在是", "变成了", "更新", "不", "别"]
        return any(w in new_fact for w in contradict_words) and \
            any(w in new_fact for w in old_fact.split() if len(w) >= 2)

    def remove_fact(self, index):
        if 0 <= index < len(self.facts):
            del self.facts[index]
            return True
        return False

    def search_facts(self, query):
        results = []
        for i, f in enumerate(self.facts):
            if query.lower() in f['content'].lower():
                f['access_count'] += 1
                f['last_accessed'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                results.append((i, f))
        return results

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
        results = []
        for kw, field in self._PROFILE_KEYWORDS.items():
            if kw in query and field in self.profile:
                results.append(f"[档案] {field}: {self.profile[field]}")
        active = [f for f in self.facts if '[已过时]' not in f['content']]
        for f in active:
            for word in query.replace("，", " ").replace("。", " ").split():
                if len(word) >= 2 and word in f['content']:
                    if f['content'] not in results:
                        results.append(f"[记忆] {f['content']}")
                        f['access_count'] += 1
                        f['last_accessed'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        return "\n".join(results[:5]) if results else ""

    def retrieve_relevant(self, query):
        local = self.retrieve_local(query)
        if local:
            return local
        active = [f for i, f in enumerate(self.facts) if '[已过时]' not in f['content']]
        if not active:
            return ""
        indexed = "\n".join(f"#{i} [{f.get('importance','medium')}] {f['content']}" for i, f in enumerate(active))
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": "你是记忆检索器。根据用户当前问题，从记忆列表中找到最相关的条目。返回最相关的3条（编号），格式：相关:#编号,#编号,#编号。若都不相关返回：相关:无"},
                    {"role": "user", "content": f"问题：{query}\n\n记忆列表：\n{indexed}\n\n哪些记忆与问题最相关？"},
                ],
                temperature=0.3, max_tokens=100,
            )
            answer = sanitize_text(resp.choices[0].message.content)
        except Exception:
            return ""
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
        parts = []
        profile_text = self.get_profile_text()
        if profile_text:
            parts.append(profile_text)
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
        lines = []
        if self.profile:
            lines.append("═══ 用户档案 ═══")
            for k, v in self.profile.items():
                lines.append(f"  {k}: {v}")
            lines.append("")
        if self.facts:
            lines.append("═══ 长期记忆 ═══")
            for i, f in enumerate(self.facts):
                imp = f.get('importance', 'medium')
                icon = {'high': '⭐', 'medium': '  ', 'low': '  '}.get(imp, '  ')
                stale = ' [已过时]' if '[已过时]' in f['content'] else ''
                lines.append(f"{i+1}. {icon}{f['content']}{stale}")
        return "\n".join(lines) if lines else "暂无记忆或档案"
