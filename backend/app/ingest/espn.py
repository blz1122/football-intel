"""真实数据源：ESPN 公开接口（无需 API key）。

设计要点：
- scoreboard 提供联赛最近一轮 + 今日赛程（真实开球时间/状态/比分/分钟）
- summary 提供 keyEvents（进球/红黄牌/换人，含分钟与球员名）与 boxscore 技术统计
- 同步为 UPSERT：以 provider_event_id 幂等，重复执行不产生重复数据
- 同步成功后删除 provider='mock' 的模拟比赛，避免界面出现"真实世界不存在"的比赛

注意：ESPN 该端点对浏览器 UA（Mozilla/Chrome）返回 403，需使用 curl 风格 UA。
"""
from __future__ import annotations

import gzip
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

UA = "curl/8.4.0-foodball-intel"
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# ESPN 联赛 slug -> (中文名, 英文名, 简称, 分组, 是否重点赛事)
# 分组用于前端联赛筛选器归类；重点赛事会优先拉取比赛详情（事件/统计/阵容）。
LEAGUES: dict[str, tuple[str, str, str, str, bool]] = {
    # ---------- 五大联赛 ----------
    "eng.1": ("英超", "Premier League", "英超", "英格兰", True),
    "esp.1": ("西甲", "La Liga", "西甲", "西班牙", True),
    "ita.1": ("意甲", "Serie A", "意甲", "意大利", True),
    "ger.1": ("德甲", "Bundesliga", "德甲", "德国", True),
    "fra.1": ("法甲", "Ligue 1", "法甲", "法国", True),
    # ---------- 欧洲其他联赛 ----------
    "ned.1": ("荷甲", "Eredivisie", "荷甲", "荷兰", False),
    "por.1": ("葡超", "Primeira Liga", "葡超", "葡萄牙", True),
    "bel.1": ("比甲", "Belgian Pro League", "比甲", "比利时", False),
    "tur.1": ("土超", "Süper Lig", "土超", "土耳其", False),
    "aut.1": ("奥地利甲", "Bundesliga", "奥甲", "奥地利", False),
    "sco.1": ("苏超", "Scottish Premiership", "苏超", "苏格兰", False),
    "sco.2": ("苏冠", "Scottish Championship", "苏冠", "苏格兰", False),
    "sui.1": ("瑞士超", "Swiss Super League", "瑞士超", "瑞士", False),
    "den.1": ("丹麦超", "Danish Superliga", "丹麦超", "丹麦", False),
    "swe.1": ("瑞典超", "Allsvenskan", "瑞典超", "瑞典", False),
    "nor.1": ("挪超", "Eliteserien", "挪超", "挪威", False),
    "gre.1": ("希腊超", "Super League", "希腊超", "希腊", False),
    "rou.1": ("罗甲", "Liga I", "罗甲", "罗马尼亚", False),
    "rus.1": ("俄超", "Premier League", "俄超", "俄罗斯", False),
    "isl.1": ("冰岛超", "Besta deild", "冰岛超", "冰岛", False),
    "irl.1": ("爱尔兰超", "Premier Division", "爱尔兰超", "爱尔兰", False),
    # ---------- 洲际俱乐部赛事 ----------
    "uefa.champions": ("欧冠", "UEFA Champions League", "欧冠", "洲际赛事", True),
    "uefa.europa": ("欧联", "UEFA Europa League", "欧联", "洲际赛事", True),
    "uefa.europa.conf": ("欧协联", "UEFA Conference League", "欧协联", "洲际赛事", False),
    "afc.champions": ("亚冠", "AFC Champions League", "亚冠", "洲际赛事", True),
    "caf.champions": ("非冠", "CAF Champions League", "非冠", "洲际赛事", False),
    "concacaf.leagues.cup": ("中北美联杯", "CONCACAF Champions Cup", "中北美联杯", "洲际赛事", False),
    # ---------- 国家队 / 国际赛事 ----------
    "uefa.nations": ("欧国联", "UEFA Nations League", "欧国联", "国家队", True),
    "fifa.friendly": ("国际友谊赛", "International Friendly", "友谊赛", "国家队", True),
    "fifa.worldq.uefa": ("世预赛-欧洲", "FIFA World Cup Qualifying - UEFA", "世预赛欧", "国家队", True),
    "fifa.worldq.concacaf": ("世预赛-中北美", "FIFA World Cup Qualifying - CONCACAF", "世预赛北美", "国家队", False),
    "fifa.worldq.conmebol": ("世预赛-南美", "FIFA World Cup Qualifying - CONMEBOL", "世预赛南美", "国家队", False),
    "fifa.worldq.afc": ("世预赛-亚洲", "FIFA World Cup Qualifying - AFC", "世预赛亚洲", "国家队", False),
    "fifa.worldq.caf": ("世预赛-非洲", "FIFA World Cup Qualifying - CAF", "世预赛非洲", "国家队", False),
    "fifa.worldq.ofc": ("世预赛-大洋洲", "FIFA World Cup Qualifying - OFC", "世预赛大洋", "国家队", False),
    "fifa.world": ("世界杯", "FIFA World Cup", "世界杯", "国家队", True),
    "uefa.euro": ("欧洲杯", "UEFA European Championship", "欧洲杯", "国家队", True),
    "afc.asian.cup": ("亚洲杯", "AFC Asian Cup", "亚洲杯", "国家队", True),
    "caf.nations": ("非洲杯", "Africa Cup of Nations", "非洲杯", "国家队", True),
    # ---------- 美洲联赛 ----------
    "usa.1": ("美职业", "MLS", "美职业", "美洲", True),
    "mex.1": ("墨西哥超", "Liga MX", "墨西哥超", "美洲", True),
    "bra.1": ("巴西甲", "Brasileirão Série A", "巴西甲", "美洲", True),
    "arg.1": ("阿甲", "Liga Profesional", "阿甲", "美洲", True),
    "chi.1": ("智利甲", "Primera División", "智利甲", "美洲", False),
    "col.1": ("哥甲", "Categoría Primera A", "哥甲", "美洲", False),
    "uru.1": ("乌拉圭甲", "Primera División", "乌拉圭甲", "美洲", False),
    "per.1": ("秘鲁甲", "Liga 1", "秘鲁甲", "美洲", False),
    # ---------- 亚洲 / 大洋洲联赛 ----------
    "jpn.1": ("J联赛", "J1 League", "J联赛", "亚洲", True),
    "chn.1": ("中超", "Chinese Super League", "中超", "亚洲", True),
    "aus.1": ("澳超", "A-League Men", "澳超", "大洋洲", True),
    "idn.1": ("印尼超", "Liga 1", "印尼超", "亚洲", False),
    "tha.1": ("泰超", "Thai League 1", "泰超", "亚洲", False),
    "ind.1": ("印度超", "Indian Super League", "印度超", "亚洲", False),
    # ---------- 非洲联赛 ----------
    "rsa.1": ("南非超", "Betway Premiership", "南非超", "非洲", False),
    "nga.1": ("尼日利亚超", "Nigeria Professional Football League", "尼日超", "非洲", False),
    "gha.1": ("加纳超", "Ghana Premier League", "加纳超", "非洲", False),
}

# 重点赛事（True）会被优先拉取详情；同步时按此排序，控制请求量。
KEY_LEAGUES = [s for s, v in LEAGUES.items() if v[4]]
OTHER_LEAGUES = [s for s, v in LEAGUES.items() if not v[4]]

# 单轮同步最多拉取多少场比赛详情（summary）。56 个源全量拉会拖慢启动，
# 按优先级（进行中 > 近 24h 完赛 > 重点赛事）截断。
def _detail_budget() -> int:
    try:
        from app.core.config import settings

        return settings.ESPN_DETAIL_BUDGET
    except Exception:
        return int(os.getenv("ESPN_DETAIL_BUDGET", "80"))

