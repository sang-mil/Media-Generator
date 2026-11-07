from __future__ import annotations

from collections import defaultdict
from typing import Any


WEIGHTS = {
    "likes": 0.15,
    "comments": 0.10,
    "saves": 0.25,
    "shares": 0.30,
    "follows": 0.20,
}


def score_post(metrics: dict[str, Any]) -> float:
    """Transparent weighted response score, normalized by reach, on a 0-100 scale."""
    denominator = max(int(metrics.get("reach", 0) or 0), int(metrics.get("views", 0) or 0), 1)
    weighted_rate = sum(WEIGHTS[key] * (int(metrics.get(key, 0) or 0) / denominator) for key in WEIGHTS)
    return round(weighted_rate * 100, 4)


def build_recommendations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [r for r in rows if r.get("measured_at")]
    if len(measured) < 3:
        return {
            "status": "collecting_data",
            "measured_posts": len(measured),
            "message": f"아직 성과 데이터가 {len(measured)}개 게시물에만 있습니다. 최소 3개 게시물의 성과를 입력하면 첫 비교를 시작합니다.",
            "recommendations": [],
            "method": "가중 반응 점수: 좋아요 15%, 댓글 10%, 저장 25%, 공유 30%, 팔로우 20%를 도달 또는 조회수로 나눠 계산합니다.",
        }

    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    category_scores: dict[str, list[float]] = defaultdict(list)
    format_scores: dict[str, list[float]] = defaultdict(list)
    scored_posts = []
    for row in measured:
        metrics = row.get("metrics") or row
        score = score_post(metrics)
        category = row.get("category", "기타")
        fmt = row.get("format", "unknown")
        groups[(category, fmt)].append(score)
        category_scores[category].append(score)
        format_scores[fmt].append(score)
        scored_posts.append({"title": row.get("title", "제목 없음"), "category": category, "format": fmt, "score": score})

    # Small samples are deliberately shrunk toward the account-wide average.
    overall_mean = sum(score_post(r.get("metrics") or r) for r in measured) / len(measured)
    rankings = []
    for (category, fmt), scores in groups.items():
        n = len(scores)
        observed_mean = sum(scores) / n
        confidence_adjusted = (observed_mean * n + overall_mean * 3) / (n + 3)
        rankings.append({
            "category": category,
            "format": fmt,
            "posts": n,
            "observed_score": round(observed_mean, 4),
            "adjusted_score": round(confidence_adjusted, 4),
        })
    rankings.sort(key=lambda x: (x["adjusted_score"], x["posts"]), reverse=True)

    best = rankings[0] if rankings else None
    under_tested = [r for r in rankings if r["posts"] < 2]
    suggestions = []
    if best:
        suggestions.append({
            "type": "repeat_winner",
            "title": f"'{best['category']}' 주제를 '{best['format']}' 형식으로 한 번 더 테스트",
            "reason": f"현재 가장 높은 보정 점수 {best['adjusted_score']}점. 표본이 적으므로 승자로 확정하지 않고 재검증합니다.",
        })
    if under_tested:
        suggestions.append({
            "type": "explore",
            "title": "표본이 적은 주제·형식도 계속 실험",
            "reason": "조회수가 적다는 이유만으로 초기에 가능성 있는 포맷을 제외하지 않도록 합니다.",
        })
    suggestions.append({
        "type": "quality",
        "title": "저장·공유를 유도하는 정보 밀도를 유지",
        "reason": "현재 학습 점수에서 저장 25%, 공유 30%를 반영합니다. 팔로워 성장 초기에는 실용성과 전달력을 함께 검증합니다.",
    })
    return {
        "status": "learning",
        "measured_posts": len(measured),
        "message": "초기 성과를 바탕으로 다음 실험을 추천합니다. 아직 소표본이므로 자동으로 콘텐츠 전략을 바꾸지 않습니다.",
        "recommendations": suggestions,
        "rankings": rankings,
        "recent_scores": sorted(scored_posts, key=lambda x: x["score"], reverse=True)[:10],
        "method": "가중 반응 점수: 좋아요 15%, 댓글 10%, 저장 25%, 공유 30%, 팔로우 20%. 그룹 표본이 적으면 계정 전체 평균 쪽으로 보정합니다.",
    }
