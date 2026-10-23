# coding=utf-8
# 觅盘 mipan.so - 纯搜索型网盘资源源(夸克 / 百度 / UC)
# 适配 蜂蜜影视(FongMi) + feimao jar 的 csp_Push 推送播放
#
# 站点特点: 只有一个聚合搜索接口, 没有"推荐/分类"可看
#   1) GET  /api/token        取防爬 token, 放进请求头 X-Mipan-Token
#   2) POST /api/search       {"kw":关键词} -> data.merged_by_type.{quark|baidu|uc}[]
#   3) POST /api/check/links  {"items":[{url,disk_type}]} -> results[].state
#      state: ok/valid/locked=有效   bad/invalid/dead=失效   uncertain=无法验证(百度)
#
# 说明: 首页不放任何推荐内容, 只显示一张"站点已加载, 请直接搜索"的提示卡,
#       搜索 -> 点影片 -> 详情页里按 夸克/百度/UC 分组的线路, 手动点哪条才推送哪条.

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

    # 只保留这三种网盘, 顺序即详情页里播放源的顺序
    KEEP = ("quark", "baidu", "xunlei")
    # 迅雷暂时不放: 分享都是多级文件夹, jar 不会递归进去, 播不了(迅雷接口要 captcha, py 侧也无法展开)
    DISK_NAME = {"quark": "夸克", "baidu": "百度", "xunlei": "迅雷", "uc": "UC"}

    # 链接有效性检测(用站点自己的检测接口, 比本地探测快且不受风控)
    CHECK = True
    CHECK_MAX = 12          # 每个影片最多检测多少条(每条都要过一遍, 别设太大)

    PER_DISK = 40           # 每个网盘最多保留多少条资源
    CHECK_N = 20            # 每次最多检测总条数(上限)
    CHECK_EACH = 24         # 每种网盘各检测前几条(原来 8, 条数一多后面的失效全留着)
    SKIP_TXT = True         # 跳过 .txt 结尾的资源(小说/剪辑文本, 不是影视)
    # 清洗后只剩这些词说明是频道广告/分类标签, 不是片名
    BLACK = {"年番", "国漫", "日漫", "美漫", "美剧", "韩剧", "日剧", "港剧", "台剧", "泰剧", "英剧",
             "国产剧", "欧美剧", "电影", "电视剧", "剧集", "动漫", "动画", "综艺", "纪录片", "短剧",
             "合集", "更新", "在线看", "补档", "资源"}

    # 明显的非影视资源关键词, 直接跳过
    SKIP_WORDS = ("有声小说", "有声书", "电子书", "网盘分享", "txt网盘", "mp3", "epub", ".pdf", "音乐专辑")

    # 标题里的噪声词: 分辨率/编码/语言/集数/体裁
    NOISE = (r"4K|8K|2160P?|1080P?|720P?|HDR|DV|DoLby|高码率|高帧率|高清|超清|蓝光|原盘|REMUX|"
             r"WEB-?DL|WEBRip|BluRay|HEVC|H264|H265|内嵌|内封|外挂|简中|繁中|中字|中英|双语|国语|粤语|"
             r"英语|多语|无删减|未删减|完整版|导演剪辑|更新至?\d+[集话期]|全\d+[集话期]|共\d+[集话期]|"
             r"完结|已完结|电影|电视剧|剧集|动漫|综艺|纪录片|短剧|超清版|收藏版|修复版|正式版|原声版|"
             r"画质增强版|真彩|多国字幕|字幕|全集|TC版?|HDTV|DVD|BD|全\d+集")

    PROBE = "zzqq腾讯无此资源xx"   # 探测 POST 用的假关键词(必须搜不到)

    # 首页提示卡的封面图(内嵌 PNG, 由 localProxy 输出, 不依赖任何外网图床)
    # 图片不显示就把 TIP_PIC 改成 "" 退回纯文字卡
    TIP_PIC = ""

    TIMEOUT = 15            # 单次请求超时(秒); 站点正常 8~10 秒, 别设太大否则蜂蜜等不到
    CHECK_TIMEOUT = 12      # 有效性检测单独超时(秒), 卡住就跳过检测
    SEARCH_TTL = 600        # 搜索结果缓存时间(秒), 详情页靠它免二次请求
    TOKEN_TTL = 7200        # token 缓存时间(秒)

    _STYLE_MAP = {}         # host -> POST 方式(类属性, 跨实例共享)
    _TOKEN_MAP = {}         # host -> (token, 过期时间)

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def getName(self):
        return "觅盘搜索[网盘]"

    def init(self, extend=""):
        self.host = "https://www.mipan.so"
        ext = (extend or "").strip()
        if ext.startswith("http"):
            self.host = ext.rstrip("/")
        self._token = ""
        self._token_exp = 0
        self._style = self._STYLE_MAP.get(self.host)
        self._style_done = self._style is not None
        self._search_cache = {}     # kw -> (时间, [分组])
        self._vid_cache = {}        # vod_id -> 分组
        self._last_kw = ""

    def getDependence(self):
        return []

    def header(self):
        return {
            "User-Agent": self.UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip",      # 关键: 响应几百 KB, 不压缩手机端会超时
            "Referer": self.host + "/",
            "Origin": self.host,
        }

    # ==================== 网络 ====================

    @staticmethod
    def _text(rsp):
        """把蜂蜜 fetch 的返回值统一成字符串"""
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

    # ==================== 网络 ====================
    # 蜂蜜的 fetch 各版本签名不同, 位置参数版/关键字参数版都可能, 传 body 很容易被吞掉。
    # 所以优先用 Python 自己的 urllib 直连; 只有 urllib 不可用时才退回 fetch。
    _NET_MAP = {}       # host -> "urllib" / "fetch"

    def _urllib_http(self, url, headers, body, timeout):
        import urllib.request
        import ssl
        data = body.encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=dict(headers),
                                     method=("POST" if data is not None else "GET"))
        ctx = ssl._create_unverified_context()
        rsp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
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

    # 蜂蜜 fetch 的 POST 调用方式, 挨个试
    POST_STYLES = ("params", "params2", "params3", "kwarg", "kwarg2", "kwarg3", "post1", "post2")

    def _send(self, style, url, headers, body, ms):
        if style == "params":
            return self.fetch(url, headers, "timeout#%d" % ms, "method#POST", "postType#json", "body#" + body)
        if style == "params2":
            return self.fetch(url, headers, "method#POST", "postType#json", "body#" + body)
        if style == "params3":
            return self.fetch(url, headers, "postType#json", "body#" + body)
        if style == "kwarg":
            return self.fetch(url, headers, timeout=ms, method="POST", postType="json", body=body)
        if style == "kwarg2":
            return self.fetch(url, headers=headers, method="POST", body=body)
        if style == "kwarg3":
            return self.fetch(url, headers=headers, postType="json", body=body)
        if style == "post1":
            return self.post(url, body, headers)
        if style == "post2":
            return self.post(url, {"body": body}, headers)
        raise ValueError(style)

    def _fetch_http(self, url, headers, body, ms):
        """退路: 用蜂蜜的 self.fetch 发, POST 方式靠探测"""
        if body is None:
            try:
                return self._text(self.fetch(url, headers, "timeout#%d" % ms))
            except TypeError:
                return self._text(self.fetch(url, headers=headers))
        style = self._style
        if style is None:
            style = self._detect_style()
        for st in ([style] if style else list(self.POST_STYLES)):
            if not st:
                continue
            try:
                txt = self._text(self._send(st, url, headers, body, ms))
            except Exception:
                continue
            if txt:
                if style or re.search(r'"total"\s*:\s*0\b', txt):
                    self._style = st
                    return txt
        return ""

    def _http(self, url, headers, body=None, timeout=None):
        """统一入口: 先 urllib, 不行退 fetch"""
        t = timeout or self.TIMEOUT
        mode = self._NET_MAP.get(self.host, "urllib")
        if mode == "urllib":
            try:
                txt = self._urllib_http(url, headers, body, t)
                self._NET_MAP[self.host] = "urllib"
                return txt
            except Exception as e:
                name = type(e).__name__
                if name in ("ImportError", "ModuleNotFoundError", "AttributeError", "NotImplementedError"):
                    self._NET_MAP[self.host] = "fetch"
                    print("觅盘: urllib 不可用(%s), 改用 fetch" % name)
                else:
                    print("觅盘: 请求失败 %s %s" % (name, url.split("/api/")[-1]))
                    return ""
        return self._fetch_http(url, headers, body, int(t * 1000))

    def _detect_style(self):
        """探测蜂蜜支持哪种 POST 写法: 搜一个不存在的词, 返回 total=0 才算请求体送达"""
        if self._style_done:
            return self._style
        self._style_done = True
        self._style = ""
        body = json.dumps({"kw": self.PROBE}, ensure_ascii=False)
        url = self.host + "/api/search"
        h = self.header()
        tok = self._get_token()
        if tok:
            h["X-Mipan-Token"] = tok
        ms = min(6000, int(self.TIMEOUT * 1000))
        for st in self.POST_STYLES:
            try:
                txt = self._text(self._send(st, url, h, body, ms))
            except Exception:
                continue
            if txt and re.search(r'"total"\s*:\s*0\b', txt):
                self._style = st
                self._STYLE_MAP[self.host] = st
                print("觅盘: POST 方式 = %s" % st)
                return st
        self._STYLE_MAP[self.host] = ""
        return ""

    def _get_token(self, force=False):
        now = time.time()
        if not force:
            cached = self._TOKEN_MAP.get(self.host)
            if cached and now < cached[1]:
                self._token = cached[0]
                return cached[0]
            if self._token and now < self._token_exp:
                return self._token
        txt = self._http(self.host + "/api/token", self.header(), timeout=min(10, self.TIMEOUT))
        try:
            j = json.loads(txt)
        except Exception:
            j = {}
        tok = (j.get("token") or "").strip()
        if tok:
            self._token = tok
            ttl = int(j.get("ttl") or 7200)
            self._token_exp = now + max(60, min(ttl, self.TOKEN_TTL) - 600)
            self._TOKEN_MAP[self.host] = (tok, self._token_exp)
        return self._token

    def _post(self, path, payload, timeout=None):
        """带 token 的 POST; 403 时刷新 token 重试一次"""
        body = json.dumps(payload, ensure_ascii=False)
        for attempt in (0, 1):
            h = self.header()
            tok = self._get_token(force=(attempt > 0))
            if tok:
                h["X-Mipan-Token"] = tok
            t = timeout or self.TIMEOUT
            if attempt > 0:
                t = max(6, t * 0.6)      # 重试不再给满额时间, 免得总耗时翻倍
            txt = self._http(self.host + path, h, body, timeout=t)
            if not txt:
                continue
            if attempt == 0 and ("403" in txt[:200] or "Forbidden" in txt[:200]):
                continue
            return txt
        return ""

    # ==================== 数据整理 ====================

    @classmethod
    def _short(cls, note):
        """逐条展示用的标题: 去 emoji/#标签/简介正文, 其余保留(集数画质这些是区分度)"""
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
    def _clean_name(cls, note):
        """把资源备注收拾成一个像片名的标题"""
        raw = (note or "").strip()
        if not raw:
            return ""
        s = re.sub(r"\.(?:txt|mp4|mkv|avi|rmvb|ts|iso|zip|rar|7z)\s*$", "", raw, flags=re.I)
        s = re.sub(r"^\s*(?:标题|片名|资源|名称)\s*[:：]\s*", "", s)
        s = re.sub(r"^\s*\d{1,3}\s*[.、)）]\s*", "", s)
        s = cls._strip_brackets(s)
        s = re.sub(r"\s+", " ", s).strip(" -_·|:：.,、/\\")
        # 截断到分隔符: 空格+年份 / 下划线 / 竖线 / 句点
        s = re.split(r"\s+(?:19|20)\d{2}\b|_|[|丨]|\.(?=\s|\d{4}|$)", s)[0]
        # 去掉尾部噪声词
        s = re.sub(r"[\s\-–—]*[\(（]?(?:%s)[\)）]?$" % cls.NOISE, "", s, flags=re.I)
        s = s.strip(" -_·|:：.,、/\\【】[]（）()")
        if len(s) < 2:
            # 回退: 取最长的一段连续文字
            parts = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9：:·]{2,}", re.sub(r"[（）()【】\[\]［］]", " ", raw))
            parts.sort(key=len, reverse=True)
            s = parts[0] if parts else raw[:20]
        return s[:30]

    @classmethod
    def _strip_brackets(cls, s):
        """反复剥离括号: 噪声括号整体删, 重复片名删, 其余保留内容只去括号"""
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
            # 括号里写的还是同一个片名 -> 删掉, 避免 "蜘蛛侠：崭新之日 蜘蛛侠崭新之日"
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

    def _search(self, kw):
        """返回逐条资源 [{'t','u','p','name','dt'}], 按网盘顺序 + 时间内新到旧"""
        kw = (kw or "").strip()
        if not kw:
            return []
        now = time.time()
        hit = self._search_cache.get(kw)
        if hit and now - hit[0] < self.SEARCH_TTL:
            return hit[1]

        txt = self._post("/api/search", {"kw": kw})
        try:
            data = (json.loads(txt).get("data") or {})
        except Exception:
            data = {}
        mbt = data.get("merged_by_type") or {}

        items = []
        for t in self.KEEP:
            for it in (mbt.get(t) or []):
                url = (it.get("url") or "").strip()
                if not url:
                    continue
                note = it.get("note") or ""
                if self.SKIP_TXT and re.search(r"\.txt\s*$", url + " " + note, re.I):
                    continue
                if any(w in note.lower() for w in self.SKIP_WORDS):
                    continue
                if self._clean_name(note) in self.BLACK:
                    continue
                name = self._short(note)
                if not name:
                    continue
                items.append({"t": t, "u": url, "p": (it.get("password") or "").strip(),
                              "name": name, "dt": it.get("datetime") or ""})
        out = []
        for t in self.KEEP:
            sub = [i for i in items if i["t"] == t]
            sub.sort(key=lambda x: x.get("dt") or "", reverse=True)
            out.extend(sub[:self.PER_DISK])

        if self.CHECK:
            out = self._check(out)
        self._search_cache[kw] = (now, out)
        return out

    # ==================== vod_id 编解码 ====================

    @staticmethod
    def _b64(s):
        return base64.b64encode(s.encode("utf-8")).decode("ascii").replace("+", "-").replace("/", "_").rstrip("=")

    @staticmethod
    def _unb64(s):
        s = (s or "").strip()
        s = s.replace("-", "+").replace("_", "/")
        s += "=" * (-len(s) % 4)
        try:
            return base64.b64decode(s).decode("utf-8", "ignore")
        except Exception:
            return ""

    def _encode_cat(self, kw, disk):
        obj = {"k": kw, "d": disk}
        return "mc_" + self._b64(json.dumps(obj, ensure_ascii=False))

    def _encode_vid(self, it):
        obj = {"t": it["t"], "u": it["u"], "p": it.get("p") or "", "n": it.get("name") or ""}
        vid = "mp_" + self._b64(json.dumps(obj, ensure_ascii=False))
        self._vid_cache[vid] = it
        return vid

    # ==================== 有效性检测 ====================

    _SID = re.compile(r"pan\.xunlei\.com/s/([0-9A-Za-z_-]+)|pan\.quark\.cn/s/([0-9A-Za-z]+)")

    @classmethod
    def _pkey(cls, u):
        """检测接口回来的 url 可能带尾随 '#' 或做过归一化, 统一用 share_id 比对"""
        m = cls._SID.search(str(u or ""))
        if m:
            return (m.group(1) or m.group(2) or "").strip()
        return str(u or "").strip().rstrip("#")

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

    def _check(self, items, strict=False):
        """用站点自带的检测接口剔除失效分享; strict=True 时失效就返回空(详情页用)"""
        if not self.CHECK or not items:
            return items
        # 按网盘各取前 N 条: 混合取前 N 条的话, 夸克条数一多就把迅雷全挤掉了(检测等于没做)
        sub = []
        for _t in ("quark", "uc", "xunlei"):
            sub += [i for i in items if i["t"] == _t][:self.CHECK_EACH]
        if not sub:
            return items
        payload = {"items": [{"url": i["u"], "disk_type": i["t"]} for i in sub]}
        state = {}
        try:
            txt = self._post("/api/check/links", payload, timeout=self.CHECK_TIMEOUT)
            for r in ((json.loads(txt) or {}).get("results") or []):
                key = self._pkey(r.get("normalized_url") or r.get("url") or "")
                if key:
                    state[key] = (r.get("state") or "").strip().lower()
        except Exception as e:
            print("觅盘: 检测失败 %s" % e)
            return items
        dead = ("bad", "invalid", "dead", "expired", "deleted", "not_found", "failed", "fail", "error", "missing")
        bad = set()
        for i in sub:
            if state.get(self._pkey(i["u"]), "") in dead:
                bad.add(i["u"])
        if not bad:
            return items
        kept = [i for i in items if i["u"] not in bad]
        print("觅盘: 剔除 %d 条失效" % len(bad))
        return kept if strict else (kept or items)

    @staticmethod
    def _with_pwd(url, pwd):
        if not pwd or "pwd=" in url:
            return url
        return url + ("&" if "?" in url else "?") + "pwd=" + pwd

    # ==================== 入口 ====================

    def homeContent(self, filter):
        tip = {
            "vod_id": "mp_tip",
            "vod_name": "搜片名",
            "vod_pic": "",
            "vod_remarks": "",
            "vod_content": "觅盘为纯搜索源。搜片名 -> 选网盘 -> 选具体资源 -> 推送播放。",
        }
        return {"class": [{"type_id": "tip", "type_name": "说明"}], "list": [tip]}

    def homeVideoContent(self):
        return {"list": self.homeContent(False)["list"]}

    def categoryContent(self, tid, pg, filter, extend):
        """点"夸克 (12个)"这种分类卡进来, 展开成该网盘下的资源列表"""
        tid = (tid or "").strip()
        if tid.startswith("mc_"):
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
                    print("觅盘 展开异常: %s" % e)
                    items = []
                out = [{"vod_id": self._encode_vid(it), "vod_name": it.get("name") or "",
                        "vod_pic": "", "vod_remarks": "", "vod_content": ""} for it in items]
                return {"list": out, "page": 1, "pagecount": 1, "limit": len(out), "total": len(out)}
        return {"list": [self.homeContent(False)["list"][0]], "page": 1, "pagecount": 1, "limit": 1, "total": 1}

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) and ids else str(ids)
        vid = (vid or "").strip()
        if not vid or vid == "mp_tip":
            return {"list": [self.homeContent(False)["list"][0]]}

        it = self._vid_cache.get(vid)
        if not it:
            try:
                obj = json.loads(self._unb64(vid[3:]))
            except Exception:
                obj = {}
            if obj.get("u"):
                it = {"t": obj.get("t") or self.KEEP[0], "u": obj["u"],
                      "p": obj.get("p") or "", "name": obj.get("n") or ""}
        if not it:
            return {"list": [{"vod_id": vid, "vod_name": "线路已过期，请重新搜索", "vod_pic": "",
                              "vod_remarks": "", "vod_content": "返回搜索结果重新点一次即可。"}]}

        disk = it["t"] if it["t"] in self.KEEP else self.KEEP[0]
        nm = self._from_name(self.DISK_NAME.get(disk, disk))
        url = self._with_pwd(it["u"], it.get("p"))
        # 详情页再检一次: 搜索阶段可能没轮到这条, 或者当时碰上风控抖动漏判了
        try:
            if self.CHECK and not self._check([{"t": disk, "u": url}], strict=True):
                return {"list": [{"vod_id": vid, "vod_name": it.get("name") or "",
                                  "vod_pic": "", "vod_remarks": "",
                                  "vod_content": "这条 %s 资源已失效，返回重新搜一条。" % nm,
                                  "vod_play_from": nm, "vod_play_url": "%s1$" % nm}]}
        except Exception:
            pass
        return {"list": [{
            "vod_id": vid,
            "vod_name": it.get("name") or "",
            "vod_pic": "",
            "vod_remarks": "",
            "vod_year": "", "vod_area": "", "vod_actor": "", "vod_director": "",
            "vod_content": "来源: 觅盘 · %s" % nm,
            "vod_play_from": nm,
            "vod_play_url": "%s1$push://%s" % (nm, url),
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
            print("觅盘 搜索异常: %s" % e)
            items = []
        if not items:
            tip = ("本机 POST 不支持，搜不了" if self._style == "" else "没搜到（或站点超时，再搜一次）")
            return {"list": [{"vod_id": "mp_tip", "vod_name": tip, "vod_pic": "",
                              "vod_remarks": "", "vod_content": "稍等几秒再搜一次通常就有了。"}],
                    "page": 1, "pagecount": 1, "limit": 1, "total": 1}

        vods = []
        for t in self.KEEP:
            sub = [i for i in items if i["t"] == t]
            if not sub:
                continue
            vods.append({
                "vod_id": self._encode_cat(kws, t),
                "vod_name": "%s (%d个)" % (self.DISK_NAME.get(t, t), len(sub)),
                "vod_pic": "",
                "vod_remarks": "",
                "vod_tag": "folder",
                "vod_content": "",
            })
        return {"list": vods, "page": 1, "pagecount": 1, "limit": len(vods), "total": len(vods)}

    def playerContent(self, flag, id, vipFlags=None):
        # 参数顺序是 (flag, id, vipFlags); 蜂蜜传进来的 id 就是 vod_play_url 里 $ 后面那部分
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
        print("觅盘 播放: %s -> %s" % (flag, url[:120]))
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
        # 首页提示卡封面图: 蜂蜜向 127.0.0.1:9978/proxy?do=py&type=tip 取图, 这里把内嵌 PNG 发回去
        try:
            q = ""
            if isinstance(param, dict):
                q = "&".join("%s=%s" % (k, v) for k, v in param.items())
            elif isinstance(param, str):
                q = param
            if "tip" in q and self.TIP_PIC:
                return {"code": 200, "content": base64.b64decode(self.TIP_PIC),
                        "headers": {"Content-Type": "image/png"}}
        except Exception as e:
            print("觅盘 localProxy: %s" % e)
        return None
