# -*- coding: utf-8 -*-
r"""修正 Task 2 子代理报出的三个真问题（都是计划/代码里的疏漏）。

① deleteByTrackId 用的是【派生删除】——Spring Data 会先把匹配的实体全部查出来，
   再逐个 em.remove()，发 N 条 DELETE。替换一条 14186 点的轨迹 = 14186 条 DELETE。
   改成 @Modifying + @Query 的一条批量 DELETE。

② findFirstByName 在同名 >=2 条时，findFirst 可能恰好命中"被排除的那条" → 漏报冲突。
   改成 findAllByName 再在 Java 里过滤（同名不会很多，成本可忽略）。

③ isNameConflict(currentName, newName, currentId, otherTrackId) 里
   currentName / newName 两个参数【根本没用到】—— 参数表在撒谎。
   简化成 isNameConflict(currentId, otherTrackId)。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-task2-issues.py
"""
import io
import sys

REPO_POINT = "backend/src/main/java/com/calcite/repository/TrackPointRepository.java"
REPO_TRACK = "backend/src/main/java/com/calcite/repository/TrackRepository.java"
SERVICE = "backend/src/main/java/com/calcite/service/TrackEditService.java"
TEST = "backend/src/test/java/com/calcite/service/TrackEditServiceTest.java"
PLAN = "docs/superpowers/plans/2026-09-21-data-management.md"

EDITS = []

# ---------- ① 批量删除 ----------
EDITS.append((REPO_POINT,
    """    void deleteByTrackId(Long trackId);""",
    """    @Modifying
    @Query("DELETE FROM TrackPoint p WHERE p.trackId = :trackId")
    void deleteByTrackId(@Param("trackId") Long trackId);"""))

# ---------- ② findAllByName ----------
EDITS.append((REPO_TRACK,
    """    Optional<Track> findFirstByName(String name);""",
    """    List<Track> findAllByName(String name);"""))

EDITS.append((SERVICE,
    """        return trackRepository.findFirstByName(name)
                .filter(t -> !t.getId().equals(excludeTrackId))
                .map(Track::getId)
                .findFirst();""",
    """        return trackRepository.findAllByName(name).stream()
                .filter(t -> !t.getId().equals(excludeTrackId))
                .map(Track::getId)
                .findFirst();"""))

# ---------- ③ 简化 isNameConflict 的签名 ----------
EDITS.append((SERVICE,
    """    public static boolean isNameConflict(String currentName, String newName,
                                         Long currentId, Long otherTrackId) {
        if (otherTrackId == null) {
            return false;
        }
        return !otherTrackId.equals(currentId);
    }""",
    """    public static boolean isNameConflict(Long currentId, Long otherTrackId) {
        if (otherTrackId == null) {
            return false;
        }
        return !otherTrackId.equals(currentId);
    }"""))

# 同步改计划里那段 javadoc（参数说明）
EDITS.append((SERVICE,
    """     * @param currentName   被改的那条现在的名字
     * @param newName       想改成的新名字
     * @param currentId     被改的那条的 id
     * @param otherTrackId  库里另一条同名轨迹的 id（没有同名就传 null）
     * @return true = 会和别人撞名""",
    """     * @param currentId    被改的那条的 id
     * @param otherTrackId 库里另一条同名轨迹的 id（没有同名就传 null）
     * @return true = 会和别人撞名
     *
     * <p><b>⚠️ 为什么参数表里没有名字</b>：早先的版本带了 {@code currentName} / {@code newName}
     * 两个参数，但<b>实现里根本没用它们</b> —— "按新名字去库里找"是调用方的事。
     * 参数表在撒谎比没有参数更糟，所以砍掉了。"""))

# ---------- 同步改测试 ----------
EDITS.append((TEST,
    """        assertEquals(true, TrackEditService.isNameConflict("资料一", "资料一", 3L, 3L),
                "改回自己原来的名字不算冲突");
        assertEquals(true, TrackEditService.isNameConflict("资料一", "资料二", 3L, 3L),
                "改成别的名字才可能是冲突");
        assertEquals(false, TrackEditService.isNameConflict("资料一", "资料一", 3L, 4L),
                "和别人同名才是冲突");""",
    """        assertEquals(false, TrackEditService.isNameConflict(3L, 3L),
                "找到的『同名那条』就是我自己 → 不算冲突");
        assertEquals(true, TrackEditService.isNameConflict(3L, 4L),
                "找到的『同名那条』是别人的 → 冲突");
        assertEquals(false, TrackEditService.isNameConflict(3L, null),
                "库里没有同名 → 不冲突");"""))

