import requests
import json
import os
import datetime
from datetime import timedelta, timezone

# ================= ⚙️ 配置区 =================
# 1. 核心数据源 (BestInSlot V2 - 速度最快)
HOLDERS_URL = "https://v2api.bestinslot.xyz/brc2.0/holders?tick=acorns"

# 2. 辅助数据源 (BRC20 Build - 用于查历史)
EXPLORER_API = "https://explorer.brc20.build/api/v2"
TOKEN_CONTRACT = "0x4aa8e9ca6d90e2e47b44336aa4725894332c1b16"
PROJECT_WALLET = "0xa07764097a4da7f3b61a562ca1f8e6779494748c"

# 3. 代币总量 (用于计算占比)
TOTAL_SUPPLY = 999703067 

# 4. 文件名 (保持您当前的设置)
DB_FILE = "acorns_light_db.json"
HTML_FILE = "acorns_monitor_v35_plus.html"

# 5. 备注名单
WATCHLIST = {
    "0xa07764097a4da7f3b61a562ca1f8e6779494748c": "🥇 榜一 (项目方)",
    "0x899cdf7bf5cf1c5a1b3c9afab2faf55482b97662": "🥈 榜二 (池子)",
        "0xbacb6e7774bb84dfcc0f5ad89c51782eade91f7e": "大宇钱包",
    "0xd3a5b717ab78f6075def527f070b9ee0dc662828": "BIS",
    "0x63160c1f9f071b57b6860bd8de66c7cb87295014": "CATSWAP",
    "0xf97ed5736eb42b0056b030e56349b3f48fce1898": "岩姐线上伙伴--8sats",
    "0xb7f1b7b18c070f998320ca75d1f1e1e33d7ab421": "岩姐团队长吕小金&J K--8.5sats",
    "0xb9d545610680be42046a75d51b199b107cb51c6c": "岩姐伙伴陈老师9.3sats"
}
# ============================================

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

# === 核心功能 1: 深度溯源 MINT 名单 ===
def fetch_mint_list_deep():
    print(f"🕵️‍♂️ [1/3] 正在全量扫描项目方历史，寻找 MINT 地址...")
    print("⏳ 正在翻阅链上账本 (为了不漏掉早期地址，这需要一点时间)...")
    
    minters = set()
    url = f"{EXPLORER_API}/addresses/{PROJECT_WALLET}/token-transfers"
    params = {"token": TOKEN_CONTRACT, "type": "ERC-20", "limit": 50}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    total_scanned = 0
    
    while True:
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200: break
            
            data = resp.json()
            items = data.get('items', [])
            if not items: break
            
            total_scanned += len(items)
            print(f"   已扫描 {total_scanned} 笔交易...", end="\r")
            
            for item in items:
                # 校验合约
                if item.get('token', {}).get('address', '').lower() != TOKEN_CONTRACT.lower(): continue
                
                from_addr = item.get('from', {}).get('hash', '').lower()
                to_addr = item.get('to', {}).get('hash', '').lower()
                
                # 项目方发出去的 -> 接收者就是 Minter
                if from_addr == PROJECT_WALLET.lower():
                    minters.add(to_addr)
            
            # 翻页逻辑
            if 'next_page_params' in data and data['next_page_params']:
                params.update(data['next_page_params'])
            else:
                break 
        except: break
            
    print(f"\n✅ MINT 名单建立完毕！共发现 {len(minters)} 个原始地址。")
    return minters

# === 核心功能 2: 智能验真 ===
def check_is_truly_new(address):
    url = f"{EXPLORER_API}/addresses/{address}/token-transfers"
    params = {"token": TOKEN_CONTRACT, "type": "ERC-20", "limit": 10}
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if resp.status_code == 200:
            items = resp.json().get('items', [])
            if not items: return True # 无记录，肯定是新人
            
            # 检查是否有早于24小时的交易
            now = datetime.datetime.now(timezone.utc)
            for item in items:
                ts_str = item.get('timestamp') 
                try:
                    dt = datetime.datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    if (now - dt).total_seconds() > 86400: return False # 是老手回归
                except: pass
    except: pass
    return True

