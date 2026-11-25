import sys, os, win32com.client.dynamic as d
src, out = map(os.path.abspath, sys.argv[1:3])
app = d.Dispatch("PowerPoint.Application")
p = app.Presentations.Open(src, True, False, False)
p.Slides(1).Export(out, "PNG", 1400, 1983)
p.Close()
print("ok")
