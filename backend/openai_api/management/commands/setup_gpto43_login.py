# backend/openai_api/management/commands/setup_o43_login.py
"""
Django管理命令：设置 O4.3 (GPT-4o) Web平台登录状态
"""
import asyncio
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from playwright.async_api import async_playwright
import os

class Command(BaseCommand):
    help = '设置 O4.3 (GPT-4o) Web平台的登录状态'

    def add_arguments(self, parser):
        parser.add_argument(
            '--headless',
            action='store_true',
            default=False,
            help='使用无头模式（不显示浏览器窗口）'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            default=False,
            help='强制重新登录（覆盖已有状态）'
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=300,
            help='等待登录的超时时间（秒）'
        )

    def handle(self, *args, **options):
        headless = options['headless']
        force = options['force']
        timeout = options['timeout']

        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write("设置 O4.3 (GPT-4o) Web登录状态")
        self.stdout.write(f"{'=' * 60}\n")

        asyncio.run(self.setup_login(headless, force, timeout))

    async def setup_login(self, headless=False, force=False, timeout=300):
        """设置 O4.3 的登录状态"""
        # 确保状态目录存在
        browser_states_dir = Path(settings.WEB_SCRAPER_CONFIG.get("state_dir", os.path.join(settings.BASE_DIR, "browser_states")))

        browser_states_dir.mkdir(exist_ok=True)
        state_file = browser_states_dir / "o43_web_state.json"

        # 检查是否已有状态文件
        if state_file.exists() and not force:
            self.stdout.write(self.style.WARNING(f"发现已有状态文件: {state_file}"))
            response = input("\n是否覆盖已有登录状态？(y/N): ")
            if response.lower() != 'y':
                self.stdout.write("保留已有状态，退出")
                return

        async with async_playwright() as p:
            self.stdout.write("启动浏览器...")

            # 浏览器启动参数
            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]

            browser = await p.chromium.launch(
                headless=headless,
                args=launch_args
            )

            # 创建上下文
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'locale': 'zh-CN',
                'timezone_id': 'Asia/Shanghai',
                'bypass_csp': True,
                'ignore_https_errors': True,
            }

            # 如果已有状态文件且不强制重新登录，尝试加载
            if state_file.exists() and not force:
                try:
                    context_options['storage_state'] = str(state_file)
                    self.stdout.write("尝试加载已有状态...")
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"加载状态失败: {e}"))

            context = await browser.new_context(**context_options)

            # 添加反检测脚本
            await context.add_init_script("""
                // 移除 webdriver 标识
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // 添加插件
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {
                            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "internal-pdf-viewer",
                            length: 1,
                            name: "Chrome PDF Plugin"
                        }
                    ]
                });

                // 添加权限
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            page = await context.new_page()

            self.stdout.write("访问 O4.3 网站...")
            await page.goto("https://share.mosha.cloud/", wait_until="domcontentloaded")

            # 等待页面完全加载
            await asyncio.sleep(5)

            # 检查是否已登录
            is_logged_in = await self.check_login_status(page)

            if is_logged_in and not force:
                self.stdout.write(self.style.SUCCESS("检测到已登录状态"))

                # 询问是否重新登录
                if not headless:
                    response = input("\n是否需要重新登录？(y/N): ")
                    if response.lower() != 'y':
                        await self.save_state(context, state_file)
                        await browser.close()
                        return
            else:
                if is_logged_in:
                    self.stdout.write("强制重新登录模式")
                else:
                    self.stdout.write("需要登录")

            if not headless:
                self.stdout.write(self.style.WARNING("""
请在浏览器中完成以下步骤：

1. 如果出现登录页面，请使用您的账号登录
2. 确保能看到聊天界面
3. 确认能看到"新聊天"按钮（通常在左侧）
4. 测试发送一条消息，确保功能正常
5. 完成后按Enter键继续...

注意：O4.3 平台可能需要：
- 有效的账号凭证
- 可能需要邮箱验证
- 某些功能可能需要特定权限
"""))
                input()

                # 给用户更多时间完成登录
                self.stdout.write(f"\n等待登录完成（最多 {timeout} 秒）...")

                start_time = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start_time < timeout:
                    is_logged_in = await self.check_login_status(page)
                    if is_logged_in:
                        break
                    await asyncio.sleep(2)
                    remaining = int(timeout - (asyncio.get_event_loop().time() - start_time))
                    self.stdout.write(f"\r等待中... 剩余 {remaining} 秒", ending="")

                self.stdout.write("")  # 换行

            else:
                self.stdout.write(self.style.ERROR("无头模式下无法手动登录，请使用非无头模式"))
                await browser.close()
                return

            # 验证登录状态
            self.stdout.write("\n验证登录状态...")
            is_logged_in = await self.check_login_status(page)

            if is_logged_in:
                self.stdout.write(self.style.SUCCESS("✅ 登录验证成功"))

                # 测试基本功能
                await self.test_basic_functionality(page)
            else:
                self.stdout.write(self.style.ERROR("❌ 登录验证失败"))

                # 截图以帮助调试
                screenshot_dir = Path(settings.BASE_DIR) / "screenshots"
                screenshot_dir.mkdir(exist_ok=True)
                screenshot_path = screenshot_dir / "o43_login_failed.png"
                await page.screenshot(path=str(screenshot_path))
                self.stdout.write(f"已保存截图到: {screenshot_path}")

                await browser.close()
                return

            # 保存状态
            await self.save_state(context, state_file)
            await browser.close()

            self.stdout.write(self.style.SUCCESS("\n✅ O4.3 登录状态设置完成！"))
            self.stdout.write(f"状态已保存到: {state_file}")
            self.stdout.write("\n现在你可以使用以下模型名称：")
            self.stdout.write("  - gpt-4o")
            self.stdout.write("  - o43")
            self.stdout.write("  - o43-web")

    async def check_login_status(self, page):
        """检查 O4.3 是否已登录"""
        try:
            login_score = 0

            # O4.3 特定的登录指标
            indicators = {
                # 新聊天按钮（最重要的指标）
                '[data-testid="create-new-chat-button"], a:has-text("新聊天"), a.__menu-item:has-text("新聊天")': 3,
                # 输入框
                'textarea, #composer-textarea, div[contenteditable="true"]': 3,
                # 发送按钮
                '#composer-submit-button, button[data-testid="send-button"]': 2,
                # 聊天历史
                'nav a[href*="/c/"], [class*="conversation-item"]': 2,
                # 侧边栏
                '[class*="sidebar"], [class*="side-panel"]': 1,
                # 用户菜单
                '[class*="user-menu"], [class*="account"]': 1,
            }

            for selector, score in indicators.items():
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element and await element.is_visible():
                        login_score += score
                        self.stdout.write(f"  ✓ 找到元素: {selector.split(',')[0][:50]}...")
                except:
                    continue

            # 检查是否在登录页面
            login_page_selectors = [
                'button:has-text("登录")',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'input[type="password"]',
                '[class*="login-form"]',
                'h1:has-text("登录")',
                'h1:has-text("Sign in")'
            ]

            for selector in login_page_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        self.stdout.write("  ✗ 检测到登录页面元素")
                        return False
                except:
                    continue

            self.stdout.write(f"登录检测分数: {login_score}")
            return login_score >= 4  # O4.3 需要较高的分数

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"检查登录状态失败: {e}"))
            return False

    async def test_basic_functionality(self, page):
        """测试基本功能"""
        try:
            self.stdout.write("\n测试基本功能...")

            # 尝试找到输入框
            input_selectors = [
                'textarea',
                '#composer-textarea',
                'textarea[placeholder*="消息"]',
                'div[contenteditable="true"]'
            ]

            input_box = None
            for selector in input_selectors:
                try:
                    input_box = await page.wait_for_selector(selector, timeout=3000)
                    if input_box:
                        break
                except:
                    continue

            if input_box:
                # 测试输入
                await input_box.click()
                await input_box.fill("测试消息")
                self.stdout.write("  ✓ 可以输入文本")

                # 清空输入框
                await input_box.fill("")
            else:
                self.stdout.write("  ✗ 未找到输入框")

            # 检查新建对话功能
            new_chat_btn = await page.query_selector('[data-testid="create-new-chat-button"]')
            if new_chat_btn and await new_chat_btn.is_visible():
                self.stdout.write("  ✓ 新建对话按钮可用")

            # 检查发送按钮
            send_btn = await page.query_selector('#composer-submit-button')
            if send_btn:
                self.stdout.write("  ✓ 发送按钮存在")

        except Exception as e:
            self.stdout.write(self.style.WARNING(f"功能测试出错: {e}"))

    async def save_state(self, context, state_file):
        """保存浏览器状态"""
        self.stdout.write("\n保存登录状态...")
        await context.storage_state(path=str(state_file))

        # 验证保存的文件
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
            cookie_count = len(state_data.get('cookies', []))
            origin_count = len(state_data.get('origins', []))
            self.stdout.write(f"已保存 {cookie_count} 个cookies, {origin_count} 个origins")

            # 显示保存的域名
            if state_data.get('origins'):
                self.stdout.write("保存的域名:")
                for origin in state_data['origins']:
                    self.stdout.write(f"  - {origin.get('origin', 'unknown')}")

            # 显示重要的cookies
            important_cookies = []
            for cookie in state_data.get('cookies', []):
                if any(domain in cookie.get('domain', '') for domain in ['mosha.cloud', 'openai']):
                    important_cookies.append(cookie)

            if important_cookies:
                self.stdout.write(f"\n找到 {len(important_cookies)} 个重要cookies")