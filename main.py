import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =================配置区=================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
# ========================================

def get_latest_data():
    """ 抓取并强力清洗数据 """
    url = "http://datachart.500.com/ssq/history/newinc/history.php?start=00001&end=99999"
    try:
        header = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=header, timeout=10)
        response.encoding = 'utf-8'
        tables = pd.read_html(response.text)
        df = tables[0]
        
        # 选取列并重命名
        df = df.iloc[:, [0, 1, 2, 3, 4, 5, 6, 7]]
        df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
        
        # 强力清洗：去除无效行，转数字
        df = df[pd.to_numeric(df['Issue'], errors='coerce').notnull()]
        df = df.sort_values(by='Issue', ascending=True)
        
        for c in df.columns:
            df[c] = df[c].astype(int)
            
        return df.tail(150).reset_index(drop=True)
    except Exception as e:
        print(f"数据抓取错误: {e}")
        return None

# --- 核心算法区 (保持与之前逻辑一致) ---
def analyze_red_dual(df):
    cols = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
    res_list = []
    for ball in range(1, 34):
        is_hit = df[cols].isin([ball]).any(axis=1)
        scores = []
        curr = 0
        for hit in is_hit:
            curr = (curr + (27/33)) if hit else (curr - (6/33))
            scores.append(curr)
        
        s10 = pd.Series(scores)
        ma5 = s10.rolling(5).mean()
        slope10 = np.polyfit(np.arange(5), s10.tail(5), 1)[0] * 10
        above_ma5 = s10.iloc[-1] > ma5.iloc[-1]
        
        ma10 = s10.rolling(10).mean()
        above_ma10 = s10.iloc[-1] > ma10.iloc[-1]
        
        tag = "☠️死号"
        if above_ma5 and above_ma10: tag = "🔥共振"
        elif above_ma5 and not above_ma10: tag = "💰回踩"
        elif not above_ma5 and above_ma10: tag = "✨妖股"
        
        res_list.append({'b': ball, 'tag': tag, 's10': slope10, 'history': scores})
    
    res_list.sort(key=lambda x: x['s10'], reverse=True)
    return res_list

def analyze_blue(df):
    blue_res = []
    for ball in range(1, 17):
        is_hit = (df['Blue'] == ball)
        scores = []
        curr = 0
        for hit in is_hit:
            curr = (curr + (15/16)*5) if hit else (curr - (1/16))
            scores.append(curr)
        slope = np.polyfit(np.arange(5), pd.Series(scores).tail(5), 1)[0] * 10
        blue_res.append({'b': ball, 'slope': slope, 'history': scores})
    blue_res.sort(key=lambda x: x['slope'], reverse=True)
    return blue_res

# --- 策略生成区 (模拟你的分析逻辑) ---
def generate_strategies(reds, blues):
    # 红球分类
    hot_reds = [r['b'] for r in reds if r['tag'] == "🔥共振"]
    dip_reds = [r['b'] for r in reds if r['tag'] == "💰回踩"]
    reversal_reds = [r['b'] for r in reds if r['tag'] == "✨妖股"]
    
    # 蓝球分类
    top_blue = blues[0]['b']
    second_blue = blues[1]['b']
    
    # 方案A：强攻 (斜率最高的红球 + 蓝球王)
    plan_a_red = hot_reds[:5] + (reversal_reds[:1] if reversal_reds else hot_reds[5:6])
    plan_a_blue = [top_blue, second_blue]
    
    # 方案B：防守 (加入回踩球 + 互补蓝)
    plan_b_red = hot_reds[:3] + dip_reds[:2] + reversal_reds[:1]
    # 补齐6个
    while len(plan_b_red) < 6:
        for r in hot_reds:
            if r not in plan_b_red: plan_b_red.append(r); break
    plan_b_red.sort()
    plan_b_blue = [blues[2]['b'], blues[3]['b']] # 选斜率第3、4名防守
    
    # 方案C：胆拖 (金胆 + 拖码)
    bankers = hot_reds[:1] + dip_reds[:1] # 1热1回踩做胆
    if not bankers: bankers = hot_reds[:2]
    drags = hot_reds[1:4] + reversal_reds[:2]
    
    return {
        "A": {"r": sorted(plan_a_red), "b": sorted(plan_a_blue)},
        "B": {"r": sorted(plan_b_red), "b": sorted(plan_b_blue)},
        "C": {"bank": sorted(bankers), "drag": sorted(drags), "b": [top_blue]}
    }

