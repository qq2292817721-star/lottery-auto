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

# 红球 51 魔力分组
RED_GROUPS = {
    'G01': [1, 19, 31], 'G02': [2, 21, 28], 'G03': [3, 22, 26],
    'G04': [4, 23, 24], 'G05': [5, 16, 30], 'G06': [6, 12, 33],
    'G07': [7, 15, 29], 'G08': [8, 18, 25], 'G09': [9, 10, 32],
    'G10': [11, 13, 27], 'G11': [14, 17, 20]
}
# 蓝球 17 互补分组
BLUE_GROUPS = {
    'G1(01+16)': [1, 16], 'G2(02+15)': [2, 15], 'G3(03+14)': [3, 14],
    'G4(04+13)': [4, 13], 'G5(05+12)': [5, 12], 'G6(06+11)': [6, 11],
    'G7(07+10)': [7, 10], 'G8(08+09)': [8, 9]
}

def get_headers():
    return {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}

# --- 1. 数据获取模块 (保持稳定) ---

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

# --- 2. 核心算法移植 (完全复刻你的本地脚本逻辑) ---

def calc_slope_poly(series, window):
    """通用斜率计算: 拟合最后 window 期的线性趋势"""
    y = series.tail(window)
    if len(y) < 2: return 0
    try: return np.polyfit(np.arange(len(y)), y, 1)[0] * 10 
    except: return 0

# A. 红球单兵 (ssq_dual_scan.py)
def analyze_red_single(df):
    results = []
    cols = ['R1','R2','R3','R4','R5','R6']
    
    for ball in range(1, 34):
        # 能量计算：中奖+miss_prob，未中-hit_prob
        prob_hit = 6/33; prob_miss = 27/33
        is_hit = df[cols].isin([ball]).any(axis=1)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += prob_miss
            else: curr -= prob_hit
            scores.append(curr)
        
        s_series = pd.Series(scores)
        ma5 = s_series.rolling(5).mean().iloc[-1]
        ma10 = s_series.rolling(10).mean().iloc[-1] # 注意：脚本里微观虽然是3期K线，但判断用的是MA10
        curr_val = s_series.iloc[-1]
        
        # 斜率
        slope_10 = calc_slope_poly(s_series, 5) # 10期看MA5斜率
        
        # 判定
        above_ma5 = curr_val > ma5
        above_ma10 = curr_val > ma10
        
        tag = "☠️双杀"
        if above_ma5:
            if above_ma10: tag = "🔥共振"
            else: tag = "💰回踩"
        else:
            if above_ma10: tag = "✨反转"
            
        results.append({'ball': ball, 's': slope_10, 'tag': tag})
    return results

# B. 红球分组 (ssq_red_groups.py)
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
        slope = calc_slope_poly(s_series, 20) # 脚本逻辑：看最近20期
        ma = s_series.rolling(10).mean().iloc[-1]
        last_val = s_series.iloc[-1]
        above_ma = last_val > ma
        
        tag = "☠️弱势"
        if above_ma:
            if slope > 2: tag = "🔥冲锋"
            elif slope > 0: tag = "📈稳升"
            else: tag = "⚠️滞涨"
        else:
            if slope > 0.5: tag = "🚀复苏"
            
        results.append({'name': name, 'balls': str(balls), 's': slope, 'tag': tag})
    
    # 按斜率排序
    results.sort(key=lambda x: x['s'], reverse=True)
    return results

# C. 蓝球单兵 (ssq_blue_scan.py)
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
        slope_10 = calc_slope_poly(s_series, 5) # 看最近5个点拟合
        ma5 = s_series.rolling(5).mean().iloc[-1]
        ma10 = s_series.rolling(10).mean().iloc[-1]
        curr_val = s_series.iloc[-1]
        
        above_ma5 = curr_val > ma5
        above_ma10 = curr_val > ma10
        
        tag = "☠️深渊"
        if above_ma5:
            if above_ma10: tag = "🔥皇冠"
            else: tag = "💰回踩"
        else:
            if above_ma10: tag = "🚀启动"
            
        results.append({'ball': ball, 's': slope_10, 'tag': tag})
    
    results.sort(key=lambda x: x['s'], reverse=True)
    return results

