"""在截图里找白色移动点，断言它沿着轨迹动了、然后停住了。"""
import sys
from pathlib import Path
from PIL import Image

OUT = Path(r"E:\JAVA_IDEA_package\JAVA_Project\Calcite\.tmp\playback-shots")

# 排除区域：左侧面板 x<400（白色文字），底部播放条 y>820
def find_white_dot(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()
    xs, ys = [], []
    for y in range(0, min(h, 820)):
        for x in range(400, w):
            r, g, b = px[x, y]
            if r >= 250 and g >= 250 and b >= 250:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None, 0
    return (sum(xs) / len(xs), sum(ys) / len(ys)), len(xs)

def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

shots = {}
for name in ("shot1", "shot2", "shot3"):
    path = OUT / (name + ".png")
    if not path.exists():
        print("FAIL 缺少截图 " + str(path))
        sys.exit(1)
    center, count = find_white_dot(path)
    if center is None:
        print("FAIL " + name + " 里没找到白色移动点")
        sys.exit(2)
    shots[name] = center
    print(f"{name}: 白色点中心 = ({center[0]:.1f}, {center[1]:.1f})，{count} 个像素")

d12 = dist(shots["shot1"], shots["shot2"])
d23 = dist(shots["shot2"], shots["shot3"])
print(f"播放中移动距离 = {d12:.1f} px")
print(f"暂停后位移     = {d23:.1f} px")

if d12 < 5:
    print("FAIL 播放中白点几乎没动，回放没生效")
    sys.exit(3)
if d23 > 2:
    print("FAIL 暂停后白点还在动，暂停没生效")
    sys.exit(4)

print("OK 回放验证通过：动了，然后停住了")
