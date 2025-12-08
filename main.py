import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import time
import random
from io import StringIO
import re

# ================= 配置区 =================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
CSV_FILE = "ssq.csv"

# 红球分组
RED_GROUPS = {
    'G01': [1, 19, 31], 'G02': [2, 21, 28], 'G03': [3, 22, 26],
    'G04': [4, 23, 24], 'G05': [5, 16, 30], 'G06': [6, 12, 33],
    'G07': [7, 15, 29], 'G08': [8, 18, 25], 'G09': [9, 10, 32],
    'G10': [11, 13, 27], 'G11': [14, 17, 20]
}
# 蓝球分组
BLUE_GROUPS = {
    'G1(01+16)': [1, 16], 'G2(02+15)': [2, 15], 'G3(03+14)': [3, 14],
    'G4(04+13)': [4, 13], 'G5(05+12)': [5, 12], 'G6(06+11)': [6, 11],
    'G7(07+10)': [7, 10], 'G8(08+09)': [8, 9]
}
# ========================================

# --- 1. 强力数据获取模块 (JSON API + 中彩网) ---

def get_headers():
    """伪装成真实浏览器"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'http://www.zhcw.com/',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

def fetch_sina_api():
    """源1：新浪彩票 JSON API (无缓存，秒级更新)"""
    print("📡 正在连接源1 (新浪API)...")
    # 这是一个隐藏的 App 接口，直接返回 JSON 数据，无需解析 HTML
    url = "https://match.lottery.sina.com.cn/client/index/client_list?lotteryCode=ssq&page=1"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        data = r.json()
        
        # 解析 JSON
        results = []
        if 'result' in data and 'data' in data['result']:
            for item in data['result']['data']:
                issue = item.get('issueNo') # 期号 2025141
                draw_code = item.get('drawCode') # "02,04,05,10,12,13|06"
                
                if issue and draw_code:
                    red_str, blue_str = draw_code.split('|')
                    reds = [int(x) for x in red_str.split(',')]
                    blue = int(blue_str)
                    
                    row = [int(issue)] + reds + [blue]
                    results.append(row)
        
        if results:
            df = pd.DataFrame(results, columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
            print(f"✅ 源1 (新浪API) 获取成功! 最新期号: {df['Issue'].max()}")
            return df
    except Exception as e:
        print(f"❌ 源1失败: {e}")
    return None

def fetch_zhcw_html():
    """源2：中彩网 (用户指定的网站)"""
    print("📡 正在连接源2 (中彩网 zhcw.com)...")
    url = "http://www.zhcw.com/ssq/kjgg/"
    try:
        r = requests.get(url, headers=get_headers(), timeout=15)
        r.encoding = 'utf-8'
        
        # 中彩网的表格比较标准，直接寻找 tr
        dfs = pd.read_html(StringIO(r.text))
        
        for df in dfs:
            # 中彩网的表通常有 "期号" "中奖号码" 等列
            # 把它转为字符串方便搜索
            s_df = df.astype(str)
            if s_df.apply(lambda x: x.str.contains('期号')).any().any():
                clean_data = []
                for _, row in df.iterrows():
                    # 提取该行的所有数字
                    row_str = " ".join([str(v) for v in row.values])
                    # 正则提取: 2025开头跟随3位数字的期号
                    issue_match = re.search(r'(202[4-9]\d{3})', row_str)
                    
                    if issue_match:
                        issue = int(issue_match.group(1))
                        # 提取红蓝球：通常中彩网一行里会有多个数字，我们需要找到除了期号外的 7 个数字
                        # 简单粗暴法：把行里所有数字拿出来
                        nums = re.findall(r'\d+', row_str)
                        nums = [int(n) for n in nums]
                        
                        # 过滤掉期号本身
                        balls = [n for n in nums if n != issue and n <= 33]
                        
                        # 双色球至少要有7个球(6红1蓝)，有时会有无关数字，取前7个或特定逻辑
                        # 中彩网表格比较干净，通常是 期号, 红1..红6, 蓝
                        # 我们尝试从这一行提取 6个 1-33 的红球 和 1个 1-16 的蓝球
                        
                        # 更精准的方法：中彩网分开列显示
                        # 让我们尝试直接清洗 df
                        # 假设我们只取前8列有效数字
                        real_balls = []
                        for val in row.values:
                            s_val = str(val).strip()
                            if s_val.isdigit():
                                real_balls.append(int(s_val))
                        
                        # 如果这一行解析出来的数字 >= 8 (1期号 + 6红 + 1蓝)
                        if len(real_balls) >= 8:
                            # 校验期号
                            if real_balls[0] > 2020000:
                                clean_data.append(real_balls[:8])

                if clean_data:
                    new_df = pd.DataFrame(clean_data, columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
                    print(f"✅ 源2 (中彩网) 获取成功! 最新期号: {new_df['Issue'].max()}")
                    return new_df

    except Exception as e:
        print(f"❌ 源2失败: {e}")
    return None

def fetch_500_xml():
    """源3：500网 XML (兜底)"""
    print("📡 正在连接源3 (500 XML)...")
    import xml.etree.ElementTree as ET
    try:
        t = int(time.time()*1000)
        url = f"http://kaijiang.500.com/static/info/kaijiang/xml/ssq/list.xml?_t={t}"
        r = requests.get(url, headers=get_headers(), timeout=10)
        r.encoding = 'gb2312'
        root = ET.fromstring(r.text)
        data = []
        for row in root.findall('row'):
            expect = row.get('expect')
            opencode = row.get('opencode')
            if expect and opencode:
                reds, blue = opencode.split('|')
                item = [int(expect)] + [int(x) for x in reds.split(',')] + [int(blue)]
                data.append(item)
        if data:
            return pd.DataFrame(data, columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
    except: pass
    return None

def get_web_data():
    """多源聚合 - 优先级：新浪API > 中彩网 > 500 XML"""
    
    # 1. 新浪 API (目前最稳)
    df = fetch_sina_api()
    if df is not None: return df.sort_values(by='Issue')
    
    # 2. 中彩网 (你看到的那个网站)
    df = fetch_zhcw_html()
    if df is not None: return df.sort_values(by='Issue')
    
    # 3. 500 XML
    df = fetch_500_xml()
    if df is not None: return df.sort_values(by='Issue')
    
    return None

def update_database():
    df_local = pd.DataFrame()
    if os.path.exists(CSV_FILE):
        try: df_local = pd.read_csv(CSV_FILE)
        except: pass
    
    df_net = get_web_data()
    
    if df_net is not None and not df_net.empty:
        if not df_local.empty:
            df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
            df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'], keep='last')
        else:
            df_final = df_net
            
        df_final = df_final.sort_values(by='Issue')
        df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
        return df_final
    
    print("⚠️ 严重警告：所有数据源均无法连接，请检查网络或Github Actions IP是否被封禁。")
    return df_local

# --- 2. 算法与绘图 (保持不变) ---
def calc_slope(series, window=5):
    y = series.tail(window)
    if len(y) < 2: return 0
    try: return np.polyfit(np.arange(len(y)), y, 1)[0] * 10 
    except: return 0

def get_energy(df, targets, type='red'):
    prob_miss = 27/33 if type == 'red' else 15/16
    cols = ['R1','R2','R3','R4','R5','R6'] if type == 'red' else ['Blue']
    is_hit = df[cols].isin(targets).any(axis=1) if type == 'red' else df['Blue'].isin(targets)
    scores = []; curr = 0
    for hit in is_hit:
        curr = (curr - (1 - prob_miss)) if hit else (curr + prob_miss * (5 if type=='blue' else 1))
        scores.append(curr)
    return pd.Series(scores)

def calculate_kline_for_chart(df, target_ball, ball_type, period):
    scores = get_energy(df, [target_ball], ball_type).tolist()
    ohlc = []
    for i in range(0, len(scores), period):
        chunk = scores[i : i+period]
        if not chunk: continue
        prev = scores[i-1] if i > 0 else 0
        ohlc.append([prev, max(prev, max(chunk)), min(prev, min(chunk)), chunk[-1]])
    k_df = pd.DataFrame(ohlc, columns=['Open', 'High', 'Low', 'Close'])
    k_df['MA'] = k_df['Close'].rolling(5 if period == 10 else 10).mean()
    k_df['Index'] = range(len(k_df))
    return k_df

def generate_interactive_page(df, last_issue, ai_text):
    if not os.path.exists("public"): os.makedirs("public")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.1, subplot_titles=("趋势(10期)", "短线(3期)"), row_heights=[0.6, 0.4])
    df_chart = df.tail(400).reset_index(drop=True)
    
    for ball in range(1, 34): 
        d10 = calculate_kline_for_chart(df_chart, ball, 'red', 10)
        d3 = calculate_kline_for_chart(df_chart, ball, 'red', 3).tail(100)
        v = (ball == 1)
        fig.add_trace(go.Candlestick(x=d10.index, open=d10['Open'], high=d10['High'], low=d10['Low'], close=d10['Close'], visible=v, increasing_line_color='#F44336', decreasing_line_color='#2196F3'), 1, 1)
        fig.add_trace(go.Scatter(x=d10.index, y=d10['MA'], mode='lines', visible=v, line=dict(color='yellow', width=1)), 1, 1)
        fig.add_trace(go.Candlestick(x=list(range(len(d3))), open=d3['Open'], high=d3['High'], low=d3['Low'], close=d3['Close'], visible=v, increasing_line_color='#E91E63', decreasing_line_color='#4CAF50'), 2, 1)
        fig.add_trace(go.Scatter(x=list(range(len(d3))), y=d3['MA'], mode='lines', visible=v, line=dict(color='white', width=1, dash='dot')), 2, 1)
    
    for ball in range(1, 17):
        d10 = calculate_kline_for_chart(df_chart, ball, 'blue', 10)
        d3 = calculate_kline_for_chart(df_chart, ball, 'blue', 3).tail(100)
        fig.add_trace(go.Candlestick(x=d10.index, open=d10['Open'], high=d10['High'], low=d10['Low'], close=d10['Close'], visible=False, increasing_line_color='#FF9800', decreasing_line_color='#03A9F4'), 1, 1)
        fig.add_trace(go.Scatter(x=d10.index, y=d10['MA'], mode='lines', visible=False, line=dict(color='cyan', width=1)), 1, 1)
        fig.add_trace(go.Candlestick(x=list(range(len(d3))), open=d3['Open'], high=d3['High'], low=d3['Low'], close=d3['Close'], visible=False, increasing_line_color='#9C27B0', decreasing_line_color='#8BC34A'), 2, 1)
        fig.add_trace(go.Scatter(x=list(range(len(d3))), y=d3['MA'], mode='lines', visible=False, line=dict(color='white', width=1, dash='dot')), 2, 1)

    fig.update_layout(template="plotly_dark", height=600, margin=dict(t=30, l=10, r=10, b=10), showlegend=False, dragmode='pan', xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False)
    plot_div = fig.to_html(full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False}, div_id='plotly_div')
    
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no"><title>第{last_issue}期</title>
    <style>body{{background:#121212;color:#eee;margin:0;font-family:sans-serif}}.header{{padding:10px;background:#1e1e1e}}select{{background:#333;color:#fff;border:1px solid #555;padding:8px;width:45%;margin-top:5px}}textarea{{position:absolute;left:-999px}}</style></head>
    <body><div class="header"><h3>📊 第{last_issue}期控制台</h3><button onclick="copyData()" style="width:100%;padding:10px;background:#00C853;color:fff;border:none;border-radius:4px">📋 复制AI数据</button><textarea id="ai">{ai_text}</textarea>
    <div style="display:flex;justify-content:space-between;margin-top:5px"><select id="r" onchange="s('red')"><option disabled>红球</option>{''.join([f'<option value="{i}" {"selected" if i==1 else ""}>{i:02d}</option>' for i in range(1,34)])}</select>
    <select id="b" onchange="s('blue')"><option selected disabled>蓝球</option>{''.join([f'<option value="{i}">{i:02d}</option>' for i in range(1,17)])}</select></div></div>{plot_div}
    <script>function copyData(){{var c=document.getElementById("ai");c.select();document.execCommand("copy");alert("已复制")}}
    function s(t){{var d=document.getElementById('plotly_div'),v,b;if(t=='red'){{document.getElementById('b').selectedIndex=0;v=parseInt(document.getElementById('r').value);b=(v-1)*4}}else{{document.getElementById('r').selectedIndex=0;v=parseInt(document.getElementById('b').value);b=132+(v-1)*4}}
    var a=new Array(196).fill(false);a[b]=a[b+1]=a[b+2]=a[b+3]=true;Plotly.restyle(d,{{'visible':a}})}}</script></body></html>"""
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(html)

def generate_raw_text(rs, rg, bs, bg):
    return f"【数据集】\n红球:\n{rs.to_string(index=False)}\n\n蓝球:\n{bs.to_string(index=False)}\n\n红组:\n{rg.to_string(index=False)}\n\n蓝组:\n{bg.to_string(index=False)}"

def format_balls_html(row):
    r_sty = "display:inline-block;width:25px;height:25px;line-height:25px;border-radius:50%;background:#f44336;color:fff;text-align:center;font-weight:bold;margin:2px;"
    b_sty = "display:inline-block;width:25px;height:25px;line-height:25px;border-radius:50%;background:#2196f3;color:fff;text-align:center;font-weight:bold;margin:2px;"
    h = "<div style='text-align:center;padding:10px;background:#fff;border-bottom:1px solid #eee;'>"
    for i in range(1,7): h += f"<span style='{r_sty}'>{row[f'R{i}']:02d}</span>"
    h += f"<span style='{b_sty}'>{row['Blue']:02d}</span></div>"
    return h

def df_to_html_table(df, title):
    h = f"<div style='margin-top:10px;border:1px solid #ddd;border-radius:5px;overflow:hidden;'><div style='background:#f1f1f1;padding:5px;font-weight:bold;font-size:13px'>{title}</div>"
    h += "<table style='width:100%;border-collapse:collapse;font-size:11px;text-align:center;'>"
    h += "<tr style='background:#eee;'>" + "".join([f"<th>{c}</th>" for c in df.columns]) + "</tr>"
    for _, r in df.iterrows():
        bg = "#ffebee" if "🔥" in str(r.values) else ("#e8f5e9" if "🚀" in str(r.values) else "#fff")
        h += f"<tr style='background:{bg};border-bottom:1px solid #eee;'>" + "".join([f"<td style='padding:4px'>{v}</td>" for v in r.values]) + "</tr>"
    h += "</table></div>"
    return h