# ESPN 队名 -> 中文名（覆盖常见升降级球队；其余走 name_en 归一化匹配）
TEAM_CN: dict[str, str] = {
    "Manchester City": "曼城",
    "Manchester United": "曼联",
    "Liverpool": "利物浦",
    "Arsenal": "阿森纳",
    "Chelsea": "切尔西",
    "Tottenham Hotspur": "热刺",
    "Newcastle United": "纽卡斯尔",
    "Aston Villa": "阿斯顿维拉",
    "West Ham United": "西汉姆联",
    "Brighton & Hove Albion": "布莱顿",
    "Everton": "埃弗顿",
    "Wolverhampton Wanderers": "狼队",
    "AFC Bournemouth": "伯恩茅斯",
    "Bournemouth": "伯恩茅斯",
    "Leeds United": "利兹联",
    "Crystal Palace": "水晶宫",
    "Sunderland": "桑德兰",
    "Fulham": "富勒姆",
    "Nottingham Forest": "诺丁汉森林",
    "Brentford": "布伦特福德",
    "Burnley": "伯恩利",
    "Real Madrid": "皇家马德里",
    "FC Barcelona": "巴塞罗那",
    "Barcelona": "巴塞罗那",
    "Atlético Madrid": "马德里竞技",
    "Atletico Madrid": "马德里竞技",
    "Sevilla": "塞维利亚",
    "Real Betis": "皇家贝蒂斯",
    "Villarreal": "比利亚雷亚尔",
    "Valencia": "瓦伦西亚",
    "Real Sociedad": "皇家社会",
    "Athletic Club": "毕尔巴鄂竞技",
    "Getafe": "赫塔菲",
    "Málaga": "马拉加",
    "Malaga": "马拉加",
    "Deportivo": "拉科鲁尼亚",
    "Celta Vigo": "塞尔塔",
    "Espanyol": "西班牙人",
    "Osasuna": "奥萨苏纳",
    "Rayo Vallecano": "巴列卡诺",
    "Real Valladolid": "巴拉多利德",
    "Girona": "赫罗纳",
    "Mallorca": "马略卡",
    "Inter Milan": "国际米兰",
    "Internazionale": "国际米兰",
    "AC Milan": "AC米兰",
    "Juventus": "尤文图斯",
    "Napoli": "那不勒斯",
    "AS Roma": "罗马",
    "Roma": "罗马",
    "Lazio": "拉齐奥",
    "Atalanta": "亚特兰大",
    "Fiorentina": "佛罗伦萨",
    "Bologna": "博洛尼亚",
    "Torino": "都灵",
    "Udinese": "乌迪内斯",
    "Genoa": "热那亚",
    "Como": "科莫",
    "Frosinone": "弗罗西诺内",
    "Parma": "帕尔马",
    "Cagliari": "卡利亚里",
    "Lecce": "莱切",
    "Empoli": "恩波利",
    "Sassuolo": "萨索洛",
    "Verona": "维罗纳",
    "Monza": "蒙扎",
    "Bayern Munich": "拜仁慕尼黑",
    "Borussia Dortmund": "多特蒙德",
    "RB Leipzig": "莱比锡红牛",
    "Bayer Leverkusen": "勒沃库森",
    "Eintracht Frankfurt": "法兰克福",
    "法兰克福": "法兰克福",
    "Borussia Monchengladbach": "门兴格拉德巴赫",
    "VfB Stuttgart": "斯图加特",
    "Werder Bremen": "云达不来梅",
    "SC Freiburg": "弗赖堡",
    "1899 Hoffenheim": "霍芬海姆",
    "TSG Hoffenheim": "霍芬海姆",
    "VfL Wolfsburg": "沃尔夫斯堡",
    "Union Berlin": "柏林联合",
    "FSV Mainz 05": "美因茨",
    "Schalke 04": "沙尔克04",
    "SV Elversberg": "埃尔弗斯贝格",
    "SC Paderborn 07": "帕德博恩",
    "1. FC Koln": "科隆",
    "FC Cologne": "科隆",
    "Hamburger SV": "汉堡",
    "Hertha Berlin": "柏林赫塔",
    "FC Augsburg": "奥格斯堡",
    "Paris Saint-Germain": "巴黎圣日耳曼",
    "Marseille": "马赛",
    "Olympique de Marseille": "马赛",
    "AS Monaco": "摩纳哥",
    "Monaco": "摩纳哥",
    "Lille": "里尔",
    "Lyon": "里昂",
    "Nice": "尼斯",
    "Lens": "朗斯",
    "Stade Rennais": "雷恩",
    "Rennes": "雷恩",
    "Stade Brest": "布雷斯特",
    "Brest": "布雷斯特",
    "AJ Auxerre": "欧塞尔",
    "Auxerre": "欧塞尔",
    "Nantes": "南特",
    "RC Strasbourg": "斯特拉斯堡",
    "Strasbourg": "斯特拉斯堡",
    "Toulouse": "图卢兹",
    "Montpellier": "蒙彼利埃",
    "Le Havre": "勒阿弗尔",
    "Angers": "昂热",
    "Reims": "兰斯",
    "Argentina": "阿根廷",
    "Brazil": "巴西",
    "France": "法国",
    "England": "英格兰",
    "Spain": "西班牙",
    "Germany": "德国",
    "Portugal": "葡萄牙",
    "Netherlands": "荷兰",
    "Italy": "意大利",
    "Belgium": "比利时",
    "Croatia": "克罗地亚",
    "Uruguay": "乌拉圭",
    "Colombia": "哥伦比亚",
    "Mexico": "墨西哥",
    "United States": "美国",
    "USA": "美国",
    "Morocco": "摩洛哥",
    "Senegal": "塞内加尔",
    "Japan": "日本",
    "South Korea": "韩国",
    "Korea Republic": "韩国",
    "Australia": "澳大利亚",
    "Canada": "加拿大",
    "Chile": "智利",
    "Ecuador": "厄瓜多尔",
    "Paraguay": "巴拉圭",
    "Peru": "秘鲁",
    "Uzbekistan": "乌兹别克斯坦",
    "Jordan": "约旦",
    "Iran": "伊朗",
    "Iraq": "伊拉克",
    "Saudi Arabia": "沙特阿拉伯",
    "Qatar": "卡塔尔",
    "Australia national team": "澳大利亚",
    "Burkina Faso": "布基纳法索",
    "Ghana": "加纳",
    "Nigeria": "尼日利亚",
    "Cameroon": "喀麦隆",
    "Tunisia": "突尼斯",
    "Ivory Coast": "科特迪瓦",
    "Côte d'Ivoire": "科特迪瓦",
    "Switzerland": "瑞士",
    "Austria": "奥地利",
    "Denmark": "丹麦",
    "Sweden": "瑞典",
    "Norway": "挪威",
    "Poland": "波兰",
    "Serbia": "塞尔维亚",
    "Turkey": "土耳其",
    "Ukraine": "乌克兰",
    "Scotland": "苏格兰",
    "Wales": "威尔士",
    "Republic of Ireland": "爱尔兰",
    "Northern Ireland": "北爱尔兰",
    "Finland": "芬兰",
    "Iceland": "冰岛",
    "Czechia": "捷克",
    "Greece": "希腊",
    "Russia": "俄罗斯",
    "Israel": "以色列",
    "Algeria": "阿尔及利亚",
    "Egypt": "埃及",
    "South Africa": "南非",
    "New Zealand": "新西兰",
    "China": "中国",
    "China PR": "中国",
    "Saudi": "沙特阿拉伯",
    "Kuwait": "科威特",
    "Estonia": "爱沙尼亚",
    "Luxembourg": "卢森堡",
    "Belarus": "白俄罗斯",
    "San Marino": "圣马力诺",
    "Bulgaria": "保加利亚",
    "Slovenia": "斯洛文尼亚",
    "North Macedonia": "北马其顿",
    "Macedonia": "北马其顿",
    "Montenegro": "黑山",
    "Bosnia and Herzegovina": "波黑",
    "Bosnia": "波黑",
    "Albania": "阿尔巴尼亚",
    "Armenia": "亚美尼亚",
    "Azerbaijan": "阿塞拜疆",
    "Georgia": "格鲁吉亚",
    "Kazakhstan": "哈萨克斯坦",
    "Malta": "马耳他",
    "Cyprus": "塞浦路斯",
    "Fiji": "斐济",
    "Vanuatu": "瓦努阿图",
    "Sri Lanka": "斯里兰卡",
    "Djibouti": "吉布提",
    "Namibia": "纳米比亚",
    "Mali": "马里",
    "Zambia": "赞比亚",
    "Zimbabwe": "津巴布韦",
    "Kenya": "肯尼亚",
    "Tanzania": "坦桑尼亚",
    "Uganda": "乌干达",
    "Rwanda": "卢旺达",
    "Mozambique": "莫桑比克",
    "Angola": "安哥拉",
    "DR Congo": "刚果民主共和国",
    "Congo": "刚果",
    "Gabon": "加蓬",
    "Equatorial Guinea": "赤道几内亚",
    "Cape Verde": "佛得角",
    "Mauritania": "毛里塔尼亚",
    "Guinea": "几内亚",
    "Sierra Leone": "塞拉利昂",
    "Liberia": "利比里亚",
    "Gambia": "冈比亚",
    "Burundi": "布隆迪",
    "Madagascar": "马达加斯加",
    "Mauritius": "毛里求斯",
    "Comoros": "科摩罗",
    "Seychelles": "塞舌尔",
    "Mauritius Islands": "毛里求斯",
    "São Tomé and Príncipe": "圣多美和普林西比",
    "Benin": "贝宁",
    "Togo": "多哥",
    "Guinea-Bissau": "几内亚比绍",
    "Sudan": "苏丹",
    "South Sudan": "南苏丹",
    "Ethiopia": "埃塞俄比亚",
    "Somalia": "索马里",
    "Djibouti Republic": "吉布提",
    "Haiti": "海地",
    "Cuba": "古巴",
    "Jamaica": "牙买加",
    "Panama": "巴拿马",
    "Costa Rica": "哥斯达黎加",
    "Honduras": "洪都拉斯",
    "Guatemala": "危地马拉",
    "El Salvador": "萨尔瓦多",
    "Nicaragua": "尼加拉瓜",
    "Trinidad and Tobago": "特立尼达和多巴哥",
    "Bolivia": "玻利维亚",
    "Venezuela": "委内瑞拉",
    "Suriname": "苏里南",
    "Guyana": "圭亚那",
    "Leverkusen": "勒沃库森",
    "Ajax": "阿贾克斯",
    "PSV Eindhoven": "埃因霍温",
    "Feyenoord": "费耶诺德",
    "Porto": "波尔图",
    "Benfica": "本菲卡",
    "Sporting CP": "里斯本竞技",
    "Club Brugge": "布鲁日",
    "Anderlecht": "安德莱赫特",
    "Rangers": "流浪者",
    "Celtic": "凯尔特人",
    "Galatasaray": "加拉塔萨雷",
    "Fenerbahce": "费内巴切",
    "Beşiktaş": "贝西克塔斯",
    "Trabzonspor": "特拉布宗",
    "Ajax Amsterdam": "阿贾克斯",
    "Sporting Lisbon": "里斯本竞技",
    "FC Porto": "波尔图",
    "Club Brugge KV": "布鲁日",
    "Dinamo Zagreb": "萨格勒布迪纳摩",
    "Olympiacos": "奥林匹亚科斯",
    "PAOK": "PAOK",
    "Red Star Belgrade": "贝尔格莱德红星",
    "Partizan": "游击队",
    "Malmö FF": "马尔默",
    "FC Copenhagen": "哥本哈根",
    "Celtic FC": "凯尔特人",
    "Olympiacos FC": "奥林匹亚科斯",
    "Dinamo Kyiv": "基辅迪纳摩",
    "Shakhtar Donetsk": "顿涅茨克矿工",
    "Crvena zvezda": "贝尔格莱德红星",
    "Lech Poznan": "波兹南莱赫",
    "Rangers FC": "流浪者",
    "Hapoel Be'er Sheva": "贝尔谢巴工人",
    "AZ Alkmaar": "阿尔克马尔",
    "CSKA Sofia": "索菲亚中央陆军",
    "CSU Craiova": "克拉约瓦大学",
    "Getafe CF": "赫塔菲",
    "Feyenoord Rotterdam": "费耶诺德",
    "Celtic Glasgow": "凯尔特人",
    "Panathinaikos": "帕纳辛奈科斯",
    "Olympiakos Piraeus": "奥林匹亚科斯",
    "Al Ahly": "阿赫利",
    "Al Hilal": "利雅得新月",
    "Al Nassr": "利雅得胜利",
    "Al Sadd": "阿尔萨德",
    "Al Qadsiah": "卡迪西亚",
    "Al Wasl": "阿尔瓦斯尔",
    "Urawa Red Diamonds": "浦和红钻",
    "Kashima Antlers": "鹿岛鹿角",
    "Gamba Osaka": "大阪钢巴",
    "Kashiwa Reysol": "柏太阳神",
    "Vissel Kobe": "神户胜利船",
    "Yokohama F. Marinos": "横滨水手",
    "FC Seoul": "首尔FC",
    "Jeonbuk Hyundai Motors": "全北现代",
    "Ulsan HD": "蔚山现代",
    "Shanghai Port": "上海海港",
    "Shanghai Shenhua": "上海申花",
    "Beijing Guoan": "北京国安",
    "Shenzhen Xinpengcheng": "深圳新鹏城",
    "Qingdao Hainiu": "青岛海牛",
    "Henan": "河南队",
    "Chengdu Rongcheng": "成都蓉城",
    "Zhejiang": "浙江队",
    "Tianjin Jinmen Tiger": "天津津门虎",
    "Al-Qadsiah": "卡迪西亚",
    "Johor Darul Ta'zim": "柔佛新山",
    "Ulsan Hyundai": "蔚山现代",
    "Buriram United": "武里南联",
    "Al-Ittihad": "吉达联合",
    "Al Shabab": "阿尔沙巴",
    "Al Fateh": "法塔赫",
    "Konyaspor": "科尼亚",
    "Basaksehir": "巴萨克赛尔",
    "Inter Miami": "迈阿密国际",
    "LA Galaxy": "洛杉矶银河",
    "Seattle Sounders": "西雅图海湾人",
    "LAFC": "洛杉矶FC",
    "New York City FC": "纽约城",
    "New York Red Bulls": "纽约红牛",
    "Atlanta United": "亚特兰大联",
    "Portland Timbers": "波特兰伐木者",
    "Columbus Crew": "哥伦布机员",
    "Chicago Fire FC": "芝加哥火焰",
    "Vancouver Whitecaps": "温哥华白帽",
    "FC Cincinnati": "辛辛那提",
    "Tigres UANL": "老虎队",
    "Toluca": "托卢卡",
    "Puebla": "普埃布拉",
    "León": "莱昂",
    "Club América": "美洲俱乐部",
    "Guadalajara": "瓜达拉哈拉",
    "Monterrey": "蒙特雷",
    "Flamengo": "弗拉门戈",
    "Palmeiras": "帕尔梅拉斯",
    "Corinthians": "科林蒂安",
    "São Paulo": "圣保罗",
    "Grêmio": "格雷米奥",
    "Internacional": "国际",
    "Atlético Mineiro": "米内罗竞技",
    "Cruzeiro": "克鲁塞罗",
    "Botafogo": "博塔弗戈",
    "Vasco da Gama": "瓦斯科",
    "Fluminense": "弗鲁米嫩塞",
    "Santos": "桑托斯",
    "River Plate": "河床",
    "Boca Juniors": "博卡青年",
    "Racing Club": "竞技俱乐部",
    "Estudiantes": "学生队",
    "Vélez Sarsfield": "贝莱斯",
    "San Lorenzo": "圣洛伦索",
    "Independiente": "独立",
    "Talleres": "塔勒瑞斯",
    "Lanús": "拉努斯",
    "Colo-Colo": "科洛科罗",
    "Universidad de Chile": "智利大学",
    "Universidad Catolica": "天主教大学",
    "Sydney FC": "悉尼FC",
    "Western Sydney Wanderers": "西悉尼流浪者",
    "Melbourne Victory": "墨尔本胜利",
    "Auckland City": "奥克兰城",
    "Bengaluru FC": "班加罗尔",
    "FC Goa": "果阿",
    "Chennaiyin FC": "金奈城",
    "Sporting Club Delhi": "德里体育",
    "Mumbai City": "孟买城",
    "Bangkok United": "曼谷联",
    "Buriram United FC": "武里南联",
    "BG Pathum United": "巴吞叻联",
    "Persib Bandung": "万隆",
    "Al-Faisaly": "费萨利",
    "Zhejiang Professional FC": "浙江队",
    "Zhejiang FC": "浙江队",
    "Rostov": "罗斯托夫",
    "Kasimpasa": "卡斯基帕萨",
    "Kasımpaşa": "卡斯基帕萨",
    "Cerezo Osaka": "大阪樱花",
    "Shonan Bellmare": "湘南比马",
    "FC Tokyo": "东京FC",
    "Urawa Reds": "浦和红钻",
    "Sanfrecce Hiroshima": "广岛三箭",
    "Avispa Fukuoka": "福冈黄蜂",
    "Nagoya Grampus": "名古屋鲸八",
    "Consadole Sapporo": "札幌冈萨多",
    "Vegalta Sendai": "仙台七夕",
    "Reykjavik": "雷克雅未克",
    "Víkingur Reykjavík": "维京人",
    "Fenerbahçe": "费内巴切",
    "Maccabi Tel Aviv": "特拉维夫马卡比",
    "Hapoel Tel Aviv": "海法工人",
    "PAOK FC": "塞萨洛尼基",
    "Partizan Belgrade": "游击队",
    "Legia Warsaw": "华沙莱吉亚",
    "Raków Częstochowa": "拉科夫",
    "Hibernian": "希伯尼安",
    "Aberdeen": "阿伯丁",
    "Hearts": "哈茨",
    "Dundee United": "邓迪联",
    "Dundee FC": "邓迪",
    "Falkirk": "福尔柯克",
    "Motherwell": "马瑟韦尔",
    "Kilmarnock": "基尔马诺克",
    "St Mirren": "圣米伦",
    "Livingston": "利文斯顿",
    "AEK Athens": "雅典AEK",
    "OFI Crete": "克里特",
    "Asteras Tripoli": "阿斯特拉斯",
    "Atromitos": "阿特罗米托斯",
    "Panionios": "帕尼约尼奥斯",
    "Olympiacos Volos": "沃洛斯奥利匹亚科斯",
    "Braga": "布拉加",
    "Casa Pia": "卡萨皮亚",
    "Estoril": "埃斯托里尔",
    "Dundee": "邓迪",
    "Raith Rovers": "拉夫流浪",
    "Arbroath": "阿布罗斯",
    "Ayr United": "艾尔联",
    "Airdrieonians": "艾德里",
    "Albion FC": "阿尔比恩",
    "Partick Thistle": "帕蒂克",
    "Queen's Park": "皇后公园",
    "Inverness Caledonian Thistle": "因弗内斯",
    "Greenock Morton": "莫顿",
    "Krylia Sovetov": "苏维埃之翼",
    "Dynamo Moscow": "莫斯科中央陆军",
    "Zenit St. Petersburg": "圣彼得堡泽尼特",
    "CSKA Moscow": "莫斯科中央陆军",
    "Spartak Moscow": "莫斯科斯巴达",
    "Atlético-MG": "米内罗竞技",
    "Atlético Tucumán": "图库曼竞技",
    "Defensa y Justicia": "正义之剑",
    "Defensor Sporting": "防守者运动",
    "Barracas Central": "巴拉卡斯中央",
    "Deportes Tolima": "托利马",
    "Boyacá Chicó FC": "博伊卡奇奥",
    "Cienciano del Cusco": "库斯科百万富翁",
    "Deportivo Maldonado": "马尔多尼多",
    "Central Español": "西班牙人中央",
    "Central Español Fútbol Club": "西班牙人中央",
    "WSG Swarovski Tirol": "蒂罗尔",
    "Once Caldas": "万卡莱斯",
    "Alianza": "阿利安萨",
    "Melgar": "梅尔加",
    "Sport Huancayo": "万卡约",
    "UTC": "UTC",
    "Aucas": "奥卡斯",
    "Emelec": "埃梅莱克",
    "Libertad": "自由队",
    "Cerro Porteño": "塞罗波特尼奥",
    "Olimpia": "奥林匹亚",
    "Nacional": "纳西奥纳尔",
    "Al-Hilal": "利雅得新月",
    "Al Taawoun": "塔亚文",
    "Al Fayha": "费哈",
    "Al Okhdood": "奥克杜德",
    "Al Raed": "拉艾德",
    "Al Ettifaq": "艾杜哈",
    "Damac": "达马克",
    "Al Wehda": "瓦赫达",
    "Al Riyadh": "利雅得",
    "Gaziantep FK": "加济安泰普",
    "Antalyaspor": "安塔利亚",
    "Rizespor": "里泽",
    "Samsunspor": "萨姆松",
    "Alanyaspor": "阿兰亚",
    "Kayserispor": "开塞利",
    "Göztepe": "格茨塔比",
    "Başakşehir": "巴萨克赛尔",
    "Panathinaikos FC": "帕纳辛奈科斯",
    "AEK Athens FC": "雅典AEK",
    "Hapoel Haifa": "海法工人",
    "Beitar Jerusalem": "贝塔耶路撒冷",
    "AZ Alkmaar FC": "阿尔克马尔",
    "SC Braga": "布拉加",
    "RSC Anderlecht": "安德莱赫特",
    "Union Saint-Gilloise": "圣吉罗斯联",
    "Villarreal CF": "比利亚雷亚尔",
    "Real Betis Balompié": "皇家贝蒂斯",
    "Celta de Vigo": "塞尔塔",
    "Rayo Vallecano de Madrid": "巴列卡诺",
    "Atlético de Madrid": "马德里竞技",
    "Real Madrid CF": "皇家马德里",
    "Sevilla FC": "塞维利亚",
    "Valencia CF": "瓦伦西亚",
    "Real Sociedad de Fútbol": "皇家社会",
    "Deportivo Alavés": "阿拉维斯",
    "Girona FC": "赫罗纳",
    "CA Osasuna": "奥萨苏纳",
    "RCD Espanyol de Barcelona": "西班牙人",
    "Levante UD": "莱万特",
    "Deportivo La Coruña": "拉科鲁尼亚",
    "Cádiz CF": "加的斯",
    "Standard Liège": "标准列日",
    "Royal Antwerp FC": "安特卫普",
    "Gent": "根特",
    "Cercle Brugge": "塞克莱布鲁日",
    "PSV": "埃因霍温",
    "AZ": "阿尔克马尔",
    "FC Utrecht": "乌德勒支",
    "Twente": "特温特",
    "Aberdeen FC": "阿伯丁",
    "Hearts FC": "哈茨",
    "Hibernian FC": "希伯尼安",
    "Motherwell FC": "马瑟韦尔",
    "St Mirren FC": "圣米伦",
    "Kilmarnock FC": "基尔马诺克",
    "Dundee United FC": "邓迪联",
    "15 de Agosto": "八月十五日",
    "Akron Tolyatti": "阿克伦",
    "Austria Vienna": "维也纳快速",
    "FC Nordsjælland": "北西兰",
    "Fomboni": "丰博尼",
    "Gil Vicente": "吉马良斯",
    "Grazer AK": "格拉茨风暴",
    "Heart of Midlothian": "哈茨",
    "Heerenveen": "海伦芬",
    "Huachipato": "瓦奇帕托",
    "IFK Göteborg": "哥德堡",
    "Ipswich Town": "伊普斯维奇",
    "Jaguares de Córdoba": "科尔多瓦美洲",
    "Lommel SK": "洛默尔",
    "Los Chankas": "尚卡斯",
    "Moreirense": "莫雷伦斯",
    "Newell's Old Boys": "纽维尔老男孩",
    "Odense Boldklub": "奥登塞",
    "Progreso": "普罗格雷索",
    "RB Salzburg": "萨尔茨堡红牛",
    "Red Bull Bragantino": "布拉干蒂诺红牛",
    "SK Brann": "布兰",
    "SK Sturm Graz": "格拉茨风暴",
    "SV Josko Ried": "里德",
    "Universidad de Concepción": "康塞普西翁大学",
    "Viking FK": "维京",
    "Västerås SK": "韦斯特罗斯",
    "Waasland-Beveren": "瓦斯特兰贝韦伦",
    "Águilas Doradas": "金色雄鹰",
    "Universidad Católica": "天主教大学",
    "India": "印度",
    "Egnatia": "埃格纳蒂亚",
    "FC Midtjylland": "中日德兰",
    "Hajduk Split": "哈伊杜克",
    "KAA Gent": "根特",
    "AGF": "奥胡斯",
    "KuPS Kuopio": "库普斯",
    "Mjällby AIF": "米亚尔比",
    "Inter D'Escaldes": "埃斯卡尔德斯",
    "Borac Banja Luka": "巴尼亚卢卡战士",
    "Riga FC": "里加",
    "Kairat Almaty": "阿拉木图凯拉特",
    "Ferencvaros": "费伦茨瓦罗斯",
    "Viktoria Plzen": "布拉格斯拉发",
    "Jagiellonia Bialystok": "雅格隆尼亚",
    "Ararat-Armenia": "阿拉拉特",
    "NEC Nijmegen": "奈梅亨",
    "Levski Sofia": "索菲亚列夫斯基",
    "Pafos": "帕福斯",
    "Kauno Zalgiris": "考诺萨基列斯",
    "F.C. København": "哥本哈根",
    "FC Thun": "图恩",
    "Jablonec": "伊林娜特斯",
    "Sint-Truidense": "圣特雷登",
    "Iberia 1999": "伊比利亚",
    "Lincoln Red Imps": "林肯红魔",
    "Besiktas": "贝西克塔斯",
    "Riga": "里加",
    "AGF Aarhus": "奥胡斯",
    "B34 Torshavn": "托尔斯港",
    "The New Saints": "新圣徒",
    "Larne FC": "拉恩",
    "Caernarfon Town": "卡那封城",
    "Connah's Quay": "康纳斯码头",
    "Rhyl": "里尔",
    "Barry Town United": "巴里城",
    "TNS": "新圣徒",
    "Penafiel": "佩纳菲耶尔",
    "Celje": "采列",
    "Panevėžys": "帕涅韦日斯",
    "Ballkani": "巴尔卡尼",
    "KÍ Klaksvík": "克拉克斯维克",
    "Víkingur Gøta": "戈塔维京人",
    "HB Torshavn": "托尔斯港",
    "Inter Club d'Escaldes": "埃斯卡尔德斯",
    "FC Dacia Buiucani": "达契亚",
    "FC Sheriff Tiraspol": "谢尔福",
    "Zrinjski Mostar": "莫斯塔尔",
    "Hapoel Beer Sheva": "贝尔谢巴工人",
    "Maccabi Tel Aviv FC": "特拉维夫马卡比",
    "Olimpija Ljubljana": "卢布尔雅那奥林匹亚",
    "Dinamo Zagreb DK": "萨格勒布迪纳摩",
    "Egnatia Rrogozhine": "埃格纳蒂亚",
    "Viktoria Plzen FK": "布拉格斯拉发",
    "Racing Ferrol": "费罗尔",
    "Omonia Nicosia": "奥莫尼亚",
    "APOEL": "尼科西亚APOEL",
    "AEK Larnaca": "拉纳卡AEK",
    "AEL Limassol": "利马索尔AEL",
    "Pafos FC": "帕福斯",
    "KÍ": "克拉克斯维克",
    "Víkingur": "维京人",
    "Connah's Quay FC": "康纳斯码头",
    "Air Force Club": "空军俱乐部",
    "Al Ahli": "阿赫利",
    "Al Ain": "艾因",
    "Al Gharafa": "加拉法",
    "Al Shamal": "沙马尔",
    "AmaZulu": "阿马祖鲁",
    "Durban City": "德班城",
    "Esteghlal": "埃斯特格拉勒",
    "FC Lugano": "卢加诺",
    "FC Twente": "特温特",
    "Hapoel Be'er": "贝尔谢巴工人",
    "Kaizer Chiefs": "凯撒酋长",
    "Lillestrom": "利勒斯特罗姆",
    "Mamelodi Sundowns": "马姆罗迪日落",
    "NK Celje": "采列",
    "Neftchi Fergana": "费尔干纳",
    "Orlando Pirates": "奥兰多海盗",
    "Pakhtakor Tashkent": "塔什干棉农",
    "Richards Bay FC": "理查兹湾",
    "Sabah FK": "萨巴赫",
    "Al Ahli SC": "阿赫利",
    "Al-Ahli": "阿赫利",
    "Al Hilal SFC": "利雅得新月",
    "Al Sadd SC": "阿尔萨德",
    "Al-Arabi": "阿拉伯",
    "Al-Sadd": "阿尔萨德",
    "Al-Fateh": "法塔赫",
    "Al-Tai": "塔伊",
    "Al-Khaleej": "海湾",
    "Al-Orobah": "欧鲁巴",
    "Al-Raed": "拉艾德",
    "Al-Fayha": "费哈",
    "Al-Hazem": "哈泽姆",
    "Al-Wehda": "瓦赫达",
    "Okazaki Kosei": "冈崎喜悦",
    "Kashiwa Reysol FC": "柏太阳神",
    "Reykjavík": "雷克雅未克",
    "Breiðablik": "贝雷达比力克",
    "KA Akureyri": "阿克雷里",
    "FH Hafnarfjörður": "哈夫纳夫约杜尔",
    "Valur": "瓦鲁尔",
    "B36 Tórshavn": "托尔斯港B36",
    "NSÍ Runavík": "鲁纳维克",
    "HB Tórshavn": "托尔斯港HB",
    "FC Suðuroy": "苏ðuroy",
    "B68 Toftir": "托夫蒂尔",
    "Víkingur Gøta FC": "戈塔维京人",
    "Slavia Prague": "布拉格斯拉发",
    "Sparta Prague": "布拉格斯巴达",
    "Stellenbosch": "斯泰伦博斯",
    "TS Galaxy FC": "银河FC",
    "Torreense": "托雷恩斯",
    "Traktor Sazi FC": "拖拉机",
    "Union St.-Gilloise": "圣吉罗斯联",
    "Alianza FC": "阿利安萨",
    "América": "美洲队",
    "Andorra": "安道尔",
    "Atlético Junior": "青年人",
    "Atlético Nacional": "国民竞技",
    "Atlético de San Luis": "圣路易斯竞技",
    "Bosnia-Herzegovina": "波黑",
    "Botswana": "博茨瓦纳",
    "Cerro": "塞罗",
    "Congo DR": "刚果民主共和国",
    "Cook Islands": "库克群岛",
    "Danubio": "达努比奥",
    "Deportivo Cali": "卡利运动",
    "Deportivo Pereira": "佩雷拉运动",
    "FC Juárez": "华雷斯",
    "Faroe Islands": "法罗群岛",
    "Fortaleza CEIF": "塞伊夫",
    "Gibraltar": "直布罗陀",
    "Hungary": "匈牙利",
    "Independiente Medellín": "麦德林独立",
    "Independiente Santa Fe": "圣菲独立",
    "Juventud": "青年人",
    "Kosovo": "科索沃",
    "Kyrgyz Republic": "吉尔吉斯斯坦",
    "Latvia": "拉脱维亚",
    "Lebanon": "黎巴嫩",
    "Liechtenstein": "列支敦士登",
    "Lithuania": "立陶宛",
    "Maldives": "马尔代夫",
    "Millonarios": "百万富翁",
    "Moldova": "摩尔多瓦",
    "Montevideo Wanderers": "蒙得维的亚流浪者",
    "Necaxa": "内察哈",
    "New Caledonia": "新喀里多尼亚",
    "Palestine": "巴勒斯坦",
    "Papua New Guinea": "巴布亚新几内亚",
    "Peñarol": "佩纳罗尔",
    "Pumas UNAM": "美洲狮",
    "Romania": "罗马尼亚",
    "Slovakia": "斯洛伐克",
    "Solomon Islands": "所罗门群岛",
    "Syria": "叙利亚",
    "Tahiti": "塔希提",
    "Tajikistan": "塔吉克斯坦",
    "Turkmenistan": "土库曼斯坦",
    "Türkiye": "土耳其",
    "América de Cali": "卡利美国",
    "Montevideo City Torque": "蒙得维的亚城",
}

