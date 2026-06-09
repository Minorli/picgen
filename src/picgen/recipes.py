from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptRecipe:
    id: str
    version: str
    title: str
    category: str
    summary: str
    mode: str
    guidance: str
    prompt_suffix: str
    default_size: str
    recommended_keywords: tuple[str, ...]

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "category": self.category,
            "summary": self.summary,
            "mode": self.mode,
            "guidance": self.guidance,
            "prompt_suffix": self.prompt_suffix,
            "default_size": self.default_size,
            "recommended_keywords": list(self.recommended_keywords),
        }


_RECIPES: tuple[PromptRecipe, ...] = (
    PromptRecipe(
        id="travel-poster-premium",
        version="2026-06-08",
        title="高级旅行海报",
        category="旅行营销",
        summary="适合朋友圈、公众号头图和销售海报。强调真实目的地感、商业摄影质感和克制构图。",
        mode="generate",
        guidance="先写清楚目的地、客群、投放渠道和必须保留的信息，再用配方补充画面质量要求。",
        prompt_suffix=(
            "高级旅行商业海报；真实目的地氛围；主体清晰；构图稳定；自然光或电影光影；"
            "材质细节真实；色彩克制；避免廉价旅行社模板、过饱和、夸张大字和虚构 LOGO。"
        ),
        default_size="1088x2240",
        recommended_keywords=("高级旅行", "精致海报", "电影光影", "色彩克制"),
    ),
    PromptRecipe(
        id="hotel-texture",
        version="2026-06-08",
        title="酒店质感",
        category="高端住宿",
        summary="适合酒店、民宿、度假村和高端定制产品视觉。强调材质、光线和安静的奢华感。",
        mode="generate",
        guidance="提示词里应写明空间类型、材质、时间、客群与要传达的服务感。",
        prompt_suffix=(
            "精品酒店摄影质感；真实空间尺度；高端织物、木材、石材和玻璃材质；"
            "柔和自然光；画面干净；生活方式摄影；避免样板间塑料感和过度磨皮。"
        ),
        default_size="1088x2240",
        recommended_keywords=("酒店质感", "色彩克制", "精致海报"),
    ),
    PromptRecipe(
        id="wild-retreat",
        version="2026-06-08",
        title="山野度假",
        category="自然度假",
        summary="适合小众自然风光、徒步、营地和轻奢户外产品。强调自然真实与生活方式感。",
        mode="generate",
        guidance="提示词里应写清地貌、季节、天气、人物尺度和希望保留的自然特征。",
        prompt_suffix=(
            "山野度假生活方式摄影；真实自然地貌；空气感；远近层次清楚；"
            "人物不过度摆拍；户外装备精致但不喧宾夺主；避免假景、塑料感和过度奇幻。"
        ),
        default_size="1088x2240",
        recommended_keywords=("山野度假", "高级旅行", "电影光影"),
    ),
    PromptRecipe(
        id="route-map-comic",
        version="2026-06-08",
        title="漫画路线图",
        category="行程路线",
        summary="适合把真实行程转成客户可读的路线图海报。漫画风格必须服从地理真实性。",
        mode="itinerary",
        guidance="粘贴真实日期、地点、交通和活动，补充地理校验要求；不要用具体旧客户行程当模板。",
        prompt_suffix=(
            "水彩漫画路线图；真实地图相对位置准确；每日日期完整；每段路线有交通方式和距离说明；"
            "地标小插画精致；路线清晰不缠绕；不要为了好看交换地点位置。"
        ),
        default_size="1792x1792",
        recommended_keywords=("漫画路线图", "地理真实", "日期完整"),
    ),
)


def list_prompt_recipes() -> list[dict[str, Any]]:
    return [recipe.public_dict() for recipe in _RECIPES]


def get_prompt_recipe(recipe_id: str) -> PromptRecipe | None:
    normalized = recipe_id.strip()
    for recipe in _RECIPES:
        if recipe.id == normalized:
            return recipe
    return None


def recipe_public_dict(recipe_id: str) -> dict[str, Any] | None:
    recipe = get_prompt_recipe(recipe_id)
    return recipe.public_dict() if recipe else None
