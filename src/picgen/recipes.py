from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SceneOption:
    value: str
    label: str
    description: str = ""

    def public_dict(self) -> dict[str, str]:
        return {
            "value": self.value,
            "label": self.label,
            **({"description": self.description} if self.description else {}),
        }


@dataclass(frozen=True)
class SceneField:
    name: str
    label: str
    kind: str
    required: bool = False
    placeholder: str = ""
    max_items: int | None = None
    options: tuple[SceneOption, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "required": self.required,
            **({"placeholder": self.placeholder} if self.placeholder else {}),
            **({"max_items": self.max_items} if self.max_items is not None else {}),
            **({"options": [option.public_dict() for option in self.options]} if self.options else {}),
        }


@dataclass(frozen=True)
class SceneCard:
    order: int
    title: str
    cover: str
    subtitle: str
    fields: tuple[SceneField, ...]
    template: str
    default_size: str
    submit_kind: str
    submit_label: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "title": self.title,
            "cover": self.cover,
            "subtitle": self.subtitle,
            "fields": [field.public_dict() for field in self.fields],
            "template": self.template,
            "default_size": self.default_size,
            "submit": {
                "kind": self.submit_kind,
                "label": self.submit_label,
            },
        }


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
    scene_card: SceneCard | None = None

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
            **({"scene_card": self.scene_card.public_dict()} if self.scene_card else {}),
        }


