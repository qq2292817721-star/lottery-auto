import pandas as pd
import numpy as np
import requests
import os
import re

# ================= 配置区 =================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
CSV_FILE = "ssq.csv"

# 手动输入参数
MANUAL_ISSUE_ENV = os.environ.get("MANUAL_ISSUE", "")
MANUAL_RED_ENV = os.environ.get("MANUAL_RED", "") 
MANUAL_BLUE_ENV = os.environ.get("MANUAL_BLUE", "")

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

def get_headers():
    return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}

# --- 1. 数据获取模块 ---

def get_manual_data():
    if MANUAL_ISSUE_ENV and MANUAL_RED_ENV and MANUAL_BLUE_ENV:
        try:
            issue = int(MANUAL_ISSUE_ENV)
            reds = [int(x.strip()) for x in MANUAL_RED_ENV.replace('，',',').split(',')]
            blue = int(MANUAL_BLUE_ENV)
            if len(reds) == 6:
                return pd.DataFrame([[issue]+reds+[blue]], columns=['Issue','R1','R2','R3','R4','R5','R6','Blue'])
        except: pass
    return None

def fetch_bing_search(target_issue):
    url = f"https://www.bing.com/search?q=双色球+{target_issue}+开奖结果"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        nums = re.findall(r'\b([0-3]?[0-9])\b', r.text[:5000])
        valid_nums = [int(n) for n in nums]
        for i in range(len(valid_nums)-7):
            chunk = valid_nums[i:i+7]
            if len(set(chunk[:6]))==6 and all(x<=33 for x in chunk[:6]) and chunk[6]<=16:
                return pd.DataFrame([[target_issue]+chunk], columns=['Issue','R1','R2','R3','R4','R5','R6','Blue'])
    except: pass
    return None

def get_web_data(local_issue):
    manual = get_manual_data()
    if manual is not None: return manual
    return fetch_bing_search(local_issue + 1)

def update_database():
    df_local = pd.DataFrame()
    last_issue = 2025000
    if os.path.exists(CSV_FILE):
        try: 
            df_local = pd.read_csv(CSV_FILE)
            if not df_local.empty: last_issue = int(df_local['Issue'].iloc[-1])
        except: pass
    
    df_new = get_web_data(last_issue)
    if df_new is not None and not df_new.empty:
        new_issue = int(df_new.iloc[0]['Issue'])
        if new_issue > last_issue:
            if not df_local.empty:
                df_final = pd.concat([df_local, df_new]).drop_duplicates(subset=['Issue'], keep='last')
            else: df_final = df_new
            df_final.sort_values(by='Issue').to_csv(CSV_FILE, index=False, encoding='utf-8')
            return df_final
    return df_local

# --- 2. 核心算法 (完全复刻脚本逻辑) ---

def calc_slope_poly(series, window):
    y = series.tail(window)
    if len(y) < 2: return 0
    try: return np.polyfit(np.arange(len(y)), y, 1)[0] * 10 
    except: return 0

def get_kline_closes(scores, period):
    """模拟K线聚合，返回收盘价序列"""
    closes = []
    for i in range(0, len(scores), period):
        chunk = scores[i : i+period]
        if chunk: closes.append(chunk[-1])
    return pd.Series(closes)

# A. 红球单兵 (含 S10 和 S3)
def analyze_red_single(df):
    results = []
    cols = ['R1','R2','R3','R4','R5','R6']
    
    for ball in range(1, 34):
        # 1. 原始能量流
        prob_hit = 6/33; prob_miss = 27/33
        is_hit = df[cols].isin([ball]).any(axis=1)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += prob_miss
            else: curr -= prob_hit
            scores.append(curr)
        
        # 2. 宏观 (10期K线)
        s_closes_10 = get_kline_closes(scores, 10)
        slope_10 = calc_slope_poly(s_closes_10, 5) # 10期K线看MA5斜率
        
        # 3. 微观 (3期K线)
        s_closes_3 = get_kline_closes(scores, 3)
        slope_3 = calc_slope_poly(s_closes_3, 10) # 3期K线看MA10斜率
        
        # 4. 状态判定 (用原始分数的MA)
        s_raw = pd.Series(scores)
        ma5 = s_raw.rolling(5).mean().iloc[-1]
        ma10 = s_raw.rolling(10).mean().iloc[-1]
        curr_val = s_raw.iloc[-1]
        
        tag = "☠️双杀"
        if curr_val > ma5:
            if curr_val > ma10: tag = "🔥共振"
            else: tag = "💰回踩"
        else:
            if curr_val > ma10: tag = "✨反转"
            
        results.append({'ball': ball, 's10': slope_10, 's3': slope_3, 'tag': tag})
    
    # 默认按 S10 宏观斜率排序
    results.sort(key=lambda x: x['s10'], reverse=True)
    return results

