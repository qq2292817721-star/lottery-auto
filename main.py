import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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

# --- 1. 数据模块 (增量更新) ---
def get_web_data():
    url = "http://datachart.500.com/ssq/history/newinc/history.php?limit=50&sort=0"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        response.encoding = 'utf-8'
        df = pd.read_html(response.text)[0].iloc[:, :8]
        df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
        df = df[pd.to_numeric(df['Issue'], errors='coerce').notnull()]
        return df.sort_values(by='Issue').astype(int)
    except: return None

def update_database():
    df_local = pd.DataFrame()
    if os.path.exists(CSV_FILE):
        for enc in ['utf-8', 'gbk', 'gb18030']:
            try:
                temp = pd.read_csv(CSV_FILE, encoding=enc)
                if not temp.empty: 
                    df_local = temp
                    break
            except: pass
            
    df_net = get_web_data()
    if df_net is not None:
        if not df_local.empty:
            df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
            df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'])
        else: df_final = df_net
        df_final = df_final.sort_values(by='Issue')
        df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
        return df_final
    return df_local

# --- 2. 算法工具 ---
def calc_slope(series, window=5):
    y = series.tail(window)
    if len(y) < 2: return 0
    return np.polyfit(np.arange(len(y)), y, 1)[0] * 10

def get_energy(df, targets, type='red'):
    if type == 'red':
        prob_miss = 27/33; cols = ['R1','R2','R3','R4','R5','R6']
        is_hit = df[cols].isin(targets).any(axis=1)
    else:
        prob_miss = 15/16; is_hit = df['Blue'].isin(targets)
    scores = []; curr = 0
    for hit in is_hit:
        curr = (curr + prob_miss * (5 if type=='blue' else 1)) if hit else (curr - (1 - prob_miss))
        scores.append(curr)
    return pd.Series(scores)

# --- 3. 专门用于画图的K线计算 (带High/Low) ---
def calculate_kline_for_chart(df, target_ball, ball_type, period):
    # 复用 get_energy 计算基础分数
    scores = get_energy(df, [target_ball], ball_type).tolist()
    
    ohlc = []
    for i in range(0, len(scores), period):
        chunk = scores[i : i+period]
        if not chunk: continue
        prev = scores[i-1] if i > 0 else 0
        chunk_max = max(chunk); chunk_min = min(chunk)
        real_high = max(prev, chunk_max); real_low = min(prev, chunk_min)
        ohlc.append([prev, real_high, real_low, chunk[-1]])
        
    k_df = pd.DataFrame(ohlc, columns=['Open', 'High', 'Low', 'Close'])
    ma_window = 5 if period == 10 else 10
    k_df['MA'] = k_df['Close'].rolling(ma_window).mean()
    k_df['Index'] = range(len(k_df))
    return k_df