STATUS_MAP = {
    "STATUS_SCHEDULED": ("scheduled", None),
    "STATUS_FINAL": ("finished", 90),
    "STATUS_FULL_TIME": ("finished", 90),
    "STATUS_IN_PROGRESS": ("live", None),
    "STATUS_HALFTIME": ("halftime", 45),
    "STATUS_END_PERIOD": ("halftime", 45),
    "STATUS_POSTPONED": ("scheduled", None),
    "STATUS_DELAYED": ("scheduled", None),
    "STATUS_CANCELED": ("finished", None),
}


def _get(url: str, timeout: int = 12) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _season_label(season: Any) -> str | None:
    """ESPN 的 season 结构不稳定（type 可能是 int），取年份作为赛季名。"""
    if not isinstance(season, dict):
        return None
    yr = season.get("year")
    typ = season.get("type")
    name = typ.get("name") if isinstance(typ, dict) else None
    if name:
        return str(name)
    return f"{yr}/{str(int(yr) + 1)[-2:]}" if isinstance(yr, int) else None


def _minute(clock: str | None, fallback_state: str | None = None) -> int | None:
    """'57'' -> 57 ; \"45'+2'\" -> 45."""
    if not clock:
        return None
    m = re.search(r"(\d+)", clock)
    if not m:
        return None
    return int(m.group(1))


