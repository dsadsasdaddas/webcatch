# ==========================================
# 📦 导入依赖
# ==========================================
import asyncio
import os
import urllib.parse
from typing import Annotated, List
from typing_extensions import TypedDict
from datetime import datetime

# 使用 OpenAI 标准库来连接 DeepSeek
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from playwright.async_api import async_playwright, Page
from openai import AsyncOpenAI

# ==========================================
# 🔧 1. 全局辅助函数
# ==========================================
GLOBAL_PAGE: Page = None
VISITED_URLS = set()

async def close_popups(page: Page):
    """
    暴力关闭常见的弹窗、登录框、Cookie同意栏。
    """
    print("   🧹 [System] 正在尝试清理弹窗...")
    close_texts = ["关闭", "Close", "No thanks", "Not now", "Maybe later", "以后再说", "跳过", "Skip", "I accept", "Accept all", "同意", "知道啦", "×", "x", "确定", "Confirm"]
    close_selectors = ["button[aria-label='Close']", "div[aria-label='Close']", ".close-btn", ".modal-close", "svg.close-icon", ".close"]

    try:
        for text in close_texts:
            try:
                btn = page.get_by_text(text, exact=True).first
                if await btn.is_visible():
                    await btn.click(timeout=3000)
                    await asyncio.sleep(0.5)
            except: pass

        for sel in close_selectors:
            try:
                if await page.locator(sel).first.is_visible():
                    await page.locator(sel).first.click(timeout=3000)
                    await asyncio.sleep(0.5)
            except: pass
        
        await page.keyboard.press("Escape")
    except Exception as e:
        print(f"   🧹 (忽略) {e}")

# ==========================================
# 🔧 2. 工具定义
# ==========================================
@tool
async def search_web(query: str, engine: str = "bing"):
    """
    全网搜索工具 (自带 DuckDuckGo 自动保底)。
    参数 engine 可选值: "bing", "google", "bilibili", "xiaohongshu", "weibo", "duckduckgo"
    """
    if not GLOBAL_PAGE: return "错误: 浏览器未连接"
    
    # 定义引擎配置 (URL模板 和 结果选择器)
    engines_config = {
        "google": {
            "url": f"https://www.google.com/search?q={urllib.parse.quote(query)}",
            "selector": "div.g"
        },
        "bilibili": {
            "url": f"https://search.bilibili.com/all?keyword={urllib.parse.quote(query)}",
            "selector": ".bili-video-card"
        },
        "xiaohongshu": {
            "url": f"https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(query)}&source=web_search_result_notes",
            "selector": ".note-item"
        },
        "weibo": {  # === ✨ 新增微博配置 ===
            "url": f"https://s.weibo.com/weibo?q={urllib.parse.quote(query)}",
            "selector": ".card-wrap"
        },
        "bing": {
            "url": f"https://cn.bing.com/search?q={urllib.parse.quote(query)}",
            "selector": "li.b_algo"
        },
        "duckduckgo": {
            "url": f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&t=h_&ia=web",
            "selector": 'a[data-testid="result-title-a"]'
        }
    }

    # 1. 获取当前目标引擎配置
    # 如果 DeepSeek 乱传参数，默认回退到 bing
    target = engines_config.get(engine, engines_config["bing"])
    
    print(f"   🔍 [Action] 正在 [{engine}] 上搜索: {query}")

    async def run_search(url, selector, is_retry=False):
        """内部搜索执行函数"""
        try:
            await GLOBAL_PAGE.goto(url)
            # 等待 DOM 加载
            await GLOBAL_PAGE.wait_for_load_state("domcontentloaded")
            await close_popups(GLOBAL_PAGE) # 关弹窗
            
            # 尝试等待结果出现 (最多等 3 秒)
            try:
                await GLOBAL_PAGE.wait_for_selector(selector, timeout=3000)
            except:
                # 如果超时没找到选择器，说明可能被拦截了，或者没结果
                return None 

            results = await GLOBAL_PAGE.locator(selector).all()
            if not results: return None # 有选择器但没内容

            data = []
            for i, res in enumerate(results[:8]):
                text = await res.inner_text()
                clean_text = text.replace("\n", " ")[:100]
                data.append(f"【{i}】: {clean_text}...")
            return "\n".join(data)
        except Exception as e:
            print(f"      ⚠️ 搜索出错: {e}")
            return None

    # === 2. 第一轮：尝试 DeepSeek 指定的引擎 ===
    result_text = await run_search(target["url"], target["selector"])

    # === 3. 🛡️ 保底机制：如果第一轮失败，且当前不是 DuckDuckGo ===
    # 只要结果是 None (被拦截/没搜到)，立刻切换 DDG
    if result_text is None and engine != "duckduckgo":
        print(f"   🛡️ [System] 检测到 {engine} 搜索失败/被拦截，自动切换至 DuckDuckGo 保底...")
        
        ddg_conf = engines_config["duckduckgo"]
        fallback_result = await run_search(ddg_conf["url"], ddg_conf["selector"], is_retry=True)
        
        if fallback_result:
            return f"✅ [DuckDuckGo (保底)] 搜索结果:\n" + fallback_result
        else:
            return "❌ 所有引擎（包括保底）均未搜索到有效内容。"
    
    # 如果第一轮成功，直接返回
    if result_text:
        return f"✅ [{engine}] 搜索结果:\n" + result_text
    else:
        return "❌ 搜索失败。"

