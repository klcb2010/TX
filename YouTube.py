#coding=utf-8
#!/usr/bin/python
import re
import sys
import json
import html
import requests
from urllib.parse import quote

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "YouTube视频"

    def init(self, extend):
        try:
            self.extendDict = json.loads(extend)
        except:
            self.extendDict = {}

        self.proxies = {}
        self.proxy_str = None
        self.channel_cache = {}

        if 'proxy' in self.extendDict:
            pv = self.extendDict['proxy']
            if isinstance(pv, dict):
                self.proxies = pv
                self.proxy_str = pv.get('http', '').replace('http://', '')
            elif isinstance(pv, str):
                self.proxy_str = pv
                self.proxies = {'http': f'http://{pv}', 'https': f'http://{pv}'}

        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Referer": "https://www.youtube.com"
        }

    # ================= HOME =================
    def homeContent(self, filter):
        return {
            'class': [
                {"type_id":"Sharp锐评影社","type_name":"犯叔说影"},
                {'type_id': '虎妞小叨叨', 'type_name': '虎妞小叨叨'},
                {'type_id': '温城鲤', 'type_name': '温城鲤'},
                {'type_id': '阿奇讲电影', 'type_name': '阿奇讲电影'},
                {'type_id': '哇萨比抓马', 'type_name': '哇萨比抓马'}
            ]
        }

    # ================= 首页 =================
    def homeVideoContent(self):
        r = requests.get(
            "https://www.youtube.com/results?search_query=国语MV新歌",
            headers=self.header,
            timeout=10,
            proxies=self.proxies
        )
        videos = self._extract_videos(r.text, 20)
        self.channel_cache["current"] = videos
        return {'list': videos}

    # ================= 分类 =================
    def categoryContent(self, cid, page, filter, ext):
        page = int(page)
        url = f"https://www.youtube.com/results?search_query={quote(cid)}"
        r = requests.get(url, headers=self.header, timeout=10, proxies=self.proxies)
        videos = self._extract_videos(r.text, 50)
        self.channel_cache["current"] = videos

        return {
            'list': videos,
            'page': page,
            'pagecount': 1,
            'limit': len(videos),
            'total': len(videos)
        }

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg=1):
        url = f"https://www.youtube.com/results?search_query={quote(key)}"
        r = requests.get(url, headers=self.header, timeout=10, proxies=self.proxies)
        videos = self._extract_videos(r.text, 50)
        self.channel_cache["current"] = videos

        return {
            'list': videos,
            'page': pg,
            'pagecount': 1,
            'limit': len(videos),
            'total': len(videos)
        }

    # ================= 详情（全部进选集） =================
    def detailContent(self, did):
        vid = did[0]
        title = self._get_title(vid)

        channel_list = self.channel_cache.get("current", [])

        seen = set()
        episode_list = []

        # 当前视频始终放在第一位
        episode_list.append(f"{self._safe(title)}${vid}")
        seen.add(vid)

        for v in channel_list:
            v_id = v.get("vod_id")
            if not v_id or v_id in seen:
                continue
            seen.add(v_id)
            episode_list.append(f"{self._safe(v.get('vod_name', '未知'))}${v_id}")

        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
            "vod_content": "YouTube视频",
            "vod_actor": "",
            "vod_director": "",
            "vod_play_from": "修不好的油管",
            "vod_play_url": "#".join(episode_list)
        }

        return {'list': [vod]}

    # ================= 播放 =================
    def playerContent(self, flag, pid, vipFlags):
        vid = pid.split('$')[-1]
        return {
            "parse": 1,
            "url": f"https://www.youtube.com/embed/{vid}",
            "header": self.header,
            "proxy": self.proxy_str
        }

    # ================= 解析 =================
    def _extract_videos(self, html_content, limit=30):
        videos = []
        try:
            m = re.search(r'var ytInitialData\s*=\s*({.+?});</script>', html_content, re.DOTALL)
            if not m:
                return []

            data = json.loads(m.group(1))

            def walk(obj, res):
                if len(res) >= limit:
                    return
                if isinstance(obj, dict):
                    if "videoRenderer" in obj:
                        res.append(obj)
                        return
                    for v in obj.values():
                        walk(v, res)
                elif isinstance(obj, list):
                    for i in obj:
                        walk(i, res)

            found = []
            walk(data, found)

            seen = set()
            for item in found:
                if len(videos) >= limit:
                    break
                r = item.get("videoRenderer")
                if not r:
                    continue

                vid = r.get("videoId")
                if not vid or vid in seen:
                    continue
                seen.add(vid)

                title = ""
                if "title" in r:
                    if "runs" in r["title"]:
                        title = r["title"]["runs"][0].get("text", "")
                    else:
                        title = r["title"].get("simpleText", "")

                videos.append({
                    "vod_id": vid,
                    "vod_name": html.unescape(title) if title else "未知",
                    "vod_pic": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                    "vod_remarks": "1080P"
                })

        except Exception as e:
            print(f"_extract_videos error: {e}")

        return videos

    # ================= 工具 =================
    def _get_title(self, vid):
        try:
            r = requests.get(
                f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json",
                headers=self.header,
                timeout=5,
                proxies=self.proxies
            )
            return r.json().get("title", vid)
        except:
            return vid

    def _safe(self, t):
        if not t:
            return "未知"
        for c in ['#', '$', '/', '\\', '|', '\n', '\r']:
            t = t.replace(c, '·')
        return t[:80]

    def destroy(self):
        pass