def fetch_scoreboard(slug: str, season: int | None = None,
                     limit: int | None = None) -> list[dict[str, Any]]:
    """拉取联赛赛程。

    - 不带 season：ESPN 返回最近一轮（含未来赛程），用于日常同步
    - season=YYYY：返回该年份全年的比赛（`?dates=YYYY&limit=N`），
      用于历史积累 —— Elo 反推与模型训练都需要大量已完赛样本
    """
    url = f"{BASE}/{slug}/scoreboard"
    if season:
        url += f"?dates={season}&limit={limit or 400}"
    d = _get(url, timeout=25 if season else 12)
    out: list[dict[str, Any]] = []
    for e in d.get("events", []):
        comp = (e.get("competitions") or [{}])[0]
        comps = comp.get("competitors") or []
        if len(comps) != 2:
            continue
        home = next((c for c in comps if c.get("homeAway") == "home"), comps[0])
        away = next((c for c in comps if c.get("homeAway") == "away"), comps[1])
        st_type = (comp.get("status") or {}).get("type") or {}
        name = st_type.get("name") or ""
        state = st_type.get("state") or ""
        status, minute = STATUS_MAP.get(name, (None, None))
        if status is None:
            status = {"pre": "scheduled", "in": "live", "post": "finished"}.get(state, "scheduled")
        if minute is None:
            minute = _minute((comp.get("status") or {}).get("displayClock"))
        if status == "scheduled":
            minute = None
        out.append({
            "event_id": str(e.get("id")),
            "slug": slug,
            "kickoff": e.get("date"),
            "home": {
                "id": str((home.get("team") or {}).get("id")),
                "name": (home.get("team") or {}).get("displayName"),
                "short": (home.get("team") or {}).get("shortDisplayName"),
                "abbr": (home.get("team") or {}).get("abbreviation"),
                "color": (home.get("team") or {}).get("color"),
            },
            "away": {
                "id": str((away.get("team") or {}).get("id")),
                "name": (away.get("team") or {}).get("displayName"),
                "short": (away.get("team") or {}).get("shortDisplayName"),
                "abbr": (away.get("team") or {}).get("abbreviation"),
                "color": (away.get("team") or {}).get("color"),
            },
            "status": status,
            "minute": minute,
            "score_home": _to_int(home.get("score")),
            "score_away": _to_int(away.get("score")),
            "venue": ((comp.get("venue") or {}) if isinstance(comp.get("venue"), dict) else {}).get("fullName"),
            "round": _season_label(e.get("season")),
        })
    return out


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_summary(slug: str, event_id: str) -> dict[str, Any]:
    """比赛详情：关键事件 + boxscore 技术统计。"""
    d = _get(f"{BASE}/{slug}/summary?event={event_id}", timeout=15)
    events: list[dict[str, Any]] = []
    for e in d.get("keyEvents", []) or []:
        etype = ((e.get("type") or {}).get("text") or "").lower()
        minute = _minute((e.get("clock") or {}).get("displayValue")) or 0
        side = None
        team_id = str((e.get("team") or {}).get("id") or "")
        if "goal" in etype and "disallow" not in etype and "own" not in etype:
            kind = "goal"
        elif "yellow" in etype:
            kind = "yellow_card"
        elif "red" in etype:
            kind = "red_card"
        elif "substitut" in etype:
            kind = "substitution"
        elif "penalty" in etype and "miss" not in etype:
            kind = "goal"
        else:
            continue
        athletes = e.get("athletesInvolved") or []
        player = athletes[0].get("displayName") if athletes else None
        related = athletes[1].get("displayName") if len(athletes) > 1 else None
        if player is None and e.get("text"):
            # 文本兜底："Goal! ... Alexander Isak (Liverpool) ..."
            m = re.search(r"\.\s*([A-Z][\w\'\-\. ]+)\s*\(", e["text"])
            player = m.group(1).strip() if m else None
        events.append({
            "minute": minute, "type": kind, "team_id": team_id,
            "player": player, "related": related, "detail": e.get("text"),
        })
    stats: dict[str, Any] = {}
    for t in (d.get("boxscore") or {}).get("teams", []) or []:
        vals = {s.get("name"): s.get("displayValue") for s in t.get("statistics", []) or []}
        stats[str((t.get("team") or {}).get("id"))] = vals
    return {"events": events, "stats": stats, "raw": d}


