"""
元宝Web适配器 - 通过网页爬取实现元宝AI接口
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from playwright.async_api import Page

from .web_adapter_base import WebAdapterBase

logger = logging.getLogger(__name__)


class YuanBaoWebAdapter(WebAdapterBase):
    """元宝Web适配器"""

    def __init__(self, config: Dict[str, Any]):
        # 设置默认配置
        config.setdefault("platform_name", "yuanbao_web")
        config.setdefault("base_url", "https://yuanbao.tencent.com/chat")

        # 浏览器配置
        default_browser_config = {
            "headless": True,  # 生产环境使用无头模式
            "timeout": 30000,
            "slow_mo": 100,  # 减慢操作速度，更像人类行为
        }
        config.setdefault("browser_config", default_browser_config)

        super().__init__(config)

    async def check_login_status(self, page: Page) -> bool:
        """检查元宝平台是否已登录"""
        try:
            login_score = 0

            # 1. 检查新建对话按钮
            new_chat_selectors = [
                'span.yb-icon.iconfont-yb.icon-yb-ic_newchat_20',
                'div.yb-common-nav__trigger[data-desc="fold"]',
                '[class*="newchat"]',
                '[class*="new-chat"]'
            ]

            for selector in new_chat_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        is_visible = await element.evaluate("""
                            (el) => {
                                const style = window.getComputedStyle(el);
                                return style.display !== 'none' && 
                                       style.visibility !== 'hidden' && 
                                       style.opacity !== '0' &&
                                       style.pointerEvents !== 'none';
                            }
                        """)
                        if is_visible:
                            login_score += 1
                            break
                except:
                    continue

            # 2. 检查输入框
            input_selectors = [
                'textarea',
                'div[contenteditable="true"]',
                '[class*="input"][class*="area"]',
                '[class*="yb-"][class*="input"]',
                'div.yb-chat-input'
            ]

            for selector in input_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        is_editable = await element.evaluate("""
                            (el) => {
                                if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
                                    return !el.disabled && !el.readOnly;
                                } else if (el.contentEditable) {
                                    return el.contentEditable === 'true';
                                }
                                return false;
                            }
                        """)
                        if is_editable:
                            login_score += 2
                            break
                except:
                    continue

            # 3. 检查用户信息（最可靠的登录标志）
            user_indicators = [
                '[class*="user-avatar"]',
                '[class*="yb-common-user"]',
                '[class*="user-info"]',
                'img[class*="avatar"]',
                'div.yb-user-profile'
            ]

            for selector in user_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        login_score += 3
                        break
                except:
                    continue

            # 4. 检查是否存在元宝特色功能（深度思考等）
            feature_selectors = [
                'button:has-text("深度思考")',
                '[class*="deep-think"]',
                'div.hyc-component-reasoner',
                '[class*="yb-feature"]'
            ]

            for selector in feature_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        login_score += 2
                        break
                except:
                    continue

            # 5. 检查是否在登录页面
            login_page_indicators = [
                'button:has-text("登录")',
                'button:has-text("立即登录")',
                'button:has-text("微信登录")',
                'button:has-text("QQ登录")',
                'input[type="password"]',
                '[class*="login-form"]'
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
            # 检查是否有处理中的提示
            processing_indicators = [
                "[class*='yb-'][class*='processing']",
                "text*='正在处理'",
                "[class*='loading']"
            ]

            for selector in processing_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        logger.info("检测到处理中提示，等待...")
                        await asyncio.sleep(3)
                        break
                except:
                    continue

            # 尝试点击新建对话按钮
            new_chat_selectors = [
                'span.yb-icon.iconfont-yb.icon-yb-ic_newchat_20',
                'div.yb-common-nav__trigger[data-desc="fold"] span.icon-yb-ic_newchat_20',
                'span:has-text("$0")',
                '[class*="newchat"]',
                '[class*="new-chat"]',
                'button:has-text("新对话")',
                'button:has-text("新建")',
                'div.yb-common-nav__trigger',
                '[class*="create-chat"]'
            ]

            for selector in new_chat_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        is_clickable = await element.evaluate("""
                            (el) => {
                                const style = window.getComputedStyle(el);
                                return !el.disabled && 
                                       style.pointerEvents !== 'none' &&
                                       style.cursor === 'pointer';
                            }
                        """)

                        if is_clickable:
                            await element.click()
                            await asyncio.sleep(2)
                            logger.info("成功点击新建对话按钮")
                            return True
                except:
                    continue

            # 使用JavaScript点击
            try:
                result = await page.evaluate("""
                    () => {
                        const selectors = [
                            '.icon-yb-ic_newchat_20',
                            '[class*="newchat"]',
                            'span[class*="newchat"]'
                        ];
                        
                        for (const selector of selectors) {
                            const element = document.querySelector(selector);
                            if (element) {
                                let clickable = element;
                                while (clickable && clickable.tagName !== 'BUTTON' && clickable.tagName !== 'DIV') {
                                    clickable = clickable.parentElement;
                                }
                                if (clickable) {
                                    clickable.click();
                                    return true;
                                }
                            }
                        }
                        
                        return false;
                    }
                """)

                if result:
                    await asyncio.sleep(2)
                    logger.info("通过JavaScript成功点击新建对话")
                    return True

            except Exception as e:
                logger.debug(f"JavaScript点击失败: {str(e)}")

            # 如果都失败了，刷新页面
            logger.warning("无法创建新对话，尝试刷新页面")
            await page.reload()
            await asyncio.sleep(3)
            return True

        except Exception as e:
            logger.error(f"创建新对话失败: {str(e)}")
            return False

    def get_input_selectors(self) -> List[str]:
        """获取输入框选择器"""
        return [
            'textarea',
            'div[contenteditable="true"]',
            '[class*="input"][class*="area"]',
            '[class*="yb-"][class*="input"]',
            'div.yb-chat-input',
            '[class*="chat-input"]',
            '[class*="message-input"]'
        ]

    def get_send_button_selectors(self) -> List[str]:
        """获取发送按钮选择器"""
        return [
            'button[aria-label*="发送"]',
            'button:has-text("发送")',
            'button[type="submit"]',
            '[class*="send-btn"]',
            '[class*="yb-send"]',
            '[class*="submit-button"]',
            'button.yb-button'
        ]

    def get_response_selectors(self) -> List[str]:
        """获取响应内容选择器"""
        return [
            # 元宝新的响应结构
            "div.hyc-component-reasoner__text",
            "div.hyc-component-reasoner__think-content",
            "div.hyc-common-markdown",
            "div.hyc-common-markdown-style",
            # 原有选择器
            "[class*='markdown']",
            "[class*='message-content']",
            "[class*='assistant']",
            # 元宝特定的响应容器
            "[class*='yb-message']",
            "[class*='yb-response']",
            "[class*='yb-chat-message']",
            "div[class*='assistant'][class*='message']",
            "[class*='bot-message']",
            "[class*='ai-response']",
            "div.yb-chat-content"
        ]

    async def wait_for_response_complete(self, page: Page) -> bool:
        """等待响应完全结束"""
        try:
            # 元宝特定的加载/处理指示器
            processing_indicators = [
                "[class*='yb-'][class*='loading']",
                "[class*='yb-'][class*='processing']",
                "text*='正在处理'",
                "text*='生成中'",
                "[class*='generating']",
                "[class*='yb-message-streaming']"
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

            # 特别检查元宝的"已深度思考"标志
            try:
                think_done = await page.wait_for_selector(
                    "div.hyc-component-reasoner__think-header__content:has-text('已深度思考')",
                    timeout=5000
                )
                if think_done:
                    logger.info("检测到'已深度思考'，响应即将完成")
                    await asyncio.sleep(2)
            except:
                pass

            # 检查是否有"done"标志
            try:
                done_indicator = await page.query_selector("div.hyc-content-md-done")
                if done_indicator:
                    logger.info("检测到响应完成标志")
                    await asyncio.sleep(1)
            except:
                pass

            # 检查停止按钮是否消失
            stop_button_selectors = [
                "span.yb-icon",
                "div.yb-button",
                "[class*='yb-'][class*='stop']",
                "button:has(svg.yb-icon)",
                "[class*='stop-generation']"
            ]

            for _ in range(10):  # 最多检查10次
                stop_button_found = False
                for selector in stop_button_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            if await element.is_visible():
                                # 检查是否是停止按钮
                                has_stop_class = await element.evaluate("""
                                    (el) => {
                                        return el.className.includes('stop') || 
                                               el.getAttribute('aria-label')?.includes('停止');
                                    }
                                """)
                                if has_stop_class:
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
        """等待并获取响应 - 元宝特定实现"""
        if timeout is None:
            timeout = self.response_timeout

        # 先等待一下让响应开始生成
        await asyncio.sleep(3)

        # 等待响应完成
        await self.wait_for_response_complete(page)

        # 调用基类方法获取响应
        return await super().wait_for_response(page, timeout)

    async def ensure_logged_in(self, page: Page) -> bool:
        """确保已登录 - 元宝特定实现"""
        if await self.check_login_status(page):
            return True

        # 如果未登录，需要手动处理
        logger.error("元宝未登录，Web适配器暂不支持自动登录")
        logger.info("请先通过浏览器手动登录元宝，并保存登录状态")

        # 可以考虑实现等待手动登录的逻辑
        # 但在生产环境中，应该预先保存好登录状态
        return False