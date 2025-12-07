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

# --- 1. 数据获取 (极速增量版) ---
def get_web_data():
    # 【核心修改点】limit=5：只抓最新的5期数据，速度极快
    url = "http://datachart.500.com/ssq/history/newinc/history.php?limit=5&sort=0"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        response.encoding = 'utf-8'
        # 解析表格
        df = pd.read_html(response.text)[0].iloc[:, :8]
        df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
        # 简单清洗
        df = df[pd.to_numeric(df['Issue'], errors='coerce').notnull()]
        return df.sort_values(by='Issue').astype(int)
    except Exception as e:
        print(f"增量抓取失败: {e}")
        return None

def update_database():
    """ 智能合并逻辑：本地全量 + 网络增量 """
    df_local = pd.DataFrame()
    
    # 1. 读取本地历史 (全量)
    if os.path.exists(CSV_FILE):
        for enc in ['utf-8', 'gbk', 'gb18030']:
            try:
                temp = pd.read_csv(CSV_FILE, encoding=enc)
                if not temp.empty: 
                    df_local = temp; break
            except: pass
            
    # 2. 获取网络新数据 (仅5条)
    df_net = get_web_data()
    
    # 3. 合并与去重
    if df_net is not None:
        if not df_local.empty:
            # 确保列名一致
            df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
            # 合并：旧数据 + 新数据，然后根据期号去重
            df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'], keep='last')
        else: 
            # 如果本地没了，就只能用这5条(虽然少但也比报错强)
            df_final = df_net
            
        # 排序并保存
        df_final = df_final.sort_values(by='Issue')
        df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
        return df_final
        
    return df_local

# --- 2. 核心算法 (保持不变) ---
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

# --- 3. 生成原始数据表 (AI专用) ---
def run_analysis_raw(df):
    # 1. 红球单兵
    red_single = []
    for b in range(1, 34):
        s = get_energy(df, [b], 'red')
        s10 = calc_slope(s, 5); s3 = calc_slope(s, 3)
        ma5 = s.rolling(5).mean().iloc[-1]; ma10 = s.rolling(10).mean().iloc[-1]
        curr = s.iloc[-1]
        
        tag = "☠️死"
        if curr > ma5 and curr > ma10: tag = "🔥共振"
        elif curr > ma5 and curr <= ma10: tag = "💰回踩"
        elif curr <= ma5 and curr > ma10: tag = "✨妖股"
        
        red_single.append({'号码': f"{b:02d}", '10期斜率': round(s10, 1), '3期斜率': round(s3, 1), '状态': tag})
    df_red_single = pd.DataFrame(red_single).sort_values(by='10期斜率', ascending=False)

    # 2. 红球集团
    red_group = []
    for name, balls in RED_GROUPS.items():
        s = get_energy(df, balls, 'red')
        slope = calc_slope(s, 10)
        tag = "🔥强" if slope > 2 else ("🚀启" if slope > 0 else "☠️弱")
        red_group.append({'代号': name, '成员': str(balls), '斜率': round(slope, 1), '态': tag})
    df_red_group = pd.DataFrame(red_group).sort_values(by='斜率', ascending=False)

    # 3. 蓝球单兵
    blue_single = []
    for b in range(1, 17):
        s = get_energy(df, [b], 'blue')
        s10 = calc_slope(s, 5); s3 = calc_slope(s, 3)
        curr = s.iloc[-1]; ma5 = s.rolling(5).mean().iloc[-1]; ma10 = s.rolling(10).mean().iloc[-1]
        tag = "☠️死"
        if curr > ma5 and curr > ma10: tag = "🔥热"
        elif curr > ma5 and curr <= ma10: tag = "💰踩"
        elif curr <= ma5 and curr > ma10: tag = "🚀妖"
        blue_single.append({'号码': f"{b:02d}", '10期': round(s10, 1), '3期': round(s3, 1), '态': tag})
    df_blue_single = pd.DataFrame(blue_single).sort_values(by='10期', ascending=False)

    # 4. 蓝球分组
    blue_group = []
    for name, balls in BLUE_GROUPS.items():
        s = get_energy(df, balls, 'blue')
        slope = calc_slope(s, 5)
        tag = "🔥强" if slope > 1 else ("🚀启" if slope > 0 else "☠️弱")
        blue_group.append({'组合': name, '斜率': round(slope, 1), '态': tag})
    df_blue_group = pd.DataFrame(blue_group).sort_values(by='斜率', ascending=False)

    return df_red_single, df_red_group, df_blue_single, df_blue_group

# --- 4. 报告生成与推送 ---
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

def generate_chart(df, last_issue):
    # 生成网页占位，防止 Action 报错
    if not os.path.exists("public"): os.makedirs("public")
    repo = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    with open("public/index.html", "w", encoding='utf-8') as f:
        f.write(f"<html><body><h1>第 {last_issue} 期数据表已生成</h1><p>请查看微信推送的详细表格。</p></body></html>")

def push_wechat(title, content):
    if not PUSH_TOKEN: return
    requests.post('http://www.pushplus.plus/send', json={
        "token": PUSH_TOKEN, "title": title, "content": content, "template": "html"
    })

def main():
    df = update_database()
    if df.empty: return
    last_issue = df['Issue'].iloc[-1]
    
    # 运行分析
    rs, rg, bs, bg = run_analysis_raw(df)
    
    # 生成网页防止报错
    generate_chart(df, last_issue)
    
    # 构造情报
    repo = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    url = f"https://{repo}.github.io/lottery-auto/" if repo else "#"
    
    msg = f"<h2>📅 第 {last_issue} 期 · 原始数据情报</h2>"
    msg += f"👉 <a href='{url}'>查看K线图</a> (当前模式主要看表格)<hr>"
    msg += "<b>【请复制以下表格发给AI进行分析】</b><br><br>"
    
    # 红球单兵 (Top 15)
    msg += df_to_html(rs, "📊 1. 红球单兵 (Top 15)", limit=15)
    # 红球集团 (全览)
    msg += df_to_html(rg, "🛡️ 2. 红球集团 (11组)")
    # 蓝球单兵 (全览)
    msg += df_to_html(bs, "🔵 3. 蓝球单兵 (16码)")
    # 蓝球分组 (全览)
    msg += df_to_html(bg, "⚖️ 4. 蓝球分组 (8组)")
    
    push_wechat(f"双色球数据-{last_issue}", msg)

if __name__ == "__main__":
    main()
