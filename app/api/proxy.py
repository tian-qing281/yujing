import httpx
import os
import hashlib
from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(BASE_DIR, "runtime", "media_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

@router.get("/proxy")
async def proxy_media(url: str):
    """工业级媒体透传代理：动态注入 Referer + Byte-Range 物理支持"""
    if not url: return {"error": "Invalid URL"}
    
    if url.startswith("//"):
        url = f"https:{url}"
    
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    
    # 动态探测 MIME与 Referer
    referer = "https://weibo.com/"
    if "zhihu.com" in url: referer = "https://www.zhihu.com/"
    elif "baidu.com" in url: referer = "https://www.baidu.com/"
    elif "hdslb.com" in url or "bilibili.com" in url: referer = "https://www.bilibili.com/"
    elif "sinaimg.cn" in url: referer = "https://weibo.com/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    }

    ext = ".jpg"
    is_video = False
    if ".mp4" in url or "video" in url: 
        ext = ".mp4"
        is_video = True
    elif ".png" in url: ext = ".png"
    elif ".gif" in url: ext = ".gif"
    elif ".webp" in url: ext = ".webp"
    
    cache_path = os.path.join(CACHE_DIR, f"{url_hash}{ext}")

    if os.path.exists(cache_path):
        return FileResponse(cache_path, headers={"Cache-Control": "public, max-age=31536000"})

    if is_video:
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=120.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                with open(cache_path, "wb") as f:
                    f.write(resp.content)
            return FileResponse(cache_path, headers={"Cache-Control": "public, max-age=31536000"})
        except Exception as e:
            return {"error": f"Video sync failed: {e}"}

    async def generate_and_cache():
        try:
            async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
                async with client.stream("GET", url, headers=headers, timeout=30.0) as r:
                    r.raise_for_status()
                    with open(cache_path, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            f.write(chunk)
                            yield chunk
        except Exception:
            yield b""

    return StreamingResponse(generate_and_cache(), media_type=f"image/{ext.replace('.','')}" if not is_video else "video/mp4")
