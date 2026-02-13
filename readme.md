# Nexus-Insight: 垂直领域商业舆情深度分析 Agent

> **声明**：本项目由温州大学生科院学生自主开发，旨在通过 AI 技术解决中小企业在非标品选品中的信息滞后问题。

---

## 🚀 项目简介
Nexus-Insight 不仅仅是一个爬虫，它是一个集成 **Playwright** 自动化抓取与 **DeepSeek** 逻辑分析能力的商业情报 Agent。
它通过模拟真实用户行为，深入挖掘小红书、微博等平台的“非结构化评价”，并将其转化为可量化的“商业洞察”。

## ✨ 核心功能
* **深度数据采集**：利用 Playwright 绕过动态加载限制，抓取实时舆情。
* **多维度情感分析**：基于 LLM 对用户反馈进行分词处理与情感归类（如：质量吐槽、尺码建议、款式偏好）。
* **自动化研报生成**：一键导出 Markdown 格式的深度研报，支持快速决策。
* **无痕巡航模式**：采用隐私浏览器模式，规避算法推荐导致的“信息茧房”。

## 🛠️ 技术栈
* **语言**：Python 3.10+
* **核心框架**：LangGraph, LangChain
* **浏览器引擎**：Playwright
* **模型支持**：DeepSeek-V3 / GPT-4o

## 📦 快速开始

### 1. 环境准备
```bash
git clone [https://github.com/你的用户名/你的仓库名.git](https://github.com/你的用户名/你的仓库名.git)
cd 你的仓库名
pip install -r requirements.txt
playwright install