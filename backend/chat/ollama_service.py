import requests
import json
import re
from typing import Dict, List, Generator, Optional
from django.conf import settings
import logging
from django.core.cache import cache
logger = logging.getLogger(__name__)


class OllamaService:
    """Ollama服务封装类"""

    def __init__(self):
        self.base_url = self._get_ollama_url()
        self.default_model = self._get_default_model()
        self.timeout = 300  # 5分钟超时

    def _get_default_model(self):
        """获取默认模型"""
        # 先从缓存获取
        model = cache.get('ollama_default_model')
        if model:
            return model

        # 从数据库获取
        from .models import SystemConfig
        model = SystemConfig.get_config(
            'ollama_default_model',
            getattr(settings, 'OLLAMA_DEFAULT_MODEL', 'llama2')
        )

        # 缓存5分钟
        cache.set('ollama_default_model', model, 300)
        return model
    def _get_ollama_url(self):
        """获取Ollama服务地址"""
        # 先从缓存获取
        url = cache.get('ollama_base_url')
        if url:
            return url

        # 从数据库获取
        from .models import SystemConfig
        url = SystemConfig.get_config(
            'ollama_base_url',
            getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        )

        # 缓存5分钟
        cache.set('ollama_base_url', url, 300)
        return url
    def _clean_deepseek_response(self, content: str) -> str:
        """清理DeepSeek R1模型的特殊输出格式"""
        # 移除<think>标签及其内容
        cleaned = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL)
        return cleaned.strip()

    def update_config(self, base_url=None, default_model=None):
        """更新配置并清除缓存"""
        from .models import SystemConfig

        if base_url:
            SystemConfig.set_config('ollama_base_url', base_url, 'Ollama服务地址')
            cache.delete('ollama_base_url')
            self.base_url = base_url

        if default_model:
            SystemConfig.set_config('ollama_default_model', default_model, '默认模型')
            cache.delete('ollama_default_model')
            self.default_model = default_model
    def chat(self, messages: List[Dict], model: Optional[str] = None, stream: bool = False) -> Dict:
        """
        普通聊天接口

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            model: 使用的模型名称
            stream: 是否使用流式响应

        Returns:
            如果stream=False，返回完整响应字典
            如果stream=True，返回生成器
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": stream
        }

        try:
            logger.info(f"Calling Ollama API: {url}")
            logger.info(f"Payload: {json.dumps(payload, ensure_ascii=False)}")

            response = requests.post(
                url,
                json=payload,
                stream=stream,
                timeout=self.timeout
            )

            # 记录响应状态
            logger.info(f"Response status code: {response.status_code}")

            # 如果不是2xx响应，记录错误内容
            if not response.ok:
                error_content = response.text
                logger.error(f"Ollama API error response: {error_content}")
                raise Exception(f"Ollama API返回错误 (状态码: {response.status_code}): {error_content}")

            if stream:
                return self._handle_stream(response)
            else:
                # 检查响应内容
                content = response.text
                if not content:
                    logger.error("Ollama返回空响应")
                    raise Exception("Ollama返回空响应")

                try:
                    result = json.loads(content)
                    logger.info(
                        f"Ollama response received, content length: {len(result.get('message', {}).get('content', ''))}")

                    # 清理DeepSeek R1模型的特殊格式
                    if 'message' in result and 'content' in result['message']:
                        original_content = result['message']['content']
                        if '<think>' in original_content:
                            logger.info("Detected DeepSeek R1 format, cleaning response")
                            result['message']['content'] = self._clean_deepseek_response(original_content)

                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"无法解析Ollama响应: {content[:200]}")
                    raise Exception(f"Ollama返回的不是有效的JSON: {str(e)}")

        except requests.exceptions.ConnectionError:
            logger.error(f"无法连接到Ollama服务: {self.base_url}")
            raise Exception(f"无法连接到Ollama服务，请确保Ollama正在运行（{self.base_url}）")
        except requests.exceptions.Timeout:
            logger.error("Ollama服务响应超时")
            raise Exception("Ollama服务响应超时，请稍后再试")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama服务调用失败: {str(e)}")
            raise Exception(f"Ollama服务调用失败: {str(e)}")

    def _handle_stream(self, response) -> Generator:
        """处理流式响应"""
        try:
            thinking_mode = False
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)

                    # 处理DeepSeek R1的特殊格式
                    if 'message' in chunk and 'content' in chunk['message']:
                        content = chunk['message']['content']

                        # 检测思考模式的开始和结束
                        if '<think>' in content:
                            thinking_mode = True
                        if '</think>' in content:
                            thinking_mode = False
                            # 清理这个chunk的内容
                            chunk['message']['content'] = self._clean_deepseek_response(content)
                            if not chunk['message']['content']:
                                continue  # 跳过空内容
                        elif thinking_mode:
                            continue  # 跳过思考内容

                    yield chunk
        except Exception as e:
            logger.error(f"处理流式响应时出错: {str(e)}")
            yield {"error": str(e)}

    def generate(self, prompt: str, model: Optional[str] = None, stream: bool = False) -> Dict:
        """
        生成接口（用于单次生成，无上下文）

        Args:
            prompt: 提示词
            model: 使用的模型名称
            stream: 是否使用流式响应
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": stream
        }

        try:
            response = requests.post(url, json=payload, stream=stream, timeout=self.timeout)
            response.raise_for_status()

            if stream:
                return self._handle_stream(response)
            else:
                return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama generate调用失败: {str(e)}")
            raise Exception(f"Ollama服务调用失败: {str(e)}")

    def list_models(self) -> List[Dict]:
        """获取可用模型列表"""
        url = f"{self.base_url}/api/tags"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            models = data.get('models', [])
            logger.info(f"Found {len(models)} available models")
            return models
        except Exception as e:
            logger.error(f"获取模型列表失败: {str(e)}")
            return []

    def check_health(self) -> bool:
        """检查Ollama服务状态"""
        try:
            response = requests.get(self.base_url, timeout=5)
            is_healthy = response.status_code == 200
            logger.info(f"Ollama health check: {'healthy' if is_healthy else 'unhealthy'}")
            return is_healthy
        except Exception as e:
            logger.error(f"Ollama健康检查失败: {str(e)}")
            return False

    def pull_model(self, model_name: str) -> Generator:
        """
        拉取模型（下载模型）

        Args:
            model_name: 模型名称，如 "llama2", "mistral" 等

        Returns:
            生成器，包含下载进度信息
        """
        url = f"{self.base_url}/api/pull"
        payload = {
            "name": model_name,
            "stream": True
        }

        try:
            logger.info(f"Pulling model: {model_name}")
            response = requests.post(url, json=payload, stream=True, timeout=None)
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    yield json.loads(line)

        except Exception as e:
            logger.error(f"拉取模型失败: {str(e)}")
            yield {"error": str(e)}