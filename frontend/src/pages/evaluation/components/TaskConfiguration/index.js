// components/TaskConfiguration/index.js
import React from 'react';
import { Card, Space, Button, Input, Radio, Descriptions, Tag, Divider, Alert, Typography } from 'antd';

const { Text } = Typography;

const TaskConfiguration = ({
  taskName,
  setTaskName,
  taskConfig,
  setTaskConfig,
  selectedConfig,
  configs,
  onPrevious,
  onSubmit,
  loading
}) => {
  const config = configs.find(c => c.id === selectedConfig);

  return (
    <Card title="配置评测任务">
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <div>
          <Descriptions bordered column={1}>
            <Descriptions.Item label="任务名称">
              <Input
                placeholder="例如：OpenCompass MMLU评测"
                value={taskName}
                onChange={(e) => setTaskName(e.target.value)}
                maxLength={200}
              />
            </Descriptions.Item>
            <Descriptions.Item label="配置文件">
              {config?.display_name || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="包含模型">
              {config?.model_names?.map(name => (
                <Tag key={name} color="purple">{name}</Tag>
              )) || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="包含数据集">
              {config?.dataset_names?.map(name => (
                <Tag key={name} color="cyan">{name}</Tag>
              )) || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="优先级">
              <Radio.Group
                value={taskConfig.priority}
                onChange={(e) => setTaskConfig(prev => ({ ...prev, priority: e.target.value }))}
              >
                <Radio value="low">低</Radio>
                <Radio value="normal">正常</Radio>
                <Radio value="high">高</Radio>
              </Radio.Group>
            </Descriptions.Item>
          </Descriptions>
        </div>

        <Divider />

        <Alert
          message="任务说明"
          description={
            <ul>
              <li>OpenCompass任务将使用配置文件中定义的模型和数据集</li>
              <li>任务将在后台运行，您可以在任务列表中查看进度</li>
              <li>完成后可以查看详细的评测结果和分析</li>
            </ul>
          }
          type="info"
          showIcon
        />

        <div style={{ textAlign: 'right' }}>
          <Space>
            <Button onClick={onPrevious}>
              上一步
            </Button>
            <Button type="primary" onClick={onSubmit} loading={loading}>
              创建并运行任务
            </Button>
          </Space>
        </div>
      </Space>
    </Card>
  );
};

export default TaskConfiguration;