# -*- coding: utf-8 -*-
import sys
import json
import re
import time
import requests
import base64
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


sys.path.append('..')
from base.spider import Spider


class DyuziPanSpider(Spider):
    """心跳4k剧场网盘资源搜索爬虫 - 适配VOX/Fongmi(全功能无损完美版)
    
    网站: https://ppan.dyuzi.com/
    """

    # 网站基础配置
    SITE_URL = "https://ppan.dyuzi.com"
    WEB_SEARCH_API = f"{SITE_URL}/api/other/web_search"
    HOME_API = f"{SITE_URL}/api/frontend/home"
    RANKING_API = f"{SITE_URL}/api/frontend/ranking"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "Accept": "text/event-stream, application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": SITE_URL,
        "X-Requested-With": "XMLHttpRequest"
    }

    REQUEST_TIMEOUT = 60
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 0.5
    # 请求间隔（秒），防止触发CDN/WAF封IP
    REQUEST_DELAY = 0.5

    # 网盘类型映射 (is_type -> pan_type)
    IS_TYPE_MAP = {
        0: 'quark',      # 夸克
        1: 'uc',         # UC
        2: 'baidu',      # 百度
        3: 'aliyun',     # 阿里
        4: 'xunlei',     # 迅雷
        5: 'a189',       # 天翼
        6: 'quark',      # 夸克(另一个标识)
    }

    # 网盘类型配置 - 100%还原原版
    PAN_CONFIG = {
        'quark': {
            'name': '夸克',
            'icon': 'https://ppan.dyuzi.com/views/index/template/btlm/disk-icons/quark.webp'
        },
        'uc': {
            'name': 'UC',
            'icon': 'https://ppan.dyuzi.com/views/index/template/btlm/disk-icons/uc.webp'
        },
        'a189': {
            'name': '天翼',
            'icon': 'https://ppan.dyuzi.com/views/index/template/btlm/disk-icons/189.webp'
        },
        'aliyun': {
            'name': '阿里',
            'icon': 'https://ppan.dyuzi.com/views/index/template/btlm/disk-icons/aliyun.webp'
        },
        'baidu': {
            'name': '百度',
            'icon': 'https://ppan.dyuzi.com/views/index/template/btlm/disk-icons/baidu.webp'
        },
        'xunlei': {
            'name': '迅雷',
            'icon': 'https://ppan.dyuzi.com/views/index/template/btlm/disk-icons/xunlei.webp'
        },
        'magnet': {
            'name': '磁力',
            'icon': ''
        },
        'other': {
            'name': '网盘',
            'icon': ''
        }
    }

    # 100%还原四个大频道分类
    CHANNELS = {
        '电视剧': '1',
        '电影': '2',
        '综艺': '3',
        '动漫': '4'
    }

    def __init__(self):
        super().__init__()
        self.pan_priority = ''
        self._last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

        retries = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=self.BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def init(self, extend):
        """初始化配置 - 还原优先级设置"""
        try:
            extend_dict = json.loads(extend) if extend else {}
            self.pan_priority = extend_dict.get('pan_priority', 'quark,a189,uc')
        except json.JSONDecodeError:
            self.pan_priority = 'quark,a189,uc'

    def getName(self):
        return "盘搜"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        """首页内容 - 100%还原4个大分类标签，一个都不少"""
        class_list = [
            {"type_id": "1", "type_name": "电视剧"},
            {"type_id": "2", "type_name": "电影"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"}
        ]
        return {
            'class': class_list,
            'filters': {},
            'list': []
        }

    def homeVideoContent(self):
        """首页推荐视频 - 获取热播榜单"""
        try:
            resp = self.session.get(
                self.RANKING_API,
                params={'channel': '电视剧', 'limit': 12},
                timeout=self.REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            vod_list = []
            if data.get('code') == 0 and data.get('data', {}).get('list'):
                for item in data['data']['list']:
                    vod_list.append({
                        "vod_id": self._b64e({
                            'title': item.get('title', ''),
                            'type': 'ranking',
                            'channel': item.get('channel', '电视剧')
                        }),
                        "vod_name": item.get('title', ''),
                        "vod_pic": item.get('src', ''),
                        "vod_remarks": f"{item.get('episode_count', '')} | 热度:{item.get('hot_score', '0')[:4]}"
                    })

            return {'list': vod_list}

        except Exception as e:
            print(f"获取首页推荐异常: {e}")
            return {'list': []}

    def categoryContent(self, cid, page, filter, ext):
        """分类内容 - 100%还原全频道热播榜支持（包含综艺、动漫）"""
        try:
            channel_map = {
                '1': '电视剧',
                '2': '电影',
                '3': '综艺',
                '4': '动漫'
            }
            channel = channel_map.get(cid, '电视剧')

            resp = self.session.get(
                self.RANKING_API,
                params={'channel': channel, 'limit': 30},
                timeout=self.REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            vod_list = []
            if data.get('code') == 0 and data.get('data', {}).get('list'):
                for item in data['data']['list']:
                    vod_list.append({
                        "vod_id": self._b64e({
                            'title': item.get('title', ''),
                            'type': 'ranking',
                            'channel': item.get('channel', channel)
                        }),
                        "vod_name": item.get('title', ''),
                        "vod_pic": item.get('src', ''),
                        "vod_remarks": f"{item.get('episode_count', '')} | 评分:{item.get('score_avg', '0')}"
                    })

            return {
                'list': vod_list,
                'page': 1,
                'pagecount': 1,
                'limit': 30,
                'total': len(vod_list)
            }

        except Exception as e:
            print(f"获取分类内容异常: {e}")
            return {
                'list': [], 'page': 1, 'pagecount': 1, 'limit': 30, 'total': 0
            }

    def _get_pan_type(self, is_type):
        return self.IS_TYPE_MAP.get(is_type, 'other')

    def _get_pan_priority_order(self):
        if self.pan_priority:
            return [p.strip() for p in self.pan_priority.split(',') if p.strip()]
        return ['quark', 'a189', 'uc', 'aliyun', 'baidu', 'xunlei']

    def _b64e(self, obj):
        if isinstance(obj, str):
            text = obj
        else:
            text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")

    def _b64d(self, s):
        try:
            s += "=" * (-len(s) % 4)
            decoded = base64.urlsafe_b64decode(s.encode()).decode()
            try:
                return json.loads(decoded)
            except:
                return decoded
        except:
            return s

    def _parse_sse_response(self, response_text):
        results = []
        lines = response_text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('data:'):
                data_str = line[5:].strip()
                if data_str == '[DONE]':
                    continue
                try:
                    data = json.loads(data_str)
                    if 'title' in data and 'url' in data:
                        results.append(data)
                except:
                    continue
        return results

    def searchContent(self, key, quick, pg="1"):
        return self._perform_search(key, pg)

    def searchContentPage(self, key, quick, page):
        return self._perform_search(key, page)

    def _perform_search(self, keywords, page_str):
        """100%无损还原的搜索逻辑，保留原汁原味的自定义网盘优先级排序"""
        try:
            page = int(page_str)
        except:
            page = 1

        result = {
            'list': [], 'page': page, 'pagecount': 1, 'limit': 100, 'total': 0
        }

        if not keywords:
            return result

        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)

        try:
            params = {
                'title': keywords, 'is_type': 'all', 'is_show': '1', 'skip_check': '0', 'status': '1', 'max': '120'
            }

            resp = self.session.get(
                self.WEB_SEARCH_API, params=params, timeout=self.REQUEST_TIMEOUT, stream=True
            )
            resp.raise_for_status()
            
            self._last_request_time = time.time()
            items = self._parse_sse_response(resp.text)
            
            if items:
                all_results = []
                for item in items:
                    title = item.get('title', '')
                    url = item.get('url', '')
                    is_type = item.get('is_type', -1)

                    if not url or not title:
                        continue

                    pan_type = self._get_pan_type(is_type)
                    pan_config = self.PAN_CONFIG.get(pan_type, self.PAN_CONFIG['other'])
                    remarks = pan_config['name']

                    vod_data = {
                        'title': title, 'url': url, 'pan_type': pan_type
                    }

                    all_results.append({
                        "vod_id": self._b64e(vod_data),
                        "vod_name": title,
                        "vod_pic": pan_config.get('icon', ''),
                        "vod_remarks": remarks,
                        "_pan_type": pan_type
                    })

                # 🌟 重新接回原版的网盘自定义排序规则
                priority_order = self._get_pan_priority_order()
                pan_order_map = {p: i for i, p in enumerate(priority_order)}
                all_results.sort(key=lambda x: pan_order_map.get(x.get('_pan_type', ''), 999))

                for item in all_results:
                    item.pop('_pan_type', None)

                total = len(all_results)
                page_size = 100
                paged_results = all_results[(page - 1) * page_size : page * page_size]

                result.update({
                    'list': paged_results,
                    'total': total,
                    'pagecount': max(1, (total + page_size - 1) // page_size),
                    'limit': page_size
                })

            return result
        except Exception as e:
            print(f"搜索异常: {e}")
            return result

    def detailContent(self, ids):
        """100%还原的详情页逻辑"""
        result = {'list': []}
        if not ids or not ids[0]:
            return result

        try:
            vod_data = self._b64d(ids[0])
            if not isinstance(vod_data, dict):
                return result

            if vod_data.get('type') == 'ranking':
                title = vod_data.get('title', '')
                channel = vod_data.get('channel', '')
                if title:
                    search_result = self._perform_search(title, "1")
                    if search_result.get('list'):
                        first_result = search_result['list'][0]
                        search_vod_data = self._b64d(first_result['vod_id'])
                        if isinstance(search_vod_data, dict):
                            url = search_vod_data.get('url', '')
                            pan_type = search_vod_data.get('pan_type', 'other')
                            pan_config = self.PAN_CONFIG.get(pan_type, self.PAN_CONFIG['other'])
                            pan_name = pan_config['name']
                            
                            result['list'].append({
                                "vod_id": first_result['vod_id'],
                                "vod_name": title,
                                "vod_pic": first_result.get('vod_pic', ''),
                                "vod_content": f"频道: {channel}\n搜索: {title}\n网盘: {pan_name}",
                                "vod_play_from": pan_name,
                                "vod_play_url": f"{pan_name}${url}",
                                "vod_remarks": first_result.get('vod_remarks', '')
                            })
                            return result
                return result

            title = vod_data.get('title', '未知资源')
            url = vod_data.get('url', '')
            pan_type = vod_data.get('pan_type', 'other')

            if not url:
                return result

            pan_config = self.PAN_CONFIG.get(pan_type, self.PAN_CONFIG['other'])
            pan_name = pan_config['name']
            play_url = f"{pan_name}${url}"

            result['list'].append({
                "vod_id": ids[0],
                "vod_name": title,
                "vod_pic": pan_config.get('icon', ''),
                "vod_content": f"网盘类型: {pan_name}\n资源链接: {url}",
                "vod_play_from": pan_name,
                "vod_play_url": play_url,
                "vod_remarks": f"{pan_name}资源"
            })
        except Exception as e:
            print(f"详情解析异常: {e}")
        return result

    def playerContent(self, flag, pid, vipFlags):
        """
        🎯 完美的桥梁位置：
        既保证上面所有原版功能无损，又精准对外输出给 csp_Push
        """
        result = {"parse": 0, "jx": 0, "url": "", "header": self.HEADERS}
        if not pid:
            return result
        try:
            url = pid.split('$', 1)[1] if '$' in pid else pid
            url = url.strip().replace(' ', '')

            if not url.startswith(('http://', 'https://', 'magnet:')):
                url = 'https://' + url

            # 强行包裹 push:// 激活 VOX 内部的本地网盘拦截读取 Cookie 机制
            if not url.startswith('push://'):
                url = 'push://' + url

            result['url'] = url
        except:
            pass
        return result

    def localProxy(self, params):
        return None


# Fongmi 爬虫入口
Spider = DyuziPanSpider