def run_analysis_raw(df):
    rs = []
    for b in range(1, 34):
        s = get_energy(df, [b], 'red')
        cur = s.iloc[-1]; m5 = s.rolling(5).mean().iloc[-1]
        tag = "🔥" if cur > m5 else "❄️"
        rs.append({'号': f"{b:02d}", 'S10': round(calc_slope(s,5),1), '态': tag})
    
    bs = []
    for b in range(1, 17):
        s = get_energy(df, [b], 'blue')
        cur = s.iloc[-1]; m5 = s.rolling(5).mean().iloc[-1]
        tag = "🔥" if cur > m5 else "❄️"
        bs.append({'号': f"{b:02d}", 'S10': round(calc_slope(s,5),1), '态': tag})

    rg = [{'组': k, '率': round(calc_slope(get_energy(df, v, 'red'), 10), 1)} for k,v in RED_GROUPS.items()]
    bg = [{'组': k, '率': round(calc_slope(get_energy(df, v, 'blue'), 5), 1)} for k,v in BLUE_GROUPS.items()]

    return (pd.DataFrame(rs).sort_values('S10', ascending=False),
            pd.DataFrame(rg).sort_values('率', ascending=False),
            pd.DataFrame(bs).sort_values('S10', ascending=False),
            pd.DataFrame(bg).sort_values('率', ascending=False))

