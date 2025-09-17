// services/api.js
import axios from 'axios';
import { message } from 'antd';

// 创建axios实例
const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  }
});

// 请求拦截器
apiClient.interceptors.request.use(
  config => {
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
      const message = error.response.data?.error || error.response.data?.message || error.response.data?.detail || '请求失败';
      console.error('API Error:', message);
    } else if (error.request) {
      console.error('Network Error:', error.message);
    }
    return Promise.reject(error);
  }
);

// Chat API
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

  // 发送聊天消息
  sendMessage: async (data) => {
    const messageData = {
      message: data.message,
      conversation_id: data.conversation_id || data.session_id,
      model: data.model,
      provider: data.provider || 'ollama',
      stream: data.stream || false,
    };

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

    return apiClient.post('/chat/conversations/chat/', messageData);
  },

  // 模型管理
  getModels: (() => {
    let cache = {};
    let cacheTime = {};
    const CACHE_DURATION = 5 * 60 * 1000;

    return async (provider = null) => {
      const now = Date.now();
      const cacheKey = provider || 'all';

      if (cache[cacheKey] && cacheTime[cacheKey] && (now - cacheTime[cacheKey] < CACHE_DURATION)) {
        return cache[cacheKey];
      }

      const params = provider ? { provider } : {};
      const response = await apiClient.get('/chat/models/list_available/', { params });

      cache[cacheKey] = response;
      cacheTime[cacheKey] = now;

      return response;
    };
  })(),

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

  getConfig: () =>
    apiClient.get('/chat/models/config/'),

  updateConfig: (data) =>
    apiClient.post('/chat/models/update_config/', data),

  pullModel: (modelName) =>
    apiClient.post('/chat/models/pull/', { model_name: modelName }),
};

