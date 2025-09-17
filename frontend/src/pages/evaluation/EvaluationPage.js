// EvaluationPage.js
import React, { useState, useEffect, useRef } from 'react';
import { Card, Steps, message, Modal } from 'antd';
import { DatabaseOutlined, SettingOutlined, ExperimentOutlined } from '@ant-design/icons';

// 导入API服务
import { evaluationAPI, TaskPoller, apiUtils } from './services/api';

// 导入组件
import ConfigSelection from './components/ConfigSelection';
import TaskConfiguration from './components/TaskConfiguration';
import TaskList from './components/TaskList';

// 导入弹窗组件
import DatasetUploadModal from './components/Modals/DatasetUploadModal';
import ConfigUploadModal from './components/Modals/ConfigUploadModal';
import TaskDetailModal from './components/Modals/TaskDetailModal';
import BadCaseModal from './components/Modals/BadCaseModal';
import ModelCompareModal from './components/Modals/ModelCompareModal';
import PromptPreviewModal from './components/Modals/PromptPreviewModal';

// 导入常量和工具
import { DEFAULT_FORM_VALUES, EVALUATION_STEPS, DATASET_CATEGORIES } from './utils/constants';
import {
  validateDatasetUpload,
  validateConfigUpload,
  validateTaskCreation,
  showValidationErrors
} from './services/validation';

// 导入样式
import './styles/evaluation.css';

const { Step } = Steps;

