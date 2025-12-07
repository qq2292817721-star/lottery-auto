import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ================= 配置区 =================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN")
CSV_FILE = "ssq.csv"

# 分组定义
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

# --- 3. 深度分析逻辑 (生成DataFrame) ---
def run_analysis_raw(df):
    # 1. 红球单兵表
    red_single = []
    for b in range(1, 34):
        s = get_energy(df, [b], 'red')
        s10 = calc_slope(s, 5); s3 = calc_slope(s, 3)
        ma5 = s.rolling(5).mean().iloc[-1]; ma10 = s.rolling(10).mean().iloc[-1]
        curr = s.iloc[-1]
        
        tag = "☠️"
        if curr > ma5 and curr > ma10: tag = "🔥共振"
        elif curr > ma5 and curr <= ma10: tag = "💰回踩"
        elif curr <= ma5 and curr > ma10: tag = "✨妖股"
        
        red_single.append({'号码': f"{b:02d}", '10期斜率': round(s10, 1), '3期斜率': round(s3, 1), '状态': tag})
    df_red_single = pd.DataFrame(red_single).sort_values(by='10期斜率', ascending=False)

    # 2. 红球集团表
    red_group = []
    for name, balls in RED_GROUPS.items():
        s = get_energy(df, balls, 'red')
        slope = calc_slope(s, 10)
        tag = "🔥" if slope > 2 else ("🚀" if slope > 0 else "☠️")
        red_group.append({'代号': name, '成员': str(balls), '斜率': round(slope, 1), '态': tag})
    df_red_group = pd.DataFrame(red_group).sort_values(by='斜率', ascending=False)

    # 3. 蓝球单兵表
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

    # 4. 蓝球分组表
    blue_group = []
    for name, balls in BLUE_GROUPS.items():
        s = get_energy(df, balls, 'blue')
        slope = calc_slope(s, 5)
        tag = "🔥" if slope > 1 else ("🚀" if slope > 0 else "☠️")
        blue_group.append({'组合': name, '斜率': round(slope, 1), '态': tag})
    df_blue_group = pd.DataFrame(blue_group).sort_values(by='斜率', ascending=False)

    return df_red_single, df_red_group, df_blue_single, df_blue_group

# --- 4. 报告生成模块 (HTML表格化) ---
def df_to_html_table(df, title, limit=None):
    if limit: df = df.head(limit)
    html = f"<div style='margin-top:10px;'><b>{title}</b><br>"
    html += "<table border='1' cellspacing='0' cellpadding='2' style='border-collapse:collapse; width:100%; font-size:12px; text-align:center; border-color:#ddd;'>"
    
    # 表头
    html += "<tr style='background-color:#f2f2f2;'>"
    for col in df.columns: html += f"<th>{col}</th>"
    html += "</tr>"
    
    # 内容
    for _, row in df.iterrows():
        bg_color = "#ffffff"
        row_str = str(row.values)
        if "🔥" in row_str: bg_color = "#fff0f0" # 浅红
        elif "💰" in row_str: bg_color = "#fffff0" # 浅黄
        elif "☠️" in row_str: bg_color = "#f9f9f9" # 浅灰
        
        html += f"<tr style='background-color:{bg_color};'>"
        for val in row.values: html += f"<td>{val}</td>"
        html += "</tr>"
    html += "</table></div>"
    return html

