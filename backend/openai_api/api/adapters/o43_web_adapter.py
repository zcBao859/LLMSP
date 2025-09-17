"""
O4.3 (GPT-4o) Web适配器 - 通过网页爬取实现 GPT-4o 接口
"""
import asyncio
import logging
import random
from typing import List, Dict, Any, Optional
from playwright.async_api import Page

from .web_adapter_base import WebAdapterBase

logger = logging.getLogger(__name__)


class O43WebAdapter(WebAdapterBase):
    """O4.3 (GPT-4o) Web适配器"""

    def __init__(self, config: Dict[str, Any]):
        # 设置默认配置
        config.setdefault("platform_name", "o43_web")
        config.setdefault("base_url", "https://share.mosha.cloud/")

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
        """检查 O4.3 平台是否已登录"""
        try:
            login_score = 0

            # 1. 检查新建对话按钮
            new_chat_selectors = [
                '[data-testid="create-new-chat-button"]',
                'a[href="/"][data-testid="create-new-chat-button"]',
                'a:has-text("新聊天")',
                '.__menu-item:has-text("新聊天")',
                '.group.__menu-item'
            ]

            for selector in new_chat_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element and await element.is_visible():
                        login_score += 2
                        break
                except:
                    continue

            # 2. 检查输入框
            input_selectors = [
                'textarea',
                'textarea[placeholder*="消息"]',
                'textarea[data-testid*="composer"]',
                '#composer-textarea',
                'div[contenteditable="true"]'
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
                            login_score += 3
                            break
                except:
                    continue

            # 3. 检查发送按钮
            send_selectors = [
                '#composer-submit-button',
                'button[data-testid="send-button"]',
                'button[aria-label*="发送"]'
            ]

            for selector in send_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        login_score += 1
                        break
                except:
                    continue

            # 4. 检查聊天历史
            history_selectors = [
                '[class*="conversation-item"]',
                '[class*="chat-item"]',
                'nav a[href*="/c/"]',
                '.flex.items-center.gap-2.rounded-xl'
            ]

            for selector in history_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements and len(elements) > 0:
                        login_score += 2
                        break
                except:
                    continue

            # 5. 检查是否在登录页面
            login_page_indicators = [
                'button:has-text("登录")',
                'button:has-text("Sign in")',
                'input[type="password"]',
                '[class*="login-form"]',
                'h1:has-text("登录")'
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

            # O4.3 的新建对话选择器
            new_chat_selectors = [
                '[data-testid="create-new-chat-button"]',
                'a[href="/"][data-testid="create-new-chat-button"]',
                'a.__menu-item:has-text("新聊天")',
                'a.group.__menu-item[href="/"]',
                'a:has-text("新聊天")',
                'a[href="/"]:has(svg)',
                'button:has-text("新对话")'
            ]

            for selector in new_chat_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element and await element.is_visible():
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
                        const newChatBtn = document.querySelector('[data-testid="create-new-chat-button"]');
                        if (newChatBtn) {
                            newChatBtn.click();
                            return true;
                        }

                        const links = document.querySelectorAll('a');
                        for (const link of links) {
                            if (link.textContent && link.textContent.includes('新聊天')) {
                                link.click();
                                return true;
                            }
                        }

                        const homeLink = document.querySelector('a[href="/"]');
                        if (homeLink) {
                            homeLink.click();
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

            # 最后的备选方案：导航到根路径
            logger.warning("无法找到新建对话按钮，继续使用当前对话")
            return True

        except Exception as e:
            logger.error(f"创建新对话失败: {str(e)}")
            return False

    def get_input_selectors(self) -> List[str]:
        """获取输入框选择器"""
        return [
            'textarea',
            'textarea[placeholder*="消息"]',
            'textarea[data-testid*="composer"]',
            '#composer-textarea',
            'div[contenteditable="true"]',
            'textarea[class*="w-full"]',
            'textarea[class*="resize-none"]'
        ]

    def get_send_button_selectors(self) -> List[str]:
        """获取发送按钮选择器"""
        return [
            '#composer-submit-button',
            'button[data-testid="send-button"]',
            'button[aria-label*="发送"]',
            'button[type="submit"]',
            'button.h-9.w-9',
            'button.rounded-full:has(svg)'
        ]

    def get_response_selectors(self) -> List[str]:
        """获取响应内容选择器"""
        return [
            # O4.3 特定的响应选择器
            '.markdown.prose',
            '.markdown.prose.dark\\:prose-invert',
            'div.markdown.prose.w-full.break-words',
            '.flex.w-full.flex-col .markdown',
            '.markdown p',
            '.markdown ol',
            '.markdown ul',
            '.markdown h1, .markdown h2, .markdown h3',
            # 通用选择器
            '[class*="markdown"]',
            '[class*="prose"]',
            '[class*="message-content"]',
            '[class*="assistant-message"]',
            'div.message',
            'div.response'
        ]

    async def wait_for_response_complete(self, page: Page) -> bool:
        """等待响应完全结束"""
        try:
            # O4.3 特定的停止按钮检查
            stop_button_selectors = [
                '#composer-submit-button[aria-label="停止流式传输"]',
                '[data-testid="stop-button"]',
                'button[aria-label="停止流式传输"]',
                'button:has(svg rect[rx="1.25"])',
                'button svg rect[x="7"][y="7"]'
            ]

            # 等待停止按钮消失
            for selector in stop_button_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        logger.info("检测到停止按钮，等待响应完成...")
                        await page.wait_for_selector(selector, state="hidden", timeout=30000)
                        await asyncio.sleep(1)
                        break
                except:
                    continue

            # 检查响应完成标志
            completion_indicators = [
                '.markdown.prose:not(:empty)',
                'button:has-text("复制")',
                'button:has-text("重新生成")',
                '[class*="message-actions"]',
                '[class*="feedback"]'
            ]

            for indicator in completion_indicators:
                try:
                    element = await page.query_selector(indicator)
                    if element:
                        logger.debug(f"检测到完成标志: {indicator}")
                        break
                except:
                    continue

            # 额外等待确保响应稳定
            await asyncio.sleep(2)
            return True

        except Exception as e:
            logger.error(f"等待响应完成时出错: {str(e)}")
            return False

    async def wait_for_response(self, page: Page, timeout: int = None) -> Optional[str]:
        """等待并获取响应 - O4.3 特定实现"""
        if timeout is None:
            timeout = self.response_timeout

        # 先等待一下让响应开始生成
        await asyncio.sleep(3)

        # 等待响应完成
        await self.wait_for_response_complete(page)

        # 调用基类方法获取响应
        return await super().wait_for_response(page, timeout)

    async def get_current_response(self, page: Page) -> Optional[str]:
        """获取当前页面上的响应内容 - O4.3 特定实现"""
        try:
            # O4.3 特定的选择器
            o43_selectors = [
                '.markdown.prose',
                'div.markdown.prose.w-full.break-words',
                '.flex.w-full.flex-col .markdown'
            ]

            for selector in o43_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        # 获取最后一个元素（最新的响应）
                        last_element = elements[-1]

                        # 使用 JavaScript 获取完整的文本内容
                        text = await last_element.evaluate("""
                            (el) => {
                                const getText = (node) => {
                                    let text = '';

                                    if (node.nodeType === Node.TEXT_NODE) {
                                        return node.textContent;
                                    }

                                    for (const child of node.childNodes) {
                                        const childText = getText(child);
                                        text += childText;
                                    }

                                    const tagName = node.tagName;
                                    if (tagName === 'P' || tagName === 'DIV' || 
                                        tagName === 'H1' || tagName === 'H2' || 
                                        tagName === 'H3' || tagName === 'H4' || 
                                        tagName === 'H5' || tagName === 'H6') {
                                        text += '\\n\\n';
                                    } else if (tagName === 'BR') {
                                        text += '\\n';
                                    } else if (tagName === 'LI') {
                                        text = '• ' + text + '\\n';
                                    }

                                    return text;
                                };

                                return getText(el).trim();
                            }
                        """)

                        if text and text.strip():
                            return text.strip()
                except:
                    continue

            # 如果特定选择器失败，使用基类方法
            return await super().get_current_response(page)

        except Exception as e:
            logger.error(f"获取响应失败: {str(e)}")
            return None

    async def ensure_logged_in(self, page: Page) -> bool:
        """确保已登录 - O4.3 特定实现"""
        if await self.check_login_status(page):
            return True

        logger.error("O4.3 未登录，Web适配器暂不支持自动登录")
        logger.info("请先通过浏览器手动登录 O4.3，并保存登录状态")
        return False