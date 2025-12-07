import pandas as pd
import numpy as np
import requests
import os
import time

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

# --- 基础工具 ---
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
        try: df_local = pd.read_csv(CSV_FILE)
        except: pass
    df_net = get_web_data()
    
    if df_net is not None:
        if not df_local.empty:
            df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'])
        else: df_final = df_net
        df_final = df_final.sort_values(by='Issue')
        df_final.to_csv(CSV_FILE, index=False)
        return df_final
    return df_local

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

# --- 核心分析逻辑 (生成数据表) ---
def run_analysis(df):
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
        
        red_single.append({'号码': f"{b:02d}", '10期斜率': round(s10, 1), '3期斜率': round(s3, 1), '诊断': tag})
    df_red_single = pd.DataFrame(red_single).sort_values(by='10期斜率', ascending=False)

    # 2. 红球集团
    red_group = []
    for name, balls in RED_GROUPS.items():
        s = get_energy(df, balls, 'red')
        slope = calc_slope(s, 10)
        tag = "🔥冲锋" if slope > 2 else ("🚀启动" if slope > 0 else "☠️弱势")
        red_group.append({'代号': name, '号码': str(balls), '斜率': round(slope, 1), '诊断': tag})
    df_red_group = pd.DataFrame(red_group).sort_values(by='斜率', ascending=False)

    # 3. 蓝球单兵
    blue_single = []
    for b in range(1, 17):
        s = get_energy(df, [b], 'blue')
        s10 = calc_slope(s, 5); s3 = calc_slope(s, 3)
        ma5 = s.rolling(5).mean().iloc[-1]; ma10 = s.rolling(10).mean().iloc[-1]
        curr = s.iloc[-1]
        
        tag = "☠️深渊"
        if curr > ma5 and curr > ma10: tag = "🔥皇冠"
        elif curr > ma5 and curr <= ma10: tag = "💰回踩"
        elif curr <= ma5 and curr > ma10: tag = "🚀启动"
        
        blue_single.append({'号码': f"{b:02d}", '10期': round(s10, 1), '3期': round(s3, 1), '诊断': tag})
    df_blue_single = pd.DataFrame(blue_single).sort_values(by='10期', ascending=False)

    # 4. 蓝球分组
    blue_group = []
    for name, balls in BLUE_GROUPS.items():
        s = get_energy(df, balls, 'blue')
        slope = calc_slope(s, 5)
        tag = "🔥拉升" if slope > 1 else ("🚀启动" if slope > 0 else "☠️下跌")
        blue_group.append({'组合': name, '斜率': round(slope, 1), '诊断': tag})
    df_blue_group = pd.DataFrame(blue_group).sort_values(by='斜率', ascending=False)

    return df_red_single, df_red_group, df_blue_single, df_blue_group

# --- 生成 HTML 报告 ---
def df_to_html(df, title, limit=None):
    if limit: df = df.head(limit)
    html = f"<h4>{title}</h4>"
    html += "<table border='1' style='border-collapse: collapse; width: 100%; font-size: 12px; text-align: center;'>"
    html += "<tr style='background-color: #f2f2f2;'>" + "".join([f"<th>{c}</th>" for c in df.columns]) + "</tr>"
    for _, row in df.iterrows():
        color = "black"
        if "🔥" in str(row.values): color = "red"
        elif "💰" in str(row.values): color = "orange"
        elif "☠️" in str(row.values): color = "gray"
        
        html += f"<tr style='color: {color};'>" + "".join([f"<td>{v}</td>" for v in row.values]) + "</tr>"
    html += "</table>"
    return html

