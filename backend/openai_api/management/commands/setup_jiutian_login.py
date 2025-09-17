# backend/openai_api/management/commands/setup_jiutian_login.py
"""
Django管理命令：设置九天Web平台登录状态
"""
import asyncio
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from playwright.async_api import async_playwright
import os

class Command(BaseCommand):
    help = '设置九天Web平台的登录状态'

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
        self.stdout.write("设置九天Web登录状态")
        self.stdout.write(f"{'=' * 60}\n")

        asyncio.run(self.setup_login(headless, force))

    async def setup_login(self, headless=False, force=False):
        """设置九天的登录状态"""
        # 确保状态目录存在
        browser_states_dir = Path(settings.WEB_SCRAPER_CONFIG.get("state_dir", os.path.join(settings.BASE_DIR, "browser_states")))

        browser_states_dir.mkdir(exist_ok=True)
        state_file = browser_states_dir / "jiutian_web_state.json"

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

                // 九天可能需要的额外反检测
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
            """)

            page = await context.new_page()

            self.stdout.write("访问九天网站...")
            # 九天的URL可能需要特殊处理，因为它使用了hash路由
            await page.goto("https://jiutian.10086.cn/largemodel/playground/#/playground/jiutian-lan",
                            wait_until="domcontentloaded")

            # 等待页面加载完成
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
1. 如果出现登录页面，请使用中国移动账号登录
2. 确保能看到九天大模型的聊天界面
3. 确认能看到"新建对话"按钮
4. 测试发送一条消息，确保功能正常
5. 完成后按Enter键继续...

注意：九天平台可能需要：
- 中国移动账号
- 手机号验证
- 企业账号权限
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

                # 测试基本功能
                await self.test_basic_functionality(page)
            else:
                self.stdout.write(self.style.ERROR("❌ 登录验证失败"))
                await browser.close()
                return

            # 保存状态
            await self.save_state(context, state_file)
            await browser.close()

            self.stdout.write(self.style.SUCCESS("\n✅ 九天登录状态设置完成！"))
            self.stdout.write(f"状态已保存到: {state_file}")
            self.stdout.write("\n现在你可以使用 jiutian-web 模型了")

    async def check_login_status(self, page):
        """检查九天是否已登录"""
        try:
            login_score = 0

            # 九天特定的登录指标
            indicators = {
                # 新建对话按钮（最重要的指标）
                'div.btn:has-text("新建对话"), div.btn i.icon-message1, [class*="btn"]:has-text("新建对话")': 3,
                # 输入框
                'textarea, textarea[placeholder*="输入"], div[contenteditable="true"]': 2,
                # 深度思考按钮（九天特有）
                'button.input-bottom-btn:has-text("深度思考"), button:has(em.icon-bulb)': 2,
                # 音频输入（九天特有）
                'div.audio-input, span.icon-audio1': 1,
                # 其他UI元素
                '[data-v-71d6fbf5], [data-v-65073c23]': 1,
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
                'button:has-text("立即登录")',
                'input[type="password"]',
                '[class*="login"]',
                'form[class*="login"]'
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
            return login_score >= 3

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
                'textarea[placeholder*="输入"]',
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

            # 检查深度思考功能
            deep_think = await page.query_selector('button:has-text("深度思考")')
            if deep_think and await deep_think.is_visible():
                self.stdout.write("  ✓ 深度思考功能可用")

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