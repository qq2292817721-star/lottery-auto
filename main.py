import pandas as pd
import numpy as np
import requests
import os
import re
import sys

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
        r = requests.get(url, headers=get_headers())
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

# --- 2. 核心算法 ---

def get_kline_dataframe(scores, period):
    ohlc = []
    for i in range(0, len(scores), period):
        chunk = scores[i : i+period]
        if not chunk: continue
        prev = scores[i-1] if i > 0 else 0
        chunk_max = max(chunk); chunk_min = min(chunk)
        real_high = max(prev, chunk_max); real_low = min(prev, chunk_min)
        ohlc.append([prev, real_high, real_low, chunk[-1]])
    return pd.DataFrame(ohlc, columns=['Open', 'High', 'Low', 'Close'])

def analyze_trend_from_kline(df_kline, ma_window):
    df_kline['MA'] = df_kline['Close'].rolling(ma_window).mean()
    if len(df_kline) < 5: return 0, False
    current_close = df_kline['Close'].iloc[-1]
    current_ma = df_kline['MA'].iloc[-1]
    
    recent = df_kline['Close'].tail(5).round(4)
    x = np.arange(len(recent))
    slope = np.polyfit(x, recent, 1)[0] * 10
    
    return slope, current_close > current_ma

# A. 红球单兵
def analyze_red_single(df):
    results = []
    cols = ['R1','R2','R3','R4','R5','R6']
    df = df.sort_values(by='Issue').reset_index(drop=True)
    for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
    
    for ball in range(1, 34):
        prob_hit = 6/33; prob_miss = 27/33
        is_hit = df[cols].isin([ball]).any(axis=1)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += prob_miss
            else: curr -= prob_hit
            scores.append(round(curr, 4))
        
        df_10 = get_kline_dataframe(scores, 10)
        s10, ma5 = analyze_trend_from_kline(df_10, 5)
        df_3 = get_kline_dataframe(scores, 3)
        s3, ma10 = analyze_trend_from_kline(df_3, 10)
        
        tag = "☠️双杀下跌"; prio = 0
        if ma5:
            if ma10:
                if s3 > 0: tag = "🔥共振加速"; prio = 5
                else: tag = "⚠️上涨中继"; prio = 4
            else:
                if s3 < 0: tag = "💰黄金回踩"; prio = 4.5
                else: tag = "🤔震荡整理"; prio = 3
        else:
            if ma10 and s3 > 2: tag = "✨妖股反转"; prio = 3.5
            elif ma10: tag = "🚀超跌反弹"; prio = 2
            else: tag = "☠️双杀下跌"; prio = 0
            
        results.append({'ball': ball, 's10': s10, 'ma5': ma5, 's3': s3, 'ma10': ma10, 'tag': tag, 'prio': prio})
    
    results.sort(key=lambda x: (x['prio'], x['s3']), reverse=True)
    return results

# B. 红球分组
def analyze_red_groups(df):
    results = []
    cols = ['R1','R2','R3','R4','R5','R6']
    for name, balls in RED_GROUPS.items():
        scores = []; curr = 0
        for i in range(len(df)):
            hits = len(set(balls) & set(df.iloc[i][cols]))
            if hits > 0: curr += (hits * 5) - 3
            else: curr -= 1
            scores.append(curr)
        
        energy_val = scores[-1]
        recent = scores[-20:]
        slope = np.polyfit(np.arange(len(recent)), recent, 1)[0] * 10 if len(recent)>1 else 0
        ma = pd.Series(scores).rolling(10).mean().iloc[-1]
        above_ma = scores[-1] > ma
        
        tag = ""; prio = 0
        if above_ma:
            if slope > 2: tag = "🔥集团冲锋"; prio = 5
            elif slope > 0: tag = "📈稳步上升"; prio = 4
            else: tag = "⚠️高位滞涨"; prio = 3
        else:
            if slope > 0.5: tag = "🚀底部复苏"; prio = 4.5
            else: tag = "☠️弱势群体"; prio = 0
        results.append({'name': name, 'balls': str(balls), 's': slope, 'val': energy_val, 'tag': tag, 'prio': prio})
    results.sort(key=lambda x: (x['prio'], x['s']), reverse=True)
    return results

