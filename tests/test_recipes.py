from __future__ import annotations

from picgen.recipes import list_prompt_recipes, recipe_public_dict


def test_prompt_recipes_return_independent_public_copies():
    recipes = list_prompt_recipes()
    assert recipes

    first_recipe_id = recipes[0]["id"]
    original_title = recipes[0]["title"]
    recipes[0]["title"] = "mutated title"
    recipes[0]["recommended_keywords"].append("mutated keyword")

    fresh_recipe = recipe_public_dict(first_recipe_id)

    assert fresh_recipe is not None
    assert fresh_recipe["title"] == original_title
    assert "mutated keyword" not in fresh_recipe["recommended_keywords"]


def test_route_map_recipe_is_global_and_geography_first():
    recipe = recipe_public_dict("route-map-comic")

    assert recipe is not None
    assert recipe["default_size"] == "1792x1792"
    assert "真实地图相对位置准确" in recipe["prompt_suffix"]
    assert "新疆" not in recipe["prompt_suffix"]
