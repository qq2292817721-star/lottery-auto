import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import StringIO

# ================= 配置区 =================
# 从环境变量获取 PushPlus Token (如果是本地运行，也可以直接填在这里)
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
CSV_FILE = "ssq.csv"

# 红球分组定义
RED_GROUPS = {
    'G01': [1, 19, 31], 'G02': [2, 21, 28], 'G03': [3, 22, 26],
    'G04': [4, 23, 24], 'G05': [5, 16, 30], 'G06': [6, 12, 33],
    'G07': [7, 15, 29], 'G08': [8, 18, 25], 'G09': [9, 10, 32],
    'G10': [11, 13, 27], 'G11': [14, 17, 20]
}
# 蓝球分组定义
BLUE_GROUPS = {
    'G1(01+16)': [1, 16], 'G2(02+15)': [2, 15], 'G3(03+14)': [3, 14],
    'G4(04+13)': [4, 13], 'G5(05+12)': [5, 12], 'G6(06+11)': [6, 11],
    'G7(07+10)': [7, 10], 'G8(08+09)': [8, 9]
}
# ========================================

# --- 1. 数据模块 ---
def get_web_data():
    """从500彩票网获取最新50期数据"""
    url = "http://datachart.500.com/ssq/history/newinc/history.php?limit=50&sort=0"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        # 使用 StringIO 避免 Pandas 的 FutureWarning
        html_io = StringIO(response.text)
        df = pd.read_html(html_io)[0].iloc[:, :8]
        df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
        # 清洗非数字行
        df = df[pd.to_numeric(df['Issue'], errors='coerce').notnull()]
        return df.sort_values(by='Issue').astype(int)
    except Exception as e:
        print(f"数据获取失败: {e}")
        return None

def update_database():
    """更新本地CSV数据库"""
    df_local = pd.DataFrame()
    # 读取本地文件 (尝试多种编码)
    if os.path.exists(CSV_FILE):
        for enc in ['utf-8', 'gbk', 'gb18030']:
            try:
                temp = pd.read_csv(CSV_FILE, encoding=enc)
                if not temp.empty: 
                    df_local = temp
                    break
            except: pass
    
    # 获取网络数据
    df_net = get_web_data()
    
    if df_net is not None:
        if not df_local.empty:
            # 确保列名一致
            df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
            # 合并并去重
            df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'])
        else:
            df_final = df_net
        
        df_final = df_final.sort_values(by='Issue')
        df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
        return df_final
    
    return df_local

# --- 2. 算法工具 ---
def calc_slope(series, window=5):
    """计算斜率（趋势）"""
    y = series.tail(window)
    if len(y) < 2: return 0
    try:
        slope = np.polyfit(np.arange(len(y)), y, 1)[0]
        return slope * 10 
    except:
        return 0

def get_energy(df, targets, type='red'):
    """计算能量遗漏值曲线"""
    if type == 'red':
        prob_miss = 27/33
        cols = ['R1','R2','R3','R4','R5','R6']
        is_hit = df[cols].isin(targets).any(axis=1)
    else:
        prob_miss = 15/16
        is_hit = df['Blue'].isin(targets)
    
    scores = []
    curr = 0
    for hit in is_hit:
        if hit:
            curr = curr - (1 - prob_miss)
        else:
            curr = curr + prob_miss * (5 if type=='blue' else 1)
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
        chunk_max = max(chunk); chunk_min = min(chunk)
        ohlc.append([prev, max(prev, chunk_max), min(prev, chunk_min), chunk[-1]])
    k_df = pd.DataFrame(ohlc, columns=['Open', 'High', 'Low', 'Close'])
    ma_window = 5 if period == 10 else 10
    k_df['MA'] = k_df['Close'].rolling(ma_window).mean()
    k_df['Index'] = range(len(k_df))
    return k_df

