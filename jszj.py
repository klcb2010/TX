# -*- coding: utf-8 -*-
"""
极速追剧 jisuzhuiju.com —— Python 版
原 JS 源 by Hermes (2026-09-22)

适配 OK影视 / TVBox Chaquopy Python 环境。
依赖：beautifulsoup4（如环境无 bs4，需要先安装）
"""

import re
import json
from urllib.parse import quote

from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    HOST = 'https://jisuzhuiju.com'
    SRC = '极速追剧'
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
          'AppleWebKit/537.36 (KHTML, like Gecko) '
          'Chrome/131.0.0.0 Safari/537.36')

    def getName(self):
        return self.SRC

    def init(self, extend=""):
        self.headers = {
            'User-Agent': self.UA,
            'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
                       'image/avif,image/webp,*/*;q=0.8'),
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.HOST + '/',
        }
        self.classes = [
            ('dianshiju', '电视剧'),
            ('dianying', '电影'),
            ('dongman', '动漫'),
            ('zongyi', '综艺'),
        ]
        self.source_names = {
            'qq': '腾讯官方线路',
            'jsm3u8': '自建线路',
            'bfzym3u8': '普通线路二',
            'co': '普通线路一',
        }

    # ---------- 工具方法 ----------
    def _fix_url(self, u):
        u = str(u or '').strip()
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if re.match(r'^https?://', u, re.I):
            return u
        return self.HOST + ('' if u.startswith('/') else '/') + u

    def _strip_tags(self, s):
        s = str(s or '').replace('&nbsp;', ' ')
        s = re.sub(r'<[^>]+>', '', s)
        s = re.sub(r'\s+', ' ', s)
        return s.strip()

    def _id_of(self, href):
        m = re.search(r'/detail/(\d+)\.html', str(href or ''))
        return m.group(1) if m else ''

    def _ep_of(self, href):
        m = re.search(r'/vodplay/(\d+)-([A-Za-z0-9_]+)-(\d+)\.html',
                      str(href or ''))
        return (m.group(1), m.group(2), m.group(3)) if m else None

    def _get_html(self, url):
        try:
            r = self.fetch(url, headers=self.headers)
            return r.text
        except Exception:
            return ''

    # ---------- 列表解析 ----------
    def _parse_list(self, html):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []
        items = []
        seen = set()
        try:
            soup = BeautifulSoup(html, 'html.parser')
            nodes = soup.select('a[href*="/detail/"]')
            if not nodes:
                nodes = soup.select('a.text-decoration-none')
            if not nodes:
                nodes = soup.select('div.vod-card')
            for node in nodes:
                # 取 href
                if node.name == 'a':
                    href = node.get('href', '') or ''
                else:
                    a = node.find('a')
                    href = (a.get('href', '') or '') if a else ''
                vid = self._id_of(href)
                if not vid or vid in seen:
                    continue

                # 取名称：.vod-title > img alt > a title
                name = ''
                title_el = node.select_one('.vod-title')
                if title_el:
                    name = title_el.get_text(strip=True)
                if not name:
                    img = node.find('img')
                    if img:
                        name = (img.get('alt', '') or '').strip()
                if not name:
                    a_tag = node if node.name == 'a' else node.find('a')
                    if a_tag:
                        name = (a_tag.get('title', '') or '').strip()
                name = re.sub(r'(封面|海报)图片$', '', name).strip()
                if not name:
                    continue

                # 取图片：data-src 优先
                pic = ''
                img = node.find('img')
                if img:
                    pic = (img.get('data-src') or
                           img.get('src') or '')

                # 取备注
                remarks = ''
                sub = node.select_one('.vod-subtitle')
                if sub:
                    remarks = sub.get_text(strip=True)

                seen.add(vid)
                items.append({
                    'vod_id': vid,
                    'vod_name': name,
                    'vod_pic': self._fix_url(pic),
                    'vod_remarks': remarks,
                })
        except Exception:
            pass
        return items

    # ---------- 首页 ----------
    def homeContent(self, filter):
        return {
            'class': [
                {'type_id': cid, 'type_name': name}
                for cid, name in self.classes
            ]
        }

    def homeVideoContent(self):
        html = self._get_html(self.HOST + '/')
        return {'list': self._parse_list(html)[:60]}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg_num = int(pg) if pg else 1
        except Exception:
            pg_num = 1
        # 站点无分页，第 2 页起返回空
        if pg_num > 1:
            return {'list': [], 'page': pg_num, 'pagecount': 1,
                    'limit': 0, 'total': 0}
        tid2 = tid or 'dianshiju'
        html = self._get_html(self.HOST + '/type/' + str(tid2) + '.html')
        items = self._parse_list(html)
        return {
            'list': items,
            'page': pg_num,
            'pagecount': 1,
            'limit': len(items),
            'total': len(items),
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0] if ids else '')
        if not vid:
            return {'list': []}
        html = self._get_html(self.HOST + '/detail/' + vid + '.html')
        if not html:
            return {'list': []}

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {'list': []}
        soup = BeautifulSoup(html, 'html.parser')

        vod = {
            'vod_id': vid,
            'vod_name': '',
            'vod_pic': '',
            'vod_content': '',
            'vod_remarks': '',
            'vod_play_from': self.SRC,
            'vod_play_url': '',
        }

        h1 = soup.select_one('h1')
        if h1:
            vod['vod_name'] = h1.get_text(strip=True)

        og_img = soup.select_one('meta[property="og:image"]')
        if og_img:
            vod['vod_pic'] = self._fix_url(og_img.get('content', '') or '')
        if not vod['vod_pic']:
            poster = soup.select_one('div.detail-poster-wrapper > img')
            if poster:
                vod['vod_pic'] = self._fix_url(poster.get('src', '') or '')

        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc:
            vod['vod_content'] = (meta_desc.get('content', '') or '').strip()

        # span.meta-value 顺序：主演/导演/地区/语言/年份/更新/备注
        metas = [s.get_text(strip=True) for s in soup.select('span.meta-value')]
        if len(metas) > 0:
            vod['vod_actor'] = metas[0]
        if len(metas) > 1:
            vod['vod_director'] = metas[1]
        if len(metas) > 2:
            vod['vod_area'] = metas[2]
        if len(metas) > 4:
            vod['vod_year'] = metas[4]
        if len(metas) > 5:
            vod['vod_remarks'] = metas[5]
        if len(metas) > 6 and metas[6]:
            vod['vod_remarks'] = metas[6]

        # 播放线路：div.source-tabs > button 与 div.source-panel 一一对应
        tabs = soup.select('div.source-tabs > button')
        panels = soup.select('div.source-panel')
        froms = []
        urls = []
        for i, panel in enumerate(panels):
            if i < len(tabs):
                name = tabs[i].get_text(strip=True)
            else:
                name = '线路' + str(i + 1)
            eps = []
            for a in panel.select('a.episode-btn'):
                href = a.get('href', '') or ''
                ep = self._ep_of(href)
                if not ep:
                    continue
                text = a.get_text(strip=True) or ('第' + str(len(eps) + 1) + '集')
                eps.append(text + '$' + self._fix_url(href))
            if eps:
                froms.append(name)
                urls.append('#'.join(eps))
        if urls:
            vod['vod_play_from'] = '$$$'.join(froms)
            vod['vod_play_url'] = '$$$'.join(urls)
        return {'list': [vod]}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg='1'):
        kw = (key or '').strip()
        if not kw:
            return {'list': [], 'page': pg, 'pagecount': 1}
        html = self._get_html(self.HOST + '/search?wd=' + quote(kw, safe=''))
        items = self._parse_list(html)[:40]
        try:
            pg_num = int(pg) if pg else 1
        except Exception:
            pg_num = 1
        return {'list': items, 'page': pg_num, 'pagecount': 1}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        raw = str(id or '')

        # 已经是 http 直链（非本站 vodplay 页）
        if re.match(r'^https?://', raw, re.I) and \
                not re.search(r'jisuzhuiju\.com/vodplay/', raw, re.I):
            return {
                'parse': 0,
                'url': raw,
                'header': {'User-Agent': self.UA, 'Referer': self.HOST + '/'},
            }

        ep = self._ep_of(raw)
        if not ep:
            # 不是播放页地址：交给客户端嗅探
            return {'parse': 1, 'url': self._fix_url(raw)}

        page_url = (self.HOST + '/vodplay/' + ep[0] + '-' + ep[1]
                    + '-' + ep[2] + '.html')
        api = (self.HOST + '/api/play-url?vodId=' + ep[0]
               + '&playFrom=' + ep[1] + '&index=' + ep[2])

        try:
            api_headers = dict(self.headers)
            api_headers['X-Requested-With'] = 'XMLHttpRequest'
            api_headers['Accept'] = 'application/json, text/plain, */*'
            api_headers['Referer'] = page_url
            r = self.fetch(api, headers=api_headers)
            j = json.loads(r.text)
            if j and j.get('code') == 200 and j.get('url'):
                return {
                    'parse': 0,
                    'url': j['url'],
                    'header': {'User-Agent': self.UA,
                               'Referer': self.HOST + '/'},
                }
        except Exception:
            pass

        # 兜底：把播放页交给客户端嗅探
        return {'parse': 1, 'url': page_url}

    # ---------- 其他 ----------
    def localProxy(self, param):
        return [404, 'text/plain', '']

    def isVideoFormat(self, url):
        return '.m3u8' in str(url or '')

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass