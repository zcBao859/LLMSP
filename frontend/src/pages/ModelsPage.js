import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Space, Tag, Progress, Modal,
  Alert, Spin, Descriptions, Timeline, Row, Col,
  Statistic, Badge, Tooltip, message, Empty, Radio
} from 'antd';
import {
  ReloadOutlined, HistoryOutlined, BarChartOutlined,
  SafetyOutlined, TrophyOutlined, ExperimentOutlined,
  CheckCircleOutlined, CloseCircleOutlined, InfoCircleOutlined,
  ApiOutlined, CloudOutlined
} from '@ant-design/icons';
import { Line, Radar } from '@ant-design/charts';
import { chatAPI, evaluationAPI } from '../services/api';

const ModelsPage = () => {
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState([]);
  const [benchmarks, setBenchmarks] = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);
  const [modelHistory, setModelHistory] = useState(null);
  const [serverStatus, setServerStatus] = useState(null);
  const [provider, setProvider] = useState('ollama'); // 添加 provider 状态

  // 获取默认provider
  useEffect(() => {
    const getDefaultProvider = async () => {
      try {
        const config = await chatAPI.getConfig();
        if (config.default_provider) {
          setProvider(config.default_provider);
        }
      } catch (error) {
        console.error('获取配置失败:', error);
      }
    };
    getDefaultProvider();
  }, []);

  useEffect(() => {
    if (provider) {
      loadData();
    }
  }, [provider]); // 当 provider 改变时重新加载数据

  const loadData = async () => {
    try {
      setLoading(true);

      // 只检查当前provider的状态
      const healthCheck = await chatAPI.healthCheck(provider);
      setServerStatus(healthCheck);

      // 根据当前provider加载模型
      const modelsRes = await chatAPI.getModels(provider);
      setModels(modelsRes.models || []);

      // 加载基准数据（异步加载，不阻塞模型显示）
      evaluationAPI.getLeaderboard().then(benchmarksRes => {
        setBenchmarks(benchmarksRes.leaderboard || []);
      }).catch(error => {
        console.error('加载基准数据失败:', error);
      });
    } catch (error) {
      message.error('加载数据失败');
    } finally {
      setLoading(false);
    }
  };

  const viewModelHistory = async (modelName) => {
    try {
      // 查找模型的benchmark ID
      const benchmark = benchmarks.find(b => b.model_name === modelName);
      if (!benchmark) {
        message.warning('该模型暂无评测历史');
        return;
      }

      const history = await evaluationAPI.getModelHistory(benchmark.id);
      setModelHistory(history);
      setSelectedModel(modelName);
    } catch (error) {
      message.error('加载历史记录失败');
    }
  };

  const refreshModels = async () => {
    message.info('正在刷新模型列表...');
    await loadData();
    message.success('刷新完成');
  };

  const getModelBenchmark = (modelName) => {
    return benchmarks.find(b => b.model_name === modelName);
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '未知';
    const gb = bytes / 1024 / 1024 / 1024;
    if (gb >= 1) return `${gb.toFixed(1)} GB`;
    const mb = bytes / 1024 / 1024;
    return `${mb.toFixed(1)} MB`;
  };

  const modelColumns = [
    {
      title: '模型名称',
      dataIndex: 'name',
      key: 'name',
      render: (name, record) => (
        <Space>
          {provider === 'deepseek' ? <CloudOutlined /> : <ExperimentOutlined />}
          <strong>{name || record}</strong>
        </Space>
      ),
    },
    {
      title: provider === 'ollama' ? '大小' : '描述',
      dataIndex: provider === 'ollama' ? 'size' : 'description',
      key: 'size_or_desc',
      width: 180,
      render: (value, record) => {
        if (provider === 'ollama') {
          return formatFileSize(value);
        } else {
          return record.description || 'DeepSeek在线模型';
        }
      },
    },
    {
      title: '安全评分',
      key: 'safety_score',
      width: 150,
      render: (_, record) => {
        const benchmark = getModelBenchmark(record.name || record);
        if (!benchmark) return <Tag>未评测</Tag>;

        const score = benchmark.safety_score * 100;
        return (
          <Progress
            percent={score}
            size="small"
            status={score >= 90 ? 'success' : score >= 70 ? 'normal' : 'exception'}
            format={(percent) => `${percent.toFixed(1)}%`}
          />
        );
      },
    },
    {
      title: '综合评分',
      key: 'overall_score',
      width: 150,
      render: (_, record) => {
        const benchmark = getModelBenchmark(record.name || record);
        if (!benchmark) return '-';

        const score = benchmark.overall_score * 100;
        return (
          <Tooltip title="综合考虑安全性、性能等多个维度">
            <Progress
              percent={score}
              size="small"
              format={(percent) => `${percent.toFixed(1)}%`}
            />
          </Tooltip>
        );
      },
    },
    {
      title: '评测次数',
      key: 'evaluations',
      width: 100,
      render: (_, record) => {
        const benchmark = getModelBenchmark(record.name || record);
        return benchmark?.total_evaluations || 0;
      },
    },
    {
      title: provider === 'ollama' ? '最后更新' : '上下文长度',
      key: 'extra_info',
      width: 180,
      render: (_, record) => {
        if (provider === 'ollama') {
          return record.modified_at ? new Date(record.modified_at).toLocaleDateString() : '-';
        } else {
          return record.context_length ? `${record.context_length / 1000}K` : '128K';
        }
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => viewModelHistory(record.name || record)}
          >
            历史
          </Button>
          <Button
            size="small"
            type="primary"
            icon={<SafetyOutlined />}
            onClick={() => window.location.href = '/evaluation'}
          >
            评测
          </Button>
        </Space>
      ),
    },
  ];

  const renderModelHistoryModal = () => {
    if (!selectedModel || !modelHistory) return null;

    // 准备折线图数据
    const chartData = modelHistory.history.map(item => ({
      date: new Date(item.completed_at).toLocaleDateString(),
      value: item.pass_rate,
      category: item.category,
    }));

    const lineConfig = {
      data: chartData,
      xField: 'date',
      yField: 'value',
      seriesField: 'category',
      yAxis: {
        label: {
          formatter: (v) => `${v}%`,
        },
      },
      legend: {
        position: 'top',
      },
      smooth: true,
      animation: {
        appear: {
          animation: 'path-in',
          duration: 1000,
        },
      },
    };

    return (
      <Modal
        title={`${selectedModel} - 评测历史`}
        open={!!selectedModel}
        onCancel={() => {
          setSelectedModel(null);
          setModelHistory(null);
        }}
        width={800}
        footer={[
          <Button key="close" onClick={() => {
            setSelectedModel(null);
            setModelHistory(null);
          }}>
            关闭
          </Button>,
        ]}
      >
        <Alert
          message={`总评测次数: ${modelHistory.total_evaluations}`}
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        {chartData.length > 0 ? (
          <>
            <Line {...lineConfig} height={300} />

            <Timeline style={{ marginTop: 24 }}>
              {modelHistory.history.slice(0, 10).map((item, idx) => (
                <Timeline.Item
                  key={idx}
                  color={item.pass_rate >= 70 ? 'green' : 'red'}
                  dot={item.pass_rate >= 70 ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                >
                  <p>
                    <strong>{item.dataset}</strong> - {item.category}
                  </p>
                  <p>
                    通过率: {item.pass_rate}% |
                    完成时间: {new Date(item.completed_at).toLocaleString()}
                  </p>
                </Timeline.Item>
              ))}
            </Timeline>
          </>
        ) : (
          <Empty description="暂无评测历史" />
        )}
      </Modal>
    );
  };

  const renderServerStatus = () => {
    if (!serverStatus) return null;

    const currentProviderStatus = serverStatus[provider];
    if (!currentProviderStatus) return null;

    return (
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Alert
            message={`${provider === 'ollama' ? 'Ollama' : 'DeepSeek'}服务状态`}
            description={
              <Space>
                <Badge
                  status={currentProviderStatus.status === 'healthy' ? 'success' : 'error'}
                  text={currentProviderStatus.status === 'healthy' ? '正常' : '异常'}
                />
                <span>地址: {currentProviderStatus.base_url}</span>
                <span>默认模型: {currentProviderStatus.default_model}</span>
                {provider === 'deepseek' && (
                  <span>API密钥: {currentProviderStatus.api_key_configured ? '已配置' : '未配置'}</span>
                )}
              </Space>
            }
            type={currentProviderStatus.status === 'healthy' ? 'success' : 'error'}
            showIcon
          />
        </Col>
      </Row>
    );
  };

  const renderModelStats = () => {
    const totalModels = models.length;
    const evaluatedModels = benchmarks.length;
    const avgSafetyScore = benchmarks.length > 0
      ? benchmarks.reduce((acc, b) => acc + b.safety_score, 0) / benchmarks.length * 100
      : 0;
    const topModel = benchmarks[0];

    return (
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总模型数"
              value={totalModels}
              prefix={<ExperimentOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已评测"
              value={evaluatedModels}
              prefix={<BarChartOutlined />}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均安全分"
              value={avgSafetyScore.toFixed(1)}
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
              value={topModel?.model_name || '-'}
              prefix={<TrophyOutlined />}
              valueStyle={{ color: '#1890ff', fontSize: 16 }}
            />
          </Card>
        </Col>
      </Row>
    );
  };

  const renderTopModels = () => {
    const top5 = benchmarks.slice(0, 5);

    if (top5.length === 0) {
      return <Empty description="暂无评测数据" />;
    }

    // 准备雷达图数据
    const radarData = [];
    const metrics = ['safety_score', 'overall_score', 'performance_score'];
    const metricNames = {
      safety_score: '安全性',
      overall_score: '综合',
      performance_score: '性能',
    };

    top5.forEach(model => {
      metrics.forEach(metric => {
        radarData.push({
          model: model.model_name,
          metric: metricNames[metric],
          value: (model[metric] || 0) * 100,
        });
      });
    });

    const radarConfig = {
      data: radarData,
      xField: 'metric',
      yField: 'value',
      seriesField: 'model',
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
      },
      yAxis: {
        line: null,
        tickLine: null,
        grid: {
          line: {
            type: 'line',
          },
        },
      },
      point: {
        size: 2,
      },
      area: {},
    };

    return (
      <Card title="Top 5 模型对比" extra={<InfoCircleOutlined />}>
        <Radar {...radarConfig} height={400} />
      </Card>
    );
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  return (
    <div className="models-page">
      {renderServerStatus()}

      {renderModelStats()}

      <Row gutter={[16, 16]}>
        <Col span={16}>
          <Card
            title="模型列表"
            extra={
              <Space>
                {/* Provider 切换放在这里 */}
                <Radio.Group
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                >
                  <Radio.Button value="ollama">
                    <ApiOutlined /> Ollama本地
                  </Radio.Button>
                  <Radio.Button value="deepseek">
                    <CloudOutlined /> DeepSeek API
                  </Radio.Button>
                </Radio.Group>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={refreshModels}
                >
                  刷新
                </Button>
              </Space>
            }
          >
            <Table
              columns={modelColumns}
              dataSource={models}
              rowKey={(record) => record.name || record}
              pagination={{ pageSize: 10 }}
            />
          </Card>
        </Col>

        <Col span={8}>
          {renderTopModels()}
        </Col>
      </Row>

      {renderModelHistoryModal()}
    </div>
  );
};

export default ModelsPage;