@tool
async def scroll_window(direction: str = "down"):
    """滑动页面。"""
    print(f"   📜 [Action] 滑动页面: {direction}")
    if not GLOBAL_PAGE: return "错误: 浏览器未连接"
    if direction == "down":
        await GLOBAL_PAGE.evaluate("window.scrollBy(0, window.innerHeight)")
    else:
        await GLOBAL_PAGE.evaluate("window.scrollBy(0, -window.innerHeight)")
    await asyncio.sleep(1)
    return "滑动完成"

@tool
async def click_link(index_or_text: str):
    """点击链接 (支持数字编号)。"""
    print(f"   👆 [Action] 尝试点击: {index_or_text}")
    if not GLOBAL_PAGE: return "错误: 浏览器未连接"
    
    try:
        target_link = None
        if index_or_text.isdigit():
            idx = int(index_or_text)
            
            # 万能选择器 (=== ✨ 已加入 .card-wrap a 用于微博 ===)
            universal_sel = "h3 a, h2 a, h3, a[data-testid='result-title-a'], .bili-video-card a, .note-item a, .card-wrap a"
            
            results = await GLOBAL_PAGE.locator(universal_sel).all()
            
            # 如果万能选择器没找到，兜底找所有 a 标签
            if not results:
                results = await GLOBAL_PAGE.locator("a").all()
                
            if 0 <= idx < len(results):
                target_link = results[idx]
                
                # Google 特殊处理：如果点的是 h3，需要点它的父级链接
                try:
                    tag_name = await target_link.evaluate("el => el.tagName")
                    if tag_name in ["H3", "H2", "DIV"]:
                        target_link = target_link.locator("xpath=..")
                except: pass
        else:
            target_link = GLOBAL_PAGE.get_by_text(index_or_text).first

        if not target_link: return "❌ 索引越界或未找到。"

        # 获取 URL 用于去重
        try:
            target_url = await target_link.get_attribute("href")
            if target_url and target_url in VISITED_URLS:
                return f"❌ 拒绝：编号 {index_or_text} 已访问过！换一个！"
            if target_url: VISITED_URLS.add(target_url)
        except: pass

        # === 强制在当前页打开，防止页面关不掉 ===
        await target_link.evaluate("el => el.setAttribute('target', '_self')")
        
        # 点击并快速返回
        await target_link.click()
        await GLOBAL_PAGE.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(1) # 等待渲染
        await close_popups(GLOBAL_PAGE)
        return f"点击成功 (编号 {index_or_text})，已进入详情页。"
        
    except Exception as e:
        return f"点击失败: {e}"

