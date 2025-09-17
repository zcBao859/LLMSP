"""
九天Web适配器 - 通过网页爬取实现九天AI接口
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from playwright.async_api import Page

from .web_adapter_base import WebAdapterBase

logger = logging.getLogger(__name__)


class JiutianWebAdapter(WebAdapterBase):
    """九天Web适配器"""

    def __init__(self, config: Dict[str, Any]):
        # 设置默认配置
        config.setdefault("platform_name", "jiutian_web")
        config.setdefault("base_url", "https://jiutian.10086.cn/largemodel/playground/#/playground/jiutian-lan")

        # 浏览器配置
        default_browser_config = {
            "headless": True,  # 生产环境使用无头模式
            "timeout": 30000,
            "slow_mo": 100,  # 减慢操作速度，更像人类行为
        }
        config.setdefault("browser_config", default_browser_config)

        super().__init__(config)

        # 会话管理
        self._conversation_count = 0

    async def check_login_status(self, page: Page) -> bool:
        """检查九天平台是否已登录"""
        try:
            login_score = 0

            # 1. 检查是否存在新建对话按钮（通常只有登录后才显示）
            new_chat_selectors = [
                'div.btn:has-text("新建对话")',
                'div.btn i.icon-message1',
                'div[data-v-65073c23].btn',
                '[class*="btn"]:has-text("新建对话")'
            ]

            for selector in new_chat_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element and await element.is_visible():
                        login_score += 2
                        break
                except:
                    continue

            # 2. 检查是否存在输入框
            input_selectors = [
                'textarea',
                'textarea[placeholder*="输入"]',
                'textarea[placeholder*="问题"]',
                'div[contenteditable="true"]',
                'input[type="text"][placeholder*="输入"]'
            ]

            for selector in input_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        is_editable = await element.evaluate("""
                            (el) => {
                                if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                                    return !el.disabled && !el.readOnly;
                                }
                                return el.contentEditable === 'true';
                            }
                        """)
                        if is_editable:
                            login_score += 2
                            break
                except:
                    continue

            # 3. 检查是否存在深度思考按钮（九天特有）
            deep_think_selectors = [
                'button.input-bottom-btn:has-text("深度思考")',
                'button:has(em.icon-bulb)',
                'button[data-v-71d6fbf5].input-bottom-btn'
            ]

            for selector in deep_think_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        login_score += 1
                        break
                except:
                    continue

            # 4. 检查是否在登录页面
            login_page_indicators = [
                'button:has-text("登录")',
                'button:has-text("立即登录")',
                'input[type="password"]',
                '[class*="login"]',
                'form[class*="login"]'
            ]

            for selector in login_page_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        logger.info("检测到登录页面元素")
                        return False
                except:
                    continue

            # 需要至少3分才认为已登录
            is_logged_in = login_score >= 3
            logger.info(f"登录检测分数: {login_score}, 判定为{'已登录' if is_logged_in else '未登录'}")
            return is_logged_in

        except Exception as e:
            logger.error(f"检查登录状态失败: {str(e)}")
            return False

    async def create_new_chat(self, page: Page) -> bool:
        """创建新对话"""
        try:
            # 增加对话计数
            self._conversation_count += 1

            # 每隔几次对话才创建新的，避免频繁创建
            if self._conversation_count % 5 != 1:
                logger.info(f"继续使用当前对话 (第{self._conversation_count}次)")
                return True

            # 九天的新建对话选择器
            new_chat_selectors = [
                'div.btn:has-text("新建对话")',
                'div[data-v-65073c23].btn:has-text("新建对话")',
                'div.btn:has(i.icon-message1)',
                '[class*="btn"]:has-text("新建对话")',
                'button:has-text("新建对话")',
                'div:has-text("新建对话")',
                'i.icon-message1',
                '.iconfont.icon-message1'
            ]

            for selector in new_chat_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element and await element.is_visible():
                        # 如果是图标，尝试点击其父元素
                        if selector.startswith('i.') or selector.endswith('icon-message1'):
                            await page.evaluate('(el) => el.parentElement && el.parentElement.click()', element)
                        else:
                            await element.click()

                        await asyncio.sleep(2)
                        logger.info("成功点击新建对话按钮")
                        return True
                except:
                    continue

            # 使用JavaScript作为备选方案
            try:
                result = await page.evaluate("""
                    () => {
                        // 查找包含"新建对话"文本的元素
                        const elements = document.querySelectorAll('div.btn, button, [class*="btn"]');
                        for (const el of elements) {
                            if (el.textContent && el.textContent.includes('新建对话')) {
                                el.click();
                                return true;
                            }
                        }

                        // 查找图标按钮
                        const iconBtn = document.querySelector('i.icon-message1');
                        if (iconBtn && iconBtn.parentElement) {
                            iconBtn.parentElement.click();
                            return true;
                        }

                        return false;
                    }
                """)

                if result:
                    await asyncio.sleep(2)
                    logger.info("通过JavaScript成功创建新对话")
                    return True

            except Exception as e:
                logger.debug(f"JavaScript点击失败: {str(e)}")

            # 如果都失败了，继续使用当前对话
            logger.warning("无法创建新对话，继续使用当前对话")
            return True

        except Exception as e:
            logger.error(f"创建新对话失败: {str(e)}")
            return False

    def get_input_selectors(self) -> List[str]:
        """获取输入框选择器"""
        return [
            'textarea',
            'textarea[placeholder*="输入"]',
            'textarea[placeholder*="问题"]',
            'textarea[placeholder*="消息"]',
            'div[contenteditable="true"]',
            'input[type="text"][placeholder*="输入"]',
            # 九天特定的输入框
            'textarea.el-textarea__inner',
            'textarea[class*="input"]',
            'textarea[class*="chat"]'
        ]

    def get_send_button_selectors(self) -> List[str]:
        """获取发送按钮选择器"""
        return [
            'button[aria-label*="发送"]',
            'button:has-text("发送")',
            'button[type="submit"]',
            '[class*="send-btn"]',
            '[class*="send-button"]',
            # 九天特定的发送按钮
            'button.el-button',
            'button[class*="primary"]',
            'button[class*="submit"]',
            # 图标按钮
            'button:has(i[class*="send"])',
            'button:has(span[class*="send"])'
        ]

    def get_response_selectors(self) -> List[str]:
        """获取响应内容选择器"""
        return [
            # 九天可能的响应容器
            "[class*='message-content']",
            "[class*='response-content']",
            "[class*='assistant-message']",
            "[class*='bot-message']",
            "[class*='ai-message']",
            # 通用markdown容器
            "[class*='markdown']",
            "[class*='md-content']",
            # 基于data-v属性的选择器
            "[data-v-71d6fbf5]",
            "[data-v-65073c23]",
            # 对话相关
            "[class*='chat-message']",
            "[class*='conversation-message']",
            # 文本容器
            "[class*='text-content']",
            "[class*='message-text']",
            "div.message",
            "div.response",
            # 九天特定
            "div.el-message",
            "[class*='el-'][class*='message']"
        ]

    async def wait_for_response_complete(self, page: Page) -> bool:
        """等待响应完全结束"""
        try:
            # 九天特定的加载/处理指示器
            processing_indicators = [
                "[class*='loading']",
                "[class*='generating']",
                "[class*='thinking']",
                "text*='生成中'",
                "text*='思考中'",
                "text*='加载中'",
                "[class*='message-loading']",
                "[class*='response-loading']",
                # Element UI 的加载指示器
                ".el-loading-mask",
                ".el-loading-spinner"
            ]

            # 等待这些指示器消失
            for selector in processing_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        logger.info(f"检测到处理指示器: {selector}")
                        await page.wait_for_selector(selector, state="hidden", timeout=10000)
                        await asyncio.sleep(1)
                except:
                    continue

            # 检查停止按钮是否消失
            stop_button_selectors = [
                "button:has-text('停止')",
                "button:has-text('取消')",
                "[class*='stop']",
                "[class*='cancel']",
                "span.icon-btn",
                "[class*='icon-stop']",
                "[class*='icon-cancel']",
                "[class*='btn-stop']",
                "[class*='stop-generate']"
            ]

            for _ in range(10):  # 最多检查10次
                stop_button_found = False
                for selector in stop_button_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            if await element.is_visible():
                                stop_button_found = True
                                break
                    except:
                        continue

                    if stop_button_found:
                        break

                if not stop_button_found:
                    logger.info("停止按钮已消失，响应可能已完成")
                    break

                await asyncio.sleep(1)

            # 额外等待确保响应稳定
            await asyncio.sleep(2)
            return True

        except Exception as e:
            logger.error(f"等待响应完成时出错: {str(e)}")
            return False

    async def wait_for_response(self, page: Page, timeout: int = None) -> Optional[str]:
        """等待并获取响应 - 九天特定实现"""
        if timeout is None:
            timeout = self.response_timeout

        # 先等待一下让响应开始生成
        await asyncio.sleep(3)

        # 等待响应完成
        await self.wait_for_response_complete(page)

        # 调用基类方法获取响应
        return await super().wait_for_response(page, timeout)

    async def handle_deep_thinking(self, page: Page) -> bool:
        """处理深度思考功能（九天特有）"""
        try:
            # 检查是否有深度思考按钮
            deep_think_selectors = [
                'button.input-bottom-btn:has-text("深度思考")',
                'button:has(em.icon-bulb)',
                'button[data-v-71d6fbf5].input-bottom-btn',
                'button.input-bottom-btn-on'
            ]

            for selector in deep_think_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        # 检查按钮是否已激活
                        class_name = await element.get_attribute('class')
                        if class_name and 'input-bottom-btn-on' in class_name:
                            logger.info("深度思考功能已开启")
                            return True
                        else:
                            # 点击开启深度思考
                            await element.click()
                            await asyncio.sleep(1)
                            logger.info("已开启深度思考功能")
                            return True
                except:
                    continue

            return False

        except Exception as e:
            logger.debug(f"处理深度思考功能失败: {str(e)}")
            return False

    async def ensure_logged_in(self, page: Page) -> bool:
        """确保已登录 - 九天特定实现"""
        if await self.check_login_status(page):
            return True

        # 如果未登录，需要手动处理
        logger.error("九天未登录，Web适配器暂不支持自动登录")
        logger.info("请先通过浏览器手动登录九天，并保存登录状态")

        # 可以考虑实现等待手动登录的逻辑
        # 但在生产环境中，应该预先保存好登录状态
        return False

    async def send_message_to_page(self, page: Page, message: str) -> bool:
        """发送消息到页面 - 九天特定实现"""
        try:
            # 如果需要，可以开启深度思考
            # await self.handle_deep_thinking(page)

            # 调用基类方法发送消息
            return await super().send_message_to_page(page, message)

        except Exception as e:
            logger.error(f"发送消息失败: {str(e)}")
            return False