# C. 蓝球单兵 (表格结构与红球完全一致)
def analyze_blue_single(df):
    results = []
    df = df.sort_values(by='Issue').reset_index(drop=True)
    for ball in range(1, 17):
        is_hit = (df['Blue'] == ball)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += 15/16 * 5
            else: curr -= 1/16
            scores.append(round(curr, 4))
            
        df_10 = get_kline_dataframe(scores, 10)
        s10, ma5 = analyze_trend_from_kline(df_10, 5)
        df_3 = get_kline_dataframe(scores, 3)
        s3, ma10 = analyze_trend_from_kline(df_3, 10)
        
        tag = ""; prio = 0
        if ma5:
            if ma10: tag = "🔥皇冠热号"; prio = 5
            else: tag = "💰黄金回踩"; prio = 4
        else:
            if ma10: tag = "🚀妖股启动"; prio = 4.5
            else: tag = "☠️极寒深渊"; prio = 0
            
        results.append({'ball': ball, 's10': s10, 'ma5': ma5, 's3': s3, 'ma10': ma10, 'tag': tag, 'prio': prio})
    
    # 蓝球依然按优先级 > S3排序
    results.sort(key=lambda x: (x['prio'], x['s3']), reverse=True)
    return results

# D. 蓝球分组
def analyze_blue_groups(df):
    results = []
    for name, balls in BLUE_GROUPS.items():
        is_hit = df['Blue'].isin(balls)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += 7/8 * 2
            else: curr -= 1/8
            scores.append(curr)
        
        energy_val = scores[-1]
        recent = scores[-20:]
        slope = np.polyfit(np.arange(len(recent)), recent, 1)[0] * 10 if len(recent)>1 else 0
        ma = pd.Series(scores).rolling(10).mean().iloc[-1]
        above_ma = scores[-1] > ma
        
        tag = ""; prio = 0
        if above_ma:
            if slope > 1: tag = "🔥强势拉升"; prio = 5
            else: tag = "⚠️高位震荡"; prio = 3
        else:
            if slope > 0: tag = "🚀底部启动"; prio = 4
            else: tag = "☠️下跌通道"; prio = 0
        results.append({'name': name, 'balls': str(balls), 's': slope, 'val': energy_val, 'tag': tag, 'prio': prio})
    results.sort(key=lambda x: (x['prio'], x['s']), reverse=True)
    return results

# --- 3. 生成全景 HTML (表格统一版) ---

def build_compressed_report(issue, last_row, r_s, r_g, b_s, b_g):
    st_t = "width:100%;font-size:11px;text-align:center;border-collapse:collapse;"
    st_th = "background:#eee;padding:4px;border-bottom:1px solid #ccc;white-space:nowrap;"
    st_td = "padding:4px;border-bottom:1px solid #eee;"
    
    r_balls = "".join([f"<b style='color:#f44336;margin:1px'>{last_row[f'R{i}']:02d}</b>" for i in range(1,7)])
    b_ball = f"<b style='color:#2196f3;margin:1px'>{last_row['Blue']:02d}</b>"
    
    html = f"<html><body style='font-family:sans-serif;padding:5px;background:#f9f9f9'>"
    html += f"<div style='background:#fff;padding:10px;border-radius:6px;text-align:center'><h4>第{issue}期 (v20.0)</h4>{r_balls} + {b_ball}</div>"
    
    # 1. 红球单兵
    html += "<div style='background:#fff;padding:8px;margin-top:10px;border-radius:6px'><h4 style='margin:0 0 5px 0;color:#d32f2f'>🔴红球单兵</h4>"
    html += f"<table style='{st_t}'><tr><th>号</th><th>S10</th><th>M5</th><th>S3</th><th>M10</th><th>态</th></tr>"
    for row in r_s:
        c = "#ffebee" if "🔥" in row['tag'] else ("#fffde7" if "💰" in row['tag'] else ("#f5f5f5" if "☠️" in row['tag'] else "#fff"))
        m5 = "√" if row['ma5'] else "×"; m10 = "√" if row['ma10'] else "×"
        tag = row['tag'].split(' ')[0]
        html += f"<tr style='background:{c};'><td><b>{row['ball']:02d}</b></td><td>{row['s10']:.2f}</td><td>{m5}</td><td>{row['s3']:.2f}</td><td>{m10}</td><td>{tag}</td></tr>"
    html += "</table></div>"
    
    # 2. 红球分组
    html += "<div style='background:#fff;padding:8px;margin-top:10px;border-radius:6px'><h4 style='margin:0 0 5px 0;color:#f57c00'>🛡️红球分组</h4>"
    html += f"<table style='{st_t}'><tr><th>组</th><th>斜</th><th>能</th><th>态</th><th>号</th></tr>"
    for g in r_g:
        tag = g['tag'].split(' ')[0]
        html += f"<tr><td>{g['name']}</td><td>{g['s']:.2f}</td><td>{g['val']:.0f}</td><td>{tag}</td><td style='font-size:10px'>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # 3. 蓝球单兵 (表头结构完全复制红球)
    html += "<div style='background:#fff;padding:8px;margin-top:10px;border-radius:6px'><h4 style='margin:0 0 5px 0;color:#1976d2'>🔵蓝球单兵</h4>"
    html += f"<table style='{st_t}'><tr><th>号</th><th>S10</th><th>M5</th><th>S3</th><th>M10</th><th>态</th></tr>"
    for row in b_s:
        c = "#e3f2fd" if "🔥" in row['tag'] else ("#fff" if "☠️" in row['tag'] else "#fff")
        m5 = "√" if row['ma5'] else "×"; m10 = "√" if row['ma10'] else "×"
        tag = row['tag'].split(' ')[0]
        html += f"<tr style='background:{c};'><td><b>{row['ball']:02d}</b></td><td>{row['s10']:.2f}</td><td>{m5}</td><td>{row['s3']:.2f}</td><td>{m10}</td><td>{tag}</td></tr>"
    html += "</table></div>"
    
    # 4. 蓝球分组 (表头结构完全复制红球分组)
    html += "<div style='background:#fff;padding:8px;margin-top:10px;border-radius:6px'><h4 style='margin:0 0 5px 0;color:#303f9f'>👥蓝球分组</h4>"
    html += f"<table style='{st_t}'><tr><th>组</th><th>斜</th><th>能</th><th>态</th><th>号</th></tr>"
    for g in b_g:
        tag = g['tag'].split(' ')[0]
        html += f"<tr><td>{g['name']}</td><td>{g['s']:.2f}</td><td>{g['val']:.0f}</td><td>{tag}</td><td style='font-size:10px'>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # AI复制区
    ai = generate_ai_text(issue, r_s, r_g, b_s, b_g)
    html += f"<div style='margin-top:10px;border:1px dashed #666;padding:5px;background:#fff;'><h5 style='margin:0;text-align:center;'>🤖 AI数据包</h5><textarea style='width:100%;height:60px;font-size:10px;border:none;'>{ai}</textarea></div></body></html>"
    return html

