# coding=utf-8
# 盘搜 PanSou(so.252035.xyz) - 纯搜索型网盘资源源
# 适配 蜂蜜影视(FongMi) + feimao jar 的 csp_Push 推送播放
#
# 一个站点同时出 夸克 / 百度, 但在**搜索结果**里就拆成两条:
#   水晶湖 · 夸克    (点进去只有夸克线路)
#   水晶湖 · 百度    (点进去只有百度线路)
# 这样详情页永远只有一个播放源, 不会被蜂蜜默认跳到另一个网盘。
#
# 接口: POST /api/search  {"kw":关键词,"res":"merge"}
#       -> data.merged_by_type.{quark|baidu}[{url,password,note,datetime,source,images}]

import sys
import json
import time
import base64
import re

try:
    from base.spider import Spider
except Exception:
    class Spider(object):
        def fetch(self, *a, **kw):
            return ""


class Spider(Spider):

    # ==================== 配置 ====================

    # 多个 PanSou 部署, 前一个不通/过载就自动换下一个(顺序即优先级, extend 可覆盖其中一个)
    HOSTS = ("https://so.252035.xyz", "https://sou.makifx.com", "https://pan.ailinux.de")
    _BEST_HOST = {"v": ""}      # 类级: 上次成功的 host, 下次优先用

    # 盘搜服务端时好时坏, 全挂了就用觅盘(同样支持夸克/百度)顶一下, 数据结构一致
    FALLBACK = True
    MIPAN = "https://www.mipan.so"

    # 只保留这两种网盘; 顺序即搜索结果里的展示顺序
    KEEP = ("quark", "baidu", "xunlei")
    # 迅雷暂时不放: 分享都是多级文件夹, jar 不会递归进去, 播不了(迅雷接口要 captcha, py 侧也无法展开)
    DISK_NAME = {"quark": "夸克", "baidu": "百度", "xunlei": "迅雷", "uc": "UC", "mobile": "移动"}

    PER_TYPE = 5            # 每个网盘最多取几条线路
    MAX_LINKS = 10          # 单个影片最多保留多少条线路
    SEARCH_MAX = 60         # 搜索列表最多显示多少条资源(每条=一条链接)

    SKIP_TXT = True         # 跳过 .txt 资源(小说/文本, 不是影视)
    SKIP_WORDS = ("有声小说", "有声书", "电子书", "网盘分享", "txt网盘", "mp3", "epub", ".pdf", "音乐专辑")

    # 清洗后如果只剩这些词, 说明原文是频道广告/分类标签, 不是片名
    BLACK = {"年番", "国漫", "日漫", "美漫", "美剧", "韩剧", "日剧", "港剧", "台剧", "泰剧", "英剧",
             "国产剧", "欧美剧", "电影", "电视剧", "剧集", "动漫", "动画", "综艺", "纪录片", "短剧",
             "合集", "更新", "在线看", "补档", "资源"}

    # 标题里的噪声词: 分辨率/编码/语言/集数/体裁
    NOISE = (r"4K|8K|2160P?|1080P?|720P?|HDR10?|DV|DoLby|杜比视界|高码率|高帧率|高清|超清|蓝光|原盘|REMUX|"
             r"WEB-?DL|WEBRip|BluRay|HEVC|H264|H265|内嵌|内封|外挂|简中|繁中|中字|中英|双语|国语|粤语|"
             r"英语|多语|无删减|未删减|完整版|导演剪辑|更新至?\d+[集话期]|全\d+[集话期]|共\d+[集话期]|"
             r"完结|已完结|电影|电视剧|剧集|动漫|动画|综艺|纪录片|短剧|超清版|收藏版|修复版|正式版|原声版|"
             r"国漫|日漫|美漫|国创|美剧|韩剧|日剧|港剧|台剧|泰剧|英剧|国产剧|欧美剧|年番|第\d+集|补档|"
             r"\d+\s*集全|全\s*\d+\s*集|第[一二三四五六七八九十\d]+[季部]|"
             r"画质增强版|真彩|多国字幕|字幕|全集|TC版?|HDTV|DVD|BD|DDP\d?\.?\d?|Atmos|PCOK")

    QUERY_TIMEOUT = 11      # 单次查询超时(秒); 实测主站正常响应要 6~7s, 原来给 4s 等于只有缓存命中才成功
    TOTAL_BUDGET = 20       # 一次搜索的总时间预算(秒), 留足重试轮次
    MAX_TRIES = 3           # 最多重试几轮(每轮: 换通道 + 换站点); 主站有 400/超时 抖动, 多给一轮
    CHECK_QUARK = True      # 检测夸克分享里到底有没有视频(空目录/音频的那种直接丢掉)
    CHECK_N = 60            # 每次搜索最多检测前多少条夸克(盘搜失效多, 检得少等于没检)
    CHECK_XUNLEI = True     # 迅雷也检(走觅盘的检测接口, 官方接口要 captcha)
    XL_CHECK_N = 10         # 迅雷每次最多检几条
    CHECK_WORKERS = 8       # 检测并发数
    CHECK_TIMEOUT = 6       # 单条检测超时(秒)
    CHECK_BUDGET = 20       # 检测总时间预算(秒)

    VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts",
                 ".rmvb", ".rm", ".webm", ".iso", ".mpg", ".mpeg", ".m4v")

    TIMEOUT = 15            # 单次请求超时(秒)
    SEARCH_TTL = 600        # 搜索结果缓存(秒), 详情页靠它免二次请求

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def getName(self):
        return "盘搜[网盘]"

    def init(self, extend=""):
        self.host = self.HOSTS[0]
        ext = (extend or "").strip()
        if ext.startswith("http"):
            self.host = ext.rstrip("/")
        self._search_cache = {}     # kw -> (时间, [分组])
        self._vid_cache = {}        # vod_id -> 单条资源
        self._q_cache = {}          # 夸克分享id -> 有效性

    def getDependence(self):
        return []

    def header(self, host=None):
        h = host or self.host
        return {
            "User-Agent": self.UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip",      # 关键: 响应几百 KB, 不压缩手机端会超时
            "Content-Type": "application/json",
            "Referer": h + "/",
            "Origin": h,
        }

    # ==================== 网络 ====================

    @staticmethod
    def _text(rsp):
        if rsp is None:
            return ""
        if isinstance(rsp, bytes):
            return rsp.decode("utf-8", "ignore")
        if isinstance(rsp, str):
            return rsp
        for attr in ("text", "content"):
            val = getattr(rsp, attr, None)
            if isinstance(val, bytes):
                return val.decode("utf-8", "ignore")
            if isinstance(val, str) and val:
                return val
        return ""

    def _urllib_http(self, url, headers, body, timeout):
        """优先用 Python 自带的 urllib 直连: 蜂蜜的 fetch 常常发不出 POST body"""
        import urllib.request
        import ssl
        data = body.encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=dict(headers),
                                     method=("POST" if data is not None else "GET"))
        rsp = urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context())
        try:
            raw = rsp.read()
            enc = (rsp.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                import gzip
                raw = gzip.decompress(raw)
        finally:
            try:
                rsp.close()
            except Exception:
                pass
        return raw.decode("utf-8", "ignore")

    POST_STYLES = ("params", "params2", "kwarg", "kwarg2")

    def _send(self, style, url, headers, body, ms):
        if style == "params":
            return self.fetch(url, headers, "timeout#%d" % ms, "method#POST", "postType#json", "body#" + body)
        if style == "params2":
            return self.fetch(url, headers, "method#POST", "postType#json", "body#" + body)
        if style == "kwarg":
            return self.fetch(url, headers, timeout=ms, method="POST", postType="json", body=body)
        if style == "kwarg2":
            return self.fetch(url, headers=headers, method="POST", body=body)
        raise ValueError(style)

    def _hosts(self):
        hosts = []
        for h in (self.host,) + tuple(self.HOSTS):
            h = (h or "").rstrip("/")
            if h and h not in hosts:
                hosts.append(h)
        best = self._BEST_HOST.get("v") or ""
        if best in hosts:
            hosts.remove(best)
            hosts.insert(0, best)
        return hosts

    def _http(self, url, body=None, timeout=None, host=None):
        t = timeout or self.TIMEOUT
        h = self.header(host)
        try:
            return self._urllib_http(url, h, body, t)
        except Exception as e:
            name = type(e).__name__
            if name not in ("ImportError", "ModuleNotFoundError", "AttributeError", "NotImplementedError"):
                print("盘搜: urllib 请求失败 %s" % name)
                return ""
        # urllib 不可用 -> 退到蜂蜜 fetch, 挨个试 POST 写法
        ms = int(t * 1000)
        for st in self.POST_STYLES:
            try:
                txt = self._text(self._send(st, url, h, body or "{}", ms))
            except Exception:
                continue
            if txt:
                return txt
        return ""

    # ==================== 数据整理 ====================

    @classmethod
    def _clean_name(cls, note):
        raw = (note or "").strip()
        if not raw:
            return ""
        s = raw
        # 介绍/正文一律砍掉
        s = re.split(r"[📜📝📖🔗📥⬇️]", s)[0]
        # 去掉开头连续的 emoji / 图标 / #标签(可能好几个)
        for _ in range(6):
            s2 = re.sub(r"^[\s\-]+", "", s)
            s2 = re.sub(r"^#\S+\s*", "", s2)          # 先吃掉 #标签
            s2 = re.sub(r"^[\s\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\-]+", "", s2)  # 再去 emoji
            if s2 == s:
                break
            s = s2
        # 美剧「xxx」/ 电影《xxx》 这类: 取书名号里的内容
        m = re.match(r"^\s*(?:美剧|韩剧|日剧|国剧|国产剧|欧美剧|港剧|台剧|电影|动漫|动画|综艺|纪录片|短剧)"
                     r"\s*[「『\"《]([^」』\"》]{2,40})[」』\"》]", s)
        if m:
            s = m.group(1)
        # 《xxx》 开头
        m = re.match(r"^\s*《([^》]{2,40})》", s)
        if m:
            s = m.group(1)
        s = re.sub(r"\.(?:txt|mp4|mkv|avi|rmvb|ts|iso|zip|rar|7z)\s*$", "", s, flags=re.I)
        s = re.sub(r"^\s*(?:标题|片名|剧名|资源标题|资源名称|资源|名称)\s*[:：]\s*", "", s)
        s = re.sub(r"^\s*\d{1,3}\s*[.、)）]\s*", "", s)
        # 片名一般在最前面: 只要不是以括号开头, 就截断到第一个括号
        # (括号里基本都是年份/集数/国家/演员/类型这些元数据)
        if not re.match(r"^\s*[（(【\[［「『《]", s):
            m = re.search(r"[（(【\[［「『《]", s)
            if m and m.start() >= 2:
                s = s[:m.start()]
        s = cls._strip_brackets(s)
        for _ in range(3):
            s2 = re.sub(r"^[\s\-]+", "", s)
            s2 = re.sub(r"^#\S+\s*", "", s2)
            s2 = re.sub(r"^(?:标题|片名|剧名|资源标题|资源名称|资源|名称)\s*[:：]\s*", "", s2)
            s2 = re.sub(r"^[\s\U0001F000-\U0001FAFF\u2600-\u27BF\-]+", "", s2)
            if s2 == s:
                break
            s = s2
        s = re.sub(r"\s+", " ", s).strip(" -_·|:：.,、/\\")
        # 遇到第一个噪声词(4K/1080P/8集全/内封.../第X季)就截断
        m = re.search(r"\s*(?:%s)" % cls.NOISE, s, re.I)
        if m and m.start() >= 2:
            s = s[:m.start()]
        s = s.strip(" -_·|:：.,、/\\")
        # 尾部英文名去掉(水晶湖 Crystal Lake -> 水晶湖), 中文后面的英文不是片名主体
        s = re.sub(r"\s+[A-Za-z][A-Za-z0-9 '&:.\-]{2,}$", "", s).strip()
        # 尾部类型串 恐怖/惊悚
        s = re.sub(r"\s*[\u4e00-\u9fa5]{1,4}(?:/[\u4e00-\u9fa5]{1,4})+\s*$", "", s).strip()
        s = s.strip(" -_·|:：.,、/\\【】[]（）()〖〗〘〙")
        if s in cls.BLACK or (s.split(" ")[0] in cls.BLACK and len(s) > 8):
            return ""
        if len(s) <= 14 and re.match(r"^(?:星期[一二三四五六日天]|\d{4}\s*年\s*\d{1,2}\s*月|\d{1,2}\s*月\s*\d{1,2}\s*日)", s):
            return ""      # 只剩日期/星期, 这是 TG 频道消息的时间戳, 不是片名
        if len(s) < 2:
            parts = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9：:·]{2,}", re.sub(r"[（）()【】\[\]［］]", " ", raw))
            parts.sort(key=len, reverse=True)
            s = parts[0] if parts else raw[:20]
        return s[:30]

    @classmethod
    def _short(cls, note):
        """逐条展示用的标题: 去掉 emoji/#标签/简介正文, 其余保留(集数、画质这些是区分度)"""
        s = (note or "").strip()
        s = re.split(r"[📜📝📖🔗📥⬇️]", s)[0]
        for _ in range(6):
            s2 = re.sub(r"^[\s\-]+", "", s)
            s2 = re.sub(r"^#\S+\s*", "", s2)
            s2 = re.sub(r"^[\s\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\-]+", "", s2)
            if s2 == s:
                break
            s = s2
        s = re.sub(r"\s+", " ", s).strip(" -_·|:：.,、/\\")
        s = re.sub(r"\.(?:txt|mp4|mkv|avi|rmvb|ts)\s*$", "", s, flags=re.I)
        if len(s) > 26:
            s = s[:26]
        return s or cls._clean_name(note)

    @classmethod
    def _strip_brackets(cls, s):
        noise_re = re.compile(
            r"^(?:%s|(?:19|20)\d{2}|第[一二三四五六七八九十\d]+[季部]|[\d\.]+\s*[GMTK]B?)$" % cls.NOISE, re.I)

        def _br(m):
            inner = m.group(1).strip()
            if not inner:
                return " "
            if noise_re.match(inner):
                return " "
            core = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", inner)
            prefix = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", m.string[:m.start()])
            if core and prefix and (core in prefix or (len(core) >= 2 and core[:2] in prefix)):
                return " "
            return " " + inner + " "

        for _ in range(6):
            new = re.sub(r"[（(【\[［]([^（）()【】\[\]［］]{0,60})[）)】\]］]", _br, s)
            if new == s:
                break
            s = new
        return s

    @staticmethod
    def _plain(name):
        return re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", (name or "").lower())

    def _merge_prefix(self, groups):
        groups = sorted(groups, key=lambda g: len(g["title"]))
        kept = []
        for g in groups:
            pk = self._plain(g["title"])
            merged = False
            for k in kept:
                kk = self._plain(k["title"])
                if len(kk) >= 5 and len(pk) > len(kk) and pk.startswith(kk):
                    k["items"].extend(g["items"])
                    merged = True
                    break
            if not merged:
                kept.append(g)
        for k in kept:
            k["items"] = self._pick(k["items"])
        return [k for k in kept if k["items"]]

    def _pick(self, items):
        out = []
        for t in self.KEEP:
            sub = [i for i in items if i["t"] == t]
            sub.sort(key=lambda x: x.get("dt") or "", reverse=True)
            out.extend(sub[:self.PER_TYPE])
        seen, uniq = set(), []
        for i in out:
            if i["u"] in seen:
                continue
            seen.add(i["u"])
            uniq.append(i)
        return uniq[:self.MAX_LINKS]