// Evaluation API - 修复版
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

  uploadDataset: (formData) =>
    apiClient.post('/evaluation/datasets/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),

  getDatasetCategories: async () => {
    try {
      return await apiClient.get('/evaluation/datasets/categories/');
    } catch (error) {
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

  previewDataset: (id, size = 10) =>
    apiClient.get(`/evaluation/datasets/${id}/preview/`, { params: { size } }),

  validateDataset: (id) =>
    apiClient.post(`/evaluation/datasets/${id}/validate/`),

  downloadDataset: (id) =>
    apiClient.get(`/evaluation/datasets/${id}/download/`, {
      responseType: 'blob'
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

  uploadConfig: (formData) =>
    apiClient.post('/evaluation/configs/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }),

  previewConfig: (id) =>
    apiClient.get(`/evaluation/configs/${id}/preview/`),

  downloadConfig: (id) =>
    apiClient.get(`/evaluation/configs/${id}/download/`, {
      responseType: 'blob'
    }),

  validateConfig: (id) =>
    apiClient.post(`/evaluation/configs/${id}/validate/`),

  listAvailableConfigs: (pattern = null) =>
    apiClient.get('/evaluation/configs/list_available/', {
      params: pattern ? { pattern } : {}
    }),

  previewPrompts: (configId, params = {}) =>
    apiClient.get(`/evaluation/configs/${configId}/preview_prompts/`, {
      params: {
        count: params.count || 1,
        dataset: params.dataset
      }
    }),

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

  createTaskWithConfig: (data) =>
    apiClient.post('/evaluation/tasks/create_task/', data),

  getTaskProgress: (taskId) =>
    apiClient.get(`/evaluation/tasks/${taskId}/progress/`),

  getTaskResults: (taskId, params = {}) =>
    apiClient.get(`/evaluation/tasks/${taskId}/results/`, { params }),

  cancelTask: (taskId) =>
    apiClient.post(`/evaluation/tasks/${taskId}/cancel/`),

  rerunTask: (taskId) =>
    apiClient.post(`/evaluation/tasks/${taskId}/rerun/`),

  getTaskLogs: (taskId) =>
    apiClient.get(`/evaluation/tasks/${taskId}/logs/`),

  // 任务文件操作 - 修复的API
  getTaskFiles: (taskId) =>
    apiClient.get(`/evaluation/tasks/${taskId}/files/`),

  downloadTaskFile: (taskId, path) =>
    apiClient.get(`/evaluation/tasks/${taskId}/download_file/`, {
      params: { path },
      responseType: 'blob'
    }),

  getOutputStructure: (taskId) =>
    apiClient.get(`/evaluation/tasks/${taskId}/output_structure/`),

  getLatestLog: (taskId, lines = 100) =>
    apiClient.get(`/evaluation/tasks/${taskId}/latest_log/`, {
      params: { lines }
    }),

  parseResults: (taskId, save = false) =>
    apiClient.get(`/evaluation/tasks/${taskId}/parse_results/`, {
      params: { save }
    }),

  analyzeBadCases: (taskId, force = false) =>
    apiClient.post(`/evaluation/tasks/${taskId}/analyze_bad_cases/`, { force }),

  mergePredictions: (taskId, clean = false) =>
    apiClient.post(`/evaluation/tasks/${taskId}/merge_predictions/`, { clean }),

  collectCodePredictions: (taskId) =>
    apiClient.post(`/evaluation/tasks/${taskId}/collect_code_predictions/`),

  compareModels: (taskIds, name = null, saveResult = true) =>
    apiClient.post('/evaluation/tasks/compare_models/', {
      task_ids: taskIds,
      name,
      save_result: saveResult
    }),

  runSync: (taskId) =>
    apiClient.post(`/evaluation/tasks/${taskId}/run_sync/`),

  getDebugInfo: (taskId) =>
    apiClient.get(`/evaluation/tasks/${taskId}/debug_info/`),

  // 基准测试管理
  getBenchmarks: (params = {}) =>
    apiClient.get('/evaluation/benchmarks/', { params }),

  getBenchmark: (id) =>
    apiClient.get(`/evaluation/benchmarks/${id}/`),

  getLeaderboard: (params = {}) =>
    apiClient.get('/evaluation/benchmarks/leaderboard/', { params }),

  getModelHistory: (modelId) =>
    apiClient.get(`/evaluation/benchmarks/${modelId}/history/`),

  compareModelBenchmarks: (modelNames, datasets = []) =>
    apiClient.post('/evaluation/benchmarks/compare/', {
      model_names: modelNames,
      datasets
    }),

  getStatistics: () =>
    apiClient.get('/evaluation/benchmarks/statistics/'),

  generateReport: (data) =>
    apiClient.post('/evaluation/reports/generate/', data),

  getReports: (params = {}) =>
    apiClient.get('/evaluation/reports/', { params }),

  getReport: (id) =>
    apiClient.get(`/evaluation/reports/${id}/`),

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
    this.pollInterval = 2000;
    this.maxInterval = 10000;
    this.errorCount = 0;
    this.maxErrors = 3;
  }

  async poll() {
    if (!this.polling) return;

    try {
      const progress = await evaluationAPI.getTaskProgress(this.taskId);

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

// 导出工具函数
export const apiUtils = {
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

  formatError: (error) => {
    if (!error.response) {
      if (error.message === 'Network Error') {
        return '网络连接失败，请检查网络设置';
      }
      return error.message || '未知错误';
    }

    const status = error.response.status;
    const data = error.response.data;

    switch (status) {
      case 400:
        if (data.errors && typeof data.errors === 'object') {
          const errorMessages = [];
          for (const [field, messages] of Object.entries(data.errors)) {
            if (Array.isArray(messages)) {
              errorMessages.push(`${field}: ${messages.join(', ')}`);
            } else {
              errorMessages.push(`${field}: ${messages}`);
            }
          }
          return errorMessages.join('; ');
        }
        break;
      case 401:
        return '未授权，请重新登录';
      case 403:
        return '没有权限执行此操作';
      case 404:
        return '请求的资源不存在';
      case 500:
        return '服务器错误，请稍后重试';
      case 502:
      case 503:
        return '服务暂时不可用，请稍后重试';
    }

    if (data?.error) return data.error;
    if (data?.detail) return data.detail;
    if (data?.message) return data.message;
    if (data?.msg) return data.msg;
    
    if (typeof data === 'string') return data;

    return `请求失败 (${status})`;
  },

  handleApiCall: async (apiCall, options = {}) => {
    const {
      loadingMessage = '处理中...',
      successMessage = '操作成功',
      errorMessage = '操作失败',
      showLoading = true,
      showSuccess = true,
      showError = true,
      onSuccess,
      onError,
      finally: finallyCallback
    } = options;

    let hideLoading;
    if (showLoading) {
      hideLoading = message.loading(loadingMessage, 0);
    }

    try {
      const result = await apiCall();
      
      if (hideLoading) hideLoading();
      
      if (showSuccess) {
        message.success(successMessage);
      }
      
      if (onSuccess) {
        onSuccess(result);
      }
      
      return result;
    } catch (error) {
      if (hideLoading) hideLoading();
      
      const formattedError = apiUtils.formatError(error);
      
      if (showError) {
        message.error(`${errorMessage}: ${formattedError}`);
      }
      
      if (onError) {
        onError(error, formattedError);
      }
      
      throw error;
    } finally {
      if (finallyCallback) {
        finallyCallback();
      }
    }
  },

  formatDuration: (seconds) => {
    if (!seconds) return '-';
    if (seconds < 60) return `${Math.round(seconds)}秒`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分${Math.round(seconds % 60)}秒`;
    return `${Math.floor(seconds / 3600)}时${Math.floor((seconds % 3600) / 60)}分`;
  },

  formatFileSize: (bytes) => {
    if (!bytes) return '-';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  },

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

  formatPercentage: (value, decimals = 1) => {
    if (value === null || value === undefined) return '-';
    return `${value.toFixed(decimals)}%`;
  },

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

  getScoreColor: (score) => {
    if (score >= 90) return '#52c41a';
    if (score >= 80) return '#73d13d';
    if (score >= 70) return '#faad14';
    if (score >= 60) return '#fa8c16';
    return '#f5222d';
  }
};

// 处理流式响应
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

export default {
  chat: chatAPI,
  evaluation: evaluationAPI,
  utils: apiUtils,
  TaskPoller,
  handleStreamResponse
};