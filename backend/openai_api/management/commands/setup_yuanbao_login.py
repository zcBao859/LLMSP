# backend/openai_api/management/commands/setup_yuanbao_login.py
"""
Django管理命令：设置元宝Web平台登录状态
"""
import asyncio
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from playwright.async_api import async_playwright
import os

class Command(BaseCommand):
    help = '设置元宝Web平台的登录状态'

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

    def handle(self, *args, **options):
        headless = options['headless']
        force = options['force']

        self.stdout.write(f"\n{'=' * 60}")
        self.stdout.write("设置元宝Web登录状态")
        self.stdout.write(f"{'=' * 60}\n")

        asyncio.run(self.setup_login(headless, force))

    async def setup_login(self, headless=False, force=False):
        """设置元宝的登录状态"""
        # 确保状态目录存在
        browser_states_dir = Path(settings.WEB_SCRAPER_CONFIG.get("state_dir", os.path.join(settings.BASE_DIR, "browser_states")))
        browser_states_dir.mkdir(exist_ok=True)
        state_file = browser_states_dir / "yuanbao_web_state.json"

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
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page = await context.new_page()

            self.stdout.write("访问元宝网站...")
            await page.goto("https://yuanbao.tencent.com/chat", wait_until="domcontentloaded")
            await asyncio.sleep(3)

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
1. 如果出现登录页面，请使用微信、QQ或其他方式登录
2. 确保能看到聊天界面
3. 测试发送一条消息，确保功能正常
4. 完成后按Enter键继续...
"""))
                input()
            else:
                self.stdout.write(self.style.ERROR("无头模式下无法手动登录，请使用非无头模式"))
                await browser.close()
                return

            # 验证登录状态
            self.stdout.write("\n验证登录状态...")
            is_logged_in = await self.check_login_status(page)

            if is_logged_in:
                self.stdout.write(self.style.SUCCESS("✅ 登录验证成功"))
            else:
                self.stdout.write(self.style.ERROR("❌ 登录验证失败"))
                await browser.close()
                return

            # 保存状态
            await self.save_state(context, state_file)
            await browser.close()

            self.stdout.write(self.style.SUCCESS("\n✅ 元宝登录状态设置完成！"))
            self.stdout.write(f"状态已保存到: {state_file}")

    async def check_login_status(self, page):
        """检查元宝是否已登录"""
        try:
            login_score = 0

            # 检查多个登录指标
            indicators = {
                # 用户信息
                '[class*="user-avatar"], [class*="yb-common-user"], img[class*="avatar"]': 3,
                # 输入框
                'textarea, div[contenteditable="true"], [class*="input"][class*="area"]': 2,
                # 新建对话按钮
                'span.yb-icon.iconfont-yb.icon-yb-ic_newchat_20, [class*="newchat"]': 1,
                # 元宝特色功能
                'button:has-text("深度思考"), div.hyc-component-reasoner': 2,
            }

            for selector, score in indicators.items():
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element and await element.is_visible():
                        login_score += score
                except:
                    continue

            # 检查是否在登录页面
            login_page_selectors = [
                'button:has-text("登录")',
                'button:has-text("微信登录")',
                'input[type="password"]'
            ]

            for selector in login_page_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        return False
                except:
                    continue

            return login_score >= 3

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"检查登录状态失败: {e}"))
            return False

    async def save_state(self, context, state_file):
        """保存浏览器状态"""
        self.stdout.write("\n保存登录状态...")
        await context.storage_state(path=str(state_file))

        # 验证保存的文件
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
            cookie_count = len(state_data.get('cookies', []))
            self.stdout.write(f"已保存 {cookie_count} 个cookies")