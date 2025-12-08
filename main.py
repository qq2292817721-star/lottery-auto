import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
import time
from io import StringIO

# ================= 配置区 =================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
CSV_FILE = "ssq.csv"

# 【核按钮】如果实在抓不到，请手动修改下方变量为 True，并填入号码
# 格式：MANUAL_ISSUE = 2025141, MANUAL_NUMS = [红1, 红2, 红3, 红4, 红5, 红6, 蓝]
USE_MANUAL = False 
MANUAL_ISSUE = 2025141
MANUAL_NUMS = [2, 4, 5, 10, 12, 13, 6] 

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

def get_headers():
    # 模拟标准的 Chrome 浏览器
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

# --- 1. 搜索引擎抓取模块 (针对 Bing/Sogou 优化) ---

def extract_from_text(text, target_issue):
    """
    通用解析器：在 HTML 源码中寻找 [期号] 周围的 [7个数字]
    """
    # 1. 简单清洗 HTML 标签
    clean_text = re.sub(r'<[^>]+>', ' ', text)
    
    # 2. 定位期号
    issue_str = str(target_issue)
    if issue_str not in clean_text:
        return None
    
    # 3. 截取期号附近的内容 (前后 300 字符)
    idx = clean_text.find(issue_str)
    # 向后找
    snippet = clean_text[idx:idx+400]
    
    # 4. 提取所有数字
    # 匹配 1-33 的数字 (允许一位数或两位数)
    nums = re.findall(r'\b([0-3]?[0-9])\b', snippet)
    nums = [int(n) for n in nums]
    
    # 5. 寻找符合双色球规则的序列 (6红 + 1蓝)
    # 红球 1-33, 蓝球 1-16
    for i in range(len(nums) - 7):
        chunk = nums[i : i+7]
        # 规则：前6个是红球(互不相同, 1-33)，第7个是蓝球(1-16)
        # 且数字之间不能全是0
        reds = chunk[:6]
        blue = chunk[6]
        
        if (len(set(reds)) == 6 and 
            all(1 <= r <= 33 for r in reds) and 
            1 <= blue <= 16):
            return chunk
            
    return None

def fetch_bing_search(target_issue):
    """
    源1: 必应搜索 (Bing)
    Github Actions 是微软家的，访问 Bing 通常不会被墙，也不会有验证码。
    """
    url = f"https://www.bing.com/search?q=双色球+{target_issue}+开奖结果"
    print(f"🔍 正在请求 Bing: {url}")
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        nums = extract_from_text(r.text, target_issue)
        if nums:
            print(f"✅ Bing 找到数据: {nums}")
            return nums
        else:
            print("⚠️ Bing 页面正常但未提取到号码 (可能结构变化)")
            # 调试：打印一小段内容看是不是被拦截了
            # print(r.text[:500]) 
    except Exception as e:
        print(f"❌ Bing 失败: {e}")
    return None

def fetch_sogou_search(target_issue):
    """
    源2: 搜狗搜索
    搜狗的爬虫反制相对较弱，且收录微信公众号内容，更新快。
    """
    url = f"https://www.sogou.com/web?query=双色球{target_issue}期开奖结果"
    print(f"🔍 正在请求 搜狗: {url}")
    try:
        # 搜狗需要 Cookie 才能减少验证码概率，这里尝试裸奔，但在 Header 加了 Language
        r = requests.get(url, headers=get_headers(), timeout=10)
        nums = extract_from_text(r.text, target_issue)
        if nums:
            print(f"✅ 搜狗 找到数据: {nums}")
            return nums
    except Exception as e:
        print(f"❌ 搜狗 失败: {e}")
    return None

def fetch_cwl_direct(target_issue):
    """
    源3: 中国福彩官网 (API 直连)
    """
    url = "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice?name=ssq&issueCount=1"
    print(f"📡 正在请求 官网API...")
    try:
        # 官网对 Referer 校验严格
        h = get_headers()
        h['Referer'] = 'http://www.cwl.gov.cn/'
        r = requests.get(url, headers=h, timeout=10)
        data = r.json()
        if data['result']:
            item = data['result'][0]
            if str(item['code']) == str(target_issue):
                reds = [int(x) for x in item['red'].split(',')]
                blue = int(item['blue'])
                print(f"✅ 官网API 找到数据: {reds} + {blue}")
                return reds + [blue]
    except Exception as e:
        print(f"❌ 官网API 失败: {e}")
    return None

