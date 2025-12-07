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
    """ 抓取网络数据 (备用) """
    url = "http://datachart.500.com/ssq/history/newinc/history.php?limit=50&sort=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        tables = pd.read_html(response.text)
        if not tables: return None
        df = tables[0].iloc[:, [0, 1, 2, 3, 4, 5, 6, 7]]
        df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
        return df
    except:
        return None

def update_database():
    """ 读取本地并尝试更新 """
    df_local = pd.DataFrame()
    
    # 1. 尝试多种编码读取本地文件
    if os.path.exists(CSV_FILE):
        print("📂 发现本地文件，尝试读取...")
        for encoding in ['utf-8', 'gbk', 'gb18030', 'utf-16']:
            try:
                df_local = pd.read_csv(CSV_FILE, encoding=encoding)
                print(f"✅ 成功用 {encoding} 编码读取！行数: {len(df_local)}")
                break
            except Exception as e:
                pass
    
    # 2. 尝试联网
    df_net = get_web_data()
    
    # 3. 合并逻辑
    if df_net is not None:
        try:
            # 统一列名，防止本地文件列名不对
            df_net.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
            if not df_local.empty:
                # 确保列名一致
                df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
                # 强转数字
                for c in df_local.columns: 
                    df_local[c] = pd.to_numeric(df_local[c], errors='coerce')
                for c in df_net.columns: 
                    df_net[c] = pd.to_numeric(df_net[c], errors='coerce')
                
                # 合并去重
                df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'])
            else:
                df_final = df_net
        except Exception as e:
            print(f"合并出错: {e}, 使用本地数据")
            df_final = df_local
    else:
        print("⚠️ 联网失败，使用本地数据")
        df_final = df_local

    # 4. 最终清洗与保存
    if not df_final.empty:
        df_final = df_final.sort_values(by='Issue', ascending=True)
        # 保存为 utf-8 标准格式，防止下次读取出错
        df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
        return df_final
    
    return pd.DataFrame() # 返回空表

def calculate_kline(df, target_ball, ball_type, period):
    # (保持原有的K线计算逻辑不变)
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
    # 强制创建目录，防止报错
    if not os.path.exists("public"): os.makedirs("public")
    
    if df.empty:
        with open("public/index.html", "w") as f:
            f.write("<h1>Data Error: No data available</h1>")
        return

    # 这里是之前的绘图逻辑，精简版
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.15,
                        subplot_titles=("【宏观】10期趋势 (MA5)", "【微观】3期买点 (MA10)"))
    buttons = []
    trace_idx = 0
    
    # 红球
    for ball in range(1, 34):
        df_10 = calculate_kline(df, ball, 'red', 10)
        df_3 = calculate_kline(df, ball, 'red', 3)
        df_3_recent = df_3.tail(100)
        
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

    # 蓝球
    for ball in range(1, 17):
        df_10 = calculate_kline(df, ball, 'blue', 10)
        df_3 = calculate_kline(df, ball, 'blue', 3)
        df_3_recent = df_3.tail(100)
        
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
    
    fig.write_html("public/index.html")

def generate_strategies(df):
    # 简单的策略生成
    if df.empty: return [], []
    
    red_res = []
    cols = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
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

def push_wechat(title, content):
    if not PUSH_TOKEN: return
    url = 'http://www.pushplus.plus/send'
    data = {"token": PUSH_TOKEN, "title": title, "content": content, "template": "html"}
    requests.post(url, json=data)

def main():
    print("🚀 启动分析引擎...")
    df = update_database()
    
    if df.empty:
        print("❌ 严重错误：数据库为空且无法联网。")
        # 即使没数据，也要生成一个空的index.html，防止Action报错
        if not os.path.exists("public"): os.makedirs("public")
        with open("public/index.html", "w") as f: f.write("<h1>No Data</h1>")
        return

    last_issue = df['Issue'].iloc[-1]
    print(f"✅ 数据准备就绪，最新期号: {last_issue}")
    
    generate_interactive_chart(df, last_issue)
    red_res, blue_res = generate_strategies(df)
    
    repo_owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    repo_name = "lottery-auto"
    chart_url = f"https://{repo_owner}.github.io/{repo_name}/" if repo_owner else "#"

    msg = f"<h3>📅 期号：{last_issue}</h3>"
    msg += f"<h1>👉 <a href='{chart_url}'>点击打开 K 线控制台</a></h1><hr>"
    msg += f"<b>红球推荐：</b> {red_res[0]['b']:02d}, {red_res[1]['b']:02d}, {red_res[2]['b']:02d}<br>"
    msg += f"<b>蓝球推荐：</b> {blue_res[0]['b']:02d}, {blue_res[1]['b']:02d}<br>"
    
    push_wechat(f"双色球分析-{last_issue}", msg)
    print("🎉 任务全部完成！")

if __name__ == "__main__":
    main()