# ---------------- 同步（写入本地库） ----------------

def _norm(name: str | None) -> str:
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(fc|cf|afc|sc|sv|as|ss|ac|real|club|de|the)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _resolve_team(db: Session, info: dict[str, Any], league_id: int, league_cn: str,
                  ctype: str = "domestic"):
    """ESPN 球队 -> 本地 Team（先查 provider_team_id，再按中文别名/英文名匹配，缺失则新建）。

    60+ 赛事源会带来数千支球队，name 归一化匹配必须走缓存，否则退化为 O(比赛×球队)。
    ctype='national' 时只用「英文名在该国家队赛事内」匹配，避免国家队与同名俱乐部
    （巴西/西班牙/美国…）被合并成一支球队。
    """
    from app.models import Team, TeamRating

    name = info.get("name") or "Unknown"
    espn_id = info.get("id")

    # 1) provider_team_id 命中（同一球队在联赛/洲际赛事间共享同一条记录）
    t = _TEAM_BY_ID.get(espn_id)
    if t is None:
        t = db.query(Team).filter(Team.provider_team_id == espn_id).first()
        if t:
            _TEAM_BY_ID[espn_id] = t
    cn = TEAM_CN.get(name)
    if t:
        # 补齐中文名：字典后续新增的翻译要能覆盖早期同步留下的英文名
        if cn and t.name != cn:
            t.name = cn
            t.short_name = cn[:2]
            _TEAM_BY_CN[cn] = t
        return t

    # 2) 中文别名 / 英文名归一化匹配（跨赛事复用同一球队，如曼城在英超与欧冠）
    if ctype == "national":
        # 国家队：只在同类型赛事内按英文名匹配，不与俱乐部混用
        t = _NATION_BY_NORM.get(_norm(name))
        if t is not None:
            t.provider = "espn"
            if not t.provider_team_id:
                t.provider_team_id = espn_id
            if cn and t.name != cn:
                t.name = cn
            db.flush()
            _TEAM_BY_ID[espn_id] = t
            _NATION_BY_NORM[_norm(t.name_en)] = t
            return t
    else:
        t = _TEAM_BY_CN.get(cn or "") or _TEAM_BY_NORM.get(_norm(name))
        if t is not None:
            t.provider = "espn"
            if not t.provider_team_id:
                t.provider_team_id = espn_id
            # 补齐中文名：字典后续新增的翻译要能覆盖早期同步留下的英文名
            if cn and t.name != cn:
                t.name = cn
            db.flush()
            _TEAM_BY_ID[espn_id] = t
            _TEAM_BY_CN[t.name] = t
            _TEAM_BY_NORM[_norm(t.name_en)] = t
            return t

    # 3) 新建真实球队（默认 Elo/TPI，避免污染模拟球队的评级）
    # short_name 用于队徽圆圈：有中文名时取中文前 2 字，否则退回 ESPN 缩写
    if cn:
        short = cn[:2]
    else:
        short = (info.get("abbr") or info.get("short") or name)[:4].upper()
    t = Team(
        league_id=league_id, name=cn or name, name_en=name,
        short_name=short, country=league_cn,
        color=f"#{(info.get('color') or '333333').lstrip('#')}"[:7],
        elo_rating=1500.0, stadium=info.get("venue") or f"{name}球场",
        provider="espn", provider_team_id=espn_id,
    )
    db.add(t)
    db.flush()
    db.add(TeamRating(
        team_id=t.id, tpi=50.0, attack=50.0, defense=50.0, form=50.0,
        possession=50.0, pressing=50.0, efficiency=50.0,
        breakdown={"form_last10": [], "season": {}, "source": "espn"},
    ))
    db.flush()
    _TEAM_BY_ID[espn_id] = t
    _TEAM_BY_CN[t.name] = t
    _TEAM_BY_NORM[_norm(t.name_en)] = t
    if ctype == "national":
        _NATION_BY_NORM[_norm(t.name_en)] = t
    return t


