# coding=utf-8
import re
import requests
from bs4 import BeautifulSoup, NavigableString
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "电影港(高清优先版)"

    def init(self, extend=""):
        self.host = "https://www.dygang.tv"

    def header(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.host
        }

    def homeContent(self, filter):
        result = {'class': [
            {"type_id": "/ys/", "type_name": "最新电影"},
            {"type_id": "/bd/", "type_name": "经典高清"},
            {"type_id": "/dsj/", "type_name": "国产剧"},
            {"type_id": "/yx/", "type_name": "美剧"},
            {"type_id": "/dmq/", "type_name": "动漫"}
        ]}
        return result

    def categoryContent(self, tid, pg, filter, extend):
        # 电影港分页规则：第一页 index.htm，后续 index_2.htm
        url = f"{self.host}{tid}index.htm" if pg == "1" else f"{self.host}{tid}index_{pg}.htm"
        res = requests.get(url, headers=self.header())
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'html.parser')
        vod_list = []
        items = soup.select('table.border1')
        for item in items:
            a_tag = item.find('a')
            img_tag = item.find('img')
            if a_tag and img_tag:
                vod_list.append({
                    "vod_id": a_tag['href'],
                    "vod_name": img_tag.get('alt', a_tag.text),
                    "vod_pic": img_tag['src']
                })
        return {"list": vod_list, "page": pg, "pagecount": 999}

    def get_priority(self, name):
        """质量排序权重计算：数字越小越靠前"""
        name = name.lower()
        if '2160' in name or '4k' in name:
            return 0
        if '1080' in name:
            return 1
        if '720' in name:
            return 2
        return 3

    def detailContent(self, ids):
        url = ids[0]
        if not url.startswith('http'):
            url = self.host + url
            
        res = requests.get(url, headers=self.header())
        res.encoding = 'gbk'
        html_text = res.text
        soup = BeautifulSoup(html_text, 'html.parser')
        
        magnet_data = [] 
        quark_data = []
        xunlei_data = []
        seen_urls = set()

        # 锁定放链接的下载单元格
        all_content_tds = soup.find_all('td', bgcolor="#ffffbb")
        for td in all_content_tds:
            a_tags = td.find_all('a', href=True)
            for a in a_tags:
                href = a['href']
                if href in seen_urls: continue
                
                # 描述溯源逻辑：从链接开始向上寻找集数或画质描述
                label_parts = []
                for sib in a.previous_siblings:
                    if sib.name in ['a', 'br', 'p', 'table']: break
                    if isinstance(sib, NavigableString): label_parts.insert(0, sib.strip())
                    else: label_parts.insert(0, sib.get_text().strip())
                
                prefix = "".join(label_parts).strip()
                link_text = a.get_text(strip=True)
                # 清洗无关字符
                clean_label = f"{prefix} {link_text}".replace("链接：", "").replace("链接:", "").replace("磁力：", "").replace("磁力", "").replace("网盘", "").strip()
                
                if len(clean_label) < 2: clean_label = "全集播放"
                priority = self.get_priority(clean_label)

                # 归类到磁力、夸克或迅雷
                if href.startswith('magnet:'):
                    magnet_data.append((priority, clean_label, href))
                elif 'pan.quark.cn' in href:
                    quark_data.append((priority, f"{clean_label}(夸克)", href))
                elif 'pan.xunlei.com' in href:
                    xunlei_data.append((priority, f"{clean_label}(迅雷)", href))
                seen_urls.add(href)

        # 按照画质优先级排序
        magnet_data.sort(key=lambda x: (x[0], x[1]))
        quark_data.sort(key=lambda x: (x[0], x[1]))
        xunlei_data.sort(key=lambda x: (x[0], x[1]))

        from_list = []
        url_list = []
        
        if magnet_data:
            from_list.append("磁力线路")
            url_list.append("#".join([f"{item[1]}${item[2]}" for item in magnet_data]))
            
        if quark_data:
            from_list.append("夸克推送")
            url_list.append("#".join([f"{item[1]}${item[2]}" for item in quark_data]))

        if xunlei_data:
            from_list.append("迅雷推送")
            url_list.append("#".join([f"{item[1]}${item[2]}" for item in xunlei_data]))

        vod = {
            "vod_id": ids[0],
            "vod_name": soup.title.text.split("_")[0],
            "vod_play_from": "$$$".join(from_list),
            "vod_play_url": "$$$".join(url_list)
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        search_url = f"{self.host}/e/search/index.php"
        # 搜索关键词也必须用 GBK 编码提交
        data = {"tempid": "1", "tbname": "article", "keyboard": key.encode('gbk'), "show": "title,smalltext", "Submit": "搜索"}
        res = requests.post(search_url, data=data, headers=self.header())
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'html.parser')
        vod_list = []
        items = soup.select('table.border1')
        for item in items:
            a_tag = item.find('a')
            if a_tag:
                vod_list.append({
                    "vod_id": a_tag['href'],
                    "vod_name": item.find('img').get('alt', a_tag.text) if item.find('img') else a_tag.text,
                    "vod_pic": item.find('img')['src'] if item.find('img') else ""
                })
        return {"list": vod_list}

    def playerContent(self, flag, id, vipFlags):
        play_url = id.strip()
        # 针对云盘链接添加 push:// 协议前缀
        if "quark.cn" in play_url or "xunlei.com" in play_url:
            return {"parse": 0, "url": "push://" + play_url}
        # 磁力链接直接返回给壳子解析
        return {"parse": 0, "url": play_url}
