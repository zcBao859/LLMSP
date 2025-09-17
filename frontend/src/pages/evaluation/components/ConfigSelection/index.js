// components/ConfigSelection/index.js
import React from 'react';
import { Card, Row, Col, Button, Space, Empty, Alert, Avatar, Tag, Tooltip, Typography } from 'antd';
import {
  UploadOutlined, ReloadOutlined, CheckCircleOutlined,
  EyeOutlined, FileSearchOutlined, ApiOutlined, CodeOutlined
} from '@ant-design/icons';
import { apiUtils } from '../../services/api';

const { Text } = Typography;

const ConfigSelection = ({
  configs,
  selectedConfig,
  setSelectedConfig,
  loading,
  onUploadClick,
  onRefresh,
  onViewDetail,
  onPreviewPrompts,
  onTestModel,
  onNext
}) => {
  return (
    <Card
      title="选择评测配置"
      extra={
        <Space>
          <Button icon={<UploadOutlined />} onClick={onUploadClick}>
            上传配置
          </Button>
          <Button icon={<ReloadOutlined />} onClick={onRefresh}>
            刷新
          </Button>
        </Space>
      }
    >
      {configs.length === 0 ? (
        <Empty
          description="暂无配置文件"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        >
          <Button type="primary" icon={<UploadOutlined />} onClick={onUploadClick}>
            上传配置文件
          </Button>
        </Empty>
      ) : (
        <>
          <Row gutter={[16, 16]}>
            {configs.map(config => {
              const isSelected = selectedConfig === config.id;

              return (
                <Col span={8} key={config.id}>
                  <Card
                    hoverable
                    className={`config-card ${isSelected ? 'selected' : ''}`}
                    style={{
                      border: isSelected ? '2px solid #1890ff' : '1px solid #d9d9d9',
                      backgroundColor: isSelected ? '#f0f5ff' : '#fff',
                      transition: 'all 0.3s ease'
                    }}
                    actions={[
                      <Tooltip title="查看详情">
                        <EyeOutlined key="view" onClick={(e) => {
                          e.stopPropagation();
                          onViewDetail(config);
                        }} />
                      </Tooltip>,
                      <Tooltip title="预览Prompt">
                        <FileSearchOutlined key="preview" onClick={(e) => {
                          e.stopPropagation();
                          onPreviewPrompts(config.id);
                        }} />
                      </Tooltip>,
                      <Tooltip title="测试模型">
                        <ApiOutlined key="test" onClick={(e) => {
                          e.stopPropagation();
                          onTestModel(config.id);
                        }} />
                      </Tooltip>,
                    ]}
                    onClick={() => {
                      setSelectedConfig(isSelected ? null : config.id);
                    }}
                  >
                    <Card.Meta
                      avatar={
                        <Avatar
                          icon={<CodeOutlined />}
                          size={48}
                          style={{ backgroundColor: '#722ed1' }}
                        />
                      }
                      title={
                        <Space>
                          {config.display_name}
                          {isSelected && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size="small" style={{ width: '100%' }}>
                          <Text type="secondary" ellipsis>{config.description || '暂无描述'}</Text>
                          <div>
                            <Tag color="purple">
                              {config.model_names?.length || 0} 个模型
                            </Tag>
                            <Tag color="cyan">
                              {config.dataset_names?.length || 0} 个数据集
                            </Tag>
                          </div>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            更新时间: {apiUtils.formatDateTime(config.updated_at)}
                          </Text>
                        </Space>
                      }
                    />
                  </Card>
                </Col>
              );
            })}
          </Row>

          {selectedConfig && (
            <Alert
              style={{ marginTop: 16 }}
              message="已选择配置文件"
              type="info"
              showIcon
            />
          )}
        </>
      )}

      <div style={{ marginTop: 24, textAlign: 'right' }}>
        <Button
          type="primary"
          disabled={!selectedConfig}
          onClick={onNext}
        >
          下一步
        </Button>
      </div>
    </Card>
  );
};

export default ConfigSelection;