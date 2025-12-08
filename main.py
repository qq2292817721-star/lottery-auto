import pandas as pd
import numpy as np
import requests
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import time
import re
from io import StringIO

# ================= 配置区 =================
PUSH_TOKEN = os.environ.get("PUSH_TOKEN") 
CSV_FILE = "ssq.csv"

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
    return {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }

# --- 1. 核弹级数据抓取模块 (v6.0) ---

def fetch_zhcw_fixed():
    """
    源1: 中彩网 (修复GBK编码问题)
    你截图里的网站，必须用 GBK 解码才能看到数据
    """
    print("📡 尝试源1: 中彩网 (GBK修复版)...")
    url = f"http://www.zhcw.com/ssq/kjgg/?_t={int(time.time()*1000)}"
    try:
        r = requests.get(url, headers=get_headers(), timeout=15)
        r.encoding = 'gbk' # 关键修正！
        
        # 使用 Pandas 解析表格
        dfs = pd.read_html(StringIO(r.text))
        for df in dfs:
            # 转换为字符串并查找期号
            s_df = df.astype(str)
            # 筛选出包含 2025141 这一行的
            # 假设最新一期在第一行，我们遍历前几行
            for _, row in df.iterrows():
                row_str = " ".join([str(v) for v in row.values])
                # 提取期号
                issue_match = re.search(r'(202[4-9]\d{3})', row_str)
                if issue_match:
                    issue = int(issue_match.group(1))
                    
                    # 提取所有球号 (中彩网通常是 期号 日期 红1..红6 蓝)
                    # 我们提取这一行里所有 <= 33 的数字
                    nums = re.findall(r'\b\d{1,2}\b', row_str)
                    clean_nums = [int(n) for n in nums if int(n) <= 33]
                    
                    # 过滤掉期号前后的杂质，通常红球蓝球连在一起
                    # 简单的启发式：找连续的7个数字
                    if len(clean_nums) >= 7:
                        # 假设最后7个是红+蓝 (倒数第1个是蓝, 倒数7-2是红)
                        # 中彩网表格：期号, 日期, R1, R2, R3, R4, R5, R6, Blue
                        # 所以我们取最后7个数字
                        balls = clean_nums[-7:]
                        
                        df_res = pd.DataFrame([[issue] + balls], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
                        print(f"✅ 源1(中彩网) 捕获成功: {issue}")
                        return df_res
    except Exception as e:
        print(f"❌ 源1失败: {e}")
    return None

def fetch_m_500():
    """
    源2: 500彩票 触屏版 (m.500.com)
    触屏版页面结构简单，且缓存策略通常比PC版宽松
    """
    print("📡 尝试源2: 500触屏版...")
    url = f"https://m.500.com/info/kaijiang/ssq/?_t={int(time.time())}"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        r.encoding = 'utf-8'
        
        # 触屏版通常直接显示最新一期
        # 寻找期号: 第2025141期
        issue_match = re.search(r'第\s*(\d{7})\s*期', r.text)
        if issue_match:
            issue = int(issue_match.group(1))
            
            # 寻找红球: <div class="ball_red">02</div>
            reds = re.findall(r'class="ball_red">(\d+)<', r.text)
            # 寻找蓝球: <div class="ball_blue">06</div>
            blues = re.findall(r'class="ball_blue">(\d+)<', r.text)
            
            if len(reds) >= 6 and len(blues) >= 1:
                row = [issue] + [int(x) for x in reds[:6]] + [int(blues[0])]
                print(f"✅ 源2(500触屏) 捕获成功: {issue}")
                return pd.DataFrame([row], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
    except Exception as e:
        print(f"❌ 源2失败: {e}")
    return None

def fetch_sina_api_v2():
    """
    源3: 新浪 API (加强版)
    """
    print("📡 尝试源3: 新浪API...")
    url = "https://match.lottery.sina.com.cn/client/index/client_list"
    params = {
        'lotteryCode': 'ssq',
        'page': 1,
        '_': int(time.time()*1000) # 时间戳破缓存
    }
    try:
        r = requests.get(url, params=params, headers=get_headers(), timeout=10)
        data = r.json()
        if 'result' in data and 'data' in data['result']:
            item = data['result']['data'][0] # 取最新的
            issue = int(item['issueNo'])
            draw = item['drawCode']
            r_str, b_str = draw.split('|')
            reds = [int(x) for x in r_str.split(',')]
            blue = int(b_str)
            print(f"✅ 源3(新浪) 捕获成功: {issue}")
            return pd.DataFrame([[issue]+reds+[blue]], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
    except Exception as e:
        print(f"❌ 源3失败: {e}")
    return None

def fetch_baidu_api():
    """
    源4: 百度搜索透传数据
    """
    print("📡 尝试源4: 百度API...")
    url = "https://sp0.baidu.com/9_Q4sjW91Qh3otqbppnN2DJv/pae/channel/data/asyncqury?appid=4001&com=wssq&limit=1"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        data = r.json()
        if data['data']:
            item = data['data'][0]
            issue = int(item['qh'])
            reds = [int(x) for x in item['red'].split(',')] # 可能需要处理格式
            blue = int(item['blue']) # 可能需要处理格式
            # 百度有时候返回的是 字符串列表，需要健壮性处理
            if len(reds) == 6:
                print(f"✅ 源4(百度) 捕获成功: {issue}")
                return pd.DataFrame([[issue]+reds+[blue]], columns=['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue'])
    except Exception as e:
        print(f"❌ 源4失败: {e}")
    return None

def get_web_data(local_issue):
    """
    轮询所有源，直到找到比 local_issue 更新的数据
    """
    fetchers = [fetch_zhcw_fixed, fetch_m_500, fetch_sina_api_v2, fetch_baidu_api]
    
    best_df = None
    
    for fetcher in fetchers:
        df = fetcher()
        if df is not None and not df.empty:
            issue = int(df.iloc[0]['Issue'])
            if issue > local_issue:
                return df # 找到新数据，直接返回
            if best_df is None or issue > int(best_df.iloc[0]['Issue']):
                best_df = df # 保留目前为止最新的
                
    return best_df

def update_database():
    df_local = pd.DataFrame()
    last_local_issue = 0
    
    if os.path.exists(CSV_FILE):
        try: 
            df_local = pd.read_csv(CSV_FILE)
            if not df_local.empty:
                last_local_issue = int(df_local['Issue'].iloc[-1])
        except: pass
    
    print(f"📂 本地最新: {last_local_issue}")
    
    # 获取网络数据
    df_net = get_web_data(last_local_issue)
    
    if df_net is not None and not df_net.empty:
        net_issue = int(df_net.iloc[0]['Issue'])
        
        # 只有真的比本地新，才进行合并
        if net_issue > last_local_issue:
            print(f"🎉 成功更新! {last_local_issue} -> {net_issue}")
            if not df_local.empty:
                df_local.columns = ['Issue', 'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'Blue']
                df_final = pd.concat([df_local, df_net]).drop_duplicates(subset=['Issue'], keep='last')
            else:
                df_final = df_net
            
            df_final = df_final.sort_values(by='Issue')
            df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
            return df_final
        else:
            print(f"💤 全网数据仍为 {net_issue} 期 (未更新)")
            return df_local # 返回旧数据
    
    return df_local

# --- 2. 算法与绘图 (不变) ---
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
    print("🚀 启动 (v6.0 核弹版 - 修复GBK/误报)...")
    
    # 1. 获取旧期号
    old_issue = 0
    if os.path.exists(CSV_FILE):
        try: old_issue = int(pd.read_csv(CSV_FILE)['Issue'].iloc[-1])
        except: pass

    # 2. 尝试更新
    df = update_database()
    if df is None or df.empty: return
    
    last_row = df.iloc[-1]
    new_issue = int(last_row['Issue'])
    
    # 3. 严格判定更新状态
    is_updated = new_issue > old_issue
    
    print(f"本地: {old_issue} | 最新: {new_issue} | 结果: {'✅已更新' if is_updated else '❌未更新'}")

    # 4. 分析
    rs, rg, bs, bg = run_analysis_raw(df)
    ai_text = generate_raw_text(rs, rg, bs, bg)
    generate_interactive_page(df, new_issue, ai_text)

    # 5. 推送
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if repo else "public/index.html"
    
    if is_updated:
        title = f"✅ 双色球第{new_issue}期 (已更新)"
        msg = f"{format_balls_html(last_row)}"
        msg += f"<p style='color:green;text-align:center;font-size:12px;margin:5px 0;'>✅ 成功获取最新数据！<br>数据源: 中彩网(修复)/500触屏/百度</p>"
    else:
        title = f"❌ 双色球第{new_issue}期 (未更新)"
        msg = f"{format_balls_html(last_row)}"
        msg += f"<p style='color:red;text-align:center;font-size:12px;margin:5px 0;'>❌ 严重警告：数据仍滞后！<br>当前显示仍为 {new_issue} 期。<br>已尝试所有接口，可能是海外IP被全面封锁。</p>"
    
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
