# J.A.R.V.I.S.

> **J**ust **A** **R**ather **V**ery **I**ntelligent **S**ystem

一个运行在 Windows 上的个人 AI 助手，支持语音/文字双模式交互，具备电脑操控、长期记忆、情绪感知和多 Agent 协作能力。

---

## ✨ 功能特性

### 核心能力
- 🎤 **语音 + 文字双模式**：语音唤醒词 "贾维斯" / "Hey Jarvis"，也支持纯文字输入
- 🧠 **Agent Brain 决策层**：每次输入先经过元认知分析，自动选择最优执行策略
- 💾 **长期记忆系统**：自动从对话中提取关键信息并持久化，下次对话时语义检索相关记忆
- 😊 **情绪感知**：检测用户情绪状态，适时给予关心，保持自然的人格化交互
- 📅 **任务调度**：支持定时提醒和自主主动问候

### 电脑操控
- 🖥️ 打开程序、搜索网页、系统控制
- 📸 截屏、鼠标控制、键盘输入
- 🔗 多工具链式协作，复杂任务自动拆解执行

### 多 Agent 协作
| Agent | 职责 |
|-------|------|
| Researcher | 信息查询与检索 |
| Executor | 执行具体操作 |
| Planner | 制定多步计划 |
| Reflector | 回顾分析已完成任务 |

---

## 🛠️ 技术栈

| 模块 | 技术 |
|------|------|
| AI 推理 | DeepSeek API（deepseek-v4-pro） |
| 语音识别 | `speech_recognition` |
| 语音合成 | `pyttsx3`（中文语音） |
| 电脑操控 | `pyautogui` |
| 记忆存储 | 本地 JSON 文件 |

---

## 📁 项目结构

```
jarvis/
├── jarvis.py              # 外部快捷入口
├── jarvis/
│   ├── jarvis_main.py     # 主入口，组装所有模块
│   ├── jarvis_config.py   # 全局配置、API 客户端、常量
│   ├── jarvis_core.py     # 对话循环、语音处理、指令路由
│   ├── jarvis_tools.py    # 工具注册表、多 Agent、自主执行引擎
│   ├── jarvis_brain.py    # Agent Brain 元认知决策层
│   ├── jarvis_memory.py   # 长期记忆管理与语义检索
│   ├── jarvis_emotion.py  # 情绪系统
│   ├── jarvis_scheduler.py # 任务调度与自主交互
│   └── jarvis_personality.txt  # 人格设定
```

---

## 🚀 快速开始

### 环境要求
- Windows 10/11
- Python 3.11+
- Clash Verge（代理工具，端口 7897）

### 安装依赖

```bash
pip install openai httpx speechrecognition pyttsx3 pyautogui pywin32
```

### 配置 API Key

编辑 `jarvis/jarvis_config.py`，替换 DeepSeek API Key：

```python
api_key="sk-your-deepseek-api-key"
```

### 运行

```bash
# 语音模式（默认）
python jarvis/jarvis_main.py

# 文字模式
python jarvis/jarvis_main.py --text
```

### 唤醒

- 语音模式：说 **"贾维斯"** 或 **"Hey Jarvis"**
- 文字模式：直接输入对话，无需唤醒词
- 退出：说/输入 "退出"、"再见"

---

## 📋 本地指令速查

| 指令 | 功能 |
|------|------|
| 打开 XXX | 打开程序 |
| 搜索 XXX | 浏览器搜索 |
| 截图 | 屏幕截图 |
| 几点 / 时间 / 日期 | 时间查询 |
| 音量 +/- / 静音 | 音量控制 |
| 锁屏 | 锁定屏幕 |
| 记事本 / 计算器 | 系统工具 |
| 记住 XXX | 手动保存记忆 |
| 忘记 XXX | 删除记忆 |
| 指令列表 | 查看所有指令 |

---

## ⚠️ 注意事项

- 需要 Clash Verge 代理运行在 `127.0.0.1:7897`，离线时自动切换直连
- API Key 已硬编码在配置文件中，注意不要将泄露版上传到公开仓库
- `pyautogui` 的 `FAILSAFE` 已开启，鼠标移到屏幕左上角可紧急停止
- 默认使用联想 SLBrowser 浏览器，可在 `jarvis_config.py` 中修改

---

## 📝 License

MIT
