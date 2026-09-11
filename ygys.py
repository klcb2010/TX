# -*- coding: utf-8 -*-

import sys
import re
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append('../../')

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""):
            pass


class Spider(BaseSpider):

    def __init__(self):

        self.siteUrl = "https://www.ygdy666.com"

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.siteUrl
        })

    def getName(self):
        return "阳光影视"

    def init(self, extend=""):
        pass

    # =========================================================
    # 请求
    # =========================================================

    def fetch(self, url, referer=None):

        try:

            headers = self.session.headers.copy()

            if referer:
                headers["Referer"] = referer

            print("\n====================")
            print("[请求]", url)

            res = self.session.get(
                url,
                headers=headers,
                timeout=10,
                verify=False
            )

            res.encoding = "utf-8"

            html = res.text

            print("[状态码]", res.status_code)
            print("[长度]", len(html))

            return html

        except Exception as e:

            print("fetch异常:", e)

            return ""

    # =========================================================
    # 首页
    # =========================================================

    def homeContent(self, filter):

        result = {
            'class': [
                {"type_name": "电影", "type_id": "20"},
                {"type_name": "电视剧", "type_id": "29"},
                {"type_name": "动漫", "type_id": "38"},
                {"type_name": "综艺", "type_id": "43"}
            ]
        }

        html = self.fetch(self.siteUrl)

        result["list"] = self.parse_list(html)

        return result

    # =========================================================
    # 分类
    # =========================================================

    def categoryContent(self, tid, pg, filter, extend):

        page = int(pg)

        if page > 1:
            url = f"{self.siteUrl}/list/{tid}/{page}.html"
        else:
            url = f"{self.siteUrl}/list/{tid}.html"

        html = self.fetch(
            url,
            referer=self.siteUrl
        )

        return {
            "list": self.parse_list(html),
            "page": page,
            "pagecount": 999,
            "limit": 20,
            "total": 99999
        }

    # =========================================================
    # 搜索（真正修复版）
    # =========================================================

    def searchContent(self, key, quick=False, pg="1"):

        result = []

        try:

            wd = urllib.parse.quote(key)

            # =================================================
            # 方案1：MACCMS标准搜索
            # =================================================

            search_urls = [

                # 标准MACCMS
                f"{self.siteUrl}/search/{wd}----------{pg}---.html",

                # 备用
                f"{self.siteUrl}/index.php/vod/search/page/{pg}/wd/{wd}.html",

                # 备用2
                f"{self.siteUrl}/vodsearch/{wd}----------{pg}---.html",
            ]

            for url in search_urls:

                print("\n[尝试搜索]", url)

                html = self.fetch(
                    url,
                    referer=self.siteUrl
                )

                if not html:
                    continue

                # =================================================
                # 检测验证码
                # =================================================

                if (
                    "验证码" in html
                    or "安全验证" in html
                    or "MAC.Verify" in html
                ):

                    print("[!] 搜索被验证码拦截")

                    # =================================================
                    # 直接绕过：
                    # 从首页搜索推荐里提取
                    # =================================================

                    home_html = self.fetch(self.siteUrl)

                    if key in home_html:
                        html = home_html
                    else:
                        continue

                videos = self.parse_list(html)

                # 过滤关键词
                if videos:

                    filtered = []

                    for v in videos:

                        name = v.get("vod_name", "")

                        if (
                            key.lower() in name.lower()
                            or key in name
                        ):
                            filtered.append(v)

                    if filtered:
                        result.extend(filtered)
                        break

            # 去重
            unique = []

            ids = set()

            for v in result:

                vid = v.get("vod_id")

                if vid not in ids:
                    ids.add(vid)
                    unique.append(v)

            print("[搜索结果数]", len(unique))

            return {
                "list": unique
            }

        except Exception as e:

            print("搜索异常:", e)

            return {
                "list": []
            }

    # =========================================================
    # 列表解析
    # =========================================================

    def parse_list(self, html_content):

        if not html_content:
            return []

        videos = []

        soup = BeautifulSoup(
            html_content,
            "html.parser"
        )

        selectors = [

            "ul.stui-vodlist li",

            ".stui-vodlist li",

            ".module-items .module-item",

            ".myui-vodlist li"
        ]

        items = []

        for s in selectors:

            items = soup.select(s)

            if items:
                print("[命中解析器]", s)
                break

        for item in items:

            a = (
                item.select_one("a.stui-vodlist__thumb")
                or item.select_one("a.module-item-pic")
                or item.select_one("a")
            )

            if not a:
                continue

            href = a.get("href", "")

            if not href:
                continue

            title = (
                a.get("title")
                or a.get("alt")
                or a.text
            ).strip()

            pic = (
                a.get("data-original")
                or a.get("data-src")
                or a.get("src")
                or ""
            )

            if pic.startswith("//"):
                pic = "https:" + pic

            if pic.startswith("/"):
                pic = self.siteUrl + pic

            remark = ""

            remark_selectors = [
                ".pic-text",
                ".module-item-note",
                ".remarks"
            ]

            for rs in remark_selectors:

                tag = item.select_one(rs)

                if tag:
                    remark = tag.text.strip()
                    break

            videos.append({
                "vod_id": href,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark
            })

        print("[解析到]", len(videos), "条")

        return videos

    # =========================================================
    # 详情 (线路改为阳光专线 + 修复重复)
    # =========================================================

    def detailContent(self, ids):
        vod_id = ids[0]
        html = self.fetch(self.siteUrl + vod_id, referer=self.siteUrl)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        vod_name = "未知"
        title = soup.select_one("h1.title") or soup.select_one("h1")
        if title:
            vod_name = title.text.strip()

        from_list = []
        url_list = []
        playuls = soup.select("ul.stui-content__playlist")

        if playuls:
            ul = playuls[0]
            plays = []
            for a in ul.select("a"):
                play_name = a.text.strip()
                play_url = a.get("href")
                if play_url:
                    plays.append(f"{play_name}${play_url}")
            # 固定线路名称为 阳光专线
            from_list.append("阳光专线")
            url_list.append("#".join(plays))

        vod = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_play_from": "$$$".join(from_list),
            "vod_play_url": "$$$".join(url_list)
        }
        return {"list": [vod]}

    # =========================================================
    # 播放
    # =========================================================

    def playerContent(self, flag, id, vipFlags):

        play_url = self.siteUrl + id

        html = self.fetch(play_url)

        if not html:

            return {
                "parse": 1,
                "url": play_url,
                "header": ""
            }

        # m3u8
        m3u8 = re.search(
            r'https?://[^\s"\'<>]+?\.m3u8',
            html
        )

        if m3u8:

            return {
                "parse": 0,
                "url": m3u8.group(0),
                "header": json.dumps({
                    "Referer": self.siteUrl
                })
            }

        # json播放
        json_url = re.search(
            r'"url":"(.*?)"',
            html
        )

        if json_url:

            url = json_url.group(1)

            url = url.replace("\\/", "/")

            if ".m3u8" in url:

                return {
                    "parse": 0,
                    "url": url,
                    "header": json.dumps({
                        "Referer": self.siteUrl
                    })
                }

        return {
            "parse": 1,
            "url": play_url,
            "header": ""
        }

    def destroy(self):
        pass
