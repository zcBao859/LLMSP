// components/Modals/ModelCompareModal.js
import React from 'react';
import { Modal, Alert } from 'antd';

const ModelCompareModal = ({
  visible,
  compareResults,
  onCancel
}) => {
  return (
    <Modal
      title="模型对比结果"
      visible={visible}
      onCancel={onCancel}
      footer={null}
      width={1000}
    >
      {compareResults && (
        <div>
          <Alert
            message={compareResults.message || '对比完成'}
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <pre style={{
            maxHeight: 500,
            overflow: 'auto',
            backgroundColor: '#f0f0f0',
            padding: 16,
            borderRadius: 4
          }}>
            {compareResults.comparison_output || JSON.stringify(compareResults, null, 2)}
          </pre>
        </div>
      )}
    </Modal>
  );
};

export default ModelCompareModal;