from django.contrib import admin
from .models import Conversation, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'user', 'created_at', 'updated_at', 'message_count']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['title', 'user__username']
    date_hierarchy = 'created_at'

    def message_count(self, obj):
        return obj.messages.count()

    message_count.short_description = '消息数量'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'role', 'content_preview', 'model_name', 'created_at']
    list_filter = ['role', 'created_at', 'model_name']
    search_fields = ['content', 'conversation__title']
    date_hierarchy = 'created_at'
    raw_id_fields = ['conversation']

    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content

    content_preview.short_description = '内容预览'