# 球队索引缓存：espn_team_id / 中文名 / 归一化英文名 -> Team 实例（每次 sync 重建）
_TEAM_BY_ID: dict[str, Any] = {}
_TEAM_BY_CN: dict[str, Any] = {}
_TEAM_BY_NORM: dict[str, Any] = {}
_NATION_BY_NORM: dict[str, Any] = {}


def rebuild_team_index(db: Session) -> None:
    """同步开始时重建球队索引，避免逐场全表扫描。"""
    from app.models import League, Team

    _TEAM_BY_ID.clear()
    _TEAM_BY_CN.clear()
    _TEAM_BY_NORM.clear()
    _NATION_BY_NORM.clear()
    national_ids = {
        l.id for l in db.query(League).filter(League.competition_type == "national").all()
    }
    for t in db.query(Team).all():
        if t.provider_team_id:
            _TEAM_BY_ID.setdefault(t.provider_team_id, t)
        _TEAM_BY_CN.setdefault(t.name, t)
        _TEAM_BY_NORM.setdefault(_norm(t.name_en), t)
        if t.league_id in national_ids:
            _NATION_BY_NORM.setdefault(_norm(t.name_en), t)


def _resolve_league(db: Session, slug: str):
    from app.models import League, Season

    cn, en, short, region, is_key = LEAGUES[slug]
    lg = db.query(League).filter(League.name == cn).first()
    if not lg:
        # competition_type: 洲际俱乐部赛事 / 国家队赛事 / 各国联赛
        if region == "洲际赛事":
            ctype = "continental"
        elif region == "国家队":
            ctype = "national"
        else:
            ctype = "domestic"
        lg = League(name=cn, name_en=en, short_name=short, country=region,
                    competition_type=ctype, is_key=is_key)
        db.add(lg)
        db.flush()
        # Season 的 start/end_date 是 NOT NULL，用赛季名做锚点补齐
        from datetime import date as _date

        db.add(Season(
            league_id=lg.id, name="2026/27",
            start_date=_date(2026, 7, 1), end_date=_date(2027, 6, 30),
            is_current=True,
        ))
        db.flush()
    else:
        lg.country, lg.competition_type, lg.is_key = region, (
            "continental" if region == "洲际赛事"
            else "national" if region == "国家队" else "domestic"
        ), is_key
    return lg


