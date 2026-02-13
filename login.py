import asyncio
import os
from playwright.async_api import async_playwright

async def setup_login():
    # 1. 确保和主程序用的是同一个文件夹名！
    # 只要这行代码一运行，文件夹立刻就会被创建出来
    user_data_dir = os.path.abspath("./nexus_browser_data")
    
    # 如果文件夹不存在，自动创建
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir)

    print(f"🚀 正在启动浏览器 (登录模式)...")
    print(f"📂 你的存档位置: {user_data_dir}")

    async with async_playwright() as p:
        # 启动带记忆的浏览器
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False, # 必须显示窗口让你操作
            channel="chrome",
            args=["--start-maximized"],
            viewport={"width": 1920, "height": 1080},
        )
        
        page = context.pages[0]
        await page.goto("https://www.baidu.com")
        
        print("\n✅ 浏览器已打开！")
        print("------------------------------------------------")
        print("👉 请现在手动在浏览器里：")
        print("   1. 打开知乎、B站、微博等你需要用的网站。")
        print("   2. 扫码登录账号。")
        print("   3. 务必勾选【记住我】或【自动登录】。")
        print("------------------------------------------------")
        
        # === 关键：这里会卡住，等你操作 ===
        input("👉 全部登录完成后，请回到这里按【回车键】保存并退出...")
        
        print("💾 正在保存 Cookies...")
        await context.close()
        print("✅ 存档建立完成！现在你可以去运行主程序了。")

if __name__ == "__main__":
    asyncio.run(setup_login())