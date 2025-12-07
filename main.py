import pandas as pd
import numpy as np
import requests
import os
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =================配置区=================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN")
CSV_FILE = "ssq.csv"
# ========================================

def get_web_data():
    """ 抓取最近 50 期数据 (作为增量补丁) """
    # 注意：这里我们只抓最近 50 期，减轻网络压力
    url = "http://datachart.500.com/ssq/history/newinc/history.php?limit=50&sort=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for i in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'
            tables = pd.read_html(response.text)
            if not tables: raise ValueError("空表格")
            
            df = tables[0].iloc[:, [0, 1, 2, 3, 4, 5, 6, 7]]
            df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
            # 清洗
            df = df[pd.to_numeric(df['Issue'], errors='coerce').notnull()]
            df = df.sort_values(by='Issue', ascending=True)
            return df
        except Exception as e:
            print(f"网络抓取重试 {i+1}/3: {e}")
            time.sleep(2)
    return None

def update_database():
    """ 核心：读取本地 + 合并网络新数据 + 保存 """
    # 1. 读取本地历史 (如果存在)
    if os.path.exists(CSV_FILE):
        print("📂 读取本地历史数据库...")
        try:
            df_local = pd.read_csv(CSV_FILE)
        except:
            df_local = pd.DataFrame()
    else:
        print("⚠️ 本地无数据库，初始化新库...")
        df_local = pd.DataFrame()

    # 2. 抓取网络新数据
    print("🌐 正在检查最新开奖...")
    df_new = get_web_data()
    
    if df_new is None:
        print("❌ 网络抓取失败，将使用现有本地数据分析")
        return df_local, False # False 表示没有更新

    # 3. 数据合并与去重
    if not df_local.empty:
        # 确保 Issue 列都是整数，方便比对
        df_local['Issue'] = df_local['Issue'].astype(int)
        df_new['Issue'] = df_new['Issue'].astype(int)
        
        # 找出 df_local 里没有的期号
        existing_issues = set(df_local['Issue'])
        # 筛选出新数据
        updates = df_new[~df_new['Issue'].isin(existing_issues)]
        
        if updates.empty:
            print("✅ 本地已是最新，无需更新。")
            return df_local, False
        else:
            print(f"♻️ 发现新开奖：{len(updates)} 期，正在追加...")
            # 合并
            df_final = pd.concat([df_local, updates]).sort_values(by='Issue', ascending=True)
    else:
        # 如果本地是空的，直接用抓到的数据（或者你可以第一次手动上传一个全量csv）
        print("✨ 初始化数据库完成。")
        df_final = df_new

    # 4. 保存回 CSV
    df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
    print("💾 数据库已更新并保存。")
    return df_final, True

# --- 以下是K线计算与画图逻辑 (保持不变，略微适配) ---
def calculate_kline(df, target_ball, ball_type, period):
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
        curr = (curr + prob_miss * 5) if (ball_type == 'blue' and hit) else \
               (curr + prob_miss) if hit else (curr - prob_hit)
        scores.append(curr)
        
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

