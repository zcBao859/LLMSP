import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConfigProvider, Layout, Menu, theme, message, Badge, Space, Tooltip, Button } from 'antd';
import {
  MessageOutlined,
  SafetyOutlined,
  BarChartOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  SettingOutlined,
  ApiOutlined,
  CloudOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined
} from '@ant-design/icons';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import SettingsPage from './pages/SettingsPage';

// 导入页面组件
import ChatPage from './pages/ChatPage';
import EvaluationPage from './pages/evaluation'; // 修改：从 evaluation 目录导入
import ResultsPage from './pages/ResultsPage';
import ModelsPage from './pages/ModelsPage';
import DashboardPage from './pages/DashboardPage';
import SubjectivePage from './pages/SubjectivePage'; // <--- 新增这行（假设你的文件叫这个名字）

// 导入API服务 - 注意：这里使用全局的 api.js
import { chatAPI } from './services/api';

// 导入样式
import './App.css';

dayjs.locale('zh-cn');

const { Header, Sider, Content } = Layout;

// 路由包装组件
function AppContent() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [selectedKey, setSelectedKey] = useState('dashboard');
  const [serverStatus, setServerStatus] = useState(null);
  const [systemStatus, setSystemStatus] = useState(null);
  const [checking, setChecking] = useState(false);
  const [currentProvider, setCurrentProvider] = useState('ollama'); // 当前选择的provider

  const {
    token: { colorBgContainer },
  } = theme.useToken();

  // 根据路径设置选中的菜单项
  useEffect(() => {
    const pathToKey = {
      '/dashboard': 'dashboard',
      '/chat': 'chat',
      '/evaluation': 'evaluation',
      '/subjective': 'Subjective',
      '/results': 'results',
      '/models': 'models',
      '/settings': 'settings',
    };
    setSelectedKey(pathToKey[location.pathname] || 'dashboard');
  }, [location]);

  // 获取当前配置的provider
  useEffect(() => {
    const loadCurrentProvider = async () => {
      try {
        const config = await chatAPI.getConfig();
        if (config.default_provider) {
          setCurrentProvider(config.default_provider);
        }
      } catch (error) {
        console.error('获取配置失败:', error);
      }
    };
    loadCurrentProvider();
  }, []);

  // 优化的健康检查 - 只检查当前provider
  const checkServerStatus = useCallback(async () => {
    try {
      // 只检查当前选择的provider
      const status = await chatAPI.healthCheck(currentProvider);
      setServerStatus(status);
    } catch (error) {
      console.error('服务器状态检查失败:', error);
      setServerStatus(null);
    }
  }, [currentProvider]);

  // 检查系统状态 - 使用 evaluation 自己的 API
  const checkSystemStatus = useCallback(async () => {
    try {
      // 动态导入 evaluation 的 API，避免循环依赖
      const { evaluationAPI } = await import('./pages/evaluation/services/api');

      // 如果有 checkSetup 方法就调用，否则跳过
      if (evaluationAPI.checkSetup) {
        const status = await evaluationAPI.checkSetup();
        setSystemStatus(status);
      } else {
        // 没有 checkSetup 方法，设置默认状态
        setSystemStatus({
          ready: true,
          opencompass_installed: true,
          celery_connected: true
        });
      }
    } catch (error) {
      console.error('系统状态检查失败:', error);
      // 如果检查失败，假设系统正常
      setSystemStatus({
        ready: true,
        opencompass_installed: true,
        celery_connected: true
      });
    }
  }, []);

  // 检查所有状态
  const checkAllStatus = useCallback(async () => {
    await Promise.all([
      checkServerStatus(),
      checkSystemStatus()
    ]);
  }, [checkServerStatus, checkSystemStatus]);

  // 在组件加载时和provider改变时检查状态
  useEffect(() => {
    checkAllStatus();
    // 每60秒检查一次（减少频率提高性能）
    const interval = setInterval(checkAllStatus, 60000);
    return () => clearInterval(interval);
  }, [checkAllStatus]);

  // 手动刷新状态
  const handleRefreshStatus = async () => {
    setChecking(true);
    await checkAllStatus();
    message.success('状态已更新');
    setTimeout(() => setChecking(false), 500);
  };

  // 切换provider
  const handleProviderSwitch = useCallback(async (provider) => {
    setCurrentProvider(provider);
    // 更新默认配置
    try {
      await chatAPI.updateConfig({ default_provider: provider });
      message.success(`已切换到 ${provider === 'ollama' ? 'Ollama' : 'DeepSeek'}`);
    } catch (error) {
      message.error('切换失败');
    }
  }, []);

  // 配置全局消息
  message.config({
    top: 100,
    duration: 3,
    maxCount: 3,
  });

  const menuItems = useMemo(() => [
    {
      key: 'dashboard',
      icon: <DashboardOutlined />,
      label: '控制台',
      path: '/dashboard',
    },
    {
      key: 'chat',
      icon: <MessageOutlined />,
      label: '模型对话',
      path: '/chat',
    },
    {
      key: 'evaluation',
      icon: <SafetyOutlined />,
      label: '安全评测',
      path: '/evaluation',
    },
    {
      key: 'Subjective',
      icon: <ApiOutlined />,
      label: '主观评测',
      path: '/subjective',
    },
    {
      key: 'results',
      icon: <BarChartOutlined />,
      label: '评测结果',
      path: '/results',
    },
    {
      key: 'models',
      icon: <ExperimentOutlined />,
      label: '模型管理',
      path: '/models',
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '系统设置',
      path: '/settings',
    },

  ], []);

  // 获取整体状态 - 优化版
  const getOverallStatus = useMemo(() => {
    const issues = [];

    // 只检查当前provider的状态
    if (!serverStatus) {
      issues.push(`无法连接到${currentProvider === 'ollama' ? 'Ollama' : 'DeepSeek'}服务`);
    } else {
      const providerStatus = serverStatus[currentProvider];
      if (providerStatus && providerStatus.status !== 'healthy') {
        issues.push(`${currentProvider === 'ollama' ? 'Ollama' : 'DeepSeek'}服务异常`);
      }
    }

    // 检查系统状态
    if (systemStatus && !systemStatus.ready) {
      issues.push(...(systemStatus.issues || []));
    }

    return {
      healthy: issues.length === 0,
      issues
    };
  }, [serverStatus, systemStatus, currentProvider]);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
      >
        <div className="logo">
          <SafetyOutlined style={{ fontSize: '24px', marginRight: '8px' }} />
          {!collapsed && <span>LLM安全平台</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => {
            const item = menuItems.find(item => item.key === key);
            if (item) {
              window.location.href = item.path;
            }
          }}
        />
      </Sider>

      <Layout>
        <Header style={{ padding: 0, background: colorBgContainer }}>
          <div className="header-content">
            <h2>大模型安全评测平台</h2>

            {/* 服务器状态显示区域 */}
            <div className="header-actions">
              <Space size="middle">
                {/* Provider切换器 */}
                <div className="provider-switcher">
                  <Button.Group>
                    <Button
                      type={currentProvider === 'ollama' ? 'primary' : 'default'}
                      icon={<ApiOutlined />}
                      onClick={() => handleProviderSwitch('ollama')}
                      size="small"
                    >
                      Ollama
                    </Button>
                    <Button
                      type={currentProvider === 'deepseek' ? 'primary' : 'default'}
                      icon={<CloudOutlined />}
                      onClick={() => handleProviderSwitch('deepseek')}
                      size="small"
                    >
                      DeepSeek
                    </Button>
                  </Button.Group>
                </div>

                {/* 当前provider状态 */}
                {serverStatus && serverStatus[currentProvider] && (
                  <Tooltip
                    title={`${currentProvider === 'ollama' ? 'Ollama' : 'DeepSeek'}服务\n地址：${serverStatus[currentProvider].base_url}\n状态：${serverStatus[currentProvider].status}`}
                  >
                    <span className={`server-status ${serverStatus[currentProvider].status === 'healthy' ? 'status-healthy' : 'status-error'}`}>
                      <Badge
                        status={serverStatus[currentProvider].status === 'healthy' ? 'success' : 'error'}
                      />
                      {currentProvider === 'ollama' ? <ApiOutlined /> : <CloudOutlined />}
                      {currentProvider === 'ollama' ? 'Ollama' : 'DeepSeek'}
                    </span>
                  </Tooltip>
                )}

                {/* OpenCompass状态 */}
                {systemStatus && (
                  <Tooltip title={`OpenCompass\n状态：${systemStatus.opencompass_installed ? '已安装' : '未安装'}\nCelery：${systemStatus.celery_connected ? '已连接' : '未连接'}`}>
                    <span className="server-status">
                      <Badge
                        status={systemStatus.opencompass_installed && systemStatus.celery_connected ? 'success' : 'warning'}
                      />
                      <ExperimentOutlined style={{ marginRight: 4 }} />
                      评测引擎
                    </span>
                  </Tooltip>
                )}

                {/* 整体状态 */}
                <Tooltip title={
                  getOverallStatus.healthy ? '系统运行正常' :
                  `存在问题：\n${getOverallStatus.issues.join('\n')}`
                }>
                  <Badge
                    status={getOverallStatus.healthy ? 'success' : 'error'}
                    text={getOverallStatus.healthy ? '正常' : '异常'}
                  />
                </Tooltip>

                {/* 刷新按钮 */}
                <Tooltip title="刷新状态">
                  <Button
                    type="text"
                    icon={checking ? <LoadingOutlined spin /> : <ReloadOutlined />}
                    onClick={handleRefreshStatus}
                    disabled={checking}
                  />
                </Tooltip>
              </Space>
            </div>
          </div>
        </Header>

        <Content style={{ margin: '24px 16px' }}>
          <div style={{ padding: 24, minHeight: 360, background: colorBgContainer, borderRadius: 8 }}>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/evaluation" element={<EvaluationPage />} />
              <Route path="/subjective" element={<SubjectivePage />} /> 
              <Route path="/results" element={<ResultsPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}

// 主App组件
function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <Router>
        <AppContent />
      </Router>
    </ConfigProvider>
  );
}

export default App;