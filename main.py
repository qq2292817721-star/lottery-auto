import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =================配置区=================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
# ========================================

def get_latest_data():
    """ 抓取并强力清洗数据 """
    url = "http://datachart.500.com/ssq/history/newinc/history.php?start=00001&end=99999"
    try:
        header = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=header, timeout=10)
        response.encoding = 'utf-8'
        tables = pd.read_html(response.text)
        df = tables[0]
        
        df = df.iloc[:, [0, 1, 2, 3, 4, 5, 6, 7]]
        df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
        
        df = df[pd.to_numeric(df['Issue'], errors='coerce').notnull()]
        df = df.sort_values(by='Issue', ascending=True)
        for c in df.columns: df[c] = df[c].astype(int)
            
        # 为了保证K线连贯，取最近 300 期计算，最后展示时截取
        return df.tail(300).reset_index(drop=True)
    except Exception as e:
        print(f"数据抓取错误: {e}")
        return None

# --- K线计算核心 (与本地脚本一致) ---
def calculate_kline(df, target_ball, ball_type, period):
    # ball_type: 'red' 或 'blue'
    if ball_type == 'red':
        cols = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
        prob_hit = 6 / 33
        prob_miss = 27 / 33
        is_hit = df[cols].isin([target_ball]).any(axis=1)
    else:
        prob_hit = 1 / 16
        prob_miss = 15 / 16
        is_hit = (df['Blue'] == target_ball)

    scores = []
    curr = 0
    for hit in is_hit:
        if hit: 
            curr += prob_miss * (5 if ball_type == 'blue' else 1)
        else: 
            curr -= prob_hit
        scores.append(curr)
        
    ohlc = []
    # 修复 High/Low 逻辑
    for i in range(0, len(scores), period):
        chunk = scores[i : i+period]
        if not chunk: continue
        prev = scores[i-1] if i > 0 else 0
        chunk_max = max(chunk)
        chunk_min = min(chunk)
        real_high = max(prev, chunk_max)
        real_low = min(prev, chunk_min)
        ohlc.append([prev, real_high, real_low, chunk[-1]])
        
    k_df = pd.DataFrame(ohlc, columns=['Open', 'High', 'Low', 'Close'])
    
    # 计算均线
    ma_window = 5 if period == 10 else 10
    k_df['MA'] = k_df['Close'].rolling(ma_window).mean()
    
    # 生成期号显示 (简化版)
    k_df['Index'] = range(len(k_df))
    
    return k_df

# --- 策略生成区 ---
def generate_strategies(df):
    # 简化的策略生成，主要为了发微信
    # 这里复用之前的逻辑，计算斜率
    red_res = []
    cols = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
    
    # 只取最近用于计算斜率
    df_calc = df.tail(50).reset_index(drop=True)
    
    for ball in range(1, 34):
        is_hit = df_calc[cols].isin([ball]).any(axis=1)
        scores = []
        curr = 0
        for hit in is_hit: curr = (curr + 27/33) if hit else (curr - 6/33)
        scores.append(curr)
        s10 = pd.Series(scores)
        slope = np.polyfit(np.arange(5), s10.tail(5), 1)[0] * 10
        red_res.append({'b': ball, 's': slope})
    red_res.sort(key=lambda x: x['s'], reverse=True)
    
    blue_res = []
    for ball in range(1, 17):
        is_hit = (df_calc['Blue'] == ball)
        scores = []
        curr = 0
        for hit in is_hit: curr = (curr + 15/16*5) if hit else (curr - 1/16)
        scores.append(curr)
        s10 = pd.Series(scores)
        slope = np.polyfit(np.arange(5), s10.tail(5), 1)[0] * 10
        blue_res.append({'b': ball, 's': slope})
    blue_res.sort(key=lambda x: x['s'], reverse=True)
    
    return red_res, blue_res

