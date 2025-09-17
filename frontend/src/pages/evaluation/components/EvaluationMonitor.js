// components/EvaluationMonitor.js
import React from 'react';
import { Card, Row, Col, Statistic, Progress, Tag } from 'antd';
import {
  ClockCircleOutlined,
  ThunderboltOutlined,
  FileTextOutlined,
  HourglassOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';

const EvaluationMonitor = ({ monitorData }) => {
  const {
    currentSample = 0,
    totalSamples = 0,
    processingRate = 0,
    estimatedTimeRemaining = 0,
    currentDataset = '',
    currentPhase = '',
    elapsedTime = 0
  } = monitorData || {};

  // 格式化时间
  const formatTime = (seconds) => {
    if (!seconds || seconds < 0) return '计算中...';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}小时 ${minutes}分钟`;
    } else if (minutes > 0) {
      return `${minutes}分钟 ${secs}秒`;
    } else {
      return `${secs}秒`;
    }
  };

  // 计算进度百分比
  const progressPercent = totalSamples > 0 ? Math.round((currentSample / totalSamples) * 100) : 0;

  // 获取阶段标签颜色
  const getPhaseColor = (phase) => {
    const phaseColors = {
      '初始化': 'blue',
      '加载数据集': 'cyan',
      '评测中': 'processing',
      '生成报告': 'orange',
      '完成': 'success',
      '失败': 'error',
    };
    return phaseColors[phase] || 'default';
  };

  return (
    <Card title="实时监控" bordered={false}>
      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Card size="small">
            <Statistic
              title="当前进度"
              value={`${currentSample} / ${totalSamples}`}
              prefix={<FileTextOutlined />}
              suffix="样本"
            />
            <Progress
              percent={progressPercent}
              status="active"
              strokeColor={{
                '0%': '#108ee9',
                '100%': '#87d068',
              }}
            />
          </Card>
        </Col>

        <Col span={12}>
          <Card size="small">
            <Statistic
              title="处理速度"
              value={processingRate.toFixed(2)}
              prefix={<ThunderboltOutlined />}
              suffix="样本/秒"
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>

        <Col span={12}>
          <Card size="small">
            <Statistic
              title="已用时间"
              value={formatTime(elapsedTime)}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>

        <Col span={12}>
          <Card size="small">
            <Statistic
              title="预计剩余时间"
              value={formatTime(estimatedTimeRemaining)}
              prefix={<HourglassOutlined />}
              valueStyle={{ color: '#cf1322' }}
            />
          </Card>
        </Col>

        <Col span={24}>
          <Card size="small">
            <Row align="middle" gutter={16}>
              <Col span={8}>
                <span style={{ marginRight: 8 }}>当前数据集：</span>
                <Tag color="blue">{currentDataset || '加载中...'}</Tag>
              </Col>
              <Col span={8}>
                <span style={{ marginRight: 8 }}>当前阶段：</span>
                <Tag color={getPhaseColor(currentPhase)}>{currentPhase || '准备中'}</Tag>
              </Col>
              <Col span={8}>
                <span style={{ marginRight: 8 }}>完成率：</span>
                <Tag icon={<CheckCircleOutlined />} color="green">
                  {progressPercent}%
                </Tag>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      {/* 性能指标 */}
      {processingRate > 0 && (
        <div style={{ marginTop: 16, fontSize: 12, color: '#666' }}>
          <Row gutter={16}>
            <Col span={8}>
              平均处理时间：{totalSamples > 0 ? (elapsedTime / currentSample).toFixed(2) : '0'} 秒/样本
            </Col>
            <Col span={8}>
              当前效率：{((currentSample / elapsedTime) * 60).toFixed(1)} 样本/分钟
            </Col>
            <Col span={8}>
              预计完成时间：{new Date(Date.now() + estimatedTimeRemaining * 1000).toLocaleTimeString()}
            </Col>
          </Row>
        </div>
      )}
    </Card>
  );
};

export default EvaluationMonitor;