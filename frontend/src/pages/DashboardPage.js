import React, { useState, useEffect } from 'react';
import { Row, Col, Card, Statistic, Table, Tag, Progress, Spin, Empty } from 'antd';
import {
  SafetyOutlined,
  RobotOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import {  Pie, Column } from '@ant-design/charts';
import { chatAPI, evaluationAPI } from '../services/api';

const DashboardPage = () => {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalModels: 0,
    totalEvaluations: 0,
    completedEvaluations: 0,
    avgSafetyScore: 0,
  });
  const [recentTasks, setRecentTasks] = useState([]);
  const [modelScores, setModelScores] = useState([]);
  const [categoryDistribution, setCategoryDistribution] = useState([]);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);

      // 并行加载所有数据
      const [modelsRes, tasksRes, leaderboardRes] = await Promise.all([
        chatAPI.getModels(),
        evaluationAPI.getTasks({ page_size: 100 }),
        evaluationAPI.getLeaderboard(),
      ]);

      // 计算统计数据
      const totalModels = modelsRes.models?.length || 0;
      const tasks = tasksRes.results || [];
      const completedTasks = tasks.filter(t => t.status === 'completed');

      const avgSafetyScore = leaderboardRes.leaderboard?.reduce((acc, model) =>
        acc + (model.safety_score || 0), 0
      ) / (leaderboardRes.leaderboard?.length || 1);

      setStats({
        totalModels,
        totalEvaluations: tasks.length,
        completedEvaluations: completedTasks.length,
        avgSafetyScore: (avgSafetyScore * 100).toFixed(1),
      });

      // 设置最近任务
      setRecentTasks(tasks.slice(0, 5));

      // 设置模型评分数据
      const scoreData = leaderboardRes.leaderboard?.map(model => ({
        model: model.model_name,
        score: model.overall_score * 100,
        safety: model.safety_score * 100,
      })) || [];
      setModelScores(scoreData);

      // 计算类别分布
      const categoryCount = {};
      tasks.forEach(task => {
        const category = task.dataset_category || '其他';
        categoryCount[category] = (categoryCount[category] || 0) + 1;
      });

      const categoryData = Object.entries(categoryCount).map(([key, value]) => ({
        type: getCategoryName(key),
        value,
      }));
      setCategoryDistribution(categoryData);

    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const getCategoryName = (category) => {
    const categoryMap = {
      safety: '安全性',
      bias: '偏见',
      toxicity: '毒性',
      privacy: '隐私',
      robustness: '鲁棒性',
      ethics: '伦理',
      factuality: '事实性',
    };
    return categoryMap[category] || category;
  };

  const getStatusTag = (status) => {
    const statusConfig = {
      pending: { color: 'default', text: '等待中', icon: <ClockCircleOutlined /> },
      running: { color: 'processing', text: '运行中', icon: <ClockCircleOutlined spin /> },
      completed: { color: 'success', text: '已完成', icon: <CheckCircleOutlined /> },
      failed: { color: 'error', text: '失败', icon: <ExclamationCircleOutlined /> },
      cancelled: { color: 'warning', text: '已取消', icon: <ExclamationCircleOutlined /> },
    };
    const config = statusConfig[status] || statusConfig.pending;
    return (
      <Tag color={config.color} icon={config.icon}>
        {config.text}
      </Tag>
    );
  };

  const taskColumns = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: '模型',
      dataIndex: 'model_name',
      key: 'model_name',
      width: 150,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status) => getStatusTag(status),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 120,
      render: (progress) => <Progress percent={progress} size="small" />,
    },
  ];

  // 模型评分图表配置
  const scoreChartConfig = {
    data: modelScores,
    xField: 'model',
    yField: 'score',
    seriesField: 'type',
    isGroup: true,
    columnStyle: {
      radius: [4, 4, 0, 0],
    },
    label: {
      position: 'middle',
      layout: [
        { type: 'interval-adjust-position' },
        { type: 'interval-hide-overlap' },
        { type: 'adjust-color' },
      ],
    },
  };

  // 类别分布饼图配置
  const pieConfig = {
    data: categoryDistribution,
    angleField: 'value',
    colorField: 'type',
    radius: 0.8,
    label: {
      type: 'outer',
      content: '{name} {percentage}',
    },
    interactions: [
      { type: 'pie-legend-active' },
      { type: 'element-active' },
    ],
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      {/* 统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="可用模型"
              value={stats.totalModels}
              prefix={<RobotOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="总评测数"
              value={stats.totalEvaluations}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="已完成"
              value={stats.completedEvaluations}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="平均安全分"
              value={stats.avgSafetyScore}
              suffix="%"
              prefix={<SafetyOutlined />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 图表区域 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="模型评分对比" extra={<LineChartOutlined />}>
            {modelScores.length > 0 ? (
              <Column {...scoreChartConfig} height={300} />
            ) : (
              <Empty description="暂无数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="评测类别分布">
            {categoryDistribution.length > 0 ? (
              <Pie {...pieConfig} height={300} />
            ) : (
              <Empty description="暂无数据" />
            )}
          </Card>
        </Col>
      </Row>

      {/* 最近任务 */}
      <Card title="最近评测任务" style={{ marginTop: 16 }}>
        <Table
          dataSource={recentTasks}
          columns={taskColumns}
          rowKey="id"
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  );
};

export default DashboardPage;