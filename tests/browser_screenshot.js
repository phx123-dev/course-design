/* 页面截图工具: 用本机 Edge/Chrome 驱动真实系统走完整业务闭环并截图
 * (演示素材/设计报告插图; 视频录制请按 docs/演示脚本.md 操作)
 *
 * 前置: 后端已启动(start.bat / uvicorn --port 8000)
 * 运行: cd tests && node browser_screenshot.js
 * 输出: docs/screenshots/shot_*.png
 */
'use strict';
const fs = require('fs');
const path = require('path');

const BASE = 'http://localhost:8000';
const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'screenshots');

async function main() {
  const { chromium } = require('playwright-core');
  let browser = null;
  for (const channel of ['msedge', 'chrome']) {
    try {
      browser = await chromium.launch({ channel, headless: true });
      console.log(`使用浏览器: ${channel}`);
      break;
    } catch (e) {
      console.log(`${channel} 不可用: ${e.message.split('\n')[0]}`);
    }
  }
  if (!browser) {
    console.error('未找到可用的 Edge/Chrome, 截图跳过');
    process.exit(0);
  }
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const shot = async (name) => {
    await page.waitForTimeout(800);
    await page.screenshot({ path: path.join(OUT_DIR, `shot_${name}.png`) });
    console.log(`  ✓ ${name}`);
  };
  const switchPage = (p, ctx) => page.evaluate(
    ([pg, c]) => window.appRoot.switchPage(pg, c), [p, ctx]);

  try {
    // 1. 登录页
    await page.goto(BASE);
    await shot('01_login');

    // 2. 登录
    await page.fill('.login-card input[placeholder="用户名"]', 'engineer');
    await page.fill('.login-card input[placeholder="密码"]', '123456');
    await page.click('.login-btn');
    await page.waitForTimeout(1500);
    await shot('02_dashboard');

    // 3. 设备监控：选 EQ-003 并注入外圈故障
    await switchPage('monitoring', { device_id: 3 });
    await page.waitForTimeout(1500);
    await page.click('button:has-text("注入外圈故障")');
    await page.waitForTimeout(2500);
    await shot('03_monitoring_fault');

    // 4. 运行机器学习预测
    await page.click('button:has-text("运行预测")');
    await page.waitForTimeout(1500);
    await shot('04_prediction');

    // 5. 智能诊断对话
    await switchPage('chat', { device_id: 3 });
    await page.waitForTimeout(800);
    await page.fill('.chat-input input', 'EQ-003 振动异常，帮我诊断一下');
    await page.click('.chat-input button');
    await page.waitForTimeout(6000);   // 等待流式回复完成
    await shot('05_chat_diagnose');

    // 6. 一键生成工单（点击依据卡片下的按钮）
    const woBtn = page.locator('button:has-text("依据此诊断生成工单")').first();
    if (await woBtn.count()) {
      await woBtn.click();
      await page.waitForTimeout(1500);
      await shot('06_workorders');
    }

    // 7. 知识库检索
    await switchPage('knowledge', {});
    await page.waitForTimeout(800);
    await page.fill('.panel input[placeholder*="内圈"]', '内圈故障有什么特征');
    await page.click('button:has-text("检索")');
    await page.waitForTimeout(1500);
    await shot('07_knowledge_search');

    // 8. 设备台账
    await switchPage('devices', {});
    await page.waitForTimeout(800);
    await shot('08_devices');

    console.log(`\n截图完成，输出目录: ${OUT_DIR}`);
  } finally {
    await browser.close();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
