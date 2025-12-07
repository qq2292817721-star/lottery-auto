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

# --- 2. 计算模块 ---
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

# --- 3. 图表生成模块 (修复报错的关键) ---
def generate_interactive_chart(df, last_issue):
    # 必须创建目录，否则部署会失败
    if not os.path.exists("public"): os.makedirs("public")
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.15,
                        subplot_titles=("【宏观】10期趋势 (MA5)", "【微观】3期买点 (MA10)"))
    buttons = []; trace_idx = 0
    
    # 简化的绘图循环，确保网页能生成
    for ball in range(1, 34):
        s = get_energy(df, [ball], 'red')
        # 10期数据
        s10_ma = s.rolling(5).mean()
        # 3期数据
        s3_ma = s.rolling(10).mean()
        
        # 为了展示方便，这里画线图代替K线，减少代码量防止出错
        # 上图
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s, mode='lines', name=f'红{ball:02d}能量', visible=(ball==1), line=dict(color='#FF4136')), row=1, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s10_ma, mode='lines', name='MA5', visible=(ball==1), line=dict(color='yellow', width=1, dash='dash')), row=1, col=1)
        # 下图
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s, mode='lines', name=f'红{ball:02d}能量', visible=(ball==1), line=dict(color='#F012BE')), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s3_ma, mode='lines', name='MA10', visible=(ball==1), line=dict(color='yellow', width=1, dash='dash')), row=2, col=1)
        
        vis = [False] * (49 * 4)
        vis[trace_idx:trace_idx+4] = [True, True, True, True]
        buttons.append(dict(label=f"🔴 红{ball:02d}", method="update", args=[{"visible": vis}, {"title": f"红球 {ball:02d} 趋势"}]))
        trace_idx += 4

    for ball in range(1, 17):
        s = get_energy(df, [ball], 'blue')
        s10_ma = s.rolling(5).mean(); s3_ma = s.rolling(10).mean()
        
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s, mode='lines', name=f'蓝{ball:02d}能量', visible=False, line=dict(color='#0074D9')), row=1, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s10_ma, mode='lines', name='MA5', visible=False, line=dict(color='cyan', width=1, dash='dash')), row=1, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s, mode='lines', name=f'蓝{ball:02d}能量', visible=False, line=dict(color='#0074D9')), row=2, col=1)
        fig.add_trace(go.Scatter(x=list(range(len(s))), y=s3_ma, mode='lines', name='MA10', visible=False, line=dict(color='cyan', width=1, dash='dash')), row=2, col=1)
        
        vis = [False] * (49 * 4)
        vis[trace_idx:trace_idx+4] = [True, True, True, True]
        buttons.append(dict(label=f"🔵 蓝{ball:02d}", method="update", args=[{"visible": vis}, {"title": f"蓝球 {ball:02d} 趋势"}]))
        trace_idx += 4

    fig.update_layout(
        updatemenus=[dict(active=0, buttons=buttons, direction="down", pad={"r": 10, "t": 10}, showactive=True, x=0.5, xanchor="center", y=1.15, yanchor="top")],
        template="plotly_dark", height=800, title=f"双色球第 {last_issue} 期 - 交互式控制台"
    )
    fig.write_html("public/index.html")