# --- 4. 生成原生交互网页 ---
def generate_interactive_page(df, last_issue, ai_text):
    if not os.path.exists("public"): 
        os.makedirs("public")
    
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.1,
        subplot_titles=("【宏观趋势】10期K线 (MA5)", "【微观买点】3期K线 (MA10)"),
        row_heights=[0.6, 0.4]
    )
    df_chart = df.tail(400).reset_index(drop=True)
    
    # 红球 Trace
    for ball in range(1, 34):
        df_10 = calculate_kline_for_chart(df_chart, ball, 'red', 10)
        df_3 = calculate_kline_for_chart(df_chart, ball, 'red', 3).tail(100)
        is_visible = (ball == 1)
        fig.add_trace(go.Candlestick(x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'], visible=is_visible, increasing_line_color='#FF4136', decreasing_line_color='#0074D9', name='趋势K'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_10.index, y=df_10['MA'], mode='lines', visible=is_visible, line=dict(color='yellow', width=1), name='MA5'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=list(range(len(df_3))), open=df_3['Open'], high=df_3['High'], low=df_3['Low'], close=df_3['Close'], visible=is_visible, increasing_line_color='#F012BE', decreasing_line_color='#2ECC40', name='短线K'), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(df_3))), y=df_3['MA'], mode='lines', visible=is_visible, line=dict(color='white', width=1, dash='dot'), name='MA10'), row=2, col=1)

    # 蓝球 Trace
    for ball in range(1, 17):
        df_10 = calculate_kline_for_chart(df_chart, ball, 'blue', 10)
        df_3 = calculate_kline_for_chart(df_chart, ball, 'blue', 3).tail(100)
        fig.add_trace(go.Candlestick(x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'], visible=False, increasing_line_color='#FF851B', decreasing_line_color='#7FDBFF', name='趋势K'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_10.index, y=df_10['MA'], mode='lines', visible=False, line=dict(color='cyan', width=1), name='MA5'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=list(range(len(df_3))), open=df_3['Open'], high=df_3['High'], low=df_3['Low'], close=df_3['Close'], visible=False, increasing_line_color='#B10DC9', decreasing_line_color='#01FF70', name='短线K'), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(df_3))), y=df_3['MA'], mode='lines', visible=False, line=dict(color='white', width=1, dash='dot'), name='MA10'), row=2, col=1)

    fig.update_layout(template="plotly_dark", height=600, margin=dict(t=40, l=10, r=10, b=10), showlegend=False, dragmode='pan', xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False)
    plot_div = fig.to_html(full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False}, div_id='plotly_div')

    custom_html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
        <title>双色球第 {last_issue} 期分析</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #121212; color: #eee; margin: 0; padding: 0; }}
            .header {{ padding: 10px 15px; background: #1e1e1e; border-bottom: 1px solid #333; }}
            .controls {{ display: flex; gap: 10px; margin-top: 10px; }}
            select {{ flex: 1; padding: 12px; font-size: 16px; border-radius: 8px; border: 1px solid #444; background: #2c2c2c; color: white; -webkit-appearance: none; outline: none; }}
            .btn-copy {{ background: #00C853; color: white; border: none; padding: 10px; width: 100%; font-size: 14px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-top: 5px; }}
            .btn-copy:active {{ background: #00E676; }}
            #ai-data {{ position: absolute; left: -9999px; opacity: 0; }}
            .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h3 style="margin:0;">📊 第 {last_issue} 期</h3><span style="font-size:12px; color:#888;">AI 辅助系统</span>
            </div>
            <button class="btn-copy" onclick="copyData()">📋 复制全量数据 (发送给AI分析)</button>
            <textarea id="ai-data">{ai_text}</textarea>
            <div class="controls">
                <select id="red-select" onchange="switchBall('red')"><option disabled>-- 红球选择 --</option>{''.join([f'<option value="{i}" {"selected" if i==1 else ""}>🔴 红球 {i:02d}</option>' for i in range(1, 34)])}</select>
                <select id="blue-select" onchange="switchBall('blue')"><option selected disabled>-- 蓝球选择 --</option>{''.join([f'<option value="{i}">🔵 蓝球 {i:02d}</option>' for i in range(1, 17)])}</select>
            </div>
        </div>
        {plot_div}
        <div class="footer">Generated by GitHub Actions | Data Source: 500.com</div>
        <script>
            function copyData() {{ var copyText = document.getElementById("ai-data"); copyText.select(); copyText.setSelectionRange(0, 99999); try {{ if(navigator.clipboard) {{ navigator.clipboard.writeText(copyText.value).then(function() {{ alert("✅ 数据已复制！\\n请粘贴到 AI 对话框中进行预测。"); }}); }} else {{ document.execCommand("copy"); alert("✅ 数据已复制！"); }} }} catch (err) {{ alert("复制失败，请手动长按文本框复制。"); }} }}
            function switchBall(type) {{ var plotlyDiv = document.getElementById('plotly_div'); var val, baseIndex; if (type === 'red') {{ document.getElementById('blue-select').selectedIndex = 0; val = parseInt(document.getElementById('red-select').value); baseIndex = (val - 1) * 4; }} else {{ document.getElementById('red-select').selectedIndex = 0; val = parseInt(document.getElementById('blue-select').value); baseIndex = 132 + (val - 1) * 4; }} var totalTraces = 196; var visibilityArray = new Array(totalTraces).fill(false); visibilityArray[baseIndex] = true; visibilityArray[baseIndex + 1] = true; visibilityArray[baseIndex + 2] = true; visibilityArray[baseIndex + 3] = true; Plotly.restyle(plotlyDiv, {{'visible': visibilityArray}}); }}
        </script>
    </body>
    </html>
    """
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(custom_html)

# --- 5. 辅助功能 ---
def generate_raw_text(rs, rg, bs, bg):
    t = "【双色球AI分析数据集】\nS10=10期斜率(宏观), S3=3期斜率(微观)\n"
    t += "=== 1. 红球单兵 ===\n" + rs.to_string(index=False) + "\n\n=== 2. 红球集团 ===\n" + rg.to_string(index=False) + "\n\n"
    t += "=== 3. 蓝球单兵 ===\n" + bs.to_string(index=False) + "\n\n=== 4. 蓝球分组 ===\n" + bg.to_string(index=False)
    return t

def format_winning_numbers_html(row):
    """生成的开奖号码的HTML展示"""
    red_style = "display:inline-block;width:28px;height:28px;line-height:28px;border-radius:50%;background:#f44336;color:white;text-align:center;font-weight:bold;margin-right:4px;"
    blue_style = "display:inline-block;width:28px;height:28px;line-height:28px;border-radius:50%;background:#2196f3;color:white;text-align:center;font-weight:bold;"
    html = "<div style='text-align:center; padding:15px 0; background:#fff; margin-bottom:10px; border-radius:8px; border:1px solid #eee; box-shadow:0 2px 4px rgba(0,0,0,0.05);'>"
    for i in range(1, 7): html += f"<span style='{red_style}'>{row[f'R{i}']:02d}</span>"
    html += f"<span style='{blue_style}'>{row['Blue']:02d}</span></div>"
    return html

def df_to_html_table(df, title):
    html = f"<div style='margin-bottom:15px; border-radius:8px; overflow:hidden; border:1px solid #ddd;'>"
    html += f"<div style='background:#f8f9fa; padding:8px; font-weight:bold; font-size:14px; border-bottom:1px solid #ddd;'>{title}</div>"
    html += "<table style='border-collapse:collapse;width:100%;font-size:12px;text-align:center;'>"
    html += "<tr style='background:#eee;color:#333;'>" + "".join([f"<th style='padding:6px;'>{c}</th>" for c in df.columns]) + "</tr>"
    for i, row in df.iterrows():
        s = str(row.values)
        bg = "#fff"
        if "🔥" in s: bg = "#ffebee" 
        elif "💰" in s: bg = "#fffde7"
        elif "☠️" in s: bg = "#f5f5f5"
        elif "🚀" in s: bg = "#e8f5e9"
        row_html = "".join([f"<td style='padding:6px; border-bottom:1px solid #eee;'>{v}</td>" for v in row.values])
        html += f"<tr style='background:{bg};'>{row_html}</tr>"
    html += "</table></div>"
    return html

def run_analysis_raw(df):
    # 1. 红球单兵
    red_single = []
    for b in range(1, 34):
        s = get_energy(df, [b], 'red')
        s10 = calc_slope(s, 5); s3 = calc_slope(s, 3)
        curr = s.iloc[-1]; ma5 = s.rolling(5).mean().iloc[-1]; ma10 = s.rolling(10).mean().iloc[-1]
        tag = "-"
        if curr > ma5 and curr > ma10: tag = "🔥强势"
        elif curr > ma5 and curr <= ma10: tag = "💰反弹"
        elif curr <= ma5 and curr > ma10: tag = "☠️转弱"
        elif curr < ma5 and curr < ma10: tag = "❄️冰点"
        red_single.append({'号': f"{b:02d}", 'S10': round(s10, 1), 'S3': round(s3, 1), '态': tag})
    df_rs = pd.DataFrame(red_single).sort_values(by='S10', ascending=False)
    # 2. 红球集团
    red_group = []
    for name, balls in RED_GROUPS.items():
        s = get_energy(df, balls, 'red')
        slope = calc_slope(s, 10)
        tag = "🔥" if slope > 2 else ("🚀" if slope > 0 else "❄️")
        red_group.append({'组': name, '球': str(balls), '率': round(slope, 1), '态': tag})
    df_rg = pd.DataFrame(red_group).sort_values(by='率', ascending=False)
    # 3. 蓝球单兵
    blue_single = []
    for b in range(1, 17):
        s = get_energy(df, [b], 'blue')
        s10 = calc_slope(s, 5); s3 = calc_slope(s, 3)
        curr = s.iloc[-1]; ma5 = s.rolling(5).mean().iloc[-1]
        tag = "🔥" if curr > ma5 else "❄️"
        blue_single.append({'号': f"{b:02d}", 'S10': round(s10, 1), 'S3': round(s3, 1), '态': tag})
    df_bs = pd.DataFrame(blue_single).sort_values(by='S10', ascending=False)
    # 4. 蓝球分组
    blue_group = []
    for name, balls in BLUE_GROUPS.items():
        s = get_energy(df, balls, 'blue')
        slope = calc_slope(s, 5)
        tag = "🔥" if slope > 1 else ("🚀" if slope > 0 else "❄️")
        blue_group.append({'组': name, '率': round(slope, 1), '态': tag})
    df_bg = pd.DataFrame(blue_group).sort_values(by='率', ascending=False)
    return df_rs, df_rg, df_bs, df_bg

def push_wechat(title, content):
    if not PUSH_TOKEN: return
    try:
        requests.post('http://www.pushplus.plus/send', json={"token": PUSH_TOKEN, "title": title, "content": content, "template": "html"})
    except Exception as e: print(f"推送出错: {e}")

# ================= 主程序 =================
def main():
    print("🚀 启动分析程序...")
    
    # 1. 检查本地最新期号
    local_last_issue = 0
    if os.path.exists(CSV_FILE):
        try:
            df_local = pd.read_csv(CSV_FILE)
            if not df_local.empty:
                local_last_issue = int(df_local['Issue'].iloc[-1])
        except: pass
    
    # 2. 更新数据库
    df = update_database()
    if df is None or df.empty:
        print("❌ 无法获取数据"); return
        
    current_last_row = df.iloc[-1]
    current_issue = int(current_last_row['Issue'])
    
    # 3. 判断是否为新数据
    is_updated = current_issue > local_last_issue
    status_icon = "✅" if is_updated else "⚠️"
    status_text = "【已更新】" if is_updated else "【未更新】"
    print(f"本地: {local_last_issue} | 线上: {current_issue} -> {status_text}")
    
    # 4. 执行分析与生成
    rs, rg, bs, bg = run_analysis_raw(df)
    ai_text = generate_raw_text(rs, rg, bs, bg)
    generate_interactive_page(df, current_issue, ai_text)
    
    # 5. 构建推送消息
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    page_url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if repo else "public/index.html"
    
    msg = f"<h2 style='text-align:center;margin-bottom:5px;'>📅 第 {current_issue} 期开奖结果</h2>"
    msg += format_winning_numbers_html(current_last_row) # 插入漂亮的开奖号码
    
    if not is_updated:
        msg += f"<div style='background:#fff3cd;color:#856404;padding:10px;border-radius:5px;font-size:12px;text-align:center;margin-bottom:10px;'>⚠️ 警告：数据源尚未更新，当前显示仍为上一期数据。<br>请稍后再次运行。</div>"
    
    msg += f"<div style='text-align:center;margin:15px 0;'><a href='{page_url}' style='background:#007bff;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;font-weight:bold;'>📈 点击查看交互式图表</a></div>"
    msg += df_to_html_table(rs.head(6), "📊 1. 红球前6名 (趋势强)")
    msg += df_to_html_table(bs.head(4), "🔵 3. 蓝球前4名")
    msg += df_to_html_table(rg.head(3), "🛡️ 2. 红球优势组")
    msg += df_to_html_table(bg, "⚖️ 4. 蓝球分组状况")
    msg += "<hr><p style='font-size:10px;color:gray;text-align:center;'>*完整数据请点击上方蓝色按钮进入控制台复制。</p>"
    
    push_wechat(f"{status_icon} 双色球第{current_issue}期-{status_text}", msg)
    print("✅ 任务完成")

if __name__ == "__main__":
    main()
