# -*- coding: utf-8 -*-
"""Jarvis 单元测试"""
import os
import sys
import unittest

# 添加父目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "jarvis"))


class TestMemory(unittest.TestCase):
    """记忆系统测试"""

    def setUp(self):
        from jarvis_memory import JarvisMemory
        self.memory = JarvisMemory(":memory:")  # 不持久化
        self.memory.filepath = os.path.join(os.path.dirname(__file__), "_test_memory.json")

    def tearDown(self):
        if os.path.exists(self.memory.filepath):
            os.remove(self.memory.filepath)

    def test_add_and_search(self):
        self.memory.add_fact("用户叫张三", "high")
        self.memory.add_fact("用户喜欢Python", "medium")
        results = self.memory.search_facts("Python")
        self.assertEqual(len(results), 1)
        self.assertIn("Python", results[0][1]["content"])

    def test_profile(self):
        self.memory.set_profile("名字", "张三")
        self.memory.set_profile("爱好", "编程")
        self.assertEqual(self.memory.profile["名字"], "张三")
        text = self.memory.get_profile_text()
        self.assertIn("名字", text)
        self.assertIn("爱好", text)

    def test_contradiction(self):
        self.memory.add_fact("住在北京", "medium")
        conflict = self.memory.add_fact("不是住在北京了，现在已经搬到上海了", "high")
        self.assertIn("过时", conflict)
        results = self.memory.search_facts("北京")
        self.assertIn("过时", results[0][1]["content"])

    def test_remove(self):
        self.memory.add_fact("测试数据", "low")
        self.assertTrue(self.memory.remove_fact(0))
        self.assertEqual(len(self.memory.facts), 0)

    def test_importance_sorting(self):
        self.memory.add_fact("AAA低优先", "medium")
        self.memory.add_fact("ZZZ高优先", "high")
        self.memory.add_fact("MMM中优先", "medium")
        ctx = self.memory.get_facts_context()
        self.assertIn("高优先", ctx)
        self.assertIn("低优先", ctx)


class TestEmotion(unittest.TestCase):
    """情绪系统测试"""

    def test_mood_mapping(self):
        from jarvis_emotion import EmotionSystem
        e = EmotionSystem()
        e.valence, e.energy = 0.5, 0.5
        self.assertIn("轻松愉快", e.mood)
        e.valence, e.energy = -0.5, -0.5
        self.assertIn("低落", e.mood)

    def test_emotion_triggers(self):
        from jarvis_emotion import analyze_emotion_triggers
        v, e = analyze_emotion_triggers("今天太开心了哈哈")
        self.assertGreater(v, 0)

    def test_decay(self):
        from jarvis_emotion import EmotionSystem
        e = EmotionSystem()
        e.valence, e.energy = 0.8, 0.8
        e.decay()
        self.assertLess(e.valence, 0.8)
        self.assertLess(e.energy, 0.8)


class TestScheduler(unittest.TestCase):
    """任务调度测试"""

    def test_add_reminder(self):
        from jarvis_scheduler import TaskManager
        s = TaskManager()
        tid = s.add_reminder("测试提醒", "23:59")
        self.assertIsNotNone(tid)
        self.assertEqual(len(s.get_pending()), 1)

    def test_add_timer(self):
        from jarvis_scheduler import TaskManager
        s = TaskManager()
        tid = s.add_timer("测试倒计时", 60)
        tasks = s.get_pending()
        self.assertEqual(tasks[0]["type"], "timer")

    def test_cancel(self):
        from jarvis_scheduler import TaskManager
        s = TaskManager()
        tid = s.add_reminder("将被取消", "12:00")
        msg = s.cancel(tid)
        self.assertIn("将被取消", msg)
        self.assertEqual(len(s.get_pending()), 0)


class TestLogger(unittest.TestCase):
    """日志系统测试"""

    def test_get_logger(self):
        from jarvis_logger import get_logger
        log = get_logger("test")
        self.assertIsNotNone(log)
        log.info("测试日志输出")


if __name__ == "__main__":
    unittest.main(verbosity=2)