def generate_interactive_chart(df, last_issue):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.15,
                        subplot_titles=("【宏观】10期趋势 (MA5)", "【微观】3期买点 (MA10)"))
    buttons = []
    trace_idx = 0
    
    # 确保列名为数字类型
    for c in ['R1','R2','R3','R4','R5','R6','Blue']: df[c] = df[c].astype(int)

    for ball in range(1, 34):
        df_10 = calculate_kline(df, ball, 'red', 10)
        df_3 = calculate_kline(df, ball, 'red', 3)
        df_3_recent = df_3.tail(100)
        
        # 添加 Trace (代码省略部分重复细节，逻辑与之前一致)
        # 上图
        fig.add_trace(go.Candlestick(x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'],
                                     name=f'红{ball:02d}-10期', visible=(ball==1), increasing_line_color='#FF4136', decreasing_line_color='#0074D9'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_10.index, y=df_10['MA'], mode='lines', name='MA5', visible=(ball==1), line=dict(color='yellow', width=1)), row=1, col=1)
        # 下图
        fig.add_trace(go.Candlestick(x=list(range(len(df_3_recent))), open=df_3_recent['Open'], high=df_3_recent['High'], low=df_3_recent['Low'], close=df_3_recent['Close'],
                                     name=f'红{ball:02d}-3期', visible=(ball==1), increasing_line_color='#F012BE', decreasing_line_color='#2ECC40'), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(df_3_recent))), y=df_3_recent['MA'], mode='lines', name='MA10', visible=(ball==1), line=dict(color='yellow', width=1)), row=2, col=1)
        
        visibility = [False] * (49 * 4)
        visibility[trace_idx:trace_idx+4] = [True, True, True, True]
        buttons.append(dict(label=f"🔴 红球 {ball:02d}", method="update", args=[{"visible": visibility}, {"title": f"红球 {ball:02d} (第{last_issue}期)"}]))
        trace_idx += 4

    for ball in range(1, 17):
        df_10 = calculate_kline(df, ball, 'blue', 10)
        df_3 = calculate_kline(df, ball, 'blue', 3)
        df_3_recent = df_3.tail(100)
        # 蓝球 Trace...
        fig.add_trace(go.Candlestick(x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'],
                                     name=f'蓝{ball:02d}-10期', visible=False, increasing_line_color='#FF4136', decreasing_line_color='#0074D9'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_10.index, y=df_10['MA'], mode='lines', name='MA5', visible=False, line=dict(color='cyan', width=1)), row=1, col=1)
        fig.add_trace(go.Candlestick(x=list(range(len(df_3_recent))), open=df_3_recent['Open'], high=df_3_recent['High'], low=df_3_recent['Low'], close=df_3_recent['Close'],
                                     name=f'蓝{ball:02d}-3期', visible=False, increasing_line_color='#F012BE', decreasing_line_color='#2ECC40'), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(df_3_recent))), y=df_3_recent['MA'], mode='lines', name='MA10', visible=False, line=dict(color='cyan', width=1)), row=2, col=1)
        
        visibility = [False] * (49 * 4)
        visibility[trace_idx:trace_idx+4] = [True, True, True, True]
        buttons.append(dict(label=f"🔵 蓝球 {ball:02d}", method="update", args=[{"visible": visibility}, {"title": f"蓝球 {ball:02d} (第{last_issue}期)"}]))
        trace_idx += 4

    fig.update_layout(
        updatemenus=[dict(active=0, buttons=buttons, direction="down", pad={"r": 10, "t": 10}, showactive=True, x=0.5, xanchor="center", y=1.15, yanchor="top")],
        template="plotly_dark", height=800, title=f"双色球第 {last_issue} 期 - 交互式 K 线控制台", xaxis_rangeslider_visible=False
    )
    if not os.path.exists("public"): os.makedirs("public")
    fig.write_html("public/index.html")

def generate_strategies(df):
    # 简化的策略生成
    red_res = []
    cols = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
    # 使用全量数据分析
    for ball in range(1, 34):
        is_hit = df[cols].isin([ball]).any(axis=1)
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
        is_hit = (df['Blue'] == ball)
        scores = []
        curr = 0
        for hit in is_hit: curr = (curr + 15/16*5) if hit else (curr - 1/16)
        scores.append(curr)
        s10 = pd.Series(scores)
        slope = np.polyfit(np.arange(5), s10.tail(5), 1)[0] * 10
        blue_res.append({'b': ball, 's': slope})
    blue_res.sort(key=lambda x: x['s'], reverse=True)
    return red_res, blue_res

def push_wechat(title, content):
    if not PUSH_TOKEN: return
    url = 'http://www.pushplus.plus/send'
    data = {"token": PUSH_TOKEN, "title": title, "content": content, "template": "html"}
    requests.post(url, json=data)

def main():
    # 1. 更新数据库
    df, is_updated = update_database()
    
    if df.empty:
        print("❌ 数据为空，无法分析")
        return

    last_issue = df['Issue'].iloc[-1]
    
    # 2. 生成图表
    generate_interactive_chart(df, last_issue)
    
    # 3. 生成策略
    red_
