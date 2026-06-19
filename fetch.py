import asyncio
from playwright.async_api import async_playwright
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        page = await browser.new_page()
        
        url = os.getenv('HTML_URL') or 'https://api.uouin.com/cloudflare.html'
        await page.goto(url, timeout=60000)
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            None
        rows = await page.evaluate('''() => {
            const trs = document.querySelectorAll('table tbody tr');
            return Array.from(trs).map(tr =>
                Array.from(tr.querySelectorAll('td, th')).map(td => td.textContent.trim())
            );
        }''')
        
        header = '序号,线路,IP,丢包,延迟,速度,带宽,Colo,时间'
        csv_lines = [header] + [','.join(r) for r in rows]
        csv = '\n'.join(csv_lines)
        
        with open('ips.csv', 'w', encoding='utf-8') as f:
            f.write(csv)
        
        print(f'✅ 成功写入 ips.csv，共 {len(rows)} 条记录')
        await browser.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as err:
        print(f'❌ 出错: {err}')
        import sys
        sys.exit(1)