# --- 4. 生成交互式网页图表 (恢复画图功能) ---
def generate_interactive_chart(df, last_issue):
    if not os.path.exists("public"): os.makedirs("public")
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.15,
                        subplot_titles=("【宏观】10期趋势 (MA5)", "【微观】3期买点 (MA10)"))
    buttons = []; trace_idx = 0
    
    # 红球循环
    for ball in range(1, 34):
        df_10 = calculate_kline_for_chart(df, ball, 'red', 10)
        df_3 = calculate_kline_for_chart(df, ball, 'red', 3)
        df_3_recent = df_3.tail(100) # 微观只看最近
        
        # 上图
        fig.add_trace(go.Candlestick(x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'],
                                     name=f'红{ball:02d}-10期', visible=(ball==1), increasing_line_color='#FF4136', decreasing_line_color='#0074D9'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_10.index, y=df_10['MA'], mode='lines', name='MA5', visible=(ball==1), line=dict(color='yellow', width=1)), row=1, col=1)
        # 下图
        fig.add_trace(go.Candlestick(x=list(range(len(df_3_recent))), open=df_3_recent['Open'], high=df_3_recent['High'], low=df_3_recent['Low'], close=df_3_recent['Close'],
                                     name=f'红{ball:02d}-3期', visible=(ball==1), increasing_line_color='#F012BE', decreasing_line_color='#2ECC40'), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(df_3_recent))), y=df_3_recent['MA'], mode='lines', name='MA10', visible=(ball==1), line=dict(color='yellow', width=1)), row=2, col=1)
        
        vis = [False] * (49 * 4); vis[trace_idx:trace_idx+4] = [True, True, True, True]
        buttons.append(dict(label=f"🔴 红{ball:02d}", method="update", args=[{"visible": vis}, {"title": f"红球 {ball:02d} (第{last_issue}期)"}]))
        trace_idx += 4

    # 蓝球循环
    for ball in range(1, 17):
        df_10 = calculate_kline_for_chart(df, ball, 'blue', 10)
        df_3 = calculate_kline_for_chart(df, ball, 'blue', 3)
        df_3_recent = df_3.tail(100)
        
        fig.add_trace(go.Candlestick(x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'],
                                     name=f'蓝{ball:02d}-10期', visible=False, increasing_line_color='#FF4136', decreasing_line_color='#0074D9'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_10.index, y=df_10['MA'], mode='lines', name='MA5', visible=False, line=dict(color='cyan', width=1)), row=1, col=1)
        fig.add_trace(go.Candlestick(x=list(range(len(df_3_recent))), open=df_3_recent['Open'], high=df_3_recent['High'], low=df_3_recent['Low'], close=df_3_recent['Close'],
                                     name=f'蓝{ball:02d}-3期', visible=False, increasing_line_color='#F012BE', decreasing_line_color='#2ECC40'), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(df_3_recent))), y=df_3_recent['MA'], mode='lines', name='MA10', visible=False, line=dict(color='cyan', width=1)), row=2, col=1)
        
        vis = [False] * (49 * 4); vis[trace_idx:trace_idx+4] = [True, True, True, True]
        buttons.append(dict(label=f"🔵 蓝{ball:02d}", method="update", args=[{"visible": vis}, {"title": f"蓝球 {ball:02d} (第{last_issue}期)"}]))
        trace_idx += 4

    fig.update_layout(
        updatemenus=[dict(active=0, buttons=buttons, direction="down", pad={"r": 10, "t": 10}, showactive=True, x=0.5, xanchor="center", y=1.15, yanchor="top")],
        template="plotly_dark", height=800, title=f"双色球第 {last_issue} 期 - K 线控制台", xaxis_rangeslider_visible=False
    )
    fig.write_html("public/index.html")