const EvaluationPage = () => {
  // 基础状态
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [datasets, setDatasets] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [categories, setCategories] = useState(DATASET_CATEGORIES);

  // 轮询管理
  const taskPollersRef = useRef({});

  // 表单数据
  const [selectedConfig, setSelectedConfig] = useState(null);
  const [taskName, setTaskName] = useState('');
  const [taskConfig, setTaskConfig] = useState({ priority: 'normal' });

  // 弹窗状态
  const [modals, setModals] = useState({
    uploadDataset: false,
    uploadConfig: false,
    taskDetail: false,
    badCase: false,
    modelCompare: false,
    promptPreview: false
  });

  // 弹窗数据
  const [selectedTask, setSelectedTask] = useState(null);
  const [taskResults, setTaskResults] = useState(null);
  const [taskFiles, setTaskFiles] = useState(null);
  const [taskLogs, setTaskLogs] = useState('');
  const [badCases, setBadCases] = useState(null);
  const [compareResults, setCompareResults] = useState(null);
  const [promptPreviews, setPromptPreviews] = useState('');

  // 上传表单数据
  const [uploadDatasetFormData, setUploadDatasetFormData] = useState(DEFAULT_FORM_VALUES.dataset);
  const [uploadConfigFormData, setUploadConfigFormData] = useState(DEFAULT_FORM_VALUES.config);

  // 辅助函数：控制弹窗显示
  const showModal = (modalName) => {
    setModals(prev => ({ ...prev, [modalName]: true }));
  };

  const hideModal = (modalName) => {
    setModals(prev => ({ ...prev, [modalName]: false }));
  };

  // 组件挂载时加载数据
  useEffect(() => {
    loadInitialData();

    // 清理函数
    return () => {
      Object.values(taskPollersRef.current).forEach(poller => poller.stop());
    };
  }, []);

  // 数据加载函数
  const loadInitialData = async () => {
    try {
      setLoading(true);
      await Promise.all([
        loadDatasets(),
        loadTasks(),
        loadCategories(),
        loadConfigs()
      ]);
    } catch (error) {
      message.error('加载数据失败: ' + apiUtils.formatError(error));
    } finally {
      setLoading(false);
    }
  };

  const loadDatasets = async () => {
    try {
      const response = await evaluationAPI.getDatasets();
      setDatasets(response.results || []);
    } catch (error) {
      console.error('加载数据集失败:', error);
    }
  };

  const loadTasks = async () => {
    try {
      const response = await evaluationAPI.getTasks({ ordering: '-created_at' });
      setTasks(response.results || []);

      // 为运行中的任务启动轮询
      response.results.forEach(task => {
        if (task.status === 'running' || task.status === 'pending') {
          startTaskPoller(task.id);
        }
      });
    } catch (error) {
      console.error('加载任务失败:', error);
    }
  };

  const loadCategories = async () => {
    try {
      const response = await evaluationAPI.getDatasetCategories();
      setCategories(response);
    } catch (error) {
      console.error('加载类别失败:', error);
      // 使用默认类别
      setCategories(DATASET_CATEGORIES);
    }
  };

  const loadConfigs = async () => {
    try {
      const response = await evaluationAPI.getConfigs();
      setConfigs(response.results || []);
    } catch (error) {
      console.error('加载配置失败:', error);
    }
  };

  // 任务轮询管理
  const startTaskPoller = (taskId) => {
    if (taskPollersRef.current[taskId]) return;

    const poller = new TaskPoller(
      taskId,
      (progress) => {
        setTasks(prev => prev.map(task =>
          task.id === taskId
            ? { ...task, progress: progress.progress, status: progress.status }
            : task
        ));
      },
      (results) => {
        message.success(`任务 ${taskId} 已完成`);
        loadTasks();
        if (taskPollersRef.current[taskId]) {
          taskPollersRef.current[taskId].stop();
          delete taskPollersRef.current[taskId];
        }
      },
      (error) => {
        message.error(`任务 ${taskId} 失败: ${error.message}`);
        loadTasks();
        if (taskPollersRef.current[taskId]) {
          taskPollersRef.current[taskId].stop();
          delete taskPollersRef.current[taskId];
        }
      }
    );

    poller.start();
    taskPollersRef.current[taskId] = poller;
  };

  // 创建评测任务
  const createEvaluationTask = async () => {
    // 验证表单
    const validation = validateTaskCreation({ name: taskName, priority: taskConfig.priority }, selectedConfig);
    if (!validation.valid) {
      showValidationErrors(validation.errors);
      return;
    }

    try {
      setLoading(true);

      const response = await evaluationAPI.createTaskWithConfig({
        name: taskName || `OpenCompass评测 - ${new Date().toLocaleString()}`,
        config_id: selectedConfig,
        priority: taskConfig.priority
      });

      message.success('OpenCompass评测任务已创建');
      setTasks(prev => [response, ...prev]);
      startTaskPoller(response.id);

      setCurrentStep(2);
      resetForm();

    } catch (error) {
      message.error('创建任务失败: ' + apiUtils.formatError(error));
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setSelectedConfig(null);
    setTaskName('');
    setTaskConfig({ priority: 'normal' });
  };

  // 数据集上传
  const handleDatasetUpload = async () => {
    const validation = validateDatasetUpload(uploadDatasetFormData);
    if (!validation.valid) {
      showValidationErrors(validation.errors);
      return;
    }

    try {
      setLoading(true);
      const formData = new FormData();

      formData.append('file', uploadDatasetFormData.file);
      formData.append('name', uploadDatasetFormData.name);
      formData.append('display_name', uploadDatasetFormData.display_name);
      formData.append('category', uploadDatasetFormData.category);
      formData.append('description', uploadDatasetFormData.description || '');

      const response = await evaluationAPI.uploadDataset(formData);

      message.success(`数据集上传成功，包含 ${response.sample_count} 个样本`);
      hideModal('uploadDataset');
      setUploadDatasetFormData(DEFAULT_FORM_VALUES.dataset);

      loadDatasets();
    } catch (error) {
      message.error('数据集上传失败: ' + apiUtils.formatError(error));
    } finally {
      setLoading(false);
    }
  };

  // 配置文件上传
  const handleConfigUpload = async () => {
    const validation = validateConfigUpload(uploadConfigFormData);
    if (!validation.valid) {
      showValidationErrors(validation.errors);
      return;
    }

    try {
      setLoading(true);
      const formData = new FormData();

      formData.append('file', uploadConfigFormData.file);
      formData.append('name', uploadConfigFormData.name);
      formData.append('display_name', uploadConfigFormData.display_name);
      formData.append('description', uploadConfigFormData.description || '');

      const response = await evaluationAPI.uploadConfig(formData);

      message.success('配置文件上传成功');
      hideModal('uploadConfig');
      setUploadConfigFormData(DEFAULT_FORM_VALUES.config);

      loadConfigs();
    } catch (error) {
      message.error('配置文件上传失败: ' + apiUtils.formatError(error));
    } finally {
      setLoading(false);
    }
  };

  // 任务操作
  const cancelTask = async (taskId) => {
    Modal.confirm({
      title: '确认取消',
      content: '确定要取消该评测任务吗？',
      onOk: async () => {
        try {
          await evaluationAPI.cancelTask(taskId);

          if (taskPollersRef.current[taskId]) {
            taskPollersRef.current[taskId].stop();
            delete taskPollersRef.current[taskId];
          }

          message.success('任务已取消');
          loadTasks();
        } catch (error) {
          message.error('取消任务失败: ' + apiUtils.formatError(error));
        }
      },
    });
  };

  const rerunTask = async (taskId) => {
    try {
      const response = await evaluationAPI.rerunTask(taskId);
      message.success('任务已重新运行');

      setTasks(prev => [response, ...prev]);
      startTaskPoller(response.id);
    } catch (error) {
      message.error('重新运行失败: ' + apiUtils.formatError(error));
    }
  };

  const viewTaskDetail = async (task) => {
    setSelectedTask(task);
    showModal('taskDetail');

    if (task.status === 'completed') {
      try {
        setLoading(true);
        const results = await evaluationAPI.getTaskResults(task.id, { include_examples: true });
        setTaskResults(results);
      } catch (error) {
        console.error('获取任务结果失败:', error);
      } finally {
        setLoading(false);
      }
    }
  };

  const analyzeBadCases = async (taskId) => {
    try {
      setLoading(true);
      const response = await evaluationAPI.analyzeBadCases(taskId);
      setBadCases(response);
      showModal('badCase');
      message.success('错误案例分析完成');
    } catch (error) {
      message.error('分析失败: ' + apiUtils.formatError(error));
    } finally {
      setLoading(false);
    }
  };

  const loadTaskFiles = async (taskId) => {
    try {
      const response = await evaluationAPI.getTaskFiles(taskId);
      setTaskFiles(response);
    } catch (error) {
      message.error('加载文件失败: ' + apiUtils.formatError(error));
    }
  };

  const loadTaskLogs = async (taskId, lines = 100) => {
    try {
      const response = await evaluationAPI.getLatestLog(taskId, lines);
      setTaskLogs(response.content || '暂无日志');
    } catch (error) {
      message.error('加载日志失败: ' + apiUtils.formatError(error));
    }
  };

  const downloadTaskFile = async (taskId, path) => {
    try {
      const blob = await evaluationAPI.downloadTaskFile(taskId, path);
      const filename = path.split('/').pop();
      apiUtils.downloadFile(blob, filename);
    } catch (error) {
      message.error('下载失败: ' + apiUtils.formatError(error));
    }
  };

  const previewPrompts = async (configId, datasetPattern = null) => {
    try {
      setLoading(true);
      const response = await evaluationAPI.previewPrompts(configId, {
        count: 3,
        dataset: datasetPattern
      });
      setPromptPreviews(response.prompts || '');
      showModal('promptPreview');
    } catch (error) {
      message.error('预览失败: ' + apiUtils.formatError(error));
    } finally {
      setLoading(false);
    }
  };

  const testApiModel = async (configId) => {
    try {
      setLoading(true);
      const response = await evaluationAPI.testModel(configId);
      Modal.info({
        title: '模型测试结果',
        width: 800,
        content: (
          <pre style={{ maxHeight: 400, overflow: 'auto' }}>
            {response.test_output}
          </pre>
        )
      });
    } catch (error) {
      message.error('测试失败: ' + apiUtils.formatError(error));
    } finally {
      setLoading(false);
    }
  };

  const compareModels = async () => {
    const completedTasks = tasks.filter(t => t.status === 'completed');
    if (completedTasks.length < 2) {
      message.warning('需要至少2个已完成的任务进行对比');
      return;
    }

    const taskIds = completedTasks.slice(0, 5).map(t => t.id);

    try {
      setLoading(true);
      const response = await evaluationAPI.compareModels(taskIds);
      setCompareResults(response);
      showModal('modelCompare');
    } catch (error) {
      message.error('对比失败: ' + apiUtils.formatError(error));
    } finally {
      setLoading(false);
    }
  };

  const exportReport = async (format = 'json', includeRaw = false) => {
    const completedTaskIds = tasks
      .filter(t => t.status === 'completed')
      .map(t => t.id)
      .slice(0, 10);

    if (completedTaskIds.length === 0) {
      message.warning('没有已完成的任务可以导出');
      return;
    }

    try {
      const params = {
        format,
        task_ids: completedTaskIds,
        include_raw_results: includeRaw
      };

      const response = await evaluationAPI.exportReport(params);

      if (format === 'csv') {
        apiUtils.downloadFile(response, `evaluation_report_${Date.now()}.csv`);
      } else {
        const blob = new Blob([JSON.stringify(response, null, 2)], { type: 'application/json' });
        apiUtils.downloadFile(blob, `evaluation_report_${Date.now()}.json`);
      }

      message.success('报告导出成功');
    } catch (error) {
      message.error('导出失败: ' + apiUtils.formatError(error));
    }
  };

  const viewConfigDetail = (config) => {
    Modal.info({
      title: '配置详情',
      width: 800,
      content: (
        <div>
          <p><strong>名称:</strong> {config.display_name}</p>
          <p><strong>描述:</strong> {config.description || '暂无'}</p>
          <p><strong>模型:</strong> {config.model_names?.join(', ') || '无'}</p>
          <p><strong>数据集:</strong> {config.dataset_names?.join(', ') || '无'}</p>
        </div>
      )
    });
  };

  // 渲染步骤内容
  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <ConfigSelection
            configs={configs}
            selectedConfig={selectedConfig}
            setSelectedConfig={setSelectedConfig}
            loading={loading}
            onUploadClick={() => showModal('uploadConfig')}
            onRefresh={loadConfigs}
            onViewDetail={viewConfigDetail}
            onPreviewPrompts={previewPrompts}
            onTestModel={testApiModel}
            onNext={() => setCurrentStep(1)}
          />
        );

      case 1:
        return (
          <TaskConfiguration
            taskName={taskName}
            setTaskName={setTaskName}
            taskConfig={taskConfig}
            setTaskConfig={setTaskConfig}
            selectedConfig={selectedConfig}
            configs={configs}
            onPrevious={() => setCurrentStep(0)}
            onSubmit={createEvaluationTask}
            loading={loading}
          />
        );

      case 2:
        return (
          <TaskList
            tasks={tasks}
            loading={loading}
            onCreateNew={() => {
              setCurrentStep(0);
              resetForm();
            }}
            onViewDetail={viewTaskDetail}
            onAnalyzeBadCases={analyzeBadCases}
            onCancelTask={cancelTask}
            onRerunTask={rerunTask}
            onCompareModels={compareModels}
            onExportReport={exportReport}
            onRefresh={loadTasks}
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="evaluation-page">
      <Card>
        <Steps current={currentStep}>
          {EVALUATION_STEPS.map((step, index) => (
            <Step
              key={index}
              title={step.title}
              icon={
                step.icon === 'DatabaseOutlined' ? <DatabaseOutlined /> :
                step.icon === 'SettingOutlined' ? <SettingOutlined /> :
                <ExperimentOutlined />
              }
            />
          ))}
        </Steps>
      </Card>

      <div style={{ marginTop: 24 }}>
        {renderStepContent()}
      </div>

      {/* 数据集上传弹窗 */}
      <DatasetUploadModal
        visible={modals.uploadDataset}
        loading={loading}
        formData={uploadDatasetFormData}
        setFormData={setUploadDatasetFormData}
        onOk={handleDatasetUpload}
        onCancel={() => {
          hideModal('uploadDataset');
          setUploadDatasetFormData(DEFAULT_FORM_VALUES.dataset);
        }}
      />

      {/* 配置文件上传弹窗 */}
      <ConfigUploadModal
        visible={modals.uploadConfig}
        loading={loading}
        formData={uploadConfigFormData}
        setFormData={setUploadConfigFormData}
        onOk={handleConfigUpload}
        onCancel={() => {
          hideModal('uploadConfig');
          setUploadConfigFormData(DEFAULT_FORM_VALUES.config);
        }}
      />

      {/* 任务详情弹窗 */}
      <TaskDetailModal
        visible={modals.taskDetail}
        task={selectedTask}
        loading={loading}
        taskResults={taskResults}
        taskFiles={taskFiles}
        taskLogs={taskLogs}
        onCancel={() => {
          hideModal('taskDetail');
          setSelectedTask(null);
          setTaskResults(null);
          setTaskFiles(null);
          setTaskLogs('');
        }}
        onLoadFiles={loadTaskFiles}
        onLoadLogs={loadTaskLogs}
        onDownloadFile={downloadTaskFile}
        onViewFile={(file) => {
          message.info('文件查看功能待实现');
        }}
      />

      {/* 错误案例分析弹窗 */}
      <BadCaseModal
        visible={modals.badCase}
        badCases={badCases}
        onCancel={() => {
          hideModal('badCase');
          setBadCases(null);
        }}
      />

      {/* 模型对比弹窗 */}
      <ModelCompareModal
        visible={modals.modelCompare}
        compareResults={compareResults}
        onCancel={() => {
          hideModal('modelCompare');
          setCompareResults(null);
        }}
      />

      {/* Prompt预览弹窗 */}
      <PromptPreviewModal
        visible={modals.promptPreview}
        promptPreviews={promptPreviews}
        onCancel={() => {
          hideModal('promptPreview');
          setPromptPreviews('');
        }}
      />
    </div>
  );
};

export default EvaluationPage;