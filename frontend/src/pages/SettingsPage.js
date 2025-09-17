import React, { useState, useEffect } from 'react';
import {
  Card, Form, Input, Button, Space, message, Spin,
  Alert, Divider, Typography, Tabs, Radio, Row, Col,
  Badge, Descriptions
} from 'antd';
import {
  SettingOutlined, SaveOutlined, ReloadOutlined,
  ApiOutlined, CloudOutlined, KeyOutlined,
  CheckCircleOutlined, ExclamationCircleOutlined
} from '@ant-design/icons';
import { chatAPI } from '../services/api';

const { Title, Text } = Typography;
const { TabPane } = Tabs;

const SettingsPage = () => {
  const [ollamaForm] = Form.useForm();
  const [deepseekForm] = Form.useForm();
  const [generalForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [currentConfig, setCurrentConfig] = useState(null);
  const [healthStatus, setHealthStatus] = useState({
    ollama: null,
    deepseek: null
  });

  useEffect(() => {
    loadConfig();
    checkHealth();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const config = await chatAPI.getConfig();
      setCurrentConfig(config);

      // 设置Ollama表单
      if (config.ollama) {
        ollamaForm.setFieldsValue({
          ollama_base_url: config.ollama.base_url,
          ollama_default_model: config.ollama.default_model,
        });
      }

      // 设置DeepSeek表单
      if (config.deepseek) {
        deepseekForm.setFieldsValue({
          deepseek_api_key: config.deepseek.api_key,
          deepseek_base_url: config.deepseek.base_url,
          deepseek_default_model: config.deepseek.default_model,
        });
      }

      // 设置通用表单
      generalForm.setFieldsValue({
        default_provider: config.default_provider || 'ollama',
      });
    } catch (error) {
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  };

  const checkHealth = async () => {
    try {
      const result = await chatAPI.healthCheck();
      setHealthStatus({
        ollama: result.ollama || null,
        deepseek: result.deepseek || null,
      });
    } catch (error) {
      console.error('健康检查失败:', error);
    }
  };

  const handleSaveOllama = async (values) => {
    try {
      setLoading(true);
      await chatAPI.updateConfig({
        ollama_base_url: values.ollama_base_url,
        ollama_default_model: values.ollama_default_model,
      });
      message.success('Ollama配置更新成功');
      await loadConfig();
      await checkHealth();
    } catch (error) {
      message.error(error.response?.data?.error || '更新配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveDeepSeek = async (values) => {
    try {
      setLoading(true);
      await chatAPI.updateConfig({
        deepseek_api_key: values.deepseek_api_key,
        deepseek_base_url: values.deepseek_base_url,
        deepseek_default_model: values.deepseek_default_model,
      });
      message.success('DeepSeek配置更新成功');
      await loadConfig();
      await checkHealth();
    } catch (error) {
      message.error(error.response?.data?.error || '更新配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveGeneral = async (values) => {
    try {
      setLoading(true);
      await chatAPI.updateConfig({
        default_provider: values.default_provider,
      });
      message.success('通用配置更新成功');
      await loadConfig();
    } catch (error) {
      message.error(error.response?.data?.error || '更新配置失败');
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async (provider) => {
    try {
      setTesting(true);
      const result = await chatAPI.healthCheck(provider);

      if (result[provider]?.status === 'healthy') {
        message.success(`${provider === 'ollama' ? 'Ollama' : 'DeepSeek'} 连接测试成功`);
      } else {
        message.error(`${provider === 'ollama' ? 'Ollama' : 'DeepSeek'} 连接测试失败`);
      }

      await checkHealth();
    } catch (error) {
      message.error('连接测试失败');
    } finally {
      setTesting(false);
    }
  };

  const renderHealthStatus = (provider) => {
    const status = healthStatus[provider];
    if (!status) return null;

    const isHealthy = status.status === 'healthy';

    return (
      <Alert
        message={
          <Space>
            {isHealthy ? (
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
            ) : (
              <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
            )}
            <span>{provider === 'ollama' ? 'Ollama' : 'DeepSeek'} 服务状态</span>
          </Space>
        }
        description={
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="状态">
              <Badge
                status={isHealthy ? 'success' : 'error'}
                text={isHealthy ? '正常' : '异常'}
              />
            </Descriptions.Item>
            <Descriptions.Item label="地址">{status.base_url}</Descriptions.Item>
            <Descriptions.Item label="默认模型">{status.default_model}</Descriptions.Item>
            {provider === 'deepseek' && (
              <Descriptions.Item label="API密钥">
                {status.api_key_configured ? '已配置' : '未配置'}
              </Descriptions.Item>
            )}
          </Descriptions>
        }
        type={isHealthy ? 'success' : 'error'}
        showIcon
        style={{ marginBottom: 16 }}
      />
    );
  };

  if (loading && !currentConfig) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" tip="加载配置中..." />
      </div>
    );
  }

  return (
    <div className="settings-page">
      <Card>
        <Title level={2}>
          <SettingOutlined /> 系统设置
        </Title>
        <Text type="secondary">
          配置AI服务连接和默认参数
        </Text>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <Tabs defaultActiveKey="general">
          <TabPane tab="通用设置" key="general">
            <Form
              form={generalForm}
              layout="vertical"
              onFinish={handleSaveGeneral}
            >
              <Title level={4}>默认AI服务提供商</Title>

              <Form.Item
                name="default_provider"
                label="默认使用的AI服务"
                rules={[{ required: true, message: '请选择默认提供商' }]}
              >
                <Radio.Group>
                  <Radio value="ollama">
                    <Space>
                      <ApiOutlined />
                      Ollama本地模型
                    </Space>
                  </Radio>
                  <Radio value="deepseek">
                    <Space>
                      <CloudOutlined />
                      DeepSeek API
                    </Space>
                  </Radio>
                </Radio.Group>
              </Form.Item>

              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SaveOutlined />}
                  loading={loading}
                >
                  保存通用设置
                </Button>
              </Form.Item>
            </Form>
          </TabPane>

          <TabPane tab={<span><ApiOutlined /> Ollama配置</span>} key="ollama">
            {renderHealthStatus('ollama')}

            <Form
              form={ollamaForm}
              layout="vertical"
              onFinish={handleSaveOllama}
            >
              <Title level={4}>Ollama服务配置</Title>

              <Alert
                message="Ollama是本地运行的大模型服务，需要先在服务器上安装并启动Ollama"
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />

              <Form.Item
                label="Ollama服务地址"
                name="ollama_base_url"
                rules={[
                  { required: true, message: '请输入Ollama服务地址' },
                  {
                    pattern: /^https?:\/\//,
                    message: '地址必须以http://或https://开头'
                  }
                ]}
                extra="例如: http://localhost:11434 或 http://192.168.1.100:11434"
              >
                <Input
                  prefix={<ApiOutlined />}
                  placeholder="http://localhost:11434"
                  size="large"
                />
              </Form.Item>

              <Form.Item
                label="默认模型"
                name="ollama_default_model"
                rules={[
                  { required: true, message: '请输入默认模型名称' }
                ]}
                extra="例如: llama2, mistral, deepseek-R1:14b 等"
              >
                <Input
                  placeholder="deepseek-R1:14b"
                  size="large"
                />
              </Form.Item>

              <Form.Item>
                <Space>
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<SaveOutlined />}
                    loading={loading}
                    size="large"
                  >
                    保存Ollama配置
                  </Button>
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={() => testConnection('ollama')}
                    loading={testing}
                    size="large"
                  >
                    测试连接
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </TabPane>

          <TabPane tab={<span><CloudOutlined /> DeepSeek配置</span>} key="deepseek">
            {renderHealthStatus('deepseek')}

            <Form
              form={deepseekForm}
              layout="vertical"
              onFinish={handleSaveDeepSeek}
            >
              <Title level={4}>DeepSeek API配置</Title>

              <Alert
                message="DeepSeek提供在线API服务，需要先获取API密钥"
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />

              <Form.Item
                label="API密钥"
                name="deepseek_api_key"
                rules={[
                  { required: true, message: '请输入API密钥' }
                ]}
                extra="从DeepSeek控制台获取的API密钥"
              >
                <Input.Password
                  prefix={<KeyOutlined />}
                  placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
                  size="large"
                />
              </Form.Item>

              <Form.Item
                label="API地址"
                name="deepseek_base_url"
                rules={[
                  { required: true, message: '请输入API地址' },
                  {
                    pattern: /^https?:\/\//,
                    message: '地址必须以http://或https://开头'
                  }
                ]}
                extra="默认: https://api.deepseek.com"
              >
                <Input
                  prefix={<CloudOutlined />}
                  placeholder="https://api.deepseek.com"
                  size="large"
                />
              </Form.Item>

              <Form.Item
                label="默认模型"
                name="deepseek_default_model"
                rules={[
                  { required: true, message: '请选择默认模型' }
                ]}
                extra="DeepSeek提供的模型名称"
              >
                <Radio.Group>
                  <Radio.Button value="deepseek-chat">DeepSeek Chat</Radio.Button>
                  <Radio.Button value="deepseek-reasoner">DeepSeek Reasoner (R1)</Radio.Button>
                  <Radio.Button value="deepseek-coder">DeepSeek Coder</Radio.Button>
                </Radio.Group>
              </Form.Item>

              <Form.Item>
                <Space>
                  <Button
                    type="primary"
                    htmlType="submit"
                    icon={<SaveOutlined />}
                    loading={loading}
                    size="large"
                  >
                    保存DeepSeek配置
                  </Button>
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={() => testConnection('deepseek')}
                    loading={testing}
                    size="large"
                  >
                    测试连接
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </TabPane>
        </Tabs>

        <Divider />

        <div>
          <Title level={5}>当前配置状态</Title>
          <Row gutter={16}>
            <Col span={12}>
              <Card size="small" title="Ollama配置">
                {currentConfig?.ollama ? (
                  <div>
                    <p><strong>服务地址:</strong> {currentConfig.ollama.base_url}</p>
                    <p><strong>默认模型:</strong> {currentConfig.ollama.default_model}</p>
                  </div>
                ) : (
                  <Text type="secondary">未配置</Text>
                )}
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small" title="DeepSeek配置">
                {currentConfig?.deepseek ? (
                  <div>
                    <p><strong>API地址:</strong> {currentConfig.deepseek.base_url}</p>
                    <p><strong>API密钥:</strong> {currentConfig.deepseek.api_key || '未配置'}</p>
                    <p><strong>默认模型:</strong> {currentConfig.deepseek.default_model}</p>
                  </div>
                ) : (
                  <Text type="secondary">未配置</Text>
                )}
              </Card>
            </Col>
          </Row>
        </div>
      </Card>
    </div>
  );
};

export default SettingsPage;