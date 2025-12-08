import pandas as pd
import numpy as np
import requests
import os
import re
import sys
import json

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
        ohlc.append([prev, max(prev, max(chunk)), min(prev, min(chunk)), chunk[-1]])
    return pd.DataFrame(ohlc, columns=['Open', 'High', 'Low', 'Close'])

def analyze_trend_from_kline(df_kline, ma_window):
    df_kline['MA'] = df_kline['Close'].rolling(ma_window).mean()
    if len(df_kline) < 5: return 0, False
    current_close = df_kline['Close'].iloc[-1]
    current_ma = df_kline['MA'].iloc[-1]
    recent = df_kline['Close'].tail(5)
    slope = np.polyfit(np.arange(len(recent)), recent, 1)[0] * 10
    return slope, current_close > current_ma

# A. 红球单兵
def analyze_red_single(df):
    results = []
    cols = ['R1','R2','R3','R4','R5','R6']
    for ball in range(1, 34):
        is_hit = df[cols].isin([ball]).any(axis=1)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += 27/33
            else: curr -= 6/33
            scores.append(curr)
        
        df_10 = get_kline_dataframe(scores, 10)
        s10, ma5 = analyze_trend_from_kline(df_10, 5)
        df_3 = get_kline_dataframe(scores, 3)
        s3, ma10 = analyze_trend_from_kline(df_3, 10)
        
        tag = "☠️双杀"; prio = 0
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
        
        recent = scores[-20:]
        slope = np.polyfit(np.arange(len(recent)), recent, 1)[0] * 10 if len(recent)>1 else 0
        ma = pd.Series(scores).rolling(10).mean().iloc[-1]
        above_ma = scores[-1] > ma
        
        tag = ""; prio = 0
        if above_ma:
            if slope > 2: tag = "🔥冲锋"; prio = 5
            elif slope > 0: tag = "📈稳升"; prio = 4
            else: tag = "⚠️滞涨"; prio = 3
        else:
            if slope > 0.5: tag = "🚀复苏"; prio = 4.5
            else: tag = "☠️弱势"; prio = 0
        results.append({'name': name, 'balls': str(balls), 's': slope, 'tag': tag, 'prio': prio})
    results.sort(key=lambda x: (x['prio'], x['s']), reverse=True)
    return results

# C. 蓝球单兵
def analyze_blue_single(df):
    results = []
    for ball in range(1, 17):
        is_hit = (df['Blue'] == ball)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += 15/16 * 5
            else: curr -= 1/16
            scores.append(curr)
        
        df_10 = get_kline_dataframe(scores, 10)
        s10, ma5 = analyze_trend_from_kline(df_10, 5)
        df_3 = get_kline_dataframe(scores, 3)
        s3, ma10 = analyze_trend_from_kline(df_3, 10)
        
        tag = ""; prio = 0
        if ma5:
            if ma10: tag = "🔥皇冠"; prio = 5
            else: tag = "💰回踩"; prio = 4
        else:
            if ma10: tag = "🚀启动"; prio = 4.5
            else: tag = "☠️深渊"; prio = 0
        results.append({'ball': ball, 's': s3, 'tag': tag, 'prio': prio})
    results.sort(key=lambda x: (x['prio'], x['s']), reverse=True)
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
        
        recent = scores[-20:]
        slope = np.polyfit(np.arange(len(recent)), recent, 1)[0] * 10 if len(recent)>1 else 0
        ma = pd.Series(scores).rolling(10).mean().iloc[-1]
        above_ma = scores[-1] > ma
        
        tag = ""; prio = 0
        if above_ma:
            if slope > 1: tag = "🔥拉升"; prio = 5
            else: tag = "⚠️震荡"; prio = 3
        else:
            if slope > 0: tag = "🚀启动"; prio = 4
            else: tag = "☠️下跌"; prio = 0
        results.append({'name': name, 'balls': str(balls), 's': slope, 'tag': tag, 'prio': prio})
    results.sort(key=lambda x: (x['prio'], x['s']), reverse=True)
    return results

# --- 3. 极速生成 HTML (压缩体积版) ---

