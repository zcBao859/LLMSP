# backend/openai_api/utils.py
"""工具函数模块"""
import json
import time
import uuid
import logging
from typing import Iterator, Dict, Any, Optional

logger = logging.getLogger(__name__)


def generate_completion_id() -> str:
    """生成聊天补全ID"""
    return f"chatcmpl-{uuid.uuid4().hex[:8]}"


def get_current_timestamp() -> int:
    """获取当前时间戳"""
    return int(time.time())


def calculate_tokens(text: str) -> int:
    """估算token数量"""
    # 简单估算：中文约2字符/token，英文约4字符/token
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return max(1, int(chinese_chars / 2 + (len(text) - chinese_chars) / 4))


def stream_generator(chunks: Iterator[Dict[str, Any]]) -> Iterator[bytes]:
    """将chunks转换为SSE格式"""
    try:
        for chunk in chunks:
            data = json.dumps(chunk, ensure_ascii=False)
            yield f"data: {data}\n\n".encode('utf-8')
    except Exception as e:
        logger.error(f"流生成器错误: {e}")
        error_data = {"error": {"message": str(e), "type": "stream_error"}}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n".encode('utf-8')
    finally:
        yield b"data: [DONE]\n\n"


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本并添加省略号"""
    return text if len(text) <= max_length else f"{text[:max_length]}..."


def safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    """安全解析JSON"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"JSON解析失败: {truncate_text(text)}")
        return None