# === 主数据抓取 ===
def fetch_data(minters_set, db_old_keys):
    print(f"🚀 [2/3] 正在下载全量持仓榜...")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(HOLDERS_URL, headers=headers, timeout=30)
        if resp.status_code != 200: return []
        items = resp.json().get('items', [])
        
        holders = []
        candidates_for_check = [] 
        
        for item in items:
            ox = item.get('evm_wallet')
            btc = item.get('btc_wallet')
            bal = float(item.get('total_balance') or item.get('evm_withdrawable_balance') or 0)
            
            if ox:
                key = ox.lower()
                if not btc: btc = "-"
                
                # 1. 判断 Mint
                is_mint = (key in minters_set)
                
                # 2. 计算占比
                percent = (bal / TOTAL_SUPPLY) * 100
                
                # 3. 初步判断是否为新人
                is_potential_new = (key not in db_old_keys) and (len(db_old_keys) > 0)
                
                status = ""
                if is_potential_new:
                    status = "CHECKING"
                    candidates_for_check.append(key)
                
                holders.append({
                    "rank": len(holders) + 1,
                    "key": key,
                    "btc": btc,
                    "bal": bal,
                    "pct": percent,
                    "is_mint": is_mint,
                    "status": status
                })
        
        # === 批量验真 ===
        if candidates_for_check:
            print(f"🕵️‍♂️ [3/3] 正在核实 {len(candidates_for_check)} 个新出现的地址...")
            skip_check = len(candidates_for_check) > 50
            
            count = 0
            cache = {}
            for addr in candidates_for_check:
                count += 1
                if skip_check:
                    res = "NEW"
                else:
                    print(f"   核查中 ({count}/{len(candidates_for_check)})...", end="\r")
                    is_true = check_is_truly_new(addr)
                    res = "NEW" if is_true else "RETURN" 
                
                cache[addr] = res
            
            for h in holders:
                if h['status'] == "CHECKING":
                    h['status'] = cache.get(h['key'], "NEW")
            print("\n✅ 核实完成。")
            
        return holders
    except Exception as e:
        print(f"❌ 错误: {e}")
        return []

