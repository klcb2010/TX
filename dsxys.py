from base.spider import Spider
import requests
import json
import re
from urllib.parse import quote

base_url = "https://www.belitv.com"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': base_url
}

class Spider(Spider):
    
    def getName(self):
        return "BeliTV"
    
    def init(self, extend):
        pass
    
    def isVideoFormat(self, url):
        return any(fmt in url.lower() for fmt in ['.m3u8', '.mp4', '.flv', '.avi', '.mkv', '.ts'])
    
    def manualVideoCheck(self):
        return False
    
    def homeContent(self, filter):
        common_letter = {"key": "letter", "name": "字母", "value": [{"n": "全部", "v": ""}, {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"}, {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"}, {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"}, {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"}, {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"}, {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"}, {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"}, {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"}, {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"}]}
        common_by = {"key": "by", "name": "排序", "value": [{"n": "时间排序", "v": "time"}, {"n": "人气排序", "v": "hits"}, {"n": "评分排序", "v": "score"}]}

        movie_cate = {"key": "cateId", "name": "类型", "value": [{"n": "全部", "v": "1"}, {"n": "动作片", "v": "6"}, {"n": "喜剧片", "v": "7"}, {"n": "爱情片", "v": "8"}, {"n": "科幻片", "v": "9"}, {"n": "奇幻片", "v": "10"}, {"n": "恐怖片", "v": "11"}, {"n": "剧情片", "v": "12"}, {"n": "战争片", "v": "20"}, {"n": "纪录片", "v": "21"}, {"n": "动画片", "v": "26"}, {"n": "悬疑片", "v": "22"}, {"n": "冒险片", "v": "23"}, {"n": "犯罪片", "v": "24"}, {"n": "惊悚片", "v": "45"}, {"n": "歌舞片", "v": "46"}, {"n": "灾难片", "v": "47"}, {"n": "网络片", "v": "48"}]}
        movie_class = {"key": "class", "name": "剧情", "value": [{"n": "全部", "v": ""}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"}, {"n": "恐怖", "v": "恐怖"}, {"n": "动作", "v": "动作"}, {"n": "科幻", "v": "科幻"}, {"n": "剧情", "v": "剧情"}, {"n": "战争", "v": "战争"}, {"n": "警匪", "v": "警匪"}, {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"}, {"n": "奇幻", "v": "奇幻"}, {"n": "武侠", "v": "武侠"}, {"n": "冒险", "v": "冒险"}, {"n": "枪战", "v": "枪战"}, {"n": "悬疑", "v": "悬疑"}, {"n": "惊悚", "v": "惊悚"}, {"n": "经典", "v": "经典"}, {"n": "青春", "v": "青春"}, {"n": "文艺", "v": "文艺"}, {"n": "微电影", "v": "微电影"}, {"n": "古装", "v": "古装"}, {"n": "历史", "v": "历史"}, {"n": "运动", "v": "运动"}, {"n": "农村", "v": "农村"}, {"n": "儿童", "v": "儿童"}, {"n": "网络电影", "v": "网络电影"}]}
        movie_area = {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"}, {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"}, {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"}, {"n": "意大利", "v": "意大利"}, {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"}, {"n": "其他", "v": "其他"}]}
        movie_lang = {"key": "lang", "name": "语言", "value": [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"}, {"n": "西班牙", "v": "西班牙"}, {"n": "德语", "v": "德语"}, {"n": "泰语", "v": "泰语"}, {"n": "其它", "v": "其它"}]}
        movie_year = {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"}, {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"}, {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"}, {"n": "更早", "v": "更早"}]}

        tv_cate = {"key": "cateId", "name": "类型", "value": [{"n": "全部", "v": "2"}, {"n": "国产剧", "v": "13"}, {"n": "港台剧", "v": "14"}, {"n": "日剧", "v": "15"}, {"n": "韩剧", "v": "33"}, {"n": "欧美剧", "v": "16"}, {"n": "泰剧", "v": "34"}, {"n": "新马剧", "v": "35"}, {"n": "其他剧", "v": "25"}]}
        tv_class = {"key": "class", "name": "剧情", "value": [{"n": "全部", "v": ""}, {"n": "古装", "v": "古装"}, {"n": "战争", "v": "战争"}, {"n": "青春偶像", "v": "青春偶像"}, {"n": "喜剧", "v": "喜剧"}, {"n": "家庭", "v": "家庭"}, {"n": "犯罪", "v": "犯罪"}, {"n": "动作", "v": "动作"}, {"n": "奇幻", "v": "奇幻"}, {"n": "剧情", "v": "剧情"}, {"n": "历史", "v": "历史"}, {"n": "经典", "v": "经典"}, {"n": "乡村", "v": "乡村"}, {"n": "情景", "v": "情景"}, {"n": "商战", "v": "商战"}, {"n": "网剧", "v": "网剧"}, {"n": "其他", "v": "其他"}]}
        tv_year = {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"}, {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"}, {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"}, {"n": "2010-2000", "v": "2010-2000"}, {"n": "90年代", "v": "90年代"}, {"n": "80年代", "v": "80年代"}, {"n": "更早", "v": "更早"}]}

        zy_cate = {"key": "cateId", "name": "类型", "value": [{"n": "全部", "v": "3"}, {"n": "内地综艺", "v": "27"}, {"n": "港台综艺", "v": "28"}, {"n": "日本综艺", "v": "29"}, {"n": "韩国综艺", "v": "36"}, {"n": "欧美综艺", "v": "30"}, {"n": "新马泰综艺", "v": "37"}, {"n": "其他综艺", "v": "38"}]}
        zy_class = {"key": "class", "name": "剧情", "value": [{"n": "全部", "v": ""}, {"n": "真人秀", "v": "真人秀"}, {"n": "情感", "v": "情感"}, {"n": "访谈", "v": "访谈"}, {"n": "播报", "v": "播报"}, {"n": "旅游", "v": "旅游"}, {"n": "音乐", "v": "音乐"}, {"n": "美食", "v": "美食"}, {"n": "纪实", "v": "纪实"}, {"n": "曲艺", "v": "曲艺"}, {"n": "生活", "v": "生活"}, {"n": "游戏互动", "v": "游戏互动"}, {"n": "财经", "v": "财经"}, {"n": "求职", "v": "求职"}]}
        zy_area = {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "内地", "v": "内地"}, {"n": "港台", "v": "港台"}, {"n": "日韩", "v": "日韩"}, {"n": "欧美", "v": "欧美"}]}
        zy_lang = {"key": "lang", "name": "语言", "value": [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}]}

        dm_cate = {"key": "cateId", "name": "类型", "value": [{"n": "全部", "v": "4"}, {"n": "国产动漫", "v": "31"}, {"n": "日本动漫", "v": "32"}, {"n": "韩国动漫", "v": "39"}, {"n": "港台动漫", "v": "40"}, {"n": "新马泰动漫", "v": "41"}, {"n": "欧美动漫", "v": "42"}, {"n": "其他动漫", "v": "43"}]}
        dm_class = {"key": "class", "name": "剧情", "value": [{"n": "全部", "v": ""}, {"n": "情感", "v": "情感"}, {"n": "科幻", "v": "科幻"}, {"n": "热血", "v": "热血"}, {"n": "推理", "v": "推理"}, {"n": "搞笑", "v": "搞笑"}, {"n": "冒险", "v": "冒险"}, {"n": "萝莉", "v": "萝莉"}, {"n": "校园", "v": "校园"}, {"n": "动作", "v": "动作"}, {"n": "机战", "v": "机战"}, {"n": "运动", "v": "运动"}, {"n": "战争", "v": "战争"}, {"n": "少年", "v": "少年"}, {"n": "少女", "v": "少女"}, {"n": "社会", "v": "社会"}, {"n": "原创", "v": "原创"}, {"n": "亲子", "v": "亲子"}, {"n": "益智", "v": "益智"}, {"n": "励志", "v": "励志"}, {"n": "其他", "v": "其他"}]}
        dm_area = {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "国产", "v": "国产"}, {"n": "日本", "v": "日本"}, {"n": "欧美", "v": "欧美"}, {"n": "其他", "v": "其他"}]}
        dm_lang = {"key": "lang", "name": "语言", "value": [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"}, {"n": "其它", "v": "其它"}]}

        return {
            "class": [
                {"type_id": "4", "type_name": "动漫"},
                {"type_id": "2", "type_name": "剧集"},
                {"type_id": "1", "type_name": "电影"},
                {"type_id": "3", "type_name": "综艺"}
            ],
            "filters": {
                "1": [movie_cate, movie_class, movie_area, movie_lang, movie_year, common_letter, common_by],
                "2": [tv_cate, tv_class, movie_area, movie_lang, tv_year, common_letter, common_by],
                "3": [zy_cate, zy_class, zy_area, zy_lang, tv_year, common_letter, common_by],
                "4": [dm_cate, dm_class, dm_area, dm_lang, tv_year, common_letter, common_by]
            }
        }
    
    def homeVideoContent(self):
        videos = []
        try:
            response = requests.get(base_url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            html = response.text
            
            pattern = r'<a href="([^"]+)"[^>]*title="([^"]+)"[^>]*class="[^"]*module-item[^"]*".*?class="module-item-note">\s*([^<]*)\s*</div>.*?data-original="([^"]+)"'
            items = re.findall(pattern, html, re.DOTALL)
            
            for link, title, remark, img in items:
                videos.append({
                    "vod_id": link,
                    "vod_name": title.strip(),
                    "vod_pic": img if img.startswith('http') else base_url + img,
                    "vod_remarks": remark.strip()
                })
        except:
            pass
        return {'list': videos}
    
    def categoryContent(self, cid, pg, filter, ext):
        try:
            cate_id = ext.get('cateId', cid)
            area = quote(ext.get('area', ''))
            by = ext.get('by', 'time')
            class_name = quote(ext.get('class', ''))
            lang = quote(ext.get('lang', ''))
            letter = ext.get('letter', '')
            year = ext.get('year', '')
            
            url = f"{base_url}/k/{cate_id}-{area}-{by}-{class_name}-{lang}-{letter}---{pg}---{year}.html"
            
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            html = response.text
            
            videos = []
            pattern = r'<a href="([^"]+)"[^>]*title="([^"]+)"[^>]*class="[^"]*module-item[^"]*".*?class="module-item-note">\s*([^<]*)\s*</div>.*?data-original="([^"]+)"'
            items = re.findall(pattern, html, re.DOTALL)
            
            for link, title, remark, img in items:
                videos.append({
                    "vod_id": link,
                    "vod_name": title.strip(),
                    "vod_pic": img if img.startswith('http') else base_url + img,
                    "vod_remarks": remark.strip()
                })
            
            return {
                'list': videos,
                'page': int(pg),
                'pagecount': 999 if videos else int(pg),
                'total': 999999,
                'limit': len(videos)
            }
        except:
            return {'list': [], 'page': 1, 'pagecount': 1, 'total': 0, 'limit': 0}
    
    def detailContent(self, ids):
        try:
            vid = ids[0]
            url = vid if vid.startswith('http') else base_url + (vid if vid.startswith('/') else '/' + vid)
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            html = response.text
            
            title_match = re.search(r'<div class="module-info-heading">\s*<h1>([^<]+)</h1>', html, re.DOTALL)
            title = title_match.group(1).strip() if title_match else ""
            
            img_match = re.search(r'class="module-info-poster".*?data-original="([^"]+)"', html, re.DOTALL)
            img = img_match.group(1) if img_match else ""
            if img and not img.startswith('http'):
                img = base_url + img
                
            desc_match = re.search(r'class="module-info-introduction-content">\s*<p>(.*?)</p>', html, re.DOTALL)
            desc = desc_match.group(1).strip() if desc_match else ""
            desc = re.sub(r'<[^>]+>', '', desc)
            
            year, area, type_name = "", "", ""
            tag_match = re.search(r'<div class="module-info-tag">(.*?)</div>\s*<div class="module-mobile-play">', html, re.DOTALL)
            if tag_match:
                tags = re.findall(r'<a[^>]*>([^<]+)</a>', tag_match.group(1))
                if len(tags) > 0: year = tags[0].strip()
                if len(tags) > 1: area = tags[1].strip()
                if len(tags) > 2: type_name = '/'.join(tag.strip() for tag in tags[2:])
            
            def get_info(label):
                m = re.search(r'<span class="module-info-item-title">' + label + r'</span>.*?<div class="module-info-item-content">(.*?)</div>', html, re.DOTALL)
                if m:
                    return re.sub(r'<[^>]+>', '', m.group(1)).replace('/', ',').strip().strip(',')
                return ""
                
            director = get_info("导演：")
            actor = get_info("主演：")
            
            play_sources = []
            play_urls = []
            
            source_section = re.search(r'id="y-playList"(.*?)</div>\s*</div>', html, re.DOTALL)
            if source_section:
                s_blocks = re.findall(r'data-dropdown-value="([^"]+)">(.*?)</div>', source_section.group(1), re.DOTALL)
                for s_name, s_html in s_blocks:
                    s_count = re.search(r'<small>([^<]+)</small>', s_html)
                    if s_count:
                        play_sources.append(f"{s_name}({s_count.group(1)})")
                    else:
                        play_sources.append(s_name)
            
            panels = re.findall(r'class="module-play-list-content[^"]*"(.*?)</div>', html, re.DOTALL)
            for panel in panels:
                episodes = re.findall(r'href="([^"]+)"[^>]*><span>([^<]+)</span>', panel, re.DOTALL)
                ep_list = []
                for ep_url, ep_name in episodes:
                    full_ep_url = ep_url.strip() if ep_url.startswith('http') else base_url + (ep_url if ep_url.startswith('/') else '/' + ep_url)
                    ep_list.append(f"{ep_name.strip()}${full_ep_url}")
                if ep_list:
                    play_urls.append('#'.join(ep_list))
            
            if len(play_sources) > len(play_urls):
                play_sources = play_sources[:len(play_urls)]
            elif len(play_sources) < len(play_urls):
                play_sources += [f"线路{i+1}" for i in range(len(play_sources), len(play_urls))]
                
            if not play_sources and play_urls:
                play_sources = [f"默认{i+1}" for i in range(len(play_urls))]
            
            return {
                'list': [{
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": img,
                    "vod_year": year,
                    "vod_area": area,
                    "vod_type": type_name,
                    "vod_actor": actor,
                    "vod_director": director,
                    "vod_content": desc,
                    "vod_play_from": '$$$'.join(play_sources),
                    "vod_play_url": '$$$'.join(play_urls)
                }]
            }
        except:
            return {'list': []}
    
    def playerContent(self, flag, id, vipFlags):
        try:
            url = id if id.startswith('http') else base_url + (id if id.startswith('/') else '/' + id)
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            html = response.text
            
            script_match = re.search(r'var player_aaaa\s*=\s*({.*?});', html, re.DOTALL)
            if script_match:
                try:
                    player_data = json.loads(script_match.group(1))
                    video_url = player_data.get('url', '')
                    if video_url:
                        parse_flag = 0 if self.isVideoFormat(video_url) else 1
                        return {
                            "parse": parse_flag,
                            "playUrl": "",
                            "url": video_url,
                            "header": json.dumps(headers)
                        }
                except:
                    pass
            
            return {
                "parse": 1,
                "playUrl": "",
                "url": url,
                "header": json.dumps(headers)
            }
        except:
            return {"parse": 1, "playUrl": "", "url": id, "header": ""}
    
    def searchContent(self, key, quick, pg="1"):
        try:
            url = f"{base_url}/s/{quote(key)}----------{pg}---.html"
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            html = response.text
            
            videos = []
            pattern1 = r'<a href="([^"]+)"[^>]*class="module-card-item-poster"[^>]*>.*?class="module-item-note">\s*([^<]*)\s*</div>.*?data-original="([^"]+)"[^>]*alt="([^"]+)"'
            items1 = re.findall(pattern1, html, re.DOTALL)
            
            if items1:
                for link, remark, img, title in items1:
                    videos.append({
                        "vod_id": link,
                        "vod_name": title.strip(),
                        "vod_pic": img if img.startswith('http') else base_url + img,
                        "vod_remarks": remark.strip()
                    })
            else:
                pattern2 = r'<a href="([^"]+)"[^>]*title="([^"]+)"[^>]*class="[^"]*module-item[^"]*".*?class="module-item-note">\s*([^<]*)\s*</div>.*?data-original="([^"]+)"'
                items2 = re.findall(pattern2, html, re.DOTALL)
                for link, title, remark, img in items2:
                    videos.append({
                        "vod_id": link,
                        "vod_name": title.strip(),
                        "vod_pic": img if img.startswith('http') else base_url + img,
                        "vod_remarks": remark.strip()
                    })
            
            return {
                'list': videos,
                'page': int(pg),
                'pagecount': 999 if videos else int(pg),
                'total': 999999,
                'limit': len(videos)
            }
        except:
            return {'list': [], 'page': 1, 'pagecount': 1, 'total': 0, 'limit': 0}
    
    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)
    
    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None
