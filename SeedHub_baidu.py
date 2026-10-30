# coding=utf-8
import sys
import os
import re
import json
import time
import base64
import html as html_lib
import urllib.parse
import urllib.request
import urllib.error
try:
    import warnings
    warnings.filterwarnings('ignore')
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

from base.spider import Spider
from bs4 import BeautifulSoup


class Spider(Spider):
    """SeedHub 影视资源站 - 适配 TVBox / 蜂蜜影视"""

    # ==================== 基本配置 ====================

    # 网盘线路是否走 push:// (蜂蜜影视/TVBox 的网盘推送,需先在设置里绑定网盘账号)
    # 若用不支持推送的播放器,改成 False 则返回网盘原始分享链接
    # 所有线路(磁力 + 网盘)统一包成 push:// 交给 feimao jar 的 csp_Push 处理
    # 若播放器不支持推送,改成 False 则返回原始链接
    PUSH_ALL = True
    KEEP_FROMS = ("百度",)   # 百度专版: 只输出百度线路
    # --- 夸克分享有效性检测 ---
    BAIDU_CHECK = True       # 只输出能正常打开的百度分享
    BAIDU_CHECK_N = 12       # 最多检查多少条
    BAIDU_NEED = 4           # 最多保留几条已验证线路
    CHECK_WORKERS = 12       # 并发线程数
    CHECK_BATCH = 6          # 分批检查,每批 6 条,凑够 BAIDU_NEED 就停
    CHECK_TIMEOUT = 5        # 单条解析/检测超时
    CHECK_BUDGET = 15        # 检测总时间预算(秒)
    SEED_LIMIT = 40      # 磁力线路最多条数(磁力已剔除,保留配置项)
    PAN_LIMIT = 40       # 每个网盘最多条数
    # 详情页不再预解析任何链接: 只有你手动点线路时才去解析并推送,
    # 避免一进详情页就自动解析/自动拉起推送。
    INLINE_RESOLVE = False
    INLINE_SEED = 0
    INLINE_PAN = 0

    def getName(self):
        return "SeedHub百度 v1"

    def init(self, extend=""):
        self.host = "https://seedog.cc"          # 当前主域名(sidhub.cc 会 302 到这里)
        if extend:
            ext = str(extend).strip()
            if ext.startswith("http"):
                self.host = ext.rstrip("/")
        self.timeout = 15
        self._types_cache = None
        self._link_cache = {}
        self._valid_cache = {}
        print(f"SeedHub init: {self.host}")

    def getDependence(self):
        return ["bs4"]

    def header(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.host + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

    # ==================== 工具方法 ====================

    def resolve_many(self, items, limit):
        """
        把 [(name, link)] 的前 limit 条并发解析成真实链接(magnet / 网盘直链),
        失败的保留原短链,交给 playerContent 再兜底解析。
        """
        items = list(items)
        if not self.INLINE_RESOLVE or not items or limit <= 0:
            return items
        head, tail = items[:limit], items[limit:]
        out = []
        for n, u in head:
            r = ''
            try:
                r = self.resolve_link(u)
            except Exception as e:
                print(f"【预解析】失败 {e}")
            out.append((n, r or u))
        print(f"【预解析】{sum(1 for _, u in out if u.startswith('magnet') or 'pan.' in u or 'drive.' in u)}/{len(head)} 条已解析成真实链接")
        out.extend(tail)
        return out
        out = [(n, real.get(u) or u) for n, u in head]
        out.extend(tail)
        return out

    def fetch_html(self, url, referer=None, retry=2, timeout=None):
        """抓页面(失败自动重试),最终失败返回空串"""
        h = self.header()
        if referer:
            h['Referer'] = referer
        last_err = None
        for _ in range(retry + 1):
            try:
                rsp = self.fetch(url, headers=h, timeout=timeout or self.timeout)
            except TypeError:
                try:
                    rsp = self.fetch(url, headers=h)
                except Exception as e:
                    last_err = e
                    continue
            except Exception as e:
                last_err = e
                continue
            try:
                text = rsp.text
            except Exception:
                text = ''
            if not text:
                try:
                    text = rsp.content.decode('utf-8', 'ignore')
                except Exception:
                    text = ''
            if text:
                return text
        print(f"fetch error {url}: {last_err}")
        return ""

    def build_full_url(self, url):
        """将相对路径补全为完整URL"""
        if not url or not isinstance(url, str):
            return ''
        url = html_lib.unescape(url.strip())
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if not url or url in ['null', 'undefined', '#']:
            return ''
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return self.host + url
        if url.startswith('./'):
            return self.host + url[1:]
        return self.host + '/' + url

    def short_link(self, href):
        """
        把 /link_start/?seed_id=xxx&movie_title=中文... 精简成纯 ASCII 短链。
        中文参数在部分播放器里会被二次编码/截断,导致解析失败,索性全部丢掉。
        """
        href = html_lib.unescape(str(href or ''))
        m = re.search(r'seed_id=([A-Za-z0-9]+)', href)
        if m:
            return f"{self.host}/link_start/?seed_id={m.group(1)}"
        m = re.search(r'redirect_to=([A-Za-z0-9_]+)', href)
        if m:
            return f"{self.host}/link_start/?redirect_to={m.group(1)}"
        return self.build_full_url(href)

    def seed_rank(self, name):
        """磁力排序: 4K > 1080P > 720P > 其他"""
        n = str(name).lower()
        if '2160' in n or '4k' in n or 'uhd' in n:
            return 0
        if '1080' in n:
            return 1
        if '720' in n:
            return 2
        return 3

    def pan_group(self, domain):
        table = [
            ("quark", "夸克"),
            ("baidu", "百度"),
            ("xunlei", "迅雷"),
            ("uc.cn", "UC"),
            ("alipan", "阿里"),
            ("aliyundrive", "阿里"),
            ("189.cn", "天翼"),
            ("115", "115"),
        ]
        d = str(domain or '').lower()
        for k, v in table:
            if k in d:
                return v
        return "其他网盘"

    def clean_name(self, name):
        """去掉标题前的 '# ' 锚点符号"""
        if not name:
            return ''
        name = str(name).replace('\u200b', '').replace('\u200e', '')
        name = re.sub(r'^\s*#+\s*', '', name)
        return re.sub(r'\s+', ' ', name).strip()

    def sanitize(self, text, limit=24):
        """$ 与 # 是播放列表分隔符必须替换; 名称过长会把选集 UI 撑坏,统一截断"""
        text = str(text or '')
        for ch in ('\ufe0f', '\ufe0e', '\u200b', '\u200e', '\u2060', '\u00a0'):
            text = text.replace(ch, '')
        text = text.replace('$', '＄').replace('#', '＃').replace('|', '｜')
        text = re.sub(r'\s+', ' ', text).strip()
        text = text.strip(' -—·')
        if limit and len(text) > limit:
            text = text[:limit]
        return text

    def extract_pic(self, element):
        pic = ''
        img = element.find('img') if hasattr(element, 'find') else None
        if img:
            pic = img.get('data-original', '') or img.get('data-src', '') or img.get('src', '')
        if not pic and hasattr(element, 'get'):
            pic = element.get('data-original', '') or element.get('src', '')
        if not pic and hasattr(element, 'get'):
            style = element.get('style', '') or ''
            m = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
            if m:
                pic = m.group(1)
        return self.build_full_url(pic) if pic else ''

    def extract_remark(self, element):
        """提取备注(本站无 pic-text,兼容保留)"""
        remark = ''
        span = element.find('span', class_='pic-text') if hasattr(element, 'find') else None
        if span:
            remark = span.get_text(strip=True)
        return remark

    def force_gbk(self, rsp):
        try:
            rsp.encoding = "gbk"
        except Exception:
            pass
        return rsp

    def get_label_by_previous(self, a_tag):
        label = ""
        try:
            for sib in a_tag.previous_siblings:
                if getattr(sib, "name", None) in ["br", "p", "a"]:
                    break
                txt = sib.strip() if isinstance(sib, str) else sib.get_text(" ", strip=True)
                if txt:
                    label = txt + label
        except Exception:
            pass
        return re.sub(r"\s+", " ", label).strip()

    def is_4k_resource(self, name):
        name = str(name).lower()
        return any(x in name for x in ["2160p", "4k", "uhd", "hdr"])

    def is_push_resource(self, title):
        if not title:
            return True
        title = str(title)
        for k in ["全集", "打包", "01-", "01~", "01至"]:
            if k in title:
                return True
        if re.fullmatch(r"\d+", title):
            return False
        if re.fullmatch(r"第?\d+[集话期]?", title):
            return False
        return True

    def extract_text_after(self, text, keyword):
        if keyword in text:
            return text.split(keyword)[-1].strip()
        return ""

    def page_count(self, soup):
        """从 .page-nav 里取最大页码"""
        pn = soup.select_one('.page-nav')
        if not pn:
            return 1
        mx = 1
        for a in pn.find_all('a', href=True):
            m = re.search(r'[?&]page=(\d+)', a['href'])
            if m:
                try:
                    mx = max(mx, int(m.group(1)))
                except Exception:
                    pass
        return mx

    # ==================== 列表解析 ====================

    def parse_covers(self, soup):
        """解析所有 .cover 卡片(首页/分类/搜索通用)"""
        videos = []
        for cover in soup.select('div.cover-container div.cover'):
            a = cover.select_one('a.image')
            if not a or not a.get('href'):
                continue
            vod_id = self.build_full_url(a.get('href'))
            img = a.find('img')
            name = ''
            h2 = cover.select_one('h2')
            if h2:
                name = self.clean_name(h2.get_text(strip=True))
            if not name and img:
                name = self.clean_name(img.get('alt'))
            if not name:
                continue

            pic = self.extract_pic(a)
            lis = cover.select('ul > li')

            year = ''
            kinds = ''
            if len(lis) > 1:
                meta = lis[1].get_text(' ', strip=True)
                parts = [p.strip() for p in meta.split('/') if p.strip()]
                for p in parts:
                    if re.fullmatch(r'(19|20)\d{2}', p):
                        year = p
                        break
                if len(parts) > 1:
                    kinds = parts[1]

            score = ''
            for li in lis:
                t = li.get_text(' ', strip=True)
                m = re.search(r'豆瓣评分[:：]?\s*([\d.]+)', t)
                if m:
                    score = m.group(1)

            remarks = []
            if score:
                remarks.append('豆瓣' + score)
            if year:
                remarks.append(year)
            elif kinds:
                remarks.append(kinds)

            videos.append({
                "vod_id": vod_id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": ' · '.join(remarks)
            })
        return videos

    # ==================== 首页 ====================

    def _load_types(self):
        """从侧边栏抓取各分类下的子类型"""
        if self._types_cache is not None:
            return self._types_cache
        cache = {'1': [], '2': [], '3': []}
        try:
            soup = BeautifulSoup(self.fetch_html(self.host + '/'), 'html.parser')
            for a in soup.select('.sidebar-links a'):
                href = a.get('href') or ''
                m = re.match(r'^/categories/(\d+)/types/(\d+)/', href)
                if m:
                    cache.setdefault(m.group(1), []).append({
                        'n': self.clean_name(a.get_text(strip=True)),
                        'v': m.group(2)
                    })
        except Exception as e:
            print(f"load types error: {e}")
        self._types_cache = cache
        return cache

    def _build_filters(self):
        types = self._load_types()
        orders = [
            {"n": "最近更新", "v": "update"},
            {"n": "上映时间", "v": "date"},
            {"n": "豆瓣评分", "v": "score"},
        ]
        filters = {}
        for cid in ['1', '2', '3']:
            values = [{"n": "全部", "v": ""}] + types.get(cid, [])
            filters[cid] = [
                {"key": "type", "name": "类型", "value": values},
                {"key": "order", "name": "排序", "value": orders},
            ]
        return filters

    def homeContent(self, filter):
        result = {}
        classes = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "动漫"},
            {"type_id": "3", "type_name": "剧集"},
        ]
        result["class"] = classes
        try:
            result["filters"] = self._build_filters()
        except Exception as e:
            print(f"filters error: {e}")
            result["filters"] = {}

        videos = []
        try:
            soup = BeautifulSoup(self.fetch_html(self.host + '/'), 'html.parser')
            videos = self.parse_covers(soup)

            seen = set()
            unique = []
            for v in videos:
                if v['vod_id'] not in seen and v['vod_name']:
                    seen.add(v['vod_id'])
                    unique.append(v)
                    if len(unique) >= 60:
                        break
            videos = unique
        except Exception as e:
            print(f"homeContent error: {e}")
            videos = []

        result["list"] = videos
        return result

    def homeVideoContent(self):
        return self.homeContent(False)

    # ==================== 分类页 ====================

    def _split_tid(self, tid):
        tid = str(tid)
        if '-' in tid:
            cid, sub = tid.split('-', 1)
            return cid, sub
        return tid, ''

    def categoryContent(self, tid, pg, filter, extend):
        result = {
            "list": [], "pagecount": 1,
            "page": pg, "limit": 0, "total": 0
        }
        try:
            pg = int(pg or 1)
            ext = extend if isinstance(extend, dict) else {}
            cid, sub = self._split_tid(tid)
            sub = str(ext.get('type') or '').strip() or sub

            if sub:
                url = f"{self.host}/categories/{cid}/types/{sub}/movies/"
            else:
                url = f"{self.host}/categories/{cid}/movies/"

            params = {}
            if pg > 1:
                params['page'] = pg
            order = str(ext.get('order') or '').strip()
            if order:
                params['order'] = order
            if params:
                url += '?' + urllib.parse.urlencode(params)

            print(f"category: {url}")
            soup = BeautifulSoup(self.fetch_html(url), 'html.parser')
            videos = self.parse_covers(soup)

            result["list"] = videos
            result["pagecount"] = self.page_count(soup)
            result["page"] = pg
            result["limit"] = len(videos)
            result["total"] = result["pagecount"] * 20 if videos else 0
        except Exception as e:
            print(f"categoryContent error: {e}")
        return result

    # ==================== 详情页 ====================

    def _info_map(self, cover_box):
        """把 详情页 .cover-container 里的 li 拆成 key -> value"""
        info = {}
        if not cover_box:
            return info
        for li in cover_box.select('ul > li'):
            text = li.get_text(' ', strip=True)
            if not text:
                continue
            m = re.match(r'^([^:：]{1,12})[:：]\s*(.*)$', text)
            if m:
                info[m.group(1).strip()] = m.group(2).strip()
        return info

    def detailContent(self, ids):
        result = {}
        try:
            vid = ids[0] if isinstance(ids, list) else ids
            vid = self.build_full_url(vid)
            print(f"detail: {vid}")
            page = self.fetch_html(vid)
            soup = BeautifulSoup(page, 'html.parser')

            vod = {
                "vod_id": vid, "vod_name": "", "vod_pic": "",
                "vod_actor": "", "vod_director": "", "vod_content": "",
                "vod_area": "", "vod_year": "", "vod_remarks": "",
                "vod_play_from": "", "vod_play_url": ""
            }

            # ---- 标题 ----
            h1 = soup.select_one('div.content h1') or soup.find('h1')
            if h1:
                vod["vod_name"] = self.clean_name(h1.get_text(' ', strip=True))
            if not vod["vod_name"]:
                t = soup.find('title')
                if t:
                    vod["vod_name"] = self.clean_name(t.get_text().split('-')[0])

            # ---- 封面 & 元信息 ----
            cover_box = soup.select_one('div.content div.cover-container')
            if cover_box:
                img = cover_box.find('img')
                if img:
                    vod["vod_pic"] = self.build_full_url(
                        img.get('data-original') or img.get('src') or '')
            if not vod["vod_pic"]:
                og = soup.find('meta', property='og:image')
                if og:
                    vod["vod_pic"] = og.get('content', '')

            info = self._info_map(cover_box)
            vod["vod_director"] = info.get('导演', '')
            vod["vod_actor"] = info.get('主演', '').replace('......', '').strip()
            vod["vod_area"] = info.get('制片国家/地区', '') or info.get('地区', '')

            y = info.get('首播', '') or info.get('上映', '') or info.get('上映日期', '')
            ym = re.search(r'((?:19|20)\d{2})', y)
            vod["vod_year"] = ym.group(1) if ym else ''

            # 详情页不显示"豆瓣X · 共N集"这种备注
            # 需要恢复就把 assemble 逻辑放回来
            vod["vod_remarks"] = ""

            # ---- 简介 ----
            desc_h = soup.select_one('h2#description')
            if desc_h:
                p = desc_h.find_next_sibling('p')
                if p:
                    vod["vod_content"] = p.get_text(' ', strip=True)
            if not vod["vod_content"]:
                d = soup.find('meta', attrs={'name': 'description'})
                if d:
                    vod["vod_content"] = d.get('content', '')

            # ---- 播放列表 ----
            play_froms = []
            play_urls = []

            # 1) 磁力(seed-list)
            seeds = []
            for a in soup.select('div.seed-list ul.seeds li a[href]'):
                link = self.short_link(a.get('href'))
                if not link:
                    continue
                name = a.get('title') or a.get_text(' ', strip=True)
                li = a.find_parent('li')
                size = ''
                if li:
                    code = li.find('code', class_='size')
                    if code:
                        size = code.get_text(strip=True)
                name = self.sanitize(name)
                if size and size not in name:
                    name = f"{name} [{size}]"
                seeds.append((self.seed_rank(name), len(seeds), name, link))
            seeds.sort(key=lambda x: (x[0], x[1]))
            seed_list = [(n, u) for _, _, n, u in seeds[:self.SEED_LIMIT]]
            if seed_list and "磁力" in self.KEEP_FROMS:
                seed_list = self.resolve_many(seed_list, self.INLINE_SEED)
                play_froms.append("磁力")
                play_urls.append('#'.join(f"{n}${u}" for n, u in seed_list))

            # 2) 网盘(pan-links),按网盘类型分组
            groups = {}
            for a in soup.select('ul.pan-links li a[href]'):
                link = self.short_link(a.get('href'))
                if not link:
                    continue
                gname = self.pan_group(a.get('data-link'))
                name = self.sanitize(a.get('title') or a.get_text(' ', strip=True))
                groups.setdefault(gname, []).append((name, link))

            order_names = ["夸克", "UC", "阿里", "天翼", "115", "百度", "迅雷", "其他网盘"]
            order_names += [k for k in groups.keys() if k not in order_names]
            for gname in order_names:
                if gname not in self.KEEP_FROMS:
                    continue
                items = groups.get(gname) or []
                if not items:
                    continue
                if gname == "百度" and self.BAIDU_CHECK:
                    items = self.filter_valid(items[:self.BAIDU_CHECK_N])
                    ok_n, chk_n = getattr(self, 'last_stat', (0, 0))
                    gname = "百度v1✓%d/%d" % (ok_n, chk_n)
                else:
                    items = items[:self.PAN_LIMIT]
                    items = self.resolve_many(items, self.INLINE_PAN)
                play_froms.append(gname)
                play_urls.append('#'.join(f"{n}${u}" for n, u in items))

            vod["vod_play_from"] = '$$$'.join(play_froms)
            vod["vod_play_url"] = '$$$'.join(play_urls)

            result["list"] = [vod]
        except Exception as e:
            print(f"detailContent error: {e}")
            import traceback
            traceback.print_exc()
            result["list"] = []
        return result

    # ==================== 搜索 ====================

    def searchContent(self, key, quick, pg=1):
        print(f"【搜索】{key} 第{pg}页")
        return self._do_search(key, pg)

    def searchContentPage(self, key, quick, pg):
        return self._do_search(key, pg)

    def search(self, key):
        return self._do_search(key, 1)

    def find(self, key):
        return self._do_search(key, 1)

    def query(self, key):
        return self._do_search(key, 1)

    def searchPage(self, key, pg):
        return self._do_search(key, pg)

    def _do_search(self, key, pg=1):
        result = {"list": [], "pagecount": 1, "page": pg, "limit": 0, "total": 0}
        try:
            pg = int(pg or 1)
            kw = urllib.parse.quote(str(key).strip(), safe='')
            url = f"{self.host}/s/{kw}/"
            if pg > 1:
                url += f"?page={pg}"
            print(f"搜索URL: {url}")

            soup = BeautifulSoup(self.fetch_html(url, referer=self.host + '/'), 'html.parser')
            videos = self.parse_covers(soup)

            result["list"] = videos
            result["pagecount"] = self.page_count(soup)
            result["page"] = pg
            result["limit"] = len(videos)
            result["total"] = result["pagecount"] * len(videos) if videos else 0
            print(f"找到 {len(videos)} 个结果")
        except Exception as e:
            print(f"搜索错误: {e}")
            import traceback
            traceback.print_exc()
        return result

    # ==================== 播放 ====================

    # ==================== 百度网盘有效性检测 ====================
    # 说明: 百度分享页可直接判断"是否还能打开"
    #   有效 -> 200 + "请输入提取码" / "文件列表"
    #   失效 -> 404 + "页面不存在" 或 "分享的文件已经被取消"
    # 百度列目录需要 POST 校验提取码 + cookie, 步骤多且不稳, 这里只做存在性判断

    def _http_text(self, url, payload=None):
        h = {'User-Agent': self.header()['User-Agent'],
             'Referer': 'https://pan.baidu.com/',
             'Accept-Encoding': 'identity'}
        try:
            import requests
            try:
                if payload is None:
                    r = requests.get(url, headers=h, timeout=self.CHECK_TIMEOUT, verify=False)
                else:
                    r = requests.post(url, headers=h, data=payload,
                                      timeout=self.CHECK_TIMEOUT, verify=False)
                return r.status_code, r.text or ''
            except Exception:
                pass
        except Exception:
            pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=self.CHECK_TIMEOUT) as r:
                return r.status, r.read().decode('utf-8', 'ignore')
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read().decode('utf-8', 'ignore')
            except Exception:
                return e.code, ''
        except Exception:
            return None, ''

    def normalize_baidu(self, url):
        # 百度分享链接常带 dp-logid / 追踪参数, 有些解析器会因此失败
        # 统一净化成 https://pan.baidu.com/s/{surl}[?pwd=xxxx]
        url = str(url or '').strip()
        m = re.search(r'pan\.baidu\.com/s/([A-Za-z0-9_\-]+)', url)
        if not m:
            return url
        surl = m.group(1)
        pm = re.search(r'[?&]pwd=([A-Za-z0-9]{1,8})', url)
        return f"https://pan.baidu.com/s/{surl}" + (f"?pwd={pm.group(1)}" if pm else "")

    def check_baidu(self, url):
        """True=分享还能打开 / False=已失效 / None=查不出"""
        if not url:
            return None
        key = 'b_' + url
        if key in self._valid_cache:
            return self._valid_cache[key]
        code, text = self._http_text(url)
        if code is None:
            return None
        if code == 404:
            self._valid_cache[key] = False
            return False
        bad = ('分享的文件已经被取消', '链接不存在', '你访问的页面不存在',
               '分享已过期', '来晚了')
        if any(k in text for k in bad):
            self._valid_cache[key] = False
            return False
        good = ('请输入提取码', '文件列表', '分享的文件', '提取文件')
        ok = any(k in text for k in good)
        self._valid_cache[key] = ok
        return True if ok else None

    VIDEO_EXT = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.ts', '.m2ts',
                 '.rmvb', '.rm', '.webm', '.iso', '.mpg', '.mpeg', '.m4v')

    def filter_valid(self, items):
        """
        并发检测前 N 条:
          True  -> 已验证可播,排前面
          False -> 分享里没有视频/已失效,丢弃
          None  -> 超时查不出,保留并标记[未验证],避免整页空掉
        """
        items = list(items)[:self.BAIDU_CHECK_N]
        self.last_stat = (0, 0)
        if not items:
            return items

        def work(item):
            n, u = item
            try:
                real = self.resolve_link(u, timeout=self.CHECK_TIMEOUT)
            except Exception:
                real = ''
            if not real:
                return (n + "[未验证]", u, None)
            try:
                ok = self.check_baidu(real) if 'pan.baidu.com/s/' in real else None
            except Exception:
                ok = None
            return (n, real, ok)

        # 分批检查: 每批 CHECK_BATCH 条, 凑够 BAIDU_NEED 条已验证就停
        # 避免一次查 20 条把详情页拖到几十秒(首次播放容易失败)
        results = []
        i = 0
        while i < len(items):
            batch = items[i:i + self.CHECK_BATCH]
            i += self.CHECK_BATCH
            try:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(self.CHECK_WORKERS) as ex:
                    results.extend(ex.map(work, batch))
            except Exception as e:
                print(f"【检测】并发不可用,串行: {e}")
                results.extend([work(x) for x in batch])
            if sum(1 for _, _, ok in results if ok is True) >= self.BAIDU_NEED:
                break

        kept = [(n, u) for n, u, ok in results if ok is True]
        unv = [(n, u) for n, u, ok in results if ok is None]
        dropped = sum(1 for _, _, ok in results if ok is False)
        self.last_stat = (len(kept), len(items))
        print(f"【检测】{len(items)} 条 -> 已验证 {len(kept)}, 未验证 {len(unv)}, 剔除 {dropped}")

        out = kept[:self.BAIDU_NEED] + unv[:2]
        if not out:
            out = [(n, u) for n, u in items[:2]]
        return out

    def resolve_link(self, url, timeout=None):
        """解析 /link_start/ 中间页: 返回 magnet 或网盘直链(带缓存,同一条不重复请求)"""
        if url in self._link_cache:
            return self._link_cache[url]
        real = self._do_resolve(url, timeout)
        if real:
            self._link_cache[url] = real
        return real

    def _do_resolve(self, url, timeout=None):
        page = self.fetch_html(url, referer=self.host + '/',
                               retry=0 if timeout else 2, timeout=timeout)
        if not page:
            return ''

        # 1) 磁力: const data = "base64"
        m = re.search(r'const\s+data\s*=\s*["\']([A-Za-z0-9+/=\s]+)["\']', page)
        if m:
            raw = re.sub(r'\s+', '', m.group(1))
            raw += '=' * (-len(raw) % 4)
            try:
                dec = base64.b64decode(raw).decode('utf-8', 'ignore').strip()
                if dec.startswith('magnet:') or dec.startswith('http') or dec.startswith('ed2k:'):
                    return dec
            except Exception:
                pass

        # 2) 网盘: a.direct-pan
        soup = BeautifulSoup(page, 'html.parser')
        a = soup.select_one('a.direct-pan[href]')
        if a:
            link = html_lib.unescape(a.get('href', '')).strip()
            if link:
                if 'pwd=' not in link:
                    pwd = ''
                    for sel in ['span.tqm-value', 'span.tqmxl-value']:
                        el = soup.select_one(sel)
                        if el:
                            pwd = el.get_text(strip=True)
                            if pwd:
                                break
                    if not pwd:
                        pm = re.search(r'提取码[:：]\s*([A-Za-z0-9]{4})', page)
                        if pm:
                            pwd = pm.group(1)
                    if pwd:
                        link += ('&' if '?' in link else '?') + 'pwd=' + pwd
                return link

        # 3) 兜底: 页面里的 magnet 文本
        mm = re.search(r'magnet:\?[^"\'\s<]+', page)
        if mm:
            return mm.group(0)
        return ''

    def looks_like_url(self, s):
        s = str(s or '').strip()
        if not s:
            return False
        return ('://' in s) or s.startswith('magnet:') or s.startswith('ed2k:') \
            or 'link_start' in s or s.startswith('/')

    def playerContent(self, flag, id, vipFlags=None):
        """
        TVBox/蜂蜜 的调用约定是 playerContent(flag, id, vipFlags):
            flag = 播放源名(磁力/夸克/百度...)
            id   = 播放地址
        这里同时兼容 (ids, flag, ext) 的写法,靠"哪个参数长得像链接"来判定。
        """
        a, b = str(flag or '').strip(), str(id or '').strip()
        if self.looks_like_url(b) or not self.looks_like_url(a):
            url, fl = b, a
        else:
            url, fl = a, b

        # 部分播放器会对 url 里的 & 做二次编码,先还原
        if '%26' in url or '%3F' in url or '%3D' in url:
            try:
                url = urllib.parse.unquote(url)
            except Exception:
                pass
        url = html_lib.unescape(url).strip()
        if url.startswith('push://'):
            url = url[7:]

        need_resolve = ('/link_start/' in url) or ('seed_id=' in url) or ('redirect_to=' in url)
        if need_resolve:
            try:
                real = self.resolve_link(url)
                if real:
                    url = real
                else:
                    print(f"【播放】解析失败, 不返回网页: {url}")
                    return {"parse": 0, "url": ""}
            except Exception as e:
                print(f"【播放】解析异常: {e}")

        push = self.PUSH_ALL or ("推送" in fl)
        if push and not url.startswith('push://'):
            url = 'push://' + url
        print(f"【播放】{fl} -> {url[:130]}")
        return {"parse": 0, "url": url}

    def is_video_url(self, url):
        if not url:
            return False
        video_exts = ['.mp4', '.m3u8', '.flv', '.avi', '.mkv', '.wmv', '.mov']
        return any(e in url.lower() for e in video_exts)

    def extract_video_url(self, page_url):
        return page_url

    def isVideoFormat(self, url):
        return self.is_video_url(url)

    def manualVideoCheck(self):
        pass

    def localProxy(self, param):
        return None

    def destroy(self):
        pass