def logic_deduction(r_s, r_g, b_s, b_g):
    # 逻辑推演文本生成
    log = "<h3>🧠 极客逻辑推演 (Step-by-Step)</h3>"
    
    # 红球推演
    log += "<b>1. 红球交叉验证：</b><br>"
    top_r_single = r_s.iloc[0]['号码']
    top_r_group_name = r_g.iloc[0]['代号']
    top_r_group_balls = r_g.iloc[0]['号码']
    
    log += f"• <b>单兵雷达：</b>显示 {top_r_single} 号斜率最高，动能最强。<br>"
    log += f"• <b>集团军：</b>显示 {top_r_group_name} {top_r_group_balls} 是第一梯队。<br>"
    
    # 找交集
    hot_list = r_s[r_s['诊断'].str.contains("🔥")]['号码'].tolist()[:6]
    group_hot = eval(top_r_group_balls)
    intersection = [f"{x:02d}" for x in group_hot if f"{x:02d}" in hot_list]
    
    if intersection:
        log += f"• <b>👉 结论：</b>单兵与集团在 <b>{intersection}</b> 发生共振，确认为铁胆！<br>"
    else:
        log += f"• <b>👉 结论：</b>单兵与集团分化，优先跟随单兵王 <b>{top_r_single}</b>。<br>"

    # 蓝球推演
    log += "<br><b>2. 蓝球趋势研判：</b><br>"
    top_b = b_s.iloc[0]['号码']
    top_bg = b_g.iloc[0]['组合']
    
    log += f"• <b>斜率王：</b>{top_b} 号（数据第一）。<br>"
    log += f"• <b>冠军组：</b>{top_bg}。<br>"
    log += "• <b>👉 策略：</b>直接锁定单兵王与冠军组的交集。<br>"
    
    return log, hot_list, top_b, intersection

def generate_final_strategy(hot_reds, top_blue, intersection):
    # 构建 ABC 方案
    # A: 强攻 (单兵前6)
    plan_a = hot_reds[:6]
    
    # B: 互补 (交集 + 黄金回踩)
    # 这里简化：取交集 + 单兵前列补齐
    plan_b = intersection + [x for x in hot_reds if x not in intersection]
    plan_b = sorted(list(set(plan_b[:7]))) # 7个号
    
    # C: 胆拖
    bankers = intersection if intersection else hot_reds[:2]
    drags = [x for x in hot_reds if x not in bankers][:5]
    
    html = "<h3>🎫 最终出票指令</h3>"
    html += "<div style='background:#fff0f0; padding:8px; border-radius:4px; margin-bottom:5px;'>"
    html += f"<b>【方案A：趋势强攻】(6+1)</b><br>🔴 {','.join(plan_a)} + 🔵 {top_blue}</div>"
    
    html += "<div style='background:#f0f8ff; padding:8px; border-radius:4px; margin-bottom:5px;'>"
    html += f"<b>【方案B：集团防守】(7+1)</b><br>🔴 {','.join(plan_b)} + 🔵 {top_blue}</div>"
    
    html += "<div style='background:#f0fff0; padding:8px; border-radius:4px;'>"
    html += f"<b>【方案C：胆拖狙击】</b><br>🔴 胆:{','.join(bankers)} 拖:{','.join(drags)} + 🔵 {top_blue}</div>"
    
    return html

def push_wechat(title, content):
    if not PUSH_TOKEN: return
    requests.post('http://www.pushplus.plus/send', json={
        "token": PUSH_TOKEN, "title": title, "content": content, "template": "html"
    })

def main():
    print("🚀 启动深度分析引擎...")
    df = update_database()
    if df.empty: return
    last_issue = df['Issue'].iloc[-1]
    
    # 1. 运行四大脚本逻辑
    df_rs, df_rg, df_bs, df_bg = run_analysis(df)
    
    # 2. 生成详细 HTML 报告
    msg = f"<h2>📅 第 {last_issue} 期 · 全维度深度复盘</h2><hr>"
    
    # 插入四个数据表 (限制行数，防止消息过长)
    msg += df_to_html(df_rs, "📊 1. 红球单兵雷达 (Top 10)", limit=10)
    msg += df_to_html(df_rg, "🛡️ 2. 红球集团军 (全览)")
    msg += df_to_html(df_bs, "🔵 3. 蓝球单兵动能 (Top 8)", limit=8)
    msg += df_to_html(df_bg, "⚖️ 4. 蓝球分组战法 (全览)")
    
    # 3. 插入逻辑推演
    logic_text, hot_reds, top_blue, intersect = logic_deduction(df_rs, df_rg, df_bs, df_bg)
    msg += "<hr>" + logic_text
    
    # 4. 插入最终方案
    msg += "<hr>" + generate_final_strategy(hot_reds, top_blue, intersect)
    
    # 5. 推送
    print("分析完成，推送中...")
    push_wechat(f"双色球深度分析-{last_issue}", msg)

if __name__ == "__main__":
    main()