def generate_full_report(last_issue, rs, rg, bs, bg, chart_url):
    # 1. 标题与链接
    msg = f"<h2>📅 第 {last_issue} 期 · 全息深度战报</h2>"
    msg += f"👉 <a href='{chart_url}'><b>[点此查看交互式K线图]</b></a><hr>"
    
    # 2. 数据展示区 (表格)
    msg += "<h3>📊 第一步：数据雷达 (Raw Data)</h3>"
    msg += df_to_html_table(rs, "1. 红球单兵 (Top 8)", limit=8)
    msg += df_to_html_table(rg, "2. 红球集团 (全览)")
    msg += df_to_html_table(bs, "3. 蓝球单兵 (Top 5)", limit=5)
    msg += df_to_html_table(bg, "4. 蓝球分组 (Top 4)", limit=4)
    
    # 3. 逻辑推演区
    msg += "<hr><h3>🧠 第二步：逻辑推演 (Logic)</h3>"
    
    # 红球推演
    hot_single = rs[rs['状态'] == '🔥共振']['号码'].tolist()
    dip_single = rs[rs['状态'] == '💰回踩']['号码'].tolist()
    top_group_name = rg.iloc[0]['代号']
    top_group_str = rg.iloc[0]['成员']
    top_group_list = eval(top_group_str)
    top_group_fmt = [f"{x:02d}" for x in top_group_list]
    
    # 找交集
    intersect = list(set(hot_single) & set(top_group_fmt))
    
    msg += "<b>🔴 红球分析：</b><br>"
    msg += f"• <b>单兵最强：</b>{hot_single[:5]}... (共{len(hot_single)}个)<br>"
    msg += f"• <b>集团最强：</b>{top_group_name} {top_group_list}<br>"
    if intersect:
        msg += f"• <b>✨ 完美共振胆码：</b>{intersect} (单兵+集团双强)<br>"
    else:
        msg += f"• <b>⚠️ 无完美共振：</b>主力分歧，以单兵斜率王 <b>{rs.iloc[0]['号码']}</b> 为准。<br>"
    
    # 蓝球推演
    top_b_single = bs.iloc[0]['号码']
    top_b_group_name = bg.iloc[0]['组合']
    
    msg += "<br><b>🔵 蓝球分析：</b><br>"
    msg += f"• <b>斜率王：</b>{top_b_single}<br>"
    msg += f"• <b>冠军组：</b>{top_b_group_name}<br>"
    
    # 4. 最终方案
    msg += "<hr><h3>🎯 第三步：实战方案 (Action)</h3>"
    
    # 生成方案号码
    # A: 强攻
    plan_a_r = sorted(hot_single[:6])
    if len(plan_a_r) < 6: plan_a_r += sorted(dip_single)[:(6-len(plan_a_r))]
    
    # B: 集团
    plan_b_r = sorted(list(set(top_group_fmt + hot_single[:3])))[:6]
    
    # C: 胆拖
    banker = intersect if intersect else hot_single[:2]
    drags = [x for x in hot_single if x not in banker][:5]
    
    msg += f"<div style='background:#fff5f5; padding:8px; border-radius:5px; margin-bottom:5px;'>"
    msg += f"<b>【A: 趋势强攻】</b>(单兵高斜率)<br>🔴 {','.join(plan_a_r)}<br>🔵 {bs.iloc[0]['号码']}, {bs.iloc[1]['号码']}</div>"
    
    msg += f"<div style='background:#f0f8ff; padding:8px; border-radius:5px; margin-bottom:5px;'>"
    msg += f"<b>【B: 集团掩护】</b>(最强组+强援)<br>🔴 {','.join(plan_b_r)}<br>🔵 {bs.iloc[0]['号码']}, {bs.iloc[2]['号码']}</div>"
    
    msg += f"<div style='background:#f0fff0; padding:8px; border-radius:5px;'>"
    msg += f"<b>【C: 极客胆拖】</b><br>🔴 胆:{','.join(banker)} <br>⚪ 拖:{','.join(drags)}<br>🔵 {bs.iloc[0]['号码']}</div>"
    
    return msg

# --- 图表生成 (保持不变，为了不报错) ---
def generate_interactive_chart(df, last_issue):
    if not os.path.exists("public"): os.makedirs("public")
    # 这里只生成简单占位，或者你可以保留之前的完整绘图逻辑
    with open("public/index.html", "w", encoding='utf-8') as f:
        f.write(f"<html><body><h1>Chart for {last_issue}</h1></body></html>")

# --- 主程序 ---
def push_wechat(title, content):
    if not PUSH_TOKEN: return
    requests.post('http://www.pushplus.plus/send', json={
        "token": PUSH_TOKEN, "title": title, "content": content, "template": "html"
    })

def main():
    df = update_database()
    if df.empty: return
    last_issue = df['Issue'].iloc[-1]
    
    # 1. 运行分析
    rs, rg, bs, bg = run_analysis_raw(df)
    
    # 2. 生成链接
    repo_owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    repo_name = "lottery-auto"
    chart_url = f"https://{repo_owner}.github.io/{repo_name}/" if repo_owner else "#"
    
    # 3. 生成并推送报告
    msg = generate_full_report(last_issue, rs, rg, bs, bg, chart_url)
    push_wechat(f"双色球第{last_issue}期-全息战报", msg)
    
    # 4. 生成网页 (防止Action报错)
    generate_interactive_chart(df, last_issue)

if __name__ == "__main__":
    main()
