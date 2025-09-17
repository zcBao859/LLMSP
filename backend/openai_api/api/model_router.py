# backend/openai_api/api/model_router.py
"""模型路由器 - 根据模型名称路由到不同的适配器（修复版）"""
import logging
from typing import Dict, Any, Optional, List, AsyncIterator
from django.conf import settings

from .adapters.base_adapter import BaseAdapter, OpenAIStreamChunk
from .adapters.huanxin_adapter import HuanxinAdapter
from .adapters.doubao_adapter import DoubaoAdapter
from .adapters.modelscope_adapter import ModelScopeAdapter
from .adapters.doubao_web_adapter import DoubaoWebAdapter
from .adapters.yuanbao_web_adapter import YuanBaoWebAdapter
from .adapters.jiutian_web_adapter import JiutianWebAdapter
from .adapters.o43_web_adapter import O43WebAdapter
from .adapters.ollama_adapter import OllamaAdapter
logger = logging.getLogger(__name__)


class ModelRouter:
    """模型路由器"""

    def __init__(self):
        self._adapters: Dict[str, BaseAdapter] = {}
        self._adapter_prefixes = {}  # 模型前缀到适配器的映射
        self._initialize_adapters()

    def _initialize_adapters(self):
        """初始化所有适配器"""

        # 获取模型配置
        model_configs = getattr(settings, 'MODEL_CONFIGS', {})
        # O4.3 Web适配器
        if "o43_web" in model_configs:
            config = model_configs["o43_web"]
            self._adapters["o43_web"] = O43WebAdapter(config)
            self._adapter_prefixes["o43"] = "o43_web"
            self._adapter_prefixes["o43-web"] = "o43_web"
            self._adapter_prefixes["o43_web"] = "o43_web"
            self._adapter_prefixes["gpt-4o"] = "o43_web"  # 支持 gpt-4o 别名
            logger.info("初始化 O4.3 (GPT-4o) Web 适配器")
        # 环信适配器（支持多个模型）
        if "huanxin" in model_configs:
            config = model_configs["huanxin"]
            if any(model_cfg.get("api_key") for model_cfg in config.get("models", {}).values()):
                self._adapters["huanxin"] = HuanxinAdapter(config)
                self._adapter_prefixes["huanxin"] = "huanxin"
                logger.info(f"初始化环信适配器，支持 {len(config.get('models', {}))} 个模型")
        if "ollama" in model_configs:
            config = model_configs["ollama"]
            try:
                self._adapters["ollama"] = OllamaAdapter(config)
                self._adapter_prefixes["ollama"] = "ollama"
                logger.info("初始化 Ollama 适配器，支持动态加载任意模型")
            except Exception as e:
                logger.warning(f"初始化 Ollama 适配器失败，将跳过 Ollama 支持: {e}")
                # 不要抛出异常，继续初始化其他适配器
        # 豆包Web适配器 - 必须在豆包API之前注册，因为前缀更具体
        if "doubao_web" in model_configs:
            config = model_configs["doubao_web"]
            self._adapters["doubao_web"] = DoubaoWebAdapter(config)
            # 注册多个可能的前缀
            self._adapter_prefixes["doubao-web"] = "doubao_web"
            self._adapter_prefixes["doubao_web"] = "doubao_web"
            logger.info("初始化豆包 Web 适配器")

        # 豆包API适配器 - 在Web适配器之后注册
        if "doubao_api" in model_configs:
            config = model_configs["doubao_api"]
            if config.get("api_key"):
                self._adapters["doubao_api"] = DoubaoAdapter(config)
                # 只匹配特定的模型名称，不使用通用前缀
                self._adapter_prefixes["doubao-seed"] = "doubao_api"  # 更具体的前缀
                self._adapter_prefixes["doubao-pro"] = "doubao_api"  # 如果有其他模型
                logger.info("初始化豆包 API 适配器")

        # 元宝Web适配器
        if "yuanbao_web" in model_configs:
            config = model_configs["yuanbao_web"]
            self._adapters["yuanbao_web"] = YuanBaoWebAdapter(config)
            self._adapter_prefixes["yuanbao"] = "yuanbao_web"
            self._adapter_prefixes["yuanbao-web"] = "yuanbao_web"
            self._adapter_prefixes["yuanbao_web"] = "yuanbao_web"
            logger.info("初始化元宝 Web 适配器")

        # 九天Web适配器
        if "jiutian_web" in model_configs:
            config = model_configs["jiutian_web"]
            self._adapters["jiutian_web"] = JiutianWebAdapter(config)
            self._adapter_prefixes["jiutian"] = "jiutian_web"
            self._adapter_prefixes["jiutian-web"] = "jiutian_web"
            self._adapter_prefixes["jiutian_web"] = "jiutian_web"
            logger.info("初始化九天 Web 适配器")

        # 魔搭适配器
        if "modelscope" in model_configs:
            config = model_configs["modelscope"]
            if config.get("api_key"):
                self._adapters["modelscope"] = ModelScopeAdapter(config)
                self._adapter_prefixes["modelscope"] = "modelscope"
                logger.info("初始化魔搭适配器")

        logger.info(f"总共初始化了 {len(self._adapters)} 个模型适配器")
        logger.info(f"注册的模型前缀: {list(self._adapter_prefixes.keys())}")

    def get_adapter(self, model_name: str) -> Optional[BaseAdapter]:
        """根据模型名获取适配器 - 优先匹配最长的前缀"""
        logger.info(f"查找模型 {model_name} 的适配器")

        # 首先尝试精确匹配
        model_lower = model_name.lower()

        # 按前缀长度降序排序，优先匹配更具体的前缀
        sorted_prefixes = sorted(self._adapter_prefixes.items(),
                                 key=lambda x: len(x[0]),
                                 reverse=True)

        for prefix, adapter_name in sorted_prefixes:
            if model_lower.startswith(prefix.lower()):
                adapter = self._adapters.get(adapter_name)
                if adapter:
                    logger.info(f"模型 {model_name} 匹配前缀 '{prefix}'，使用 {adapter_name} 适配器")
                    return adapter
                else:
                    logger.error(f"适配器 {adapter_name} 未初始化")
                    return None

        # 检查模型别名
        model_aliases = getattr(settings, 'MODEL_ROUTER_CONFIG', {}).get('model_aliases', {})
        if model_lower in model_aliases:
            aliased_model = model_aliases[model_lower]
            logger.info(f"模型 {model_name} 是 {aliased_model} 的别名")
            return self.get_adapter(aliased_model)

        logger.warning(f"未找到模型 {model_name} 的适配器")
        logger.debug(f"可用的适配器: {list(self._adapters.keys())}")
        logger.debug(f"可用的前缀: {list(self._adapter_prefixes.keys())}")
        return None

    def list_models(self) -> List[Dict[str, Any]]:
        """列出所有可用模型"""
        models = []
        # Ollama 模型 - 优雅处理
        if "ollama" in self._adapters:
            try:
                ollama_adapter = self._adapters["ollama"]

                # 使用异步方式获取模型列表，设置短超时
                import asyncio

                # 获取当前事件循环或创建新的
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        raise RuntimeError("Event loop is closed")
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    should_close_loop = True
                else:
                    should_close_loop = False

                try:
                    # 使用 wait_for 设置超时，避免长时间阻塞
                    future = asyncio.ensure_future(ollama_adapter.list_models(), loop=loop)

                    if loop.is_running():
                        # 如果循环已经在运行（例如在异步上下文中），使用 create_task
                        available_models = loop.run_until_complete(
                            asyncio.wait_for(future, timeout=1.0)
                        )
                    else:
                        # 否则直接运行
                        available_models = loop.run_until_complete(
                            asyncio.wait_for(future, timeout=1.0)
                        )

                    if available_models:
                        models.extend(available_models)
                        logger.debug(f"添加了 {len(available_models)} 个 Ollama 模型")

                except asyncio.TimeoutError:
                    logger.debug("获取 Ollama 模型列表超时，跳过")
                except Exception as e:
                    logger.debug(f"获取 Ollama 模型列表失败: {type(e).__name__}: {str(e)}")
                finally:
                    if should_close_loop:
                        loop.close()

            except Exception as e:
                logger.debug(f"处理 Ollama 模型时出错: {e}")
        # 环信模型
        if "huanxin" in self._adapters:
            huanxin_adapter = self._adapters["huanxin"]
            for model_name in huanxin_adapter.models_config.keys():
                models.append({
                    "id": model_name,
                    "object": "model",
                    "owned_by": "huanxin",
                    "created": 1700000000
                })
        # O4.3 Web模型
        if "o43_web" in self._adapters:
            models.append({
                "id": "o43-web",
                "object": "model",
                "owned_by": "openai-via-web",
                "created": 1700000000,
                "description": "GPT-4o Web版本（通过浏览器自动化访问）"
            })
        # 豆包API模型
        if "doubao_api" in self._adapters:
            models.append({
                "id": "doubao-seed-1-6-250615",
                "object": "model",
                "owned_by": "doubao",
                "created": 1700000000
            })
            models.append({
                "id": "doubao-seed-1-6-250615",
                "object": "model",
                "owned_by": "doubao",
                "created": 1700000000
            })

        # 豆包Web模型
        if "doubao_web" in self._adapters:
            models.append({
                "id": "doubao-web",
                "object": "model",
                "owned_by": "doubao-web",
                "created": 1700000000,
                "description": "豆包Web版本（通过浏览器自动化访问）"
            })

        # 元宝Web模型
        if "yuanbao_web" in self._adapters:
            models.append({
                "id": "yuanbao-web",
                "object": "model",
                "owned_by": "tencent-yuanbao",
                "created": 1700000000,
                "description": "腾讯元宝Web版本（通过浏览器自动化访问）"
            })

        # 九天Web模型
        if "jiutian_web" in self._adapters:
            models.append({
                "id": "jiutian-web",
                "object": "model",
                "owned_by": "china-mobile-jiutian",
                "created": 1700000000,
                "description": "中国移动九天Web版本（通过浏览器自动化访问）"
            })

        # 魔搭模型
        if "modelscope" in self._adapters:
            models.append({
                "id": "modelscope-deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
                "object": "model",
                "owned_by": "modelscope",
                "created": 1700000000,
                "description": "支持任意魔搭模型，使用格式: modelscope-<实际模型ID>"
            })
            models.append({
                "id": "modelscope-Qwen/Qwen3-32B",
                "object": "model",
                "owned_by": "modelscope",
                "created": 1700000000,
                "description": "支持任意魔搭模型，使用格式: modelscope-<实际模型ID>"
            })


        return models

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """获取模型信息"""
        adapter = self.get_adapter(model_name)
        if adapter:
            return {
                "id": model_name,
                "object": "model",
                "created": 1700000000,
                "owned_by": "custom",
                "permission": [],
                "root": model_name,
                "parent": None
            }
        return None

    async def create_chat_completion(
            self,
            messages: List[Dict[str, str]],
            model: str,
            stream: bool = False,
            **kwargs
    ):
        """创建聊天补全 - 统一入口"""
        adapter = self.get_adapter(model)
        if not adapter:
            raise ValueError(f"No adapter found for model {model}")

        logger.info(f"使用模型: {model}, 适配器: {type(adapter).__name__}")

        if stream:
            return adapter.create_completion_stream(messages, model, **kwargs)
        else:
            return await adapter.create_completion(messages, model, stream=False, **kwargs)

    async def cleanup(self):
        """清理资源 - 特别是Web适配器的浏览器实例"""
        from .adapters.web_adapter_base import cleanup_browsers

        logger.info("清理模型路由器资源...")

        # 清理Web浏览器实例
        try:
            await cleanup_browsers()
            logger.info("已清理所有浏览器实例")
        except Exception as e:
            logger.error(f"清理浏览器实例失败: {str(e)}")


# 全局路由器实例
model_router = ModelRouter()