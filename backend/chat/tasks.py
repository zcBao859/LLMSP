from celery import shared_task
from celery.utils.log import get_task_logger
import json
from .models import Conversation, Message
from .ollama_service import OllamaService
from .deepseek_service import DeepSeekService

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def process_ai_chat_async(self, conversation_id, messages, model=None, provider='ollama'):
    """
    异步处理AI聊天请求

    Args:
        conversation_id: 会话ID
        messages: 消息列表
        model: 模型名称
        provider: AI服务提供商
    """
    try:
        logger.info(f"Processing async chat for conversation {conversation_id} with {provider}")

        # 获取AI服务
        if provider == 'deepseek':
            ai_service = DeepSeekService()
        else:
            ai_service = OllamaService()

        # 调用AI服务
        response = ai_service.chat(messages, model=model)
        assistant_content = response.get('message', {}).get('content', '')

        # 保存助手回复
        conversation = Conversation.objects.get(id=conversation_id)
        assistant_message = Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=assistant_content,
            model_name=model or ai_service.default_model
        )

        # 更新会话
        conversation.save()

        logger.info(f"Successfully processed chat for conversation {conversation_id}")

        return {
            'status': 'success',
            'message_id': assistant_message.id,
            'content': assistant_content
        }

    except Exception as e:
        logger.error(f"Error processing chat: {str(e)}")
        # 重试任务
        raise self.retry(exc=e, countdown=60)  # 60秒后重试


@shared_task
def batch_process_messages(conversation_ids, provider='ollama'):
    """
    批量处理多个会话的消息

    Args:
        conversation_ids: 会话ID列表
        provider: AI服务提供商
    """
    results = []

    for conv_id in conversation_ids:
        try:
            conversation = Conversation.objects.get(id=conv_id)
            messages = [
                {"role": msg.role, "content": msg.content}
                for msg in conversation.messages.all()
            ]

            # 异步处理每个会话
            task = process_ai_chat_async.delay(conv_id, messages, provider=provider)
            results.append({
                'conversation_id': conv_id,
                'task_id': task.id
            })

        except Exception as e:
            logger.error(f"Error processing conversation {conv_id}: {str(e)}")
            results.append({
                'conversation_id': conv_id,
                'error': str(e)
            })

    return results


@shared_task
def analyze_conversation_sentiment(conversation_id):
    """
    分析会话的情感倾向

    Args:
        conversation_id: 会话ID
    """
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        messages = conversation.messages.filter(role='user')

        # 构建分析提示
        user_messages = '\n'.join([msg.content for msg in messages])
        analysis_prompt = f"""
        请分析以下用户消息的情感倾向和主要关注点：

        {user_messages}

        请提供：
        1. 整体情感倾向（正面/中性/负面）
        2. 主要讨论话题
        3. 用户可能的需求
        """

        # 使用DeepSeek进行分析（通常更适合分析任务）
        ai_service = DeepSeekService()
        response = ai_service.chat([
            {"role": "system", "content": "你是一个专业的对话分析师。"},
            {"role": "user", "content": analysis_prompt}
        ])

        analysis_result = response.get('message', {}).get('content', '')

        # 可以将结果存储到数据库或缓存
        logger.info(f"Sentiment analysis completed for conversation {conversation_id}")

        return {
            'conversation_id': conversation_id,
            'analysis': analysis_result
        }

    except Exception as e:
        logger.error(f"Error analyzing conversation {conversation_id}: {str(e)}")
        return {
            'conversation_id': conversation_id,
            'error': str(e)
        }


@shared_task
def export_conversation_history(conversation_id, format='json'):
    """
    导出会话历史

    Args:
        conversation_id: 会话ID
        format: 导出格式（json/markdown）
    """
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        messages = conversation.messages.all()

        if format == 'markdown':
            # 导出为Markdown格式
            content = f"# {conversation.title}\n\n"
            content += f"创建时间：{conversation.created_at}\n\n"

            for msg in messages:
                role_name = "用户" if msg.role == "user" else "AI助手"
                content += f"## {role_name} ({msg.created_at.strftime('%Y-%m-%d %H:%M')})\n\n"
                content += f"{msg.content}\n\n"
                content += "---\n\n"

            filename = f"conversation_{conversation_id}.md"

        else:
            # 默认导出为JSON
            data = {
                'conversation': {
                    'id': conversation.id,
                    'title': conversation.title,
                    'created_at': conversation.created_at.isoformat(),
                    'updated_at': conversation.updated_at.isoformat(),
                },
                'messages': [
                    {
                        'role': msg.role,
                        'content': msg.content,
                        'created_at': msg.created_at.isoformat(),
                        'model_name': msg.model_name
                    }
                    for msg in messages
                ]
            }

            content = json.dumps(data, ensure_ascii=False, indent=2)
            filename = f"conversation_{conversation_id}.json"

        # 这里可以将文件保存到媒体目录或发送到存储服务
        # 为了演示，我们只返回内容

        logger.info(f"Exported conversation {conversation_id} as {format}")

        return {
            'filename': filename,
            'content': content,
            'format': format
        }

    except Exception as e:
        logger.error(f"Error exporting conversation {conversation_id}: {str(e)}")
        return {
            'error': str(e)
        }


@shared_task
def cleanup_old_conversations(days=30):
    """
    清理旧的会话记录

    Args:
        days: 保留最近几天的记录
    """
    from datetime import datetime, timedelta

    cutoff_date = datetime.now() - timedelta(days=days)

    # 查找旧会话
    old_conversations = Conversation.objects.filter(
        updated_at__lt=cutoff_date,
        user__isnull=True  # 只清理匿名用户的会话
    )

    count = old_conversations.count()

    # 删除旧会话（会级联删除相关消息）
    old_conversations.delete()

    logger.info(f"Cleaned up {count} old conversations")

    return {
        'deleted_count': count,
        'cutoff_date': cutoff_date.isoformat()
    }