def get_web_data(local_issue):
    target_issue = local_issue + 1
    print(f"🎯 目标期号: {target_issue} (脚本将在全网搜寻此数据)")
    
    # 0. 核按钮检查
    if USE_MANUAL and MANUAL_ISSUE == target_issue:
        print(f"☢️ 检测到手动核按钮开启，强制使用预设数据！")
        row = [MANUAL_ISSUE] + MANUAL_NUMS
        return pd.DataFrame([row], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])

    # 1. 必应 (最推荐 GHA 环境)
    nums = fetch_bing_search(target_issue)
    if nums: return to_df(target_issue, nums)
    
    # 2. 官网 API
    nums = fetch_cwl_direct(target_issue)
    if nums: return to_df(target_issue, nums)

    # 3. 搜狗
    nums = fetch_sogou_search(target_issue)
    if nums: return to_df(target_issue, nums)
    
    print(f"⚠️ 全网搜索未果。Bing/搜狗/官网 均未返回第 {target_issue} 期数据。")
    return None

def to_df(issue, nums):
    # nums 应该是 [r1, r2, r3, r4, r5, r6, b]
    row = [issue] + nums
    return pd.DataFrame([row], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])

def update_database():
    df_local = pd.DataFrame()
    last_issue = 2025000
    
    if os.path.exists(CSV_FILE):
        try: 
            df_local = pd.read_csv(CSV_FILE)
            if not df_local.empty:
                last_issue = int(df_local['Issue'].iloc[-1])
        except: pass
    
    print(f"📂 本地最新: {last_issue}")
    
    # 这里的 last_issue 必须是本地的，用于预测下一期
    df_net = get_web_data(last_issue)
    
    if df_net is not None and not df_net.empty:
        net_issue = int(df_net.iloc[0]['Issue'])
        if net_issue > last_issue:
            print(f"🎉 抓取成功! 更新本地数据库: {last_issue} -> {net_issue}")
            if not df_local.empty:
                df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
                df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'], keep='last')
            else:
                df_final = df_net
            df_final = df_final.sort_values(by='Issue')
            df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
            return df_final
    
    return df_local

# --- 2. 核心算法 (不变) ---
def calc_slope(series, window=5):
    y = series.tail(window)
    if len(y) < 2: return 0
    try: return np.polyfit(np.arange(len(y)), y, 1)[0] * 10 
    except: return 0

def get_energy(df, targets, type='red'):
    prob_miss = 27/33 if type == 'red' else 15/16
    cols = ['R1','R2','R3','R4','R5','R6'] if type == 'red' else ['Blue']
    is_hit = df[cols].isin(targets).any(axis=1) if type == 'red' else df['Blue'].isin(targets)
    scores = []; curr = 0
    for hit in is_hit:
        curr = (curr - (1 - prob_miss)) if hit else (curr + prob_miss * (5 if type=='blue' else 1))
        scores.append(curr)
    return pd.Series(scores)

def calculate_kline_for_chart(df, target_ball, ball_type, period):
    scores = get_energy(df, [target_ball], ball_type).tolist()
    ohlc = []
    for i in range(0, len(scores), period):
        chunk = scores[i : i+period]
        if not chunk: continue
        prev = scores[i-1] if i > 0 else 0
        ohlc.append([prev, max(prev, max(chunk)), min(prev, min(chunk)), chunk[-1]])
    k_df = pd.DataFrame(ohlc, columns=['Open', 'High', 'Low', 'Close'])
    k_df['MA'] = k_df['Close'].rolling(5 if period == 10 else 10).mean()
    k_df['Index'] = range(len(k_df))
    return k_df

