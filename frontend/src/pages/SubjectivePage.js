import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Space, Tag, Typography, message, Modal, Form, Input, Breadcrumb, Divider, Popconfirm } from 'antd';
import { PlusOutlined, PlayCircleOutlined, EyeOutlined, ArrowLeftOutlined, RobotOutlined, DeleteOutlined, IssuesCloseOutlined } from '@ant-design/icons';
import { subjectiveAPI } from '../services/api'; 

const { Title, Text, Paragraph } = Typography;

const SubjectivePage = () => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [currentTask, setCurrentTask] = useState(null);
  
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [form] = Form.useForm();

  // 获取任务列表的方法
  const fetchTasks = async () => {
    setLoading(true);
    try {
      const res = await subjectiveAPI.getTasks();
      setTasks(res.results || res || []);
    } catch (error) {
      message.error('获取评测任务失败，请检查后端是否运行正常');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  // 提交新建任务的方法
  const handleCreateTask = async (values) => {
    setSubmitLoading(true);
    try {
      await subjectiveAPI.createTask(values);
      message.success('任务创建成功！');
      setIsModalVisible(false);
      form.resetFields(); 
      fetchTasks(); 
    } catch (error) {
      message.error('创建失败：' + (error.message || '未知错误'));
    } finally {
      setSubmitLoading(false);
    }
  };

  // 触发大模型裁判评测
  const handleRunEvaluation = async (taskId) => {
    try {
      message.loading({ content: '正在呼叫裁判模型打分...', key: 'eval' });
      await subjectiveAPI.runEvaluation(taskId);
      message.success({ content: '评测指令已发送！', key: 'eval' });
      fetchTasks(); 
    } catch (error) {
      message.error({ content: '启动评测失败', key: 'eval' });
    }
  };

  // 获取任务详情
  const fetchTaskDetail = async (id) => {
    try {
      const res = await subjectiveAPI.getTask(id);
      setCurrentTask(res);
    } catch (error) {
      message.error('获取详情失败');
    }
  };

  // 删除任务的方法
  const handleDeleteTask = async (id) => {
    try {
      await subjectiveAPI.deleteTask(id);
      message.success('任务已成功删除');
      fetchTasks(); 
    } catch (error) {
      message.error('删除失败');
    }
  };

  // ==================== ✨ 分数颜色与平均分逻辑 ====================
  // 1. 获取文本 (Text) 的颜色类别
  const getScoreTextType = (score) => {
    if (score < 50) return 'danger';      // 红色
    if (score < 90) return 'warning';     // 橙黄色
    return 'success';                     // 绿色
  };

  // 2. 获取标签 (Tag) 的颜色类别
  const getScoreTagColor = (score) => {
    if (score < 50) return 'error';       // 红色 (Tag 使用 error)
    if (score < 90) return 'warning';     // 橙黄色
    return 'success';                     // 绿色
  };

  // 3. 动态计算当前任务的平均分
  let averageScore = 0;
  let hasValidScores = false;
  if (currentTask && currentTask.items && currentTask.items.length > 0) {
    const scoredItems = currentTask.items.filter(item => item.judge_score !== null && item.judge_score !== undefined);
    if (scoredItems.length > 0) {
      const totalScore = scoredItems.reduce((acc, item) => acc + item.judge_score, 0);
      averageScore = (totalScore / scoredItems.length).toFixed(1); // 保留一位小数
      hasValidScores = true;
    }
  }
  // =======================================================================

  const columns = [
    { title: '评测任务名称', dataIndex: 'name', key: 'name' },
    { 
      title: '待测模型', 
      dataIndex: 'test_model_name', 
      key: 'test_model_name',
      render: (text) => <Tag color="blue">{text || '未知'}</Tag>, 
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        const statusMap = {
          'pending': { color: 'default', text: '准备就绪' },
          'running': { color: 'processing', text: '评测中' },
          'completed': { color: 'success', text: '已完成' },
          'failed': { color: 'error', text: '失败' },
        };
        const config = statusMap[status] || { color: 'default', text: status };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (text) => new Date(text).toLocaleString() },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space size="middle">
          {
          (record.status === 'pending' )&& 
          (
            <Button 
              type="link" 
              icon={<PlayCircleOutlined />} 
              onClick={() => handleRunEvaluation(record.id)}
            >
              开始评测
            </Button>
          )}

          {(record.status === 'running' )&& 
          (
            <Button 
              type="link" 
              icon={<IssuesCloseOutlined />} 
            >
              评测中
            </Button>
          )}

          {
          (record.status === 'completed' || record.status === 'failed')&& 
          (
            <Button 
              type="link" 
              icon={<PlayCircleOutlined />} 
              onClick={() => handleRunEvaluation(record.id)}
            >
              重新评测
            </Button>
          )}

          <Button 
            type="link" 
            icon={<EyeOutlined />} 
            onClick={() => fetchTaskDetail(record.id)}
          >
            查看详情
          </Button>

          <Popconfirm
            title="确定要删除这个评测任务吗？"
            description="删除后，相关的所有测试题和打分记录也将被清除。"
            onConfirm={() => handleDeleteTask(record.id)}
            okText="确定删除"
            cancelText="取消"
            placement="topRight"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  if (currentTask) {
    return (
      <div style={{ padding: '0px' }}>
        <Breadcrumb style={{ marginBottom: 16 }}>
          <Breadcrumb.Item><a onClick={() => { setCurrentTask(null); fetchTasks(); }}>主观评测列表</a></Breadcrumb.Item>
          <Breadcrumb.Item>{currentTask.name}</Breadcrumb.Item>
        </Breadcrumb>

        <Card 
          title={
            <Space align="center">
              <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => { setCurrentTask(null); fetchTasks(); }} />
              <Title level={4} style={{ margin: 0 }}>评测报告：{currentTask.name}</Title>
              <Tag color="blue" style={{ marginLeft: 8 }}>{currentTask.test_model_name}</Tag>
              
              {/* ✨ 这里的 Tag 颜色现在会根据平均分动态变化了 */}
              {hasValidScores && (
                <Tag 
                  color={getScoreTagColor(Number(averageScore))} 
                  style={{ fontSize: '16px', padding: '4px 12px', marginLeft: 16 }}
                >
                  平均得分: <strong style={{ fontSize: '18px' }}>{averageScore}</strong> 分
                </Tag>
              )}
            </Space>
          }
        >
          {(!currentTask.items || currentTask.items.length === 0) ? (
            <div style={{ textAlign: 'center', padding: '60px 0' }}>
              <Title level={5} type="secondary">该模型尚未进行评测</Title>
              <Text type="secondary" style={{ display: 'block', marginBottom: 20 }}>请返回列表页点击“开始评测”按钮。</Text>
              <Button onClick={() => { setCurrentTask(null); fetchTasks(); }}>返回列表</Button>
            </div>
          ) : (
            currentTask.items.map((item, index) => (
              <Card type="inner" title={`测试题 ${index + 1}: ${item.prompt}`} key={item.id} style={{ marginBottom: 16 }}>
                <Paragraph>
                  <Text strong>待测模型回答：</Text> 
                  <Text>{item.test_response}</Text>
                </Paragraph>
                <Divider style={{ margin: '12px 0' }} />
                <Paragraph style={{ margin: 0 }}>
                  <Text strong><RobotOutlined /> 裁判大模型评分：</Text>
                  
                  {/* ✨ 单题分数也使用同样的判定逻辑 */}
                  <Text 
                    type={getScoreTextType(item.judge_score)} 
                    strong 
                    style={{ fontSize: 18, marginLeft: 8 }}
                  >
                    {item.judge_score !== null ? `${item.judge_score} 分` : '暂无评分'}
                  </Text>
                </Paragraph>
                <Paragraph type="secondary" style={{ marginTop: 8, background: '#f5f5f5', padding: '8px', borderRadius: 4 }}>
                  点评：{item.judge_reasoning}
                </Paragraph>
              </Card>
            ))
          )}
        </Card>
      </div>
    );
  }

  return (
    <div style={{ padding: '0px' }}>
      <Card
        title={<Title level={4} style={{ margin: 0 }}>主观评测 (LLM-as-a-Judge)</Title>}
        extra={
          <Button 
            type="primary" 
            icon={<PlusOutlined />} 
            onClick={() => setIsModalVisible(true)}
          >
            新建评测任务
          </Button>
        }
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
          配置待测大模型的 API 参数，系统将调用内置的裁判大模型进行自动化打分和点评。
        </Text>
        
        <Table 
          columns={columns} 
          dataSource={tasks} 
          rowKey="id" 
          loading={loading}
          pagination={{ pageSize: 10 }} 
        />
      </Card>

      <Modal
        title="新建主观评测任务"
        open={isModalVisible}
        onCancel={() => {
          setIsModalVisible(false);
          form.resetFields();
        }}
        confirmLoading={submitLoading}
        onOk={() => form.submit()} 
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateTask}
          initialValues={{ judge_model_name: '内置超级裁判大模型' }} 
        >
          <Form.Item
            name="name"
            label="评测任务名称"
            rules={[{ required: true, message: '请输入任务名称' }]}
          >
            <Input placeholder="例如：DeepSeek-V3 写诗能力盲测" />
          </Form.Item>

          <Form.Item
            name="test_model_name"
            label="待测模型名称"
            rules={[{ required: true, message: '请输入待测模型名称' }]}
          >
            <Input placeholder="例如：gpt-3.5-turbo 或 deepseek-chat" />
          </Form.Item>

          <Form.Item
            name="test_api_url"
            label="待测模型 API 地址 (Base URL)"
            rules={[
              { required: true, message: '请输入API地址' },
              { type: 'url', message: '请输入有效的网址' }
            ]}
          >
            <Input placeholder="例如：https://api.openai.com/v1/chat/completions" />
          </Form.Item>

          <Form.Item
            name="test_api_key"
            label="待测模型 API Key"
            rules={[{ required: true, message: '请输入API Key' }]}
          >
            <Input.Password placeholder="sk-..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SubjectivePage;