# B. 红球分组
def analyze_red_groups(df):
    results = []
    cols = ['R1','R2','R3','R4','R5','R6']
    for name, balls in RED_GROUPS.items():
        scores = []; curr = 0
        for i in range(len(df)):
            row = df.iloc[i][cols]
            hits = len(set(balls) & set(row))
            if hits > 0: curr += (hits * 5) - 3
            else: curr -= 1
            scores.append(curr)
        
        s_series = pd.Series(scores)
        slope = calc_slope_poly(s_series, 20)
        ma = s_series.rolling(10).mean().iloc[-1]
        tag = "🔥冲锋" if s_series.iloc[-1] > ma else "☠️弱势"
        results.append({'name': name, 'balls': str(balls), 's': slope, 'tag': tag})
    
    results.sort(key=lambda x: x['s'], reverse=True)
    return results

# C. 蓝球单兵
def analyze_blue_single(df):
    results = []
    prob_hit = 1/16; prob_miss = 15/16
    for ball in range(1, 17):
        is_hit = (df['Blue'] == ball)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += prob_miss * 5
            else: curr -= prob_hit
            scores.append(curr)
        
        s_series = pd.Series(scores)
        slope = calc_slope_poly(s_series, 5)
        ma5 = s_series.rolling(5).mean().iloc[-1]
        tag = "🔥皇冠" if s_series.iloc[-1] > ma5 else "☠️深渊"
        results.append({'ball': ball, 's': slope, 'tag': tag})
    
    results.sort(key=lambda x: x['s'], reverse=True)
    return results

# D. 蓝球分组
def analyze_blue_groups(df):
    results = []
    prob_hit = 1/8; prob_miss = 7/8
    for name, balls in BLUE_GROUPS.items():
        is_hit = df['Blue'].isin(balls)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += prob_miss * 2
            else: curr -= prob_hit
            scores.append(curr)
        
        s_series = pd.Series(scores)
        slope = calc_slope_poly(s_series, 20)
        ma = s_series.rolling(10).mean().iloc[-1]
        tag = "🔥拉升" if s_series.iloc[-1] > ma else "☠️下跌"
        results.append({'name': name, 'balls': str(balls), 's': slope, 'tag': tag})
        
    results.sort(key=lambda x: x['s'], reverse=True)
    return results

# --- 3. 生成全景 HTML 报表 (专业表格版) ---

