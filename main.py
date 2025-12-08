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

# --- 1. 数据获取 ---

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

# --- 2. 分析逻辑 ---

def get_energy(df, targets, type='red'):
    prob = 27/33 if type == 'red' else 15/16
    cols = ['R1','R2','R3','R4','R5','R6'] if type == 'red' else ['Blue']
    is_hit = df[cols].isin(targets).any(axis=1) if type == 'red' else df['Blue'].isin(targets)
    scores = []; curr = 0
    for hit in is_hit:
        curr = (curr - (1 - prob)) if hit else (curr + prob * (5 if type=='blue' else 1))
        scores.append(curr)
    return pd.Series(scores)

def calc_slope(series, window=5):
    y = series.tail(window)
    if len(y) < 2: return 0
    try: return np.polyfit(np.arange(len(y)), y, 1)[0] * 10 
    except: return 0

def analyze_raw_data(df):
    # 红球单兵
    red_single = []
    for b in range(1, 34):
        s = get_energy(df, [b], 'red')
        ma5 = s.rolling(5).mean().iloc[-1]
        ma10 = s.rolling(10).mean().iloc[-1]
        curr = s.iloc[-1]
        slope = calc_slope(s, 5)
        tag = '☠️双杀'
        if curr > ma5 and curr > ma10: tag = '🔥共振'
        elif curr > ma5 and curr <= ma10: tag = '💰回踩'
        elif curr <= ma5 and curr > ma10: tag = '✨反转'
        red_single.append({'b': b, 's': slope, 'tag': tag})
    
    # 红球分组
    red_groups = []
    for k, v in RED_GROUPS.items():
        s = get_energy(df, v, 'red')
        red_groups.append({'name': k, 'balls': v, 's': calc_slope(s, 10)})
    red_groups.sort(key=lambda x: x['s'], reverse=True)
        
    # 蓝球单兵
    blue_single = []
    for b in range(1, 17):
        s = get_energy(df, [b], 'blue')
        blue_single.append({'b': b, 's': calc_slope(s, 5)})
    blue_single.sort(key=lambda x: x['s'], reverse=True)
    
    # 蓝球分组
    blue_groups = []
    for k, v in BLUE_GROUPS.items():
        s = get_energy(df, v, 'blue')
        blue_groups.append({'name': k, 'balls': v, 's': calc_slope(s, 5)})
    blue_groups.sort(key=lambda x: x['s'], reverse=True)
    
    return red_single, red_groups, blue_single, blue_groups

# --- 3. 生成内容 (HTML可视化 + AI指令) ---

def generate_ai_prompt(issue, r_s, r_g, b_s, b_g):
    t = f"【双色球第 {issue} 期量化情报】\n"
    t += "请根据波浪理论手册v3.0，结合以下数据为我制定方案：\n\n"
    t += "=== 1. 红球单兵 (按象限) ===\n"
    for tag in ['🔥共振', '💰回踩', '✨反转', '☠️双杀']:
        items = sorted([x for x in r_s if x['tag'] == tag], key=lambda x: x['s'], reverse=True)
        nums = ", ".join([f"{x['b']:02d}({x['s']:.1f})" for x in items])
        t += f"{tag}: {nums}\n"
    t += "\n=== 2. 红球51魔力分组 (前5强) ===\n"
    for g in r_g[:5]:
        t += f"{g['name']} (斜率{g['s']:.1f}): {g['balls']}\n"
    t += "\n=== 3. 蓝球单兵 (前5强) ===\n"
    top_b = ", ".join([f"{x['b']:02d}({x['s']:.1f})" for x in b_s[:5]])
    t += f"{top_b}\n"
    t += "\n=== 4. 蓝球分组 (前3强) ===\n"
    for g in b_g[:3]:
        t += f"{g['name']} (斜率{g['s']:.1f}): {g['balls']}\n"
    return t

