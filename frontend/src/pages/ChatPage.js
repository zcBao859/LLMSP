import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Layout, Input, Button, Select, List, Card, Avatar,
  Space, Divider, Modal, message, Spin, Empty, Tag, Radio
} from 'antd';
import {
  SendOutlined, DeleteOutlined, PlusOutlined,
  RobotOutlined, UserOutlined, ClearOutlined,
  SettingOutlined, CloudOutlined, ApiOutlined
} from '@ant-design/icons';
import { chatAPI } from '../services/api';
import './ChatPage.css';

const { Sider, Content } = Layout;
const { TextArea } = Input;
const { Option } = Select;

const ChatPage = () => {
  const [conversations, setConversations] = useState([]);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [provider, setProvider] = useState(''); // 初始为空
  const [config, setConfig] = useState(null);
  const messagesEndRef = useRef(null);

  // 使用useCallback优化函数
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // 加载配置和默认provider
  useEffect(() => {
    const initialize = async () => {
      try {
        const res = await chatAPI.getConfig();
        setConfig(res);
        // 设置默认provider
        if (res.default_provider) {
          setProvider(res.default_provider);
          // 根据provider设置默认模型
          if (res.default_provider === 'deepseek' && res.deepseek?.default_model) {
            setSelectedModel(res.deepseek.default_model);
          } else if (res.ollama?.default_model) {
            setSelectedModel(res.ollama.default_model);
          }
        }
      } catch (error) {
        console.error('加载配置失败:', error);
      }
    };
    initialize();
    loadConversations();
  }, []);

  // 当provider改变时，重新加载模型列表
  useEffect(() => {
    if (provider) {
      loadModels();
    }
  }, [provider]);

  // 优化滚动
  useEffect(() => {
    if (messages.length > 0) {
      scrollToBottom();
    }
  }, [messages, scrollToBottom]);

  const loadModels = useCallback(async () => {
    if (!provider) return;

    try {
      const res = await chatAPI.getModels(provider);
      setModels(res.models || []);

      // 如果当前选中的模型不在列表中，选择默认模型
      if (res.default_model && !res.models.find(m =>
        (typeof m === 'string' ? m : m.name) === selectedModel
      )) {
        setSelectedModel(res.default_model);
      }
    } catch (error) {
      message.error('加载模型列表失败');
      setModels([]);
    }
  }, [provider, selectedModel]);

  const loadConversations = useCallback(async () => {
    try {
      const res = await chatAPI.getConversations();
      setConversations(res.results || []);
    } catch (error) {
      message.error('加载会话列表失败');
    }
  }, []);

  const loadConversationMessages = useCallback(async (conversationId) => {
    try {
      setLoading(true);
      const res = await chatAPI.getConversation(conversationId);
      setMessages(res.messages || []);
      setCurrentConversation(res);
    } catch (error) {
      message.error('加载会话消息失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const createNewConversation = useCallback(async () => {
    try {
      const res = await chatAPI.createConversation({
        title: '新对话',
      });
      await loadConversations();
      setCurrentConversation(res);
      setMessages([]);
    } catch (error) {
      message.error('创建会话失败');
    }
  }, [loadConversations]);

  const sendMessage = useCallback(async () => {
    if (!inputMessage.trim()) {
      message.warning('请输入消息');
      return;
    }

    const messageContent = inputMessage;
    setInputMessage('');
    setSending(true);

    // 添加用户消息到界面
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: messageContent,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);

    try {
      const res = await chatAPI.sendMessage({
        message: messageContent,
        conversation_id: currentConversation?.id,
        model: selectedModel,
        provider: provider, // 添加provider参数
        stream: false, // 暂时不使用流式响应
      });

      // 如果是新会话，更新当前会话信息
      if (!currentConversation) {
        setCurrentConversation({ id: res.conversation_id });
        loadConversations();
      }

      // 添加助手回复
      setMessages(prev => [...prev, res.message]);
    } catch (error) {
      message.error('发送消息失败');
      // 移除刚添加的用户消息
      setMessages(prev => prev.filter(m => m.id !== userMessage.id));
      setInputMessage(messageContent);
    } finally {
      setSending(false);
    }
  }, [inputMessage, currentConversation, selectedModel, provider, loadConversations]);

  const clearConversation = () => {
    Modal.confirm({
      title: '确认清空',
      content: '确定要清空当前会话的所有消息吗？',
      onOk: async () => {
        try {
          await chatAPI.clearMessages(currentConversation.id);
          setMessages([]);
          message.success('已清空会话');
        } catch (error) {
          message.error('清空失败');
        }
      },
    });
  };

  const deleteConversation = (conversationId, e) => {
    e?.stopPropagation();
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个会话吗？',
      onOk: async () => {
        try {
          await chatAPI.deleteConversation(conversationId);
          if (currentConversation?.id === conversationId) {
            setCurrentConversation(null);
            setMessages([]);
          }
          loadConversations();
          message.success('已删除会话');
        } catch (error) {
          message.error('删除失败');
        }
      },
    });
  };

  // 切换Provider
  const handleProviderChange = useCallback(async (newProvider) => {
    setProvider(newProvider);
    // 更新默认配置
    try {
      await chatAPI.updateConfig({ default_provider: newProvider });
      message.success(`已切换到 ${newProvider === 'ollama' ? 'Ollama本地模型' : 'DeepSeek API'}`);
    } catch (error) {
      message.error('切换失败');
    }
  }, []);

  const formatTime = useCallback((dateString) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit'
    });
  }, []);

  const renderMessage = (message) => {
    const isUser = message.role === 'user';

    return (
      <div className={`message-item ${isUser ? 'user' : 'assistant'}`} key={message.id}>
        <Avatar
          icon={isUser ? <UserOutlined /> : <RobotOutlined />}
          style={{
            backgroundColor: isUser ? '#1890ff' : '#52c41a',
            flexShrink: 0
          }}
        />
        <div className="message-content">
          <div className="message-header">
            <span className="message-role">
              {isUser ? '你' : message.model_name || selectedModel}
            </span>
            <span className="message-time">
              {formatTime(message.created_at)}
            </span>
          </div>
          <div className="message-text">
            {message.content.split('\n').map((line, i) => (
              <p key={i}>{line || '\u00A0'}</p>
            ))}
          </div>
        </div>
      </div>
    );
  };

  return (
    <Layout className="chat-page">
      <Sider width={300} theme="light" className="chat-sider">
        <div className="sider-header">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={createNewConversation}
            block
          >
            新建会话
          </Button>
        </div>

        <div className="conversation-list">
          <List
            dataSource={conversations}
            renderItem={conversation => (
              <List.Item
                className={`conversation-item ${
                  currentConversation?.id === conversation.id ? 'active' : ''
                }`}
                onClick={() => loadConversationMessages(conversation.id)}
                actions={[
                  <Button
                    type="text"
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={(e) => deleteConversation(conversation.id, e)}
                  />
                ]}
              >
                <List.Item.Meta
                  title={conversation.title}
                  description={
                    <div>
                      <div>{conversation.last_message?.content || '暂无消息'}</div>
                      <Tag size="small">{conversation.message_count || 0} 条消息</Tag>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        </div>
      </Sider>

      <Content className="chat-content">
        <div className="chat-header">
          <Space>
            <span>AI服务：</span>
            <Radio.Group value={provider} onChange={(e) => handleProviderChange(e.target.value)}>
              <Radio.Button value="ollama">
                <ApiOutlined /> Ollama本地
              </Radio.Button>
              <Radio.Button value="deepseek">
                <CloudOutlined /> DeepSeek API
              </Radio.Button>
            </Radio.Group>

            <Divider type="vertical" />

            <span>模型：</span>
            <Select
              value={selectedModel}
              onChange={setSelectedModel}
              style={{ width: 250 }}
              placeholder="选择模型"
              loading={!models.length && provider}
            >
              {models.map(model => {
                const modelName = typeof model === 'string' ? model : model.name;
                const modelData = typeof model === 'string' ? { name: model } : model;

                return (
                  <Option key={modelName} value={modelName}>
                    {provider === 'deepseek' ? (
                      <Space>
                        <CloudOutlined />
                        {modelName} - {modelData.description || '在线模型'}
                      </Space>
                    ) : (
                      <Space>
                        <ApiOutlined />
                        {modelName} ({modelData.size ? `${(modelData.size / 1024 / 1024 / 1024).toFixed(1)}GB` : '本地'})
                      </Space>
                    )}
                  </Option>
                );
              })}
            </Select>
          </Space>

          {currentConversation && (
            <Space>
              <Button
                icon={<ClearOutlined />}
                onClick={clearConversation}
              >
                清空会话
              </Button>
            </Space>
          )}
        </div>

        <div className="messages-container">
          {loading ? (
            <div className="loading-container">
              <Spin size="large" tip="加载中..." />
            </div>
          ) : messages.length === 0 ? (
            <Empty
              description="暂无消息，开始你的对话吧"
              className="empty-messages"
            />
          ) : (
            <div className="messages-list">
              {messages.map((message) => renderMessage(message))}
              {sending && (
                <div className="message-item assistant">
                  <Avatar
                    icon={<RobotOutlined />}
                    style={{ backgroundColor: '#52c41a' }}
                  />
                  <div className="message-content">
                    <Spin size="small" /> 正在思考...
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="input-container">
          <TextArea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="输入消息... (Shift+Enter 换行)"
            autoSize={{ minRows: 2, maxRows: 6 }}
            disabled={sending}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={sendMessage}
            loading={sending}
            disabled={!inputMessage.trim()}
          >
            发送
          </Button>
        </div>
      </Content>
    </Layout>
  );
};

export default ChatPage;