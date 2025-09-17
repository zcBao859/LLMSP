// components/TaskList/index.js
import React from 'react';
import { Card, Table, Button, Space, Select, Tag, Progress, Badge, Popconfirm } from 'antd';
import {
  PlayCircleOutlined, EyeOutlined, BugOutlined, ReloadOutlined,
  DiffOutlined, DownloadOutlined, CodeOutlined, StopOutlined,
  ClockCircleOutlined, LoadingOutlined, CheckCircleOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons';
import { apiUtils } from '../../services/api';
import { TASK_STATUS_CONFIG } from '../../utils/constants';

const { Option } = Select;

const TaskList = ({
  tasks,
  loading,
  onCreateNew,
  onViewDetail,
  onAnalyzeBadCases,
  onCancelTask,
  onRerunTask,
  onCompareModels,
  onExportReport,
  onRefresh
}) => {
  const getStatusIcon = (status) => {
    const iconMap = {
      'ClockCircleOutlined': <ClockCircleOutlined />,
      'LoadingOutlined': <LoadingOutlined />,
      'CheckCircleOutlined': <CheckCircleOutlined />,
      'ExclamationCircleOutlined': <ExclamationCircleOutlined />,
      'StopOutlined': <StopOutlined />
    };
    return iconMap[TASK_STATUS_CONFIG[status]?.icon] || null;
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: '类型',
      key: 'type',
      width: 120,
      render: () => (
        <Tag color="purple" icon={<CodeOutlined />}>
          OpenCompass
        </Tag>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status) => {
        const config = TASK_STATUS_CONFIG[status] || { color: 'default', text: status };
        return (
          <Badge status={config.badgeStatus} text={
            <Space>
              {getStatusIcon(status)}
              {config.text}
            </Space>
          } />
        );
      },
    },
    {
      title: '进度',
      key: 'progress',
      width: 200,
      render: (_, task) => (
        <Progress
          percent={task.progress || 0}
          status={
            task.status === 'failed' ? 'exception' :
            task.status === 'completed' ? 'success' : 'active'
          }
          size="small"
        />
      ),
    },
    {
      title: '运行时长',
      dataIndex: 'duration',
      key: 'duration',
      width: 100,
      render: (duration) => apiUtils.formatDuration(duration)
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time) => apiUtils.formatDateTime(time),
    },
    {
      title: '操作',
      key: 'action',
      width: 260,
      fixed: 'right',
      render: (_, task) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => onViewDetail(task)}
          >
            详情
          </Button>
          {task.status === 'completed' && (
            <Button
              size="small"
              icon={<BugOutlined />}
              onClick={() => onAnalyzeBadCases(task.id)}
            >
              分析
            </Button>
          )}
          {task.status === 'running' && (
            <Popconfirm
              title="确定要取消该任务吗？"
              onConfirm={() => onCancelTask(task.id)}
            >
              <Button size="small" danger>
                取消
              </Button>
            </Popconfirm>
          )}
          {(task.status === 'completed' || task.status === 'failed') && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => onRerunTask(task.id)}
            >
              重跑
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="评测任务列表"
      extra={
        <Space>
          <Select
            placeholder="任务状态"
            style={{ width: 120 }}
            allowClear
            onChange={(status) => {
              // 可以添加状态筛选逻辑
            }}
          >
            <Option value="pending">等待中</Option>
            <Option value="running">运行中</Option>
            <Option value="completed">已完成</Option>
            <Option value="failed">失败</Option>
          </Select>
          <Button icon={<DiffOutlined />} onClick={onCompareModels}>
            对比模型
          </Button>
          <Button icon={<DownloadOutlined />} onClick={() => onExportReport('json', false)}>
            导出JSON
          </Button>
          <Button icon={<DownloadOutlined />} onClick={() => onExportReport('csv', false)}>
            导出CSV
          </Button>
          <Button icon={<ReloadOutlined />} onClick={onRefresh}>
            刷新
          </Button>
        </Space>
      }
    >
      <Table
        dataSource={tasks}
        columns={columns}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1500 }}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个任务`,
        }}
      />

      <Button
        type="primary"
        icon={<PlayCircleOutlined />}
        style={{ marginTop: 16 }}
        onClick={onCreateNew}
      >
        创建新任务
      </Button>
    </Card>
  );
};

export default TaskList;