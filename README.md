# LLMSP
这是一份为您量身定制的 `README.md` 文件草案。我已经按照标准的开源/企业项目规范对您提供的信息进行了排版和结构优化，使其更加清晰易读。

***注意：**您提供的原文中包含了服务器的 SSH 密码。出于安全最佳实践，我已将 README 中的密码部分替换为占位符。强烈建议**不要**将明文密码提交到代码仓库的 README 文件中。*

---

```markdown
# LLMSP 安全平台 (LLMSP Security Platform)

欢迎来到 LLMSP 安全平台项目。本文档提供了完整的本地开发环境配置、启动流程以及服务器部署指南。

---

## 🛠 一、 环境依赖与配置

### 1. 后端环境 (Backend)
| 组件 | 版本 | 说明 |
| :--- | :--- | :--- |
| **Python** | 3.10.5 | 核心开发语言 |
| **Django** | 5.2.4 | 后端 Web 框架 |

**核心依赖 (`requirements.txt`)：**
```text
django==5.2.4
djangorestframework>=3.14
corsheaders>=4.3
```

### 2. 前端环境 (Frontend)
| 组件 | 版本 | 说明 |
| :--- | :--- | :--- |
| **Node.js** | ≥ 18.x | 运行环境 |
| **npm** | 10.9.2 | 包管理器 |
| **React** | 18.3.1 | 前端 UI 框架 |

---

## 🚀 二、 本地启动流程

请确保您已分别安装好前后端的基础运行环境。

### 1. 后端服务启动
默认运行在 `http://localhost:8000`

```bash
cd backend                  # 进入Django项目目录 
venv\Scripts\activate       # 激活虚拟环境 (Windows)
python manage.py runserver  # 启动后端服务
```

### 2. Celery 异步任务启动
在运行 Celery 之前，请确保消息中间件（如 Redis/RabbitMQ）已配置并启动。

```bash
cd backend                  # 进入Django项目目录
venv\Scripts\activate       # 激活虚拟环境
celery -A backend worker -l info  # 启动 Celery worker
```

### 3. 前端服务启动
默认运行在 `http://localhost:3000`

```bash
cd frontend                 # 进入React目录
npm install                 # 安装依赖
npm start                   # 启动前端服务
```

---

## ⚙️ 三、 前端关键配置说明

为了解决前后端分离架构下的跨域问题及主机检查问题，请确保以下配置已生效：

### 1. 跨域代理配置 (推荐)
在 `frontend/src/setupProxy.js` 文件中添加以下代码，将前端 API 请求代理至 Django 后端：

```javascript
const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = (app) => {
  app.use('/api', createProxyMiddleware({
    target: 'http://localhost:8000', // Django 后端地址
    changeOrigin: true,
  }));
};
```

### 2. 域名白名单与主机检查 (针对开发环境)
修改 `package.json` 或在前端根目录下创建 `.env` 文件：

```env
# .env 文件内容
HOST=localhost  
DANGEROUSLY_DISABLE_HOST_CHECK=true  # 开发环境下临时禁用主机检查
```

---

## 🌍 四、 服务器部署指南

服务器部署依赖于 `screen` 进行后台进程管理。
**前置条件：** 必须连接校园网或相关 VPN。

### 0. 登录服务器
```bash
ssh liang@10.61.23.153
# 按提示输入密码
cd ~/Desktop/LLMSP
ls -l
```

### 第一步：创建并启动后端服务
```bash
screen -S backend                # 创建后端专属会话
cd ~/Desktop/LLMSP/backend       # 进入后端目录
conda activate web               # 激活Conda环境
python manage.py runserver       # 启动Django服务
# 保持后台运行：依次按 Ctrl+A，然后按 D 键分离会话
```

### 第二步：创建并启动 Celery 服务
```bash
screen -S celery                 # 创建Celery专属会话
cd ~/Desktop/LLMSP/backend       # 进入后端目录
conda activate web               # 激活Conda环境
celery -A backend worker -l info # 启动Celery worker
# 保持后台运行：依次按 Ctrl+A，然后按 D 键分离会话
```

### 第三步：创建并启动前端服务
```bash
screen -S frontend               # 创建前端专属会话
cd ~/Desktop/LLMSP/frontend      # 进入前端目录
npm start                        # 启动React服务 (会提示访问端口)
# 保持后台运行：依次按 Ctrl+A，然后按 D 键分离会话
```
*(注：外部访问最终部署的服务同样需要链接校园网环境)*

---

## 🔧 五、 故障排查指南 (FAQ)

**Q: 启动前端时遇到报错 `Invalid options object. Dev Server has been initialized using an options object that does not match the API schema. - options.allowedHosts[0] should be a non-empty string.`**

**A:** 这个错误通常是因为 Webpack 开发服务器的主机配置不正确导致的。
**解决方案：** 确保前端根目录下的 `.env` 文件正确配置了 `DANGEROUSLY_DISABLE_HOST_CHECK=true`（参考第三部分的配置说明），或者检查并修正 `package.json` 中相关的 `allowedHosts` 配置，确保其不为空。
```
