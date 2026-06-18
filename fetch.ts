import { webkit } from 'playwright';
import * as dotenv from 'dotenv';

// 加载 .env 文件中的环境变量
dotenv.config();

async function main() {
    const browser = await webkit.launch({ headless: true });
    const page = await browser.newPage();

    await page.goto(process.env.HTML_URL || 'https://api.uouin.com/cloudflare.html', { waitUntil: 'networkidle' });

    // Extract table data: each row = [序号, 线路, IP, 丢包, 延迟, 速度, 带宽, Colo, 时间]
    const rows = await page.evaluate(() => {
        const trs = document.querySelectorAll('table tbody tr');
        return Array.from(trs).map(tr =>
            Array.from(tr.querySelectorAll('td, th')).map(td => td.textContent.trim())
        );
    });

    // Build CSV
    const header = '序号,线路,IP,丢包,延迟,速度,带宽,Colo,时间';
    const csvLines = [header, ...rows.map(r => r.join(','))];
    const csv = csvLines.join('\n');

    // Write to file
    const fs = await import('fs');
    fs.writeFileSync('ips.csv', csv, 'utf-8');
    console.log(`✅ 成功写入 ips.csv，共 ${rows.length} 条记录`);

    await browser.close();
}

main().catch(err => {
    console.error('❌ 出错:', err);
    process.exit(1);
});
