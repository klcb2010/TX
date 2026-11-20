# 电影港·百度版(只出百度网盘线路)
# 站点配置: {"key":"dygb","name":"电影港百度[网盘]","type":3,"api":"./dygang_baidu.py",
#            "searchable":1,"changeable":0,"quickSearch":1,"filterable":0,"playerType":2}
# coding=utf-8
# 电影港 dygang.tv — 网盘推送版
# 改造要点:
#   1) 详情页识别 夸克/百度/迅雷/UC/天翼/移动/阿里/115/微云/PikPak + 磁力, 每条一个播放源
#   2) 网盘点播一律 push:// 交给 feimao jar 的 csp_Push(原来是 quark/xunlei 两个硬编码名字)
#   3) 百度自动补提取码 ?pwd=
#   4) 播放前做有效性检测(夸克问 sharepage/token, 百度看发布页), 失效的不显示
#   5) 条目名用画质(4K/1080P/720P), 没有画质就"正片", 不再出现"迅雷云盘链接"这种噪音
import re
import json
import requests
from bs4 import BeautifulSoup
from base.spider import Spider

# ================= jar Java 桥: 把网盘分享直接展开成剧集(九七同款) =================
_JB_CACHE = []


def _plog(tag, msg):
    """诊断日志(默认关闭; 排查时删掉下面的 return)"""
    return
    try:
        import time as _t
        with open("/storage/emulated/0/MCP/pybridge.log", "a", encoding="utf-8") as _f:
            _f.write("%d %s | %s\n" % (int(_t.time()), tag, str(msg)[:800]))
    except Exception:
        pass



def _jb_loader():
    """探测 py 环境的 Java 桥, 返回类加载函数或 None(不可用)"""
    if _JB_CACHE:
        return _JB_CACHE[0]
    ldr = None
    try:
        from java import jclass as _c
        ldr = _c
    except Exception:
        for mod, attr in (("java", "jclass"), ("jnius", "autoclass"), ("pyjnius", "autoclass")):
            try:
                m = __import__(mod)
                ldr = getattr(m, attr, None)
                if ldr:
                    break
            except Exception:
                continue
        if not ldr:
            ldr = globals().get("jclass") or globals().get("autoclass")
    _plog("JBRIDGE", "on" if ldr else "off")
    try:
        print("dygang JBRIDGE=%s" % ("on" if ldr else "off"))
    except Exception:
        pass
    _JB_CACHE.append(ldr)
    return ldr


def _pan_vod(link, pwd=""):
    """调 jar 的 PanWebSite.detailFromShareUrl 展开网盘分享, 返回 vod dict 或 None"""
    ldr = _jb_loader()
    _plog("PANCALL", "loader=%s link=%s" % ("y" if ldr else "n", str(link)[:120]))
    if not ldr or not link:
        return None
    try:
        cls = ldr("com.github.catvod.spider.PanWebSite")
        s = cls.detailFromShareUrl(str(link), str(pwd or ""))
    except Exception as e:
        try:
            print("dygang PAN-EXPAND err %s" % e)
        except Exception:
            pass
        _plog("PANERR", "%s: %s" % (type(e).__name__, str(e)[:300]))
        return None
    try:
        _plog("PANRAW", "type=%s val=%s" % (type(s).__name__, str(s)[:200]))
    except Exception:
        pass
    try:
        txt = s if isinstance(s, str) else s.toString()
    except Exception:
        try:
            txt = str(s)
        except Exception:
            return None
    if not txt or len(txt) < 20:
        _plog("PANSHORT", str(txt)[:200])
        return None
    try:
        d = json.loads(txt)
    except Exception as e2:
        _plog("PANJSON", "%s | %s" % (type(e2).__name__, txt[:300]))
        return None
    if isinstance(d, dict):
        lst = d.get("list")
        if isinstance(lst, list) and lst and isinstance(lst[0], dict):
            return lst[0]
        if d.get("vod_play_url") or d.get("vod_id"):
            return d
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return d[0]
    return None