# --- 可视化图表生成区 ---
def generate_html_chart(reds, blues, last_issue):
    # 只画前3名红球和第1名蓝球，避免图表太大
    top_balls = reds[:3]
    top_blue = blues[0]
    
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05,
                        subplot_titles=[f"红球{b['b']}趋势" for b in top_balls] + [f"蓝球{top_blue['b']}趋势"])
    
    # 画红球
    for i, ball in enumerate(top_balls):
        y_data = ball['history']
        x_data = list(range(len(y_data)))
        fig.add_trace(go.Scatter(x=x_data, y=y_data, mode='lines', name=f'红{ball["b"]}', line=dict(color='#FF4136')), row=i+1, col=1)
        
    # 画蓝球
    y_b = top_blue['history']
    fig.add_trace(go.Scatter(x=list(range(len(y_b))), y=y_b, mode='lines', name=f'蓝{top_blue["b"]}', line=dict(color='#0074D9')), row=4, col=1)
    
    fig.update_layout(height=800, title=f"双色球第 {last_issue} 期 - 核心号码能量图", template="plotly_dark")
    
    # 保存为文件，供GitHub Pages发布
    if not os.path.exists("public"): os.makedirs("public")
    fig.write_html("public/index.html")

# --- 推送逻辑 ---
def push_wechat(title, content):
    if not PUSH_TOKEN: return
    url = 'http://www.pushplus.plus/send'
    data = {"token": PUSH_TOKEN, "title": title, "content": content, "template": "html"}
    requests.post(url, json=data)

def main():
    df = get_latest_data()
    if df is None or df.empty: return
    
    last_issue = df['Issue'].iloc[-1]
    reds = analyze_red_dual(df)
    blues = analyze_blue(df)
    strats = generate_strategies(reds, blues)
    
    # 生成图表
    generate_html_chart(reds, blues, last_issue)
    
    # 你的 GitHub Pages 地址 (需要替换用户名)
    # 格式：https://<你的GitHub用户名>.github.io/<仓库名>/
    # 脚本会自动尝试获取环境变量，如果获取不到，请手动替换下面的 URL
    repo_owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    repo_name = "lottery-auto" # 你的仓库名
    chart_url = f"https://{repo_owner}.github.io/{repo_name}/" if repo_owner else "请在配置中设置URL"

    # 构建详细报告
    msg = f"<h3>📅 期号：{last_issue}</h3>"
    msg += f"<a href='{chart_url}'>👉 <b>点击查看云端K线图 (交互版)</b></a><hr>"
    
    msg += "<h4>📊 市场状态诊断</h4>"
    hot_count = len([r for r in reds if r['tag']=="🔥共振"])
    msg += f"🔥 共振热号：{hot_count} 个 (市场{'过热' if hot_count>10 else '正常'})<br>"
    msg += f"💰 黄金回踩：{[r['b'] for r in reds if r['tag']=='💰回踩'][:3]}<br>"
    msg += f"✨ 妖股反转：{[r['b'] for r in reds if r['tag']=='✨妖股'][:2]}<br>"
    
    msg += "<hr><h4>🛠️ 实战方案推荐</h4>"
    
    msg += "<b>【方案A：趋势强攻单】(6+2)</b><br>"
    msg += f"🔴 红球：{strats['A']['r']}<br>🔵 蓝球：{strats['A']['b']}<br><br>"
    
    msg += "<b>【方案B：防守互补单】(6+2)</b><br>"
    msg += f"🔴 红球：{strats['B']['r']}<br>🔵 蓝球：{strats['B']['b']}<br><br>"
    
    msg += "<b>【方案C：极客胆拖】(3胆5拖)</b><br>"
    msg += f"🔴 胆码：{strats['C']['bank']}<br>⚪ 拖码：{strats['C']['drag']}<br>🔵 蓝球：{strats['C']['b']}<br>"
    
    print("分析完成，正在推送...")
    push_wechat(f"双色球战报-{last_issue}", msg)

if __name__ == "__main__":
    main()
