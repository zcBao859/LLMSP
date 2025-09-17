import React, { useState, useEffect } from 'react';
import {
  Card, Table, Tag, Button, Space, Select, DatePicker,
  Row, Col, Statistic, Progress, Modal, Descriptions,
  Alert, Empty, Tabs, Badge
} from 'antd';
import {
  DownloadOutlined, EyeOutlined, FileTextOutlined,
  TrophyOutlined, SafetyOutlined,
  CheckCircleOutlined, CloseCircleOutlined
} from '@ant-design/icons';
import { Radar } from '@ant-design/charts';
import { evaluationAPI } from '../services/api';
import dayjs from 'dayjs';

const { Option } = Select;
const { RangePicker } = DatePicker;
const { TabPane } = Tabs;

const ResultsPage = () => {
  const [loading, setLoading] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [taskResults, setTaskResults] = useState(null);
  const [filters, setFilters] = useState({
    status: '',
    model: '',
    dateRange: null,
  });
  const [stats, setStats] = useState({
    totalTasks: 0,
    completedTasks: 0,
    avgPassRate: 0,
    topModel: '',
  });

  useEffect(() => {
    loadData();
  }, [filters]);

  const loadData = async () => {
    try {
      setLoading(true);

      // 构建查询参数
      const params = {};
      if (filters.status) params.status = filters.status;
      if (filters.model) params.model = filters.model;
      if (filters.dateRange && filters.dateRange.length === 2) {
        params.created_after = filters.dateRange[0].format('YYYY-MM-DD');
        params.created_before = filters.dateRange[1].format('YYYY-MM-DD');
      }

      const [tasksRes, leaderboardRes] = await Promise.all([
        evaluationAPI.getTasks(params),
        evaluationAPI.getLeaderboard(),
      ]);

      setTasks(tasksRes.results || []);
      setLeaderboard(leaderboardRes.leaderboard || []);

      // 计算统计数据
      const completed = tasksRes.results.filter(t => t.status === 'completed');
      const passRates = completed
        .map(t => t.results?.find(r => r.metric_name === 'pass_rate')?.metric_value)
        .filter(Boolean);

      setStats({
        totalTasks: tasksRes.results.length,
        completedTasks: completed.length,
        avgPassRate: passRates.length > 0
          ? (passRates.reduce((a, b) => a + b, 0) / passRates.length).toFixed(1)
          : 0,
        topModel: leaderboardRes.leaderboard[0]?.model_name || '-',
      });
    } catch (error) {
      console.error('加载数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const viewTaskDetails = async (task) => {
    try {
      const results = await evaluationAPI.getTaskResults(task.id, true);
      setSelectedTask(task);
      setTaskResults(results);
    } catch (error) {
      console.error('加载任务结果失败:', error);
    }
  };

  const exportResults = (task) => {
    // 实现导出功能
    const data = {
      task: task,
      results: taskResults?.results || [],
      exportTime: new Date().toISOString(),
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `evaluation_results_${task.id}_${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getStatusTag = (status) => {
    const statusConfig = {
      pending: { color: 'default', text: '等待中' },
      running: { color: 'processing', text: '运行中' },
      completed: { color: 'success', text: '已完成' },
      failed: { color: 'error', text: '失败' },
      cancelled: { color: 'warning', text: '已取消' },
    };
    const config = statusConfig[status] || statusConfig.pending;
    return <Tag color={config.color}>{config.text}</Tag>;
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
      title: '数据集',
      dataIndex: 'dataset_name',
      key: 'dataset_name',
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
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date) => dayjs(date).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => viewTaskDetails(record)}
            disabled={record.status !== 'completed'}
          >
            查看
          </Button>
          <Button
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => exportResults(record)}
            disabled={record.status !== 'completed'}
          >
            导出
          </Button>
        </Space>
      ),
    },
  ];

  const leaderboardColumns = [
    {
      title: '排名',
      dataIndex: 'rank',
      key: 'rank',
      width: 80,
      render: (rank) => {
        if (rank === 1) return <TrophyOutlined style={{ color: '#ffd700', fontSize: 20 }} />;
        if (rank === 2) return <TrophyOutlined style={{ color: '#c0c0c0', fontSize: 18 }} />;
        if (rank === 3) return <TrophyOutlined style={{ color: '#cd7f32', fontSize: 16 }} />;
        return rank;
      },
    },
    {
      title: '模型',
      dataIndex: 'model_name',
      key: 'model_name',
    },
    {
      title: '综合评分',
      dataIndex: 'overall_score',
      key: 'overall_score',
      render: (score) => (
        <Progress
          percent={score * 100}
          size="small"
          format={(percent) => `${percent.toFixed(1)}%`}
        />
      ),
    },
    {
      title: '安全评分',
      dataIndex: 'safety_score',
      key: 'safety_score',
      render: (score) => `${(score * 100).toFixed(1)}%`,
    },
    {
      title: '评测次数',
      dataIndex: 'total_evaluations',
      key: 'total_evaluations',
    },
  ];

  const renderResultsModal = () => {
    if (!selectedTask || !taskResults) return null;

    // 准备雷达图数据
    const radarData = taskResults.results.map(r => ({
      metric: r.metric_name,
      value: r.metric_value,
      fullValue: 100,
    }));

    const radarConfig = {
      data: radarData,
      xField: 'metric',
      yField: 'value',
      seriesField: 'metric',
      meta: {
        value: {
          alias: '分数',
          min: 0,
          max: 100,
        },
      },
      xAxis: {
        line: null,
        tickLine: null,
        grid: {
          line: {
            style: {
              lineDash: null,
            },
          },
        },
      },
      yAxis: {
        line: null,
        tickLine: null,
        grid: {
          line: {
            type: 'line',
            style: {
              lineDash: null,
            },
          },
        },
      },
      point: {
        size: 2,
      },
    };

    return (
      <Modal
        title={`评测结果 - ${selectedTask.name}`}
        open={!!selectedTask}
        onCancel={() => {
          setSelectedTask(null);
          setTaskResults(null);
        }}
        width={900}
        footer={[
          <Button key="close" onClick={() => {
            setSelectedTask(null);
            setTaskResults(null);
          }}>
            关闭
          </Button>,
          <Button key="export" type="primary" icon={<DownloadOutlined />} onClick={() => exportResults(selectedTask)}>
            导出结果
          </Button>,
        ]}
      >
        <Tabs defaultActiveKey="overview">
          <TabPane tab="总览" key="overview">
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="模型">{selectedTask.model_name}</Descriptions.Item>
              <Descriptions.Item label="数据集">{selectedTask.dataset_name}</Descriptions.Item>
              <Descriptions.Item label="完成时间">
                {selectedTask.completed_at ? dayjs(selectedTask.completed_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="耗时">{selectedTask.duration || '-'}</Descriptions.Item>
              <Descriptions.Item label="整体状态" span={2}>
                {taskResults.summary.overall_status === 'passed' ? (
                  <Badge status="success" text="通过" />
                ) : (
                  <Badge status="error" text="未通过" />
                )}
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 24 }}>
              <Radar {...radarConfig} height={300} />
            </div>
          </TabPane>

          <TabPane tab="详细指标" key="metrics">
            <Table
              dataSource={taskResults.results}
              columns={[
                { title: '指标名称', dataIndex: 'metric_name', key: 'metric_name' },
                {
                  title: '数值',
                  key: 'value',
                  render: (_, record) => `${record.metric_value.toFixed(2)} ${record.metric_unit}`,
                },
                {
                  title: '阈值',
                  dataIndex: 'threshold',
                  key: 'threshold',
                  render: (val) => val ? val.toFixed(2) : '-',
                },
                {
                  title: '状态',
                  dataIndex: 'passed',
                  key: 'passed',
                  render: (passed) => passed ? (
                    <Tag icon={<CheckCircleOutlined />} color="success">通过</Tag>
                  ) : (
                    <Tag icon={<CloseCircleOutlined />} color="error">未通过</Tag>
                  ),
                },
              ]}
              pagination={false}
              size="small"
            />
          </TabPane>

          <TabPane tab="建议" key="recommendations">
            {taskResults.summary.recommendations && taskResults.summary.recommendations.length > 0 ? (
              <Alert
                message="改进建议"
                description={
                  <ul>
                    {taskResults.summary.recommendations.map((rec, idx) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                }
                type="info"
                showIcon
              />
            ) : (
              <Empty description="暂无建议" />
            )}
          </TabPane>

          {taskResults.examples && taskResults.examples.length > 0 && (
            <TabPane tab="示例" key="examples">
              <Table
                dataSource={taskResults.examples.slice(0, 10)}
                columns={[
                  {
                    title: '输入',
                    dataIndex: 'input',
                    key: 'input',
                    ellipsis: true,
                    width: '40%',
                  },
                  {
                    title: '输出',
                    dataIndex: 'output',
                    key: 'output',
                    ellipsis: true,
                    width: '40%',
                  },
                  {
                    title: '分数',
                    dataIndex: 'score',
                    key: 'score',
                    width: '20%',
                    render: (score) => (
                      <Progress
                        percent={score * 100}
                        size="small"
                        status={score >= 0.7 ? 'success' : 'exception'}
                      />
                    ),
                  },
                ]}
                pagination={{ pageSize: 5 }}
                size="small"
              />
            </TabPane>
          )}
        </Tabs>
      </Modal>
    );
  };

  return (
    <div className="results-page">
      {/* 统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总评测数"
              value={stats.totalTasks}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已完成"
              value={stats.completedTasks}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均通过率"
              value={stats.avgPassRate}
              suffix="%"
              prefix={<SafetyOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="最佳模型"
              value={stats.topModel}
              prefix={<TrophyOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 筛选器 */}
      <Card style={{ marginTop: 16 }}>
        <Space size="middle">
          <Select
            style={{ width: 150 }}
            placeholder="任务状态"
            allowClear
            value={filters.status}
            onChange={(value) => setFilters({ ...filters, status: value })}
          >
            <Option value="pending">等待中</Option>
            <Option value="running">运行中</Option>
            <Option value="completed">已完成</Option>
            <Option value="failed">失败</Option>
            <Option value="cancelled">已取消</Option>
          </Select>

          <Select
            style={{ width: 200 }}
            placeholder="选择模型"
            allowClear
            value={filters.model}
            onChange={(value) => setFilters({ ...filters, model: value })}
          >
            {Array.from(new Set(tasks.map(t => t.model_name))).map(model => (
              <Option key={model} value={model}>{model}</Option>
            ))}
          </Select>

          <RangePicker
            value={filters.dateRange}
            onChange={(dates) => setFilters({ ...filters, dateRange: dates })}
          />

          <Button onClick={() => setFilters({ status: '', model: '', dateRange: null })}>
            重置
          </Button>
        </Space>
      </Card>

      {/* 结果表格 */}
      <Tabs defaultActiveKey="tasks" style={{ marginTop: 16 }}>
        <TabPane tab="评测任务" key="tasks">
          <Card>
            <Table
              columns={taskColumns}
              dataSource={tasks}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </Card>
        </TabPane>

        <TabPane tab="模型排行榜" key="leaderboard">
          <Card>
            <Table
              columns={leaderboardColumns}
              dataSource={leaderboard}
              rowKey="id"
              loading={loading}
              pagination={false}
            />
          </Card>
        </TabPane>
      </Tabs>

      {/* 结果详情弹窗 */}
      {renderResultsModal()}
    </div>
  );
};

export default ResultsPage;