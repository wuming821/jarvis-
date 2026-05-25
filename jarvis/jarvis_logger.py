# -*- coding: utf-8 -*-
"""Jarvis 统一日志系统 + 重试机制"""
import logging
import os
import functools
import time
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_loggers = {}


def get_logger(name="jarvis"):
    """获取或创建模块级 logger"""
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加 handler
    if not logger.handlers:
        # 文件 handler — 所有级别
        log_file = os.path.join(LOG_DIR, f"{datetime.now().strftime('%Y%m%d')}.log")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        ))
        logger.addHandler(fh)

        # 控制台 handler — INFO 以上
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(ch)

    _loggers[name] = logger
    return logger


def retry_on_failure(max_retries=3, delay=1.0, backoff=2.0, exceptions=(Exception,)):
    """重试装饰器：API 调用失败时自动重试，支持指数退避"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger("retry")
            last_exc = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"{func.__name__} 第{attempt+1}次尝试成功")
                    return result
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} 第{attempt+1}次失败: {e}，"
                            f"{current_delay:.1f}s 后重试 ({attempt+1}/{max_retries})"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"{func.__name__} 已达最大重试次数({max_retries+1})，最终失败: {e}"
                        )
            raise last_exc
        return wrapper
    return decorator


def log_call(logger=None):
    """装饰器：记录函数调用和返回值"""
    if logger is None:
        logger = get_logger("call")
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            short_args = str(args)[:100] if args else ""
            logger.debug(f"→ {func.__name__}({short_args})")
            result = func(*args, **kwargs)
            short_result = str(result)[:100] if result else ""
            logger.debug(f"← {func.__name__} → {short_result}")
            return result
        return wrapper
    return decorator