# --- 核心：生成交互式网页图表 ---
def generate_interactive_chart(df, last_issue):
    # 创建子图：上图10期，下图3期
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=False,
        vertical_spacing=0.15,
        subplot_titles=("【宏观】10期趋势 (MA5)", "【微观】3期买点 (MA10)")
    )

    # 预先生成所有球的数据，创建 Traces
    # 顺序：红1..33, 蓝1..16
    # 每个球有4个Trace: 10期K线, 10期MA, 3期K线, 3期MA
    
    buttons = []
    visible_traces = [True] * 4 + [False] * (49 * 4 - 4) # 默认只显示第一个球(红01)
    
    trace_idx = 0
    
    # --- 红球循环 ---
    for ball in range(1, 34):
        # 计算数据
        df_10 = calculate_kline(df, ball, 'red', 10)
        df_3 = calculate_kline(df, ball, 'red', 3)
        df_3_recent = df_3.tail(100) # 微观图只看最近100根
        
        # 1. 上图 K线
        fig.add_trace(go.Candlestick(
            x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'],
            name=f'红{ball:02d}-10期', visible=(ball==1), increasing_line_color='#FF4136', decreasing_line_color='#0074D9'
        ), row=1, col=1)
        
        # 2. 上图 MA
        fig.add_trace(go.Scatter(
            x=df_10.index, y=df_10['MA'], mode='lines', name=f'MA5', 
            visible=(ball==1), line=dict(color='yellow', width=1)
        ), row=1, col=1)
        
        # 3. 下图 K线
        fig.add_trace(go.Candlestick(
            x=list(range(len(df_3_recent))), # 重置索引防止错位
            open=df_3_recent['Open'], high=df_3_recent['High'], low=df_3_recent['Low'], close=df_3_recent['Close'],
            name=f'红{ball:02d}-3期', visible=(ball==1), increasing_line_color='#F012BE', decreasing_line_color='#2ECC40'
        ), row=2, col=1)
        
        # 4. 下图 MA
        fig.add_trace(go.Scatter(
            x=list(range(len(df_3_recent))), y=df_3_recent['MA'], mode='lines', name=f'MA10', 
            visible=(ball==1), line=dict(color='yellow', width=1)
        ), row=2, col=1)
        
        # 添加按钮配置
        visibility = [False] * (49 * 4) # 总共有 49个球 * 4个Trace
        visibility[trace_idx:trace_idx+4] = [True, True, True, True]
        
        buttons.append(dict(
            label=f"🔴 红球 {ball:02d}",
            method="update",
            args=[{"visible": visibility},
                  {"title": f"红球 {ball:02d} 号趋势分析 (第{last_issue}期)"}]
        ))
        trace_idx += 4

    # --- 蓝球循环 ---
    for ball in range(1, 17):
        df_10 = calculate_kline(df, ball, 'blue', 10)
        df_3 = calculate_kline(df, ball, 'blue', 3)
        df_3_recent = df_3.tail(100)
        
        # 重复上面的添加Trace逻辑，稍微改颜色区分
        fig.add_trace(go.Candlestick(
            x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'],
            name=f'蓝{ball:02d}-10期', visible=False, increasing_line_color='#FF4136', decreasing_line_color='#0074D9'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=df_10.index, y=df_10['MA'], mode='lines', name=f'MA5', visible=False, line=dict(color='cyan', width=1)
        ), row=1, col=1)
        
        fig.add_trace(go.Candlestick(
            x=list(range(len(df_3_recent))),
            open=df_3_recent['Open'], high=df_3_recent['High'], low=df_3_recent['Low'], close=df_3_recent['Close'],
            name=f'蓝{ball:02d}-3期', visible=False, increasing_line_color='#F012BE', decreasing_line_color='#2ECC40'
        ), row=2, col=1)
        
        fig.add_trace(go.Scatter(
            x=list(range(len(df_3_recent))), y=df_3_recent['MA'], mode='lines', name=f'MA10', visible=False, line=dict(color='cyan', width=1)
        ), row=2, col=1)
        
        visibility = [False] * (49 * 4)
        visibility[trace_idx:trace_idx+4] = [True, True, True, True]
        
        buttons.append(dict(
            label=f"🔵 蓝球 {ball:02d}",
            method="update",
            args=[{"visible": visibility},
                  {"title": f"蓝球 {ball:02d} 号趋势分析 (第{last_issue}期)"}]
        ))
        trace_idx += 4

    # 更新布局，添加下拉菜单
    fig.update_layout(
        updatemenus=[dict(
            active=0,
            buttons=buttons,
            direction="down",
            pad={"r": 10, "t": 10},
            showactive=True,
            x=0.5, xanchor="center",
            y=1.15, yanchor="top"
        )],
        template="plotly_dark",
        height=800,
        title=f"双色球第 {last_issue} 期 - 交互式 K 线控制台",
        xaxis_rangeslider_visible=False
    )
    
    if not os.path.exists("public"): os.makedirs("public")
    fig.write_html("public/index.html")

# --- 推送逻辑 ---
def push_wechat(title, content):
    if not PUSH_TOKEN: return
    url = 'http://www.pushplus.plus/send'
    data = {"token": PUSH_TOKEN, "title": title, "content": content, "template": "html"}
    requests.post(url, json=data)

def main():
    df = get_latest_data()
    if df is None or df.empty: return
    
    last_issue = df['Issue'].iloc[-1]
    
    # 1. 生成带下拉菜单的网页
    generate_interactive_chart(df, last_issue)
    
    # 2. 生成简单文本分析
    red_res, blue_res = generate_strategies(df)
    
    # 获取 GitHub Pages 链接
    repo_owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    repo_name = "lottery-auto"
    chart_url = f"https://{repo_owner}.github.io/{repo_name}/" if repo_owner else "#"

    msg = f"<h3>📅 期号：{last_issue}</h3>"
    msg += f"<h1>👉 <a href='{chart_url}'>点击打开 K 线控制台</a></h1>"
    msg += "<p>（网页包含所有红球/蓝球的 K 线，点击顶部菜单切换号码）</p><hr>"
    
    msg += "<h4>🔥 极客推荐</h4>"
    msg += f"<b>红球热号：</b> {red_res[0]['b']:02d}, {red_res[1]['b']:02d}, {red_res[2]['b']:02d}<br>"
    msg += f"<b>蓝球热号：</b> {blue_res[0]['b']:02d}, {blue_res[1]['b']:02d}<br>"
    
    msg += "<br><i>请点击上方链接，在网页中查看详细的 K 线形态。</i>"
    
    print("分析完成，网页已生成，正在推送...")
    push_wechat(f"双色球K线图-{last_issue}", msg)

if __name__ == "__main__":
    main()
