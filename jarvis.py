import speech_recognition as sr
import pyttsx3
from openai import OpenAI
import sys
import time

# DeepSeek API
client = OpenAI(
    api_key="sk-placeholder",
    base_url="https://api.deepseek.com"
)

# TTS 引擎
engine = pyttsx3.init()
engine.setProperty('rate', 180)
engine.setProperty('volume', 1.0)

# 尝试找中文语音
voices = engine.getProperty('voices')
for voice in voices:
    if 'chinese' in voice.name.lower() or 'zh' in voice.id.lower():
        engine.setProperty('voice', voice.id)
        break

# 语音识别
r = sr.Recognizer()
r.energy_threshold = 50
r.dynamic_energy_threshold = False
r.pause_threshold = 0.8

# 使用本地 Whisper 模型（离线，无需联网，支持中文）
# 首次运行会自动下载 small 模型(~1GB)，之后离线使用
WHISPER_MODEL = "small"

# 对话历史
messages = [
    {
        "role": "system",
        "content": (
            "你是贾维斯(Jarvis)，钢铁侠的AI管家。"
            "你聪明、幽默、忠诚、高效。"
            "用中文回复，语气像一位可靠的管家兼朋友。"
            "回答简洁但不失个性，偶尔可以调侃一下。"
            "称呼用户为'先生'。"
        )
    }
]

MAX_HISTORY = 20  # 保留最近20轮对话


def speak(text):
    print(f"贾维斯: {text}")
    engine.say(text)
    engine.runAndWait()


_ambient_adjusted = False

def listen():
    global _ambient_adjusted
    with sr.Microphone(device_index=8) as source:
        # 只在第一次运行时校准环境噪音
        if not _ambient_adjusted:
            print("[校准环境噪音...]")
            r.adjust_for_ambient_noise(source, duration=1.0)
            _ambient_adjusted = True
            print(f"[就绪，能量阈值={r.energy_threshold:.0f}]")

        print("\n[聆听中...]")
        try:
            audio = r.listen(source, timeout=5, phrase_time_limit=15)
            print("[Whisper 识别中...]")
            text = r.recognize_whisper(
                audio,
                model=WHISPER_MODEL,
                language="zh",
                show_dict=False
            )
            text = text.strip()
            print(f"你: {text}")
            return text
        except sr.WaitTimeoutError:
            print("[未检测到语音, 重试...]")
            return None
        except sr.UnknownValueError:
            print("[未能识别语音内容，请重试]")
            return None
        except Exception as e:
            print(f"[识别错误: {e}]")
            return None


def chat(user_input):
    messages.append({"role": "user", "content": user_input})

    # 保持对话历史在合理范围
    if len(messages) > MAX_HISTORY + 1:
        del messages[1:3]

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.8,
            max_tokens=1000
        )
        reply = response.choices[0].message.content
        messages.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"抱歉先生，系统出现了一些问题: {e}"


def main():
    print("=" * 50)
    print("  J.A.R.V.I.S.")
    print("  Just A Rather Very Intelligent System")
    print("=" * 50)
    print("  说 '退出' 或 '再见' 结束对话")
    print("=" * 50)

    speak("贾维斯系统已就绪，有什么可以帮您的，先生？")

    while True:
        user_input = listen()
        if user_input is None:
            time.sleep(0.5)  # 避免刷新过快
            continue

        if any(w in user_input for w in ["退出", "再见", "关闭", "拜拜"]):
            speak("再见，先生。随时为您效劳。")
            break

        reply = chat(user_input)
        speak(reply)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[贾维斯已关闭]")
        sys.exit(0)