@tool
async def read_page_content():
    """读取详情 (增强版：自动展开 + 返回 URL 来源)。"""
    print(f"   📖 [Action] 阅读详情...")
    if not GLOBAL_PAGE: return "错误: 浏览器未连接"
    
    try:
        # === 1. B站策略 ===
        if "bilibili.com" in GLOBAL_PAGE.url:
            try:
                await GLOBAL_PAGE.locator(".desc-info .toggle-btn").first.click(timeout=500)
            except: pass
            # B站有时候评论需要滚动才加载
            await GLOBAL_PAGE.evaluate("window.scrollBy(0, 500)")

        # === 2. 小红书策略 ===
        elif "xiaohongshu.com" in GLOBAL_PAGE.url:
            try:
                await GLOBAL_PAGE.locator(".content-container .expand-btn").first.click(timeout=500)
            except: pass
            
            try:
                # 🚨 关键修复：加了 timeout，防止找不到评论区时死等 30秒
                await GLOBAL_PAGE.locator(".comments-container").scroll_into_view_if_needed(timeout=1000)
            except: pass

        # === 3. 微博策略 ===
        elif "weibo.com" in GLOBAL_PAGE.url:
            try:
                await GLOBAL_PAGE.locator("a[action-type='fl_unfold']").first.click(timeout=500)
            except: pass
            
            try:
                await GLOBAL_PAGE.get_by_text("评论", exact=False).first.click(timeout=1000)
            except: pass
            
            await GLOBAL_PAGE.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1) # 等数据飞一会儿
            
            try:
                await GLOBAL_PAGE.get_by_text("查看更多", exact=False).first.click(timeout=500)
            except: pass

        # === 4. 通用兜底策略 ===
        try:
            await GLOBAL_PAGE.get_by_text("展开", exact=True).first.click(timeout=500)
        except: pass

    except Exception as e:
        print(f"      (展开操作跳过: {e})")

    # === 读取全文 ===
    await asyncio.sleep(0.5)
    content = await GLOBAL_PAGE.inner_text("body")
    current_url = GLOBAL_PAGE.url
    
    total_len = len(content)
    # print(f"      (原文共 {total_len} 字)")
    
    limit = 10000
    if total_len > limit:
        return f"🔗 Source: {current_url}\n\n" + content[:limit] + f"\n...(剩余 {total_len - limit} 字已省略)..."
    
    return f"🔗 Source: {current_url}\n\n" + content

@tool
async def go_back():
    """返回上一页。"""
    print(f"   🔙 [Action] 返回上一页")
    if not GLOBAL_PAGE: return "错误: 浏览器未连接"
    await GLOBAL_PAGE.go_back()
    await asyncio.sleep(1)
    return "已返回上一页"

@tool
async def generate_structured_report(
    brand_name: str, 
    sentiment_score: int, 
    summary: str, 
    risks: str, 
    opportunities: str,
    real_quotes: str,
    deep_analysis: str,
    sources: str
):
    """
    生成【工业级】商业舆情报告 (无装饰/数据表格化)，保存到 D:\\web抓取。
    """
    print(f"   📝 [Action] 正在渲染工业级报告: {brand_name}")
    
    # 1. 评级逻辑 (使用专业术语)
    if sentiment_score >= 80: 
        rating = "Positive (Tier A)"
        trend = "Bullish (看多)"
    elif sentiment_score >= 60: 
        rating = "Neutral (Tier B)"
        trend = "Stable (震荡)"
    elif sentiment_score >= 40: 
        rating = "Volatile (Tier C)"
        trend = "Uncertain (波动)"
    else: 
        rating = "Negative (Tier D)"
        trend = "Bearish (看空)"

    # 2. 工业化 Markdown 模板 (极简、表格、数据)
    template = f"""# [REPORT] {brand_name} Commercial Sentiment Analysis

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Source:** Nexus Intelligence System  
**Classification:** INTERNAL USE ONLY  

---

## 1. Executive Dashboard (核心数据看板)

| Metric (指标) | Value (数值) | Rating (评级) | Trend (趋势) |
| :--- | :--- | :--- | :--- |
| **Sentiment Index** | **{sentiment_score}/100** | {rating} | {trend} |
| **Data Sample** | Multi-channel | Validated | - |

---

## 2. Strategic Summary (结论)
{summary}

---

## 3. Deep Dive Analysis (深度研判)
{deep_analysis}

---

## 4. Risk Assessment (风险评估)
{risks}

---

## 5. Growth Opportunities (增长机会)
{opportunities}

---

## 6. Verbatim Feedback (用户原声采样)
{real_quotes}

---

## 7. Data References (数据溯源)
{sources}

---
*Generated by Nexus System. automated analysis.*
"""

    # 3. 保存逻辑 (保持不变)
    save_dir = r"D:\web抓取"
    if not os.path.exists(save_dir):
        try: os.makedirs(save_dir)
        except: return "❌ System Error: Cannot create directory."

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Report_{brand_name}_{timestamp}.md"
    full_path = os.path.join(save_dir, filename)

    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(template)
        print(f"\n✅ Report Generated: {full_path}\n")
        return f"✅ Success. Report saved to: {full_path}"
    except Exception as e:
        return f"❌ IO Error: {e}"