# D. 蓝球分组 (ssq_blue_groups.py)
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
        last_val = s_series.iloc[-1]
        above_ma = last_val > ma
        
        tag = "☠️下跌"
        if above_ma:
            if slope > 1: tag = "🔥拉升"
            else: tag = "⚠️震荡"
        else:
            if slope > 0: tag = "🚀启动"
            
        results.append({'name': name, 'balls': str(balls), 's': slope, 'tag': tag})
        
    results.sort(key=lambda x: x['s'], reverse=True)
    return results

# --- 3. 生成全景 HTML 报表 ---

def build_full_report(issue, last_row, r_s, r_g, b_s, b_g):
    # 样式
    card_style = "background:#fff; border-radius:8px; padding:12px; margin-bottom:15px; box-shadow:0 1px 3px rgba(0,0,0,0.1);"
    table_style = "width:100%; border-collapse:collapse; font-size:11px; text-align:center;"
    th_style = "background:#f5f5f5; padding:5px; border-bottom:1px solid #ddd; color:#666;"
    td_style = "padding:5px; border-bottom:1px solid #eee;"
    
    # 1. 头部
    r_ball = "".join([f"<span style='display:inline-block;width:24px;height:24px;line-height:24px;background:#f44336;color:#fff;border-radius:50%;margin:1px;'>{last_row[f'R{i}']:02d}</span>" for i in range(1,7)])
    b_ball = f"<span style='display:inline-block;width:24px;height:24px;line-height:24px;background:#2196f3;color:#fff;border-radius:50%;margin:1px;'>{last_row['Blue']:02d}</span>"
    
    html = f"""
    <div style='font-family:sans-serif; background:#f0f2f5; padding:10px;'>
        <div style='{card_style} text-align:center;'>
            <h3 style='margin:0 0 5px 0;'>📊 第 {issue} 期全景数据</h3>
            <div>{r_ball}{b_ball}</div>
        </div>
    """
    
    # 2. 红球四象限 (全量)
    html += f"<div style='{card_style}'><h4 style='margin:0 0 10px 0; border-left:4px solid #f44336; padding-left:8px;'>🔴 红球单兵 (全33码)</h4>"
    html += f"<table style='{table_style}'>"
    html += f"<tr><th style='{th_style}'>象限</th><th style='{th_style}'>号码 (斜率)</th></tr>"
    
    # 按固定顺序展示：共振 -> 回踩 -> 反转 -> 双杀
    quadrants = ['🔥共振', '💰回踩', '✨反转', '☠️双杀']
    bg_colors = {'🔥共振': '#ffebee', '💰回踩': '#fffde7', '✨反转': '#e8f5e9', '☠️双杀': '#fafafa'}
    
    for q in quadrants:
        items = sorted([x for x in r_s if x['tag'] == q], key=lambda x: x['s'], reverse=True)
        nums_str = ""
        for x in items:
            color = "#d32f2f" if x['s'] > 2 else "#333"
            nums_str += f"<span style='color:{color}'><b>{x['ball']:02d}</b>({x['s']:.1f})</span> "
        if not nums_str: nums_str = "<span style='color:#ccc'>无</span>"
        
        html += f"<tr style='background:{bg_colors[q]};'><td style='{td_style} width:15%; font-weight:bold;'>{q}</td><td style='{td_style} text-align:left;'>{nums_str}</td></tr>"
    html += "</table></div>"
    
    # 3. 红球分组 (全量)
    html += f"<div style='{card_style}'><h4 style='margin:0 0 10px 0; border-left:4px solid #ff9800; padding-left:8px;'>🛡️ 51魔力分组 (全11组)</h4>"
    html += f"<table style='{table_style}'>"
    html += f"<tr><th style='{th_style}'>组名</th><th style='{th_style}'>趋势</th><th style='{th_style}'>斜率</th><th style='{th_style}'>包含号码</th></tr>"
    for g in r_g:
        html += f"<tr><td style='{td_style}'><b>{g['name']}</b></td><td style='{td_style}'>{g['tag']}</td><td style='{td_style}'>{g['s']:.1f}</td><td style='{td_style} font-size:10px; color:#666;'>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # 4. 蓝球单兵 (全量)
    html += f"<div style='{card_style}'><h4 style='margin:0 0 10px 0; border-left:4px solid #2196f3; padding-left:8px;'>🔵 蓝球单兵 (全16码)</h4>"
    # 为了节省空间，用流式布局
    html += "<div style='display:flex; flex-wrap:wrap; gap:5px;'>"
    for b in b_s:
        bg = "#e3f2fd" if "🔥" in b['tag'] else ("#fff" if "☠️" in b['tag'] else "#f5f5f5")
        border = "2px solid #2196f3" if "🔥" in b['tag'] else "1px solid #ddd"
        html += f"<div style='background:{bg}; border:{border}; border-radius:4px; padding:4px; width:45%; flex-grow:1; text-align:center; font-size:12px;'>"
        html += f"<b>{b['ball']:02d}</b> <span style='color:#666'>S:{b['s']:.1f}</span><br>{b['tag']}"
        html += "</div>"
    html += "</div></div>"
    
    # 5. 蓝球分组 (全量)
    html += f"<div style='{card_style}'><h4 style='margin:0 0 10px 0; border-left:4px solid #3f51b5; padding-left:8px;'>👥 蓝球分组 (全8组)</h4>"
    html += f"<table style='{table_style}'>"
    html += f"<tr><th style='{th_style}'>组名</th><th style='{th_style}'>趋势</th><th style='{th_style}'>斜率</th><th style='{th_style}'>号码</th></tr>"
    for g in b_g:
        html += f"<tr><td style='{td_style}'><b>{g['name']}</b></td><td style='{td_style}'>{g['tag']}</td><td style='{td_style}'>{g['s']:.1f}</td><td style='{td_style}'>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # 6. 底部 AI 复制区 (供你复制给我)
    ai_text = generate_ai_text(issue, r_s, r_g, b_s, b_g)
    html += f"<div style='{card_style} background:#e8eaf6; border:1px dashed #3f51b5;'>"
    html += f"<h4 style='margin:0 0 5px 0; text-align:center; color:#303f9f;'>🤖 AI 决策数据包 (长按复制)</h4>"
    html += f"<textarea id='ai-data' style='width:100%; height:100px; font-size:10px; border:1px solid #c5cae9; padding:5px; resize:none;'>{ai_text}</textarea>"
    html += "</div></div>"
    
    return html