# ---------- 同步改计划（三处代码块） ----------
EDITS.append((PLAN,
    """    Optional<Track> findFirstByName(String name);""",
    """    List<Track> findAllByName(String name);"""))

EDITS.append((PLAN,
    """    /**
     * 按名字找一条轨迹（同名检测用）。
     *
     * <p>Spring Data 的派生查询 —— 方法名翻译成 SQL 的 {@code WHERE name = ? LIMIT 1}。
     */""",
    """    /**
     * 按名字找**所有**同名轨迹（同名检测用）。
     *
     * <p>⚠️ 用 {@code findAllByName} 而不是 {@code findFirstByName}：
     * {@code name} 在库里**没有唯一约束**（设计上允许重名），
     * 所以同名 ≥2 条时 {@code findFirst} 可能恰好命中"被排除的那条" → **漏报冲突**。
     */"""))

EDITS.append((PLAN,
    """    void deleteByTrackId(Long trackId);""",
    """    @Modifying
    @Query("DELETE FROM TrackPoint p WHERE p.trackId = :trackId")
    void deleteByTrackId(@Param("trackId") Long trackId);"""))

EDITS.append((PLAN,
    """     * <p>派生删除：Spring Data 会翻译成 {@code DELETE FROM track_point WHERE track_id = ?}。
     * <b>为什么不用 {@code trackPointRepository.deleteAll(points)}</b>：
     * 那会把几万个实体一个个查出来再删 —— 慢得多，而且内存里要放 1 万多个对象。""",
    """     * <p><b>⚠️ 必须用 {@code @Modifying + @Query}，不能用派生删除</b>：
     * Spring Data 的派生删除（{@code deleteByTrackId}）会<b>先把匹配的实体全部查出来</b>，
     * 再逐个 {@code em.remove()}，发 <b>N 条 DELETE</b> ——
     * 替换一条 14186 点的轨迹就是 14186 条 DELETE。
     * 这个写法发的是<b>一条</b> {@code DELETE FROM track_point WHERE track_id = ?}。"""))

EDITS.append((PLAN,
    """    public static boolean isNameConflict(String currentName, String newName,
                                         Long currentId, Long otherTrackId) {
        if (otherTrackId == null) {
            return false;
        }
        return !otherTrackId.equals(currentId);
    }""",
    """    public static boolean isNameConflict(Long currentId, Long otherTrackId) {
        if (otherTrackId == null) {
            return false;
        }
        return !otherTrackId.equals(currentId);
    }"""))

EDITS.append((PLAN,
    """        assertEquals(true, TrackEditService.isNameConflict("资料一", "资料一", 3L, 3L),
                "改回自己原来的名字不算冲突");
        assertEquals(true, TrackEditService.isNameConflict("资料一", "资料二", 3L, 3L),
                "改成别的名字才可能是冲突");
        assertEquals(false, TrackEditService.isNameConflict("资料一", "资料一", 3L, 4L),
                "和别人同名才是冲突");""",
    """        assertEquals(false, TrackEditService.isNameConflict(3L, 3L),
                "找到的『同名那条』就是我自己 → 不算冲突");
        assertEquals(true, TrackEditService.isNameConflict(3L, 4L),
                "找到的『同名那条』是别人的 → 冲突");
        assertEquals(false, TrackEditService.isNameConflict(3L, null),
                "库里没有同名 → 不冲突");"""))

EDITS.append((PLAN,
    """        return trackRepository.findFirstByName(name)
                .filter(t -> !t.getId().equals(excludeTrackId))
                .map(Track::getId)
                .findFirst();""",
    """        return trackRepository.findAllByName(name).stream()
                .filter(t -> !t.getId().equals(excludeTrackId))
                .map(Track::getId)
                .findFirst();"""))


def main():
    # 按文件分组，逐个替换（同一个文件可能有多处）
    by_file = {}
    for path, old, new in EDITS:
        by_file.setdefault(path, []).append((old, new))

    ok = True
    for path, pairs in by_file.items():
        with io.open(path, encoding="utf-8") as fh:
            t = fh.read()
        for old, new in pairs:
            n = t.count(old)
            if n != 1:
                print(f"  [XX] {path.split('/')[-1]} 期望命中 1 次，实得 {n}：{old[:52]!r}")
                ok = False
                continue
            t = t.replace(old, new)
            print(f"  [OK] {path.split('/')[-1]}  {old[:48]}…")
        if ok:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
    print()
    print("全部修正完成" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
