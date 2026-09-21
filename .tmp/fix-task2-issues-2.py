# -*- coding: utf-8 -*-
r"""补齐上一步没替换成功的地方（空行/缩进对不上）。

实际现状：
  TrackEditService.findNameConflict 里还是 findFirstByName(...).filter(...).map(...)
  但仓储已经改成 findAllByName → 编译不过
  TrackPointRepository 缺 @Modifying 的 import

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-task2-issues-2.py
"""
import io
import sys

SERVICE = "backend/src/main/java/com/calcite/service/TrackEditService.java"
REPO_POINT = "backend/src/main/java/com/calcite/repository/TrackPointRepository.java"
TEST = "backend/src/test/java/com/calcite/service/TrackEditServiceTest.java"
PLAN = "docs/superpowers/plans/2026-09-21-data-management.md"

EDITS = [
    # ① service 里的调用改成 findAllByName（去掉一行 .map 前面的空行差异）
    (SERVICE,
     "        return trackRepository.findFirstByName(name)\n"
     "                .filter(t -> !t.getId().equals(excludeTrackId))\n"
     "                .map(Track::getId);",
     "        return trackRepository.findAllByName(name).stream()\n"
     "                .filter(t -> !t.getId().equals(excludeTrackId))\n"
     "                .map(Track::getId)\n"
     "                .findFirst();"),

    # ② 仓储补 @Modifying 的 import
    (REPO_POINT,
     "import org.springframework.data.jpa.repository.JpaRepository;\n"
     "import org.springframework.data.jpa.repository.Query;",
     "import org.springframework.data.jpa.repository.JpaRepository;\n"
     "import org.springframework.data.jpa.repository.Modifying;\n"
     "import org.springframework.data.jpa.repository.Query;"),
]

# ③ 测试文件：先把实际内容读出来看看是不是子代理已经改过了
def patch_test():
    with io.open(TEST, encoding="utf-8") as fh:
        t = fh.read()
    marker = "isNameConflict"
    if marker not in t:
        print("  [--] 测试文件里没有 isNameConflict，跳过")
        return True
    import re
    # 找到那个测试方法体，整体替换成新签名
    m = re.search(r"    @Test\n    void 同名判定_排除自己\(\) \{.*?\n    \}\n", t, re.S)
    if not m:
        print("  [--] 没匹配到『同名判定_排除自己』那个方法，跳过")
        return True
    new = """    @Test
    void 同名判定_排除自己() {
        assertEquals(false, TrackEditService.isNameConflict(3L, 3L),
                "找到的『同名那条』就是我自己 → 不算冲突");
        assertEquals(true, TrackEditService.isNameConflict(3L, 4L),
                "找到的『同名那条』是别人的 → 冲突");
        assertEquals(false, TrackEditService.isNameConflict(3L, null),
                "库里没有同名 → 不冲突");
    }
"""
    t = t[:m.start()] + new + t[m.end():]
    with io.open(TEST, "w", encoding="utf-8", newline="") as fh:
        fh.write(t)
    print("  [OK] 测试方法已换成新签名")
    return True


def patch_plan():
    with io.open(PLAN, encoding="utf-8") as fh:
        t = fh.read()
    reps = [
        ("        return trackRepository.findFirstByName(name)\n"
         "                .filter(t -> !t.getId().equals(excludeTrackId))\n"
         "                .map(Track::getId)\n"
         "                .findFirst();",
         "        return trackRepository.findAllByName(name).stream()\n"
         "                .filter(t -> !t.getId().equals(excludeTrackId))\n"
         "                .map(Track::getId)\n"
         "                .findFirst();"),
        ("     * <p>派生删除：Spring Data 会翻译成 {@code DELETE FROM track_point WHERE track_id = ?}。",
         "     * <p><b>⚠️ 必须用 {@code @Modifying + @Query}，不能用派生删除</b>：\n"
         "     * Spring Data 的派生删除会<b>先把匹配的实体全部查出来</b>再逐个 {@code em.remove()}，发 <b>N 条 DELETE</b> ——\n"
         "     * 替换一条 14186 点的轨迹就是 14186 条 DELETE。这个写法只发<b>一条</b>。\n"
         "     *\n"
         "     * <p>（原注释说的『派生删除 = DELETE FROM ...』是不准确的。）"),
    ]
    ok = True
    for old, new in reps:
        n = t.count(old)
        if n != 1:
            print(f"  [--] 计划里命中 {n} 次，跳过：{old[:44]!r}")
            continue
        t = t.replace(old, new)
        print(f"  [OK] 计划 {old[:44]}…")
    with io.open(PLAN, "w", encoding="utf-8", newline="") as fh:
        fh.write(t)
    return ok


def main():
    ok = True
    for path, old, new in EDITS:
        with io.open(path, encoding="utf-8") as fh:
            t = fh.read()
        n = t.count(old)
        if n != 1:
            print(f"  [XX] {path.split('/')[-1]} 命中 {n} 次：{old[:50]!r}")
            ok = False
            continue
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(t.replace(old, new))
        print(f"  [OK] {path.split('/')[-1]}  {old[:48]}…")
    ok = patch_test() and ok
    patch_plan()
    print()
    print("全部修正完成" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
