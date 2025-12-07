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

# --- 1. 数据模块 ---
def get_web_data():
    url = "http://datachart.500.com/ssq/history/newinc/history.php?limit=50&sort=0"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
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

# --- 3. 计算并生成原始文本数据 (给AI看) ---
def generate_ai_report_text(df_rs, df_rg, df_bs, df_bg, last_issue):
    text = f"=== 双色球第 {last_issue} 期 · AI分析数据源 ===\n\n"
    
    text += "【1. 红球单兵雷达 (前20名 + 回踩关注)】\n"
    text += df_rs.head(20).to_string(index=False) + "\n\n"
    
    text += "【2. 红球集团军 (11组)】\n"
    text += df_rg.to_string(index=False) + "\n\n"
    
    text += "【3. 蓝球单兵 (16码)】\n"
    text += df_bs.to_string(index=False) + "\n\n"
    
    text += "【4. 蓝球分组 (8组)】\n"
    text += df_bg.to_string(index=False) + "\n"
    
    return text

# --- 4. 生成带“复制按钮”的网页 (核心升级) ---
def generate_interactive_page(df, last_issue, ai_report_text):
    if not os.path.exists("public"): os.makedirs("public")
    
    # === A. 生成 Plotly 图表 HTML 片段 ===
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.15,
                        subplot_titles=("【宏观】10期趋势 (MA5)", "【微观】3期买点 (MA10)"))
    
    # (此处省略部分重复的 Trace 代码以节省篇幅，逻辑与之前完全一致，仅用于生成 fig)
    # --- 绘图逻辑开始 ---
    buttons = []; trace_idx = 0
    # 为了网页加载速度，只取最近 300 期画图
    df_chart = df.tail(300).reset_index(drop=True)
    
    def calc_k(df, t, type, p):
        s = get_energy(df, [t], type).tolist()
        ohlc = []
        for i in range(0, len(s), p):
            c = s[i:i+p]
            if not c: continue
            prev = s[i-1] if i>0 else 0
            ohlc.append([prev, max(prev, max(c)), min(prev, min(c)), c[-1]])
        k = pd.DataFrame(ohlc, columns=['Open','High','Low','Close'])
        k['MA'] = k['Close'].rolling(5 if p==10 else 10).mean()
        return k

    # 红球
    for ball in range(1, 34):
        d10 = calc_k(df_chart, ball, 'red', 10)
        d3 = calc_k(df_chart, ball, 'red', 3).tail(100)
        fig.add_trace(go.Candlestick(x=d10.index, open=d10['Open'], high=d10['High'], low=d10['Low'], close=d10['Close'], visible=(ball==1), increasing_line_color='#FF4136', decreasing_line_color='#0074D9'), 1, 1)
        fig.add_trace(go.Scatter(x=d10.index, y=d10['MA'], mode='lines', visible=(ball==1), line=dict(color='yellow', width=1)), 1, 1)
        fig.add_trace(go.Candlestick(x=list(range(len(d3))), open=d3['Open'], high=d3['High'], low=d3['Low'], close=d3['Close'], visible=(ball==1), increasing_line_color='#F012BE', decreasing_line_color='#2ECC40'), 2, 1)
        fig.add_trace(go.Scatter(x=list(range(len(d3))), y=d3['MA'], mode='lines', visible=(ball==1), line=dict(color='yellow', width=1)), 2, 1)
        
        vis = [False] * (49*4); vis[trace_idx:trace_idx+4] = [True]*4
        buttons.append(dict(label=f"🔴{ball:02d}", method="update", args=[{"visible": vis}, {"title": f"红球 {ball:02d}"}]))
        trace_idx += 4
        
    # 蓝球
    for ball in range(1, 17):
        d10 = calc_k(df_chart, ball, 'blue', 10)
        d3 = calc_k(df_chart, ball, 'blue', 3).tail(100)
        fig.add_trace(go.Candlestick(x=d10.index, open=d10['Open'], high=d10['High'], low=d10['Low'], close=d10['Close'], visible=False, increasing_line_color='#FF4136', decreasing_line_color='#0074D9'), 1, 1)
        fig.add_trace(go.Scatter(x=d10.index, y=d10['MA'], mode='lines', visible=False, line=dict(color='cyan', width=1)), 1, 1)
        fig.add_trace(go.Candlestick(x=list(range(len(d3))), open=d3['Open'], high=d3['High'], low=d3['Low'], close=d3['Close'], visible=False, increasing_line_color='#F012BE', decreasing_line_color='#2ECC40'), 2, 1)
        fig.add_trace(go.Scatter(x=list(range(len(d3))), y=d3['MA'], mode='lines', visible=False, line=dict(color='cyan', width=1)), 2, 1)
        
        vis = [False] * (49*4); vis[trace_idx:trace_idx+4] = [True]*4
        buttons.append(dict(label=f"🔵{ball:02d}", method="update", args=[{"visible": vis}, {"title": f"蓝球 {ball:02d}"}]))
        trace_idx += 4
    # --- 绘图逻辑结束 ---

    fig.update_layout(
        updatemenus=[dict(active=0, buttons=buttons, direction="down", pad={"r": 10, "t": 10}, showactive=True, x=0.5, xanchor="center", y=1.15, yanchor="top")],
        template="plotly_dark", height=800, margin=dict(t=100)
    )
    
    # 获取 Plotly 的 HTML 字符串 (只获取 div 部分，不包含 full html)
    plot_html = fig.to_html(full_html=False, include_plotlyjs='cdn')

    # === B. 构建自定义 HTML 页面 ===
    # 这里我们手写 HTML 结构，嵌入“复制按钮”和“隐藏数据”
    custom_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>双色球第 {last_issue} 期战术板</title>
        <style>
            body {{ font-family: sans-serif; background: #111; color: #eee; margin: 0; padding: 0; }}
            .header {{ padding: 20px; text-align: center; background: #222; }}
            .btn-copy {{
                background: #00C853; color: white; border: none; padding: 15px 30px;
                font-size: 18px; border-radius: 8px; cursor: pointer;
                box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: transform 0.1s;
                width: 90%; max-width: 400px; margin: 10px auto; display: block;
            }}
            .btn-copy:active {{ transform: scale(0.98); background: #00E676; }}
            .tips {{ color: #aaa; font-size: 12px; text-align: center; margin-bottom: 10px; }}
            textarea {{ display: none; }} /* 隐藏数据源 */
        </style>
    </head>
    <body>
        <div class="header">
            <h2>📊 双色球第 {last_issue} 期</h2>
            <p>全自动量化分析系统 · 极客版</p>
            
            <!-- 核心功能区 -->
            <button class="btn-copy" onclick="copyData()">📋 一键复制数据给 AI</button>
            <div class="tips">点击按钮 -> 回到对话框粘贴 -> 获取策略</div>
            
            <!-- 隐藏的数据容器 -->
            <textarea id="ai-data">{ai_report_text}</textarea>
        </div>

        <!-- 图表区域 -->
        {plot_html}

        <script>
            function copyData() {{
                var copyText = document.getElementById("ai-data");
                copyText.style.display = "block"; // 临时显示以便选区
                copyText.select();
                copyText.setSelectionRange(0, 99999); // 兼容手机
                navigator.clipboard.writeText(copyText.value).then(function() {{
                    alert("✅ 数据已复制！\n请切换回 AI 对话窗口，直接粘贴即可。");
                }}, function(err) {{
                    document.execCommand("copy"); // 备用方案
                    alert("✅ 数据已复制 (兼容模式)！");
                }});
                copyText.style.display = "none"; // 恢复隐藏
            }}
        </script>
    </body>
    </html>
    """
    
    with open("public/index.html", "w", encoding='utf-8') as f:
        f.write(custom_html)

# --- 5. 主流程 ---
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
    
    # 2. 生成给AI的文本报告
    ai_text = generate_ai_report_text(rs, rg, bs, bg, last_issue)
    
    # 3. 生成带复制按钮的网页
    generate_interactive_page(df, last_issue, ai_text)
    
    # 4. 推送消息 (只给链接和简单结论)
    repo = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    url = f"https://{repo}.github.io/lottery-auto/" if repo else "#"
    
    msg = f"<h2>📅 第 {last_issue} 期 · 分析完毕</h2>"
    msg += f"<h1>👉 <a href='{url}'>点击打开控制台 & 复制数据</a></h1>"
    msg += "<p>网页已包含：<br>1. 一键复制数据按钮<br>2. 交互式 K 线图</p>"
    msg += f"<hr><b>红球榜首：</b> {rs.iloc[0]['号码']} (斜率 {rs.iloc[0]['10期斜率']})<br>"
    msg += f"<b>蓝球榜首：</b> {bs.iloc[0]['号码']} (斜率 {bs.iloc[0]['10期']})"
    
    print("推送中...")
    push_wechat(f"双色球战报-{last_issue}", msg)

if __name__ == "__main__":
    main()
