// components/Modals/DatasetUploadModal.js
import React from 'react';
import { Modal, Button, Upload, Input, Select, Form, Alert, Tag } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { FILE_SIZE_LIMITS, DATASET_CATEGORIES } from '../../utils/constants';
import { beforeUploadCheck } from '../../services/validation';

const { TextArea } = Input;
const { Option } = Select;

const DatasetUploadModal = ({
  visible,
  loading,
  formData,
  setFormData,
  onOk,
  onCancel
}) => {
  const isFormValid = formData.file && formData.name && formData.display_name;

  return (
    <Modal
      title="上传数据集"
      visible={visible}
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={loading}
          onClick={onOk}
          disabled={!isFormValid}
        >
          上传
        </Button>
      ]}
      width={600}
    >
      <Form layout="vertical">
        <Form.Item
          label="数据集文件"
          required
          extra="支持的格式：.json, .jsonl, .csv"
        >
          <Upload
            accept=".json,.jsonl,.csv"
            maxCount={1}
            beforeUpload={(file) => {
              if (!beforeUploadCheck(file, 'dataset')) {
                return false;
              }
              setFormData(prev => ({ ...prev, file }));
              return false;
            }}
            onRemove={() => {
              setFormData(prev => ({ ...prev, file: null }));
            }}
            fileList={formData.file ? [{
              uid: '-1',
              name: formData.file.name,
              status: 'done',
            }] : []}
          >
            <Button icon={<UploadOutlined />}>选择文件</Button>
          </Upload>
        </Form.Item>

        <Form.Item
          label="数据集名称"
          required
          extra="用于系统标识，只能包含字母、数字和下划线"
          validateStatus={formData.name && !/^[a-zA-Z0-9_]+$/.test(formData.name) ? 'error' : ''}
          help={formData.name && !/^[a-zA-Z0-9_]+$/.test(formData.name) ? '只能包含字母、数字和下划线' : ''}
        >
          <Input
            placeholder="例如：safety_prompts_v1"
            value={formData.name}
            onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
            maxLength={100}
          />
        </Form.Item>

        <Form.Item
          label="显示名称"
          required
          extra="用于界面显示的友好名称"
        >
          <Input
            placeholder="例如：安全提示数据集 v1"
            value={formData.display_name}
            onChange={(e) => setFormData(prev => ({ ...prev, display_name: e.target.value }))}
            maxLength={200}
          />
        </Form.Item>

        <Form.Item
          label="类别"
          extra="选择数据集所属的类别"
        >
          <Select
            style={{ width: '100%' }}
            value={formData.category}
            onChange={(value) => setFormData(prev => ({ ...prev, category: value }))}
          >
            {DATASET_CATEGORIES.map(cat => (
              <Option key={cat.value} value={cat.value}>
                <Tag color={cat.color}>{cat.label}</Tag>
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          label="描述"
          extra="数据集的详细说明（可选）"
        >
          <TextArea
            rows={3}
            placeholder="数据集的简要描述"
            value={formData.description}
            onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
            maxLength={500}
            showCount
          />
        </Form.Item>

        <Alert
          message="上传说明"
          description={
            <ul style={{ marginBottom: 0, paddingLeft: 20 }}>
              <li>数据集文件大小限制：{FILE_SIZE_LIMITS.dataset / 1024 / 1024}MB</li>
              <li>JSON格式：必须是数组或包含'data'字段的对象</li>
              <li>JSONL格式：每行一个JSON对象</li>
              <li>CSV格式：第一行为表头</li>
            </ul>
          }
          type="info"
          showIcon
        />
      </Form>
    </Modal>
  );
};

export default DatasetUploadModal;