import json
import re
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import SubjectiveTask, TaskItem
from .serializers import SubjectiveTaskSerializer, TaskItemSerializer
from openai import OpenAI

# 裁判模型：deepseek-chat (建议后续把密钥移到 .env 环境变量里)
judge = OpenAI(
    base_url='https://api.deepseek.com',
    api_key="sk-95e21bca0bf94dab9d1cbb2c00a7d5f1"
)
judge_model = "deepseek-chat"

class SubjectiveTaskViewSet(viewsets.ModelViewSet):
    queryset = SubjectiveTask.objects.all().order_by('-created_at')
    serializer_class = SubjectiveTaskSerializer

    @action(detail=True, methods=['post'])
    def run_evaluation(self, request, pk=None):
        task = self.get_object()
        
        # 改变状态为评测中 (注意：这里应该是 running，前端才会显示“评测中”)
        task.status = 'running'
        task.save()
        
        # 每次重新评测时，清空旧的题目，防止重复累加
        task.items.all().delete()
        
        task_item = task.name # 例如："DeepSeek写诗能力盲测"

        try:
            # 被测大模型的客户端初始化
            client = OpenAI(
                base_url=task.test_api_url,
                api_key=task.test_api_key,
            )
            model = task.test_model_name

            # ==========================================
            # 第一步：裁判出题 (生成 3 个问题)
            # ==========================================
            sys_prompt_gen = f"""你现在是给大模型能力打分的评测官。你现在是严谨的,给分十分十分吝啬与挑剔的 AI 裁判。
用户的评测任务是：【{task_item}】。
请基于这个任务，生成 3 个高质量的测试问题。
强制要求：必须以严格的 JSON 格式输出，包含一个 'questions' 数组，里面是 3 个字符串问题。"""

            response_gen = judge.chat.completions.create(
                model=judge_model,
                messages=[{"role": "user", "content": sys_prompt_gen}],
                response_format={"type": "json_object"} # 强制返回JSON结构
            )
            gen_content = response_gen.choices[0].message.content
            
            # 容错处理：清除可能存在的 markdown 标记
            clean_json_str = re.sub(r"```json|```", "", gen_content).strip()
            print(clean_json_str)
            questions = json.loads(clean_json_str).get("questions", [])

            # 兜底：如果没成功生成，给几个默认问题
            if not questions:
                questions = ["你好，请介绍一下你自己。", "请用鲁迅的口吻写一段话。", "1+1等于几？"]

            # ==========================================
            # 第二步 & 第三步：循环让选手答题，并让裁判打分
            # ==========================================
            for q in questions[:3]: # 限制最多3题
                # 2. 选手(待测模型)答题
                test_resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": q}],
                    temperature=0.7
                )
                test_answer = test_resp.choices[0].message.content

                # 3. 裁判(DeepSeek)打分
                sys_prompt_judge = f"""你现在是严谨的,给分十分十分吝啬与挑剔的 AI 裁判。
请根据题目，对选手的回答进行打分（满分 100 分,发现一个小小小的错误就要扣很多分）并给出简短点评。
题目：{q}
选手回答：{test_answer}
强制要求：必须以严格的 JSON 格式输出，包含 'score' (整数) 和 'reasoning' (字符串) 两个字段。"""

                response_judge = judge.chat.completions.create(
                    model=judge_model,
                    messages=[{"role": "user", "content": sys_prompt_judge}],
                    response_format={"type": "json_object"}
                )
                judge_content = response_judge.choices[0].message.content
                
                # 解析裁判的打分结果
                clean_judge_str = re.sub(r"```json|```", "", judge_content).strip()
                judge_data = json.loads(clean_judge_str)

                # 4. 存入数据库，前端此时就能看到了
                TaskItem.objects.create(
                    task=task,
                    prompt=q,
                    test_response=test_answer,
                    judge_score=int(judge_data.get("score", 0)),
                    judge_reasoning=judge_data.get("reasoning", "解析评价失败")
                )
            
            # 全部完成，更新状态
            task.status = 'completed'
            task.save()
            return Response({"status": "success", "message": "评测完成！裁判已出具报告。"})
            
        except Exception as e:
            # 捕获异常（比如用户填错了 API Key 或者网络不通）
            task.status = 'failed'
            task.save()
            return Response({"status": "error", "message": f"评测失败: {str(e)}"}, status=500)

class TaskItemViewSet(viewsets.ModelViewSet):
    queryset = TaskItem.objects.all()
    serializer_class = TaskItemSerializer