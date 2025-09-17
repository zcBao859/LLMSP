// components/Modals/TaskDetailModal.js
import React, { useState, useEffect } from 'react';
import {
  Modal, Tabs, Descriptions, Badge, Progress, Tag, Alert, Button,
  Space, Card, Row, Col, Statistic, List, Collapse, Spin, Typography
} from 'antd';
import {
  FileTextOutlined, ExpandOutlined, SyncOutlined, FolderOpenOutlined,
  DownloadOutlined, EyeOutlined, FileOutlined, CodeOutlined
} from '@ant-design/icons';
import { apiUtils } from '../../services/api';

const { TabPane } = Tabs;
const { Panel } = Collapse;
const { Text } = Typography;

const TaskDetailModal = ({
  visible,
  task,
  loading,
  taskResults,
  taskFiles,
  taskLogs,
  onCancel,
  onLoadFiles,
  onLoadLogs,
  onDownloadFile,
  onViewFile
}) => {
  const [activeTab, setActiveTab] = useState('info');

  useEffect(() => {
    if (visible && task) {
      setActiveTab('info');
    }
  }, [visible, task]);

  if (!task) return null;

  return (
    <Modal
      title="任务详情"
      visible={visible}
      onCancel={onCancel}
      footer={null}
      width={1200}
    >
      <Spin spinning={loading}>
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="基本信息" key="info">
            <Descriptions bordered column={2}>
              <Descriptions.Item label="任务ID">{task.id}</Descriptions.Item>
              <Descriptions.Item label="任务名称">{task.name}</Descriptions.Item>
              <Descriptions.Item label="任务类型">
                <Tag color="purple" icon={<CodeOutlined />}>OpenCompass</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Badge
                  status={
                    task.status === 'running' ? 'processing' :
                    task.status === 'completed' ? 'success' :
                    task.status === 'failed' ? 'error' : 'default'
                  }
                  text={task.status}
                />
              </Descriptions.Item>
              <Descriptions.Item label="进度">
                <Progress percent={task.progress || 0} />
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                <Tag color={task.priority === 'high' ? 'red' : task.priority === 'low' ? 'default' : 'blue'}>
                  {task.priority}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="运行时长">
                {apiUtils.formatDuration(task.duration)}
              </Descriptions.Item>
              <Descriptions.Item label="工作目录">
                {task.work_dir || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {apiUtils.formatDateTime(task.created_at)}
              </Descriptions.Item>
              <Descriptions.Item label="开始时间">
                {task.started_at ? apiUtils.formatDateTime(task.started_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="完成时间">
                {task.completed_at ? apiUtils.formatDateTime(task.completed_at) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="错误信息" span={2}>
                {task.error_message && (
                  <Alert type="error" message={task.error_message} />
                )}
              </Descriptions.Item>
            </Descriptions>
          </TabPane>

          {taskResults && (
            <TabPane tab="评测结果" key="results">
              <Row gutter={[16, 16]}>
                <Col span={24}>
                  <Card>
                    <Statistic
                      title="总体准确率"
                      value={taskResults.summary?.overall_accuracy || 0}
                      precision={2}
                      suffix="%"
                      valueStyle={{ color: apiUtils.getScoreColor(taskResults.summary?.overall_accuracy || 0) }}
                    />
                  </Card>
                </Col>
              </Row>

              <Card title="详细结果" style={{ marginTop: 16 }}>
                <pre style={{ maxHeight: 400, overflow: 'auto' }}>
                  {JSON.stringify(taskResults.results || taskResults, null, 2)}
                </pre>
              </Card>
            </TabPane>
          )}

          <TabPane tab="任务文件" key="files">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button
                icon={<FolderOpenOutlined />}
                onClick={() => onLoadFiles(task.id)}
              >
                加载文件列表
              </Button>

              {taskFiles && (
                <Collapse defaultActiveKey={['logs', 'results']}>
                  <Panel header={`日志文件 (${taskFiles.logs?.length || 0})`} key="logs">
                    <List
                      dataSource={taskFiles.logs || []}
                      renderItem={file => (
                        <List.Item
                          actions={[
                            <Button
                              size="small"
                              icon={<EyeOutlined />}
                              onClick={() => onViewFile({ taskId: task.id, ...file })}
                            >
                              查看
                            </Button>,
                            <Button
                              size="small"
                              icon={<DownloadOutlined />}
                              onClick={() => onDownloadFile(task.id, file.path)}
                            >
                              下载
                            </Button>
                          ]}
                        >
                          <List.Item.Meta
                            avatar={<FileTextOutlined />}
                            title={file.name}
                            description={`大小: ${apiUtils.formatFileSize(file.size)}`}
                          />
                        </List.Item>
                      )}
                    />
                  </Panel>
                  <Panel header={`结果文件 (${taskFiles.results?.length || 0})`} key="results">
                    <List
                      dataSource={taskFiles.results || []}
                      renderItem={file => (
                        <List.Item
                          actions={[
                            <Button
                              size="small"
                              icon={<EyeOutlined />}
                              onClick={() => onViewFile({ taskId: task.id, ...file })}
                            >
                              查看
                            </Button>,
                            <Button
                              size="small"
                              icon={<DownloadOutlined />}
                              onClick={() => onDownloadFile(task.id, file.path)}
                            >
                              下载
                            </Button>
                          ]}
                        >
                          <List.Item.Meta
                            avatar={<FileOutlined />}
                            title={file.name}
                            description={`大小: ${apiUtils.formatFileSize(file.size)}`}
                          />
                        </List.Item>
                      )}
                    />
                  </Panel>
                  <Panel header={`配置文件 (${taskFiles.configs?.length || 0})`} key="configs">
                    <List
                      dataSource={taskFiles.configs || []}
                      renderItem={file => (
                        <List.Item
                          actions={[
                            <Button
                              size="small"
                              icon={<EyeOutlined />}
                              onClick={() => onViewFile({ taskId: task.id, ...file })}
                            >
                              查看
                            </Button>,
                            <Button
                              size="small"
                              icon={<DownloadOutlined />}
                              onClick={() => onDownloadFile(task.id, file.path)}
                            >
                              下载
                            </Button>
                          ]}
                        >
                          <List.Item.Meta
                            avatar={<CodeOutlined />}
                            title={file.name}
                            description={`大小: ${apiUtils.formatFileSize(file.size)}`}
                          />
                        </List.Item>
                      )}
                    />
                  </Panel>
                </Collapse>
              )}
            </Space>
          </TabPane>

          <TabPane tab="日志" key="logs">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                <Button
                  icon={<FileTextOutlined />}
                  onClick={() => onLoadLogs(task.id, 100)}
                >
                  加载最新日志（100行）
                </Button>
                <Button
                  icon={<ExpandOutlined />}
                  onClick={() => onLoadLogs(task.id, 500)}
                >
                  加载更多（500行）
                </Button>
                <Button
                  icon={<SyncOutlined />}
                  onClick={() => onLoadLogs(task.id, 100)}
                >
                  刷新
                </Button>
              </Space>

              <Card>
                <pre style={{
                  maxHeight: 500,
                  overflow: 'auto',
                  backgroundColor: '#f0f0f0',
                  padding: 16,
                  borderRadius: 4
                }}>
                  {taskLogs || '点击上方按钮加载日志...'}
                </pre>
              </Card>
            </Space>
          </TabPane>

          <TabPane tab="配置信息" key="config">
            <Descriptions bordered column={1}>
              <Descriptions.Item label="配置类型">
                OpenCompass配置文件
              </Descriptions.Item>
              <Descriptions.Item label="配置文件">
                {task.config_name || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="模型列表">
                {task.model_names?.map(name => (
                  <Tag key={name} color="purple">{name}</Tag>
                ))}
              </Descriptions.Item>
              <Descriptions.Item label="数据集列表">
                {task.dataset_names?.map(name => (
                  <Tag key={name} color="cyan">{name}</Tag>
                ))}
              </Descriptions.Item>
            </Descriptions>
          </TabPane>
        </Tabs>
      </Spin>
    </Modal>
  );
};

export default TaskDetailModal;