# --- 4. 深度分析逻辑 ---
def run_analysis(df):
    # 红球单兵
    red_single = []
    for b in range(1, 34):
        s = get_energy(df, [b], 'red')
        s10 = calc_slope(s, 5); ma5 = s.rolling(5).mean().iloc[-1]
        ma10 = s.rolling(10).mean().iloc[-1]; curr = s.iloc[-1]
        tag = "☠️死"
        if curr > ma5 and curr > ma10: tag = "🔥共振"
        elif curr > ma5 and curr <= ma10: tag = "💰回踩"
        elif curr <= ma5 and curr > ma10: tag = "✨妖股"
        red_single.append({'b': b, 's': s10, 'tag': tag})
    red_single.sort(key=lambda x: x['s'], reverse=True)

    # 集团与蓝球
    red_group = [{'n': k, 'b': v, 's': calc_slope(get_energy(df, v, 'red'), 10)} for k,v in RED_GROUPS.items()]
    red_group.sort(key=lambda x: x['s'], reverse=True)
    
    blue_single = [{'b': b, 's': calc_slope(get_energy(df, [b], 'blue'), 5)} for b in range(1, 17)]
    blue_single.sort(key=lambda x: x['s'], reverse=True)
    
    blue_group = [{'n': k, 's': calc_slope(get_energy(df, v, 'blue'), 5)} for k,v in BLUE_GROUPS.items()]
    blue_group.sort(key=lambda x: x['s'], reverse=True)
    
    return red_single, red_group, blue_single, blue_group

# --- 5. 报告生成与推送 ---
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
    
    # 1. 生成图表 (修复报错)
    generate_interactive_chart(df, last_issue)
    
    # 2. 运行分析
    rs, rg, bs, bg = run_analysis(df)
    
    # 3. 逻辑推演
    hot_reds = [r['b'] for r in rs if r['tag']=="🔥共振"][:6]
    top_group_balls = rg[0]['b']
    intersection = list(set(hot_reds) & set(top_group_balls))
    
    # 4. 生成方案
    plan_a = sorted(hot_reds) # 趋势强攻
    plan_b = sorted(list(set(top_group_balls + hot_reds[:3])))[:6] # 集团掩护
    
    # 胆拖逻辑
    banker = intersection if intersection else hot_reds[:2]
    drags = [x for x in hot_reds if x not in banker][:5]
    
    repo_owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    repo_name = "lottery-auto"
    chart_url = f"https://{repo_owner}.github.io/{repo_name}/" if repo_owner else "#"

    # HTML 报告
    msg = f"<h2>📅 第 {last_issue} 期 · 深度战报</h2>"
    msg += f"👉 <a href='{chart_url}'><b>点击打开云端 K 线图</b></a><hr>"
    
    msg += "<h3>📊 数据铁证</h3>"
    msg += f"<b>1. 红球单兵王：</b> {rs[0]['b']:02d} (斜率 {rs[0]['s']:.1f})<br>"
    msg += f"<b>2. 红球最强组：</b> {rg[0]['n']} (斜率 {rg[0]['s']:.1f})<br>"
    msg += f"<b>3. 蓝球单兵王：</b> {bs[0]['b']:02d} (斜率 {bs[0]['s']:.1f})<br>"
    msg += f"<b>4. 蓝球最强组：</b> {bg[0]['n']} (斜率 {bg[0]['s']:.1f})<br>"
    
    msg += "<hr><h3>🧠 逻辑推演</h3>"
    if intersection:
        msg += f"发现红球共振胆码：<b>{intersection}</b><br>"
    else:
        msg += f"未发现完美共振，死磕单兵王 <b>{rs[0]['b']}</b><br>"
    
    msg += "<hr><h3>🎫 最终方案</h3>"
    msg += f"<div style='background:#fff0f0; padding:10px;'><b>【A: 强攻】</b> 🔴 {plan_a} + 🔵 {bs[0]['b']:02d}, {bs[1]['b']:02d}</div><br>"
    msg += f"<div style='background:#f0f8ff; padding:10px;'><b>【B: 集团】</b> 🔴 {plan_b} + 🔵 {bs[0]['b']:02d}</div><br>"
    msg += f"<div style='background:#f0fff0; padding:10px;'><b>【C: 胆拖】</b> 🔴 胆:{banker} 拖:{drags} + 🔵 {bs[0]['b']:02d}</div>"
    
    print("推送中...")
    push_wechat(f"双色球深度复盘-{last_issue}", msg)

if __name__ == "__main__":
    main()