# ==========================================
# 🧠 3. 构建 DeepSeek 智能体
# ==========================================

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    visited_urls: Annotated[List[str], lambda x, y: x + y]

async def tool_node(state: AgentState):
    messages = state['messages']
    last_message = messages[-1]
    
    # 绑定所有工具
    tools_map = {
        "search_web": search_web, 
        "scroll_window": scroll_window, 
        "click_link": click_link, 
        "read_page_content": read_page_content, 
        "go_back": go_back,
        "generate_structured_report": generate_structured_report # 👈 新增
    }
    
    results = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call['name']
        args = tool_call['args']
        if tool_name in tools_map:
            try:
                action_result = await tools_map[tool_name].ainvoke(args)
            except Exception as e:
                action_result = f"Error: {e}"
            results.append(ToolMessage(tool_call_id=tool_call['id'], name=tool_name, content=str(action_result)))
            
    return {"messages": results}

async def call_deepseek(state: AgentState):
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key="sk-c7efc0d3d9154cdf959fa1ba665ed1a8", # 你的 Key
        base_url="https://api.deepseek.com",
        temperature=0.2
    )
    # 绑定包含 Report 工具的列表
    llm_with_tools = llm.bind_tools([
        search_web, scroll_window, click_link, read_page_content, go_back, generate_structured_report
    ])
    
    system_prompt = """
    你是一个全网搜索专家。
    策略：
    - 优先使用 Google/Bing/Xiaohongshu。
    - 如果搜不到，工具会自动切 DuckDuckGo 保底，你无需操心。
  你是一个【首席品牌情报官】(Chief Brand Intelligence Officer)。
    你的客户是企业老板，你的任务是提供【有商业价值】的市场洞察。
    你必须多去微博小红书b站,浏览器搜索是辅助,而且在这些社交平台你必须看很多人的帖子,提取【用户真实反馈】。
    每个社交平台看五个博主以上的帖子
    
    核心分析逻辑：
    1. 【情感极性】：用户是夸还是骂？
    2. 【痛点挖掘】：用户在抱怨什么？(太贵/难用/丑/服务差)
    3. 【购买意向】：用户有没有问“哪里买”？
    4. 【竞品对比】：用户有没有提到别的品牌更好？
    
    请忽略无意义的灌水评论，专注于提取【决策依据】。分辨用户是否使用ai生成的内容,寻找热门的帖子,时间越新越好
    标出引用的来源的链接或者视频标题
    
    状态机：
    1. 【搜索】-> 2. 【点击】(传入编号) -> 3. 【阅读】-> 4. 【后退】
    ### 核心指令：
    1. **必须引用原文**：在分析用户反馈时，必须直接摘录用户的原话,不能改动一个字（包括他们的语气词、抱怨的细节）。
    2. **数据溯源**：每一条引用的评论，必须在后面标注大概来源（如：来自小红书笔记、来自微博评论）。
    3. **深度分析**：不要只列点，要写出有逻辑的分析文章，分析背后的社会心理或商业逻辑,同时不能给太低的评级,再说完不好后要说点优点.
    
    ### 搜集策略：
    - 优先去微博、小红书、B站寻找【最新】的用户真实评论。
    - 阅读网页时，务必记录下该网页的 URL。
    - 至少阅读 5-8 个不同的网页/帖子，确保信息量充足。
    
    ### 最终输出要求：
    搜集完足够信息后，**必须**调用工具 `generate_structured_report` 生成文件。
    
    在调用工具填写参数时，请严格遵守以下格式：
    - `real_quotes`: 必须包含至少 10 条真实用户评论的摘录，格式如下：
      > "瑞幸现在的9.9只有几款了，太坑了！" —— (来源：小红书用户)
      > "每天早上一杯冰吸生椰，提神醒脑。" —— (来源：微博用户)
      
    - `deep_analysis`: 请撰写一篇 500字左右的深度分析文章，探讨现象背后的本质。
    
    - `sources`: 列出所有参考过的 URL 链接。
    
    严禁直接在对话框输出报告文本，必须调用工具生成文件！
    
    ⛔ 严禁行为：
    - 禁止点击重复链接。
    - 读完必须 go_back。
    """
    messages = [SystemMessage(content=system_prompt)] + state['messages']
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    if state['messages'][-1].tool_calls: return "tools"
    return END

