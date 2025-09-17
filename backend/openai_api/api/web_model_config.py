# backend/openai_api/api/web_model_config.py
"""
Web模型测试配置模块

本模块基于测试隔离理论(Test Isolation Theory)和浏览器自动化最佳实践，
封装了Web模型特有的测试参数和行为模式。
"""
from typing import Dict, Any, List, Optional
import logging
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class SessionIsolationMode(Enum):
    """会话隔离模式枚举"""
    STRICT = "strict"  # 严格隔离：每次测试强制新会话
    MODERATE = "moderate"  # 适度隔离：根据情况决定是否新建会话
    LOOSE = "loose"  # 宽松隔离：尽可能复用会话


@dataclass
class WebModelProfile:
    """Web模型配置文件"""
    platform_name: str
    new_chat_cooldown: int = 3
    inter_test_delay: int = 2
    validation_timeout: int = 10000
    max_retries: int = 3
    session_isolation_mode: SessionIsolationMode = SessionIsolationMode.STRICT
    clear_cookies_interval: int = 10
    browser_restart_interval: int = 50
    response_verification: bool = True
    screenshot_on_error: bool = False
    custom_settings: Dict[str, Any] = field(default_factory=dict)


class WebModelTestConfig:
    """
    Web模型测试配置类

    基于测试隔离理论(Test Isolation Theory)和浏览器自动化最佳实践，
    本配置类封装了Web模型特有的测试参数和行为模式。
    """

    # Web模型识别模式 - 基于命名约定的模式匹配
    WEB_MODEL_PATTERNS = [
        'web',  # 包含 'web' 的模型名
        '-web',  # 以 '-web' 结尾
        '_web',  # 以 '_web' 结尾
    ]

    # Web模型特定配置 - 基于经验参数的优化配置
    DEFAULT_WEB_MODEL_SETTINGS = {
        "force_new_chat": True,  # 强制每次新建对话
        "session_isolation_mode": "strict",  # 严格会话隔离
        "new_chat_cooldown": 3,  # 新建对话冷却时间（秒）
        "inter_test_delay": 2,  # 测试间隔时间（秒）
        "max_concurrent": 1,  # 最大并发数（建议为1）
        "retry_on_session_error": True,  # 会话错误时重试
        "clear_cookies_interval": 10,  # 每N次测试清理cookies
        "response_verification": True,  # 响应验证
        "screenshot_on_error": False,  # 错误时截图
        "browser_restart_interval": 50,  # 每N次测试重启浏览器
        "wait_for_stable_state": True,  # 等待页面稳定
        "verify_new_chat_success": True,  # 验证新会话创建成功
        "max_response_wait_time": 60,  # 最大响应等待时间（秒）
        "response_check_interval": 1,  # 响应检查间隔（秒）
        "enable_performance_metrics": True,  # 启用性能指标收集
    }

    # 平台特定的配置覆盖
    PLATFORM_PROFILES = {
        "doubao_web": WebModelProfile(
            platform_name="doubao_web",
            new_chat_cooldown=3,
            inter_test_delay=3,
            validation_timeout=10000,
            clear_cookies_interval=8,
            custom_settings={
                "wait_for_validation": True,
                "validation_selectors": ["text*='回在验证中'", "text*='正在验证'"],
                "max_validation_wait": 15000,
            }
        ),
        "yuanbao_web": WebModelProfile(
            platform_name="yuanbao_web",
            new_chat_cooldown=2,
            inter_test_delay=2,
            validation_timeout=8000,
            custom_settings={
                "login_check_interval": 300,  # 每5分钟检查一次登录状态
                "auto_refresh_session": True,
            }
        ),
        "jiutian_web": WebModelProfile(
            platform_name="jiutian_web",
            new_chat_cooldown=2,
            inter_test_delay=2,
            validation_timeout=8000,
            browser_restart_interval=30,  # 九天平台需要更频繁的重启
            custom_settings={
                "use_alternate_selectors": True,
                "response_format_check": True,
            }
        ),
        "o43_web": WebModelProfile(
            platform_name="o43_web",
            new_chat_cooldown=4,
            inter_test_delay=3,
            validation_timeout=12000,
            session_isolation_mode=SessionIsolationMode.STRICT,
            custom_settings={
                "handle_rate_limits": True,
                "rate_limit_cooldown": 5,
                "premium_features_check": True,
            }
        )
    }

    # 错误恢复策略配置
    ERROR_RECOVERY_STRATEGIES = {
        "session_error": {
            "max_retries": 3,
            "backoff_factor": 2,
            "recovery_actions": ["clear_cookies", "refresh_page", "restart_browser"],
        },
        "timeout_error": {
            "max_retries": 2,
            "backoff_factor": 1.5,
            "recovery_actions": ["wait_and_retry", "refresh_page"],
        },
        "validation_error": {
            "max_retries": 5,
            "backoff_factor": 1,
            "recovery_actions": ["wait_for_validation", "skip_validation"],
        }
    }

    @classmethod
    def is_web_model(cls, model_name: str) -> bool:
        """
        判断是否为Web模型

        基于命名约定的启发式判断算法，通过模式匹配识别Web模型。

        Args:
            model_name: 模型名称

        Returns:
            bool: 是否为Web模型
        """
        if not model_name:
            return False

        model_lower = model_name.lower()
        is_web = any(pattern in model_lower for pattern in cls.WEB_MODEL_PATTERNS)

        if is_web:
            logger.debug(f"模型 '{model_name}' 被识别为Web模型")

        return is_web

    @classmethod
    def get_web_model_config(cls, model_name: str) -> Dict[str, Any]:
        """
        获取Web模型的特定配置

        实施配置继承策略：基础配置 -> 平台特定配置 -> 运行时覆盖

        Args:
            model_name: 模型名称

        Returns:
            Dict[str, Any]: 模型配置字典
        """
        if not cls.is_web_model(model_name):
            return {}

        # 基础配置
        config = cls.DEFAULT_WEB_MODEL_SETTINGS.copy()

        # 应用平台特定配置
        model_lower = model_name.lower()
        for platform_key, profile in cls.PLATFORM_PROFILES.items():
            if platform_key in model_lower:
                # 从profile对象提取配置
                config.update({
                    "new_chat_cooldown": profile.new_chat_cooldown,
                    "inter_test_delay": profile.inter_test_delay,
                    "validation_timeout": profile.validation_timeout,
                    "max_retries": profile.max_retries,
                    "session_isolation_mode": profile.session_isolation_mode.value,
                    "clear_cookies_interval": profile.clear_cookies_interval,
                    "browser_restart_interval": profile.browser_restart_interval,
                    "response_verification": profile.response_verification,
                    "screenshot_on_error": profile.screenshot_on_error,
                })

                # 合并自定义设置
                if profile.custom_settings:
                    config.update(profile.custom_settings)

                logger.debug(f"应用 {platform_key} 的特定配置")
                break

        return config

    @classmethod
    def get_platform_profile(cls, model_name: str) -> Optional[WebModelProfile]:
        """获取平台配置文件对象"""
        model_lower = model_name.lower()
        for platform_key, profile in cls.PLATFORM_PROFILES.items():
            if platform_key in model_lower:
                return profile
        return None

    @classmethod
    def get_all_web_models(cls, models: List[str]) -> List[str]:
        """
        从模型列表中筛选出所有Web模型

        Args:
            models: 模型名称列表

        Returns:
            List[str]: Web模型列表
        """
        return [model for model in models if cls.is_web_model(model)]

    @classmethod
    def get_api_models(cls, models: List[str]) -> List[str]:
        """
        从模型列表中筛选出所有API模型

        Args:
            models: 模型名称列表

        Returns:
            List[str]: API模型列表
        """
        return [model for model in models if not cls.is_web_model(model)]

    @classmethod
    def group_models_by_type(cls, models: List[str]) -> Dict[str, List[str]]:
        """
        按类型对模型进行分组

        Args:
            models: 模型名称列表

        Returns:
            Dict[str, List[str]]: 分组后的模型字典
        """
        return {
            "web": cls.get_all_web_models(models),
            "api": cls.get_api_models(models)
        }

    @classmethod
    def get_test_strategy(cls, model_name: str) -> Dict[str, Any]:
        """
        获取模型的测试策略

        基于模型类型返回推荐的测试执行策略。

        Args:
            model_name: 模型名称

        Returns:
            Dict[str, Any]: 测试策略配置
        """
        if cls.is_web_model(model_name):
            return {
                "execution_mode": "serial",
                "concurrency": 1,
                "session_management": "strict_isolation",
                "error_handling": "retry_with_backoff",
                "resource_management": "conservative",
                "monitoring": "detailed",
                "performance_tracking": True,
            }
        else:
            return {
                "execution_mode": "concurrent",
                "concurrency": 10,
                "session_management": "stateless",
                "error_handling": "fail_fast",
                "resource_management": "aggressive",
                "monitoring": "basic",
                "performance_tracking": False,
            }

    @classmethod
    def get_error_recovery_strategy(cls, error_type: str) -> Dict[str, Any]:
        """
        获取错误恢复策略

        Args:
            error_type: 错误类型

        Returns:
            Dict[str, Any]: 恢复策略配置
        """
        return cls.ERROR_RECOVERY_STRATEGIES.get(
            error_type,
            cls.ERROR_RECOVERY_STRATEGIES.get("timeout_error")  # 默认策略
        )

    @classmethod
    def calculate_test_timeout(cls, model_name: str, base_timeout: int = 60) -> int:
        """
        计算测试超时时间

        基于模型类型和配置计算合理的超时时间。

        Args:
            model_name: 模型名称
            base_timeout: 基础超时时间（秒）

        Returns:
            int: 计算后的超时时间（秒）
        """
        if not cls.is_web_model(model_name):
            return base_timeout

        config = cls.get_web_model_config(model_name)

        # Web模型需要额外的时间
        timeout = base_timeout
        timeout += config.get("new_chat_cooldown", 0)
        timeout += config.get("validation_timeout", 0) / 1000  # 转换为秒
        timeout *= 1.5  # 安全系数

        return int(timeout)

    @classmethod
    def validate_config(cls, config: Dict[str, Any]) -> bool:
        """
        验证配置的合理性

        实施配置验证规则，确保参数在合理范围内。

        Args:
            config: 配置字典

        Returns:
            bool: 配置是否有效
        """
        required_keys = ["force_new_chat", "session_isolation_mode", "max_concurrent"]

        # 检查必需键
        for key in required_keys:
            if key not in config:
                logger.error(f"配置缺少必需键: {key}")
                return False

        # 验证数值范围
        validations = [
            ("new_chat_cooldown", 0, 60),
            ("inter_test_delay", 0, 60),
            ("max_concurrent", 1, 5),
            ("clear_cookies_interval", 1, 100),
            ("browser_restart_interval", 10, 1000),
            ("max_response_wait_time", 10, 300),
        ]

        for key, min_val, max_val in validations:
            if key in config:
                value = config[key]
                if not isinstance(value, (int, float)) or value < min_val or value > max_val:
                    logger.error(f"配置 {key}={value} 超出有效范围 [{min_val}, {max_val}]")
                    return False

        # 验证枚举值
        valid_isolation_modes = [mode.value for mode in SessionIsolationMode]
        if config.get("session_isolation_mode") not in valid_isolation_modes:
            logger.error(f"无效的session_isolation_mode: {config.get('session_isolation_mode')}")
            return False

        return True

    @classmethod
    def get_performance_metrics_config(cls, model_name: str) -> Dict[str, Any]:
        """
        获取性能指标收集配置

        Args:
            model_name: 模型名称

        Returns:
            Dict[str, Any]: 性能指标配置
        """
        if cls.is_web_model(model_name):
            return {
                "collect_browser_metrics": True,
                "collect_network_timing": True,
                "collect_dom_metrics": True,
                "collect_memory_usage": True,
                "sampling_interval": 1000,  # 毫秒
                "metrics_buffer_size": 1000,
            }
        else:
            return {
                "collect_api_latency": True,
                "collect_token_usage": True,
                "collect_error_rates": True,
                "sampling_rate": 1.0,
            }

    @classmethod
    def get_test_priority(cls, model_name: str) -> int:
        """
        获取测试优先级

        Web模型由于资源消耗大，应该获得较低的优先级以避免资源竞争。

        Args:
            model_name: 模型名称

        Returns:
            int: 优先级（数值越小优先级越高）
        """
        if cls.is_web_model(model_name):
            # Web模型根据平台给予不同优先级
            profile = cls.get_platform_profile(model_name)
            if profile:
                if profile.platform_name == "o43_web":
                    return 3  # O4.3最消耗资源
                elif profile.platform_name == "doubao_web":
                    return 2
                else:
                    return 1
            return 2  # 默认Web模型优先级
        else:
            return 0  # API模型最高优先级