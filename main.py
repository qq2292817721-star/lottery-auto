import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import xml.etree.ElementTree as ET
import time
import random

# ================= 配置区 =================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
CSV_FILE = "ssq.csv"

RED_GROUPS = {
    'G01': [1, 19, 31], 'G02': [2, 21, 28], 'G03': [3, 22, 26],
    'G04': [4, 23, 24], 'G05': [5, 16, 30], 'G06': [6, 12, 33],
    'G07': [7, 15, 29], 'G08': [8, 18, 25], 'G09': [9, 10, 32],
    'G10': [11, 13, 27], 'G11': [14, 17, 20]
}
BLUE_GROUPS = {
    'G1(01+16)': [1, 16], 'G2(02+15)': [2, 15], 'G3(03+14)': [3, 14],
    'G4(04+13)': [4, 13], 'G5(05+12)': [5, 12], 'G6(06+11)': [6, 11],
    'G7(07+10)': [7, 10], 'G8(08+09)': [8, 9]
}
# ========================================

# --- 1. 强力数据获取模块 (XML/API 版) ---

def fetch_xml_500():
    """源1：500彩票网官方XML接口 (最快、最稳)"""
    # 加上时间戳防止缓存
    t = int(time.time() * 1000)
    url = f"http://kaijiang.500.com/static/info/kaijiang/xml/ssq/list.xml?_t={t}"
    print(f"📡 正在连接源1 (XML接口)...")
    
    try:
        r = requests.get(url, timeout=10)
        r.encoding = 'gb2312' # XML通常是gb2312
        
        # 解析 XML
        root = ET.fromstring(r.text)
        data = []
        
        # 遍历 XML 节点
        for row in root.findall('row'):
            expect = row.get('expect') # 期号
            opencode = row.get('opencode') # 号码 "01,02,03,04,05,06|07"
            
            if expect and opencode:
                reds, blue = opencode.split('|')
                r_list = [int(x) for x in reds.split(',')]
                b_val = int(blue)
                
                # 构造一行数据
                item = [int(expect)] + r_list + [b_val]
                data.append(item)
        
        if data:
            df = pd.DataFrame(data, columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
            print(f"✅ 源1获取成功! 最新期号: {df['Issue'].max()}")
            return df
            
    except Exception as e:
        print(f"❌ 源1失败: {e}")
    return None

def fetch_html_500_bust_cache():
    """源2：传统的500.com网页 (带缓存破坏参数)"""
    t = int(time.time())
    url = f"http://datachart.500.com/ssq/history/newinc/history.php?limit=50&sort=0&_random={t}"
    print(f"📡 正在连接源2 (网页版)...")
    
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        r.encoding = 'utf-8'
        # 清洗数据
        from io import StringIO
        dfs = pd.read_html(StringIO(r.text))
        for df in dfs:
            if df.shape[1] >= 8 and len(df) > 5:
                # 简单的列名重置和清洗
                df = df.iloc[:, :8]
                df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
                # 强转数字，把非法行变成 NaN 并删除
                for col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                df = df.dropna().astype(int)
                if not df.empty:
                    print(f"✅ 源2获取成功! 最新期号: {df['Issue'].max()}")
                    return df
    except Exception as e:
        print(f"❌ 源2失败: {e}")
    return None

def get_web_data():
    """多源聚合获取"""
    # 优先尝试 XML，因为它几乎不会出错
    df = fetch_xml_500()
    if df is not None: return df.sort_values(by='Issue')
    
    # 其次尝试网页爬虫
    df = fetch_html_500_bust_cache()
    if df is not None: return df.sort_values(by='Issue')
    
    return None

def update_database():
    """数据库更新逻辑"""
    df_local = pd.DataFrame()
    if os.path.exists(CSV_FILE):
        try: df_local = pd.read_csv(CSV_FILE)
        except: pass
    
    # 联网获取
    df_net = get_web_data()
    
    if df_net is not None and not df_net.empty:
        if not df_local.empty:
            df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
            # 合并策略：用网络数据更新本地，以 Issue 为基准去重，保留网络端最新的数据
            df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'], keep='last')
        else:
            df_final = df_net
            
        df_final = df_final.sort_values(by='Issue')
        df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
        return df_final
    
    print("⚠️ 所有网络源均失败，使用本地数据。")
    return df_local

# --- 2. 核心算法 (保持稳定) ---
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

# --- 3. 绘图模块 ---
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

# --- 4. 辅助函数 ---
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
    print("🚀 启动 (v3.0 强力API版)...")
    
    # 获取本地旧期号
    old_issue = 0
    if os.path.exists(CSV_FILE):
        try: old_issue = int(pd.read_csv(CSV_FILE)['Issue'].iloc[-1])
        except: pass

    # 更新数据
    df = update_database()
    if df is None or df.empty: return
    
    # 状态判断
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
    
    title = f"{'✅' if is_new else '⚠️'} 双色球第{new_issue}期"
    msg = f"{format_balls_html(last_row)}"
    
    if is_new:
        msg += "<p style='color:green;text-align:center;font-size:12px'>✅ 已通过官方XML接口获取最新数据</p>"
    else:
        msg += f"<p style='color:red;text-align:center;font-size:12px'>⚠️ 数据仍为 {new_issue} 期。可能全网数据源尚未更新。</p>"
    
    msg += f"<div style='text-align:center;margin:10px'><a href='{url}'>📊 打开交互图表控制台</a></div>"
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