class Spider(Spider):

    def getName(self):
        return "电影港百度[网盘]"

    def init(self, extend=""):
        self.host = "https://www.dygang.tv"
        self.EXPAND = False     # 关: 不用 Java 桥展开(回到早上版本, 少一次失败跳转)
        self.EXPAND_MAX = 6     # 每次详情最多展开几条分享

    def header(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.host
        }

    # ==================== 网盘工具 ====================

    # 域名关键字 -> 播放源名
    DISK_RULES = (
        ("pan.quark.cn", "夸克"),
        ("baidu.com", "百度"),
        ("pan.xunlei.com", "迅雷"),
        ("pan.uc.cn", "UC"), ("drive.uc.cn", "UC"), ("fast.uc.cn", "UC"),
        ("cloud.189.cn", "天翼"),
        ("caiyun.139.com", "移动"),
        ("alipan.com", "阿里"), ("aliyundrive.com", "阿里"),
        ("115.com", "115"), ("115cdn.com", "115"),
        ("share.weiyun.com", "微云"),
        ("mypikpak.com", "PikPak"),
    )
    # 播放源显示顺序(磁力放最后)
    DISK_ORDER = ("夸克", "百度", "迅雷", "UC", "天翼", "移动", "阿里",
                  "115", "微云", "PikPak", "磁力")

    # 本版出哪些播放源(顺序无关, 显示顺序由 DISK_ORDER 决定); 拆分版会改这里
    KEEP = ("百度",)

    # jar 的解析档位名(默认配置: quarkHD=夸克无限, ucHD=UC无限,
    # baiduHD=百度原画|百度无限, aliHD=阿里原画)。线路名必须用它认识的名字,
    # 否则 Push.playerContent 走不到对应解析分支, 表现就是"10几K后归零"。
    # 九七的线路名就是"夸克无限#1"。
    FROM_NAME = {
        "夸克": "夸克无限",
        "百度": "百度无限",
        "UC": "UC无限",
        "阿里": "阿里原画",
        "天翼": "天翼",
        "移动": "移动智能",
        "迅雷": "迅雷",
        "115": "115",
        "微云": "微云",
        "PikPak": "PikPak",
    }

    @classmethod
    def _from_name(cls, k):
        return cls.FROM_NAME.get(str(k or ""), str(k or ""))
    KEEP_MAGNET = False      # 磁力: 蜂蜜里 push 不了、直接交给播放器也多半失败, 默认不出

    # 有效性检测: 失效的网盘不显示
    #   夸克: sharepage/token, code=0 才算能打开(失效时接口回 HTTP 404 + code 41006)
    #   百度: 打开发布页, "页面不存在/分享已失效" 判失效
    #   其它(迅雷/UC/天翼...): 查不了, 一律保留
    CHECK = True     # 详情页做有效性检测
    CHECK_TIMEOUT = 5

    def _disk_of(self, url):
        u = str(url or "").lower()
        for k, v in self.DISK_RULES:
            if k in u:
                return v
        return ""

    @staticmethod
    def _quality_of(text):
        t = str(text or "").lower()
        if ("2160" in t) or ("4k" in t):
            return "4K"
        if "1080" in t:
            return "1080P"
        if "720" in t:
            return "720P"
        if "蓝光" in t:
            return "蓝光"
        return ""

    @staticmethod
    def _pwd_of(s):
        m = re.search(r'(?:pwd|password|提取码|密码)\s*[=:：]?\s*([0-9a-zA-Z]{4})(?![0-9a-zA-Z])',
                      str(s or ""), re.I)
        return m.group(1) if m else ""

    @staticmethod
    def _fix_url(url, pwd=""):
        u = str(url or "").strip()
        if u.startswith("//"):
            u = "https:" + u
        if pwd and ("baidu.com" in u) and ("pwd=" not in u):
            u = u + ("&" if "?" in u else "?") + "pwd=" + pwd
        return u

    def _quark_ok(self, url):
        """True / False / None(查不出, 保留)"""
        m = re.search(r"pan\.quark\.cn/s/([0-9A-Za-z]+)", url or "")
        if not m:
            return None
        import urllib.request
        import urllib.error
        import ssl
        import gzip
        import json as _json
        api = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc&uc_param_str="
        body = _json.dumps({"pwd_id": m.group(1), "passcode": self._pwd_of(url)}).encode("utf-8")
        h = {"User-Agent": self.header().get("User-Agent", "Mozilla/5.0"),
             "Content-Type": "application/json", "Referer": "https://pan.quark.cn/",
             "Accept-Encoding": "gzip"}
        raw, hdr = b"", {}
        try:
            req = urllib.request.Request(api, data=body, headers=h, method="POST")
            rsp = urllib.request.urlopen(req, timeout=self.CHECK_TIMEOUT,
                                         context=ssl._create_unverified_context())
            raw, hdr = rsp.read(), rsp.headers
        except urllib.error.HTTPError as e:
            raw, hdr = e.read(), e.headers          # 失效分享走这里: 404 + code 41006
        except Exception:
            return None
        try:
            if (hdr.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.decompress(raw)
            code = _json.loads(raw.decode("utf-8", "ignore")).get("code")
        except Exception:
            return None
        if code == 0:
            return True
        try:
            _plog("QCODE", str(code))
        except Exception:
            pass
        if code in (41006, 41012):     # 41006 分享不存在 / 41012 已取消分享
            return False
        # 41011 在手机网络下也会出现在有效分享上(风控), 不能判死, 否则整条夸克线路消失
        # (= 用户看到的"不跳转")。只认 41006/41012 这两个确定的码。
        if code == 41011:
            _plog("Q41011", u[:100]) if False else None
            return None
        return None

    def _baidu_ok(self, url):
        try:
            res = requests.get(url, headers=self.header(), timeout=self.CHECK_TIMEOUT)
            head = (res.text or "")[:4000]
        except Exception:
            return None
        # 只有明确写着"不存在/失效"才判死; 风控页/中转页/精简页(四个关键词都没有)
        # 一律保留 —— 手机网络下百度常返回中转页, 按关键词缺失判死会把有效分享全灭。
        for w in ("页面不存在", "分享已失效", "链接不存在", "你所访问的页面不存在", "来晚了"):
            if w in head:
                return False
        return True

    _CHK = {}

    def _pan_ok(self, url):
        u = str(url or "")
        low = u.lower()
        if "quark.cn" not in low and "baidu.com" not in low:
            return None
        if u in self._CHK:
            return self._CHK[u]
        r = self._quark_ok(u) if "quark.cn" in low else self._baidu_ok(u)
        self._CHK[u] = r
        return r

    # ==================== 首页 / 分类 ====================

    def homeContent(self, filter):
        return {'class': [
            {"type_id": "/ys/", "type_name": "最新电影"},
            {"type_id": "/bd/", "type_name": "经典高清"},
            {"type_id": "/dsj/", "type_name": "国产剧"},
            {"type_id": "/yx/", "type_name": "美剧"},
            {"type_id": "/dmq/", "type_name": "动漫"}
        ]}

    def categoryContent(self, tid, pg, filter, extend):
        # 电影港分页规则：第一页 index.htm，后续 index_2.htm
        url = f"{self.host}{tid}index.htm" if str(pg) == "1" else f"{self.host}{tid}index_{pg}.htm"
        res = requests.get(url, headers=self.header(), timeout=20)
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'html.parser')
        vod_list = []
        for item in soup.select('table.border1'):
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
        name = str(name or "").lower()
        if '2160' in name or '4k' in name:
            return 0
        if '1080' in name:
            return 1
        if '720' in name:
            return 2
        return 3

    def _expand_from(self, name, items):
        """把一组网盘条目展开成剧集: items=[(排序键, 条目名, 链接)]; 返回 (新from, 新url)"""
        sub, keep, cnt = {}, [], 0
        for it in items:
            nm = it[1] if len(it) > 1 else ""
            u = (it[2] if len(it) > 2 else "").strip()
            if not u:
                continue
            v = None
            if self.EXPAND and cnt < self.EXPAND_MAX and self._disk_of(u):
                v = _pan_vod(u, self._pwd_of(u))
                if v:
                    cnt += 1
            if v:
                fs = str(v.get("vod_play_from") or "")
                us = str(v.get("vod_play_url") or "")
                if us:
                    fl = fs.split("$$$") if fs else []
                    for i, seg in enumerate(us.split("$$$")):
                        f = (fl[i] if i < len(fl) and fl[i].strip() else "") or name
                        sub.setdefault(f, [])
                        sub[f].extend([x for x in seg.split("#") if x])
                    print("dygang 展开 [%s] -> %d 集" % (name, sum(len(x) for x in sub.values())))
                    continue
            keep.append("%s$%s" % (nm or "正片", u))
        out_f, out_u = [], []
        for f, eps in sub.items():
            if eps:
                out_f.append(f)
                out_u.append("#".join(eps))
        if keep:
            out_f.append(name)
            out_u.append("#".join(keep))
        return out_f, out_u

    # ==================== 详情 ====================

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        url = str(vid or "")
        if not url.startswith('http'):
            url = self.host + url
        try:
            res = requests.get(url, headers=self.header(), timeout=20)
        except Exception:
            return {"list": []}
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'html.parser')

        buckets = {}          # 播放源名 -> [(排序键, 条目名, 链接)]
        seen = set()
        # 锁定放链接的下载单元格(一个单元格通常是一个版本, 画质标签对整格通用)
        for td in soup.find_all('td', bgcolor="#ffffbb"):
            block = td.get_text(" ", strip=True)
            quality = self._quality_of(block)
            pwd_block = self._pwd_of(block)
            for a in td.find_all('a', href=True):
                href = str(a['href']).strip()
                if not href or href in seen:
                    continue
                seen.add(href)
                if href.startswith("magnet:"):
                    key, name, link = "磁力", (quality or "全集"), href
                else:
                    key = self._disk_of(href)
                    if not key:
                        continue
                    pwd = self._pwd_of(href) or pwd_block or self._pwd_of(a.get_text(" ", strip=True))
                    link = self._fix_url(href, pwd)
                    name = quality or "正片"
                buckets.setdefault(key, []).append((self.get_priority(name), name, link))

        _plog("BUCKETS", str({k: len(v) for k, v in buckets.items()}))
        from_list, url_list = [], []
        for key in self.DISK_ORDER:
            if key == "磁力":
                if not self.KEEP_MAGNET:
                    continue
            elif key not in self.KEEP:
                continue
            items = buckets.get(key) or []
            if not items:
                continue
            if key != "磁力" and self.CHECK:
                alive = [it for it in items if self._pan_ok(it[2]) is not False]
                if len(alive) != len(items):
                    _plog("CHECK", "%s dead=%d alive=%d" % (key, len(items) - len(alive), len(alive)))
                    print("电影港 剔除失效%s %d 条" % (key, len(items) - len(alive)))
                items = alive
            if not items:
                continue
            items.sort(key=lambda x: (x[0], x[1]))
            if self.EXPAND:
                nf, nu = self._expand_from(key, items)
                from_list.extend(nf)
                url_list.extend(nu)
            else:
                from_list.append(self._from_name(key))
                url_list.append("#".join("%s$%s" % (it[1], it[2]) for it in items))

        title = ""
        try:
            title = soup.title.text.split("_")[0].strip()
        except Exception:
            title = str(vid)
        _plog("DETAIL", "from=%s" % (" | ".join(from_list)[:300]))
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_play_from": "$$$".join(from_list),
            "vod_play_url": "$$$".join(url_list)
        }
        return {"list": [vod]}

    # ==================== 搜索 ====================

    def searchContent(self, key, quick, pg="1"):
        search_url = f"{self.host}/e/search/index.php"
        # 搜索关键词也必须用 GBK 编码提交
        data = {"tempid": "1", "tbname": "article", "keyboard": key.encode('gbk'),
                "show": "title,smalltext", "Submit": "搜索"}
        res = requests.post(search_url, data=data, headers=self.header(), timeout=20)
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'html.parser')
        vod_list = []
        for item in soup.select('table.border1'):
            a_tag = item.find('a')
            if a_tag:
                img = item.find('img')
                vod_list.append({
                    "vod_id": a_tag['href'],
                    "vod_name": img.get('alt', a_tag.text) if img else a_tag.text,
                    "vod_pic": img['src'] if img else ""
                })
        return {"list": vod_list}

    # ==================== 播放 ====================

    def playerContent(self, flag, id, vipFlags=None):
        u = str(id or "").strip()
        # 部分播放器会对 id 二次编码(&#37;26 %3A %2F), 不还原的话 _disk_of 认不出网盘域名,
        # 就不会包 push://, 壳子也就不会跳推送
        if "%" in u:
            try:
                _d = __import__("urllib.parse", fromlist=["unquote"]).unquote(u)
                if _d and ("://" in _d or "pan." in _d or "baidu.com" in _d):
                    u = _d
            except Exception:
                pass
        if "%" in u:
            try:
                _d = __import__("html").unescape(u)
                if _d and _d != u:
                    u = _d
            except Exception:
                pass
        _plog("PC-IN", "flag=%s id=%s" % (flag, u[:150]))
        if "$" in u:
            u = u.split("$")[-1].strip()
        u = self._fix_url(u, self._pwd_of(u))
        # 网盘/磁力: 交给 feimao jar 的 csp_Push; 磁力不能套 push://(会变成本地路径)
        if u.startswith("magnet:") or u.startswith("thunder:") or u.startswith("ed2k:"):
            return {"parse": 0, "url": u}
        _plog("PC-DISK", "%s | %s" % (self._disk_of(u), u[:120]))
        if self._disk_of(u):
            # parse=1: 告诉壳子"这不是直链, 交给解析模块", 解析模块见 push:// 直接走推送。
            # 原来给 0, 壳子把 push:// 当直链塞给播放器, 表现就是 0 KB/s 播不出来。
            return {"parse": 0, "url": "push://" + u}
        return {"parse": 0, "url": u}

    def isVideoFormat(self, url):
        try:
            return any(x in str(url or "") for x in (".m3u8", ".mp4", ".mkv", ".flv"))
        except Exception:
            return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def destroy(self):
        return None
