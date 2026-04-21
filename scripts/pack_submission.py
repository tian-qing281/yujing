"""打包完整可运行的参赛源码 zip。排除测试文件和非交付物。"""
import zipfile, os, sys

ROOT = r"D:\Desktop\计算机设计大赛\yujing"
DEST = r"D:\Desktop\计算机设计大赛\2026042001-参赛总文件夹\2026042001-02素材与源码\2026042001-源码.zip"

# 要打进 zip 的顶层条目
INCLUDES = [
    # 源码
    ("app", "app"),
    ("scripts", "scripts"),
    ("yujing-ui", "yujing-ui"),
    # 配置
    ("requirements.txt", "requirements.txt"),
    (".env.example", ".env.example"),
    (".env", ".env"),
    # 运行时数据
    ("runtime/db/yujing.db", "runtime/db/yujing.db"),
    ("runtime/meili/meilisearch-windows-amd64.exe", "runtime/meili/meilisearch-windows-amd64.exe"),
    ("runtime/meili/data.ms", "runtime/meili/data.ms"),
]

# 要排除的目录名（精确匹配）
EXCLUDE_DIRS = {
    '__pycache__', '.pytest_cache', 'node_modules', '.git', '.codex',
    '.vscode', '_backups', '_bug_images', '__backup', 'tests',
    'media_cache',
}

# 要排除的文件扩展名
EXCLUDE_EXTS = {'.pyc', '.bak', '.log'}

# 要排除的文件名
EXCLUDE_FILES = {
    'AGENTS.md', 'CLAUDE.md', 'routes.py.bak',
    'yujing.db-shm', 'yujing.db-wal',
}

def should_exclude(rel_parts, filename):
    for part in rel_parts:
        if part in EXCLUDE_DIRS:
            return True
    if filename in EXCLUDE_FILES:
        return True
    _, ext = os.path.splitext(filename)
    if ext.lower() in EXCLUDE_EXTS:
        return True
    return False

LARGE_THRESHOLD = 50 * 1024 * 1024  # 50MB

def add_path(zf, src_abs, arc_prefix):
    if os.path.isfile(src_abs):
        # Large files stored without compression for speed
        if os.path.getsize(src_abs) > LARGE_THRESHOLD:
            zf.write(src_abs, arc_prefix, compress_type=zipfile.ZIP_STORED)
        else:
            zf.write(src_abs, arc_prefix)
        return 1
    count = 0
    for dirpath, dirnames, filenames in os.walk(src_abs):
        rel = os.path.relpath(dirpath, src_abs)
        parts = rel.split(os.sep) if rel != '.' else []
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if should_exclude(parts, fn):
                continue
            full = os.path.join(dirpath, fn)
            arc = os.path.join(arc_prefix, rel, fn) if rel != '.' else os.path.join(arc_prefix, fn)
            zf.write(full, arc)
            count += 1
    return count

def main():
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    total = 0
    with zipfile.ZipFile(DEST, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src_rel, arc_name in INCLUDES:
            src_abs = os.path.join(ROOT, src_rel)
            if not os.path.exists(src_abs):
                print(f"  SKIP (not found): {src_rel}")
                continue
            n = add_path(zf, src_abs, arc_name)
            size_mb = sum(i.compress_size for i in zf.infolist() if i.filename.startswith(arc_name)) / 1024 / 1024
            print(f"  + {arc_name}: {n} files")
            total += n
    
    final_mb = os.path.getsize(DEST) / 1024 / 1024
    print(f"\nTotal: {total} files, {final_mb:.1f} MB -> {DEST}")

if __name__ == "__main__":
    main()
