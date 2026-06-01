# -*- coding: utf-8 -*-
"""
台股七大組合 — 每日趨勢儀表板（含新聞 + 免費版消息面標籤）
消息面標籤：用新聞關鍵字粗略判斷各組偏多/中性/偏空，並與趨勢燈號比對「一致 / 背離」。
注意：關鍵字判斷是粗略參考，會漏判或讀錯（如否定句、輕重），請以趨勢面為主、新聞為輔。
"""
import time, datetime, webbrowser, os, base64, json
from html import escape as esc
from urllib.parse import quote
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
import requests
import yfinance as yf

GROUPS = {
    "AI代工組合":   ["2317", "2382", "3231", "6669", "2376", "2356", "3706"],
    "半導體組合":   ["2330", "2454", "2303", "3711", "2379", "3034", "2408"],
    "ETF組合":      ["0050", "0056", "00878", "006208", "00919", "00929", "00940"],
    "金融銀行組合": ["2881", "2882", "2891", "2886", "2884", "2892"],
    "電子組合":     ["2308", "2324", "4938", "2301", "2382", "2317"],
    "低軌衛星組合": ["3491", "6285", "2314", "3178", "6271", "3596"],
    "光電組合":     ["3008", "3406", "2409", "3481", "2393", "4979"],
}
NAMES = {
    "2317":"鴻海","2382":"廣達","3231":"緯創","6669":"緯穎","2376":"技嘉","2356":"英業達","3706":"神達",
    "2330":"台積電","2454":"聯發科","2303":"聯電","3711":"日月光","2379":"瑞昱","3034":"聯詠","2408":"南亞科",
    "0050":"元大台灣50","0056":"高股息","00878":"永續高息","006208":"富邦台50","00919":"精選高息","00929":"科技優息","00940":"價值高息",
    "2881":"富邦金","2882":"國泰金","2891":"中信金","2886":"兆豐金","2884":"玉山金","2892":"第一金",
    "2308":"台達電","2324":"仁寶","4938":"和碩","2301":"光寶科",
    "3491":"昇達科","6285":"啟碁","2314":"台揚","3178":"公準","6271":"同欣電","3596":"智易",
    "3008":"大立光","3406":"玉晶光","2409":"友達","3481":"群創","2393":"億光","4979":"華星光",
}
# 抓新聞用的關鍵字
NEWS_QUERIES = ["台股","半導體","台積電","聯準會 利率","AI 伺服器","金融 升息 降息","面板 光電","低軌衛星"]
NEWS_POOL = 30   # 抓進來分析的新聞數
NEWS_SHOW = 8    # 儀表板上顯示幾則

# 各組「相關新聞」判斷用的產業關鍵字（會自動再加上該組股票中文名）
SECTOR_TERMS = {
    "AI代工組合": ["AI伺服器","伺服器","代工","ODM","散熱","機櫃","電源","CPO","液冷"],
    "半導體組合": ["半導體","晶圓","台積","封裝","CoWoS","晶片","製程","IC設計","HBM","記憶體"],
    "ETF組合": ["ETF","高股息","配息","除息","大盤","加權","台股"],
    "金融銀行組合": ["金控","銀行","升息","降息","利率","利差","金融"],
    "電子組合": ["電子","筆電","NB","電源","組裝","消費性"],
    "低軌衛星組合": ["衛星","低軌","太空","SpaceX","星鏈","通訊"],
    "光電組合": ["光電","面板","鏡頭","光學","LED","顯示"],
}
# 情緒關鍵字
POS = ["大漲","飆","攻","創高","創新高","新高","看好","樂觀","利多","受惠","強勢","上修","調高","買超","加碼","暢旺","旺","拉貨","突破","漲停","報喜","優於預期","擴產","回溫","反彈","降息","成長"]
NEG = ["大跌","重挫","崩","跌停","殺","利空","賣超","減碼","砍單","衰退","下修","調降","虧損","示警","警訊","疲弱","走弱","賣壓","獲利了結","急殺","暴跌","升息","摔"]
NEG_WORDS = ["否認","不","未","無","沒","免","非"]

# ===== 發佈到網路（GitHub Pages）=====
# 三個都填好才會自動發佈；留空就只在本機產生 dashboard.html。
# 注意：填了權杖後，請勿把這支程式分享出去（權杖是你的密碼）。
GITHUB_USER  = ""    # 你的 GitHub 帳號
GITHUB_REPO  = ""    # 你建立的 repo 名稱，例如 stock
GITHUB_TOKEN = ""    # 你的存取權杖
GITHUB_BRANCH = "main"

