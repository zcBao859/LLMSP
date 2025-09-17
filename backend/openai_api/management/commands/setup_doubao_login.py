# backend/openai_api/management/commands/setup_web_login.py
"""
Django管理命令 - 设置Web模型的登录状态
使用方法: python manage.py setup_web_login --platform doubao_web
"""
import asyncio
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from playwright.async_api import async_playwright


class Command(BaseCommand):
    help = '设置Web模型的登录状态'

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform',
            type=str,
            required=True,
            help='平台名称（如: doubao_web, tongyi_web, wenxin_web）'
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

        # 获取平台配置
        model_configs = getattr(settings, 'MODEL_CONFIGS', {})
        if platform not in model_configs:
            self.stdout.write(self.style.ERROR(f'未找到平台配置: {platform}'))
            return

        config = model_configs[platform]

        # 运行异步设置函数
        asyncio.run(self.setup_login(platform, config, timeout))

    async def setup_login(self, platform: str, config: dict, timeout: int):
        """设置登录状态"""
        self.stdout.write(f'正在为 {platform} 设置登录状态...')

        playwright = await async_playwright().start()

        try:
            # 启动浏览器（有头模式）
            browser = await playwright.chromium.launch(
                headless=False,
                args=['--disable-blink-features=AutomationControlled']
            )

            # 创建上下文
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )

            # 创建页面
            page = await context.new_page()

            # 导航到目标网站
            base_url = config.get('base_url', '')
            self.stdout.write(f'导航到: {base_url}')
            await page.goto(base_url)

            # 提示用户登录
            self.stdout.write(self.style.WARNING('\n' + '=' * 60))
            self.stdout.write(self.style.WARNING('请在浏览器中完成登录'))
            self.stdout.write(self.style.WARNING('登录成功后，按 Enter 键继续...'))
            self.stdout.write(self.style.WARNING('=' * 60 + '\n'))

            # 等待用户输入
            input()

            # 保存状态
            state_dir = settings.WEB_SCRAPER_CONFIG.get("state_dir", "browser_states")
            os.makedirs(state_dir, exist_ok=True)
            state_file = os.path.join(state_dir, f'{platform}_state.json')

            await context.storage_state(path=state_file)
            self.stdout.write(self.style.SUCCESS(f'✅ 登录状态已保存到: {state_file}'))

            # 验证保存的状态
            self.stdout.write('正在验证保存的状态...')

            # 创建新的上下文使用保存的状态
            test_context = await browser.new_context(storage_state=state_file)
            test_page = await test_context.new_page()
            await test_page.goto(base_url)
            await asyncio.sleep(3)

            # 检查是否仍然保持登录状态
            # 这里可以根据不同平台添加特定的检查逻辑

            self.stdout.write(self.style.SUCCESS('✅ 登录状态验证成功！'))
            self.stdout.write(f'\n现在您可以使用模型: {platform}')

            await test_context.close()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'设置登录状态失败: {str(e)}'))

        finally:
            await browser.close()
            await playwright.stop()