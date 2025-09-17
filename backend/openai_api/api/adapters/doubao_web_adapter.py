"""
豆包Web适配器 - 严格会话隔离完整实现

本模块基于会话管理理论(Session Management Theory)和浏览器自动化最佳实践，
实现了具有严格会话隔离能力的豆包平台适配器。
"""
import asyncio
import logging
import random
from typing import List, Dict, Any, Optional
from datetime import datetime
from playwright.async_api import Page

from .web_adapter_base import WebAdapterBase
from ..web_model_config import WebModelTestConfig, SessionIsolationMode

logger = logging.getLogger(__name__)


class DoubaoWebAdapter(WebAdapterBase):
    """豆包Web适配器 - 严格会话隔离版本"""

    def __init__(self, config: Dict[str, Any]):
        # 设置默认配置
        config.setdefault("platform_name", "doubao_web")
        config.setdefault("base_url", "https://www.doubao.com/chat")

        # 获取Web模型特定配置
        web_config = WebModelTestConfig.get_web_model_config("doubao_web")

        # 合并配置（传入配置优先）
        for key, value in web_config.items():
            config.setdefault(key, value)

        # 浏览器配置
        default_browser_config = {
            "headless": True,
            "timeout": 30000,
            "slow_mo": 1000,  # 减慢操作速度，更像人类行为
        }
        config.setdefault("browser_config", default_browser_config)

        super().__init__(config)

        # 会话管理 - 豆包特定状态
        self._last_request_time = 0
        self._request_count = 0
        self._conversation_count = 0
        self._last_conversation_id = None
        self._validation_wait_times = []  # 记录验证等待时间用于优化

    async def check_login_status(self, page: Page) -> bool:
        """检查豆包平台是否已登录 - 多策略验证"""
        try:
            login_score = 0

            # 策略1: 检查新建对话按钮
            new_chat_selectors = [
                'div[data-testid="create_conversation_button"]',
                'div.thread-creation-CThjxH',
                '[class*="thread-creation"]',
            ]

            for selector in new_chat_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        is_disabled = await element.evaluate('el => el.getAttribute("data-disabled") === "true"')
                        if not is_disabled:
                            login_score += 2
                            logger.debug(f"找到可用的新建对话按钮: {selector}")
                            break
                except:
                    continue

            # 策略2: 检查输入框
            input_selectors = [
                'textarea.semi-input',
                'textarea[placeholder*="输入"]',
                'div[contenteditable="true"]',
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
                            login_score += 3
                            logger.debug(f"找到可编辑的输入框: {selector}")
                            break
                except:
                    continue

            # 策略3: 检查用户头像或个人信息
            user_indicators = [
                '[class*="avatar"]',
                '[class*="user-info"]',
                '[data-testid*="user"]',
            ]

            for selector in user_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        login_score += 1
                        logger.debug(f"找到用户信息元素: {selector}")
                        break
                except:
                    continue

            # 策略4: 反向检查 - 确保不在登录页面
            login_page_indicators = [
                'button:has-text("登录")',
                'input[type="password"]',
                '[class*="login-form"]',
                'text*="验证码"',
            ]

            for selector in login_page_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        logger.info("检测到登录页面元素，判定为未登录")
                        return False
                except:
                    continue

            # 综合评分判定
            is_logged_in = login_score >= 4  # 提高阈值以确保准确性
            logger.info(f"登录检测综合得分: {login_score}/6, 判定为{'已登录' if is_logged_in else '未登录'}")

            return is_logged_in

        except Exception as e:
            logger.error(f"检查登录状态失败: {str(e)}")
            return False

    async def has_active_conversation(self, page: Page) -> bool:
        """检查是否有活跃的对话 - 豆包特定实现"""
        try:
            # 多维度检查策略

            # 策略1: 检查消息容器
            message_selectors = [
                'div[data-testid="message_text_content"]',
                'div.flow-markdown-body',
                '[class*="message"][class*="content"]',
                'div.container-ZYIsnH'
            ]

            total_messages = 0
            user_messages = 0
            assistant_messages = 0

            for selector in message_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    total_messages += len(elements)

                    # 尝试区分用户和助手消息
                    for element in elements:
                        try:
                            # 检查父元素或自身的类名/属性
                            is_user = await element.evaluate("""
                                (el) => {
                                    const classStr = (el.className || '') + (el.parentElement?.className || '');
                                    return classStr.includes('user') || 
                                           classStr.includes('human') ||
                                           el.closest('[data-role="user"]') !== null;
                                }
                            """)
                            if is_user:
                                user_messages += 1
                            else:
                                assistant_messages += 1
                        except:
                            pass

            # 策略2: 检查对话标题或ID
            has_conversation_title = False
            try:
                title_selectors = [
                    '[class*="conversation-title"]',
                    '[class*="chat-title"]',
                    '[data-testid*="title"]'
                ]
                for selector in title_selectors:
                    element = await page.query_selector(selector)
                    if element:
                        text = await element.text_content()
                        if text and text.strip() and text.strip() != "新对话":
                            has_conversation_title = True
                            break
            except:
                pass

            # 综合判断
            # 豆包通常有1条系统欢迎消息，所以 >1 表示有实际对话
            has_real_conversation = (
                total_messages > 1 or
                user_messages > 0 or
                has_conversation_title
            )

            if has_real_conversation:
                logger.debug(f"检测到活跃对话: 总消息={total_messages}, "
                          f"用户消息={user_messages}, 助手消息={assistant_messages}, "
                          f"有标题={has_conversation_title}")

            return has_real_conversation

        except Exception as e:
            logger.debug(f"检查活跃对话时出错: {str(e)}")
            return False

    async def get_current_session_id(self, page: Page) -> Optional[str]:
        """获取当前会话ID - 豆包特定实现"""
        try:
            # 方法1: 从URL提取
            current_url = await page.evaluate('() => window.location.href')
            if '/chat/' in current_url:
                parts = current_url.split('/chat/')
                if len(parts) > 1:
                    # 提取路径中的ID部分
                    path_parts = parts[1].split('/')
                    conversation_id = path_parts[0].split('?')[0]
                    if conversation_id and len(conversation_id) > 10:  # 基本验证
                        logger.debug(f"从URL提取到会话ID: {conversation_id}")
                        return conversation_id

            # 方法2: 从DOM元素提取
            id_selectors = [
                '[data-conversation-id]',
                '[data-chat-id]',
                '[class*="conversation"][id]'
            ]

            for selector in id_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        # 尝试获取data属性
                        conv_id = await element.get_attribute('data-conversation-id')
                        if not conv_id:
                            conv_id = await element.get_attribute('data-chat-id')
                        if not conv_id:
                            conv_id = await element.get_attribute('id')

                        if conv_id and len(conv_id) > 10:
                            logger.debug(f"从DOM元素提取到会话ID: {conv_id}")
                            return conv_id
                except:
                    continue

            # 方法3: 从JavaScript全局变量提取
            try:
                conv_id = await page.evaluate("""
                    () => {
                        // 尝试常见的全局变量名
                        return window.conversationId || 
                               window.chatId || 
                               window.__CONVERSATION_ID__ ||
                               (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.conversationId);
                    }
                """)
                if conv_id and len(str(conv_id)) > 10:
                    logger.debug(f"从JavaScript变量提取到会话ID: {conv_id}")
                    return str(conv_id)
            except:
                pass

        except Exception as e:
            logger.debug(f"获取会话ID失败: {str(e)}")

        return None

    async def create_new_chat(self, page: Page) -> bool:
        """创建新对话 - 豆包优化实现"""
        try:
            # 记录当前会话ID
            old_session_id = await self.get_current_session_id(page)

            # 增加对话计数
            self._conversation_count += 1
            logger.info(f"[豆包] 准备创建第 {self._conversation_count} 个新对话")

            # 检查并等待任何进行中的验证
            await self._wait_for_validation(page)

            # 尝试多种新建对话的方法
            success = False

            # 方法1: 标准按钮点击
            success = await self._try_new_chat_button(page)

            # 方法2: 使用快捷键
            if not success:
                success = await self._try_new_chat_shortcut(page)

            # 方法3: URL导航
            if not success:
                success = await self._try_new_chat_navigation(page)

            # 方法4: JavaScript强制创建
            if not success:
                success = await self._try_force_new_chat(page)

            if success:
                # 等待新会话加载
                await asyncio.sleep(self.new_chat_cooldown)

                # 验证新会话创建成功
                new_session_id = await self.get_current_session_id(page)

                # 多重验证策略
                verification_passed = False

                # 验证1: 会话ID变化
                if old_session_id and new_session_id and old_session_id != new_session_id:
                    logger.info(f"[豆包] 会话ID已变化: {old_session_id[:8]}... -> {new_session_id[:8]}...")
                    verification_passed = True

                # 验证2: 无消息历史
                elif not await self.has_active_conversation(page):
                    logger.info("[豆包] 检测到空白会话，新建成功")
                    verification_passed = True

                # 验证3: 输入框可用且清空
                elif await self._verify_clean_input_state(page):
                    logger.info("[豆包] 输入框状态正常，新建成功")
                    verification_passed = True

                if verification_passed:
                    self._last_conversation_id = new_session_id
                    return True
                else:
                    logger.warning("[豆包] 新对话创建验证失败")

            return False

        except Exception as e:
            logger.error(f"[豆包] 创建新对话失败: {str(e)}")
            return False

    async def _wait_for_validation(self, page: Page):
        """等待豆包特定的验证完成"""
        try:
            start_time = asyncio.get_event_loop().time()

            validation_selectors = [
                "text*='回在验证中'",
                "text*='正在验证'",
                "text*='验证中'",
                "text*='处理中'",
                "[class*='validating']",
                "[class*='processing']"
            ]

            for selector in validation_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        logger.info(f"[豆包] 检测到验证提示: {selector}")
                        try:
                            await page.wait_for_selector(selector, state="hidden", timeout=15000)
                            wait_time = asyncio.get_event_loop().time() - start_time
                            self._validation_wait_times.append(wait_time)
                            logger.info(f"[豆包] 验证完成，耗时: {wait_time:.1f}秒")
                        except:
                            logger.warning("[豆包] 验证等待超时")

                        # 额外等待确保稳定
                        await asyncio.sleep(1)
                        break
                except:
                    continue

        except Exception as e:
            logger.debug(f"[豆包] 等待验证时出错: {str(e)}")

    async def _try_new_chat_button(self, page: Page) -> bool:
        """尝试点击新建对话按钮 - 豆包优化版"""
        new_chat_selectors = [
            # 豆包特定选择器（按优先级排序）
            'div[data-testid="create_conversation_button"]:not([data-disabled="true"])',
            'div.thread-creation-CThjxH:not([data-disabled="true"])',
            'div[class*="thread-creation"]:not([data-disabled="true"])',
            'div:has-text("新对话"):not([data-disabled="true"])',
            'button:has-text("新对话")',
            'button[aria-label*="新对话"]',
            '[class*="new-chat"]',
            '[class*="create-chat"]'
        ]

        for selector in new_chat_selectors:
            try:
                # 使用较短的超时以快速尝试多个选择器
                element = await page.wait_for_selector(selector, timeout=1500)
                if element:
                    # 多重检查确保元素可点击
                    is_visible = await element.is_visible()
                    is_enabled = await element.is_enabled()

                    # 豆包特定：检查data-disabled属性
                    is_not_disabled = await element.evaluate("""
                        (el) => {
                            const disabled = el.getAttribute('data-disabled');
                            return disabled !== 'true' && disabled !== true;
                        }
                    """)

                    if is_visible and is_enabled and is_not_disabled:
                        # 确保元素在视口内
                        await element.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)

                        # 尝试多种点击方式
                        try:
                            await element.click()
                        except:
                            # 备用：JavaScript点击
                            await page.evaluate('(el) => el.click()', element)

                        logger.info(f"[豆包] 成功点击新建对话按钮: {selector}")
                        return True

            except Exception as e:
                logger.debug(f"[豆包] 尝试选择器 {selector} 失败: {str(e)}")
                continue

        return False

    async def _try_new_chat_shortcut(self, page: Page) -> bool:
        """尝试使用快捷键创建新对话"""
        try:
            # 聚焦到页面主体
            await page.click('body')
            await asyncio.sleep(0.2)

            # 豆包可能支持的快捷键组合
            shortcuts = [
                'Control+Shift+n',
                'Control+n',
                'Alt+n',
                'Control+Shift+o',  # 豆包可能的特定快捷键
            ]

            for shortcut in shortcuts:
                logger.debug(f"[豆包] 尝试快捷键: {shortcut}")
                await page.keyboard.press(shortcut)
                await asyncio.sleep(1.5)

                # 检查是否创建了新对话
                if not await self.has_active_conversation(page):
                    logger.info(f"[豆包] 使用快捷键 {shortcut} 创建新对话成功")
                    return True

        except Exception as e:
            logger.debug(f"[豆包] 快捷键方法失败: {str(e)}")

        return False

    async def _try_new_chat_navigation(self, page: Page) -> bool:
        """尝试通过URL导航创建新对话"""
        try:
            # 豆包的新对话URL模式
            new_chat_urls = [
                self.base_url,
                f"{self.base_url}/new",
                f"{self.base_url}?new=true",
            ]

            for url in new_chat_urls:
                logger.debug(f"[豆包] 尝试导航到: {url}")
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # 等待页面加载并检查
                await self.wait_for_page_stable(page)

                if not await self.has_active_conversation(page):
                    logger.info(f"[豆包] 通过URL导航创建新对话成功: {url}")
                    return True

        except Exception as e:
            logger.debug(f"[豆包] URL导航方法失败: {str(e)}")

        return False

    async def _try_force_new_chat(self, page: Page) -> bool:
        """尝试通过JavaScript强制创建新对话"""
        try:
            # 尝试调用豆包的内部API或方法
            result = await page.evaluate("""
                async () => {
                    try {
                        // 方法1: 查找并触发React组件
                        const buttons = document.querySelectorAll('div[data-testid="create_conversation_button"]');
                        for (const button of buttons) {
                            const reactKey = Object.keys(button).find(key => key.startsWith('__react'));
                            if (reactKey && button[reactKey]) {
                                const props = button[reactKey].memoizedProps || button[reactKey].pendingProps;
                                if (props && props.onClick) {
                                    props.onClick();
                                    return true;
                                }
                            }
                        }
                        
                        // 方法2: 触发自定义事件
                        const event = new CustomEvent('create-new-chat', { bubbles: true });
                        document.dispatchEvent(event);
                        
                        // 方法3: 查找全局函数
                        if (window.createNewChat) {
                            window.createNewChat();
                            return true;
                        }
                        
                        return false;
                    } catch (e) {
                        console.error('Force new chat error:', e);
                        return false;
                    }
                }
            """)

            if result:
                logger.info("[豆包] 通过JavaScript强制创建新对话成功")
                return True

        except Exception as e:
            logger.debug(f"[豆包] JavaScript强制方法失败: {str(e)}")

        return False

    async def _verify_clean_input_state(self, page: Page) -> bool:
        """验证输入框是否处于干净状态"""
        try:
            input_selectors = self.get_input_selectors()

            for selector in input_selectors:
                try:
                    input_box = await page.wait_for_selector(selector, timeout=1000)
                    if input_box:
                        # 检查输入框内容
                        content = await input_box.evaluate("""
                            (el) => {
                                if (el.value !== undefined) return el.value;
                                if (el.textContent !== undefined) return el.textContent;
                                return el.innerText || '';
                            }
                        """)

                        # 检查是否可编辑
                        is_editable = await input_box.is_editable()

                        # 输入框应该是空的且可编辑
                        return is_editable and (not content or content.strip() == '')
                except:
                    continue

        except Exception as e:
            logger.debug(f"[豆包] 验证输入状态失败: {str(e)}")

        return False

    async def send_message_to_page(self, page: Page, message: str) -> bool:
        """发送消息到页面 - 豆包优化版"""
        try:
            # 频率控制
            import time
            current_time = time.time()
            if self._last_request_time > 0:
                time_since_last = current_time - self._last_request_time
                if time_since_last < 3:
                    wait_time = 3 - time_since_last + random.uniform(0.5, 1.5)
                    logger.info(f"[豆包] 频率控制，等待 {wait_time:.1f} 秒")
                    await asyncio.sleep(wait_time)

            self._last_request_time = current_time
            self._request_count += 1

            # 查找并准备输入框
            input_box = await self._find_and_prepare_input(page)
            if not input_box:
                raise Exception("无法找到或准备输入框")

            # 输入消息
            success = await self._input_message(page, input_box, message)
            if not success:
                raise Exception("消息输入失败")

            # 发送消息
            send_success = await self._send_message(page, input_box)

            if send_success:
                logger.info(f"[豆包] 消息发送成功 (长度: {len(message)})")
            else:
                logger.error("[豆包] 消息发送失败")

            return send_success

        except Exception as e:
            logger.error(f"[豆包] 发送消息失败: {str(e)}")
            return False

    async def _find_and_prepare_input(self, page: Page) -> Any:
        """查找并准备输入框"""
        input_selectors = self.get_input_selectors()

        for selector in input_selectors:
            try:
                input_box = await page.wait_for_selector(selector, timeout=3000)
                if input_box:
                    # 确保输入框可见且可编辑
                    is_visible = await input_box.is_visible()
                    is_editable = await input_box.is_editable()

                    if is_visible and is_editable:
                        # 滚动到视图并聚焦
                        await input_box.scroll_into_view_if_needed()
                        await input_box.click()
                        await asyncio.sleep(0.2)

                        # 清空输入框
                        await input_box.fill("")

                        return input_box
            except:
                continue

        return None

    async def _input_message(self, page: Page, input_box, message: str) -> bool:
        """输入消息内容 - 支持长消息"""
        try:
            message_length = len(message)
            logger.info(f"[豆包] 准备输入消息，长度: {message_length} 字符")

            if message_length > 100:
                # 长消息处理策略
                logger.info("[豆包] 检测到长消息，使用优化输入策略")

                # 策略1: 直接填充
                await input_box.fill(message)
                await asyncio.sleep(0.5)

                # 验证输入完整性
                actual_content = await input_box.evaluate("""
                    (el) => el.value || el.textContent || el.innerText || ''
                """)

                if len(actual_content) < message_length * 0.95:
                    logger.warning(f"[豆包] 输入可能不完整: 期望 {message_length}，实际 {len(actual_content)}")

                    # 策略2: 分块输入
                    await input_box.fill("")
                    chunk_size = 500

                    for i in range(0, message_length, chunk_size):
                        chunk = message[i:i + chunk_size]
                        await input_box.type(chunk, delay=10)

                        # 每块之间短暂暂停
                        if i + chunk_size < message_length:
                            await asyncio.sleep(0.1)

                    # 再次验证
                    await asyncio.sleep(0.5)
                    actual_content = await input_box.evaluate("""
                        (el) => el.value || el.textContent || el.innerText || ''
                    """)
                    logger.info(f"[豆包] 分块输入后长度: {len(actual_content)}")

            else:
                # 短消息模拟人类输入
                await input_box.type(message, delay=random.randint(30, 80))

            # 最终验证
            await asyncio.sleep(0.3)
            final_content = await input_box.evaluate("""
                (el) => el.value || el.textContent || el.innerText || ''
            """)

            if len(final_content.strip()) < len(message) * 0.9:
                logger.error(f"[豆包] 输入验证失败: 期望 {len(message)}，实际 {len(final_content)}")
                return False

            return True

        except Exception as e:
            logger.error(f"[豆包] 输入消息时出错: {str(e)}")
            return False

    async def _send_message(self, page: Page, input_box) -> bool:
        """发送消息 - 多策略尝试"""
        try:
            # 策略1: 尝试点击发送按钮（优先）
            send_selectors = self.get_send_button_selectors()

            for selector in send_selectors:
                try:
                    send_btn = await page.wait_for_selector(selector, timeout=1000)
                    if send_btn and await send_btn.is_visible():
                        await send_btn.click()
                        logger.info(f"[豆包] 通过发送按钮发送: {selector}")
                        return True
                except:
                    continue

            # 策略2: 使用回车键
            try:
                # 确保焦点在输入框
                await input_box.focus()
                await page.keyboard.press("Enter")
                logger.info("[豆包] 通过回车键发送")
                return True
            except Exception as e:
                logger.debug(f"[豆包] 回车键发送失败: {str(e)}")

            # 策略3: Shift+Enter（某些情况下需要）
            try:
                await page.keyboard.press("Shift+Enter")
                logger.info("[豆包] 通过Shift+Enter发送")
                return True
            except:
                pass

            return False

        except Exception as e:
            logger.error(f"[豆包] 发送消息时出错: {str(e)}")
            return False

    async def wait_for_response_complete(self, page: Page) -> bool:
        """等待响应完全结束 - 豆包增强版"""
        try:
            logger.info("[豆包] 开始等待响应完成")

            # 阶段1: 等待响应开始
            await self._wait_for_response_start(page)

            # 阶段2: 等待处理指示器消失
            await self._wait_for_processing_complete(page)

            # 阶段3: 等待停止按钮消失
            await self._wait_for_stop_button_disappear(page)

            # 阶段4: 验证内容稳定
            stable = await self._verify_content_stable(page)

            if stable:
                logger.info("[豆包] 响应已完成并稳定")
            else:
                logger.warning("[豆包] 响应可能未完全稳定")

            return stable

        except Exception as e:
            logger.error(f"[豆包] 等待响应完成时出错: {str(e)}")
            return False

    async def _wait_for_response_start(self, page: Page):
        """等待响应开始生成"""
        try:
            # 等待响应容器出现或更新
            response_started = False
            max_wait = 10  # 最多等待10秒

            for i in range(max_wait):
                if await self._check_response_started(page):
                    response_started = True
                    logger.info(f"[豆包] 检测到响应开始生成 ({i+1}秒)")
                    break
                await asyncio.sleep(1)

            if not response_started:
                logger.warning("[豆包] 未检测到响应开始")

        except Exception as e:
            logger.debug(f"[豆包] 等待响应开始时出错: {str(e)}")

    async def _check_response_started(self, page: Page) -> bool:
        """检查响应是否开始生成"""
        try:
            # 检查是否有新的助手消息
            response_selectors = self.get_response_selectors()

            for selector in response_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    # 获取最后一个元素
                    last_element = elements[-1]
                    text = await last_element.text_content()

                    # 检查是否有内容且不是空白
                    if text and text.strip() and len(text.strip()) > 10:
                        return True

            # 检查是否有加载指示器
            loading_indicators = [
                "[class*='loading']",
                "[class*='streaming']",
                "[class*='generating']",
                "text*='正在输入'",
                "text*='正在回复'",
            ]

            for indicator in loading_indicators:
                element = await page.query_selector(indicator)
                if element and await element.is_visible():
                    return True

        except:
            pass

        return False

    async def _wait_for_processing_complete(self, page: Page):
        """等待处理指示器消失"""
        processing_indicators = [
            "text*='回在验证中'",
            "text*='正在生成'",
            "text*='思考中'",
            "text*='处理中'",
            "text*='请稍候'",
            "[class*='loading']",
            "[class*='streaming']",
            "[class*='processing']",
            "[class*='thinking']"
        ]

        for selector in processing_indicators:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    logger.info(f"[豆包] 等待处理指示器消失: {selector}")
                    try:
                        await page.wait_for_selector(selector, state="hidden", timeout=20000)
                    except:
                        logger.warning(f"[豆包] 处理指示器等待超时: {selector}")
                    await asyncio.sleep(0.5)
            except:
                continue

    async def _wait_for_stop_button_disappear(self, page: Page):
        """等待停止按钮消失 - 豆包优化版"""
        stop_button_selectors = [
            # 豆包特定的停止按钮选择器
            "button:has(svg[viewBox='0 0 24 24'] rect[rx='1.5'])",
            "button.semi-button:has(svg path[d*='M6 6'])",
            "[class*='stop-generate']",
            "[class*='stop-button']",
            "[aria-label*='停止']",
            "button:has-text('停止')"
        ]

        max_checks = 30  # 最多检查30次（30秒）
        found_count = 0

        for check in range(max_checks):
            stop_button_found = False

            for selector in stop_button_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        if await element.is_visible():
                            # 豆包特定的停止按钮验证
                            is_stop_button = await element.evaluate("""
                                (el) => {
                                    // 检查文本
                                    const text = el.textContent || '';
                                    if (text.includes('停止')) return true;
                                    
                                    // 检查SVG特征（豆包的停止图标）
                                    const svg = el.querySelector('svg');
                                    if (svg) {
                                        // 方形停止图标
                                        const rect = svg.querySelector('rect[rx="1.5"]');
                                        if (rect) return true;
                                        
                                        // 路径停止图标
                                        const path = svg.querySelector('path');
                                        if (path) {
                                            const d = path.getAttribute('d') || '';
                                            if (d.includes('M6 6') || d.includes('square')) {
                                                return true;
                                            }
                                        }
                                    }
                                    
                                    // 检查类名
                                    const className = el.className || '';
                                    if (className.includes('stop')) return true;
                                    
                                    return false;
                                }
                            """)

                            if is_stop_button:
                                stop_button_found = True
                                found_count += 1
                                if found_count % 5 == 0:
                                    logger.debug(f"[豆包] 停止按钮仍可见 (检查 {check + 1}/{max_checks})")
                                break
                except:
                    continue

                if stop_button_found:
                    break

            if not stop_button_found:
                logger.info("[豆包] 停止按钮已消失，响应生成完成")
                break

            await asyncio.sleep(1)

        if check >= max_checks - 1:
            logger.warning("[豆包] 停止按钮检查超时")

    async def _verify_content_stable(self, page: Page, checks: int = 3, interval: float = 1.0) -> bool:
        """验证内容是否稳定"""
        try:
            last_content = ""
            last_length = 0
            stable_count = 0

            for i in range(checks):
                current_response = await self.get_current_response(page)
                current_length = len(current_response) if current_response else 0

                # 检查内容是否变化
                if current_response and current_response == last_content:
                    stable_count += 1
                elif current_length > 0 and current_length == last_length:
                    # 即使内容略有不同，但长度相同也可能表示稳定
                    stable_count += 1
                else:
                    stable_count = 0

                last_content = current_response
                last_length = current_length

                logger.debug(f"[豆包] 内容稳定性检查 {i+1}/{checks}: "
                           f"长度={current_length}, 稳定计数={stable_count}")

                if stable_count >= 2:
                    return True

                if i < checks - 1:
                    await asyncio.sleep(interval)

            return stable_count > 0

        except Exception as e:
            logger.error(f"[豆包] 验证内容稳定性时出错: {str(e)}")
            return True  # 出错时假设已稳定

    async def wait_for_response(self, page: Page, timeout: int = None) -> Optional[str]:
        """等待并获取响应 - 豆包特定实现"""
        if timeout is None:
            timeout = self.response_timeout

        try:
            # 先等待响应开始生成
            logger.info("[豆包] 等待响应生成...")
            await asyncio.sleep(2)

            # 等待响应完成
            complete = await self.wait_for_response_complete(page)

            if not complete:
                logger.warning("[豆包] 响应可能未完全完成，但继续获取当前内容")

            # 获取最终响应
            response = await self.get_current_response(page)

            if response:
                logger.info(f"[豆包] 成功获取响应，长度: {len(response)}")
            else:
                logger.warning("[豆包] 未能获取到有效响应")

            return response

        except Exception as e:
            logger.error(f"[豆包] 等待响应时出错: {str(e)}")
            return None

    async def get_current_response(self, page: Page) -> Optional[str]:
        """获取当前响应 - 豆包优化版"""
        try:
            response_selectors = self.get_response_selectors()
            all_responses = []

            for selector in response_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        for element in elements:
                            # 检查是否是助手消息
                            is_assistant = await element.evaluate("""
                                (el) => {
                                    // 检查元素或父元素的类名/属性
                                    const classStr = (el.className || '') + 
                                                   (el.parentElement?.className || '') +
                                                   (el.closest('[class*="message"]')?.className || '');
                                    
                                    // 豆包的助手消息特征
                                    return !classStr.includes('user') && 
                                           !classStr.includes('human') &&
                                           (classStr.includes('assistant') ||
                                            classStr.includes('bot') ||
                                            classStr.includes('ai') ||
                                            el.closest('[data-role="assistant"]') !== null);
                                }
                            """)

                            if is_assistant:
                                text = await element.text_content()
                                if text and text.strip():
                                    all_responses.append(text.strip())
                except:
                    continue

            # 返回最后一个助手响应（最新的）
            if all_responses:
                latest_response = all_responses[-1]

                # 清理响应文本
                cleaned_response = self._clean_response_text(latest_response)
                return cleaned_response

        except Exception as e:
            logger.error(f"[豆包] 获取当前响应失败: {str(e)}")

        return None

    def _clean_response_text(self, text: str) -> str:
        """清理响应文本"""
        if not text:
            return ""

        # 移除豆包可能的特殊标记
        cleaned = text.strip()

        # 移除可能的元数据标记
        metadata_patterns = [
            r'\[.*?\]$',  # 末尾的方括号内容
            r'^回复：',     # 开头的"回复："
            r'^答：',       # 开头的"答："
        ]

        import re
        for pattern in metadata_patterns:
            cleaned = re.sub(pattern, '', cleaned).strip()

        return cleaned

    async def ensure_logged_in(self, page: Page) -> bool:
        """确保已登录 - 豆包特定实现"""
        is_logged_in = await self.check_login_status(page)

        if is_logged_in:
            # 定期刷新以保持会话活跃
            if self._request_count > 0 and self._request_count % 10 == 0:
                logger.info("[豆包] 定期刷新页面以保持会话活跃")
                await page.reload()
                await asyncio.sleep(3)
                # 重新检查登录状态
                is_logged_in = await self.check_login_status(page)

        if not is_logged_in:
            logger.error("[豆包] 未登录，请先手动登录豆包平台")
            logger.info("提示：请在浏览器中登录 https://www.doubao.com 并保存登录状态")

        return is_logged_in

    def get_input_selectors(self) -> List[str]:
        """获取输入框选择器 - 豆包特定"""
        return [
            # 豆包特定选择器（按优先级排序）
            'textarea.semi-input-textarea',
            'textarea.semi-input',
            'textarea[placeholder*="输入"]',
            'textarea[placeholder*="问题"]',
            'textarea[placeholder*="消息"]',
            'textarea[data-testid*="input"]',
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
        ]

    def get_send_button_selectors(self) -> List[str]:
        """获取发送按钮选择器 - 豆包特定"""
        return [
            # 豆包特定选择器
            'button[aria-label*="发送"]',
            'button.semi-button[type="button"]:has(svg)',
            'button:has-text("发送")',
            '[class*="send-btn"]',
            '[class*="submit-btn"]',
            'button[class*="semi-button"]:not([data-disabled="true"])',
        ]

    def get_response_selectors(self) -> List[str]:
        """获取响应内容选择器 - 豆包特定"""
        return [
            # 豆包特定选择器（按优先级排序）
            'div[data-testid="message_text_content"]',
            'div.flow-markdown-body',
            'div.container-ZYIsnH',
            '[class*="markdown"][class*="body"]',
            '[class*="message"][class*="content"]:not([class*="user"])',
            '[class*="assistant"][class*="message"]',
            '[class*="bot"][class*="message"]',
            'div[theme-mode="light"] [class*="markdown"]',
            '[class*="flow-markdown"]',
        ]

    def get_session_metrics(self) -> Dict[str, Any]:
        """获取会话度量信息"""
        avg_validation_time = 0
        if self._validation_wait_times:
            avg_validation_time = sum(self._validation_wait_times) / len(self._validation_wait_times)

        return {
            "platform": "doubao_web",
            "conversation_count": self._conversation_count,
            "request_count": self._request_count,
            "last_conversation_id": self._last_conversation_id,
            "avg_validation_wait_time": avg_validation_time,
            "session_state": self.get_session_state()
        }