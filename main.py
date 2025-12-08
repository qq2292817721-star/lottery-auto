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

# --- 2. 核心算法 (复刻本地脚本) ---

def get_kline_dataframe(scores, period):
    """将分数序列转换为K线DataFrame"""
    ohlc = []
    for i in range(0, len(scores), period):
        chunk = scores[i : i+period]
        if not chunk: continue
        prev = scores[i-1] if i > 0 else 0
        chunk_max = max(chunk)
        chunk_min = min(chunk)
        real_high = max(prev, chunk_max)
        real_low = min(prev, chunk_min)
        ohlc.append([prev, real_high, real_low, chunk[-1]])
    return pd.DataFrame(ohlc, columns=['Open', 'High', 'Low', 'Close'])

def analyze_trend_from_kline(df_kline, ma_window):
    """从K线计算斜率和均线状态"""
    df_kline['MA'] = df_kline['Close'].rolling(ma_window).mean()
    if len(df_kline) < 5: return 0, False
    
    current_close = df_kline['Close'].iloc[-1]
    current_ma = df_kline['MA'].iloc[-1]
    
    # 拟合斜率
    recent = df_kline['Close'].tail(5)
    x = np.arange(len(recent))
    slope = np.polyfit(x, recent, 1)[0] * 10
    
    is_above_ma = current_close > current_ma
    return slope, is_above_ma

# A. 红球单兵 (复刻 ssq_dual_scan.py)
def analyze_red_single(df):
    results = []
    cols = ['R1','R2','R3','R4','R5','R6']
    
    for ball in range(1, 34):
        # 1. 能量计算
        prob_hit = 6/33; prob_miss = 27/33
        is_hit = df[cols].isin([ball]).any(axis=1)
        scores = []; curr = 0
        for hit in is_hit:
            if hit: curr += prob_miss
            else: curr -= prob_hit
            scores.append(curr)
        
        # 2. 10期分析 (看MA5)
        df_10 = get_kline_dataframe(scores, 10)
        slope_10, above_ma5 = analyze_trend_from_kline(df_10, 5)
        
        # 3. 3期分析 (看MA10)
        df_3 = get_kline_dataframe(scores, 3)
        slope_3, above_ma10 = analyze_trend_from_kline(df_3, 10)
        
        # 4. 诊断逻辑 (完全一致)
        tag = ""; priority = 0
        if above_ma5:
            if above_ma10:
                if slope_3 > 0: tag = "🔥 共振加速 (必追)"; priority = 5
                else: tag = "⚠️ 上涨中继 (防)"; priority = 4
            else:
                if slope_3 < 0: tag = "💰 黄金回踩 (重仓)"; priority = 4.5
                else: tag = "🤔 震荡整理 (观)"; priority = 3
        else:
            if above_ma10 and slope_3 > 2: tag = "✨ 妖股反转 (博胆)"; priority = 3.5
            elif above_ma10: tag = "🚀 超跌反弹 (拖)"; priority = 2
            else: tag = "☠️ 双杀下跌 (杀)"; priority = 0
            
        results.append({
            'ball': ball,
            's10': slope_10, 'ma5': above_ma5,
            's3': slope_3, 'ma10': above_ma10,
            'tag': tag, 'prio': priority
        })
    
    # 排序：优先级 > 3期斜率 (和脚本一致)
    results.sort(key=lambda x: (x['prio'], x['s3']), reverse=True)
    return results

# B. 红球分组 (复刻 ssq_red_groups.py)
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
        
        # 计算趋势
        recent = scores[-20:]
        slope = np.polyfit(np.arange(len(recent)), recent, 1)[0] * 10 if len(recent)>1 else 0
        ma = pd.Series(scores).rolling(10).mean().iloc[-1]
        above_ma = scores[-1] > ma
        
        tag = ""; prio = 0
        if above_ma:
            if slope > 2: tag = "🔥 集团冲锋"; prio = 5
            elif slope > 0: tag = "📈 稳步上升"; prio = 4
            else: tag = "⚠️ 高位滞涨"; prio = 3
        else:
            if slope > 0.5: tag = "🚀 底部复苏"; prio = 4.5
            else: tag = "☠️ 弱势群体"; prio = 0
            
        results.append({'name': name, 'balls': str(balls), 's': slope, 'tag': tag, 'prio': prio})
    
    results.sort(key=lambda x: (x['prio'], x['s']), reverse=True)
    return results

