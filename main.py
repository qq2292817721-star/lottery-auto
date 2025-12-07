import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json

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

# --- 1. 数据模块 ---
def get_web_data():
    url = "http://datachart.500.com/ssq/history/newinc/history.php?limit=50&sort=0"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.encoding = 'utf-8'
        # 修复 FutureWarning
        from io import StringIO
        df = pd.read_html(StringIO(response.text))[0].iloc[:, :8]
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
                    df_local = temp; break
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

# --- 3. K线计算 ---
def calculate_kline_for_chart(df, target_ball, ball_type, period):
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

# --- 4. 生成原生交互网页 (重大升级) ---
def generate_interactive_page(df, last_issue, ai_text):
    if not os.path.exists("public"): os.makedirs("public")
    
    # 准备数据
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.15,
                        subplot_titles=("【宏观】10期趋势 (MA5)", "【微观】3期买点 (MA10)"))
    
    # 限制数据量
    df_chart = df.tail(300).reset_index(drop=True)
    
    # 添加所有 Trace，但默认只显示第一个(红01)
    # 顺序：红01...红33, 蓝01...蓝16
    # 每个球 4 个 Trace (上K, 上MA, 下K, 下MA)
    
    total_traces = (33 + 16) * 4
    
    # 红球
    for ball in range(1, 34):
        df_10 = calculate_kline_for_chart(df_chart, ball, 'red', 10)
        df_3 = calculate_kline_for_chart(df_chart, ball, 'red', 3).tail(100)
        is_visible = (ball == 1)
        
        fig.add_trace(go.Candlestick(x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'],
                                     visible=is_visible, increasing_line_color='#FF4136', decreasing_line_color='#0074D9', name='10期K'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_10.index, y=df_10['MA'], mode='lines', visible=is_visible, line=dict(color='yellow', width=1), name='MA5'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=list(range(len(df_3))), open=df_3['Open'], high=df_3['High'], low=df_3['Low'], close=df_3['Close'],
                                     visible=is_visible, increasing_line_color='#F012BE', decreasing_line_color='#2ECC40', name='3期K'), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(df_3))), y=df_3['MA'], mode='lines', visible=is_visible, line=dict(color='yellow', width=1), name='MA10'), row=2, col=1)

    # 蓝球
    for ball in range(1, 17):
        df_10 = calculate_kline_for_chart(df_chart, ball, 'blue', 10)
        df_3 = calculate_kline_for_chart(df_chart, ball, 'blue', 3).tail(100)
        
        fig.add_trace(go.Candlestick(x=df_10.index, open=df_10['Open'], high=df_10['High'], low=df_10['Low'], close=df_10['Close'],
                                     visible=False, increasing_line_color='#FF4136', decreasing_line_color='#0074D9', name='10期K'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_10.index, y=df_10['MA'], mode='lines', visible=False, line=dict(color='cyan', width=1), name='MA5'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=list(range(len(df_3))), open=df_3['Open'], high=df_3['High'], low=df_3['Low'], close=df_3['Close'],
                                     visible=False, increasing_line_color='#F012BE', decreasing_line_color='#2ECC40', name='3期K'), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(df_3))), y=df_3['MA'], mode='lines', visible=False, line=dict(color='cyan', width=1), name='MA10'), row=2, col=1)

    # 基础布局 (去掉 Plotly 自带的按钮，我们自己写 HTML 控件)
    fig.update_layout(
        template="plotly_dark", 
        height=700, 
        margin=dict(t=50, l=10, r=10, b=10),
        showlegend=False,
        dragmode='pan' # 手机上默认拖动
    )
    
    # 生成图表 Div (不含 HTML 头尾)
    plot_div = fig.to_html(full_html=False, include_plotlyjs='cdn', div_id='plotly_div')

    # === 构建原生 HTML 页面 ===
    # 这里我们注入自定义 JavaScript 来控制 Plotly 的显示
    custom_html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
        <title>双色球第 {last_issue} 期</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #121212; color: #eee; margin: 0; padding: 0; }}
            .header {{ padding: 15px; background: #1e1e1e; border-bottom: 1px solid #333; }}
            .controls {{ display: flex; gap: 10px; margin-top: 10px; }}
            select {{ 
                flex: 1; padding: 10px; font-size: 16px; border-radius: 8px; border: 1px solid #444; 
                background: #333; color: white; -webkit-appearance: none; 
            }}
            .btn-copy {{
                background: #00C853; color: white; border: none; padding: 12px; width: 100%;
                font-size: 16px; border-radius: 8px; font-weight: bold; cursor: pointer;
            }}
            .btn-copy:active {{ background: #00E676; }}
            textarea {{ display: none; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h3 style="margin:0 0 10px 0; text-align:center;">📊 第 {last_issue} 期 · 极客控制台</h3>
            
            <button class="btn-copy" onclick="copyData()">📋 复制全量数据 (发给AI)</button>
            <textarea id="ai-data">{ai_text}</textarea>
            
            <div class="controls">
                <select id="red-select" onchange="switchBall('red')">
                    <option disabled>-- 切换红球 --</option>
                    {''.join([f'<option value="{i}">🔴 红球 {i:02d}</option>' for i in range(1, 34)])}
                </select>
                <select id="blue-select" onchange="switchBall('blue')">
                    <option selected disabled>-- 切换蓝球 --</option>
                    {''.join([f'<option value="{i}">🔵 蓝球 {i:02d}</option>' for i in range(1, 17)])}
                </select>
            </div>
        </div>

        <!-- 图表容器 -->
        {plot_div}

        <script>
            // 复制功能
            function copyData() {{
                var copyText = document.getElementById("ai-data");
                copyText.style.display = "block";
                copyText.select();
                copyText.setSelectionRange(0, 99999);
                try {{
                    navigator.clipboard.writeText(copyText.value);
                    alert("✅ 数据已复制！\\n请去对话框粘贴。");
                }} catch (err) {{
                    document.execCommand("copy");
                    alert("✅ 数据已复制！");
                }}
                copyText.style.display = "none";
            }}

            // 切换图表逻辑
            function switchBall(type) {{
                var plotlyDiv = document.getElementById('plotly_div');
                var val;
                var baseIndex;
                
                // 重置另一个下拉框
                if (type === 'red') {{
                    document.getElementById('blue-select').selectedIndex = 0;
                    val = parseInt(document.getElementById('red-select').value);
                    // 红球索引: (val - 1) * 4
                    baseIndex = (val - 1) * 4;
                }} else {{
                    document.getElementById('red-select').selectedIndex = 0;
                    val = parseInt(document.getElementById('blue-select').value);
                    // 蓝球索引: (33 * 4) + (val - 1) * 4
                    baseIndex = (33 * 4) + (val - 1) * 4;
                }}

                // 构建 visible 数组
                // 总共有 (33+16)*4 = 196 个 trace
                var update = {{'visible': []}};
                for (var i = 0; i < 196; i++) {{
                    update.visible.push(false);
                }}
                
                // 开启选中的那4条线
                update.visible[baseIndex] = true;     // 10期K
                update.visible[baseIndex + 1] = true; // 10期MA
                update.visible[baseIndex + 2] = true; // 3期K
                update.visible[baseIndex + 3] = true; // 3期MA

                // 调用 Plotly 重绘 (瞬间完成)
                Plotly.restyle(plotlyDiv, update);
            }}
        </script>
    </body>
    </html>
    """
    
    with open("public/index.html", "w", encoding='utf-8') as f:
        f.write(custom_html)

# --- 5. 生成纯文本数据 ---
def generate_raw_text(rs, rg, bs, bg):
    t = "【双色球数据源】\n"
    t += "1. 红球单兵:\n" + rs.to_string() + "\n\n"
    t += "2. 红球集团:\n" + rg.to_string() + "\n\n"
    t += "3. 蓝球单兵:\n" + bs.to_string() + "\n\n"
    t += "4. 蓝球分组:\n" + bg.to_string()
    return t

# --- 6. 生成 HTML 表格 ---
def df_to_html_table(df, title):
    html = f"<div style='margin-bottom:15px'><b>{title}</b>"
    html += "<table border='1' style='border-collapse:collapse;width:100%;font-size:11px;text-align:center;'>"
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
        red_single.append({'号': f"{b:02d}", '10期': round(s10, 1), '3期': round(s3, 1), '态': tag})
    df_rs = pd.DataFrame(red_single).sort_values(by='10期', ascending=False)

    # 红球集团
    red_group = []
    for name, balls in RED_GROUPS.items():
        s = get_energy(df, balls, 'red')
        slope = calc_slope(s, 10)
        tag = "🔥" if slope > 2 else ("🚀" if slope > 0 else "☠️")
        red_group.append({'组': name, '球': str(balls), '率': round(slope, 1), '态': tag})
    df_rg = pd.DataFrame(red_group).sort_values(by='率', ascending=False)

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
        blue_single.append({'号': f"{b:02d}", '10期': round(s10, 1), '3期': round(s3, 1), '态': tag})
    df_bs = pd.DataFrame(blue_single).sort_values(by='10期', ascending=False)

    # 蓝球分组
    blue_group = []
    for name, balls in BLUE_GROUPS.items():
        s = get_energy(df, balls, 'blue')
        slope = calc_slope(s, 5)
        tag = "🔥" if slope > 1 else ("🚀" if slope > 0 else "☠️")
        blue_group.append({'组': name, '率': round(slope, 1), '态': tag})
    df_bg = pd.DataFrame(blue_group).sort_values(by='率', ascending=False)

    return df_rs, df_rg, df_bs, df_bg

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
    
    # 1. 计算所有数据
    rs, rg, bs, bg = run_analysis_raw(df)
    
    # 2. 生成给AI的纯文本
    ai_text = generate_raw_text(rs, rg, bs, bg)
    
    # 3. 生成原生交互网页 (带 select 下拉框)
    generate_interactive_page(df, last_issue, ai_text)
    
    # 4. 生成微信内容
    repo = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    url = f"https://{repo}.github.io/lottery-auto/" if repo else "#"
    
    msg = f"<h2>📅 第 {last_issue} 期 · 全量数据战报</h2>"
    msg += f"👉 <a href='{url}'><b>点击打开控制台 (交互版)</b></a><hr>"
    
    msg += df_to_html_table(rs, "📊 1. 红球单兵")
    msg += df_to_html_table(rg, "🛡️ 2. 红球集团")
    msg += df_to_html_table(bs, "🔵 3. 蓝球单兵")
    msg += df_to_html_table(bg, "⚖️ 4. 蓝球分组")
    
    msg += "<hr><b>📋 纯文本数据 (长按复制)：</b><br>"
    msg += f"<textarea rows='10' style='width:100%;font-size:10px;background:#f4f4f4;'>{ai_text}</textarea>"
    
    print("推送中...")
    push_wechat(f"双色球数据-{last_issue}", msg)

if __name__ == "__main__":
    main()