def generate_ai_text(issue, r_s, r_g, b_s, b_g):
    t = f"【第{issue}期 全量数据报告】\n"
    t += "1.红球四象限:\n"
    for q in ['🔥共振', '💰回踩', '✨反转', '☠️双杀']:
        items = [f"{x['ball']:02d}({x['s']:.1f})" for x in r_s if x['tag']==q]
        t += f"{q}: {', '.join(items)}\n"
    t += "\n2.红球分组:\n"
    for g in r_g: t += f"{g['name']} {g['tag']} (S:{g['s']:.1f}): {g['balls']}\n"
    t += "\n3.蓝球单兵:\n"
    for b in b_s: t += f"{b['ball']:02d} {b['tag']} (S:{b['s']:.1f})\n"
    t += "\n4.蓝球分组:\n"
    for g in b_g: t += f"{g['name']} {g['tag']} (S:{g['s']:.1f})\n"
    return t

def save_web_file(html_content, issue):
    if not os.path.exists("public"): os.makedirs("public")
    full_html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>第{issue}期全景数据</title></head><body style="margin:0;padding:0;">{html_content}</body></html>"""
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(full_html)

# --- 主程序 ---

def main():
    print("🚀 启动 v13.0 全景数据版...")
    df = update_database()
    if df is None or df.empty: return
    
    last_row = df.iloc[-1]
    issue = int(last_row['Issue'])
    print(f"✅ 处理期号: {issue}")
    
    # 1. 全量计算
    r_s = analyze_red_single(df)
    r_g = analyze_red_groups(df)
    b_s = analyze_blue_single(df)
    b_g = analyze_blue_groups(df)
    
    # 2. 生成报表
    html_msg = build_full_report(issue, last_row, r_s, r_g, b_s, b_g)
    
    # 3. 保存与推送
    save_web_file(html_msg, issue)
    
    if PUSH_TOKEN:
        try:
            requests.post('http://www.pushplus.plus/send', json={
                "token": PUSH_TOKEN, 
                "title": f"📊 第 {issue} 期全景数据报表", 
                "content": html_msg, 
                "template": "html"
            })
            print("✅ 推送成功")
        except Exception as e: print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    main()
