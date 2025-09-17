# backend/openai_api/api/data_api.py
"""测试数据API视图"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Count, Avg, Sum
from ..models import TestSession, TestResult, TestPlatform


class TestSessionListAPI(APIView):
    """测试会话列表API"""
    authentication_classes = []  # 移除认证
    permission_classes = [AllowAny]  # 允许所有访问

    def get(self, request):
        """获取测试会话列表"""
        sessions = TestSession.objects.select_related('platform').order_by('-started_at')[:20]

        data = [{
            'session_id': s.session_id,
            'platform': s.platform.name,
            'test_type': s.test_type,
            'status': s.status,
            'total_tests': s.total_tests,
            'successful_tests': s.successful_tests,
            'success_rate': s.success_rate,
            'started_at': s.started_at.isoformat() if s.started_at else None,
            'completed_at': s.completed_at.isoformat() if s.completed_at else None,
        } for s in sessions]

        return Response({'sessions': data})


class TestSessionDetailAPI(APIView):
    """测试会话详情API"""
    authentication_classes = []  # 移除认证
    permission_classes = [AllowAny]  # 允许所有访问

    def get(self, request, session_id):
        """获取测试会话详情"""
        try:
            session = TestSession.objects.get(session_id=session_id)
            results = session.results.order_by('test_index')[:100]

            return Response({
                'session': {
                    'session_id': session.session_id,
                    'platform': session.platform.name,
                    'test_type': session.test_type,
                    'status': session.status,
                    'total_tests': session.total_tests,
                    'successful_tests': session.successful_tests,
                    'success_rate': session.success_rate,
                    'duration': session.duration,
                },
                'results': [{
                    'test_index': r.test_index,
                    'success': r.success,
                    'prompt': r.prompt[:100],
                    'response': r.response[:200] if r.response else None,
                    'error_message': r.error_message,
                    'duration': r.duration,
                } for r in results]
            })
        except TestSession.DoesNotExist:
            return Response({'error': 'Session not found'}, status=404)


class TestResultsAPI(APIView):
    """测试结果API"""
    authentication_classes = []  # 移除认证
    permission_classes = [AllowAny]  # 允许所有访问

    def get(self, request):
        """获取测试结果"""
        results = TestResult.objects.select_related('session__platform').order_by('-created_at')[:50]

        data = [{
            'session_id': r.session.session_id,
            'platform': r.session.platform.name,
            'test_index': r.test_index,
            'success': r.success,
            'prompt': r.prompt[:100],
            'response': r.response[:200] if r.response else None,
            'error_message': r.error_message,
            'duration': r.duration,
            'created_at': r.created_at.isoformat(),
        } for r in results]

        return Response({'results': data})


class TestPlatformsAPI(APIView):
    """测试平台API"""
    authentication_classes = []  # 移除认证
    permission_classes = [AllowAny]  # 允许所有访问

    def get(self, request):
        """获取测试平台列表"""
        platforms = TestPlatform.objects.filter(is_active=True)

        data = [{
            'id': p.id,
            'name': p.name,
            'platform_type': p.platform_type,
            'base_url': p.base_url,
            'is_active': p.is_active,
        } for p in platforms]

        return Response({'platforms': data})


class TestStatisticsAPI(APIView):
    """测试统计API"""
    authentication_classes = []  # 移除认证
    permission_classes = [AllowAny]  # 允许所有访问

    def get(self, request):
        """获取测试统计信息"""
        stats = {
            'total_sessions': TestSession.objects.count(),
            'total_tests': TestResult.objects.count(),
            'success_rate': TestResult.objects.filter(success=True).count() / max(TestResult.objects.count(), 1) * 100,
            'platforms': list(TestPlatform.objects.values('name').annotate(
                sessions=Count('testsession'),
                tests=Count('testsession__results')
            )),
        }

        return Response(stats)