import requests
import json
import os
import datetime
from datetime import timedelta

# ================= 配置区 =================
# 从 GitHub 环境变量读取 Key (安全性)
API_KEY = os.environ.get("BIS_API_KEY") 

TICKER = "ACORNS"
# 这里对应您刚上传的文件名
DB_FILE = "data.json" 
HTML_FILE = "index.html" 
# 设置为 6000，确保覆盖您目前的 5000 人，并留有增长空间
TARGET_COUNT = 6000 
# =========================================

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def fetch_data_via_api():
    if not API_KEY:
        print("❌ 错误: 未配置 API Key (Secrets)")
        return []
        
    print(f"🚀 [GitHub Action] 开始抓取 {TICKER} (目标前 {TARGET_COUNT} 名)...")
    url = "https://api.bestinslot.xyz/v3/brc20/holders"
    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}
    
    all_holders = []
    offset = 0
    batch_size = 100
    
    # 循环抓取，直到达到目标数量
    while len(all_holders) < TARGET_COUNT:
        params = {
            "ticker": TICKER,
            "sort_by": "balance",
            "order": "desc",
            "offset": offset,
            "count": batch_size
        }
        try:
            resp = requests.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                items = resp.json().get('data', [])
                if not items: break # 没数据了
                
                for item in items:
                    # 数据清洗：确保地址格式与您旧数据一致 (全部小写)
                    wallet = item['wallet'].lower()
                    balance = float(item['overall_balance'])
                    
                    all_holders.append({
                        "rank": len(all_holders) + 1,
                        "key": wallet,
                        "bal": balance,
                        # 生成缩略地址用于显示
                        "short_addr": wallet[:6] + "..." + wallet[-4:]
                    })
                
                offset += batch_size
                # 如果单次获取不足 100，说明已经是最后一页
                if len(items) < batch_size: break
            else:
                print(f"⚠️ API 报错: {resp.status_code} - {resp.text}")
                break
        except Exception as e:
            print(f"❌ 网络错误: {e}")
            break
            
    print(f"✅ 抓取完成: 共 {len(all_holders)} 个地址")
    return all_holders