def _upsert_prediction(db: Session, m, home_elo: float, away_elo: float) -> None:
    from app.core.predictor import prematch
    from app.models import MatchPrediction

    pred = prematch(home_elo, away_elo)
    try:
        from app.ml.train import blend, predict_proba

        ml = predict_proba(home_elo - away_elo, 0.5, 0.5)
        pred = blend(pred, ml)
    except Exception:
        pred["model_version"] = "dc-only-v0.1"
    row = m.prediction
    if row is None:
        row = MatchPrediction(match_id=m.id, **pred)
        db.add(row)
    else:
        for k, v in pred.items():
            setattr(row, k, v)


def _stats_payload(stats: dict[str, Any], home_id: str, away_id: str) -> dict[str, Any] | None:
    h = stats.get(home_id) or {}
    a = stats.get(away_id) or {}
    if not h and not a:
        return None

    def g(d: dict, key: str, default: float = 0.0) -> float:
        try:
            return float(d.get(key, default))
        except (TypeError, ValueError):
            return default

    return {
        "minute": 90,
        "possession_home": round(g(h, "possessionPct", 50.0)),
        "shots_home": int(g(h, "totalShots")), "shots_away": int(g(a, "totalShots")),
        "shots_on_target_home": int(g(h, "shotsOnTarget")),
        "shots_on_target_away": int(g(a, "shotsOnTarget")),
        "corners_home": int(g(h, "wonCorners")), "corners_away": int(g(a, "wonCorners")),
        "fouls_home": int(g(h, "foulsCommitted")), "fouls_away": int(g(a, "foulsCommitted")),
        "yellow_home": int(g(h, "yellowCards")), "yellow_away": int(g(a, "yellowCards")),
        "red_home": int(g(h, "redCards")), "red_away": int(g(a, "redCards")),
        "dangerous_home": int(g(h, "totalShots") * 4), "dangerous_away": int(g(a, "totalShots") * 4),
        "xg_home": round(g(h, "totalShots") * 0.11, 2),
        "xg_away": round(g(a, "totalShots") * 0.11, 2),
    }


_last_sync: dict[str, Any] = {"ok": None, "at": None, "matches": 0, "error": None}


def last_sync() -> dict[str, Any]:
    return dict(_last_sync)


def _fetch_all_scoreboards() -> dict[str, list[dict[str, Any]]]:
    """并发拉取所有联赛的 scoreboard（60+ 源，串行会非常慢）。"""
    slugs = list(LEAGUES)
    out: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        for slug, rows in zip(slugs, pool.map(_safe_scoreboard, slugs)):
            if rows:
                out[slug] = rows
    return out


def _safe_scoreboard(slug: str) -> list[dict[str, Any]]:
    try:
        return fetch_scoreboard(slug)
    except Exception:
        return []


def _safe_season(slug: str, year: int) -> list[dict[str, Any]]:
    try:
        return fetch_scoreboard(slug, season=year, limit=400)
    except Exception:
        return []


def sync_history(db: Session, year: int | None = None,
                  progress: bool = False) -> dict[str, Any]:
    """拉取指定年份（或去年+今年）的历史赛果，只入库比分不拉详情。

    用途：为 Elo 反推与 XGBoost 训练积累真实样本。数据量大（每年 6000+ 场），
    因此不拉 summary（事件/统计/阵容），只同步赛程与比分。
    """
    from app.models import League, Match, MatchEvent, MatchPrediction, Team

    years = [year] if year else [datetime.now(timezone.utc).year - 1,
                                 datetime.now(timezone.utc).year]
    result = {"ok": False, "years": years, "leagues": 0, "new_matches": 0,
              "updated": 0, "error": None}
    try:
        slugs = list(LEAGUES)
        total_rows: list[tuple[str, list]] = []
        for y in years:
            # 每年一次并发拉取（ThreadPoolExecutor 不能跨轮复用）
            with ThreadPoolExecutor(max_workers=10) as pool:
                results = list(pool.map(lambda s, yy=y: _safe_season(s, yy), slugs))
            for slug, rows in zip(slugs, results):
                # 只保留已完赛的历史比赛（未来赛程由日常同步负责）
                rows = [r for r in rows if r["status"] == "finished"
                        and r["score_home"] is not None and r["score_away"] is not None]
                if rows:
                    total_rows.append((slug, rows))
        result["leagues"] = len({s for s, _ in total_rows})

        rebuild_team_index(db)
        existing = {
            eid for (eid,) in db.query(Match.provider_event_id)
            .filter(Match.provider == "espn").all()
        }
        for slug, rows in total_rows:
            lg = _resolve_league(db, slug)
            ctype = lg.competition_type
            for r in rows:
                if r["event_id"] in existing:
                    m = db.query(Match).filter(
                        Match.provider == "espn",
                        Match.provider_event_id == r["event_id"],
                    ).first()
                    if m is not None and m.score_home is None:
                        m.score_home, m.score_away = r["score_home"], r["score_away"]
                        result["updated"] += 1
                    continue
                home = _resolve_team(db, r["home"], lg.id, lg.name, ctype)
                away = _resolve_team(db, r["away"], lg.id, lg.name, ctype)
                m = Match(
                    league_id=lg.id, home_team_id=home.id, away_team_id=away.id,
                    kickoff_at=_parse_dt(r["kickoff"]) or datetime.now(timezone.utc),
                    venue=r.get("venue"), round=r.get("round"), sim_seed=0,
                    provider="espn", provider_event_id=r["event_id"],
                    status_override="finished", minute_override=90,
                    score_home=r["score_home"], score_away=r["score_away"],
                    is_history=True,
                )
                db.add(m)
                db.flush()
                # 不在此处建预测：此时 Elo 还是初始 1500，预测无意义。
                # 由调用方在 recompute_elo() 之后统一 rebuild_predictions()。
                existing.add(r["event_id"])
                result["new_matches"] += 1
        db.commit()
        result["ok"] = True
    except Exception as e:
        db.rollback()
        result["error"] = str(e)
    return result


def _safe_summary(job: tuple[str, str]) -> dict[str, Any] | None:
    slug, event_id = job
    try:
        return fetch_summary(slug, event_id)
    except Exception:
        return None


