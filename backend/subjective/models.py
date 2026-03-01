from django.db import models

class SubjectiveTask(models.Model):
    """主观评测任务表（LLM-as-a-Judge 模式）"""
    STATUS_CHOICES = (
        ('pending', '准备就绪'),
        ('running', '评测中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    )
    
    name = models.CharField(max_length=200, verbose_name="任务名称")
    
    # 用户上传的待测 API 信息
    test_api_url = models.URLField(verbose_name="待测API地址")
    test_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="待测API Key")
    test_model_name = models.CharField(max_length=100, verbose_name="待测模型名称")
    
    # 系统内置的裁判模型（可以写死默认值，也可以记录下来）
    judge_model_name = models.CharField(max_length=100, default="内置超级裁判大模型", verbose_name="裁判模型")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="状态")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    def __str__(self):
        return self.name

class TaskItem(models.Model):
    """具体的评测题目和裁判打分结果"""
    task = models.ForeignKey(SubjectiveTask, related_name='items', on_delete=models.CASCADE, verbose_name="所属任务")
    
    prompt = models.TextField(verbose_name="测试题目(Prompt)")
    test_response = models.TextField(blank=True, null=True, verbose_name="待测模型的回答")
    
    # 裁判模型的评价结果
    judge_score = models.IntegerField(blank=True, null=True, verbose_name="裁判打分(比如1-10分)")
    judge_reasoning = models.TextField(blank=True, null=True, verbose_name="裁判点评/理由")
    
    def __str__(self):
        return f"{self.task.name} - 题目 {self.id}"