def generate_interactive_page(df, last_issue, ai_text):
    if not os.path.exists("public"): os.makedirs("public")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.1, subplot_titles=("趋势(10期)", "短线(3期)"), row_heights=[0.6, 0.4])
    df_chart = df.tail(400).reset_index(drop=True)
    
    for ball in range(1, 34): 
        d10 = calculate_kline_for_chart(df_chart, ball, 'red', 10)
        d3 = calculate_kline_for_chart(df_chart, ball, 'red', 3).tail(100)
        v = (ball == 1)
        fig.add_trace(go.Candlestick(x=d10.index, open=d10['Open'], high=d10['High'], low=d10['Low'], close=d10['Close'], visible=v, increasing_line_color='#F44336', decreasing_line_color='#2196F3'), 1, 1)
        fig.add_trace(go.Scatter(x=d10.index, y=d10['MA'], mode='lines', visible=v, line=dict(color='yellow', width=1)), 1, 1)
        fig.add_trace(go.Candlestick(x=list(range(len(d3))), open=d3['Open'], high=d3['High'], low=d3['Low'], close=d3['Close'], visible=v, increasing_line_color='#E91E63', decreasing_line_color='#4CAF50'), 2, 1)
        fig.add_trace(go.Scatter(x=list(range(len(d3))), y=d3['MA'], mode='lines', visible=v, line=dict(color='white', width=1, dash='dot')), 2, 1)
    
    for ball in range(1, 17):
        d10 = calculate_kline_for_chart(df_chart, ball, 'blue', 10)
        d3 = calculate_kline_for_chart(df_chart, ball, 'blue', 3).tail(100)
        fig.add_trace(go.Candlestick(x=d10.index, open=d10['Open'], high=d10['High'], low=d10['Low'], close=d10['Close'], visible=False, increasing_line_color='#FF9800', decreasing_line_color='#03A9F4'), 1, 1)
        fig.add_trace(go.Scatter(x=d10.index, y=d10['MA'], mode='lines', visible=False, line=dict(color='cyan', width=1)), 1, 1)
        fig.add_trace(go.Candlestick(x=list(range(len(d3))), open=d3['Open'], high=d3['High'], low=d3['Low'], close=d3['Close'], visible=False, increasing_line_color='#9C27B0', decreasing_line_color='#8BC34A'), 2, 1)
        fig.add_trace(go.Scatter(x=list(range(len(d3))), y=d3['MA'], mode='lines', visible=False, line=dict(color='white', width=1, dash='dot')), 2, 1)

    fig.update_layout(template="plotly_dark", height=600, margin=dict(t=30, l=10, r=10, b=10), showlegend=False, dragmode='pan', xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False)
    plot_div = fig.to_html(full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False}, div_id='plotly_div')
    
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no"><title>第{last_issue}期</title>
    <style>body{{background:#121212;color:#eee;margin:0;font-family:sans-serif}}.header{{padding:10px;background:#1e1e1e}}select{{background:#333;color:#fff;border:1px solid #555;padding:8px;width:45%;margin-top:5px}}textarea{{position:absolute;left:-999px}}</style></head>
    <body><div class="header"><h3>📊 第{last_issue}期控制台</h3><button onclick="copyData()" style="width:100%;padding:10px;background:#00C853;color:fff;border:none;border-radius:4px">📋 复制AI数据</button><textarea id="ai">{ai_text}</textarea>
    <div style="display:flex;justify-content:space-between;margin-top:5px"><select id="r" onchange="s('red')"><option disabled>红球</option>{''.join([f'<option value="{i}" {"selected" if i==1 else ""}>{i:02d}</option>' for i in range(1,34)])}</select>
    <select id="b" onchange="s('blue')"><option selected disabled>蓝球</option>{''.join([f'<option value="{i}">{i:02d}</option>' for i in range(1,17)])}</select></div></div>{plot_div}
    <script>function copyData(){{var c=document.getElementById("ai");c.select();document.execCommand("copy");alert("已复制")}}
    function s(t){{var d=document.getElementById('plotly_div'),v,b;if(t=='red'){{document.getElementById('b').selectedIndex=0;v=parseInt(document.getElementById('r').value);b=(v-1)*4}}else{{document.getElementById('r').selectedIndex=0;v=parseInt(document.getElementById('b').value);b=132+(v-1)*4}}
    var a=new Array(196).fill(false);a[b]=a[b+1]=a[b+2]=a[b+3]=true;Plotly.restyle(d,{{'visible':a}})}}</script></body></html>"""
    with open("public/index.html", "w", encoding='utf-8') as f: f.write(html)

def generate_raw_text(rs, rg, bs, bg):
    return f"【数据集】\n红球:\n{rs.to_string(index=False)}\n\n蓝球:\n{bs.to_string(index=False)}\n\n红组:\n{rg.to_string(index=False)}\n\n蓝组:\n{bg.to_string(index=False)}"

def format_balls_html(row):
    r_sty = "display:inline-block;width:25px;height:25px;line-height:25px;border-radius:50%;background:#f44336;color:fff;text-align:center;font-weight:bold;margin:2px;"
    b_sty = "display:inline-block;width:25px;height:25px;line-height:25px;border-radius:50%;background:#2196f3;color:fff;text-align:center;font-weight:bold;margin:2px;"
    h = "<div style='text-align:center;padding:10px;background:#fff;border-bottom:1px solid #eee;'>"
    for i in range(1,7): h += f"<span style='{r_sty}'>{row[f'R{i}']:02d}</span>"
    h += f"<span style='{b_sty}'>{row['Blue']:02d}</span></div>"
    return h

def df_to_html_table(df, title):
    h = f"<div style='margin-top:10px;border:1px solid #ddd;border-radius:5px;overflow:hidden;'><div style='background:#f1f1f1;padding:5px;font-weight:bold;font-size:13px'>{title}</div>"
    h += "<table style='width:100%;border-collapse:collapse;font-size:11px;text-align:center;'>"
    h += "<tr style='background:#eee;'>" + "".join([f"<th>{c}</th>" for c in df.columns]) + "</tr>"
    for _, r in df.iterrows():
        bg = "#ffebee" if "🔥" in str(r.values) else ("#e8f5e9" if "🚀" in str(r.values) else "#fff")
        h += f"<tr style='background:{bg};border-bottom:1px solid #eee;'>" + "".join([f"<td style='padding:4px'>{v}</td>" for v in r.values]) + "</tr>"
    h += "</table></div>"
    return h

def run_analysis_raw(df):
    rs = []
    for b in range(1, 34):
        s = get_energy(df, [b], 'red')
        cur = s.iloc[-1]; m5 = s.rolling(5).mean().iloc[-1]
        tag = "🔥" if cur > m5 else "❄️"
        rs.append({'号': f"{b:02d}", 'S10': round(calc_slope(s,5),1), '态': tag})
    
    bs = []
    for b in range(1, 17):
        s = get_energy(df, [b], 'blue')
        cur = s.iloc[-1]; m5 = s.rolling(5).mean().iloc[-1]
        tag = "🔥" if cur > m5 else "❄️"
        bs.append({'号': f"{b:02d}", 'S10': round(calc_slope(s,5),1), '态': tag})

    rg = [{'组': k, '率': round(calc_slope(get_energy(df, v, 'red'), 10), 1)} for k,v in RED_GROUPS.items()]
    bg = [{'组': k, '率': round(calc_slope(get_energy(df, v, 'blue'), 5), 1)} for k,v in BLUE_GROUPS.items()]

    return (pd.DataFrame(rs).sort_values('S10', ascending=False),
            pd.DataFrame(rg).sort_values('率', ascending=False),
            pd.DataFrame(bs).sort_values('S10', ascending=False),
            pd.DataFrame(bg).sort_values('率', ascending=False))

def main():
    print("🚀 启动 (v8.0 Bing/Sogou 越狱版)...")
    
    # 1. 更新数据库
    df = update_database()
    if df is None or df.empty: return
    
    last_row = df.iloc[-1]
    new_issue = int(last_row['Issue'])
    
    # 2. 判断状态
    # 读取原始 CSV 再次确认，防止内存缓存问题
    try:
        csv_check = pd.read_csv(CSV_FILE)
        csv_issue = int(csv_check['Issue'].iloc[-1])
        is_updated = (csv_issue >= 2025141) # 硬编码判断，只有拿到141才算成功
    except:
        is_updated = False
    
    print(f"最终判定: 期号 {new_issue} | 是否更新: {is_updated}")

    # 3. 分析
    rs, rg, bs, bg = run_analysis_raw(df)
    ai_text = generate_raw_text(rs, rg, bs, bg)
    generate_interactive_page(df, new_issue, ai_text)

    # 4. 推送
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if repo else "public/index.html"
    
    if is_updated:
        title = f"✅ 双色球第{new_issue}期 (已更新)"
        msg_header = f"<p style='color:green;text-align:center;font-weight:bold;'>✅ Bing/搜狗 搜索成功！<br>已获取最新数据。</p>"
    else:
        title = f"❌ 双色球第{new_issue}期 (未更新)"
        msg_header = f"<p style='color:red;text-align:center;font-weight:bold;'>❌ 搜索未果，仍显示旧数据。<br>请稍后，或启用代码中的 USE_MANUAL 核按钮。</p>"
    
    msg = f"{format_balls_html(last_row)}" + msg_header
    msg += f"<div style='text-align:center;margin:10px'><a href='{url}' style='color:#007bff;text-decoration:none;'>📊 打开交互图表控制台</a></div>"
    msg += df_to_html_table(rs, "🔴 红球全量趋势 (S10降序)")
    msg += df_to_html_table(bs, "🔵 蓝球全量趋势")
    msg += df_to_html_table(rg, "🛡️ 红球分组")
    msg += df_to_html_table(bg, "⚖️ 蓝球分组")
    
    if PUSH_TOKEN:
        try:
            requests.post('http://www.pushplus.plus/send', json={"token": PUSH_TOKEN, "title": title, "content": msg, "template": "html"})
            print("✅ 推送成功")
        except Exception as e: print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    main()