def generate_report(holders, db):
    chart_data = {}
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    html_rows = ""
    
    # 获取旧数据的键集合，用于判断 New (新增地址)
    old_keys = set(db.keys()) if db else set()
    
    for h in holders:
        key = h['key']
        
        # 1. 历史数据处理
        if key not in db: db[key] = []
        history = db[key]
        
        # 防止同一天重复运行导致数据重复
        if not history or history[-1]['t'] != today_str:
            # 简单的断点补全 (如果昨天没跑，补齐中间的空档，让图表连续)
            if history:
                last_date_str = history[-1]['t']
                try:
                    last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
                    curr_date = datetime.date.today()
                    delta = (curr_date - last_date).days
                    if delta > 1:
                        # 补全中间缺失的天数 (用旧余额填充)
                        for i in range(1, delta):
                            missing_day = (last_date + timedelta(days=i)).strftime("%Y-%m-%d")
                            history.append({"t": missing_day, "y": history[-1]['y']})
                except: pass
            
            # 写入今天的最新余额
            history.append({"t": today_str, "y": h['bal']})
        else:
            # 如果今天已经跑过，更新今天的最新值
            history[-1]['y'] = h['bal']
        
        # 只保留最近 90 天数据 (避免文件无限膨胀)
        if len(history) > 90: history = history[-90:]
        db[key] = history
        
        # 2. 计算 24H 变化
        change = 0
        if len(history) >= 2:
            change = h['bal'] - history[-2]['y']
        
        # 标记是否为新进大户 (昨天不在库里，今天在)
        is_new = (key not in old_keys) and (len(history) == 1)
        
        h['change'] = change
        chart_data[key] = history
        
        # 3. 生成 HTML 表格行
        chg_cls = "flat"; chg_txt = "-"
        if change > 0: 
            chg_cls = "up"
            chg_txt = f"+{change:,.0f} ▲"
        elif change < 0: 
            chg_cls = "down"
            chg_txt = f"{change:,.0f} ▼"
            
        new_tag = "<span class='new'>NEW</span>" if is_new else ""
        
        btn = f"<button class='btn' onclick=\"show('{key}')\">📈</button>"
        
        html_rows += f"""
        <tr>
            <td data-sort="{h['rank']}">#{h['rank']}</td>
            <td>{new_tag} <span class="addr">{h['key']}</span></td>
            <td data-sort="{h['bal']}">{h['bal']:,.0f}</td>
            <td data-sort="{change}" class="{chg_cls}">{chg_txt}</td>
            <td>{btn}</td>
        </tr>"""

    # 保存数据库回文件 (这一步会被 Git Commit 上传)
    save_db(db)
    
    # 生成 HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>ACORNS Cloud Monitor</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ background: #121212; color: #ccc; font-family: sans-serif; padding: 20px; }}
            h1 {{ text-align: center; color: #00bcd4; }}
            .info {{ text-align: center; color: #666; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; background: #1e1e1e; font-size: 13px; }}
            th, td {{ padding: 10px; border-bottom: 1px solid #333; text-align: left; }}
            th {{ background: #252525; cursor: pointer; color: #888; }}
            th:hover {{ color: #fff; }}
            .up {{ color: #f44336; }} .down {{ color: #4caf50; }} 
            .addr {{ color: #00bcd4; font-family: monospace; }}
            .new {{ background: #f44336; color: #fff; padding: 2px 4px; border-radius: 3px; font-size: 10px; margin-right:5px; }}
            .btn {{ background: #333; border: 1px solid #555; color: #fff; cursor: pointer; padding: 2px 8px; }}
            #modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); }}
            .modal-content {{ background: #222; margin: 10% auto; padding: 20px; width: 80%; height: 400px; }}
        </style>
    </head>
    <body>
    <h1>🌰 ACORNS 每日监控 ({len(holders)}人)</h1>
    <div class="info">GitHub 自动更新 | {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
    <table id="myTable">
        <thead>
            <tr>
                <th onclick="s(0)">排名 ⇵</th>
                <th>地址</th>
                <th onclick="s(2)">持仓 ⇵</th>
                <th onclick="s(3)">24H 变化 ⇵</th>
                <th>走势</th>
            </tr>
        </thead>
        <tbody>{html_rows}</tbody>
    </table>
    
    <div id="modal" onclick="this.style.display='none'">
        <div class="modal-content"><canvas id="chart"></canvas></div>
    </div>
    
    <script>
        const data = {json.dumps(chart_data)};
        let c;
        function show(k) {{
            document.getElementById('modal').style.display='block';
            if(c) c.destroy();
            c = new Chart(document.getElementById('chart'), {{
                type: 'line',
                data: {{ labels: data[k].map(p=>p.t), datasets: [{{ label: '持仓', data: data[k].map(p=>p.y), borderColor: '#00bcd4', pointRadius: 3 }}] }},
                options: {{ maintainAspectRatio: false, scales: {{ y: {{ grid: {{ color: '#333' }} }} }} }}
            }});
        }}
        // 简化的排序函数
        function s(n) {{
            var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
            table = document.getElementById("myTable");
            switching = true; dir = "asc"; 
            while (switching) {{
                switching = false; rows = table.rows;
                for (i = 1; i < (rows.length - 1); i++) {{
                    shouldSwitch = false;
                    x = parseFloat(rows[i].getElementsByTagName("TD")[n].getAttribute("data-sort"));
                    y = parseFloat(rows[i + 1].getElementsByTagName("TD")[n].getAttribute("data-sort"));
                    if (dir == "asc") {{ if (x > y) {{ shouldSwitch = true; break; }} }} 
                    else if (dir == "desc") {{ if (x < y) {{ shouldSwitch = true; break; }} }}
                }}
                if (shouldSwitch) {{
                    rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                    switching = true; switchcount ++; 
                }} else {{
                    if (switchcount == 0 && dir == "asc") {{ dir = "desc"; switching = true; }}
                }}
            }}
        }}
    </script>
    </body></html>
    """
    
    with open(HTML_FILE, 'w', encoding='utf-8') as f: f.write(html)

if __name__ == "__main__":
    # 1. 抓数据
    holders = fetch_data_via_api()
    if holders:
        # 2. 读取刚上传的旧数据库
        db = load_db()
        # 3. 合并新旧数据并生成网页
        generate_report(holders, db)