def build_full_report(issue, last_row, r_s, r_g, b_s, b_g):
    # 样式
    card_style = "background:#fff; border-radius:8px; padding:12px; margin-bottom:15px; box-shadow:0 1px 3px rgba(0,0,0,0.1);"
    table_style = "width:100%; border-collapse:collapse; font-size:12px; text-align:center;"
    th_style = "background:#f0f0f0; padding:6px; border-bottom:2px solid #ddd; color:#333; font-weight:bold;"
    td_style = "padding:6px; border-bottom:1px solid #eee;"
    
    # 1. 头部
    r_ball = "".join([f"<span style='display:inline-block;width:24px;height:24px;line-height:24px;background:#f44336;color:#fff;border-radius:50%;margin:1px;'>{last_row[f'R{i}']:02d}</span>" for i in range(1,7)])
    b_ball = f"<span style='display:inline-block;width:24px;height:24px;line-height:24px;background:#2196f3;color:#fff;border-radius:50%;margin:1px;'>{last_row['Blue']:02d}</span>"
    
    html = f"""
    <div style='font-family:-apple-system, sans-serif; background:#f0f2f5; padding:10px;'>
        <div style='{card_style} text-align:center;'>
            <h3 style='margin:0 0 5px 0;'>📊 第 {issue} 期全景数据</h3>
            <div>{r_ball}{b_ball}</div>
        </div>
    """
    
    # 2. 红球单兵 (专业数据表)
    html += f"<div style='{card_style}'>"
    html += f"<h4 style='margin:0 0 10px 0; border-left:4px solid #f44336; padding-left:8px;'>🔴 红球单兵 (双斜率分析)</h4>"
    html += f"<table style='{table_style}'>"
    html += f"<tr><th style='{th_style}'>号</th><th style='{th_style}'>S10(宏)</th><th style='{th_style}'>S3(微)</th><th style='{th_style}'>状态</th></tr>"
    
    for row in r_s:
        # 颜色逻辑
        bg_color = "#fff"
        if "🔥" in row['tag']: bg_color = "#ffebee" # 共振红
        elif "💰" in row['tag']: bg_color = "#fffde7" # 回踩黄
        
        # 斜率颜色: 正数为红，负数为绿
        s10_color = "#d32f2f" if row['s10'] > 0 else "#388e3c"
        s3_color = "#d32f2f" if row['s3'] > 0 else "#388e3c"
        
        # 只有 S10 > -5 的才显示，太差的就折叠? 不，全量显示，但太长的可以不在此处
        # 为了美观，全量显示
        
        html += f"<tr style='background:{bg_color};'>"
        html += f"<td style='{td_style} font-weight:bold;'>{row['ball']:02d}</td>"
        html += f"<td style='{td_style} color:{s10_color};'>{row['s10']:.1f}</td>"
        html += f"<td style='{td_style} color:{s3_color};'>{row['s3']:.1f}</td>"
        html += f"<td style='{td_style} font-size:10px;'>{row['tag']}</td>"
        html += "</tr>"
        
    html += "</table></div>"
    
    # 3. 红球分组
    html += f"<div style='{card_style}'><h4 style='margin:0 0 10px 0; border-left:4px solid #ff9800; padding-left:8px;'>🛡️ 魔力51分组 (Top 5)</h4>"
    html += f"<table style='{table_style}'>"
    html += f"<tr><th style='{th_style}'>组名</th><th style='{th_style}'>斜率</th><th style='{th_style}'>号码</th></tr>"
    for g in r_g[:5]:
        html += f"<tr><td style='{td_style}'><b>{g['name']}</b></td><td style='{td_style} color:#d32f2f;'>{g['s']:.1f}</td><td style='{td_style} font-size:10px; color:#666;'>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # 4. 蓝球数据 (并排布局)
    html += f"<div style='{card_style}'><h4 style='margin:0 0 10px 0; border-left:4px solid #2196f3; padding-left:8px;'>🔵 蓝球数据 (单兵+分组)</h4>"
    
    html += f"<div style='margin-bottom:10px;'><b>🔥 单兵前3名:</b><br>"
    for b in b_s[:3]:
        html += f"<span style='background:#e3f2fd; padding:3px 6px; border-radius:4px; margin-right:5px; font-size:12px;'><b>{b['ball']:02d}</b> (S:{b['s']:.1f})</span>"
    html += "</div>"
    
    html += f"<div><b>👥 强组前2名:</b><br>"
    for g in b_g[:2]:
        html += f"<div style='font-size:11px; color:#666;'>{g['name']} (S:{g['s']:.1f})</div>"
    html += "</div></div>"
    
    # 5. AI 复制区
    ai_text = generate_ai_text(issue, r_s, r_g, b_s, b_g)
    html += f"<div style='{card_style} background:#e8eaf6; border:1px dashed #3f51b5;'>"
    html += f"<h4 style='margin:0 0 5px 0; text-align:center; color:#303f9f;'>🤖 AI 决策数据包 (长按复制)</h4>"
    html += f"<textarea id='ai-data' style='width:100%; height:80px; font-size:10px; border:1px solid #c5cae9; padding:5px; resize:none;'>{ai_text}</textarea>"
    html += "</div></div>"
    
    return html

def generate_ai_text(issue, r_s, r_g, b_s, b_g):
    t = f"【第{issue}期 全量数据】\n"
    t += "1.红球详细数据(号,S10,S3,态):\n"
    # 为了AI读取方便，用简洁格式
    for row in r_s:
        t += f"{row['ball']:02d},{row['s10']:.1f},{row['s3']:.1f},{row['tag']} | "
    t += "\n\n2.红球分组(前5):\n"
    for g in r_g[:5]: t += f"{g['name']}(S:{g['s']:.1f}):{g['balls']}\n"
    t += "\n3.蓝球单兵(前5):\n"
    for b in b_s[:5]: t += f"{b['ball']:02d}(S:{b['s']:.1f})\n"
    t += "\n4.蓝球分组(前3):\n"
    for g in b_g[:3]: t += f"{g['name']}(S:{g['s']:.1f})\n"
    return t

def save_web_file(html_content, issue):
    if not os.path.exists("public"): os.makedirs("public")
    full_html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>第{issue}期报表</title></head><body style="margin:0;padding:0;">{html_content}</body></html>"""
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(full_html)

# --- 主程序 ---

def main():
    print("🚀 启动 v13.1 (表格增强版)...")
    df = update_database()
    if df is None or df.empty: return
    
    last_row = df.iloc[-1]
    issue = int(last_row['Issue'])
    
    r_s = analyze_red_single(df)
    r_g = analyze_red_groups(df)
    b_s = analyze_blue_single(df)
    b_g = analyze_blue_groups(df)
    
    html_msg = build_full_report(issue, last_row, r_s, r_g, b_s, b_g)
    save_web_file(html_msg, issue)
    
    if PUSH_TOKEN:
        try:
            requests.post('http://www.pushplus.plus/send', json={
                "token": PUSH_TOKEN, 
                "title": f"📊 第 {issue} 期专业战报", 
                "content": html_msg, 
                "template": "html"
            })
            print("✅ 推送成功")
        except Exception as e: print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    main()
