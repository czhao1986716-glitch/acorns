import json
import os
import time
import datetime
from datetime import timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

# ================= ⚙️ 配置区 =================
TARGET_URL = "https://bestinslot.xyz/brc2.0/acorns/holders"
DB_FILE = "data.json"   # 必须叫这个名字，用来读取您的历史数据
HTML_FILE = "index.html"

# 关注名单 (可以在这里备注大户是谁)
WATCHLIST = {
    "0xa07764097a4da7f3b61a562ca1f8e6779494748c": "🥇 榜一巨鲸",
    "0x899cdf7bf5cf1c5a1b3c9afab2faf55482b97662": "🥈 榜二大佬"
}
# ============================================

def setup_headless_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=chrome_options)

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def get_beijing_time():
    # UTC时间 + 8小时 = 北京时间
    utc_now = datetime.datetime.utcnow()
    beijing_now = utc_now + timedelta(hours=8)
    return beijing_now.strftime("%Y-%m-%d %H:%M")

def get_today_date():
    # 获取北京时间的“今天”
    utc_now = datetime.datetime.utcnow()
    beijing_now = utc_now + timedelta(hours=8)
    return beijing_now.strftime("%Y-%m-%d")

def scrape_data():
    print(f"🚀 [GitHub] 启动抓取: {TARGET_URL}")
    driver = setup_headless_driver()
    
    try:
        driver.get(TARGET_URL)
        time.sleep(5) 
        
        # === 暴力滚动逻辑 (确保抓全) ===
        last_height = driver.execute_script("return document.body.scrollHeight")
        retries = 0
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = driver.execute_script("return document.body.scrollHeight")
            rows = len(driver.find_elements(By.TAG_NAME, "tr"))
            print(f"   ...已加载 {rows} 行", end="\r")
            
            if new_height == last_height:
                retries += 1
                if retries >= 5: break
            else:
                retries = 0
                last_height = new_height
                
        print(f"\n✅ 滚动结束。开始解析...")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        holders = []
        
        # 解析表格
        for row in soup.select('table tr')[1:]:
            cols = row.find_all('td')
            if len(cols) >= 5:
                try:
                    # === 1. 地址解析 (修复：同时抓取 0x 和 btc) ===
                    # BiS 的表格通常是：Link是0x地址，Link下面或者旁边是BTC地址
                    
                    # 尝试获取 0x 地址 (作为唯一Key)
                    href = cols[0].find('a').get('href') if cols[0].find('a') else ""
                    if not href and len(cols) > 1: href = cols[1].find('a').get('href') # 有时候在第二列
                    
                    brc_addr = href.split('/')[-1].lower() if href else ""
                    
                    # 如果没抓到 0x 地址，跳过 (必须要有Key)
                    if "0x" not in brc_addr: continue

                    # 尝试获取 BTC 地址 (通常是纯文本)
                    full_text = cols[0].get_text(strip=True) + cols[1].get_text(strip=True)
                    # 简单的提取逻辑：找 bc1 开头的
                    btc_addr = "Unknown"
                    import re
                    btc_match = re.search(r'(bc1[a-zA-Z0-9]+)', full_text)
                    if btc_match:
                        btc_addr = btc_match.group(1)
                    else:
                        # 如果没正则到，尝试取 title 属性或者直接截取
                        btc_addr = brc_addr[:4] + "..." # 兜底

                    # === 2. 余额解析 ===
                    bal_str = cols[4].get_text(strip=True).replace(',', '')
                    balance = float(bal_str)
                    
                    holders.append({
                        "rank": len(holders) + 1,
                        "key": brc_addr,  # 使用 0x 地址作为数据库主键 (和您旧数据一致)
                        "brc": brc_addr,
                        "btc": btc_addr,
                        "bal": balance
                    })
                except Exception as e: 
                    continue
        
        print(f"🎉 成功抓取 {len(holders)} 个地址")
        return holders
        
    except Exception as e:
        print(f"❌ 抓取出错: {e}")
        return []
    finally:
        driver.quit()

