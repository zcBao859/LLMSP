from rest_framework import serializers
from .models import SubjectiveTask, TaskItem

class TaskItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskItem
        fields = '__all__'

class SubjectiveTaskSerializer(serializers.ModelSerializer):
    items = TaskItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = SubjectiveTask
        # 把刚才新建的字段都暴露给前端
        fields = [
            'id', 'name', 'test_api_url', 'test_api_key', 
            'test_model_name', 'judge_model_name', 
            'status', 'created_at', 'items'
        ]