import json
import logging
from typing import Dict, List, Generator, Optional
from django.conf import settings
from django.core.cache import cache
from openai import OpenAI
import re

logger = logging.getLogger(__name__)


class DeepSeekService:
    """DeepSeek API服务封装类"""

    def __init__(self):
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()
        self.default_model = self._get_default_model()
        self.client = None
        self._init_client()

    def _get_api_key(self):
        """获取API密钥"""
        # 先从缓存获取
        api_key = cache.get('deepseek_api_key')
        if api_key:
            return api_key

        # 从数据库获取
        from .models import SystemConfig
        api_key = SystemConfig.get_config(
            'deepseek_api_key',
            getattr(settings, 'DEEPSEEK_API_KEY', '')
        )

        # 缓存5分钟
        if api_key:
            cache.set('deepseek_api_key', api_key, 300)
        return api_key

    def _get_base_url(self):
        """获取API基础URL"""
        # 先从缓存获取
        base_url = cache.get('deepseek_base_url')
        if base_url:
            return base_url

        # 从数据库获取
        from .models import SystemConfig
        base_url = SystemConfig.get_config(
            'deepseek_base_url',
            getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
        )

        # 缓存5分钟
        cache.set('deepseek_base_url', base_url, 300)
        return base_url

    def _get_default_model(self):
        """获取默认模型"""
        # 先从缓存获取
        model = cache.get('deepseek_default_model')
        if model:
            return model

        # 从数据库获取
        from .models import SystemConfig
        model = SystemConfig.get_config(
            'deepseek_default_model',
            getattr(settings, 'DEEPSEEK_DEFAULT_MODEL', 'deepseek-chat')
        )

        # 缓存5分钟
        cache.set('deepseek_default_model', model, 300)
        return model

    def _init_client(self):
        """初始化OpenAI客户端"""
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        else:
            logger.warning("DeepSeek API密钥未配置")

    def _clean_deepseek_response(self, content: str) -> str:
        """清理DeepSeek R1模型的特殊输出格式"""
        # 移除<think>标签及其内容
        cleaned = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL)
        return cleaned.strip()

    def update_config(self, api_key=None, base_url=None, default_model=None):
        """更新配置并清除缓存"""
        from .models import SystemConfig

        if api_key:
            SystemConfig.set_config('deepseek_api_key', api_key, 'DeepSeek API密钥')
            cache.delete('deepseek_api_key')
            self.api_key = api_key

        if base_url:
            SystemConfig.set_config('deepseek_base_url', base_url, 'DeepSeek API地址')
            cache.delete('deepseek_base_url')
            self.base_url = base_url

        if default_model:
            SystemConfig.set_config('deepseek_default_model', default_model, 'DeepSeek默认模型')
            cache.delete('deepseek_default_model')
            self.default_model = default_model

        # 重新初始化客户端
        self._init_client()

    def chat(self, messages: List[Dict], model: Optional[str] = None, stream: bool = False) -> Dict:
        """
        聊天接口

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            model: 使用的模型名称
            stream: 是否使用流式响应

        Returns:
            如果stream=False，返回完整响应字典
            如果stream=True，返回生成器
        """
        if not self.client:
            raise Exception("DeepSeek API未配置，请先设置API密钥")

        try:
            model_name = model or self.default_model
            logger.info(f"Calling DeepSeek API with model: {model_name}")
            logger.info(f"Messages: {json.dumps(messages, ensure_ascii=False)}")

            response = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                stream=stream
            )

            if stream:
                return self._handle_stream(response)
            else:
                # 非流式响应
                content = response.choices[0].message.content

                # 清理DeepSeek R1模型的特殊格式
                if '<think>' in content:
                    logger.info("Detected DeepSeek R1 format, cleaning response")
                    content = self._clean_deepseek_response(content)

                result = {
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    } if response.usage else None
                }

                logger.info(f"DeepSeek response received, content length: {len(content)}")
                return result

        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {str(e)}")
            raise Exception(f"DeepSeek API调用失败: {str(e)}")

    def _handle_stream(self, response) -> Generator:
        """处理流式响应"""
        try:
            thinking_mode = False
            accumulated_content = ""

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    accumulated_content += content

                    # 检测思考模式的开始和结束
                    if '<think>' in accumulated_content and not thinking_mode:
                        thinking_mode = True
                        # 输出<think>之前的内容
                        pre_think = accumulated_content.split('<think>')[0]
                        if pre_think:
                            yield {
                                "message": {"content": pre_think},
                                "done": False
                            }
                        accumulated_content = ""
                        continue

                    if '</think>' in accumulated_content and thinking_mode:
                        thinking_mode = False
                        # 清理accumulated_content，只保留</think>之后的内容
                        post_think = accumulated_content.split('</think>')[-1]
                        accumulated_content = post_think
                        if accumulated_content:
                            yield {
                                "message": {"content": accumulated_content},
                                "done": False
                            }
                            accumulated_content = ""
                        continue

                    # 如果不在思考模式，正常输出
                    if not thinking_mode and content:
                        yield {
                            "message": {"content": content},
                            "done": False
                        }

                # 检查是否结束
                if chunk.choices and chunk.choices[0].finish_reason:
                    yield {
                        "done": True,
                        "model": chunk.model
                    }

        except Exception as e:
            logger.error(f"处理流式响应时出错: {str(e)}")
            yield {"error": str(e), "done": True}

    def list_models(self) -> List[Dict]:
        """获取可用模型列表"""
        # DeepSeek的模型是固定的，不需要动态获取
        models = [
            {
                "name": "deepseek-chat",
                "description": "DeepSeek Chat模型",
                "context_length": 128000
            },
            {
                "name": "deepseek-reasoner",
                "description": "DeepSeek R1推理模型（支持思维链）",
                "context_length": 128000
            },
            {
                "name": "deepseek-coder",
                "description": "DeepSeek Coder编程模型",
                "context_length": 128000
            }
        ]

        logger.info(f"Available DeepSeek models: {len(models)}")
        return models

    def check_health(self) -> bool:
        """检查API服务状态"""
        if not self.client:
            logger.error("DeepSeek API客户端未初始化")
            return False

        try:
            # 发送一个简单的测试请求
            response = self.client.chat.completions.create(
                model=self.default_model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1
            )
            logger.info("DeepSeek API health check: healthy")
            return True
        except Exception as e:
            logger.error(f"DeepSeek API健康检查失败: {str(e)}")
            return False

    def estimate_tokens(self, text: str) -> int:
        """估算文本的token数量"""
        # 简单估算：中文约1.5字符/token，英文约4字符/token
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)