def generate_report(holders, db):
    chart_data = {}
    today_str = get_today_date()
    html_rows = ""
    
    # 获取旧数据的 Key，用来判断是不是新人
    old_keys = set(db.keys()) if db else set()
    
    for h in holders:
        key = h['key']
        
        # === 历史数据合并逻辑 ===
        if key not in db: db[key] = []
        history = db[key]
        
        # 写入今天的数据 (防止重复写入)
        if not history or history[-1]['t'] != today_str:
            # 如果中间断档了，补齐 (为了图表好看)
            if history:
                try:
                    last_date = datetime.datetime.strptime(history[-1]['t'], "%Y-%m-%d").date()
                    curr_date = datetime.datetime.strptime(today_str, "%Y-%m-%d").date()
                    delta = (curr_date - last_date).days
                    if delta > 1:
                        for i in range(1, delta):
                            missing = (last_date + timedelta(days=i)).strftime("%Y-%m-%d")
                            history.append({"t": missing, "y": history[-1]['y']})
                except: pass
            history.append({"t": today_str, "y": h['bal']})
        else:
            # 如果今天已经跑过一次，更新最新值
            history[-1]['y'] = h['bal']
            
        # 限制数据长度，防止文件无限大 (保留最近180天)
        if len(history) > 180: history = history[-180:]
        db[key] = history
        
        # === 计算 24H 变化 ===
        change = 0
        if len(history) >= 2:
            change = h['bal'] - history[-2]['y']
        
        # 标记 New
        is_new = (key not in old_keys) and (len(history) == 1)
        
        # 准备图表数据
        chart_data[key] = history
        
        # === 生成 HTML (修复排序和样式) ===
        chg_cls = "flat"; chg_txt = "-"
        if change > 0: 
            chg_cls = "up"
            chg_txt = f"+{change:,.0f} ▲"
        elif change < 0: 
            chg_cls = "down"
            chg_txt = f"{change:,.0f} ▼"
            
        new_tag = "<span class='new'>NEW</span>" if is_new else ""
        rem = f"<span class='rem'>{WATCHLIST.get(key, '')}</span>" if WATCHLIST.get(key) else ""
        
        # 地址显示优化：0x换行显示BTC
        addr_html = f"""
            <span class="addr">{h['brc']}</span>
            <br>
            <span class="sub">{h['btc']}</span>
        """
        
        btn = f"<button class='btn' onclick=\"show('{key}')\">📈</button>"
        
        html_rows += f"""
        <tr>
            <td data-sort="{h['rank']}">#{h['rank']}</td>
            <td>{new_tag} {rem} {addr_html}</td>
            <td data-sort="{h['bal']}" style="font-weight:bold;color:#fff">{h['bal']:,.0f}</td>
            <td data-sort="{change}" class="{chg_cls}">{chg_txt}</td>
            <td>{btn}</td>
        </tr>"""

    save_db(db)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>ACORNS 监控 (Fix版)</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ background: #121212; color: #ccc; font-family: sans-serif; padding: 20px; }}
            h1 {{ text-align: center; color: #00bcd4; }}
            .info {{ text-align: center; color: #666; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; background: #1e1e1e; font-size: 13px; }}
            th, td {{ padding: 8px; border-bottom: 1px solid #333; text-align: left; }}
            th {{ background: #252525; cursor: pointer; color: #888; position: sticky; top: 0; }}
            th:hover {{ color: #fff; background: #333; }}
            .up {{ color: #f44336; }} .down {{ color: #4caf50; }} 
            .addr {{ color: #00bcd4; font-family: monospace; font-size: 13px; }}
            .sub {{ color: #666; font-size: 11px; font-family: monospace; }}
            .new {{ background: #f44336; color: #fff; padding: 1px 3px; font-size: 10px; border-radius: 2px; margin-right:4px; }}
            .rem {{ background: #ff9800; color: #000; padding: 1px 3px; font-size: 10px; border-radius: 2px; font-weight:bold; }}
            .btn {{ background: #333; border: 1px solid #555; color: #fff; cursor: pointer; padding: 2px 6px; }}
            #modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index:999; }}
            .modal-content {{ background: #222; margin: 5% auto; padding: 20px; width: 90%; max-width:800px; height: 500px; border-radius:8px; }}
            .close {{ float: right; font-size: 28px; cursor: pointer; color: #fff; }}
        </style>
    </head>
    <body>
    <h1>🌰 ACORNS 数据监控</h1>
    <div class="info">更新时间: {get_beijing_time()} (北京时间) | 总人数: {len(holders)}</div>
    
    <table id="myTable">
        <thead>
            <tr>
                <th onclick="s(0)">排名 ⇵</th>
                <th>地址 (0x / btc)</th>
                <th onclick="s(2)">持仓 ⇵</th>
                <th onclick="s(3)">24H 变化 ⇵</th>
                <th>趋势</th>
            </tr>
        </thead>
        <tbody>{html_rows}</tbody>
    </table>
    
    <div id="modal">
        <div class="modal-content">
            <span class="close" onclick="document.getElementById('modal').style.display='none'">&times;</span>
            <canvas id="chart"></canvas>
        </div>
    </div>
    
    <script>
        const data = {json.dumps(chart_data)};
        let c;
        
        function show(k) {{
            const pts = data[k];
            if(!pts) {{ alert("暂无该地址历史数据"); return; }}
            
            document.getElementById('modal').style.display='block';
            if(c) c.destroy();
            
            c = new Chart(document.getElementById('chart'), {{
                type: 'line',
                data: {{ 
                    labels: pts.map(p=>p.t), 
                    datasets: [{{ 
                        label: '持仓数量', 
                        data: pts.map(p=>p.y), 
                        borderColor: '#00bcd4', 
                        backgroundColor: 'rgba(0, 188, 212, 0.1)',
                        fill: true,
                        pointRadius: 4,
                        tension: 0.2
                    }}] 
                }},
                options: {{ 
                    maintainAspectRatio: false, 
                    plugins: {{ title: {{ display: true, text: '地址: ' + k, color: '#fff' }} }},
                    scales: {{ 
                        y: {{ grid: {{ color: '#333' }}, ticks: {{ color: '#888' }} }},
                        x: {{ ticks: {{ color: '#888' }} }}
                    }} 
                }}
            }});
        }}

        // 排序算法 (修复版)
        function s(n) {{
            var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
            table = document.getElementById("myTable");
            switching = true; dir = "asc"; 
            while (switching) {{
                switching = false; rows = table.rows;
                for (i = 1; i < (rows.length - 1); i++) {{
                    shouldSwitch = false;
                    // 关键修复：取出 data-sort 属性并转为浮点数，忽略逗号
                    x = parseFloat(rows[i].getElementsByTagName("TD")[n].getAttribute("data-sort"));
                    y = parseFloat(rows[i + 1].getElementsByTagName("TD")[n].getAttribute("data-sort"));
                    if (dir == "asc") {{ if (x > y) {{ shouldSwitch = true; break; }} }} 
                    else if (dir == "desc") {{ if (x < y) {{ shouldSwitch = true; break; }} }}
                }}
                if (shouldSwitch) {{
                    rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                    switching = true; switchcount ++; 
                }} else {{
                    if (switchcount == 0 && dir == \"asc\") {{ dir = \"desc\"; switching = true; }}
                }}
            }}
        }}
        
        // 点击遮罩层关闭
        window.onclick = function(event) {{
            if (event.target == document.getElementById('modal')) {{
                document.getElementById('modal').style.display = "none";
            }}
        }}
    </script>
    </body></html>
    """
    
    with open(HTML_FILE, 'w', encoding='utf-8') as f: f.write(html)

if __name__ == "__main__":
    holders = scrape_data()
    if holders:
        db = load_db()
        generate_report(holders, db)
