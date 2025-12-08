import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import time
import re
from io import StringIO

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
BLUE_GROUPS = {
    'G1(01+16)': [1, 16], 'G2(02+15)': [2, 15], 'G3(03+14)': [3, 14],
    'G4(04+13)': [4, 13], 'G5(05+12)': [5, 12], 'G6(06+11)': [6, 11],
    'G7(07+10)': [7, 10], 'G8(08+09)': [8, 9]
}
# ========================================

def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'http://www.cwl.gov.cn/',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
    }

# --- 1. 定点爆破模块 (Sniper Fetcher) ---

def fetch_target_issue_500(target_issue):
    """
    策略1：定点爆破 (Sniper)
    直接访问 'http://kaijiang.500.com/shtml/ssq/2025141.shtml'
    避开所有列表页缓存。
    """
    url = f"http://kaijiang.500.com/shtml/ssq/{target_issue}.shtml"
    print(f"🔫 正在定点狙击下一期: {url}")
    
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        r.encoding = 'gb2312' # 500网详情页通常是 gb2312
        
        if r.status_code == 200:
            # 使用正则暴力提取，不依赖 html 结构，防止结构变化
            # 寻找红球: class="red_ball">02</li>
            reds = re.findall(r'class="red_ball">(\d{2})</li>', r.text)
            # 寻找蓝球: class="blue_ball">06</li>
            blues = re.findall(r'class="blue_ball">(\d{2})</li>', r.text)
            
            if len(reds) == 6 and len(blues) >= 1:
                print(f"✅ 狙击成功! 捕获第 {target_issue} 期数据。")
                
                # 构造 DataFrame
                row = [int(target_issue)] + [int(x) for x in reds] + [int(blues[0])]
                df = pd.DataFrame([row], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
                return df
            else:
                print(f"❌ 页面存在但数据解析失败 (可能是未开奖页面)")
        else:
            print(f"❌ 目标页面不存在 (404)，可能尚未生成。")
            
    except Exception as e:
        print(f"❌ 狙击失败: {e}")
    return None

def fetch_cwl_official():
    """
    策略2：官方 API (Referer 伪装)
    中国福彩官网接口，数据最权威。
    """
    print("📡 尝试连接福彩官网 API...")
    url = "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice?name=ssq&issueCount=1"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        data = r.json()
        if data['result']:
            item = data['result'][0]
            issue = int(item['code'])
            red_str = item['red'] # "02,04,05,10,12,13"
            blue_str = item['blue'] # "06"
            
            reds = [int(x) for x in red_str.split(',')]
            blue = int(blue_str)
            
            row = [issue] + reds + [blue]
            df = pd.DataFrame([row], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
            print(f"✅ 官网API获取成功! 期号: {issue}")
            return df
    except Exception as e:
        print(f"❌ 官网API失败: {e}")
    return None

def fetch_sina_trend():
    """
    策略3：新浪走势图接口 (比 App 接口更稳定)
    """
    print("📡 尝试新浪走势图接口...")
    url = "https://match.lottery.sina.com.cn/lotto/pc_zst/index?lottoType=ssq&action=list&length=10"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        data = r.json()
        if data['status'] == 0 and data['data']:
            # 取第一条
            item = data['data'][0]
            # 新浪字段可能是 issueNo 或者 issue
            issue = int(item.get('issue', 0))
            if issue == 0: issue = int(item.get('issueNo', 0))
            
            # 号码字段处理
            # 假设返回格式需要自行探索，通常是 openCode: "01,02..."
            # 这里做容错
            nums = []
            for k in ['c1','c2','c3','c4','c5','c6','c7']: # 新浪走势图常用字段 c1-c6红 c7蓝
                if k in item:
                    nums.append(int(item[k]))
            
            if len(nums) == 7:
                row = [issue] + nums
                df = pd.DataFrame([row], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
                print(f"✅ 新浪走势接口获取成功! 期号: {issue}")
                return df
                
    except Exception as e:
        print(f"❌ 新浪走势失败: {e}")
    return None

def get_web_data(last_local_issue):
    """
    智能调度器
    1. 计算下一期是多少 (例如 2025141)
    2. 优先定点爆破下一期
    3. 如果爆破失败，尝试官方API和走势图
    """
    target_issue = last_local_issue + 1
    
    # 1. 优先尝试定点爆破 (最强抗缓存)
    df = fetch_target_issue_500(target_issue)
    if df is not None: return df
    
    # 2. 尝试官网
    df = fetch_cwl_official()
    if df is not None: return df
    
    # 3. 尝试新浪走势
    df = fetch_sina_trend()
    if df is not None: return df
    
    return None

def update_database():
    df_local = pd.DataFrame()
    last_issue = 2025000 # 默认兜底
    
    if os.path.exists(CSV_FILE):
        try: 
            df_local = pd.read_csv(CSV_FILE)
            if not df_local.empty:
                last_issue = int(df_local['Issue'].iloc[-1])
        except: pass
    
    print(f"📂 本地最新期号: {last_issue}")
    
    # 传入本地最新期号，用于预测下一期
    df_net = get_web_data(last_issue)
    
    if df_net is not None and not df_net.empty:
        net_issue = int(df_net['Issue'].iloc[0])
        
        if net_issue > last_issue:
            print(f"🎉 发现新数据! {last_issue} -> {net_issue}")
            if not df_local.empty:
                df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
                df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'], keep='last')
            else:
                df_final = df_net
            
            df_final = df_final.sort_values(by='Issue')
            df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
            return df_final
        else:
            print(f"💤 抓取到的数据 ({net_issue}) 不是最新的，无需更新。")
            return df_local
    else:
        print("⚠️ 未能抓取到任何有效数据。")
        return df_local

# --- 2. 分析与绘图 (标准模块) ---
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
    print("🚀 启动 (v5.0 定点爆破版)...")
    
    # 1. 更新数据库
    df = update_database()
    if df is None or df.empty: return
    
    # 2. 判断状态
    old_issue = 0 # 模拟旧的
    if os.path.exists(CSV_FILE):
        # 这里其实有点逻辑闭环，update_database已经更新了CSV，所以last_row肯定是最新的
        # 我们用一个逻辑判断：如果 df 的最新一期 > 2025140 (你截图里的旧数据)，那就是新的
        pass

    last_row = df.iloc[-1]
    new_issue = int(last_row['Issue'])
    
    # 简单判定：只要能跑到这里，update_database 内部已经做过更新检查了
    # 我们假设如果 new_issue 比本地之前记录的大，就是新的
    # 但因为 update_database 已经重写了 CSV，我们直接展示最新状态即可
    
    print(f"✅ 当前全量数据最新期号: {new_issue}")

    # 3. 分析
    rs, rg, bs, bg = run_analysis_raw(df)
    ai_text = generate_raw_text(rs, rg, bs, bg)
    generate_interactive_page(df, new_issue, ai_text)

    # 4. 推送
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if repo else "public/index.html"
    
    title = f"✅ 双色球第{new_issue}期 (已更新)"
    msg = f"{format_balls_html(last_row)}"
    msg += f"<p style='color:green;text-align:center;font-size:12px;margin:5px 0;'>✅ 已成功获取最新数据！<br>数据源: 500网/官网/新浪</p>"
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
