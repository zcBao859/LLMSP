// components/Modals/ConfigUploadModal.js
import React from 'react';
import { Modal, Button, Upload, Input, Form, Alert, message } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { FILE_SIZE_LIMITS } from '../../utils/constants';
import { beforeUploadCheck } from '../../services/validation';

const { TextArea } = Input;

const ConfigUploadModal = ({
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
      title="上传配置文件"
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
          label="配置文件"
          required
          extra="仅支持Python文件（.py）"
        >
          <Upload
            accept=".py"
            maxCount={1}
            beforeUpload={(file) => {
              if (!file.name.endsWith('.py')) {
                message.error('只能上传Python文件');
                return false;
              }
              if (!beforeUploadCheck(file, 'config')) {
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
            <Button icon={<UploadOutlined />}>选择Python配置文件</Button>
          </Upload>
        </Form.Item>

        <Form.Item
          label="配置名称"
          required
          extra="用于标识配置，建议使用英文"
        >
          <Input
            placeholder="例如：gpt4_mmlu_eval"
            value={formData.name}
            onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
            maxLength={200}
          />
        </Form.Item>

        <Form.Item
          label="显示名称"
          required
          extra="用于界面显示的友好名称"
        >
          <Input
            placeholder="例如：GPT-4 MMLU评测配置"
            value={formData.display_name}
            onChange={(e) => setFormData(prev => ({ ...prev, display_name: e.target.value }))}
            maxLength={200}
          />
        </Form.Item>

        <Form.Item
          label="描述"
          extra="配置文件的详细说明（可选）"
        >
          <TextArea
            rows={3}
            placeholder="配置文件的简要描述"
            value={formData.description}
            onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
            maxLength={500}
            showCount
          />
        </Form.Item>

        <Alert
          message="配置文件要求"
          description={
            <ul style={{ marginBottom: 0, paddingLeft: 20 }}>
              <li>必须是有效的OpenCompass配置文件</li>
              <li>需要定义models和datasets</li>
              <li>文件大小限制：{FILE_SIZE_LIMITS.config / 1024 / 1024}MB</li>
              <li>配置中的模型和数据集必须在系统中可用</li>
            </ul>
          }
          type="info"
          showIcon
        />
      </Form>
    </Modal>
  );
};

export default ConfigUploadModal;