# ==========================================
# 🚀 4. 主程序 (自动弹窗 + 持久化记忆版)
# ==========================================
async def main():
    global GLOBAL_PAGE
    VISITED_URLS.clear()

    print("\n🚀 正在启动 Nexus (Auto-Launch Mode)...")
    
    # 1. 定义数据存储目录 (当前目录下的 browser_data 文件夹)
    # 这就是浏览器的“大脑记忆区”，存 Cookie 和 登录状态
    user_data_dir = os.path.abspath("./nexus_browser_data")
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir)

    async with async_playwright() as p:
        try:
            # === 你的原生启动配置 (保留了去横条) ===
            browser_context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel="chrome",
                # 去除 "Chrome 正受到自动测试软件的控制"
                ignore_default_args=["--enable-automation"], 
                args=[
                    "--start-maximized", 
                    "--disable-blink-features=AutomationControlled", # 伪装成真人
                    "--no-sandbox",
                    "--disable-infobars",
                ],
                viewport={"width": 1920, "height": 1080},
            )
            
            # 注入隐身 JS
            await browser_context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """)
            
            GLOBAL_PAGE = browser_context.pages[0]
         

            # 构建图
            workflow = StateGraph(AgentState)
            workflow.add_node("agent", call_deepseek)
            workflow.add_node("tools", tool_node)
            workflow.add_edge(START, "agent")
            workflow.add_conditional_edges("agent", should_continue)
            workflow.add_edge("tools", "agent")
            app = workflow.compile()

            # 任务
            task = "皇室战争现在的经营怎么样和同类游戏进行对比"
            
            print(f"\n🎯 任务启动: {task}\n")
            
            async for chunk in app.astream({"messages": [HumanMessage(content=task)]}, stream_mode="values"):
                last_msg = chunk["messages"][-1]
                if last_msg.type == "ai":
                    if last_msg.tool_calls:
                        print(f"🧠 [DeepSeek 决策]: {last_msg.tool_calls[0]['name']} Args: {last_msg.tool_calls[0]['args']}")
                    else:
                        print(f"🤖 [DeepSeek 总结]:\n{last_msg.content}")
            
            print("\n✅ 任务完成！为了让你看清楚，浏览器将保持打开 60 秒...")
            await asyncio.sleep(60)
            
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            print("💡 如果报错，请检查：\n1. 你的电脑装了 Chrome 吗？\n2. 请务必【关闭所有已经打开的 Chrome 窗口】再运行此程序！")

if __name__ == "__main__":
    asyncio.run(main())