def generate_report(holders, db):
    chart_data = {}
    
    # === 北京时间修正 (UTC+8) ===
    tz_cn = timezone(timedelta(hours=8))
    today_str = datetime.datetime.now(tz_cn).strftime("%Y-%m-%d")
    
    table_data = [] 
    
    for h in holders:
        key = h['key']
        if key not in db: db[key] = []
        history = db[key]
        
        # 历史记录逻辑
        if not history or history[-1]['t'] != today_str:
            if history:
                try:
                    last = datetime.datetime.strptime(history[-1]['t'], "%Y-%m-%d").date()
                    current_date_obj = datetime.datetime.strptime(today_str, "%Y-%m-%d").date()
                    delta = (current_date_obj - last).days
                    if delta > 1:
                        for i in range(1, delta):
                            d = (last + timedelta(days=i)).strftime("%Y-%m-%d")
                            history.append({"t": d, "y": history[-1]['y']})
                except: pass
            history.append({"t": today_str, "y": h['bal']})
        else:
            history[-1]['y'] = h['bal']
            
        if len(history) > 180: history = history[-180:]
        db[key] = history
        
        change = 0
        if len(history) >= 2: 
            raw_change = h['bal'] - history[-2]['y']
            if abs(raw_change) >= 1: change = raw_change

        chart_data[key] = history
        
        note = WATCHLIST.get(key, "")
        if h['is_mint'] and key != PROJECT_WALLET.lower():
            note = "🎁 [MINT] " + note
            
        table_data.append({
            "rank": h['rank'],
            "key": key,
            "btc": h['btc'],
            "bal": h['bal'],
            "pct": h['pct'],
            "change": change,
            "note": note,
            "status": h['status'],
            "is_new_day": (len(history) == 1)
        })

    save_db(db)
    
    # === HTML 生成 ===
    json_chart = json.dumps(chart_data)
    json_table = json.dumps(table_data)
    
    # === 北京时间显示 ===
    now = datetime.datetime.now(tz_cn).strftime("%Y-%m-%d %H:%M")
    
    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"><title>ACORNS V35+ 融合版</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body{{background:#121212;color:#ccc;font-family:sans-serif;padding:20px}}
        h1{{text-align:center;color:#00bcd4}} .info{{text-align:center;color:#666}}
        
        .controls {{text-align:center; margin:20px 0;}}
        input {{background:#333;border:1px solid #555;color:#fff;padding:8px;border-radius:4px;width:300px;}}
        
        table{{width:100%;border-collapse:collapse;background:#1e1e1e;font-size:13px}}
        th,td{{padding:10px;border-bottom:1px solid #333;text-align:left}}
        th{{background:#252525;color:#888;cursor:pointer;user-select:none}} 
        th:hover{{color:#fff;background:#333}}
        
        .addr-0x{{color:#00bcd4;font-family:monospace;display:block}} 
        .addr-btc{{color:#666;font-size:11px;font-family:monospace}}
        .up{{color:#f44336}} .down{{color:#4caf50}} 
        
        .mint-tag{{background:#9c27b0;color:#fff;padding:2px 4px;font-size:10px;border-radius:3px;font-weight:bold;margin-right:4px}}
        .new-tag{{background:#f44336;color:#fff;padding:2px 4px;font-size:10px;border-radius:3px;margin-right:4px}}
        .ret-tag{{background:#2196F3;color:#fff;padding:2px 4px;font-size:10px;border-radius:3px;margin-right:4px}}
        .rem{{background:#ff9800;color:#000;padding:2px 4px;font-size:10px;border-radius:3px;font-weight:bold}}
        
        .btn{{background:#333;border:1px solid #555;color:#fff;cursor:pointer;padding:4px 8px;border-radius:4px}}
        
        #modal{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);z-index:999}}
        .box{{background:#222;margin:5% auto;width:90%;max-width:900px;height:500px;padding:20px;border-radius:8px;position:relative}}
        .close{{position:absolute;top:10px;right:15px;font-size:24px;cursor:pointer;color:#fff}}
    </style></head><body>
    
    <h1>🌰 ACORNS V35+ (终极融合版)</h1>
    <div class="info">总人数: <span id="count">{len(holders)}</span> | 更新: {now} (北京时间)</div>
    
    <div class="controls">
        <input type="text" id="search" placeholder="🔍 搜索地址 / MINT / NEW / 备注..." onkeyup="render()">
    </div>
    
    <table>
        <thead>
            <tr>
                <th onclick="sort('rank')">排名 ⇵</th>
                <th onclick="sort('key')">地址 (0x / btc)</th>
                <th onclick="sort('bal')">持仓 ⇵</th>
                <th onclick="sort('pct')">占比 % ⇵</th>
                <th onclick="sort('change')">24H 变化 ⇵</th>
                <th>趋势</th>
            </tr>
        </thead>
        <tbody id="tbody"></tbody>
    </table>
    
    <div id="modal"><div class="box"><span class="close" onclick="document.getElementById('modal').style.display='none'">&times;</span><canvas id="c"></canvas></div></div>
    
    <script>
    let rawData = {json_table};
    const chartData = {json_chart};
    let sortCol = 'bal';
    let sortDesc = true; 
    
    function render() {{
        const tbody = document.getElementById('tbody');
        const search = document.getElementById('search').value.toLowerCase();
        
        let data = rawData.filter(item => 
            item.key.includes(search) || item.btc.includes(search) || item.note.toLowerCase().includes(search) || item.status.toLowerCase().includes(search)
        );
        document.getElementById('count').innerText = data.length;
        
        data.sort((a, b) => {{
            let valA = a[sortCol];
            let valB = b[sortCol];
            if (typeof valA === 'string') return sortDesc ? valB.localeCompare(valA) : valA.localeCompare(valB);
            return sortDesc ? (valB - valA) : (valA - valB);
        }});
        
        let html = [];
        data.forEach(item => {{
            let balStr = item.bal.toLocaleString('en-US', {{maximumFractionDigits: 0}});
            let pctStr = item.pct.toFixed(2) + "%";
            let chgClass = "flat", chgText = "-";
            if(item.change > 0) {{ 
                chgClass="up"; 
                chgText = "+" + item.change.toLocaleString('en-US', {{maximumFractionDigits: 0}}) + " ▲"; 
            }}
            else if(item.change < 0) {{ 
                chgClass="down"; 
                chgText = item.change.toLocaleString('en-US', {{maximumFractionDigits: 0}}) + " ▼"; 
            }}
            
            let tags = "";
            if(item.status === "NEW") tags += "<span class='new-tag'>🔥 NEW</span>";
            if(item.status === "RETURN") tags += "<span class='ret-tag'>♻️ 回归</span>";
            
            if(item.note) {{
                if(item.note.includes("MINT")) {{
                     let cleanNote = item.note.replace("🎁 [MINT] ", "");
                     tags += "<span class='mint-tag'>MINT</span>";
                     if(cleanNote) tags += "<span class='rem'>" + cleanNote + "</span> ";
                }} else {{
                     tags += "<span class='rem'>" + item.note + "</span> ";
                }}
            }}
            
            html.push(`
                <tr>
                    <td>#${{item.rank}}</td>
                    <td>${{tags}}<span class="addr-0x">${{item.key}}</span><span class="addr-btc">${{item.btc}}</span></td>
                    <td style="color:#fff;font-weight:bold">${{balStr}}</td>
                    <td style="color:#aaa">${{pctStr}}</td>
                    <td class="${{chgClass}}">${{chgText}}</td>
                    <td><button class="btn" onclick="show('${{item.key}}')">📈</button></td>
                </tr>
            `);
        }});
        tbody.innerHTML = html.join('');
    }}
    
    function sort(col) {{
        if(sortCol === col) sortDesc = !sortDesc;
        else {{ sortCol = col; sortDesc = true; }}
        render();
    }}
    
    let myChart;
    function show(key) {{
        document.getElementById('modal').style.display='block';
        if(myChart) myChart.destroy();
        const pts = chartData[key];
        if(!pts) return;
        myChart = new Chart(document.getElementById('c'), {{
            type: 'line',
            data: {{
                labels: pts.map(p=>p.t),
                datasets: [{{
                    label: '持仓量',
                    data: pts.map(p=>p.y),
                    borderColor: '#00bcd4',
                    backgroundColor: 'rgba(0,188,212,0.1)',
                    fill: true,
                    pointRadius: 3,
                    tension: 0.1
                }}]
            }},
            options: {{
                maintainAspectRatio: false,
                plugins: {{ title: {{ display: true, text: '地址: '+key, color:'#fff', font:{{size:16}} }} }},
                scales: {{ y: {{ grid: {{ color: '#333' }} }} }}
            }}
        }});
    }}
    
    window.onclick = function(e){{if(e.target==document.getElementById('modal'))document.getElementById('modal').style.display='none';}}
    render();
    </script>
    </body></html>
    """
    
    with open(HTML_FILE, 'w', encoding='utf-8') as f: f.write(html)
    return HTML_FILE

if __name__ == "__main__":
    db = load_db()
    minters_set = fetch_mint_list_deep()
    holders = fetch_data(minters_set, db.keys())
    
    if holders:
        path = generate_report(holders, db)
        print(f"✅ 报告已生成: {path}")
        # 注意: webbrowser 已移除，适合 GitHub Actions
    else:
        print("❌ 抓取失败。")