# jar 的 csp_Push 按线路名里的模式关键字选解析路径(默认配置: quarkHD=夸克无限,
    # ucHD=UC无限, baiduHD=百度原画|百度无限, aliHD=阿里原画); 名字对不上会先失败再回退,
    # 表现就是"播放失败再跳转推送"。播放源名统一映射成 jar 认识的规范名。
    # 线路名必须用 jar 的档位名(quarkHD=夸克无限, baiduHD=百度原画|百度无限, ucHD=UC无限, aliHD=阿里原画),
    # 名字对不上 Push.playerContent 走不到解析分支, 表现为"10几K后归零"
    FROM_NAME = {"夸克": "夸克无限", "百度": "百度无限", "UC": "UC无限",
                 "迅雷": "迅雷", "移动": "移动智能", "阿里": "阿里原画"}

    @classmethod
    def _from_name(cls, k):
        return cls.FROM_NAME.get(k, k)

    def _cnt(self, d):
        m = (d or {}).get("merged_by_type") or {}
        return sum(len(m.get(k) or []) for k in self.KEEP)

    def _query_all(self, kw):
        """盘搜(tg / all 双通道, 带站点重试) 与 觅盘兜底 同时发, 谁先给出有效结果用谁"""
        def query(host, src, tmo):
            body = json.dumps({"kw": kw, "res": "merge", "src": src}, ensure_ascii=False)
            txt = self._http(host.rstrip("/") + "/api/search", body, timeout=tmo, host=host.rstrip("/"))
            try:
                return (json.loads(txt).get("data") or {})
            except Exception:
                return {}

        def once(tmo, host):
            best = {}
            try:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                ex = ThreadPoolExecutor(max_workers=2)
                futs = [ex.submit(query, host, "tg", tmo), ex.submit(query, host, "all", tmo)]
                try:
                    for f in as_completed(futs, timeout=tmo + 2):
                        try:
                            d = f.result()
                        except Exception:
                            continue
                        if self._cnt(d) > self._cnt(best):
                            best = d
                        if self._cnt(best) >= 5:
                            break
                except Exception:
                    pass
                finally:
                    try:
                        ex.shutdown(wait=False)
                    except Exception:
                        pass
            except Exception:
                best = query(host, "tg", tmo) or query(host, "all", tmo)
            return best

        def pansou():
            deadline = time.time() + self.TOTAL_BUDGET
            best = {}
            for _ in range(self.MAX_TRIES):
                for host in self._hosts()[:1]:
                    left = deadline - time.time()
                    if left < 2.5:
                        break
                    d = once(min(self.QUERY_TIMEOUT, left), host)
                    if self._cnt(d) > self._cnt(best):
                        best = d
                        self._BEST_HOST["v"] = host
                    if self._cnt(best) > 0:
                        break
                if self._cnt(best) > 0 or time.time() >= deadline:
                    break
                time.sleep(0.4)
            return best

        data = {}
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            ex = ThreadPoolExecutor(max_workers=2)
            futs = [ex.submit(pansou)]
            if self.FALLBACK:
                futs.append(ex.submit(self._mipan_search, kw))
            try:
                for f in as_completed(futs, timeout=self.TOTAL_BUDGET + 5):
                    try:
                        d = f.result()
                    except Exception:
                        d = {}
                    if self._cnt(d) > self._cnt(data):
                        data = d
                    if self._cnt(data) > 0:
                        break
            finally:
                ex.shutdown(wait=False)
        except Exception:
            data = pansou() or {}
            if self._cnt(data) == 0 and self.FALLBACK:
                data = self._mipan_search(kw) or data
        return data

    def _mipan_search(self, kw):
        """兜底: 觅盘 /api/token + /api/search, 返回和盘搜一样的 {merged_by_type:{...}}"""
        import urllib.request
        import urllib.error
        import ssl
        import gzip

        def call(url, body=None, hd=None, tmo=4):
            h = {"User-Agent": self.UA, "Accept-Encoding": "gzip"}
            if hd:
                h.update(hd)
            if body is not None:
                h["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=body, headers=h,
                                         method=("POST" if body is not None else "GET"))
            r = urllib.request.urlopen(req, timeout=tmo, context=ssl._create_unverified_context())
            raw = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8", "ignore"))

        try:
            tok = (call(self.MIPAN + "/api/token").get("token") or "").strip()
            if not tok:
                return {}
            d = call(self.MIPAN + "/api/search",
                     json.dumps({"kw": kw}, ensure_ascii=False).encode("utf-8"),
                     {"X-Mipan-Token": tok})
        except Exception as e:
            print("盘搜兜底(觅盘)失败: %s" % type(e).__name__)
            return {}
        data = (d.get("data") or {}) if isinstance(d, dict) else {}
        print("盘搜兜底(觅盘): %s" % kw)
        return {"merged_by_type": data.get("merged_by_type") or {}}

    def _search(self, kw):
        """返回逐条资源 [{'t','u','p','name','dt'}], 按 网盘顺序 + 时间新到旧"""
        kw = (kw or "").strip()
        if not kw:
            return []
        now = time.time()
        hit = self._search_cache.get(kw)
        if hit and now - hit[0] < self.SEARCH_TTL:
            return hit[1]

        data = self._query_all(kw)
        mbt = data.get("merged_by_type") or {}

        out = []
        for t in self.KEEP:
            for it in (mbt.get(t) or []):
                url = (it.get("url") or "").strip()
                if not url:
                    continue
                note = it.get("note") or ""
                if self.SKIP_TXT and re.search(r"\.txt\s*$", url + " " + note, re.I):
                    continue
                low = note.lower()
                if any(w in low for w in self.SKIP_WORDS):
                    continue
                name = self._short(note)
                if not name:
                    continue
                if self._clean_name(note) in self.BLACK:
                    continue
                out.append({"t": t, "u": url, "p": (it.get("password") or "").strip(),
                            "name": name, "dt": it.get("datetime") or ""})
        # 同一网盘内按时间从新到旧
        out.sort(key=lambda x: (self.KEEP.index(x["t"]), -1 * 0, 0))
        res = []
        for t in self.KEEP:
            sub = [i for i in out if i["t"] == t]
            sub.sort(key=lambda x: x.get("dt") or "", reverse=True)
            res.extend(sub)
        if self.CHECK_QUARK:
            keep = self._check_quarks(res)
            if keep:
                res2 = [i for i in res if i["t"] != "quark" or i["u"] in keep]
                if res2:
                    res = res2
        if self.CHECK_XUNLEI:
            bad = self._check_xunlei([i for i in res if i["t"] == "xunlei"])
            if bad:
                res2 = [i for i in res if i["u"] not in bad]
                print("盘搜: 剔除失效迅雷 %d 条" % len(bad))
                if res2:
                    res = res2
        self._search_cache[kw] = (now, res)
        return res

    # ==================== 夸克有效性检测 ====================

    def _q_json(self, url, payload=None, timeout=None):
        import urllib.request
        import ssl
        import gzip
        h = {"User-Agent": self.UA, "Referer": "https://pan.quark.cn/",
             "Content-Type": "application/json", "Accept-Encoding": "gzip"}
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=h, method=("POST" if data else "GET"))
        r = urllib.request.urlopen(req, timeout=timeout or self.CHECK_TIMEOUT,
                                   context=ssl._create_unverified_context())
        raw = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8", "ignore"))

    def _quark_stoken(self, fid):
        """'' = 分享已失效; None = 网络异常"""
        api = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc&uc_param_str="
        try:
            d = self._q_json(api, {"pwd_id": fid, "passcode": ""})
        except Exception as e:
            # 404/410 就是分享不存在, 当成失效; 其它(超时/5xx)算查不出来
            code = getattr(e, "code", None)
            if code in (400, 404, 410, 403):
                try:
                    body = json.loads(e.read().decode("utf-8", "ignore"))
                    if body.get("code") == 0:
                        return (body.get("data") or {}).get("stoken") or ""
                except Exception:
                    pass
                return ""
            return None
        if d.get("code") != 0:
            return ""
        return (d.get("data") or {}).get("stoken") or ""

    def _quark_has_video(self, fid, stoken, max_depth=3, max_items=50):
        import urllib.parse
        api = ("https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail?pr=ucpro&fr=pc&uc_param_str="
               "&pwd_id=%s&stoken=%s&pdir_fid=%s&force=0&_page=1&_size=100"
               "&_fetch_banner=0&_fetch_share=0&_fetch_total=0&_sort=file_type:asc,updated_at:desc")
        queue = [("0", 0)]
        seen = 0
        while queue and seen < max_items:
            dir_fid, depth = queue.pop(0)
            try:
                d = self._q_json(api % (fid, urllib.parse.quote(stoken), dir_fid))
            except Exception:
                continue
            for it in ((d.get("data") or {}).get("list") or []):
                seen += 1
                nm = (it.get("file_name") or "").lower()
                cat = (it.get("obj_category") or "").lower()
                if it.get("file_type") == 1:
                    if cat == "video" or nm.endswith(self.VIDEO_EXT):
                        return True
                elif it.get("file_type") == 0 and depth < max_depth and it.get("fid"):
                    queue.append((it.get("fid"), depth + 1))
        return False

    def _quark_ok(self, url):
        """True=里面有视频 / False=失效或空目录 / None=查不出来"""
        m = re.search(r"pan\.quark\.cn/s/([0-9A-Za-z]+)", url or "")
        if not m:
            return None
        fid = m.group(1)
        hit = self._q_cache.get(fid, "?")
        if hit != "?":
            return hit
        st = self._quark_stoken(fid)
        if st is None:
            res = None
        elif st == "":
            res = False
        else:
            try:
                res = self._quark_has_video(fid, st)
            except Exception:
                res = None
        self._q_cache[fid] = res
        return res

    _SID = re.compile(r"pan\.xunlei\.com/s/([0-9A-Za-z_-]+)")

    @classmethod
    def _pkey(cls, u):
        m = cls._SID.search(str(u or ""))
        if m:
            return m.group(1).strip()
        return str(u or "").strip().rstrip("#")

    def _check_xunlei(self, items):
        """迅雷分享有效性: 官方接口要 captcha_token, 借觅盘的检测接口
        返回"失效"的 url 集合; 查不出来的一律不剔除"""
        import urllib.request
        import ssl
        import gzip

        urls = [i["u"] for i in (items or [])][:self.XL_CHECK_N]
        if not urls:
            return set()

        def call(url, body=None, hd=None, tmo=8):
            h = {"User-Agent": self.UA, "Accept-Encoding": "gzip"}
            if hd:
                h.update(hd)
            if body is not None:
                h["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=body, headers=h,
                                         method=("POST" if body is not None else "GET"))
            r = urllib.request.urlopen(req, timeout=tmo, context=ssl._create_unverified_context())
            raw = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8", "ignore"))

        try:
            tok = getattr(self, "_mp_tok", "") or ""
            if not tok:
                tok = (call("https://www.mipan.so/api/token").get("token") or "").strip()
                self._mp_tok = tok
            if not tok:
                return set()
            d = call("https://www.mipan.so/api/check/links",
                     json.dumps({"items": [{"url": u, "disk_type": "xunlei"} for u in urls]},
                                ensure_ascii=False).encode("utf-8"),
                     {"X-Mipan-Token": tok})
        except Exception as e:
            print("盘搜: 迅雷检测失败 %s" % type(e).__name__)
            return set()
        bad = set()
        for r in (d.get("results") or []):
            if (r.get("state") or "").lower() == "bad":
                key = self._pkey(r.get("normalized_url") or r.get("url") or "")
                if key:
                    bad.add(key)
        # 用 share_id 比对(接口回来的 url 可能带尾随 '#' 或被归一化)
        return set(u for u in urls if self._pkey(u) in bad)

    def _check_quarks(self, items):
        """并发检测前 CHECK_N 条夸克, 返回可以保留的 url 集合(查不出来的保留)"""
        quarks = [i for i in items if i["t"] == "quark"][:self.CHECK_N]
        if not quarks:
            return set()
        self._valid = {}
        budget = time.time() + self.CHECK_BUDGET

        def work(it):
            if time.time() > budget:
                return
            try:
                self._valid[it["u"]] = self._quark_ok(it["u"])
            except Exception:
                self._valid[it["u"]] = None

        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.CHECK_WORKERS) as pool:
                list(pool.map(work, quarks))
        except Exception:
            for it in quarks:
                work(it)
        keep = set()
        for it in quarks:
            ok = self._valid.get(it["u"], None)   # 没排上/超时的当 None, 保留
            if ok is not False:
                keep.add(it["u"])
        dead = len(quarks) - len(keep)
        if dead > 0:
            print("盘搜: 剔除失效夸克 %d 条 / 检测 %d 条" % (dead, len(quarks)))
        return keep

    # ==================== vod_id ====================

    @staticmethod
    def _b64(s):
        return base64.b64encode(s.encode("utf-8")).decode("ascii").replace("+", "-").replace("/", "_").rstrip("=")

    @staticmethod
    def _unb64(s):
        s = (s or "").strip().replace("-", "+").replace("_", "/")
        s += "=" * (-len(s) % 4)
        try:
            return base64.b64decode(s).decode("utf-8", "ignore")
        except Exception:
            return ""

    def _encode_cat(self, kw, disk):
        obj = {"k": kw, "d": disk}
        return "pc_" + self._b64(json.dumps(obj, ensure_ascii=False))

    def _encode_vid(self, it):
        obj = {"t": it["t"], "u": it["u"], "p": it.get("p") or "", "n": it.get("name") or ""}
        vid = "ps_" + self._b64(json.dumps(obj, ensure_ascii=False))
        self._vid_cache[vid] = it
        return vid

    # ==================== 入口 ====================

    @staticmethod
    def _with_pwd(url, pwd):
        if not pwd or "pwd=" in url:
            return url
        return url + ("&" if "?" in url else "?") + "pwd=" + pwd

    def homeContent(self, filter):
        tip = {
            "vod_id": "ps_tip",
            "vod_name": "搜片名",
            "vod_pic": "",
            "vod_remarks": "",
            "vod_content": "盘搜为纯搜索源。同一个片子会在结果里出现两条: 夸克 / 百度, 点哪条就只推那条。",
        }
        return {"class": [{"type_id": "tip", "type_name": "说明"}], "list": [tip]}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        """点"夸克 (7个)"这种分类卡进来, 这里把它展开成资源列表"""
        tid = (tid or "").strip()
        if tid.startswith("pc_"):
            try:
                obj = json.loads(self._unb64(tid[3:]))
            except Exception:
                obj = {}
            kw = obj.get("k") or ""
            disk = obj.get("d") or ""
            if kw and disk in self.KEEP:
                try:
                    items = [i for i in self._search(kw) if i["t"] == disk]
                except Exception as e:
                    print("盘搜 展开异常: %s" % e)
                    items = []
                out = []
                for it in items:
                    out.append({
                        "vod_id": self._encode_vid(it),
                        "vod_name": it.get("name") or "",
                        "vod_pic": "",
                        "vod_remarks": "",
                        "vod_content": "",
                    })
                return {"list": out, "page": 1, "pagecount": 1, "limit": len(out), "total": len(out)}
        return {"list": [self.homeContent(False)["list"][0]], "page": 1, "pagecount": 1, "limit": 1, "total": 1}

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) and ids else str(ids)
        vid = (vid or "").strip()
        if not vid or vid == "ps_tip":
            return {"list": [self.homeContent(False)["list"][0]]}

        try:
            obj = json.loads(self._unb64(vid[3:] if vid[:3] in ("ps_", "pc_") else vid))
        except Exception:
            obj = {}

        # 分类卡: 列出该网盘下的全部资源, 每条一个"集数"
        if vid.startswith("pc_") or ("k" in obj and "d" in obj and "u" not in obj):
            kw = obj.get("k") or ""
            disk = obj.get("d") or ""
            if disk not in self.KEEP:
                return {"list": [{"vod_id": vid, "vod_name": "线路已过期，请重新搜索",
                                  "vod_pic": "", "vod_remarks": "", "vod_content": "返回搜索结果重新点一次。"}]}
            sub = [i for i in self._search(kw) if i["t"] == disk]
            if not sub:
                return {"list": [{"vod_id": vid, "vod_name": "%s %s" % (kw, self.DISK_NAME[disk]),
                                  "vod_pic": "", "vod_remarks": "",
                                  "vod_content": "这个网盘下暂时没有可用资源，换个网盘或再搜一次。"}]}
            lines = []
            for n, it in enumerate(sub, 1):
                title = (it.get("name") or "").strip()[:20]
                lines.append("%d.%s$push://%s" % (n, title, self._with_pwd(it["u"], it.get("p"))))
            return {"list": [{
                "vod_id": vid,
                "vod_name": "%s %s" % (kw, self.DISK_NAME[disk]),
                "vod_pic": "",
                "vod_remarks": "",
                "vod_year": "", "vod_area": "", "vod_actor": "", "vod_director": "",
                "vod_content": "共 %d 条 %s 资源，点哪条推哪条" % (len(sub), self.DISK_NAME[disk]),
                "vod_play_from": self._from_name(self.DISK_NAME[disk]),
                "vod_play_url": "#".join(lines),
            }]}

        # 兼容: 单条资源的 vod_id
        it = self._vid_cache.get(vid)
        if not it and obj.get("u"):
            it = {"t": obj.get("t") or self.KEEP[0], "u": obj["u"], "p": obj.get("p") or "", "name": obj.get("n") or ""}
        if not it:
            return {"list": [{"vod_id": vid, "vod_name": "线路已过期，请重新搜索", "vod_pic": "",
                              "vod_remarks": "", "vod_content": "返回搜索结果重新点一次即可。"}]}
        disk = it["t"] if it["t"] in self.KEEP else self.KEEP[0]
        nm = self._from_name(self.DISK_NAME[disk])
        return {"list": [{
            "vod_id": vid, "vod_name": it.get("name") or "", "vod_pic": "", "vod_remarks": "",
            "vod_year": "", "vod_area": "", "vod_actor": "", "vod_director": "",
            "vod_content": "来源: 盘搜 · %s" % nm,
            "vod_play_from": nm,
            "vod_play_url": "%s1$push://%s" % (nm, self._with_pwd(it["u"], it.get("p"))),
        }]}

    def searchContent(self, key, quick, pg=1):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg=1):
        try:
            p = int(pg)
        except Exception:
            p = 1
        kws = (key or "").strip()
        if p > 1:
            return {"list": [], "page": p, "pagecount": 1, "limit": 0, "total": 0}
        try:
            items = self._search(kws)
        except Exception as e:
            print("盘搜 搜索异常: %s" % e)
            items = []
        if not items:
            return {"list": [{
                "vod_id": "ps_tip", "vod_name": "没搜到（或站点超时，再搜一次）", "vod_pic": "",
                "vod_remarks": "", "vod_content": "稍等几秒再搜一次通常就有了。",
            }], "page": 1, "pagecount": 1, "limit": 1, "total": 1}

        # 按网盘分类, 一个网盘一张卡, 点进去才是该网盘下的具体资源
        vods = []
        for t in self.KEEP:
            sub = [i for i in items if i["t"] == t]
            if not sub:
                continue
            vods.append({
                "vod_id": self._encode_cat(kws, t),
                "vod_name": "%s (%d个)" % (self.DISK_NAME[t], len(sub)),
                "vod_pic": "",
                "vod_remarks": "",
                "vod_tag": "folder",      # 点进去是列表页, 不是播放页
                "vod_content": "",
            })
        return {"list": vods, "page": 1, "pagecount": 1, "limit": len(vods), "total": len(vods)}

    def playerContent(self, flag, id, vipFlags=None):
        url = (id or "").strip()
        # 壳子偶尔把 id 二次编码(%2F/%3A), 不还原会导致链接失效
        if "%" in url:
            try:
                _d = __import__("urllib.parse", fromlist=["unquote"]).unquote(url)
                if _d and ("://" in _d):
                    url = _d
            except Exception:
                pass
        if not url:
            return {"parse": 0, "url": ""}
        if not url.startswith("push://"):
            url = "push://" + url
        print("盘搜 播放: %s -> %s" % (flag, url[:120]))
        if str(url or "").startswith("push://"):
            # parse=0 + push://: 壳子见到前缀直接转 push_agent(种子站写法), 不先当直链播一次
            return {"parse": 0, "url": url}
        return {"parse": 0, "url": url}

    def isVideoFormat(self, url):
        u = (url or "").lower()
        return any(e in u for e in (".m3u8", ".mp4", ".flv", ".mkv", ".avi"))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None
