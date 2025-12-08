import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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

# --- 1. 多源数据获取模块 (核心升级) ---

def fetch_500_com():
    """数据源1: 500彩票网"""
    print("Trying Source 1 (500.com)...")
    url = "http://datachart.500.com/ssq/history/newinc/history.php?limit=50&sort=0"
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        r.encoding = 'utf-8'
        df = pd.read_html(StringIO(r.text))[0]
        # 500网通常前8列是: 期号, R1...R6, Blue
        df = df.iloc[:, :8]
        df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
        return df
    except Exception as e:
        print(f"Source 1 failed: {e}")
        return None

def fetch_sina():
    """数据源2: 新浪彩票 (备用)"""
    print("Trying Source 2 (Sina)...")
    url = "http://lottery.sina.com.cn/history/ssq/index.shtml?args=50"
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        r.encoding = 'utf-8' # 新浪可能是utf-8或gbk
        # 新浪的表格比较复杂，需要精确定位
        dfs = pd.read_html(StringIO(r.text))
        # 通常是数据量最大的那个表
        target_df = None
        for df in dfs:
            if df.shape[0] > 10 and df.shape[1] > 7:
                target_df = df
                break
        
        if target_df is None: return None
        
        # 新浪列名通常包含：期号, 红1, 红2... 蓝
        # 简单处理：只取前几列，并重命名
        # 注意：新浪有时有"年份"列，需要判断
        # 假设我们取包含"期号"的列作为起始
        
        # 简化策略：只保留数值类型的列，并且数量符合预期的
        # 这里做一种通用清洗
        clean_rows = []
        for _, row in target_df.iterrows():
            # 转为字符串列表
            vals = [str(v).strip() for v in row.values]
            # 过滤掉非数字行
            nums = [v for v in vals if v.isdigit()]
            # 双色球数据行至少要有: 期号(1)+红(6)+蓝(1) = 8个数字
            if len(nums) >= 8:
                # 假设第一个长数字是期号 (2025141)
                issue = nums[0]
                if len(issue) == 7: # 2025xxx
                    # 取紧接在期号后面的7个数字 (6红1蓝)
                    # 新浪格式通常是: 期号, 红1..红6, 蓝
                    idx = vals.index(issue)
                    # 尝试提取后续数据，需跳过空值
                    data_part = []
                    for k in range(idx+1, len(vals)):
                        if vals[k].isdigit():
                            data_part.append(int(vals[k]))
                        if len(data_part) == 7: break
                    
                    if len(data_part) == 7:
                        clean_rows.append([int(issue)] + data_part)
        
        if not clean_rows: return None
        df_new = pd.DataFrame(clean_rows, columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
        return df_new
    except Exception as e:
        print(f"Source 2 failed: {e}")
        return None

def fetch_163():
    """数据源3: 网易彩票 (兜底)"""
    print("Trying Source 3 (163.com)...")
    url = "https://caipiao.163.com/award/ssq/"
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        r.encoding = 'utf-8'
        dfs = pd.read_html(StringIO(r.text))
        for df in dfs:
            # 网易的表头通常有 "期号"
            s_df = df.astype(str)
            if s_df.apply(lambda x: x.str.contains('期号')).any().any():
                # 清洗网易数据
                clean_data = []
                for _, row in df.iterrows():
                    vals = [str(v).strip() for v in row.values if str(v).strip().isdigit()]
                    # 网易可能把红球放在一个单元格，或者分开
                    # 这里做简单容错，寻找符合 2025xxx 的期号
                    if len(vals) >= 8: # 至少8个数字
                        if len(vals[0]) == 7: # 期号
                            clean_data.append([int(x) for x in vals[:8]])
                
                if clean_data:
                    return pd.DataFrame(clean_data, columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
        return None
    except Exception as e:
        print(f"Source 3 failed: {e}")
        return None

def get_web_data():
    """多源聚合获取逻辑"""
    # 1. 尝试 500.com
    df = fetch_500_com()
    if df is not None and not df.empty:
        print("✅ Fetched from 500.com")
        return df.sort_values(by='Issue').astype(int)
    
    # 2. 尝试 Sina
    df = fetch_sina()
    if df is not None and not df.empty:
        print("✅ Fetched from Sina")
        return df.sort_values(by='Issue').astype(int)
        
    # 3. 尝试 163
    df = fetch_163()
    if df is not None and not df.empty:
        print("✅ Fetched from 163")
        return df.sort_values(by='Issue').astype(int)
        
    print("❌ All sources failed.")
    return None

def update_database():
    """更新逻辑：智能合并"""
    df_local = pd.DataFrame()
    # 读取本地
    if os.path.exists(CSV_FILE):
        try:
            df_local = pd.read_csv(CSV_FILE)
        except: pass
    
    # 获取网络数据
    df_net = get_web_data()
    
    if df_net is not None:
        if not df_local.empty:
            df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
            # 合并：用网络数据覆盖或追加本地数据
            df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'], keep='last')
        else:
            df_final = df_net
        
        df_final = df_final.sort_values(by='Issue')
        df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
        return df_final
    else:
        print("⚠️ 无法连接网络，使用本地数据。")
        return df_local

# --- 2. 算法工具 (保持不变) ---
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

# --- 3. K线计算 ---
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

# --- 4. 网页生成 ---
def generate_interactive_page(df, last_issue, ai_text):
    if not os.path.exists("public"): os.makedirs("public")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.1, subplot_titles=("趋势(10期)", "短线(3期)"), row_heights=[0.6, 0.4])
    df_chart = df.tail(400).reset_index(drop=True)
    
    for ball in range(1, 34): # 红
        d10 = calculate_kline_for_chart(df_chart, ball, 'red', 10)
        d3 = calculate_kline_for_chart(df_chart, ball, 'red', 3).tail(100)
        v = (ball == 1)
        fig.add_trace(go.Candlestick(x=d10.index, open=d10['Open'], high=d10['High'], low=d10['Low'], close=d10['Close'], visible=v, increasing_line_color='#F44336', decreasing_line_color='#2196F3'), 1, 1)
        fig.add_trace(go.Scatter(x=d10.index, y=d10['MA'], mode='lines', visible=v, line=dict(color='yellow', width=1)), 1, 1)
        fig.add_trace(go.Candlestick(x=list(range(len(d3))), open=d3['Open'], high=d3['High'], low=d3['Low'], close=d3['Close'], visible=v, increasing_line_color='#E91E63', decreasing_line_color='#4CAF50'), 2, 1)
        fig.add_trace(go.Scatter(x=list(range(len(d3))), y=d3['MA'], mode='lines', visible=v, line=dict(color='white', width=1, dash='dot')), 2, 1)
    
    for ball in range(1, 17): # 蓝
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

# --- 5. 辅助与推送 ---
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
    print("🚀 启动 (多源版)...")
    
    # 1. 记录本地旧期号
    old_issue = 0
    if os.path.exists(CSV_FILE):
        try: old_issue = int(pd.read_csv(CSV_FILE)['Issue'].iloc[-1])
        except: pass

    # 2. 尝试更新 (自动尝试3个源)
    df = update_database()
    if df is None or df.empty: return
    
    # 3. 获取最新状态
    last_row = df.iloc[-1]
    new_issue = int(last_row['Issue'])
    is_new = new_issue > old_issue
    
    print(f"本地: {old_issue} | 线上(抓取后): {new_issue} | 状态: {'🆕 已更新' if is_new else '🔁 未更新'}")

    # 4. 分析
    rs, rg, bs, bg = run_analysis_raw(df)
    ai_text = generate_raw_text(rs, rg, bs, bg)
    generate_interactive_page(df, new_issue, ai_text)

    # 5. 推送
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if repo else "public/index.html"
    
    title = f"{'✅' if is_new else '⚠️'} 双色球第{new_issue}期"
    msg = f"{format_balls_html(last_row)}"
    
    if not is_new:
        msg += "<p style='color:red;text-align:center;font-size:12px'>⚠️ 即使切换了数据源，仍未抓取到新数据。<br>可能全网数据尚未同步，建议10分钟后再试。</p>"
    else:
        msg += "<p style='color:green;text-align:center;font-size:12px'>✅ 成功抓取到最新一期数据！</p>"
    
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