_POSTER_SIZE_OPTIONS = (
    SceneOption("1088x2240", "手机全屏海报", "1088 x 2240"),
    SceneOption("1024x1024", "方图", "1024 x 1024"),
    SceneOption("1536x1024", "横图", "1536 x 1024"),
)


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
        scene_card=SceneCard(
            order=1,
            title="竖版海报",
            cover="scene-poster.jpg",
            subtitle="朋友圈/群发宣传图",
            fields=(
                SceneField("title", "主标题", "text", required=True, placeholder="例如：金秋北疆·喀纳斯"),
                SceneField("subtitle", "副标题", "text", placeholder="例如：禾木晨雾 · 湖畔木屋"),
                SceneField("highlights", "亮点", "list", placeholder="一行一个亮点", max_items=8),
                SceneField("price", "参考价", "text", placeholder="例如：21000 元/人"),
                SceneField(
                    "atmosphere",
                    "画面氛围",
                    "chips",
                    options=tuple(
                        SceneOption(keyword, keyword)
                        for keyword in ("高级旅行", "山野度假", "电影光影", "色彩克制", "精致海报")
                    ),
                ),
                SceneField("reference_image", "参考图", "image"),
                SceneField("size", "尺寸", "size", required=True, options=_POSTER_SIZE_OPTIONS),
            ),
            template=(
                "制作一张竖版旅行宣传海报。\n"
                "主标题：{{title}}\n副标题：{{subtitle}}\n亮点：{{highlights}}\n"
                "参考价：{{price}}\n画面氛围：{{atmosphere}}"
            ),
            default_size="1088x2240",
            submit_kind="generate",
            submit_label="生成海报",
        ),
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
        scene_card=SceneCard(
            order=2,
            title="行程路线图",
            cover="scene-itinerary.jpg",
            subtitle="按真实地理位置的漫画路线图",
            fields=(
                SceneField("title", "标题", "text", required=True, placeholder="例如：北疆秋日之旅"),
                SceneField("subtitle", "副标题日期", "text", required=True, placeholder="例如：9/5 - 9/12"),
                SceneField(
                    "itinerary",
                    "逐日行程",
                    "textarea",
                    required=True,
                    placeholder="粘贴包含日期、地点和交通方式的逐日行程",
                ),
            ),
            template="标题：{{title}}\n副标题/日期：{{subtitle}}\n逐日行程：\n{{itinerary}}",
            default_size="1792x1792",
            submit_kind="itinerary",
            submit_label="生成路线图",
        ),
    ),
    PromptRecipe(
        id="list-ranking",
        version="2026-07-11",
        title="清单/榜单",
        category="信息海报",
        summary="适合 TOP10、对比表和推荐榜单等信息密度较高的长图。",
        mode="generate",
        guidance="填写清晰的榜单标题和短条目，避免在单个条目中堆叠过多信息。",
        prompt_suffix=(
            "信息层级清楚；标题醒目；条目编号和文字完整可读；网格对齐；留白稳定；避免文字遮挡、内容截断和装饰喧宾夺主。"
        ),
        default_size="1088x2240",
        recommended_keywords=("精致海报", "色彩克制"),
        scene_card=SceneCard(
            order=3,
            title="清单/榜单",
            cover="scene-ranking.jpg",
            subtitle="TOP10、对比表、榜单图",
            fields=(
                SceneField("title", "榜单标题", "text", required=True, placeholder="例如：欧洲亲子博物馆 TOP10"),
                SceneField(
                    "items",
                    "条目列表",
                    "list",
                    required=True,
                    placeholder="一行一个条目",
                    max_items=15,
                ),
                SceneField(
                    "style",
                    "风格",
                    "chips",
                    options=tuple(
                        SceneOption(keyword, keyword) for keyword in ("高级旅行", "精致海报", "色彩克制", "电影光影")
                    ),
                ),
                SceneField("size", "尺寸", "size", required=True, options=_POSTER_SIZE_OPTIONS),
            ),
            template="制作一张清单或榜单海报。\n榜单标题：{{title}}\n条目：\n{{items}}\n视觉风格：{{style}}",
            default_size="1088x2240",
            submit_kind="generate",
            submit_label="生成榜单",
        ),
    ),
    PromptRecipe(
        id="image-edit",
        version="2026-07-11",
        title="改一张图",
        category="图像编辑",
        summary="上传现有图片，完成换字、换色、去杂物等局部修改。",
        mode="generate",
        guidance="明确说明需要修改的区域和必须保持不变的内容。",
        prompt_suffix="只修改明确指定的内容；其余构图、文字、人物、物体、色彩和细节保持不变。",
        default_size="auto",
        recommended_keywords=("只改背景", "去杂物", "边缘干净", "提高清晰度", "统一色调"),
        scene_card=SceneCard(
            order=4,
            title="改一张图",
            cover="scene-edit.jpg",
            subtitle="换字/换色/去杂物",
            fields=(
                SceneField("image", "图片", "image", required=True),
                SceneField(
                    "instruction",
                    "想改哪里",
                    "textarea",
                    required=True,
                    placeholder="例如：只把主标题改为“初雪喀纳斯”，其余保持不变",
                ),
                SceneField(
                    "quick_actions",
                    "快捷要求",
                    "chips",
                    options=tuple(
                        SceneOption(keyword, keyword)
                        for keyword in ("只改背景", "去杂物", "边缘干净", "提高清晰度", "统一色调")
                    ),
                ),
            ),
            template="{{instruction}}\n补充要求：{{quick_actions}}",
            default_size="auto",
            submit_kind="edit",
            submit_label="开始改图",
        ),
    ),
    PromptRecipe(
        id="free-create",
        version="2026-07-11",
        title="自由创作",
        category="自由创作",
        summary="直接输入完整提示词，自由决定画面内容和风格。",
        mode="generate",
        guidance="写明主体、环境、构图、光线、风格和必须出现的文字。",
        prompt_suffix="构图完整；主体清晰；细节自然；严格保留提示词中明确要求的文字和内容。",
        default_size="1088x2240",
        recommended_keywords=(),
        scene_card=SceneCard(
            order=5,
            title="自由创作",
            cover="scene-free.jpg",
            subtitle="从一句想法开始创作",
            fields=(
                SceneField("prompt", "提示词", "textarea", required=True, placeholder="描述你想生成的画面"),
                SceneField("size", "尺寸", "size", required=True, options=_POSTER_SIZE_OPTIONS),
            ),
            template="{{prompt}}",
            default_size="1088x2240",
            submit_kind="generate",
            submit_label="开始生成",
        ),
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
