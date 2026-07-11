from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _run_logo_policy(expression: str) -> object:
    script = f"""
import {{
  calculateLogoPlacementScore,
  calculateRegionComplexity,
  calculateRegionTextEdgePenalty,
  chooseLogoPlacement,
  expandLogoSafetyRegion,
}} from './static/logo-placement.mjs'
console.log(JSON.stringify({expression}))
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_logo_stays_at_standard_position_for_marginal_improvement() -> None:
    result = _run_logo_policy(
        "chooseLogoPlacement(["
        "{ placement: { x: 42, y: 42, width: 174, height: 54 }, score: 3.809 },"
        "{ placement: { x: 42, y: 81, width: 174, height: 54 }, score: 3.545 },"
        "{ placement: { x: 115, y: 42, width: 174, height: 54 }, score: 3.646 }"
        "])"
    )

    assert result == {"x": 42, "y": 42, "width": 174, "height": 54}


def test_logo_moves_only_for_absolute_and_relative_score_improvement() -> None:
    significant = _run_logo_policy(
        "chooseLogoPlacement(["
        "{ placement: { x: 42, y: 42, width: 174, height: 54 }, score: 10 },"
        "{ placement: { x: 42, y: 81, width: 174, height: 54 }, score: 7.2 }"
        "])"
    )
    absolute_only = _run_logo_policy(
        "chooseLogoPlacement(["
        "{ placement: { x: 42, y: 42, width: 174, height: 54 }, score: 10 },"
        "{ placement: { x: 42, y: 81, width: 174, height: 54 }, score: 7.8 }"
        "])"
    )
    relative_only = _run_logo_policy(
        "chooseLogoPlacement(["
        "{ placement: { x: 42, y: 42, width: 174, height: 54 }, score: 4 },"
        "{ placement: { x: 42, y: 81, width: 174, height: 54 }, score: 2.9 }"
        "])"
    )
    at_both_thresholds = _run_logo_policy(
        "chooseLogoPlacement(["
        "{ placement: { x: 42, y: 42, width: 174, height: 54 }, score: 8 },"
        "{ placement: { x: 42, y: 81, width: 174, height: 54 }, score: 6 }"
        "])"
    )

    assert significant == {"x": 42, "y": 81, "width": 174, "height": 54}
    assert absolute_only == {"x": 42, "y": 42, "width": 174, "height": 54}
    assert relative_only == {"x": 42, "y": 42, "width": 174, "height": 54}
    assert at_both_thresholds == {"x": 42, "y": 81, "width": 174, "height": 54}


def test_logo_safety_region_includes_surrounding_title_space() -> None:
    result = _run_logo_policy(
        "expandLogoSafetyRegion(1088, 2240, { x: 42, y: 42, width: 174, height: 54 })"
    )

    assert result == {"x": 21, "y": 31, "width": 282, "height": 119}


def test_logo_safety_region_is_clamped_to_canvas_edges() -> None:
    result = _run_logo_policy(
        "expandLogoSafetyRegion(100, 80, { x: 0, y: 0, width: 90, height: 70 })"
    )

    assert result == {"x": 0, "y": 0, "width": 100, "height": 80}


def test_logo_score_penalizes_edges_in_expanded_safety_area() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const placement = { x: 42, y: 42, width: 174, height: 54 };"
        "const makeContext = (outerEdges) => ({"
        "canvas: { width: 1088, height: 2240 },"
        "getImageData: (originX, originY, width, height) => {"
        "const data = new Uint8ClampedArray(width * height * 4);"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 0; x < width; x += 1) {"
        "const outsideCore = originY + y >= placement.y + placement.height;"
        "const band = Math.floor((originX + x) / 2) % 2;"
        "const value = outerEdges && outsideCore ? (band ? 245 : 20) : 128;"
        "const index = (y * width + x) * 4;"
        "data[index] = value; data[index + 1] = value; data[index + 2] = value; data[index + 3] = 255;"
        "}"
        "}"
        "return { data };"
        "}"
        "});"
        "const flat = makeContext(false); const edged = makeContext(true);"
        "return {"
        "flat: calculateLogoPlacementScore(flat, flat.canvas, placement),"
        "edged: calculateLogoPlacementScore(edged, edged.canvas, placement),"
        "};"
        "})()"
    )

    assert result["flat"] == 0
    assert result["edged"] > 5


def test_logo_core_edges_are_weighted_more_than_surrounding_edges() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const placement = { x: 42, y: 42, width: 174, height: 54 };"
        "const makeContext = (mode) => ({"
        "canvas: { width: 1088, height: 2240 },"
        "getImageData: (originX, originY, width, height) => {"
        "const data = new Uint8ClampedArray(width * height * 4);"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 0; x < width; x += 1) {"
        "const absoluteX = originX + x; const absoluteY = originY + y;"
        "const inCore = absoluteX >= placement.x && absoluteX < placement.x + placement.width "
        "&& absoluteY >= placement.y && absoluteY < placement.y + placement.height;"
        "const active = mode === 'core' ? inCore : !inCore;"
        "const band = Math.floor(absoluteX / 2) % 2;"
        "const value = active ? (band ? 245 : 20) : 128;"
        "const index = (y * width + x) * 4;"
        "data[index] = value; data[index + 1] = value; data[index + 2] = value; data[index + 3] = 255;"
        "}"
        "}"
        "return { data };"
        "}"
        "});"
        "const core = makeContext('core'); const surrounding = makeContext('surrounding');"
        "return {"
        "core: calculateLogoPlacementScore(core, core.canvas, placement),"
        "surrounding: calculateLogoPlacementScore(surrounding, surrounding.canvas, placement),"
        "};"
        "})()"
    )

    assert result["core"] > result["surrounding"] * 1.5


def test_logo_moves_when_standard_position_has_severe_edge_collision() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const placements = ["
        "{ x: 42, y: 42, width: 174, height: 54 },"
        "{ x: 42, y: 81, width: 174, height: 54 },"
        "];"
        "const ctx = {"
        "canvas: { width: 1088, height: 2240 },"
        "getImageData: (originX, originY, width, height) => {"
        "const data = new Uint8ClampedArray(width * height * 4);"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 0; x < width; x += 1) {"
        "const absoluteX = originX + x; const absoluteY = originY + y;"
        "const collision = absoluteX >= 42 && absoluteX < 216 && absoluteY >= 42 && absoluteY < 81;"
        "const value = collision ? (Math.floor(absoluteX / 2) % 2 ? 245 : 20) : 128;"
        "const index = (y * width + x) * 4;"
        "data[index] = value; data[index + 1] = value; data[index + 2] = value; data[index + 3] = 255;"
        "}"
        "}"
        "return { data };"
        "}"
        "};"
        "const scored = placements.map((placement) => ({"
        "placement, score: calculateLogoPlacementScore(ctx, ctx.canvas, placement),"
        "}));"
        "return { scored, chosen: chooseLogoPlacement(scored) };"
        "})()"
    )

    assert result["scored"][0]["score"] > result["scored"][1]["score"] + 2
    assert result["chosen"] == {"x": 42, "y": 81, "width": 174, "height": 54}


def test_text_and_edge_density_increases_logo_penalty() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const makeContext = (striped) => ({"
        "canvas: { width: 12, height: 12 },"
        "getImageData: (_x, _y, width, height) => {"
        "const data = new Uint8ClampedArray(width * height * 4);"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 0; x < width; x += 1) {"
        "const value = striped && x % 2 ? 245 : 20;"
        "const index = (y * width + x) * 4;"
        "data[index] = value; data[index + 1] = value; data[index + 2] = value; data[index + 3] = 255;"
        "}"
        "}"
        "return { data };"
        "}"
        "});"
        "const region = { x: 0, y: 0, width: 12, height: 12 };"
        "return {"
        "flat: calculateRegionTextEdgePenalty(makeContext(false), region),"
        "striped: calculateRegionTextEdgePenalty(makeContext(true), region),"
        "};"
        "})()"
    )

    assert result["flat"] == 0
    assert result["striped"] > 50


def test_complexity_and_edge_penalties_are_polarity_invariant() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const makeContext = (inverted) => ({"
        "canvas: { width: 12, height: 12 },"
        "getImageData: (_x, _y, width, height) => {"
        "const data = new Uint8ClampedArray(width * height * 4);"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 0; x < width; x += 1) {"
        "const dark = x % 2 === 0;"
        "const value = dark !== inverted ? 20 : 245;"
        "const index = (y * width + x) * 4;"
        "data[index] = value; data[index + 1] = value; data[index + 2] = value; data[index + 3] = 255;"
        "}"
        "}"
        "return { data };"
        "}"
        "});"
        "const region = { x: 0, y: 0, width: 12, height: 12 };"
        "const normal = makeContext(false); const inverted = makeContext(true);"
        "return {"
        "normalComplexity: calculateRegionComplexity(normal, region),"
        "invertedComplexity: calculateRegionComplexity(inverted, region),"
        "normalPenalty: calculateRegionTextEdgePenalty(normal, region),"
        "invertedPenalty: calculateRegionTextEdgePenalty(inverted, region),"
        "};"
        "})()"
    )

    assert result["normalComplexity"] == result["invertedComplexity"]
    assert result["normalPenalty"] == result["invertedPenalty"]


def test_moderate_contrast_penalty_is_polarity_invariant() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const makeContext = (inverted) => ({"
        "canvas: { width: 12, height: 12 },"
        "getImageData: (_x, _y, width, height) => {"
        "const data = new Uint8ClampedArray(width * height * 4);"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 0; x < width; x += 1) {"
        "const base = x % 2 === 0 ? 80 : 190;"
        "const value = inverted ? 255 - base : base;"
        "const index = (y * width + x) * 4;"
        "data[index] = value; data[index + 1] = value; data[index + 2] = value; data[index + 3] = 255;"
        "}"
        "}"
        "return { data };"
        "}"
        "});"
        "const region = { x: 0, y: 0, width: 12, height: 12 };"
        "return {"
        "normal: calculateRegionTextEdgePenalty(makeContext(false), region),"
        "inverted: calculateRegionTextEdgePenalty(makeContext(true), region),"
        "};"
        "})()"
    )

    assert result["normal"] == result["inverted"]


def test_production_size_thin_edges_do_not_alias_by_direction() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const makeContext = (vertical) => ({"
        "canvas: { width: 174, height: 54 },"
        "getImageData: (_x, _y, width, height) => {"
        "const data = new Uint8ClampedArray(width * height * 4);"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 0; x < width; x += 1) {"
        "const stripe = vertical ? Math.floor(x / 2) : Math.floor(y / 2);"
        "const value = stripe % 2 ? 235 : 20;"
        "const index = (y * width + x) * 4;"
        "data[index] = value; data[index + 1] = value; data[index + 2] = value; data[index + 3] = 255;"
        "}"
        "}"
        "return { data };"
        "}"
        "});"
        "const region = { x: 0, y: 0, width: 174, height: 54 };"
        "return {"
        "vertical: calculateRegionTextEdgePenalty(makeContext(true), region),"
        "horizontal: calculateRegionTextEdgePenalty(makeContext(false), region),"
        "};"
        "})()"
    )

    assert result["vertical"] > 40
    assert result["horizontal"] > 40
    assert 0.9 < result["vertical"] / result["horizontal"] < 1.1
