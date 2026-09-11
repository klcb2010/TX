#coding=utf-8
#!/usr/bin/python
import re
import sys
import json
import time
from datetime import datetime
from urllib.parse import quote, unquote
import html

import requests

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
        
        # 代理配置 - 支持简化格式
        self.proxies = {}
        self.proxy_str = None  # 保存字符串格式的代理
        if 'proxy' in self.extendDict:
            proxy_val = self.extendDict['proxy']
            if proxy_val:
                if isinstance(proxy_val, dict):
                    self.proxies = proxy_val
                    if 'http' in proxy_val:
                        self.proxy_str = proxy_val['http'].replace('http://', '')
                elif isinstance(proxy_val, str):
                    self.proxy_str = proxy_val
                    self.proxies = {
                        'http': f'http://{proxy_val}',
                        'https': f'http://{proxy_val}'
                    }
        
        # 加载自定义分类配置
        self.config = {}
        if 'json' in self.extendDict:
            try:
                config_url = self.extendDict['json']
                if config_url.startswith('./'):
                    import os
                    config_path = os.path.join(os.path.dirname(__file__), config_url[2:])
                    with open(config_path, 'r', encoding='utf-8') as f:
                        self.config = json.load(f)
                else:
                    r = requests.get(config_url, timeout=10)
                    self.config = r.json()
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                self.config = {}
        
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.youtube.com"
        }
        
        self.continuation_cache = {}

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def homeContent(self, filter):
        result = {}
        # 固定常驻分类，把“虎妞小叨叨”牢牢固定在第一个
        result['class'] = [
            {'type_id': '虎妞小叨叨', 'type_name': '虎妞小叨叨'},
            {'type_id': '全部', 'type_name': '全部'},
            {'type_id': '音乐', 'type_name': '音乐'},
            {'type_id': '游戏', 'type_name': '游戏'}
        ]
        
        # 将配置里的其他分类追加进来（去重）
        if 'class' in self.config:
            for cls in self.config['class']:
                if cls['type_id'] not in ['虎妞小叨叨', '全部', '音乐', '游戏']:
                    result['class'].append(cls)
                    
        if filter and 'filters' in self.config:
            result['filters'] = self.config['filters']
        return result

    def homeVideoContent(self):
        result = {}
        videos = []
        try:
            # 首页直接默认展现虎妞小叨叨的内容
            url = "https://www.youtube.com/results?search_query=虎妞小叨叨"
            r = requests.get(url, headers=self.header, timeout=10, proxies=self.proxies)
            videos = self._extract_videos_fixed(r.text, 20)
        except Exception as e:
            print(f"首页视频获取失败: {e}")
        result['list'] = videos[:20]
        return result

    def categoryContent(self, cid, page, filter, ext):
        page = int(page)
        result = {}
        videos = []
        has_more = False
        
        if ext and 'tid' in ext and ext['tid']:
            raw_keyword = ext['tid']
            if ',' in raw_keyword:
                keywords = [x.strip() for x in raw_keyword.split(',')]
                channel_items = []
                search_items = []
                for kw in keywords:
                    if '@' in kw:
                        channel_items.append(kw)
                    else:
                        search_items.append(kw)
                
                if page == 1:
                    for item in channel_items:
                        parts = item.split('@')
                        display_name = parts[0].strip() if parts[0].strip() else parts[1]
                        channel_name = parts[1].strip()
                        videos.append({
                            "vod_id": f"channel_{channel_name}",
                            "vod_name": display_name,
                            "vod_pic": "https://www.youtube.com/s/desktop/2ad2ef02/img/favicon_144x144.png",
                            "vod_remarks": "频道"
                        })
                
                all_has_more = False
                for item in search_items:
                    item_videos, item_has_more = self._handle_pagination(page=page, search_keyword=item, cache_prefix=f"search_{item}")
                    videos.extend(item_videos)
                    if item_has_more:
                        all_has_more = True
                has_more = all_has_more
                
            elif '@' in raw_keyword:
                parts = raw_keyword.split('@')
                channel_name = parts[1].strip()
                videos, has_more = self._handle_pagination(page=page, channel_name=channel_name, cache_prefix=f"channel_{channel_name}")
            else:
                videos, has_more = self._handle_pagination(page=page, search_keyword=raw_keyword, cache_prefix=f"search_{raw_keyword}")
        
        elif cid.startswith('LIST:'):
            items = cid[5:].split(',')
            channel_items = []
            search_items = []
            for item in items:
                item = item.strip()
                if '@' in item:
                    channel_items.append(item)
                else:
                    search_items.append(item)
            
            if page == 1:
                for item in channel_items:
                    parts = item.split('@')
                    display_name = parts[0].strip() if parts[0].strip() else parts[1]
                    channel_name = parts[1].strip()
                    videos.append({
                        "vod_id": f"channel_{channel_name}",
                        "vod_name": display_name,
                        "vod_pic": "https://www.youtube.com/s/desktop/2ad2ef02/img/favicon_144x144.png",
                        "vod_remarks": "频道"
                    })
                all_has_more = False
                for item in search_items:
                    item_videos, item_has_more = self._handle_pagination(page=1, search_keyword=item, cache_prefix=f"search_{item}")
                    videos.extend(item_videos)
                    if item_has_more:
                        all_has_more = True
                has_more = all_has_more
            else:
                all_has_more = False
                for item in search_items:
                    item_videos, item_has_more = self._handle_pagination(page=page, search_keyword=item, cache_prefix=f"search_{item}")
                    videos.extend(item_videos)
                    if item_has_more:
                        all_has_more = True
                has_more = all_has_more
        
        elif cid.startswith('channel_'):
            channel_name = cid[8:]
            videos, has_more = self._handle_pagination(page=page, channel_name=channel_name, cache_prefix=f"channel_{channel_name}")
        else:
            videos, has_more = self._handle_pagination(page=page, search_keyword=cid, cache_prefix=f"search_{cid}")
        
        seen = set()
        unique_videos = []
        for v in videos:
            if v['vod_id'] not in seen:
                seen.add(v['vod_id'])
                unique_videos.append(v)
        
        result['list'] = unique_videos
        result['page'] = page
        result['pagecount'] = page + 1 if has_more else page
        result['limit'] = len(unique_videos)
        result['total'] = len(unique_videos)
        return result

    def _handle_pagination(self, page, search_keyword=None, channel_name=None, cache_prefix=None):
        videos = []
        has_more = False
        if channel_name:
            base_url = f"https://www.youtube.com/@{channel_name}/videos"
            api_url = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
        else:
            base_url = f"https://www.youtube.com/results?search_query={quote(search_keyword)}"
            api_url = "https://www.youtube.com/youtubei/v1/search?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
        
        if page == 1:
            try:
                r = requests.get(base_url, headers=self.header, timeout=15, proxies=self.proxies)
                html_content = r.text
                videos = self._extract_videos_fixed(html_content, 30)
                continuation = self._extract_continuation_token(html_content)
                if continuation:
                    self.continuation_cache[f"{cache_prefix}_2"] = continuation
                    has_more = True
            except Exception as e:
                print(f"获取第一页失败: {e}")
        else:
            continuation = self.continuation_cache.get(f"{cache_prefix}_{page}")
            if continuation:
                payload = {
                    "context": {"client": {"clientName": "WEB", "clientVersion": "2.20260310.01.00"}},
                    "continuation": continuation
                }
                try:
                    r = requests.post(api_url, json=payload, headers=self.header, timeout=15, proxies=self.proxies)
                    if r.status_code == 200:
                        data = r.json()
                        videos = self._extract_videos_from_api(data, 30)
                        next_token = self._extract_next_continuation(data)
                        if next_token:
                            self.continuation_cache[f"{cache_prefix}_{page+1}"] = next_token
                            has_more = True
                except Exception as e:
                    print(f"API请求异常: {e}")
        return videos, has_more

    def detailContent(self, did):
        video_id = did[0]
        print(f"获取详情: {video_id}")
        
        # 1. 处理频道文件夹卡片点击进入的情况
        if video_id.startswith('channel_'):
            channel_name = video_id[8:]
            all_videos = []
            page = 1
            max_pages = 10
            max_videos = 100
            continuation = None
            
            while page <= max_pages and len(all_videos) < max_videos:
                if page == 1:
                    channel_url = f"https://www.youtube.com/@{channel_name}/videos"
                    try:
                        r = requests.get(channel_url, headers=self.header, timeout=15, proxies=self.proxies)
                        html_content = r.text
                        page_videos = self._extract_videos_fixed(html_content, 30)
                        if page_videos:
                            all_videos.extend(page_videos)
                        continuation = self._extract_continuation_token(html_content)
                        if not continuation:
                            break
                    except Exception as e:
                        print(f"获取第一页失败: {e}")
                        break
                else:
                    if not continuation:
                        break
                    api_url = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
                    payload = {
                        "context": {"client": {"clientName": "WEB", "clientVersion": "2.20260310.01.00"}},
                        "continuation": continuation
                    }
                    try:
                        r = requests.post(api_url, json=payload, headers=self.header, timeout=15, proxies=self.proxies)
                        if r.status_code == 200:
                            data = r.json()
                            page_videos = self._extract_videos_from_api(data, 30)
                            if page_videos:
                                all_videos.extend(page_videos)
                            continuation = self._extract_next_continuation(data)
                            if not continuation:
                                break
                        else:
                            break
                    except Exception as e:
                        print(f"获取第{page}页失败: {e}")
                        break
                page += 1
                time.sleep(0.3)
            
            if not all_videos:
                return {'list': []}
            if len(all_videos) > max_videos:
                all_videos = all_videos[:max_videos]
            
            play_url_parts = [f"{self._safe_title(v['vod_name'])}${v['vod_id']}" for v in all_videos]
            vod = {
                "vod_id": video_id,
                "vod_name": f"{channel_name}的频道 ({len(all_videos)}个视频)",
                "vod_pic": "https://www.youtube.com/s/desktop/2ad2ef02/img/favicon_144x144.png",
                "vod_play_from": "UP主频道",
                "vod_play_url": '#'.join(play_url_parts),
                "vod_content": f"{channel_name}的YouTube频道，共{len(all_videos)}个视频"
            }
            return {'list': [vod]}
        
        # 2. 正常单视频详情页解析
        try:
            # 严格局部变量初始化，绝不共用、绝不残留
            channel_display_name = ""
            channel_identifier = ""
            
            video_title = self._get_video_title(video_id)
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            r = requests.get(video_url, headers=self.header, timeout=15, proxies=self.proxies)
            html_content = r.text
            
            # 精确抓取当前网页实际拥有者，解决张冠李戴的大Bug
            channel_display_name = self._extract_channel_display_name(html_content)
            if not channel_display_name:
                channel_display_name = "未知播主"
                
            channel_identifier = self._get_channel_identifier_by_search(channel_display_name)
            
            channel_videos = []
            if channel_identifier and channel_identifier != "未知播主":
                encoded_identifier = quote(channel_identifier, safe='')
                channel_url = f"https://www.youtube.com/@{encoded_identifier}/videos"
                
                page = 1
                max_pages = 4  
                max_videos = 50
                continuation = None
                
                while page <= max_pages and len(channel_videos) < max_videos:
                    if page == 1:
                        try:
                            r2 = requests.get(channel_url, headers=self.header, timeout=10, proxies=self.proxies)
                            page_videos = self._extract_videos_fixed(r2.text, 30)
                            if page_videos:
                                channel_videos.extend(page_videos)
                            continuation = self._extract_continuation_token(r2.text)
                            if not continuation:
                                break
                        except:
                            break
                    else:
                        if not continuation:
                            break
                        api_url = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
                        payload = {
                            "context": {"client": {"clientName": "WEB", "clientVersion": "2.20260310.01.00"}},
                            "continuation": continuation
                        }
                        try:
                            r2 = requests.post(api_url, json=payload, headers=self.header, timeout=12, proxies=self.proxies)
                            if r2.status_code == 200:
                                data = r2.json()
                                page_videos = self._extract_videos_from_api(data, 30)
                                if page_videos:
                                    channel_videos.extend(page_videos)
                                continuation = self._extract_next_continuation(data)
                                if not continuation:
                                    break
                            else:
                                break
                        except:
                            break
                    page += 1
                    time.sleep(0.1)
            
            vod = {
                "vod_id": video_id,
                "vod_name": video_title[:100] + ('...' if len(video_title) > 100 else ''),
                "vod_pic": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                "vod_content": f"播主: {channel_display_name}\n当前视频ID: {video_id}",
                "vod_actor": channel_display_name,
                "vod_remarks": '1080P'
            }
            
            # 线路一：当前视频单集线路
            play_url1 = f"{self._safe_title(video_title)}${video_id}"
            
            # 线路二：UP主历史视频（不剔除当前集，确保完整不前挪错位）
            play_url2_parts = []
            for cv in channel_videos:
                play_url2_parts.append(f"{self._safe_title(cv['vod_name'])}${cv['vod_id']}")
            
            if channel_identifier and channel_identifier != "未知播主":
                vod['vod_director'] = f'[a=cr:{{"id":"channel_{channel_identifier}","name":"{channel_display_name}"}}/]{channel_display_name}[/a]'
            else:
                vod['vod_director'] = channel_display_name

            # 🛠️ 彻底砍掉相关视频线路，只平铺两条最干净的线路
            vod['vod_play_from'] = '当前视频$$$UP主频道'
            p2 = '#'.join(play_url2_parts) if play_url2_parts else play_url1
            vod['vod_play_url'] = f"{play_url1}$$$\n{p2}"
            
            return {'list': [vod]}
            
        except Exception as e:
            print(f"Detail error: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg=1):
        if quick:
            return {'list': []}
        page = int(pg) if pg else 1
        videos, has_more = self._handle_pagination(page=page, search_keyword=key, cache_prefix=f"search_{key}")
        seen = set()
        unique_videos = []
        for v in videos:
            if v['vod_id'] not in seen:
                seen.add(v['vod_id'])
                unique_videos.append(v)
        return {
            'list': unique_videos, 'page': page, 'pagecount': page + 1 if has_more else page,
            'limit': len(unique_videos), 'total': len(unique_videos)
        }

    def playerContent(self, flag, pid, vipFlags):
        result = {}
        video_id = pid.split('$')[-1] if '$' in pid else pid
        result["parse"] = 1
        result["url"] = f"https://www.youtube.com/embed/{video_id}?autoplay=1"
        result["header"] = self.header
        if self.proxy_str:
            result["proxy"] = self.proxy_str
        return result

    def _get_vod_remarks(self, title, duration):
        if duration:
            return duration
        live_keywords = ['live', '直播', '生放送', 'LIVE', '🔴', '🟢', '🔵']
        for keyword in live_keywords:
            if keyword in title:
                return "🟢 直播"
        return "1080P"

    def _extract_continuation_token(self, html_content):
        try:
            pattern = r'var ytInitialData = ({.*?});</script>'
            match = re.search(pattern, html_content, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group(1))
            def find_token(obj):
                if isinstance(obj, dict):
                    if 'continuationCommand' in obj and 'token' in obj['continuationCommand']:
                        return obj['continuationCommand']['token']
                    if 'continuation' in obj and isinstance(obj['continuation'], str):
                        return obj['continuation']
                    for value in obj.values():
                        result = find_token(value)
                        if result: return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_token(item)
                        if result: return result
                return None
            return find_token(data)
        except:
            return None

    def _extract_next_continuation(self, data):
        try:
            def find_token(obj):
                if isinstance(obj, dict):
                    if 'continuationCommand' in obj and 'token' in obj['continuationCommand']:
                        return obj['continuationCommand']['token']
                    if 'continuation' in obj and isinstance(obj['continuation'], str):
                        return obj['continuation']
                    for value in obj.values():
                        result = find_token(value)
                        if result: return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_token(item)
                        if result: return result
                return None
            return find_token(data)
        except:
            return None

    def _extract_videos_from_api(self, data, limit=30):
        videos = []
        try:
            def extract_videos(obj):
                items = []
                if isinstance(obj, dict):
                    if 'videoRenderer' in obj or 'compactVideoRenderer' in obj:
                        items.append(obj)
                    else:
                        for value in obj.values(): items.extend(extract_videos(value))
                elif isinstance(obj, list):
                    for item in obj: items.extend(extract_videos(item))
                return items
            video_items = extract_videos(data)
            seen = set()
            for item in video_items[:limit]:
                video = self._parse_video_renderer(item['videoRenderer']) if 'videoRenderer' in item else (self._parse_compact_video_renderer(item['compactVideoRenderer']) if 'compactVideoRenderer' in item else None)
                if video and video['vod_id'] not in seen:
                    seen.add(video['vod_id'])
                    videos.append(video)
        except:
            pass
        return videos

    def _parse_video_renderer(self, renderer):
        try:
            video_id = renderer.get('videoId', '')
            if len(video_id) != 11: return None
            title = ''
            if 'title' in renderer:
                if 'runs' in renderer['title'] and renderer['title']['runs']: title = renderer['title']['runs'][0]['text']
                elif 'simpleText' in renderer['title']: title = renderer['title']['simpleText']
            if not title: return None
            title = html.unescape(title)
            duration = renderer.get('lengthText', {}).get('simpleText', '')
            return {"vod_id": video_id, "vod_name": title, "vod_pic": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg", "vod_remarks": self._get_vod_remarks(title, duration)}
        except:
            return None

    def _parse_compact_video_renderer(self, renderer):
        try:
            video_id = renderer.get('videoId', '')
            if len(video_id) != 11: return None
            title = ''
            if 'title' in renderer:
                if 'runs' in renderer['title'] and renderer['title']['runs']: title = renderer['title']['runs'][0]['text']
                elif 'simpleText' in renderer['title']: title = renderer['title']['simpleText']
            if not title: return None
            title = html.unescape(title.replace('\\u0026', '&').replace('\\"', '"'))
            duration = renderer.get('lengthText', {}).get('simpleText', '') if 'simpleText' in renderer.get('lengthText', {}) else (renderer['lengthText']['runs'][0]['text'] if 'runs' in renderer.get('lengthText', {}) and renderer['lengthText']['runs'] else '')
            return {"vod_id": video_id, "vod_name": title, "vod_pic": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg", "vod_remarks": self._get_vod_remarks(title, duration)}
        except:
            return None

    def _extract_videos_fixed(self, html_content, limit=50):
        videos = []
        try:
            pattern = r'var ytInitialData = ({.+?});</script>'
            match = re.search(pattern, html_content, re.DOTALL)
            if not match: return videos
            data = json.loads(match.group(1))
            def find_videos(obj):
                items = []
                if isinstance(obj, dict):
                    if 'videoRenderer' in obj or 'compactVideoRenderer' in obj: items.append(obj)
                    else:
                        for value in obj.values(): items.extend(find_videos(value))
                elif isinstance(obj, list):
                    for item in obj: items.extend(find_videos(item))
                return items
            video_items = find_videos(data)
            seen = set()
            for item in video_items[:limit]:
                video = self._parse_video_renderer(item['videoRenderer']) if 'videoRenderer' in item else (self._parse_compact_video_renderer(item['compactVideoRenderer']) if 'compactVideoRenderer' in item else None)
                if video and video['vod_id'] not in seen:
                    seen.add(video['vod_id'])
                    videos.append(video)
        except:
            pass
        return videos

    def _safe_title(self, title, max_len=80):
        if not title: return "未知标题"
        title = str(title)
        for char in ['#', '$', '/', '\\', '?', '&', '=', '+', '%', '@', '!', '*', '|', '<', '>', '"', "'"]:
            title = title.replace(char, '·')
        if len(title) > max_len: title = title[:max_len] + '...'
        return title

    def _get_video_title(self, video_id):
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            r = requests.get(oembed_url, headers=self.header, timeout=5, proxies=self.proxies)
            if r.status_code == 200: return html.unescape(r.json().get('title', video_id))
        except: pass
        return video_id

    def _extract_channel_display_name(self, html_content):
        try:
            # 多重保险正则抓取真实名称，防空值借用
            m = re.search(r'"ownerChannelName":"([^"]+)"', html_content)
            if m and m.group(1).strip(): return m.group(1).strip()
            m = re.search(r'"author":"([^"]+)"', html_content)
            if m and m.group(1).strip(): return m.group(1).strip()
            m = re.search(r'"content":"@([^"\s<>/?&#\\]+)"', html_content)
            if m and m.group(1).strip(): return m.group(1).strip()
        except: pass
        return ''

    def _get_channel_identifier_by_search(self, channel_name):
        if not channel_name or channel_name == "未知播主": return ''
        try:
            search_url = f"https://www.youtube.com/results?search_query={quote(channel_name)}"
            r = requests.get(search_url, headers=self.header, timeout=10, proxies=self.proxies)
            matches = re.findall(r'@([^"\s<>/?&#\\]+)', r.text)
            if matches: return unquote(max(matches, key=len))
        except: pass
        return channel_name

    def removeHtmlTags(self, src):
        from re import sub, compile
        return sub(compile('<.*?>'), '', src)

    def cleanText(self, text):
        return text.replace('\n', '').replace('\r', '').replace('\t', '')

    def getCache(self, key): return None
    def setCache(self, key, value): pass
    def delCache(self, key): pass
    def destroy(self): pass