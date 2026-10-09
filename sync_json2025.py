import os
import re
import argparse

FILE1 = "2024.json"
LIVE_FILE = "li.m3u"
OK_DIR = "./ok"

# 从 live.m3u 第二行提取 UA：
UA_PATTERNS = [
    r'设置为\s*([^\s，,]+)',
    r'[Uu]ser-?[Aa]gent[:：]?\s*([^\s，,]+)',
    r'\bUA\b[:：]?\s*([^\s，,]+)',
]

jpg_OLD_PATH_PATTERN = r"\./ok/ok\d{4}\.jpg"
UA_VALUE_PATTERN = re.compile(r'("ua"\s*:\s*")([^"]*)(")')

def read_file_lines(path):
    if not os.path.exists(path):
        print(f"[WARN] 文件未找到: {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()

def write_file_lines(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

def extract_ua_from_line(line):
    if not line:
        return None
    for pat in UA_PATTERNS:
        m = re.search(pat, line)
        if m:
            return m.group(1).strip()
    return None

def replace_ua_value_in_line6_or_file(path, new_ua):
    lines = read_file_lines(path)
    if not lines:
        return False, None, None

    # ----- 尝试第6行 -----
    if len(lines) >= 6:
        line6 = lines[5]
        m6 = UA_VALUE_PATTERN.search(line6)
        if m6:
            old_val = m6.group(2)
            if old_val == new_ua:
                print(f"[INFO] UA 在 {path} 的第6行已一致，无需更新")
                return False, old_val, 'line6'
            new_line6 = UA_VALUE_PATTERN.sub(rf'\1{new_ua}\3', line6, count=1)
            lines[5] = new_line6
            write_file_lines(path, lines)
            print(f"[SYNC] 更新 UA（第6行）：{old_val} → {new_ua}")
            return True, old_val, 'line6'
        else:
            print(f"[INFO] 第6行未包含 UA 字段，开始扫描整文件")

    # ----- 扫描整文件 -----
    content = "".join(lines)
    m_any = UA_VALUE_PATTERN.search(content)
    if m_any:
        old_val = m_any.group(2)
        if old_val == new_ua:
            print(f"[INFO] UA 已一致，无需更新")
            return False, old_val, 'file'
        content_new = UA_VALUE_PATTERN.sub(rf'\1{new_ua}\3', content, count=1)
        write_file_lines(path, content_new.splitlines(keepends=True))
        print(f"[SYNC] 更新 UA（文件内首个）：{old_val} → {new_ua}")
        return True, old_val, 'file'

    print(f"[WARN] 未发现 UA 字段，跳过")
    return False, None, None

def update_jpg_path(json_file, latest_jpg_path):
    lines = read_file_lines(json_file)
    if not lines:
        return False

    content = "".join(lines)
    if re.search(jpg_OLD_PATH_PATTERN, content):
        content_new = re.sub(jpg_OLD_PATH_PATTERN, latest_jpg_path, content)
        if content_new != content:
            write_file_lines(json_file, content_new.splitlines(keepends=True))
            print(f"[SYNC] jpg 路径已更新 → {latest_jpg_path}")
            return True
        print("[INFO] jpg 路径已是最新")
        return False

    print("[INFO] 未匹配到旧 jpg 路径，跳过")
    return False

def main(update_ua=False, update_jpg=False):
    changed = False
    ua_changed = False
    jpg_changed = False

    # ----- UA 更新 -----
    if update_ua:
        live_lines = read_file_lines(LIVE_FILE)
        if len(live_lines) >= 2:
            ua = extract_ua_from_line(live_lines[1].strip())
            if ua:
                print(f"[INFO] 提取到 UA: {ua}")
                did, old, scope = replace_ua_value_in_line6_or_file(FILE1, ua)
                if did:
                    changed = True
                    ua_changed = True
            else:
                print("[WARN] 未在第二行找到 UA")
        else:
            print("[WARN] live.m3u 不足2行，跳过 UA 更新")

    # ----- jpg 更新 -----
    if update_jpg:
        jpg_files = []
        if os.path.isdir(OK_DIR):
            jpg_files = [f for f in os.listdir(OK_DIR) if re.match(r"ok(\d+)\.jpg", f)]

        if not jpg_files:
            print("[INFO] ok 目录未找到 jpg 文件，跳过 jpg 同步")
        else:
            # 按编号排序
            def extract_num(fname):
                m = re.search(r"ok(\d+)\.jpg", fname)
                return int(m.group(1)) if m else -1

            latest_jpg = sorted(jpg_files, key=extract_num)[-1]
            latest_jpg_full = os.path.join(OK_DIR, latest_jpg).replace("\\", "/")

            print(f"[INFO] 最新 jpg 文件：{latest_jpg_full}")

            if update_jpg_path(FILE1, latest_jpg_full):
                changed = True
                jpg_changed = True

    # ----- 总结 -----
    if changed:
        print(f"[SUMMARY] 更新完成：UA={ua_changed}, jpg={jpg_changed}")
    else:
        print("[SUMMARY] 无变化，无需提交")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync JSON files with UA or jpg updates")
    parser.add_argument('--update-ua', action='store_true', help='Update UA in JSON files')
    parser.add_argument('--update-jpg', action='store_true', help='Update jpg path in JSON files')
    args = parser.parse_args()
    main(update_ua=args.update_ua, update_jpg=args.update_jpg)