def build_compressed_report(issue, last_row, r_s, r_g, b_s, b_g):
    # CSS 压缩：使用简写类名
    css = """<style>
    body{font-family:sans-serif;background:#f2f3f5;padding:5px}
    .c{background:#fff;border-radius:6px;padding:8px;margin-bottom:10px;text-align:center}
    .t{width:100%;font-size:10px;border-collapse:collapse}
    .t th{background:#eee;padding:3px}
    .t td{padding:3px;border-bottom:1px solid #eee}
    .b-r{display:inline-block;width:20px;height:20px;line-height:20px;background:#f44336;color:#fff;border-radius:50%;margin:1px;font-size:11px}
    .b-b{display:inline-block;width:20px;height:20px;line-height:20px;background:#2196f3;color:#fff;border-radius:50%;margin:1px;font-size:11px}
    .bg-1{background:#ffebee}.bg-2{background:#fffde7}.bg-3{background:#f5f5f5}
    </style>"""
    
    # 头部
    r_balls = "".join([f"<span class='b-r'>{last_row[f'R{i}']:02d}</span>" for i in range(1,7)])
    b_ball = f"<span class='b-b'>{last_row['Blue']:02d}</span>"
    
    html = f"<html><head>{css}</head><body>"
    html += f"<div class='c'><h4>第{issue}期战报 (v16.0)</h4>{r_balls}{b_ball}</div>"
    
    # 红球表
    html += "<div class='c'><b>🔴红球单兵</b><table class='t'><tr><th>号</th><th>S10</th><th>M5</th><th>S3</th><th>M10</th><th>态</th></tr>"
    for r in r_s:
        cls = "bg-1" if "🔥" in r['tag'] else ("bg-2" if "💰" in r['tag'] else ("bg-3" if "☠️" in r['tag'] else ""))
        m5, m10 = ("√" if r['ma5'] else "×"), ("√" if r['ma10'] else "×")
        html += f"<tr class='{cls}'><td>{r['ball']:02d}</td><td>{r['s10']:.1f}</td><td>{m5}</td><td>{r['s3']:.1f}</td><td>{m10}</td><td>{r['tag']}</td></tr>"
    html += "</table></div>"
    
    # 分组表
    html += "<div class='c'><b>🛡️红球分组</b><table class='t'><tr><th>组</th><th>斜</th><th>态</th><th>号</th></tr>"
    for g in r_g:
        html += f"<tr><td>{g['name']}</td><td>{g['s']:.1f}</td><td>{g['tag']}</td><td>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # 蓝球表
    html += "<div class='c'><b>🔵蓝球单兵</b><table class='t'><tr><th>号</th><th>斜</th><th>态</th></tr>"
    for b in b_s:
        cls = "bg-1" if "🔥" in b['tag'] else ""
        html += f"<tr class='{cls}'><td>{b['ball']:02d}</td><td>{b['s']:.1f}</td><td>{b['tag']}</td></tr>"
    html += "</table></div>"
    
    # 蓝球分组表
    html += "<div class='c'><b>👥蓝球分组</b><table class='t'><tr><th>组</th><th>斜</th><th>态</th><th>号</th></tr>"
    for g in b_g:
        html += f"<tr><td>{g['name']}</td><td>{g['s']:.1f}</td><td>{g['tag']}</td><td>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # AI 复制区
    ai = generate_ai_text(issue, r_s, r_g, b_s, b_g)
    html += f"<div class='c'><b>🤖AI指令(复制)</b><textarea style='width:100%;height:60px;font-size:10px;border:1px solid #ccc'>{ai}</textarea></div>"
    html += "</body></html>"
    return html

def generate_ai_text(issue, r_s, r_g, b_s, b_g):
    t = f"第{issue}期数据:\n1.红球(号,S10,M5,S3,M10,态):\n"
    for row in r_s:
        m5="1" if row['ma5'] else "0"; m10="1" if row['ma10'] else "0"
        t += f"{row['ball']},{row['s10']:.1f},{m5},{row['s3']:.1f},{m10},{row['tag']}|"
    t += "\n2.红组:\n"
    for g in r_g: t += f"{g['name']}(S:{g['s']:.1f}):{g['balls']}\n"
    t += "\n3.蓝单:\n"
    for b in b_s: t += f"{b['ball']}(S:{b['s']:.1f}):{b['tag']}\n"
    t += "\n4.蓝组:\n"
    for g in b_g: t += f"{g['name']}(S:{g['s']:.1f})\n"
    return t

def save_web_file(html_content, issue):
    if not os.path.exists("public"): os.makedirs("public")
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(html_content)

# --- 主程序 ---

def main():
    print("🚀 启动 v16.0 (诊断修复版)...")
    
    # 1. 诊断 Token
    if not PUSH_TOKEN:
        print("❌ 错误：未检测到 PUSH_TOKEN！请在 Secrets 中配置。")
        return
    else:
        print(f"✅ Token 已加载: {PUSH_TOKEN[:4]}******")

    # 2. 获取数据
    df = update_database()
    if df is None or df.empty:
        if os.path.exists(CSV_FILE):
            print("⚠️ 使用本地旧数据兜底...")
            df = pd.read_csv(CSV_FILE)
        else:
            print("❌ 无数据，退出。")
            return
            
    last_row = df.iloc[-1]
    issue = int(last_row['Issue'])
    
    # 3. 计算
    r_s = analyze_red_single(df)
    r_g = analyze_red_groups(df)
    b_s = analyze_blue_single(df)
    b_g = analyze_blue_groups(df)
    
    # 4. 生成报表 (极度压缩版)
    html_msg = build_compressed_report(issue, last_row, r_s, r_g, b_s, b_g)
    print(f"📄 HTML 报表大小: {len(html_msg)} 字符")
    save_web_file(html_msg, issue)
    
    # 5. 推送 (带双重保险)
    print("📡 开始推送...")
    try:
        # 尝试发送完整版
        resp = requests.post('http://www.pushplus.plus/send', json={
            "token": PUSH_TOKEN, 
            "title": f"📊 第 {issue} 期全景战报", 
            "content": html_msg, 
            "template": "html"
        })
        print(f"📥 响应: {resp.text}")
        
        # 检查是否真的成功 (PushPlus 有时返回 200 但 code!=200)
        res_json = resp.json()
        if res_json.get('code') != 200:
            print("❌ 完整版推送失败，尝试发送简报...")
            raise Exception("Full report failed")
            
    except Exception as e:
        # 兜底：发送纯文本简报
        print(f"⚠️ 切换到兜底模式: {e}")
        simple_msg = f"第 {issue} 期数据已生成。\n由于完整报表过大，请访问网页查看。\n\nAI指令:\n{generate_ai_text(issue, r_s, r_g, b_s, b_g)}"
        requests.post('http://www.pushplus.plus/send', json={
            "token": PUSH_TOKEN, 
            "title": f"⚠️ 第 {issue} 期简报 (完整版失败)", 
            "content": simple_msg
        })

if __name__ == "__main__":
    main()
