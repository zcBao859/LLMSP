// components/Modals/BadCaseModal.js
import React from 'react';
import { Modal, Space, Row, Col, Card, Statistic, Table, Alert, Tooltip } from 'antd';
import { DatabaseOutlined, CloseCircleOutlined } from '@ant-design/icons';

const BadCaseModal = ({
  visible,
  badCases,
  onCancel
}) => {
  if (!badCases) return null;

  const columns = [
    {
      title: '输入',
      dataIndex: 'origin_prompt',
      key: 'origin_prompt',
      width: '40%',
      ellipsis: true,
      render: (text) => (
        <Tooltip title={text}>
          <div style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {text}
          </div>
        </Tooltip>
      )
    },
    {
      title: '预测结果',
      dataIndex: 'prediction',
      key: 'prediction',
      width: '30%',
      ellipsis: true,
    },
    {
      title: '正确答案',
      dataIndex: 'reference',
      key: 'reference',
      width: '30%',
      ellipsis: true,
    },
  ];

  const totalCases = badCases.bad_cases_count + (badCases.correct_cases_count || 0);
  const errorRate = totalCases > 0 ? (badCases.bad_cases_count / totalCases * 100).toFixed(2) : 0;

  return (
    <Modal
      title="错误案例分析"
      visible={visible}
      onCancel={onCancel}
      footer={null}
      width={1000}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Row gutter={16}>
          <Col span={8}>
            <Card>
              <Statistic
                title="总案例数"
                value={totalCases}
                prefix={<DatabaseOutlined />}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="错误案例"
                value={badCases.bad_cases_count}
                valueStyle={{ color: '#cf1322' }}
                prefix={<CloseCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="错误率"
                value={errorRate}
                suffix="%"
                valueStyle={{ color: '#cf1322' }}
              />
            </Card>
          </Col>
        </Row>

        <Card title="错误案例详情">
          <Table
            dataSource={badCases.bad_cases || []}
            columns={columns}
            pagination={{ pageSize: 10 }}
            size="small"
            rowKey={(record, index) => index}
          />
        </Card>

        <Alert
          message="分析建议"
          description={
            <ul>
              <li>检查错误案例是否存在共同模式</li>
              <li>考虑调整模型参数或添加特定领域的训练数据</li>
              <li>可以导出错误案例进行详细分析</li>
            </ul>
          }
          type="info"
          showIcon
        />
      </Space>
    </Modal>
  );
};

export default BadCaseModal;