def main():
    print("🚀 启动 (v4.0 终极API版)...")
    
    old_issue = 0
    if os.path.exists(CSV_FILE):
        try: old_issue = int(pd.read_csv(CSV_FILE)['Issue'].iloc[-1])
        except: pass

    # 数据更新
    df = update_database()
    if df is None or df.empty: return
    
    last_row = df.iloc[-1]
    new_issue = int(last_row['Issue'])
    is_new = new_issue > old_issue
    
    print(f"本地: {old_issue} | 线上(最终): {new_issue} | 状态: {'🆕 已更新' if is_new else '🔁 未更新'}")

    # 分析
    rs, rg, bs, bg = run_analysis_raw(df)
    ai_text = generate_raw_text(rs, rg, bs, bg)
    generate_interactive_page(df, new_issue, ai_text)

    # 推送
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if repo else "public/index.html"
    
    # 动态标题
    status_emoji = "✅" if is_new else "⚠️"
    title = f"{status_emoji} 双色球第{new_issue}期"
    
    msg = f"{format_balls_html(last_row)}"
    
    if is_new:
        msg += f"<p style='color:green;text-align:center;font-size:12px;margin:5px 0;'>✅ 已获取到最新第 {new_issue} 期数据！</p>"
    else:
        msg += f"<p style='color:red;text-align:center;font-size:12px;margin:5px 0;'>⚠️ 警告：全网数据源尚未同步，仍显示旧数据。</p>"
    
    msg += f"<div style='text-align:center;margin:10px'><a href='{url}' style='color:#007bff;text-decoration:none;'>📊 打开交互图表控制台</a></div>"
    msg += df_to_html_table(rs, "🔴 红球全量趋势 (S10降序)")
    msg += df_to_html_table(bs, "🔵 蓝球全量趋势")
    msg += df_to_html_table(rg, "🛡️ 红球分组")
    msg += df_to_html_table(bg, "⚖️ 蓝球分组")
    
    if PUSH_TOKEN:
        try:
            requests.post('http://www.pushplus.plus/send', json={"token": PUSH_TOKEN, "title": title, "content": msg, "template": "html"})
            print("✅ 推送成功")
        except Exception as e: print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    main()