# C. 蓝球单兵 (复刻 ssq_blue_scan.py)
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
            
        # 10期/3期分析
        df_10 = get_kline_dataframe(scores, 10)
        s10, ma5 = analyze_trend_from_kline(df_10, 5)
        df_3 = get_kline_dataframe(scores, 3)
        s3, ma10 = analyze_trend_from_kline(df_3, 10)
        
        tag = ""; prio = 0
        if ma5:
            if ma10: tag = "🔥 皇冠热号"; prio = 5
            else: tag = "💰 黄金回踩"; prio = 4
        else:
            if ma10: tag = "🚀 妖股启动"; prio = 4.5
            else: tag = "☠️ 极寒深渊"; prio = 0
            
        results.append({'ball': ball, 's': s3, 'tag': tag, 'prio': prio}) # 这里原脚本用S3排序
    
    results.sort(key=lambda x: (x['prio'], x['s']), reverse=True)
    return results

# D. 蓝球分组 (复刻 ssq_blue_groups.py)
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
            
        recent = scores[-20:]
        slope = np.polyfit(np.arange(len(recent)), recent, 1)[0] * 10 if len(recent)>1 else 0
        ma = pd.Series(scores).rolling(10).mean().iloc[-1]
        above_ma = scores[-1] > ma
        
        tag = ""; prio = 0
        if above_ma:
            if slope > 1: tag = "🔥 强势拉升"; prio = 5
            else: tag = "⚠️ 高位震荡"; prio = 3
        else:
            if slope > 0: tag = "🚀 底部启动"; prio = 4
            else: tag = "☠️ 下跌通道"; prio = 0
            
        results.append({'name': name, 'balls': str(balls), 's': slope, 'tag': tag, 'prio': prio})
        
    results.sort(key=lambda x: (x['prio'], x['s']), reverse=True)
    return results

# --- 3. 生成全景 HTML 报表 (复刻截图格式) ---

