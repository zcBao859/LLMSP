// utils/constants.js

// 数据集类别
export const DATASET_CATEGORIES = [
  { value: 'safety', label: '安全性', count: 0, color: '#ff4d4f' },
  { value: 'bias', label: '偏见', count: 0, color: '#ff7a45' },
  { value: 'toxicity', label: '毒性', count: 0, color: '#ffa940' },
  { value: 'privacy', label: '隐私', count: 0, color: '#ffc53d' },
  { value: 'robustness', label: '鲁棒性', count: 0, color: '#95de64' },
  { value: 'ethics', label: '伦理', count: 0, color: '#5cdbd3' },
  { value: 'factuality', label: '事实性', count: 0, color: '#69c0ff' },
  { value: 'custom', label: '自定义', count: 0, color: '#b37feb' },
];

// 任务状态配置
export const TASK_STATUS_CONFIG = {
  'pending': {
    color: 'default',
    text: '等待中',
    icon: 'ClockCircleOutlined',
    badgeStatus: 'default'
  },
  'running': {
    color: 'processing',
    text: '运行中',
    icon: 'LoadingOutlined',
    badgeStatus: 'processing'
  },
  'completed': {
    color: 'success',
    text: '已完成',
    icon: 'CheckCircleOutlined',
    badgeStatus: 'success'
  },
  'failed': {
    color: 'error',
    text: '失败',
    icon: 'ExclamationCircleOutlined',
    badgeStatus: 'error'
  },
  'cancelled': {
    color: 'warning',
    text: '已取消',
    icon: 'StopOutlined',
    badgeStatus: 'warning'
  },
};

// 文件类型配置
export const FILE_TYPE_CONFIG = {
  'log': { icon: 'FileTextOutlined', category: 'logs' },
  'json': { icon: 'FileOutlined', category: 'results' },
  'py': { icon: 'CodeOutlined', category: 'configs' },
  'out': { icon: 'FileTextOutlined', category: 'results' },
  'csv': { icon: 'FileOutlined', category: 'results' },
};

// 默认表单值
export const DEFAULT_FORM_VALUES = {
  dataset: {
    file: null,
    name: '',
    display_name: '',
    category: 'custom',
    description: ''
  },
  config: {
    file: null,
    name: '',
    display_name: '',
    description: ''
  },
  task: {
    name: '',
    priority: 'normal'
  }
};

// 文件大小限制
export const FILE_SIZE_LIMITS = {
  dataset: 100 * 1024 * 1024, // 100MB
  config: 10 * 1024 * 1024,   // 10MB
};

// 轮询配置
export const POLLING_CONFIG = {
  initialInterval: 2000,  // 2秒
  maxInterval: 10000,     // 10秒
  maxErrors: 3,
};

// 步骤配置
export const EVALUATION_STEPS = [
  {
    title: '选择配置',
    icon: 'DatabaseOutlined',
    description: '选择或上传评测配置文件'
  },
  {
    title: '配置任务',
    icon: 'SettingOutlined',
    description: '设置任务参数'
  },
  {
    title: '运行评测',
    icon: 'ExperimentOutlined',
    description: '查看和管理评测任务'
  },
];