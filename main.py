import json
import os
import time
import datetime
from datetime import timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

# ================= 配置区 =================
TARGET_URL = "https://bestinslot.xyz/brc2.0/acorns/holders"
DB_FILE = "data.json"
HTML_FILE = "index.html"

# 关注名单 (可选)
WATCHLIST = {
    "0xa07764097a4da7f3b61a562ca1f8e6779494748c": "🥇 榜一",
    "0x899cdf7bf5cf1c5a1b3c9afab2faf55482b97662": "🥈 榜二"
}
# =========================================

def setup_headless_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") # 无头模式，无界面运行
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # 模拟真实用户 User-Agent
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

def scrape_data():
    print(f"🚀 [GitHub] 启动隐形浏览器抓取: {TARGET_URL}")
    driver = setup_headless_driver()
    
    try:
        driver.get(TARGET_URL)
        time.sleep(5) # 等待网页初次加载
        
        # 暴力滚动逻辑 (模拟您的 V25)
        last_height = driver.execute_script("return document.body.scrollHeight")
        retries = 0
        
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            # 检查是否有新内容加载
            rows = len(driver.find_elements(By.TAG_NAME, "tr"))
            print(f"   ...已加载 {rows} 行", end="\r")
            
            if new_height == last_height:
                retries += 1
                if retries >= 5: # 如果连续5次高度没变，认为到底了
                    break
            else:
                retries = 0
                last_height = new_height
                
        print(f"\n✅ 滚动结束。开始解析...")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        holders = []
        
        for row in soup.select('table tr')[1:]:
            cols = row.find_all('td')
            if len(cols) >= 5:
                try:
                    def get_text(i): return cols[i].get_text(strip=True)
                    # 兼容不同网页结构的取值逻辑
                    raw_addr = cols[0].find('a').get('href').split('/')[-1] if cols[0].find('a') else get_text(0)
                    if "0x" not in raw_addr and cols[1].find('a'):
                        raw_addr = cols[1].find('a').get('href').split('/')[-1]
                        
                    bal_str = cols[4].get_text(strip=True).replace(',', '')
                    balance = float(bal_str)
                    
                    wallet = raw_addr.lower()
                    
                    holders.append({
                        "rank": len(holders) + 1,
                        "key": wallet,
                        "bal": balance,
                        "short": wallet[:6] + "..." + wallet[-4:]
                    })
                except: continue
        
        print(f"🎉 成功抓取 {len(holders)} 个地址 (0x...)")
        return holders
        
    except Exception as e:
        print(f"❌ 抓取出错: {e}")
        return []
    finally:
        driver.quit()