def fetch(code):
    for suffix in (".TW", ".TWO"):
        try:
            df = yf.Ticker(code+suffix).history(period="1y", auto_adjust=True)
            if df is not None and len(df) >= 60:
                return df["Close"].dropna()
        except Exception:
            pass
    return None

def analyze(c):
    ma = {n: c.rolling(n).mean() for n in (5,10,20,60)}
    last = c.iloc[-1]; s = 50.0
    if ma[5].iloc[-1] > ma[10].iloc[-1] > ma[20].iloc[-1] > ma[60].iloc[-1]: s += 20
    elif ma[5].iloc[-1] < ma[10].iloc[-1] < ma[20].iloc[-1] < ma[60].iloc[-1]: s -= 20
    s += 8 if last > ma[20].iloc[-1] else -8
    s += 8 if last > ma[60].iloc[-1] else -8
    s += 6 if ma[20].iloc[-1] > ma[20].iloc[-6] else -6
    mom20 = (last/c.iloc[-21]-1)*100 if len(c)>21 else 0
    s += max(min(mom20,10),-10); s = max(0,min(100,s))
    chg1 = (last/c.iloc[-2]-1)*100 if len(c)>=2 else 0
    mom5 = (last/c.iloc[-6]-1)*100 if len(c)>=6 else 0
    return round(s), round(chg1,1), mom5

def status(score): return "多" if score>=65 else ("空" if score<45 else "觀望")
def arrow(m):
    if m>5: return "↑"
    if m>1: return "↗"
    if m<-5: return "↓"
    if m<-1: return "↘"
    return "→"

def market_status():
    try:
        c = yf.Ticker("^TWII").history(period="1y", auto_adjust=True)["Close"].dropna()
        ma60 = c.rolling(60).mean().iloc[-1]
        ma240 = c.rolling(240).mean().iloc[-1] if len(c)>=240 else ma60
        if c.iloc[-1]>ma60 and c.iloc[-1]>ma240: return "大盤 偏多","good"
        if c.iloc[-1]<ma240: return "大盤 偏空（留意風險）","bad"
        return "大盤 中性","warn"
    except Exception:
        return "大盤 資料取得失敗","warn"

def rel_time(dt):
    if dt is None: return ""
    mins = (datetime.datetime.now(datetime.timezone.utc)-dt).total_seconds()/60
    if mins<1: return "剛剛"
    if mins<60: return f"{int(mins)}分鐘前"
    if mins<60*24: return f"{int(mins//60)}小時前"
    return f"{int(mins//(60*24))}天前"

def fetch_news(max_items=NEWS_POOL):
    items, seen = [], set()
    for q in NEWS_QUERIES:
        url = f"https://news.google.com/rss/search?q={quote(q)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent":"Mozilla/5.0"})
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for it in root.iter("item"):
            title=(it.findtext("title") or "").strip()
            link=(it.findtext("link") or "").strip()
            pub=it.findtext("pubDate") or ""
            se=it.find("source"); src=(se.text or "").strip() if se is not None else ""
            if not title or title in seen: continue
            seen.add(title)
            if src and title.endswith(" - "+src): title=title[:-(len(src)+3)]
            try: dt=parsedate_to_datetime(pub)
            except Exception: dt=None
            items.append({"title":title,"link":link,"src":src,"dt":dt})
    far=datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    items.sort(key=lambda x:x["dt"] or far, reverse=True)
    return items[:max_items]

def title_polarity(title):
    """回傳 +1 利多 / -1 利空 / 0 中性（含簡單否定詞處理）"""
    s = 0
    for kw in POS:
        if kw in title:
            i = title.find(kw)
            neg = any(nw in title[max(0,i-3):i] for nw in NEG_WORDS)
            s += -1 if neg else 1
    for kw in NEG:
        if kw in title:
            i = title.find(kw)
            neg = any(nw in title[max(0,i-3):i] for nw in NEG_WORDS)
            s += 1 if neg else -1
    return 1 if s>0 else (-1 if s<0 else 0)

def group_news_tag(news_pool, gkw):
    matched = [n for n in news_pool if any(k in n["title"] for k in gkw)]
    net = sum(title_polarity(n["title"]) for n in matched)
    tag = "偏多" if net>0 else ("偏空" if net<0 else "中性")
    return tag, len(matched)

def agree_flag(trend_status, news_tag):
    if (trend_status=="多" and news_tag=="偏多") or (trend_status=="空" and news_tag=="偏空"):
        return "一致"
    if (trend_status=="多" and news_tag=="偏空") or (trend_status=="空" and news_tag=="偏多"):
        return "背離"
    return "—"

