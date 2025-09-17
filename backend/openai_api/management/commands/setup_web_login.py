backend / openai_api / management / commands / setup_web_login.py
"""
设置Web平台登录状态的管理命令
"""
import asyncio
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from playwright.async_api import async_playwright


class Command(BaseCommand):
    help = '设置Web平台的登录状态'

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            type=str,
            required=True,
            choices=['doubao_web', 'yuanbao_web', 'jiutian_web'],
            help='要设置登录的平台'
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=300,
            help='等待登录的超时时间（秒）'
        )

    def handle(self, *args, **options):
        platform = options['platform']
        timeout = options['timeout']

        self.stdout.write(f"设置 {platform} 平台的登录状态...")

        # 运行异步任务
        asyncio.run(self.setup_login(platform, timeout))

    async def setup_login(self, platform: str, timeout: int):
        """设置登录状态"""

        # 获取平台配置
        platform_configs = {
            'doubao_web': {
                'url': 'https://www.doubao.com/chat',
                'name': '豆包',
                'login_indicators': [
                    'div[data-testid="create_conversation_button"]',
                    'textarea.semi-input',
                ]
            },
            'yuanbao_web': {
                'url': 'https://yuanbao.tencent.com/chat',
                'name': '元宝',
                'login_indicators': [
                    'span.yb-icon.iconfont-yb.icon-yb-ic_newchat_20',
                    'textarea',
                ]
            },
            'jiutian_web': {
                'url': 'https://jiutian.10086.cn/largemodel/playground/#/playground/jiutian-lan',
                'name': '九天',
                'login_indicators': [
                    'div.btn:has-text("新建对话")',
                    'textarea',
                    'button:has-text("深度思考")',
                ]
            }
        }

        config = platform_configs.get(platform)
        if not config:
            self.stdout.write(self.style.ERROR(f"未知平台: {platform}"))
            return

        async with async_playwright() as p:
            # 启动浏览器（非无头模式，方便手动登录）
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )

            # 创建上下文
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
            )

            # 添加反检测脚本
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page = await context.new_page()

            # 访问平台
            self.stdout.write(f"正在打开 {config['name']} 网站...")
            await page.goto(config['url'], wait_until='domcontentloaded')

            self.stdout.write(self.style.WARNING(
                f"\n请在浏览器中手动登录 {config['name']}！\n"
                f"登录成功后，脚本会自动保存登录状态。\n"
                f"超时时间: {timeout} 秒\n"
            ))

            # 等待登录
            logged_in = False
            start_time = asyncio.get_event_loop().time()

            while not logged_in and (asyncio.get_event_loop().time() - start_time) < timeout:
                # 检查登录指示器
                for indicator in config['login_indicators']:
                    try:
                        element = await page.query_selector(indicator)
                        if element and await element.is_visible():
                            logged_in = True
                            break
                    except:
                        pass

                if not logged_in:
                    await asyncio.sleep(2)
                    remaining = timeout - int(asyncio.get_event_loop().time() - start_time)
                    self.stdout.write(f"\r等待登录... 剩余时间: {remaining} 秒", ending='')

            if logged_in:
                self.stdout.write(self.style.SUCCESS("\n\n✅ 检测到登录成功！"))

                # 保存状态
                state_dir = settings.WEB_SCRAPER_CONFIG.get("state_dir", "browser_states")
                os.makedirs(state_dir, exist_ok=True)
                state_file = os.path.join(state_dir, f"{platform}_state.json")

                await context.storage_state(path=state_file)
                self.stdout.write(self.style.SUCCESS(f"✅ 登录状态已保存到: {state_file}"))

                # 测试一下
                self.stdout.write("\n测试发送消息...")

                # 找到输入框
                input_selectors = ['textarea', 'div[contenteditable="true"]']
                input_box = None

                for selector in input_selectors:
                    try:
                        input_box = await page.wait_for_selector(selector, timeout=3000)
                        if input_box:
                            break
                    except:
                        pass

                if input_box:
                    await input_box.fill("测试消息：你好")
                    self.stdout.write(self.style.SUCCESS("✅ 可以正常输入消息"))
                else:
                    self.stdout.write(self.style.WARNING("⚠️  未找到输入框"))

            else:
                self.stdout.write(self.style.ERROR(f"\n\n❌ 登录超时（{timeout}秒）"))

            # 关闭浏览器
            await browser.close()

            if logged_in:
                self.stdout.write(self.style.SUCCESS(
                    f"\n\n设置完成！现在可以使用 {config['name']} Web API 了。\n"
                    f"运行测试: python test_doubao.py"
                ))