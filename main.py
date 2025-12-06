import pandas as pd
import numpy as np
import requests
import os
import time

# =================配置区=================
# 在这里填入你的 PushPlus Token，或者在云端环境变量里设置
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
# 如果你在本地运行测试，把下面这行取消注释，填入你的Token
# PUSH_TOKEN = "你的token粘贴在这里" 
# ========================================

def get_latest_data():
    """ 自动从网上抓取最近 100 期双色球数据 """
    url = "http://datachart.500.com/ssq/history/newinc/history.php?start=00001&end=99999"
    try:
        # 伪装浏览器请求
        header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=header)
        response.encoding = 'utf-8'
        
        # 使用 pandas 解析网页表格
        tables = pd.read_html(response.text)
        df = tables[0]
        
        # 清洗数据 (保留期号和红蓝球)
        # 500彩票网的列索引：0=期号, 1-6=红球, 7=蓝球
        df = df.iloc[:, [0, 1, 2, 3, 4, 5, 6, 7]]
        df.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
        
        # 排序并转数字
        df = df.sort_values(by='Issue', ascending=True)
        for c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        
        # 只取最近 150 期做分析足够了
        return df.tail(150).reset_index(drop=True)
    except Exception as e:
        return None

def analyze_red_dual(df):
    """ 红球双周期扫描逻辑 """
    cols = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
    res_list = []
    
    for ball in range(1, 34):
        # 计算能量
        is_hit = df[cols].isin([ball]).any(axis=1)
        scores = []
        curr = 0
        for hit in is_hit:
            curr = (curr + (27/33)) if hit else (curr - (6/33))
            scores.append(curr)
        
        # 10期趋势 (MA5)
        s10 = pd.Series(scores)
        ma5 = s10.rolling(5).mean()
        slope10 = np.polyfit(np.arange(5), s10.tail(5), 1)[0] * 10
        above_ma5 = s10.iloc[-1] > ma5.iloc[-1]
        
        # 3期买点 (MA10)
        ma10 = s10.rolling(10).mean()
        slope3 = np.polyfit(np.arange(5), s10.tail(5), 1)[0] * 10 # 简化斜率算法
        above_ma10 = s10.iloc[-1] > ma10.iloc[-1]
        
        tag = ""
        if above_ma5 and above_ma10: tag = "🔥共振"
        elif above_ma5 and not above_ma10: tag = "💰回踩"
        elif not above_ma5 and above_ma10: tag = "✨妖股"
        else: tag = "☠️死号"
        
        res_list.append({'b': ball, 'tag': tag, 's10': slope10, 's3': slope3})
        
    # 排序：优先共振和回踩
    res_list.sort(key=lambda x: x['s10'], reverse=True)
    return res_list

def analyze_blue(df):
    """ 蓝球斜率与分组分析 """
    # 1. 单兵斜率
    blue_res = []
    for ball in range(1, 17):
        is_hit = (df['Blue'] == ball)
        scores = []
        curr = 0
        for hit in is_hit:
            curr = (curr + (15/16)*5) if hit else (curr - (1/16))
            scores.append(curr)
        s_series = pd.Series(scores)
        slope = np.polyfit(np.arange(5), s_series.tail(5), 1)[0] * 10
        blue_res.append({'b': ball, 'slope': slope})
    blue_res.sort(key=lambda x: x['slope'], reverse=True)
    
    # 2. 分组分析 (G7等)
    groups = {
        'G7(07+10)': [7, 10], 'G3(03+14)': [3, 14], 'G9(09+08)': [8, 9] # 简化示例
    }
    g_res = []
    for name, balls in groups.items():
        is_hit = df['Blue'].isin(balls)
        curr = 0
        scores = []
        for hit in is_hit:
            curr = (curr + (7/8)*2) if hit else (curr - (1/8))
            scores.append(curr)
        slope = np.polyfit(np.arange(5), pd.Series(scores).tail(5), 1)[0] * 10
        g_res.append({'name': name, 'slope': slope})
    g_res.sort(key=lambda x: x['slope'], reverse=True)
    
    return blue_res, g_res

def push_wechat(title, content):
    if not PUSH_TOKEN:
        print("未设置Token，跳过推送")
        return
    url = 'http://www.pushplus.plus/send'
    data = {"token": PUSH_TOKEN, "title": title, "content": content, "template": "html"}
    requests.post(url, json=data)

def main():
    print("正在启动云端分析系统...")
    df = get_latest_data()
    if df is None:
        print("获取数据失败")
        return
    
    last_issue = df['Issue'].iloc[-1]
    print(f"最新一期: {last_issue}")
    
    # 运行分析
    reds = analyze_red_dual(df)
    blues, groups = analyze_blue(df)
    
    # 生成报告文本
    msg = f"<h3>📅 期号：{last_issue}</h3>"
    msg += "<hr>"
    
    msg += "<h4>🔴 红球重点推荐</h4>"
    msg += "<b>【🔥 共振加速区】(追热):</b><br>"
    hot_list = [f"{r['b']:02d}" for r in reds if r['tag'] == "🔥共振"][:6]
    msg += ", ".join(hot_list) + "<br>"
    
    msg += "<b>【💰 黄金回踩区】(抄底):</b><br>"
    dip_list = [f"{r['b']:02d}" for r in reds if r['tag'] == "💰回踩"][:3]
    msg += ", ".join(dip_list) if dip_list else "无明显回踩"
    msg += "<br>"
    
    msg += "<h4>🔵 蓝球雷达</h4>"
    msg += f"<b>单兵王 (斜率最高):</b> {blues[0]['b']:02d} (强度:{blues[0]['slope']:.1f})<br>"
    msg += f"<b>第二名:</b> {blues[1]['b']:02d}<br>"
    msg += f"<b>最强分组:</b> {groups[0]['name']}<br>"
    
    msg += "<hr>"
    msg += "<h4>🎫 极客最终建议</h4>"
    msg += f"<b>红球胆码：</b> {hot_list[0]}, {hot_list[1] if len(hot_list)>1 else ''}<br>"
    msg += f"<b>蓝球必买：</b> {blues[0]['b']:02d}, {blues[1]['b']:02d}<br>"
    
    print(msg) # 本地打印
    push_wechat(f"双色球分析报告-{last_issue}", msg) # 发送微信

if __name__ == "__main__":
    main()
