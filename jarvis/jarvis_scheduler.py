# -*- coding: utf-8 -*-
"""Jarvis 任务调度器 — TaskManager"""
import time
from datetime import datetime


class TaskManager:
    def __init__(self):
        self.tasks = []
        self.last_interaction = time.time()
        self._last_autocheck = 0

    def add_reminder(self, message, time_str):
        tid = str(int(time.time() * 1000))[-6:]
        self.tasks.append({"type": "reminder", "message": message, "time": time_str,
                           "id": tid, "created": datetime.now().strftime('%m-%d %H:%M')})
        return tid

    def add_timer(self, message, seconds):
        tid = str(int(time.time() * 1000))[-6:]
        self.tasks.append({"type": "timer", "message": message, "fire_at": time.time() + seconds,
                           "id": tid, "created": datetime.now().strftime('%m-%d %H:%M')})
        return tid

    def add_periodic(self, message, interval_minutes):
        tid = str(int(time.time() * 1000))[-6:]
        self.tasks.append({"type": "periodic", "message": message,
                           "interval": interval_minutes * 60, "last_fired": 0,
                           "id": tid, "created": datetime.now().strftime('%m-%d %H:%M')})
        return tid

    def check(self):
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
        idle = time.time() - self.last_interaction
        since_last = time.time() - self._last_autocheck
        hour = datetime.now().hour
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
        return {"tasks": self.tasks, "last_interaction": self.last_interaction,
                "last_autocheck": self._last_autocheck}

    @classmethod
    def from_dict(cls, d):
        tm = cls()
        if d:
            tm.tasks = d.get("tasks", [])
            tm.last_interaction = d.get("last_interaction", time.time())
            tm._last_autocheck = d.get("last_autocheck", 0)
        return tm
