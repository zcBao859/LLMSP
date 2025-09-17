# backend/openai_api/api/cookie_manager.py
"""Cookie管理API - 用于上传和管理浏览器状态"""
import json
import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class CookieUploadView(APIView):
    """上传浏览器Cookie"""
    authentication_classes = []
    permission_classes = [AllowAny]  # 生产环境应该添加认证

    def post(self, request):
        """上传Cookie文件"""
        platform = request.data.get('platform')
        cookies = request.data.get('cookies')

        if not platform or not cookies:
            return Response(
                {"error": "platform and cookies are required"},
                status=400
            )

        # 验证平台名称
        valid_platforms = ['doubao_web', 'yuanbao_web', 'jiutian_web', 'o43_web']
        if platform not in valid_platforms:
            return Response(
                {"error": f"Invalid platform. Must be one of: {valid_platforms}"},
                status=400
            )

        try:
            # 保存Cookie文件
            state_dir = settings.WEB_SCRAPER_CONFIG.get("state_dir", "browser_states")
            os.makedirs(state_dir, exist_ok=True)

            state_file = os.path.join(state_dir, f"{platform}_state.json")

            # 构建Playwright state格式
            state_data = {
                "cookies": cookies if isinstance(cookies, list) else [],
                "origins": []
            }

            # 验证Cookie格式
            for cookie in state_data['cookies']:
                if not isinstance(cookie, dict):
                    return Response(
                        {"error": "Each cookie must be a dictionary"},
                        status=400
                    )
                # 验证必需字段
                required_fields = ['name', 'value', 'domain', 'path']
                for field in required_fields:
                    if field not in cookie:
                        return Response(
                            {"error": f"Cookie missing required field: {field}"},
                            status=400
                        )

            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)

            logger.info(f"保存了 {platform} 的Cookie，包含 {len(state_data['cookies'])} 个cookie")

            return Response({
                "message": f"Cookie saved for {platform}",
                "file": state_file,
                "cookie_count": len(state_data['cookies'])
            })

        except Exception as e:
            logger.error(f"保存Cookie失败: {str(e)}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=500
            )

    def get(self, request):
        """获取当前保存的Cookie状态"""
        state_dir = settings.WEB_SCRAPER_CONFIG.get("state_dir", "browser_states")

        result = {}
        for platform in ['doubao_web', 'yuanbao_web', 'jiutian_web', 'o43_web']:
            state_file = os.path.join(state_dir, f"{platform}_state.json")

            if os.path.exists(state_file):
                try:
                    with open(state_file, 'r') as f:
                        state_data = json.load(f)

                    result[platform] = {
                        "exists": True,
                        "cookie_count": len(state_data.get('cookies', [])),
                        "file_size": os.path.getsize(state_file),
                        "modified": os.path.getmtime(state_file)
                    }
                except Exception as e:
                    result[platform] = {
                        "exists": True,
                        "error": f"Failed to read file: {str(e)}"
                    }
            else:
                result[platform] = {"exists": False}

        return Response(result)


class CookieExportView(APIView):
    """从浏览器导出当前Cookie"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        """获取指定平台的当前Cookie"""
        platform = request.query_params.get('platform')

        if not platform:
            return Response({"error": "platform parameter is required"}, status=400)

        # 验证平台名称
        valid_platforms = ['doubao_web', 'yuanbao_web', 'jiutian_web', 'o43_web']
        if platform not in valid_platforms:
            return Response(
                {"error": f"Invalid platform. Must be one of: {valid_platforms}"},
                status=400
            )

        state_dir = settings.WEB_SCRAPER_CONFIG.get("state_dir", "browser_states")
        state_file = os.path.join(state_dir, f"{platform}_state.json")

        if not os.path.exists(state_file):
            return Response({"error": f"No cookie file found for {platform}"}, status=404)

        try:
            with open(state_file, 'r') as f:
                state_data = json.load(f)

            cookies = state_data.get('cookies', [])

            # 脱敏处理 - 隐藏部分cookie值
            safe_cookies = []
            for cookie in cookies:
                safe_cookie = cookie.copy()
                if 'value' in safe_cookie and len(safe_cookie['value']) > 10:
                    # 只显示前4个和后4个字符
                    value = safe_cookie['value']
                    safe_cookie['value'] = f"{value[:4]}...{value[-4:]}"
                safe_cookies.append(safe_cookie)

            return Response({
                "platform": platform,
                "cookies": safe_cookies,
                "total": len(cookies),
                "note": "Cookie values are partially hidden for security"
            })
        except Exception as e:
            logger.error(f"导出Cookie失败: {str(e)}", exc_info=True)
            return Response({"error": str(e)}, status=500)


class CookieDeleteView(APIView):
    """删除指定平台的Cookie"""
    authentication_classes = []
    permission_classes = [AllowAny]

    def delete(self, request, platform):
        """删除指定平台的Cookie文件"""
        # 验证平台名称
        valid_platforms = ['doubao_web', 'yuanbao_web', 'jiutian_web', 'o43_web']
        if platform not in valid_platforms:
            return Response(
                {"error": f"Invalid platform. Must be one of: {valid_platforms}"},
                status=400
            )

        state_dir = settings.WEB_SCRAPER_CONFIG.get("state_dir", "browser_states")
        state_file = os.path.join(state_dir, f"{platform}_state.json")

        if not os.path.exists(state_file):
            return Response({"error": f"No cookie file found for {platform}"}, status=404)

        try:
            os.remove(state_file)
            logger.info(f"删除了 {platform} 的Cookie文件")

            return Response({
                "message": f"Cookie file deleted for {platform}",
                "platform": platform
            })
        except Exception as e:
            logger.error(f"删除Cookie失败: {str(e)}", exc_info=True)
            return Response({"error": str(e)}, status=500)