# --- 5. 生成报表数据 (保持不变) ---
def run_analysis_raw(df):
    # 红球单兵
    red_single = []
    for b in range(1, 34):
        s = get_energy(df, [b], 'red')
        s10 = calc_slope(s, 5); s3 = calc_slope(s, 3)
        ma5 = s.rolling(5).mean().iloc[-1]; ma10 = s.rolling(10).mean().iloc[-1]; curr = s.iloc[-1]
        tag = "☠️"
        if curr > ma5 and curr > ma10: tag = "🔥共振"
        elif curr > ma5 and curr <= ma10: tag = "💰回踩"
        elif curr <= ma5 and curr > ma10: tag = "✨妖股"
        red_single.append({'号码': f"{b:02d}", '10期斜率': round(s10, 1), '3期斜率': round(s3, 1), '状态': tag})
    df_red_single = pd.DataFrame(red_single).sort_values(by='10期斜率', ascending=False)

    # 红球集团
    red_group = []
    for name, balls in RED_GROUPS.items():
        s = get_energy(df, balls, 'red')
        slope = calc_slope(s, 10)
        tag = "🔥" if slope > 2 else ("🚀" if slope > 0 else "☠️")
        red_group.append({'代号': name, '成员': str(balls), '斜率': round(slope, 1), '态': tag})
    df_red_group = pd.DataFrame(red_group).sort_values(by='斜率', ascending=False)

    # 蓝球单兵
    blue_single = []
    for b in range(1, 17):
        s = get_energy(df, [b], 'blue')
        s10 = calc_slope(s, 5); s3 = calc_slope(s, 3)
        curr = s.iloc[-1]; ma5 = s.rolling(5).mean().iloc[-1]; ma10 = s.rolling(10).mean().iloc[-1]
        tag = "☠️"
        if curr > ma5 and curr > ma10: tag = "🔥"
        elif curr > ma5 and curr <= ma10: tag = "💰"
        elif curr <= ma5 and curr > ma10: tag = "🚀"
        blue_single.append({'号码': f"{b:02d}", '10期': round(s10, 1), '3期': round(s3, 1), '态': tag})
    df_blue_single = pd.DataFrame(blue_single).sort_values(by='10期', ascending=False)

    # 蓝球分组
    blue_group = []
    for name, balls in BLUE_GROUPS.items():
        s = get_energy(df, balls, 'blue')
        slope = calc_slope(s, 5)
        tag = "🔥" if slope > 1 else ("🚀" if slope > 0 else "☠️")
        blue_group.append({'组合': name, '斜率': round(slope, 1), '态': tag})
    df_blue_group = pd.DataFrame(blue_group).sort_values(by='斜率', ascending=False)

    return df_red_single, df_red_group, df_blue_single, df_blue_group

def df_to_html(df, title, limit=None):
    if limit: df = df.head(limit)
    html = f"<div style='margin-bottom:15px'><b>{title}</b>"
    html += "<table border='1' style='border-collapse:collapse;width:100%;font-size:12px;text-align:center;'>"
    html += "<tr style='background:#eee;'>" + "".join([f"<th>{c}</th>" for c in df.columns]) + "</tr>"
    for _, row in df.iterrows():
        bg = "#fff"
        s = str(row.values)
        if "🔥" in s: bg = "#ffebee"
        elif "💰" in s: bg = "#fffde7"
        elif "☠️" in s: bg = "#f5f5f5"
        html += f"<tr style='background:{bg};'>" + "".join([f"<td>{v}</td>" for v in row.values]) + "</tr>"
    html += "</table></div>"
    return html

def push_wechat(title, content):
    if not PUSH_TOKEN: return
    requests.post('http://www.pushplus.plus/send', json={
        "token": PUSH_TOKEN, "title": title, "content": content, "template": "html"
    })

def main():
    print("🚀 启动...")
    df = update_database()
    if df.empty: return
    last_issue = df['Issue'].iloc[-1]
    
    # 1. 生成并保存交互式网页 (这就是你点击链接看到的内容)
    generate_interactive_chart(df, last_issue)
    
    # 2. 计算报表数据
    rs, rg, bs, bg = run_analysis_raw(df)
    
    # 3. 构造微信推送内容
    repo = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    url = f"https://{repo}.github.io/lottery-auto/" if repo else "#"
    
    msg = f"<h2>📅 第 {last_issue} 期 · 原始数据情报</h2>"
    msg += f"👉 <a href='{url}'>查看交互式K线图</a><hr>"
    msg += "<b>【请复制以下表格发给AI进行分析】</b><br><br>"
    
    msg += df_to_html(rs, "📊 1. 红球单兵 (Top 15)", limit=15)
    msg += df_to_html(rg, "🛡️ 2. 红球集团 (11组)")
    msg += df_to_html(bs, "🔵 3. 蓝球单兵 (16码)")
    msg += df_to_html(bg, "⚖️ 4. 蓝球分组 (8组)")
    
    print("推送中...")
    push_wechat(f"双色球数据-{last_issue}", msg)

if __name__ == "__main__":
    main()
