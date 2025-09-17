# backend/openai_api/api/adapters/web_adapter_base.py
"""
Web适配器基类 - 会话隔离增强版

本模块实现了基于浏览器自动化的模型适配器基类，融合了会话隔离理论
和分布式系统的状态管理最佳实践。
"""
import asyncio
import json
import os
import threading
import concurrent.futures
from abc import abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, AsyncIterator
import logging
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright
from django.conf import settings

from .base_adapter import BaseAdapter, OpenAIResponse, OpenAIChoice, OpenAIMessage, OpenAIUsage, OpenAIStreamChunk
from ..web_model_config import WebModelTestConfig, SessionIsolationMode

logger = logging.getLogger(__name__)


class PlaywrightManager:
    """Playwright 实例管理器 - 优化无头模式支持"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self._thread = None
            self._loop = None
            self._browsers = {}  # platform -> browser info
            self._playwright = None
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            self._start_event_loop()

    def _start_event_loop(self):
        """在独立线程中启动事件循环"""

        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        # 等待循环启动
        import time
        while self._loop is None:
            time.sleep(0.01)

    def _run_async(self, coro):
        """在 Playwright 线程中运行异步代码"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=60)

    async def _get_or_create_browser(self, platform: str, config: Dict[str, Any]):
        """获取或创建浏览器实例（优化无头模式）"""

        logger.info(f"[浏览器管理] 开始获取/创建浏览器: platform={platform}")

        # 强制使用无头模式（除非明确设置为 False）
        is_headless = config.get('headless', True)

        # 从环境变量读取（用于调试）
        if os.environ.get('BROWSER_HEADLESS', '').lower() == 'false':
            is_headless = False
            logger.warning("通过环境变量 BROWSER_HEADLESS=false 禁用了无头模式")

        logger.info(f"[浏览器管理] 无头模式: {is_headless}")

        # 初始化 Playwright
        if not self._playwright:
            self._playwright = await async_playwright().start()
            logger.info("Playwright 已初始化")

        # 检查现有浏览器
        if platform in self._browsers:
            browser_info = self._browsers[platform]
            browser_info['last_used'] = datetime.now()

            # 检查页面是否有效
            try:
                await browser_info['page'].evaluate('() => true')
                logger.info(f"复用 {platform} 浏览器实例")
                return browser_info['context'], browser_info['page']
            except:
                logger.warning(f"{platform} 浏览器失效，重新创建")
                await self._close_browser_internal(platform)

        # 创建新浏览器
        logger.info(f"创建新的 {platform} 浏览器实例")

        # 优化的启动参数
        default_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-gpu',  # 无头模式必需
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--disable-images',  # 禁用图片加载，提高速度
            '--window-size=1920,1080',
            '--start-maximized',
            '--disable-notifications',
            '--disable-popup-blocking',
            '--disable-translate',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            '--disable-default-apps',
            '--hide-scrollbars',
            '--mute-audio',
            '--no-first-run',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
        ]

        # 合并用户自定义参数
        custom_args = config.get('args', [])
        launch_args = list(set(default_args + custom_args))  # 去重

        # 浏览器启动选项
        launch_options = {
            'headless': is_headless,
            'args': launch_args,
            'ignore_default_args': ['--enable-automation'],  # 禁用自动化标识
        }

        # 如果配置中有其他启动选项，合并进来
        for key in ['executable_path', 'channel', 'devtools', 'downloads_path']:
            if key in config:
                launch_options[key] = config[key]

        browser = await self._playwright.chromium.launch(**launch_options)

        # 上下文选项
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'bypass_csp': True,
            'ignore_https_errors': True,
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
            'permissions': ['geolocation', 'notifications'],  # 授予必要权限
            'extra_http_headers': {
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            }
        }

        # 加载保存的状态
        state_dir = settings.WEB_SCRAPER_CONFIG.get("state_dir", "browser_states")
        state_file = os.path.join(state_dir, f"{platform}_state.json")

        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state_data = json.load(f)

                # 验证状态数据
                if state_data.get('cookies'):
                    context_options['storage_state'] = state_file
                    logger.info(
                        f"[状态加载] ✅ 成功加载 {platform} 的保存状态 ({len(state_data.get('cookies', []))} cookies)")
                else:
                    logger.warning(f"[状态加载] ⚠️ 状态文件存在但没有cookies")
            except Exception as e:
                logger.error(f"[状态加载] ❌ 加载状态失败: {e}")

        context = await browser.new_context(**context_options)

        # 增强的反检测脚本
        await context.add_init_script("""
            // 移除 webdriver 标识
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 修改 plugins 长度
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // 修改 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });

            // 添加 chrome 对象
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // 修改权限查询
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

        # 设置额外的 CDP 命令（如果是 Chromium）
        if hasattr(context, 'add_init_script'):
            # 禁用 WebRTC IP 泄露
            await context.add_init_script("""
                const mediaDevices = navigator.mediaDevices;
                if (mediaDevices && mediaDevices.getUserMedia) {
                    mediaDevices.getUserMedia = new Proxy(mediaDevices.getUserMedia, {
                        apply: function(target, thisArg, argumentsList) {
                            return Promise.reject(new Error('Permission denied'));
                        }
                    });
                }
            """)

        page = await context.new_page()

        # 设置默认超时
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(30000)

        # 监听控制台消息（用于调试）
        if logger.isEnabledFor(logging.DEBUG):
            page.on('console', lambda msg: logger.debug(f"[浏览器控制台] {msg.text}"))
            page.on('pageerror', lambda err: logger.error(f"[浏览器错误] {err}"))

        self._browsers[platform] = {
            'browser': browser,
            'context': context,
            'page': page,
            'last_used': datetime.now(),
            'headless': is_headless
        }

        logger.info(f"[浏览器管理] 成功创建 {platform} 浏览器实例 (无头模式: {is_headless})")
        return context, page

    async def _close_browser_internal(self, platform: str):
        """关闭浏览器（内部方法）"""
        if platform in self._browsers:
            browser_info = self._browsers[platform]
            try:
                # 保存状态
                state_dir = settings.WEB_SCRAPER_CONFIG.get("state_dir", "browser_states")
                os.makedirs(state_dir, exist_ok=True)
                state_file = os.path.join(state_dir, f"{platform}_state.json")

                try:
                    await browser_info['context'].storage_state(path=state_file)
                    logger.info(f"保存 {platform} 状态到 {state_file}")
                except Exception as e:
                    logger.error(f"保存状态失败: {e}")

                # 关闭页面、上下文和浏览器
                await browser_info['page'].close()
                await browser_info['context'].close()
                await browser_info['browser'].close()

                logger.info(f"成功关闭 {platform} 浏览器")
            except Exception as e:
                logger.error(f"关闭浏览器失败: {e}")
            finally:
                del self._browsers[platform]

    def get_browser(self, platform: str, config: Dict[str, Any]) -> tuple:
        """获取浏览器实例（公共方法）"""
        return self._run_async(self._get_or_create_browser(platform, config))

    def cleanup(self):
        """清理所有资源"""

        async def _cleanup():
            for platform in list(self._browsers.keys()):
                await self._close_browser_internal(platform)

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

        if self._loop:
            self._run_async(_cleanup())
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)


class WebAdapterBase(BaseAdapter):
    """Web适配器基类 - 增强版，支持严格的会话隔离"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.browser_manager = PlaywrightManager()
        self.platform_name = config.get("platform_name", "unknown")
        self.base_url = config.get("base_url", "")
        self.browser_config = config.get("browser_config", {})

        # 默认配置
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 5)
        self.response_timeout = config.get("response_timeout", 60)
        self.response_check_interval = config.get("response_check_interval", 1)

        # 新增：会话隔离配置
        self._init_session_isolation_config(config)

        # 会话管理状态
        self._session_state = {
            "current_session_id": None,
            "session_count": 0,
            "last_session_time": None,
            "session_errors": [],
        }

    def _init_session_isolation_config(self, config: Dict[str, Any]):
        """初始化会话隔离配置"""
        # 获取Web模型配置
        web_config = WebModelTestConfig.get_web_model_config(self.platform_name)

        # 合并配置（传入配置优先）
        self.session_isolation_mode = config.get(
            "session_isolation_mode",
            web_config.get("session_isolation_mode", "strict")
        )
        self.force_new_chat = config.get(
            "force_new_chat",
            web_config.get("force_new_chat", True)
        )
        self.new_chat_cooldown = config.get(
            "new_chat_cooldown",
            web_config.get("new_chat_cooldown", 2)
        )
        self.verify_new_chat_success = config.get(
            "verify_new_chat_success",
            web_config.get("verify_new_chat_success", True)
        )
        self.wait_for_stable_state = config.get(
            "wait_for_stable_state",
            web_config.get("wait_for_stable_state", True)
        )

        logger.info(f"[会话隔离] {self.platform_name} 配置: "
                    f"模式={self.session_isolation_mode}, "
                    f"强制新建={self.force_new_chat}, "
                    f"冷却时间={self.new_chat_cooldown}秒")

    def update_session_config(self, config: Dict[str, Any]):
        """动态更新会话配置"""
        if "session_isolation_mode" in config:
            self.session_isolation_mode = config["session_isolation_mode"]
        if "force_new_chat" in config:
            self.force_new_chat = config["force_new_chat"]
        if "new_chat_cooldown" in config:
            self.new_chat_cooldown = config["new_chat_cooldown"]

        logger.debug(f"[会话隔离] 更新配置: {config}")

    async def ensure_logged_in(self, page: Page) -> bool:
        """确保已登录 - 需要在子类中实现具体的登录检查逻辑"""
        return await self.check_login_status(page)

    async def ensure_clean_session(self, page: Page) -> bool:
        """确保干净的会话状态"""
        try:
            logger.info(f"[会话隔离] 开始确保干净会话 (模式: {self.session_isolation_mode})")

            # 根据隔离模式执行不同策略
            if self.session_isolation_mode == SessionIsolationMode.STRICT.value:
                # 严格模式：总是创建新会话
                return await self._ensure_strict_isolation(page)
            elif self.session_isolation_mode == SessionIsolationMode.MODERATE.value:
                # 适度模式：检查后决定
                return await self._ensure_moderate_isolation(page)
            else:
                # 宽松模式：尽可能复用
                return await self._ensure_loose_isolation(page)

        except Exception as e:
            logger.error(f"[会话隔离] 确保干净会话失败: {str(e)}")
            self._session_state["session_errors"].append({
                "time": datetime.now().isoformat(),
                "error": str(e),
                "type": "ensure_clean_session"
            })
            return False

    async def _ensure_strict_isolation(self, page: Page) -> bool:
        """严格隔离：总是创建新会话"""
        # 检查是否有活跃对话
        if await self.has_active_conversation(page):
            logger.info("[会话隔离-严格] 检测到活跃对话，结束当前对话")
            await self.end_current_conversation(page)
            await asyncio.sleep(self.new_chat_cooldown)

        # 创建新对话
        success = await self.create_new_chat_enhanced(page)

        if success:
            self._session_state["session_count"] += 1
            self._session_state["last_session_time"] = datetime.now()
            logger.info(f"[会话隔离-严格] 新会话创建成功 (总计: {self._session_state['session_count']})")

        return success

    async def _ensure_moderate_isolation(self, page: Page) -> bool:
        """适度隔离：根据情况决定"""
        # 检查会话年龄
        if self._session_state["last_session_time"]:
            session_age = (datetime.now() - self._session_state["last_session_time"]).seconds
            if session_age > 300:  # 5分钟
                logger.info(f"[会话隔离-适度] 会话已老化 ({session_age}秒)，创建新会话")
                return await self._ensure_strict_isolation(page)

        # 检查错误计数
        recent_errors = [e for e in self._session_state["session_errors"]
                         if datetime.fromisoformat(e["time"]) > datetime.now() - timedelta(minutes=10)]
        if len(recent_errors) > 2:
            logger.info(f"[会话隔离-适度] 近期错误过多 ({len(recent_errors)}次)，创建新会话")
            return await self._ensure_strict_isolation(page)

        # 检查对话状态
        if await self.has_active_conversation(page):
            # 有对话但状态良好，可以复用
            logger.info("[会话隔离-适度] 复用现有会话")
            return True
        else:
            # 无对话，创建新的
            return await self.create_new_chat_enhanced(page)

    async def _ensure_loose_isolation(self, page: Page) -> bool:
        """宽松隔离：尽可能复用会话"""
        # 只在必要时创建新会话
        if not await self.has_active_conversation(page):
            logger.info("[会话隔离-宽松] 无活跃会话，创建新会话")
            return await self.create_new_chat_enhanced(page)

        logger.info("[会话隔离-宽松] 复用现有会话")
        return True

    async def has_active_conversation(self, page: Page) -> bool:
        """检查是否有活跃的对话"""
        # 子类需要实现具体的检测逻辑
        # 默认实现：检查是否有消息历史
        try:
            message_selectors = self.get_response_selectors()
            for selector in message_selectors:
                elements = await page.query_selector_all(selector)
                if elements and len(elements) > 0:
                    return True
            return False
        except:
            return False

    async def end_current_conversation(self, page: Page) -> bool:
        """结束当前对话 - 子类可以覆盖实现平台特定逻辑"""
        # 默认实现：尝试点击新建对话按钮
        return await self.create_new_chat(page)

    async def create_new_chat_enhanced(self, page: Page) -> bool:
        """增强的创建新对话方法"""
        max_attempts = self.max_retries

        for attempt in range(max_attempts):
            try:
                logger.info(f"[会话隔离] 尝试创建新对话 (尝试 {attempt + 1}/{max_attempts})")

                # 等待页面稳定
                if self.wait_for_stable_state:
                    await self.wait_for_page_stable(page)

                # 记录当前会话ID（如果子类支持）
                old_session_id = await self.get_current_session_id(page) if hasattr(self,
                                                                                    'get_current_session_id') else None

                # 调用原始的create_new_chat方法
                success = await self.create_new_chat(page)

                if success:
                    # 验证新对话创建成功
                    await asyncio.sleep(self.new_chat_cooldown)

                    if self.verify_new_chat_success:
                        # 验证会话ID变化
                        new_session_id = await self.get_current_session_id(page) if hasattr(self,
                                                                                            'get_current_session_id') else None

                        if old_session_id and new_session_id and old_session_id == new_session_id:
                            logger.warning("[会话隔离] 会话ID未变化，可能创建失败")
                            success = False
                        elif await self.verify_new_chat_ready(page):
                            logger.info(f"[会话隔离] 新对话创建成功并验证通过")
                            self._session_state["current_session_id"] = new_session_id
                            return True
                        else:
                            logger.warning("[会话隔离] 新对话创建后验证失败")
                            success = False
                    else:
                        return True

            except Exception as e:
                logger.error(f"[会话隔离] 创建新对话尝试 {attempt + 1} 失败: {str(e)}")
                self._session_state["session_errors"].append({
                    "time": datetime.now().isoformat(),
                    "error": str(e),
                    "type": "create_new_chat",
                    "attempt": attempt + 1
                })

            if attempt < max_attempts - 1:
                wait_time = self.retry_delay * (attempt + 1)
                logger.info(f"[会话隔离] 等待 {wait_time} 秒后重试")
                await asyncio.sleep(wait_time)

        return False

    async def wait_for_page_stable(self, page: Page, timeout: int = 5000):
        """等待页面稳定"""
        try:
            # 等待网络空闲
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except:
            # 降级到domcontentloaded
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except:
                logger.warning("[会话隔离] 页面稳定等待超时")

    async def verify_new_chat_ready(self, page: Page) -> bool:
        """验证新对话是否准备就绪"""
        try:
            # 检查输入框是否可用
            input_selectors = self.get_input_selectors()
            for selector in input_selectors:
                try:
                    input_box = await page.wait_for_selector(selector, timeout=2000)
                    if input_box:
                        is_editable = await input_box.is_editable()
                        if is_editable:
                            # 检查是否没有历史消息（或只有欢迎消息）
                            message_count = 0
                            for msg_selector in self.get_response_selectors():
                                elements = await page.query_selector_all(msg_selector)
                                message_count += len(elements)

                            # 允许最多1条消息（欢迎消息）
                            return message_count <= 1
                except:
                    continue
            return False
        except Exception as e:
            logger.error(f"[会话隔离] 验证新对话就绪失败: {str(e)}")
            return False

    async def get_current_session_id(self, page: Page) -> Optional[str]:
        """获取当前会话ID - 子类可以覆盖实现"""
        # 默认实现：返回None
        return None

    @abstractmethod
    async def check_login_status(self, page: Page) -> bool:
        """检查登录状态 - 需要在子类中实现"""
        pass

    @abstractmethod
    async def create_new_chat(self, page: Page) -> bool:
        """创建新对话 - 需要在子类中实现"""
        pass

    @abstractmethod
    def get_input_selectors(self) -> List[str]:
        """获取输入框选择器 - 需要在子类中实现"""
        pass

    @abstractmethod
    def get_send_button_selectors(self) -> List[str]:
        """获取发送按钮选择器 - 需要在子类中实现"""
        pass

    @abstractmethod
    def get_response_selectors(self) -> List[str]:
        """获取响应内容选择器 - 需要在子类中实现"""
        pass

    async def send_message_to_page(self, page: Page, message: str) -> bool:
        """发送消息到页面 - 基础实现"""
        try:
            # 找到输入框
            input_box = None
            for selector in self.get_input_selectors():
                try:
                    input_box = await page.wait_for_selector(selector, timeout=3000)
                    if input_box:
                        break
                except:
                    continue

            if not input_box:
                raise Exception("无法找到输入框")

            # 清空并输入消息
            await input_box.click()
            await input_box.fill("")
            await input_box.fill(message)
            await asyncio.sleep(0.5)

            # 发送消息
            send_success = False

            # 尝试回车键
            try:
                await page.keyboard.press("Enter")
                send_success = True
            except:
                # 查找发送按钮
                for selector in self.get_send_button_selectors():
                    try:
                        send_btn = await page.wait_for_selector(selector, timeout=1000)
                        if send_btn:
                            await send_btn.click()
                            send_success = True
                            break
                    except:
                        continue

            return send_success

        except Exception as e:
            logger.error(f"发送消息失败: {str(e)}")
            return False

    async def wait_for_response(self, page: Page, timeout: int = None) -> Optional[str]:
        """等待并获取响应"""
        if timeout is None:
            timeout = self.response_timeout

        start_time = asyncio.get_event_loop().time()
        last_response = ""
        stable_count = 0

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                # 获取当前响应
                current_response = await self.get_current_response(page)

                if current_response:
                    # 检查响应是否稳定
                    if current_response == last_response and len(current_response) > 50:
                        stable_count += 1
                        if stable_count >= 3:  # 连续3次相同，认为响应完成
                            return current_response
                    else:
                        stable_count = 0
                        last_response = current_response

                await asyncio.sleep(self.response_check_interval)

            except Exception as e:
                logger.debug(f"等待响应时出错: {str(e)}")

        return last_response if last_response else None

    async def get_current_response(self, page: Page) -> Optional[str]:
        """获取当前页面上的响应内容"""
        try:
            for selector in self.get_response_selectors():
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        # 获取最后一个元素（最新的响应）
                        last_element = elements[-1]
                        text = await last_element.text_content()
                        if text and text.strip():
                            return text.strip()
                except:
                    continue
        except Exception as e:
            logger.error(f"获取响应失败: {str(e)}")

        return None

    async def create_completion(
            self,
            messages: List[Dict[str, str]],
            model: str,
            stream: bool = False,
            **kwargs
    ) -> OpenAIResponse:
        """创建聊天补全 - 增强版，确保会话隔离"""

        def browser_task():
            """在 Playwright 线程中执行的任务"""
            try:
                # 获取浏览器
                context, page = self.browser_manager.get_browser(
                    self.platform_name,
                    self.browser_config
                )

                # 在事件循环中运行异步操作
                loop = self.browser_manager._loop

                # 确保在正确的页面
                current_url = asyncio.run_coroutine_threadsafe(
                    page.evaluate('() => window.location.href'), loop
                ).result()

                if not current_url.startswith(self.base_url):
                    asyncio.run_coroutine_threadsafe(
                        page.goto(self.base_url, wait_until="domcontentloaded"), loop
                    ).result()
                    import time
                    time.sleep(3)

                # 检查登录状态
                logged_in = asyncio.run_coroutine_threadsafe(
                    self.ensure_logged_in(page), loop
                ).result()

                if not logged_in:
                    return None, "未登录到平台"

                # 关键改进：确保干净的会话状态
                if self.force_new_chat:
                    clean_session = asyncio.run_coroutine_threadsafe(
                        self.ensure_clean_session(page), loop
                    ).result()

                    if not clean_session:
                        logger.warning("[会话隔离] 无法确保干净的会话，但继续执行")
                        # 可以选择是否继续
                        if self.session_isolation_mode == SessionIsolationMode.STRICT.value:
                            return None, "无法创建干净的会话"
                else:
                    # 使用原有逻辑
                    asyncio.run_coroutine_threadsafe(
                        self.create_new_chat(page), loop
                    ).result()

                # 提取用户消息
                user_message = ""
                for msg in reversed(messages):
                    if msg["role"] == "user":
                        user_message = msg["content"]
                        break

                if not user_message:
                    return None, "没有用户消息"

                # 发送消息
                send_success = asyncio.run_coroutine_threadsafe(
                    self.send_message_to_page(page, user_message), loop
                ).result()

                if not send_success:
                    return None, "发送消息失败"

                # 等待响应
                response_text = asyncio.run_coroutine_threadsafe(
                    self.wait_for_response(page), loop
                ).result()

                if not response_text:
                    return None, "未收到响应"

                return response_text, None

            except Exception as e:
                logger.error(f"浏览器任务失败: {str(e)}", exc_info=True)
                return None, str(e)

        # 在线程池中执行浏览器任务
        try:
            response_text, error = browser_task()

            if error:
                return self.create_error_response(error, model)

            # 估算token使用
            prompt_text = self.format_messages(messages)
            usage = OpenAIUsage(
                prompt_tokens=self.estimate_tokens(prompt_text),
                completion_tokens=self.estimate_tokens(response_text),
                total_tokens=self.estimate_tokens(prompt_text) + self.estimate_tokens(response_text)
            )

            return OpenAIResponse(
                model=model,
                choices=[
                    OpenAIChoice(
                        index=0,
                        message=OpenAIMessage(
                            role="assistant",
                            content=response_text
                        ),
                        finish_reason="stop"
                    )
                ],
                usage=usage
            )

        except Exception as e:
            logger.error(f"创建completion失败: {str(e)}", exc_info=True)
            return self.create_error_response(str(e), model)

    async def create_completion_stream(
            self,
            messages: List[Dict[str, str]],
            model: str,
            **kwargs
    ) -> AsyncIterator[OpenAIStreamChunk]:
        """创建流式响应 - 通过模拟实现"""

        # 先获取完整响应
        response = await self.create_completion(messages, model, stream=False, **kwargs)

        # 模拟流式输出
        chunk_id = f"chatcmpl-{self.platform_name}-stream"

        # 初始块
        yield OpenAIStreamChunk(
            id=chunk_id,
            model=model,
            choices=[{
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None
            }]
        )

        # 内容块
        if response.choices and response.choices[0].message.content:
            content = response.choices[0].message.content
            chunk_size = 20

            for i in range(0, len(content), chunk_size):
                chunk_text = content[i:i + chunk_size]
                yield OpenAIStreamChunk(
                    id=chunk_id,
                    model=model,
                    choices=[{
                        "index": 0,
                        "delta": {"content": chunk_text},
                        "finish_reason": None
                    }]
                )
                await asyncio.sleep(0.05)

        # 结束块
        yield OpenAIStreamChunk(
            id=chunk_id,
            model=model,
            choices=[{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        )

    def get_session_state(self) -> Dict[str, Any]:
        """获取会话状态信息"""
        return self._session_state.copy()

    def reset_session_state(self):
        """重置会话状态"""
        self._session_state = {
            "current_session_id": None,
            "session_count": 0,
            "last_session_time": None,
            "session_errors": [],
        }
        logger.info("[会话隔离] 会话状态已重置")


# 全局清理函数
async def cleanup_browsers():
    """清理所有浏览器实例"""
    manager = PlaywrightManager()
    manager.cleanup()