def publish_github(html):
    """把 html 發佈成 GitHub Pages 的 index.html。三個設定沒填齊就跳過。"""
    if not (GITHUB_USER and GITHUB_REPO and GITHUB_TOKEN):
        return
    api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/index.html"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}",
               "Accept": "application/vnd.github+json",
               "User-Agent": "stock-dashboard"}
    sha = None
    try:
        r = requests.get(api, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass
    payload = {"message": "update dashboard",
               "content": base64.b64encode(html.encode("utf-8")).decode(),
               "branch": GITHUB_BRANCH}
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(api, headers=headers, data=json.dumps(payload), timeout=20)
        if r.status_code in (200, 201):
            print(f"  已發佈到網路：https://{GITHUB_USER}.github.io/{GITHUB_REPO}/")
        else:
            print(f"  發佈失敗（{r.status_code}）：{r.text[:200]}")
    except Exception as e:
        print(f"  發佈失敗：{e}")

CSS = """
body{font-family:-apple-system,'Microsoft JhengHei','PingFang TC',sans-serif;background:#f6f5f1;margin:0;padding:20px;color:#222}
.wrap{max-width:720px;margin:0 auto}
h1{font-size:20px;font-weight:600;margin:0 0 4px}
.sub{color:#777;font-size:13px;margin-bottom:6px}
.note{color:#999;font-size:12px;margin-bottom:16px;line-height:1.6}
.card{background:#fff;border:1px solid #eceae3;border-radius:14px;padding:14px 16px;margin-bottom:12px}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px}
.gname{font-size:17px;font-weight:600}
.gsum{font-size:13px;color:#777;margin-top:3px}
.pill{font-size:13px;font-weight:600;padding:3px 12px;border-radius:8px;white-space:nowrap}
.sc{font-size:13px;color:#777;margin-top:6px;text-align:right}
.news-tag{font-size:12px;margin-top:4px;text-align:right;color:#999}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:13px;padding:4px 10px;border:1px solid #eceae3;border-radius:8px;margin:0 6px 6px 0}
.dot{width:8px;height:8px;border-radius:50%}
.code{color:#aaa;font-size:11px}
.legend{font-size:12px;color:#777;margin-top:8px}
.foot{font-size:11px;color:#aaa;margin-top:14px;line-height:1.6}
.up{color:#1a7f37}.down{color:#b42318}.flat{color:#888}
.p-good{background:#e6f4ea;color:#1a7f37}.p-warn{background:#fdf3e0;color:#9a6700}.p-bad{background:#fbeae8;color:#b42318}
.news-card{border-left:4px solid #c9933a}
.news-item{display:block;text-decoration:none;color:inherit;padding:8px 0;border-top:1px solid #f0eee7}
.news-item:first-of-type{border-top:none}
.news-item:hover .news-title{color:#1a5fb4}
.news-title{font-size:14px;line-height:1.45}
.news-meta{font-size:11px;color:#aaa;margin-top:2px}
"""
def color_class(st): return {"多":"p-good","觀望":"p-warn","空":"p-bad"}[st]
def label(st): return {"多":"偏多","觀望":"觀望","空":"偏空"}[st]
def news_color(tag): return {"偏多":"#1a7f37","偏空":"#b42318","中性":"#999"}[tag]
def agree_color(a): return {"一致":"#1a7f37","背離":"#9a6700","—":"#bbb"}[a]

def build_news_html(news):
    if not news:
        return '<div class="card news-card"><div class="gname">市場重大新聞</div><div class="gsum">目前暫時無法取得新聞（可能沒網路或來源忙碌），不影響下方股價。</div></div>'
    rows=""
    for n in news[:NEWS_SHOW]:
        meta=" · ".join(x for x in [n["src"], rel_time(n["dt"])] if x)
        rows+=f'<a href="{esc(n["link"],quote=True)}" target="_blank" class="news-item"><div class="news-title">{esc(n["title"])}</div><div class="news-meta">{esc(meta)}</div></a>'
    return f'<div class="card news-card"><div class="gname">市場重大新聞</div>{rows}</div>'

def build_html(results, mkt_text, mkt_cls, news_html=""):
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y/%m/%d %H:%M")
    mkt_color={"good":"#1a7f37","warn":"#9a6700","bad":"#b42318"}[mkt_cls]
    cards=""
    for g in results:
        chips=""
        for s in g["stocks"]:
            cls="up" if s["chg"]>0 else ("down" if s["chg"]<0 else "flat")
            sign="+" if s["chg"]>0 else ""
            chips+=f'<span class="chip"><span class="dot {cls}" style="background:currentColor"></span>{esc(s["name"])}<span class="code">{esc(s["code"])}</span><span class="{cls}" style="font-weight:600">{sign}{s["chg"]}%</span></span>'
        arr_cls="up" if g["arrow"] in ("↑","↗") else ("down" if g["arrow"] in ("↓","↘") else "flat")
        nt=g["news_tag"]; ag=g["agree"]
        news_line=f'<div class="news-tag">消息面 <span style="color:{news_color(nt)};font-weight:600">{nt}</span> · <span style="color:{agree_color(ag)};font-weight:600">{ag}</span></div>'
        cards+=f'<div class="card"><div class="head"><div style="flex:1;min-width:0"><div class="gname">{esc(g["name"])}</div><div class="gsum">{esc(g["sum"])}</div></div><div style="text-align:right"><span class="pill {color_class(g["status"])}">{label(g["status"])}</span><div class="sc"><span class="{arr_cls}" style="font-size:17px">{g["arrow"]}</span> {g["score"]}分</div>{news_line}</div></div><div>{chips}</div></div>'
    return f'<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-status-bar-style" content="default"><meta name="apple-mobile-web-app-title" content="台股趨勢"><meta name="theme-color" content="#f6f5f1"><link rel="apple-touch-icon" href="icon.png"><title>台股每日趨勢</title><style>{CSS}</style></head><body><div class="wrap"><h1>台股七大組合 · 每日趨勢</h1><div class="sub">更新時間：{now}　·　<span style="color:{mkt_color};font-weight:600">{esc(mkt_text)}</span></div><div class="note">「消息面」是用新聞關鍵字粗略判斷（會漏判或讀錯，僅供參考）。「一致」＝消息面與趨勢同向；「背離」＝兩者相反，要提高警覺（可能利多出盡或利空鈍化），請以趨勢面為主。</div>{news_html}{cards}<div class="legend"><span class="up">●</span> 偏多/上漲　<span class="flat">●</span> 觀望/盤整　<span class="down">●</span> 偏空/下跌</div><div class="foot">股價來源：Yahoo Finance；新聞來源：Google 新聞（個人用途）。本表為自動計算之參考訊號，非投資建議；過去走勢不代表未來，投資決策與風險請自行評估。</div></div></body></html>'

def main():
    print("開始抓取新聞與最新股價…（約需 1~2 分鐘）")
    try:
        news_pool=fetch_news(); print(f"  新聞：取得 {len(news_pool)} 則")
    except Exception as e:
        news_pool=[]; print(f"  新聞抓取失敗（略過）：{e}")
    news_html=build_news_html(news_pool)
    cache, results = {}, []
    for gname, codes in GROUPS.items():
        stocks, scores, moms = [], [], []
        for code in codes:
            if code not in cache:
                cache[code]=fetch(code); time.sleep(0.3)
            c=cache[code]
            if c is None: continue
            sc,chg1,mom5=analyze(c)
            stocks.append({"name":NAMES.get(code,code),"code":code,"chg":chg1})
            scores.append(sc); moms.append(mom5)
        if not scores: continue
        gscore=round(sum(scores)/len(scores)); gmom=sum(moms)/len(moms); gstatus=status(gscore)
        best=max(stocks,key=lambda x:x["chg"]); worst=min(stocks,key=lambda x:x["chg"])
        summ=(f"動能偏強，{best['name']} 領漲" if gstatus=="多" else (f"走勢偏弱，{worst['name']} 拖累" if gstatus=="空" else f"區間整理，{best['name']} 相對抗跌"))
        gkw=[NAMES.get(code,code) for code in codes]+SECTOR_TERMS.get(gname,[])
        ntag,_=group_news_tag(news_pool, gkw)
        results.append({"name":gname,"status":gstatus,"score":gscore,"arrow":arrow(gmom),"sum":summ,
                        "stocks":stocks,"news_tag":ntag,"agree":agree_flag(gstatus,ntag)})
    results.sort(key=lambda x:x["score"], reverse=True)
    mkt_text, mkt_cls = market_status()
    html=build_html(results, mkt_text, mkt_cls, news_html)
    out_name = os.environ.get("OUT_FILE", "dashboard.html")
    out=os.path.join(os.path.dirname(os.path.abspath(__file__)), out_name)
    open(out,"w",encoding="utf-8").write(html)
    print(f"完成！已產生：{out}")
    publish_github(html)
    try: webbrowser.open("file://"+out)
    except Exception: pass

if __name__=="__main__":
    main()
