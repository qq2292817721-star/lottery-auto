import pandas as pd
import numpy as np
import requests
import os
import re
from io import StringIO

# ================= 配置区 =================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
CSV_FILE = "ssq.csv"

# 手动输入参数 (GitHub Actions)
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

# --- 1. 数据获取模块 (手动 + 必应) ---

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

# --- 2. 核心计算逻辑 ---

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
    """只计算数据，不给建议"""
    # 1. 红球单兵 (四象限)
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
    
    # 2. 51魔力分组
    red_groups = []
    for k, v in RED_GROUPS.items():
        s = get_energy(df, v, 'red')
        slope = calc_slope(s, 10) # 集团军看10期趋势
        red_groups.append({'name': k, 'balls': v, 's': slope})
    red_groups.sort(key=lambda x: x['s'], reverse=True)
        
    # 3. 蓝球单兵
    blue_single = []
    for b in range(1, 17):
        s = get_energy(df, [b], 'blue')
        blue_single.append({'b': b, 's': calc_slope(s, 5)})
    blue_single.sort(key=lambda x: x['s'], reverse=True)
    
    # 4. 蓝球分组
    blue_groups = []
    for k, v in BLUE_GROUPS.items():
        s = get_energy(df, v, 'blue')
        blue_groups.append({'name': k, 'balls': v, 's': calc_slope(s, 5)})
    blue_groups.sort(key=lambda x: x['s'], reverse=True)
    
    return red_single, red_groups, blue_single, blue_groups

# --- 3. 生成 AI 专用提示词 (Prompt) ---
def generate_ai_prompt(issue, r_s, r_g, b_s, b_g):
    t = f"【双色球第 {issue} 期量化情报】\n"
    t += "请根据波浪理论手册v3.0，结合以下数据为我制定方案：\n\n"
    
    t += "=== 1. 红球单兵 (按象限) ===\n"
    # 按象限分组输出
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

# --- 4. 生成 HTML 推送 (带一键复制) ---
def generate_html_msg(issue, last_row, ai_prompt):
    # 开奖球展示
    r_sty = "display:inline-block;width:25px;height:25px;line-height:25px;border-radius:50%;background:#f44336;color:fff;text-align:center;font-weight:bold;margin:2px;"
    b_sty = "display:inline-block;width:25px;height:25px;line-height:25px;border-radius:50%;background:#2196f3;color:fff;text-align:center;font-weight:bold;margin:2px;"
    balls_html = "<div>"
    for i in range(1,7): balls_html += f"<span style='{r_sty}'>{last_row[f'R{i}']:02d}</span>"
    balls_html += f"<span style='{b_sty}'>{last_row['Blue']:02d}</span></div>"

    html = f"""
    <div style='font-family:sans-serif;'>
        <div style='background:#eee;padding:10px;border-radius:8px;text-align:center;'>
            <h3 style='margin:0;'>📊 第 {issue} 期情报站</h3>
            {balls_html}
        </div>
        
        <div style='margin-top:15px;border:2px dashed #2196f3;padding:10px;border-radius:8px;background:#e3f2fd;'>
            <h4 style='margin:0;color:#1565c0;text-align:center;'>📋 AI 分析指令 (长按复制)</h4>
            <p style='font-size:12px;color:#666;text-align:center;margin:5px 0;'>👇 将下方内容发送给 AI 进行决策</p>
            <textarea id="ai-prompt" style="width:100%;height:300px;font-size:12px;padding:5px;border:1px solid #90caf9;border-radius:5px;font-family:monospace;">{ai_prompt}</textarea>
        </div>
        
        <div style='text-align:center;margin-top:10px;'>
            <p style='font-size:12px;color:#999;'>GitHub Actions 生成 | 波浪理论 v3.0 数据源</p>
        </div>
    </div>
    """
    return html

def main():
    print("🚀 启动 v11.0 (侦察兵版)...")
    df = update_database()
    if df is None or df.empty: return
    
    last_row = df.iloc[-1]
    issue = int(last_row['Issue'])
    print(f"✅ 数据期号: {issue}")
    
    # 1. 计算核心数据
    r_s, r_g, b_s, b_g = analyze_raw_data(df)
    
    # 2. 生成 AI Prompt 文本
    ai_prompt = generate_ai_prompt(issue, r_s, r_g, b_s, b_g)
    
    # 3. 生成 HTML 战报
    html_msg = generate_html_msg(issue, last_row, ai_prompt)
    
    # 4. 推送
    if PUSH_TOKEN:
        try:
            requests.post('http://www.pushplus.plus/send', json={
                "token": PUSH_TOKEN, 
                "title": f"📈 第 {issue} 期量化情报 (请复制给AI)", 
                "content": html_msg, 
                "template": "html"
            })
            print("✅ 推送成功")
        except Exception as e: print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    main()
