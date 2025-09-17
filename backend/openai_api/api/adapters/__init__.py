# backend/openai_api/api/adapters/__init__.py
"""
AI模型适配器包
"""

from .base_adapter import BaseAdapter, OpenAIResponse, OpenAIChoice, OpenAIMessage, OpenAIUsage, OpenAIStreamChunk
from .huanxin_adapter import HuanxinAdapter
from .doubao_adapter import DoubaoAdapter
from .modelscope_adapter import ModelScopeAdapter
from .web_adapter_base import WebAdapterBase
from .doubao_web_adapter import DoubaoWebAdapter
from .yuanbao_web_adapter import YuanBaoWebAdapter
from .jiutian_web_adapter import JiutianWebAdapter
from .o43_web_adapter import O43WebAdapter
from .ollama_adapter import OllamaAdapter
__all__ = [
    'BaseAdapter',
    'OpenAIResponse',
    'OpenAIChoice',
    'OpenAIMessage',
    'OpenAIUsage',
    'OpenAIStreamChunk',
    'HuanxinAdapter',
    'DoubaoAdapter',
    'ModelScopeAdapter',
    'WebAdapterBase',
    'DoubaoWebAdapter',
    'YuanBaoWebAdapter',
    'JiutianWebAdapter',
    'O43WebAdapter',
    "OllamaAdapter"
]