// components/Modals/PromptPreviewModal.js
import React from 'react';
import { Modal } from 'antd';

const PromptPreviewModal = ({
  visible,
  promptPreviews,
  onCancel
}) => {
  return (
    <Modal
      title="Prompt预览"
      visible={visible}
      onCancel={onCancel}
      footer={null}
      width={900}
    >
      <div style={{ maxHeight: 600, overflow: 'auto' }}>
        <pre style={{
          backgroundColor: '#f0f0f0',
          padding: 16,
          borderRadius: 4,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word'
        }}>
          {promptPreviews || '暂无预览内容'}
        </pre>
      </div>
    </Modal>
  );
};

export default PromptPreviewModal;