def generate_ai_text(issue, r_s, r_g, b_s, b_g):
    t = f"【第{issue}期全量】\n1.红球(号,S10,M5,S3,M10,态):\n"
    for row in r_s:
        m5="1" if row['ma5'] else "0"; m10="1" if row['ma10'] else "0"
        t += f"{row['ball']},{row['s10']:.2f},{m5},{row['s3']:.2f},{m10},{row['tag']}|"
    t += "\n2.红组(组,斜,能,号):\n"
    for g in r_g: t += f"{g['name']},{g['s']:.2f},{g['val']:.0f},{g['balls']}\n"
    t += "\n3.蓝单(号,S10,M5,S3,M10,态):\n"
    for row in b_s:
        m5="1" if row['ma5'] else "0"; m10="1" if row['ma10'] else "0"
        t += f"{row['ball']},{row['s10']:.2f},{m5},{row['s3']:.2f},{m10},{row['tag']}|"
    t += "\n4.蓝组(组,斜,能):\n"
    for g in b_g: t += f"{g['name']},{g['s']:.2f},{g['val']:.0f}\n"
    return t

def save_web_file(html_content, issue):
    if not os.path.exists("public"): os.makedirs("public")
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(html_content)

# --- 主程序 ---

def main():
    print("🚀 启动 v20.0 (极致统一版)...")
    
    if not PUSH_TOKEN: print("🔴 警告：无 PUSH_TOKEN")
        
    df = update_database()
    if df is None or df.empty:
        if os.path.exists(CSV_FILE): df = pd.read_csv(CSV_FILE)
        else: return
            
    last_row = df.iloc[-1]
    issue = int(last_row['Issue'])
    
    r_s = analyze_red_single(df)
    r_g = analyze_red_groups(df)
    b_s = analyze_blue_single(df)
    b_g = analyze_blue_groups(df)
    
    html_msg = build_compressed_report(issue, last_row, r_s, r_g, b_s, b_g)
    save_web_file(html_msg, issue)
    
    if PUSH_TOKEN:
        print("📡 推送中...")
        requests.post('http://www.pushplus.plus/send', json={
            "token": PUSH_TOKEN, 
            "title": f"📊 第 {issue} 期统一战报", 
            "content": html_msg, 
            "template": "html"
        })

if __name__ == "__main__":
    main()