def _fetch_summaries(jobs: list[tuple[str, str]]) -> dict[str, dict[str, Any]]:
    """并发拉取 summary，返回 {event_id: summary}。"""
    out: dict[str, dict[str, Any]] = {}
    if not jobs:
        return out
    with ThreadPoolExecutor(max_workers=8) as pool:
        for job, s in zip(jobs, pool.map(_safe_summary, jobs)):
            if s:
                out[job[1]] = s
    return out


def sync(db: Session, with_details: bool = True, keep_days: int = 21) -> dict[str, Any]:
    """同步真实赛程/比分/统计到本地库。返回同步摘要。

    两阶段：先并发拉取所有 ESPN 源（scoreboard + 需要的 summary），再单线程写库，
    避免在 SQLAlchemy Session 上跨线程共享。
    """
    from app.models import Match, MatchEvent, MatchPrediction, Player

    result = {"ok": False, "leagues": 0, "matches": 0, "live": 0, "events": 0,
              "error": None, "skipped": 0, "detail": 0}
    try:
        now = datetime.now(timezone.utc)

        # ---------- 阶段一：并发拉取 ----------
        boards = _fetch_all_scoreboards()
        result["leagues"] = len(boards)

        # 详情优先级：进行中 > 近 24h 完赛 > 重点赛事的未开赛比赛（拉阵容）
        ranked: list[tuple[float, str, dict]] = []
        for slug, rows in boards.items():
            for r in rows:
                ko = _parse_dt(r["kickoff"]) or now
                if r["status"] in ("live", "halftime"):
                    ranked.append((0.0, slug, r))
                elif r["status"] == "finished" and ko >= now - timedelta(days=1):
                    ranked.append((1.0, slug, r))
                elif r["status"] == "scheduled" and LEAGUES[slug][4]:
                    ranked.append((2.0, slug, r))
        ranked.sort(key=lambda t: (t[0], -(_parse_dt(t[2]["kickoff"]) or now).timestamp()))
        budget = _detail_budget() if with_details else 0
        chosen = ranked[:budget]
        result["skipped"] = max(0, len(ranked) - budget)
        summaries = _fetch_summaries([(s, r["event_id"]) for _, s, r in chosen])
        result["detail"] = len(summaries)

        # ---------- 阶段二：写库（单线程） ----------
        rebuild_team_index(db)
        for slug, rows in boards.items():
            lg = _resolve_league(db, slug)
            ctype = lg.competition_type
            for r in rows:
                ko = _parse_dt(r["kickoff"]) or now
                home = _resolve_team(db, r["home"], lg.id, lg.name, ctype)
                away = _resolve_team(db, r["away"], lg.id, lg.name, ctype)
                m = db.query(Match).filter(
                    Match.provider == "espn", Match.provider_event_id == r["event_id"]
                ).first()
                if m is None:
                    m = Match(
                        league_id=lg.id, home_team_id=home.id, away_team_id=away.id,
                        kickoff_at=ko, venue=r.get("venue"), round=r.get("round"),
                        sim_seed=0, provider="espn", provider_event_id=r["event_id"],
                    )
                    db.add(m)
                    db.flush()
                m.kickoff_at = ko
                m.home_team_id, m.away_team_id = home.id, away.id
                m.status_override = r["status"]
                m.minute_override = r["minute"]
                m.score_home = r["score_home"]
                m.score_away = r["score_away"]
                result["matches"] += 1
                if r["status"] in ("live", "halftime"):
                    result["live"] += 1
                _upsert_prediction(db, m, home.elo_rating, away.elo_rating)

                s = summaries.get(r["event_id"])
                if s is None:
                    continue
                m.stats_json = _stats_payload(
                    s["stats"], str(r["home"]["id"]), str(r["away"]["id"]))
                for grp in (s["raw"].get("rosters") or []):
                    side = grp.get("homeAway")
                    entries = grp.get("roster") or []
                    if isinstance(entries, list) and entries:
                        _sync_roster(db, home if side == "home" else away, entries, side)
                db.query(MatchEvent).filter(MatchEvent.match_id == m.id).delete()
                id_home, id_away = str(r["home"]["id"]), str(r["away"]["id"])
                for ev in s["events"]:
                    if ev["team_id"] == id_home:
                        side = "home"
                    elif ev["team_id"] == id_away:
                        side = "away"
                    else:
                        continue
                    team = home if side == "home" else away
                    db.add(MatchEvent(
                        match_id=m.id, minute=ev["minute"], side=side, type=ev["type"],
                        player_id=_find_or_create_player(db, ev["player"], team),
                        related_player_id=_find_or_create_player(db, ev["related"], team),
                        detail=(ev.get("detail") or "")[:180] or None,
                    ))
                    result["events"] += 1
        db.flush()

        # ---------- 清理：模拟比赛 + 超出保留窗口的旧比赛 ----------
        # 注意：is_history=True 的历史样本库必须跳过 —— 否则刚同步的多年历史
        # 会被日常同步按 keep_days 立刻删掉，Elo/模型就永远没有样本。
        if result["matches"]:
            # 先删子表（MatchPrediction/MatchEvent 对 match_id 是 NOT NULL 外键，
            # 直接 db.delete(Match) 会让 ORM 把外键置 NULL 从而违反约束）
            doomed = db.query(Match.id).filter(
                Match.is_history.is_(False),
                (Match.provider != "espn")
                | (Match.kickoff_at < now - timedelta(days=keep_days)),
            ).all()
            ids = [i for (i,) in doomed]
            if ids:
                db.query(MatchEvent).filter(MatchEvent.match_id.in_(ids)).delete(
                    synchronize_session=False)
                db.query(MatchPrediction).filter(
                    MatchPrediction.match_id.in_(ids)).delete(synchronize_session=False)
                db.query(Match).filter(Match.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        result["ok"] = bool(result["matches"])
        _last_sync.update({
            "ok": result["ok"], "at": now.isoformat(),
            "matches": result["matches"], "leagues": result["leagues"],
            "live": result["live"], "error": result["error"],
        })
    except Exception as e:  # 同步失败不影响服务
        db.rollback()
        result["error"] = str(e)
        _last_sync.update({"ok": False, "at": datetime.now(timezone.utc).isoformat(),
                           "error": str(e)})
    return result


def _find_or_create_player(db: Session, name: str | None, team) -> int | None:
    """真实球员：按队内姓名匹配，缺失则建占位球员（真实数据源无赛季汇总数据）。"""
    from app.models import Player

    if not name:
        return None
    p = db.query(Player).filter(Player.team_id == team.id, Player.name_en == name).first()
    if p:
        return p.id
    p = Player(
        team_id=team.id, name=name, name_en=name, position="MF",
        number=0, age=0, rating=6.5, ai_rating=6.5, status="normal",
        season_stats={}, provider="espn",
    )
    db.add(p)
    db.flush()
    return p.id


_POS_MAP = {"G": "GK", "GK": "GK", "D": "DF", "DF": "DF", "M": "MF", "MF": "MF",
            "F": "FW", "FW": "FW", "A": "FW", "ST": "FW"}


def _sync_roster(db: Session, team, roster: list, home_away: str) -> int:
    """把 ESPN 阵容写入球队（真实球员：姓名/号码/位置）。"""
    from app.models import Player

    created = 0
    for entry in roster or []:
        ath = entry.get("athlete") or {}
        name = ath.get("displayName") or ath.get("shortName")
        if not name:
            continue
        pos_raw = entry.get("position") or ath.get("position") or {}
        if isinstance(pos_raw, dict):
            pos_raw = pos_raw.get("abbreviation") or ""
        jersey = entry.get("jersey") or ath.get("jersey")
        try:
            jersey = int(jersey) if jersey else 0
        except (TypeError, ValueError):
            jersey = 0
        exists = db.query(Player).filter(
            Player.team_id == team.id, Player.name_en == name).first()
        if exists:
            if exists.provider != "espn":
                exists.provider = "espn"
            if jersey and exists.number == 0:
                exists.number = jersey
            continue
        db.add(Player(
            team_id=team.id, name=name, name_en=name,
            position=_POS_MAP.get(str(pos_raw).upper(), "MF"),
            number=jersey, age=ath.get("age") or 0,
            rating=6.5, ai_rating=6.5, status="normal",
            season_stats={}, provider="espn",
        ))
        created += 1
    db.flush()
    return created


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