def build_full_report(issue, last_row, r_s, r_g, b_s, b_g):
    # 样式
    style_card = "background:#fff; border-radius:8px; padding:10px; margin-bottom:12px; box-shadow:0 1px 2px rgba(0,0,0,0.1);"
    style_table = "width:100%; border-collapse:collapse; font-size:11px; text-align:center;"
    style_th = "background:#f0f0f0; padding:4px; border-bottom:2px solid #ddd; color:#333; font-weight:bold; white-space:nowrap;"
    style_td = "padding:4px; border-bottom:1px solid #eee;"
    
    # 1. 头部
    r_ball = "".join([f"<span style='display:inline-block;width:22px;height:22px;line-height:22px;background:#f44336;color:#fff;border-radius:50%;margin:1px;font-size:12px;'>{last_row[f'R{i}']:02d}</span>" for i in range(1,7)])
    b_ball = f"<span style='display:inline-block;width:22px;height:22px;line-height:22px;background:#2196f3;color:#fff;border-radius:50%;margin:1px;font-size:12px;'>{last_row['Blue']:02d}</span>"
    
    html = f"""
    <div style='font-family:sans-serif; background:#f2f3f5; padding:8px;'>
        <div style='{style_card} text-align:center;'>
            <h4 style='margin:0 0 5px 0;'>📊 第 {issue} 期全景扫描</h4>
            <div>{r_ball}{b_ball}</div>
        </div>
    """
    
    # 2. 红球单兵 (复刻表格)
    html += f"<div style='{style_card}'>"
    html += f"<h4 style='margin:0 0 8px 0; border-left:4px solid #f44336; padding-left:6px;'>🔴 红球单兵 (全量)</h4>"
    html += f"<table style='{style_table}'>"
    html += f"<tr><th style='{style_th}'>号</th><th style='{style_th}'>S10</th><th style='{style_th}'>MA5</th><th style='{style_th}'>S3</th><th style='{style_th}'>MA10</th><th style='{style_th}'>AI诊断</th></tr>"
    
    for row in r_s:
        bg = "#fff"
        if "🔥" in row['tag']: bg = "#ffebee"
        elif "💰" in row['tag']: bg = "#fffde7"
        elif "☠️" in row['tag']: bg = "#f5f5f5"
        
        ma5_icon = "✅" if row['ma5'] else "❌"
        ma10_icon = "✅" if row['ma10'] else "❌"
        
        html += f"<tr style='background:{bg};'>"
        html += f"<td style='{style_td} font-weight:bold;'>{row['ball']:02d}</td>"
        html += f"<td style='{style_td}'>{row['s10']:.1f}</td>"
        html += f"<td style='{style_td}'>{ma5_icon}</td>"
        html += f"<td style='{style_td}'>{row['s3']:.1f}</td>"
        html += f"<td style='{style_td}'>{ma10_icon}</td>"
        html += f"<td style='{style_td} font-size:10px;text-align:left;'>{row['tag']}</td>"
        html += "</tr>"
    html += "</table></div>"
    
    # 3. 红球分组
    html += f"<div style='{style_card}'>"
    html += f"<h4 style='margin:0 0 8px 0; border-left:4px solid #ff9800; padding-left:6px;'>🛡️ 红球分组 (全量)</h4>"
    html += f"<table style='{style_table}'>"
    html += f"<tr><th style='{style_th}'>组名</th><th style='{style_th}'>斜率</th><th style='{style_th}'>趋势</th><th style='{style_th}'>号码</th></tr>"
    for g in r_g:
        html += f"<tr><td style='{style_td}'><b>{g['name']}</b></td><td style='{style_td}'>{g['s']:.1f}</td><td style='{style_td}'>{g['tag']}</td><td style='{style_td} font-size:9px;color:#666;'>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # 4. 蓝球单兵
    html += f"<div style='{style_card}'>"
    html += f"<h4 style='margin:0 0 8px 0; border-left:4px solid #2196f3; padding-left:6px;'>🔵 蓝球单兵 (全量)</h4>"
    html += f"<table style='{style_table}'>"
    html += f"<tr><th style='{style_th}'>号</th><th style='{style_th}'>斜率(S3)</th><th style='{style_th}'>诊断</th></tr>"
    for b in b_s:
        bg = "#e3f2fd" if "🔥" in b['tag'] else "#fff"
        html += f"<tr style='background:{bg};'><td style='{style_td} font-weight:bold;'>{b['ball']:02d}</td><td style='{style_td}'>{b['s']:.1f}</td><td style='{style_td}'>{b['tag']}</td></tr>"
    html += "</table></div>"
    
    # 5. 蓝球分组
    html += f"<div style='{style_card}'>"
    html += f"<h4 style='margin:0 0 8px 0; border-left:4px solid #3f51b5; padding-left:6px;'>👥 蓝球分组 (全量)</h4>"
    html += f"<table style='{style_table}'>"
    html += f"<tr><th style='{style_th}'>组名</th><th style='{style_th}'>斜率</th><th style='{style_th}'>趋势</th><th style='{style_th}'>号码</th></tr>"
    for g in b_g:
        html += f"<tr><td style='{style_td}'><b>{g['name']}</b></td><td style='{style_td}'>{g['s']:.1f}</td><td style='{style_td}'>{g['tag']}</td><td style='{style_td} font-size:9px;color:#666;'>{g['balls']}</td></tr>"
    html += "</table></div>"
    
    # 6. AI 复制区
    ai_text = generate_ai_text(issue, r_s, r_g, b_s, b_g)
    html += f"<div style='{style_card} background:#e8eaf6; border:1px dashed #3f51b5;'>"
    html += f"<h4 style='margin:0 0 5px 0; text-align:center; color:#303f9f;'>🤖 AI 全量数据包 (长按复制)</h4>"
    html += f"<textarea id='ai-data' style='width:100%; height:80px; font-size:10px; border:1px solid #c5cae9; padding:5px; resize:none;'>{ai_text}</textarea>"
    html += "</div></div>"
    
    return html

def generate_ai_text(issue, r_s, r_g, b_s, b_g):
    t = f"【第{issue}期 全量数据报告】\n"
    t += "1.红球详细(号,S10,MA5,S3,MA10,态):\n"
    for row in r_s:
        m5 = "1" if row['ma5'] else "0"
        m10 = "1" if row['ma10'] else "0"
        t += f"{row['ball']:02d},{row['s10']:.1f},{m5},{row['s3']:.1f},{m10},{row['tag']} | "
    t += "\n\n2.红球分组(全量):\n"
    for g in r_g: t += f"{g['name']}(S:{g['s']:.1f}):{g['balls']}\n"
    t += "\n3.蓝球单兵(全量):\n"
    for b in b_s: t += f"{b['ball']:02d}(S:{b['s']:.1f}):{b['tag']}\n"
    t += "\n4.蓝球分组(全量):\n"
    for g in b_g: t += f"{g['name']}(S:{g['s']:.1f})\n"
    return t

def save_web_file(html_content, issue):
    if not os.path.exists("public"): os.makedirs("public")
    full_html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>第{issue}期全景报表</title></head><body style="margin:0;padding:0;">{html_content}</body></html>"""
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(full_html)

# --- 主程序 ---

def main():
    print("🚀 启动 v15.0 (像素级复刻版)...")
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
                "title": f"📊 第 {issue} 期全景数据", 
                "content": html_msg, 
                "template": "html"
            })
            print("✅ 推送成功")
        except Exception as e: print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    main()