def generate_report(holders, db):
    chart_data = {}
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    html_rows = ""
    old_keys = set(db.keys()) if db else set()
    
    for h in holders:
        key = h['key']
        if key not in db: db[key] = []
        history = db[key]
        
        if not history or history[-1]['t'] != today_str:
            # 补全逻辑
            if history:
                try:
                    last_date = datetime.datetime.strptime(history[-1]['t'], "%Y-%m-%d").date()
                    delta = (datetime.date.today() - last_date).days
                    for i in range(1, delta):
                        history.append({"t": (last_date + timedelta(days=i)).strftime("%Y-%m-%d"), "y": history[-1]['y']})
                except: pass
            history.append({"t": today_str, "y": h['bal']})
        else:
            history[-1]['y'] = h['bal']
            
        if len(history) > 90: history = history[-90:]
        db[key] = history
        
        change = 0
        if len(history) >= 2: change = h['bal'] - history[-2]['y']
        
        is_new = (key not in old_keys) and (len(history) == 1)
        
        # 样式
        chg_cls = "flat"; chg_txt = "-"
        if change > 0: chg_cls = "up"; chg_txt = f"+{change:,.0f} ▲"
        elif change < 0: chg_cls = "down"; chg_txt = f"{change:,.0f} ▼"
        
        new_tag = "<span class='new'>NEW</span>" if is_new else ""
        rem = f"<span class='rem'>{WATCHLIST[key]}</span>" if key in WATCHLIST else ""
        btn = f"<button class='btn' onclick=\"show('{key}')\">📈</button>"
        
        html_rows += f"""<tr>
            <td data-sort="{h['rank']}">#{h['rank']}</td>
            <td>{new_tag} {rem} <span class="addr">{h['key']}</span></td>
            <td data-sort="{h['bal']}">{h['bal']:,.0f}</td>
            <td data-sort="{change}" class="{chg_cls}">{chg_txt}</td>
            <td>{btn}</td></tr>"""

    save_db(db)
    
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>ACORNS Cloud Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body{{background:#121212;color:#ccc;font-family:sans-serif;padding:20px}}
        h1{{text-align:center;color:#00bcd4}} .info{{text-align:center;color:#666}}
        table{{width:100%;border-collapse:collapse;background:#1e1e1e;margin-top:20px}}
        th,td{{padding:10px;border-bottom:1px solid #333;text-align:left}}
        th{{background:#252525;cursor:pointer;color:#888}} th:hover{{color:#fff}}
        .up{{color:#f44336}} .down{{color:#4caf50}} .addr{{color:#00bcd4;font-family:monospace}}
        .new{{background:#f44336;color:#fff;padding:2px 4px;font-size:10px;border-radius:3px}}
        .rem{{background:#ff9800;color:#000;padding:2px 4px;font-size:10px;border-radius:3px;font-weight:bold}}
        .btn{{background:#333;border:1px solid #555;color:#fff;cursor:pointer}}
        #modal{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8)}}
        .modal-content{{background:#222;margin:10% auto;padding:20px;width:80%;height:400px}}
    </style></head><body>
    <h1>🌰 ACORNS 每日监控 (0x版)</h1>
    <div class="info">GitHub 自动抓取 | 总人数: {len(holders)} | 更新: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
    <table id="myTable"><thead><tr>
        <th onclick="s(0)">排名 ⇵</th><th>地址</th><th onclick="s(2)">持仓 ⇵</th><th onclick="s(3)">24H 变化 ⇵</th><th>图</th>
    </tr></thead><tbody>{html_rows}</tbody></table>
    <div id="modal" onclick="this.style.display='none'"><div class="modal-content"><canvas id="chart"></canvas></div></div>
    <script>
        const data={json.dumps(chart_data)}; let c;
        function show(k){{document.getElementById('modal').style.display='block';if(c)c.destroy();c=new Chart(document.getElementById('chart'),{{type:'line',data:{{labels:data[k].map(p=>p.t),datasets:[{{label:'持仓',data:data[k].map(p=>p.y),borderColor:'#00bcd4',pointRadius:3}}]}},options:{{maintainAspectRatio:false,scales:{{y:{{grid:{{color:'#333'}}}}}}}}}})}}
        function s(n){{var t=document.getElementById("myTable"),r,sw,i,x,y,sh,d="asc",c=0;sw=true;while(sw){{sw=false;r=t.rows;for(i=1;i<(r.length-1);i++){{sh=false;x=parseFloat(r[i].getElementsByTagName("TD")[n].getAttribute("data-sort"));y=parseFloat(r[i+1].getElementsByTagName("TD")[n].getAttribute("data-sort"));if(d=="asc"){{if(x>y){{sh=true;break}}}}else if(d=="desc"){{if(x<y){{sh=true;break}}}}}}if(sh){{r[i].parentNode.insertBefore(r[i+1],r[i]);sw=true;c++}}else{{if(c==0&&d=="asc"){{d="desc";sw=true}}}}}}}}
    </script></body></html>"""
    
    with open(HTML_FILE, 'w', encoding='utf-8') as f: f.write(html)

if __name__ == "__main__":
    holders = scrape_data()
    if holders:
        db = load_db()
        generate_report(holders, db)