def generate_html_content(issue, last_row, r_s, r_g, b_s, b_g, ai_prompt):
    # 样式定义
    style_card = "background:#fff; border-radius:8px; padding:10px; margin-bottom:15px; box-shadow:0 2px 5px rgba(0,0,0,0.05);"
    style_table = "width:100%; border-collapse:collapse; font-size:12px; text-align:center;"
    style_th = "padding:6px; background:#f0f0f0; border-bottom:1px solid #ddd;"
    style_td = "padding:6px; border-bottom:1px solid #eee;"
    
    # 顶部开奖球
    r_sty = "display:inline-block;width:28px;height:28px;line-height:28px;border-radius:50%;background:#f44336;color:fff;text-align:center;font-weight:bold;margin:2px;"
    b_sty = "display:inline-block;width:28px;height:28px;line-height:28px;border-radius:50%;background:#2196f3;color:fff;text-align:center;font-weight:bold;margin:2px;"
    balls_html = "<div>"
    for i in range(1,7): balls_html += f"<span style='{r_sty}'>{last_row[f'R{i}']:02d}</span>"
    balls_html += f"<span style='{b_sty}'>{last_row['Blue']:02d}</span></div>"

    # 构建红球象限表
    red_table_html = f"<table style='{style_table}'>"
    red_table_html += f"<tr><th style='{style_th}'>象限</th><th style='{style_th}'>号码 (斜率)</th></tr>"
    
    colors = {'🔥共振': '#ffebee', '💰回踩': '#fffde7', '✨反转': '#e8f5e9', '☠️双杀': '#f5f5f5'}
    for tag in ['🔥共振', '💰回踩', '✨反转', '☠️双杀']:
        items = sorted([x for x in r_s if x['tag'] == tag], key=lambda x: x['s'], reverse=True)
        # 将号码格式化，每行显示太多可以换行，这里简单拼接
        nums_str = ""
        for x in items:
            # 高亮斜率 > 2 的优质号码
            s_color = "#d32f2f" if x['s'] > 2 else "#999"
            nums_str += f"<b>{x['b']:02d}</b><span style='color:{s_color};font-size:10px'>({x['s']:.1f})</span> "
        
        red_table_html += f"<tr style='background:{colors[tag]};'><td style='{style_td}width:20%;font-weight:bold;'>{tag}</td><td style='{style_td}text-align:left;'>{nums_str}</td></tr>"
    red_table_html += "</table>"

    # 构建分组表 (前3)
    group_html = f"<div style='font-size:12px; margin-top:5px;'>"
    for g in r_g[:3]:
        group_html += f"<div style='margin-bottom:4px;'><span style='background:#e3f2fd;padding:2px 4px;border-radius:3px;'>{g['name']}</span> <span style='color:#666;'>(S:{g['s']:.1f})</span>: {g['balls']}</div>"
    group_html += "</div>"

    # 构建蓝球表
    blue_html = f"<div style='font-size:12px; margin-top:5px; color:#1565c0;'>"
    top_b = ", ".join([f"<b>{x['b']:02d}</b>({x['s']:.1f})" for x in b_s[:5]])
    blue_html += f"<div>🔥 热号: {top_b}</div>"
    blue_html += f"<div>🛡️ 强组: {b_g[0]['name']} {b_g[0]['balls']}</div>"
    blue_html += "</div>"

    # 最终组装
    html = f"""
    <div style='font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#f4f4f4; padding:10px;'>
        <!-- 头部 -->
        <div style='{style_card} text-align:center;'>
            <h3 style='margin:0 0 10px 0;'>📊 第 {issue} 期情报站</h3>
            {balls_html}
        </div>
        
        <!-- 红球四象限 (核心) -->
        <div style='{style_card}'>
            <h4 style='margin:0 0 8px 0; border-left:4px solid #f44336; padding-left:8px;'>🔴 红球四象限 (波浪)</h4>
            {red_table_html}
        </div>

        <!-- 辅助数据 -->
        <div style='{style_card}'>
            <h4 style='margin:0 0 8px 0; border-left:4px solid #ff9800; padding-left:8px;'>🛡️ 魔力分组 & 🔵 蓝球</h4>
            {group_html}
            <hr style='border:0; border-top:1px dashed #eee; margin:8px 0;'>
            {blue_html}
        </div>
        
        <!-- AI 指令区 -->
        <div style='{style_card} background:#e3f2fd; border:1px solid #bbdefb;'>
            <h4 style='margin:0 0 5px 0; color:#1565c0; text-align:center;'>🤖 AI 分析指令 (长按复制)</h4>
            <p style='font-size:11px; color:#666; text-align:center; margin:0 0 5px 0;'>👇 发送给 AI 制定最终方案</p>
            <textarea id="ai-prompt" style="width:100%; height:150px; font-size:11px; padding:5px; border:1px solid #90caf9; border-radius:5px; font-family:monospace; resize:none;">{ai_prompt}</textarea>
        </div>
    </div>
    """
    return html

def save_web_file(html_content, issue):
    if not os.path.exists("public"): os.makedirs("public")
    full_html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>第 {issue} 期 AI 情报</title></head><body style="margin:0;padding:0;background:#f4f4f4;">{html_content}</body></html>"""
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(full_html)

def main():
    print("🚀 启动 v12.0 (完美展示版)...")
    df = update_database()
    if df is None or df.empty: return
    
    last_row = df.iloc[-1]
    issue = int(last_row['Issue'])
    
    # 1. 计算所有数据
    r_s, r_g, b_s, b_g = analyze_raw_data(df)
    
    # 2. 生成纯文本指令
    ai_prompt = generate_ai_prompt(issue, r_s, r_g, b_s, b_g)
    
    # 3. 生成可视化 HTML (传入所有原始数据用于绘表)
    html_msg = generate_html_content(issue, last_row, r_s, r_g, b_s, b_g, ai_prompt)
    
    # 4. 保存与推送
    save_web_file(html_msg, issue)
    
    if PUSH_TOKEN:
        try:
            requests.post('http://www.pushplus.plus/send', json={
                "token": PUSH_TOKEN, 
                "title": f"📈 第 {issue} 期量化情报", 
                "content": html_msg, 
                "template": "html"
            })
            print("✅ 推送成功")
        except Exception as e: print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    main()
