// services/api.js
import axios from 'axios';

// 创建axios实例
const apiClient = axios.create({
  baseURL: '/api',  // 使用相对路径
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  }
});

// 请求拦截器
apiClient.interceptors.request.use(
  config => {
    // 可以在这里添加token等
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

// 响应拦截器
apiClient.interceptors.response.use(
  response => response.data,
  error => {
    if (error.response) {
      // 服务器返回错误
      const message = error.response.data?.error || error.response.data?.message || error.response.data?.detail || '请求失败';
      console.error('API Error:', message);
    } else if (error.request) {
      // 请求发送失败
      console.error('Network Error:', error.message);
    }
    return Promise.reject(error);
  }
);

// Chat API - 保持不变
export const chatAPI = {
  // 会话管理
  getConversations: (params = {}) =>
    apiClient.get('/chat/conversations/', { params }),

  createConversation: (data) =>
    apiClient.post('/chat/conversations/', data),

  getConversation: (id) =>
    apiClient.get(`/chat/conversations/${id}/`),

  updateConversation: (id, data) =>
    apiClient.put(`/chat/conversations/${id}/`, data),

  deleteConversation: (id) =>
    apiClient.delete(`/chat/conversations/${id}/`),

  clearMessages: (conversationId) =>
    apiClient.delete(`/chat/conversations/${conversationId}/clear_messages/`),

  // 发送聊天消息 - 修正端点
  sendMessage: async (data) => {
    const messageData = {
      message: data.message,
      conversation_id: data.conversation_id || data.session_id, // 兼容旧字段名
      model: data.model,
      provider: data.provider || 'ollama',
      stream: data.stream || false,
    };

    // 如果需要流式响应，需要特殊处理
    if (messageData.stream) {
      const response = await fetch(`${apiClient.defaults.baseURL}/chat/conversations/chat/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...apiClient.defaults.headers
        },
        body: JSON.stringify(messageData)
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return response;
    }

    // 非流式响应使用axios
    return apiClient.post('/chat/conversations/chat/', messageData);
  },

  // 模型管理 - 修正端点
  getModels: (() => {
    let cache = {};
    let cacheTime = {};
    const CACHE_DURATION = 5 * 60 * 1000; // 5分钟缓存

    return async (provider = null) => {
      const now = Date.now();
      const cacheKey = provider || 'all';

      // 检查缓存
      if (cache[cacheKey] && cacheTime[cacheKey] && (now - cacheTime[cacheKey] < CACHE_DURATION)) {
        return cache[cacheKey];
      }

      // 获取新数据
      const params = provider ? { provider } : {};
      const response = await apiClient.get('/chat/models/list_available/', { params });

      // 更新缓存
      cache[cacheKey] = response;
      cacheTime[cacheKey] = now;

      return response;
    };
  })(),

  // 健康检查
  healthCheck: async (provider = null) => {
    try {
      const params = provider ? { provider } : {};
      const response = await apiClient.get('/chat/models/health_check/', { params });
      return response;
    } catch (error) {
      console.error('Health check failed:', error);
      return null;
    }
  },

  // 获取系统配置
  getConfig: () =>
    apiClient.get('/chat/models/config/'),

  // 更新系统配置
  updateConfig: (data) =>
    apiClient.post('/chat/models/update_config/', data),

  // 拉取模型（仅Ollama）
  pullModel: (modelName) =>
    apiClient.post('/chat/models/pull/', { model_name: modelName }),
};

// 处理流式响应的辅助函数
export const handleStreamResponse = async (response, onChunk, onComplete, onError) => {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim() === '') continue;
        if (!line.startsWith('data: ')) continue;

        const data = line.slice(6);
        if (data === '[DONE]') {
          onComplete && onComplete();
          return;
        }

        try {
          const parsed = JSON.parse(data);

          if (parsed.type === 'error') {
            onError && onError(new Error(parsed.error));
            return;
          }

          onChunk && onChunk(parsed);

          if (parsed.type === 'done') {
            onComplete && onComplete(parsed);
            return;
          }
        } catch (e) {
          console.error('Failed to parse SSE data:', e);
        }
      }
    }
  } catch (error) {
    onError && onError(error);
  }
};

// Evaluation API - 修复版本
export const evaluationAPI = {
  // 数据集管理
  getDatasets: (params = {}) =>
    apiClient.get('/evaluation/datasets/', { params }),

  createDataset: (data) =>
    apiClient.post('/evaluation/datasets/', data),

  getDataset: (id) =>
    apiClient.get(`/evaluation/datasets/${id}/`),

  updateDataset: (id, data) =>
    apiClient.put(`/evaluation/datasets/${id}/`, data),

  deleteDataset: (id) =>
    apiClient.delete(`/evaluation/datasets/${id}/`),

  // 数据集上传
  uploadDataset: (formData) =>
    apiClient.post('/evaluation/datasets/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),

  // 获取数据集类别
  getDatasetCategories: async () => {
    try {
      return await apiClient.get('/evaluation/datasets/categories/');
    } catch (error) {
      // 返回默认类别
      return [
        { value: 'safety', label: '安全性', count: 0, color: '#ff4d4f' },
        { value: 'bias', label: '偏见', count: 0, color: '#ff7a45' },
        { value: 'toxicity', label: '毒性', count: 0, color: '#ffa940' },
        { value: 'privacy', label: '隐私', count: 0, color: '#ffc53d' },
        { value: 'robustness', label: '鲁棒性', count: 0, color: '#95de64' },
        { value: 'ethics', label: '伦理', count: 0, color: '#5cdbd3' },
        { value: 'factuality', label: '事实性', count: 0, color: '#69c0ff' },
        { value: 'custom', label: '自定义', count: 0, color: '#b37feb' },
      ];
    }
  },

  // 预览数据集
  previewDataset: (id, size = 10) =>
    apiClient.get(`/evaluation/datasets/${id}/preview/`, { params: { size } }),

  // 验证数据集
  validateDataset: (id) =>
    apiClient.post(`/evaluation/datasets/${id}/validate/`),

  // 下载数据集
  downloadDataset: (id) =>
    apiClient.get(`/evaluation/datasets/${id}/download/`, {
      responseType: 'blob'
    }),

  // 数据集相关的文件操作（注意：这些是在EvaluationDatasetViewSet中）
  getTaskFiles: (datasetId) =>
    apiClient.get(`/evaluation/tasks/${datasetId}/files/`),

  downloadTaskFile: (datasetId, path) =>
    apiClient.get(`/evaluation/tasks/${datasetId}/download_file/`, {
      params: { path },
      responseType: 'blob'
    }),

  getOutputStructure: (datasetId) =>
    apiClient.get(`/evaluation/tasks/${datasetId}/output_structure/`),

  getLatestLog: (datasetId, lines = 100) =>
    apiClient.get(`/evaluation/tasks/${datasetId}/latest_log/`, {
      params: { lines }
    }),

  parseResults: (datasetId, save = false) =>
    apiClient.get(`/evaluation/tasks/${datasetId}/parse_results/`, {
      params: { save }
    }),

  // 配置管理
  getConfigs: (params = {}) =>
    apiClient.get('/evaluation/configs/', { params }),

  createConfig: (data) =>
    apiClient.post('/evaluation/configs/', data),

  getConfig: (id) =>
    apiClient.get(`/evaluation/configs/${id}/`),

  updateConfig: (id, data) =>
    apiClient.put(`/evaluation/configs/${id}/`, data),

  deleteConfig: (id) =>
    apiClient.delete(`/evaluation/configs/${id}/`),

  // 上传配置文件
  uploadConfig: (formData) =>
    apiClient.post('/evaluation/configs/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),

  // 预览配置文件
  previewConfig: (id) =>
    apiClient.get(`/evaluation/configs/${id}/preview/`),

  // 下载配置文件
  downloadConfig: (id) =>
    apiClient.get(`/evaluation/configs/${id}/download/`, {
      responseType: 'blob'
    }),

  // 验证配置文件
  validateConfig: (id) =>
    apiClient.post(`/evaluation/configs/${id}/validate/`),

  // 列出可用的模型和数据集配置
  listAvailableConfigs: (pattern = null) =>
    apiClient.get('/evaluation/configs/list_available/', {
      params: pattern ? { pattern } : {}
    }),

  // 预览Prompt（添加dataset参数）
  previewPrompts: (configId, params = {}) =>
    apiClient.get(`/evaluation/configs/${configId}/preview_prompts/`, {
      params: {
        count: params.count || 1,
        dataset: params.dataset  // 可选：数据集模式过滤
      }
    }),

  // 测试API模型
  testModel: (configId) =>
    apiClient.post(`/evaluation/configs/${configId}/test_model/`),

  // 评测任务管理
  getTasks: (params = {}) =>
    apiClient.get('/evaluation/tasks/', { params }),

  createTask: (data) =>
    apiClient.post('/evaluation/tasks/', data),

  getTask: (id) =>
    apiClient.get(`/evaluation/tasks/${id}/`),

  updateTask: (id, data) =>
    apiClient.put(`/evaluation/tasks/${id}/`, data),

  deleteTask: (id) =>
    apiClient.delete(`/evaluation/tasks/${id}/`),

  // 创建评测任务 - 使用配置文件
  createTaskWithConfig: (data) =>
    apiClient.post('/evaluation/tasks/create_task/', data),

  // 获取任务进度
  getTaskProgress: (taskId) =>
    apiClient.get(`/evaluation/tasks/${taskId}/progress/`),

  // 获取任务结果
  getTaskResults: (taskId, params = {}) =>
    apiClient.get(`/evaluation/tasks/${taskId}/results/`, { params }),

  // 取消任务
  cancelTask: (taskId) =>
    apiClient.post(`/evaluation/tasks/${taskId}/cancel/`),

  // 重新运行任务
  rerunTask: (taskId) =>
    apiClient.post(`/evaluation/tasks/${taskId}/rerun/`),

  // 获取任务日志
  getTaskLogs: (taskId) =>
    apiClient.get(`/evaluation/tasks/${taskId}/logs/`),

  // 分析错误案例
  analyzeBadCases: (taskId, force = false) =>
    apiClient.post(`/evaluation/tasks/${taskId}/analyze_bad_cases/`, { force }),

  // 合并预测结果
  mergePredictions: (taskId, clean = false) =>
    apiClient.post(`/evaluation/tasks/${taskId}/merge_predictions/`, { clean }),

  // 收集代码预测
  collectCodePredictions: (taskId) =>
    apiClient.post(`/evaluation/tasks/${taskId}/collect_code_predictions/`),

  // 对比模型
  compareModels: (taskIds, name = null, saveResult = true) =>
    apiClient.post('/evaluation/tasks/compare_models/', {
      task_ids: taskIds,
      name,
      save_result: saveResult
    }),

  // 同步运行任务（调试用）
  runSync: (taskId) =>
    apiClient.post(`/evaluation/tasks/${taskId}/run_sync/`),

  // 获取调试信息
  getDebugInfo: (taskId) =>
    apiClient.get(`/evaluation/tasks/${taskId}/debug_info/`),

  // 基准测试管理
  getBenchmarks: (params = {}) =>
    apiClient.get('/evaluation/benchmarks/', { params }),

  getBenchmark: (id) =>
    apiClient.get(`/evaluation/benchmarks/${id}/`),

  // 获取排行榜
  getLeaderboard: (params = {}) =>
    apiClient.get('/evaluation/benchmarks/leaderboard/', { params }),

  // 获取模型历史
  getModelHistory: (modelId) =>
    apiClient.get(`/evaluation/benchmarks/${modelId}/history/`),

  // 模型对比
  compareModelBenchmarks: (modelNames, datasets = []) =>
    apiClient.post('/evaluation/benchmarks/compare/', {
      model_names: modelNames,
      datasets
    }),

  // 获取统计信息
  getStatistics: () =>
    apiClient.get('/evaluation/benchmarks/statistics/'),

  // 报告管理
  generateReport: (data) =>
    apiClient.post('/evaluation/reports/generate/', data),

  getReports: (params = {}) =>
    apiClient.get('/evaluation/reports/', { params }),

  getReport: (id) =>
    apiClient.get(`/evaluation/reports/${id}/`),

  // 导出报告（添加include_raw_results参数）
  exportReport: (params = {}) => {
    const exportParams = {
      format: params.format || 'json',
      task_ids: params.task_ids || [],
      include_raw_results: params.include_raw_results || false
    };

    return apiClient.get('/evaluation/benchmarks/export_report/', {
      params: exportParams,
      responseType: exportParams.format === 'csv' ? 'blob' : 'json'
    });
  },

  // OpenCompass工具
  tools: {
    // 转换AlignmentBench格式
    convertAlignmentBench: (data) =>
      apiClient.post('/evaluation/tools/convert_alignment_bench/', data),
  }
};

// 任务轮询器
export class TaskPoller {
  constructor(taskId, onProgress, onComplete, onError) {
    this.taskId = taskId;
    this.onProgress = onProgress;
    this.onComplete = onComplete;
    this.onError = onError;
    this.polling = false;
    this.pollInterval = 2000; // 2秒
    this.maxInterval = 10000; // 最大10秒
    this.errorCount = 0;
    this.maxErrors = 3;
  }

  async poll() {
    if (!this.polling) return;

    try {
      const progress = await evaluationAPI.getTaskProgress(this.taskId);

      // 重置错误计数
      this.errorCount = 0;
      this.pollInterval = 2000;

      if (this.onProgress) {
        this.onProgress(progress);
      }

      if (progress.status === 'completed') {
        this.polling = false;
        if (this.onComplete) {
          const results = await evaluationAPI.getTaskResults(this.taskId, { include_examples: true });
          this.onComplete(results);
        }
      } else if (progress.status === 'failed' || progress.status === 'cancelled') {
        this.polling = false;
        if (this.onError) {
          this.onError(new Error(progress.error_message || `Task ${progress.status}`));
        }
      } else {
        // 继续轮询，使用动态间隔
        if (progress.progress > 50) {
          this.pollInterval = Math.min(this.pollInterval * 1.2, this.maxInterval);
        }
        setTimeout(() => this.poll(), this.pollInterval);
      }
    } catch (error) {
      this.errorCount++;

      if (this.errorCount >= this.maxErrors) {
        this.polling = false;
        if (this.onError) {
          this.onError(error);
        }
      } else {
        // 错误重试，增加间隔
        this.pollInterval = Math.min(this.pollInterval * 1.5, this.maxInterval);
        setTimeout(() => this.poll(), this.pollInterval);
      }
    }
  }

  start() {
    this.polling = true;
    this.poll();
  }

  stop() {
    this.polling = false;
  }
}

// WebSocket 连接管理（如果后端支持）
export class EvaluationWebSocket {
  constructor(taskId, onMessage, onError, onClose) {
    this.taskId = taskId;
    this.onMessage = onMessage;
    this.onError = onError;
    this.onClose = onClose;
    this.ws = null;
  }

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    const port = window.location.port || (protocol === 'wss:' ? '443' : '80');
    const wsUrl = `${protocol}//${host}:${port}/ws/evaluation/${this.taskId}/`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket connected for task:', this.taskId);
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (this.onMessage) {
            this.onMessage(data);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        if (this.onError) {
          this.onError(error);
        }
      };

      this.ws.onclose = () => {
        console.log('WebSocket closed for task:', this.taskId);
        if (this.onClose) {
          this.onClose();
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      if (this.onError) {
        this.onError(error);
      }
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// 导出工具函数
export const apiUtils = {
  // 防抖函数
  debounce: (func, wait) => {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },

  // 节流函数
  throttle: (func, limit) => {
    let inThrottle;
    return function(...args) {
      if (!inThrottle) {
        func.apply(this, args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  },

  // 格式化错误消息
  formatError: (error) => {
    if (error.response?.data?.error) {
      return error.response.data.error;
    } else if (error.response?.data?.detail) {
      return error.response.data.detail;
    } else if (error.response?.data?.message) {
      return error.response.data.message;
    } else if (error.message) {
      return error.message;
    }
    return '未知错误';
  },

  // 格式化时间
  formatDuration: (seconds) => {
    if (!seconds) return '-';
    if (seconds < 60) return `${Math.round(seconds)}秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分${Math.round(seconds % 60)}秒`;
    return `${Math.floor(seconds / 3600)}时${Math.floor((seconds % 3600) / 60)}分`;
  },

  // 格式化文件大小
  formatFileSize: (bytes) => {
    if (!bytes) return '-';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  },

  // 下载文件
  downloadFile: (blob, filename) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  },

  // 格式化日期时间
  formatDateTime: (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  },

  // 格式化百分比
  formatPercentage: (value, decimals = 1) => {
    if (value === null || value === undefined) return '-';
    return `${value.toFixed(decimals)}%`;
  },

  // 获取状态颜色
  getStatusColor: (status) => {
    const statusColors = {
      'pending': '#FFA500',
      'running': '#1890ff',
      'completed': '#52c41a',
      'failed': '#f5222d',
      'cancelled': '#999999'
    };
    return statusColors[status] || '#999999';
  },

  // 获取分数颜色
  getScoreColor: (score) => {
    if (score >= 90) return '#52c41a';
    if (score >= 80) return '#73d13d';
    if (score >= 70) return '#faad14';
    if (score >= 60) return '#fa8c16';
    return '#f5222d';
  }
};

// 导出默认对象
export default {
  chat: chatAPI,
  evaluation: evaluationAPI,
  utils: apiUtils,
  TaskPoller,
  EvaluationWebSocket,
  handleStreamResponse
};