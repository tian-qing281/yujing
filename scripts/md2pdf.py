"""将 Markdown 文档转为带样式的 HTML，再用 Edge 无头模式打印 PDF。"""
import sys, os, pathlib, subprocess, markdown

CSS = """
<style>
  @page { size: A4; margin: 2cm 2.5cm; }
  body { font-family: "Microsoft YaHei", sans-serif; font-size: 11pt; line-height: 1.6; color: #222; max-width: 100%; }
  h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 6px; margin-top: 32px; }
  h2 { font-size: 15pt; border-bottom: 1px solid #aaa; padding-bottom: 4px; margin-top: 28px; }
  h3 { font-size: 13pt; margin-top: 20px; }
  code { font-family: Consolas, "Microsoft YaHei", monospace; background: #f4f4f4; padding: 1px 4px; border-radius: 3px; font-size: 10pt; }
  pre { background: #f8f8f8; border: 1px solid #ddd; border-radius: 4px; padding: 12px; overflow-x: auto; font-size: 9.5pt; line-height: 1.4; }
  pre code { background: none; padding: 0; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; }
  th, td { border: 1px solid #bbb; padding: 6px 10px; text-align: left; }
  th { background: #f0f0f0; font-weight: bold; }
  tr:nth-child(even) { background: #fafafa; }
  blockquote { border-left: 4px solid #ccc; margin: 12px 0; padding: 8px 16px; color: #555; background: #fafafa; }
  hr { border: none; border-top: 1px solid #ccc; margin: 24px 0; }
</style>
"""

def md_to_pdf(md_path: str, pdf_path: str, edge_exe: str):
    text = pathlib.Path(md_path).read_text(encoding="utf-8")
    html_body = markdown.markdown(text, extensions=["tables", "fenced_code", "codehilite", "toc"])
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Document</title>{CSS}</head>
<body>{html_body}</body>
</html>"""
    html_path = pdf_path.replace(".pdf", ".html")
    pathlib.Path(html_path).write_text(html, encoding="utf-8")
    subprocess.run([
        edge_exe, "--headless", "--disable-gpu",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        html_path
    ], capture_output=True, timeout=30)
    os.remove(html_path)
    size_kb = os.path.getsize(pdf_path) / 1024
    print(f"  OK: {os.path.basename(pdf_path)}  ({size_kb:.0f} KB)")

if __name__ == "__main__":
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    root = r"D:\Desktop\计算机设计大赛\yujing"
    out = r"D:\Desktop\计算机设计大赛\2026042001-参赛总文件夹\2026042001-03设计与开发文档"
    docs = [
        ("核心原理文档.md", "2026042001-核心原理文档.pdf"),
        ("项目文档.md",     "2026042001-项目文档.pdf"),
        ("部署文档.md",     "2026042001-本地部署说明.pdf"),
        ("评测指标文档.md", "2026042001-评测指标文档.pdf"),
    ]
    for src, dst in docs:
        print(f"Converting {src} ...")
        md_to_pdf(os.path.join(root, src), os.path.join(out, dst), edge)
    print("All done.")
