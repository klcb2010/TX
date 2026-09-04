/**
 * 自动生成的百度 OCR 鉴权中间件
 * 由 GitHub Actions 自动编译，请勿手动修改
 */
(function(global) {
    'use strict';

    // 解密函数，防止明文 Key 被机器人爬虫直接扫描
    function _d(str) {
        if (typeof atob === 'function') {
            return atob(str);
        }
        // 兼容 Node.js / Python execjs 运行环境
        return Buffer.from(str, 'base64').toString('utf-8');
    }

    // Actions 编译时会自动将密文注入到这里
    const _ak = "__API_KEY_PLACEHOLDER__";
    const _sk = "__SECRET_KEY_PLACEHOLDER__";

    const config = {
        getApiKey: () => _d(_ak),
        getSecretKey: () => _d(_sk)
    };

    // 暴露给外部调用的核心方法（Python 或 油猴脚本直接调用这个方法获取请求体数据）
    global.getBaiduAuthParam = function() {
        const apiKey = config.getApiKey();
        const secretKey = config.getSecretKey();
        
        return 'grant_type=client_credentials' +
               '&client_id=' + encodeURIComponent(apiKey) +
               '&client_secret=' + encodeURIComponent(secretKey);
    };

    console.log("👉 [OCR Service] 百度鉴权模块加载成功。");

})(typeof window !== 'undefined' ? window : global);
