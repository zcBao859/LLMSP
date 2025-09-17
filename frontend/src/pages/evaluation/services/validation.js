// services/validation.js
import { message } from 'antd';
import { FILE_SIZE_LIMITS } from '../utils/constants';

// 数据集名称验证正则
const DATASET_NAME_PATTERN = /^[a-zA-Z0-9_]+$/;

// 验证数据集上传表单
export const validateDatasetUpload = (formData) => {
  const errors = [];

  // 验证文件
  if (!formData.file) {
    errors.push('请选择要上传的数据集文件');
  } else {
    // 验证文件类型
    const validExtensions = ['.json', '.jsonl', '.csv'];
    const fileExt = formData.file.name.substring(formData.file.name.lastIndexOf('.')).toLowerCase();
    if (!validExtensions.includes(fileExt)) {
      errors.push(`文件格式不支持，请上传 ${validExtensions.join(', ')} 格式的文件`);
    }

    // 验证文件大小
    if (formData.file.size > FILE_SIZE_LIMITS.dataset) {
      errors.push(`文件大小不能超过 ${FILE_SIZE_LIMITS.dataset / 1024 / 1024}MB`);
    }
  }

  // 验证名称
  if (!formData.name) {
    errors.push('请输入数据集名称');
  } else if (!DATASET_NAME_PATTERN.test(formData.name)) {
    errors.push('数据集名称只能包含字母、数字和下划线');
  } else if (formData.name.length > 100) {
    errors.push('数据集名称不能超过100个字符');
  }

  // 验证显示名称
  if (!formData.display_name) {
    errors.push('请输入显示名称');
  } else if (formData.display_name.length > 200) {
    errors.push('显示名称不能超过200个字符');
  }

  // 验证描述
  if (formData.description && formData.description.length > 500) {
    errors.push('描述不能超过500个字符');
  }

  return {
    valid: errors.length === 0,
    errors
  };
};

// 验证配置上传表单
export const validateConfigUpload = (formData) => {
  const errors = [];

  // 验证文件
  if (!formData.file) {
    errors.push('请选择要上传的配置文件');
  } else {
    // 验证文件类型
    if (!formData.file.name.endsWith('.py')) {
      errors.push('配置文件必须是Python文件（.py）');
    }

    // 验证文件大小
    if (formData.file.size > FILE_SIZE_LIMITS.config) {
      errors.push(`文件大小不能超过 ${FILE_SIZE_LIMITS.config / 1024 / 1024}MB`);
    }
  }

  // 验证名称
  if (!formData.name) {
    errors.push('请输入配置名称');
  } else if (formData.name.length > 200) {
    errors.push('配置名称不能超过200个字符');
  }

  // 验证显示名称
  if (!formData.display_name) {
    errors.push('请输入显示名称');
  } else if (formData.display_name.length > 200) {
    errors.push('显示名称不能超过200个字符');
  }

  // 验证描述
  if (formData.description && formData.description.length > 500) {
    errors.push('描述不能超过500个字符');
  }

  return {
    valid: errors.length === 0,
    errors
  };
};

// 验证任务创建表单
export const validateTaskCreation = (taskData, selectedConfig) => {
  const errors = [];

  // 验证配置选择
  if (!selectedConfig) {
    errors.push('请选择一个配置文件');
  }

  // 验证任务名称（可选，但如果填写了要验证）
  if (taskData.name && taskData.name.length > 200) {
    errors.push('任务名称不能超过200个字符');
  }

  // 验证优先级
  const validPriorities = ['low', 'normal', 'high'];
  if (taskData.priority && !validPriorities.includes(taskData.priority)) {
    errors.push('无效的优先级设置');
  }

  return {
    valid: errors.length === 0,
    errors
  };
};

// 显示验证错误
export const showValidationErrors = (errors) => {
  if (errors.length === 1) {
    message.error(errors[0]);
  } else if (errors.length > 1) {
    message.error(
      <div>
        <div>请修正以下错误：</div>
        <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>
          {errors.map((error, index) => (
            <li key={index}>{error}</li>
          ))}
        </ul>
      </div>
    );
  }
};

// 解析和验证数据集内容
export const parseAndValidateDatasetContent = (content, fileType) => {
  try {
    let data = [];

    if (fileType === '.json') {
      const parsed = JSON.parse(content);
      if (Array.isArray(parsed)) {
        data = parsed;
      } else if (parsed && typeof parsed === 'object' && 'data' in parsed) {
        data = parsed.data;
      } else {
        throw new Error('JSON文件必须是数组或包含"data"字段的对象');
      }
    } else if (fileType === '.jsonl') {
      const lines = content.trim().split('\n');
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].trim()) {
          try {
            data.push(JSON.parse(lines[i]));
          } catch (e) {
            throw new Error(`第 ${i + 1} 行的JSON格式错误: ${e.message}`);
          }
        }
      }
    } else if (fileType === '.csv') {
      // CSV解析需要在组件中使用专门的库处理
      throw new Error('CSV文件需要使用专门的解析库处理');
    }

    // 基本验证
    if (!data || data.length === 0) {
      throw new Error('数据集为空');
    }

    // 验证数据结构（可根据需要添加更多验证）
    const sampleItem = data[0];
    if (!sampleItem || typeof sampleItem !== 'object') {
      throw new Error('数据格式无效：每条数据必须是对象');
    }

    return {
      valid: true,
      data,
      sampleCount: data.length
    };
  } catch (error) {
    return {
      valid: false,
      error: error.message
    };
  }
};

// 验证文件上传前的检查
export const beforeUploadCheck = (file, type = 'dataset') => {
  const sizeLimit = FILE_SIZE_LIMITS[type];

  if (file.size > sizeLimit) {
    message.error(`文件大小不能超过 ${sizeLimit / 1024 / 1024}MB`);
    return false;
  }

  return true;
};