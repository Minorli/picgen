from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]


def _run_logo_policy(expression: str) -> object:
    script = f"""
import {{
  calculateLogoPlacementScore,
  calculateOfficialLogoPixelMatch,
  calculateRegionComplexity,
  calculateRegionTextEdgePenalty,
  chooseLogoPlacement,
  createLogoPreservationDiagnostic,
  expandLogoSafetyRegion,
  scaleLogoDetectionPlacements,
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


def test_official_logo_pixel_match_accepts_lossless_and_small_color_drift() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const logo = { data: Uint8ClampedArray.from(["
        "10,20,30,255, 40,160,90,255, 250,250,250,0, 90,80,70,240"
        "]) };"
        "const exact = { data: Uint8ClampedArray.from(["
        "10,20,30,255, 40,160,90,255, 1,2,3,255, 90,80,70,255"
        "]) };"
        "const drift = { data: Uint8ClampedArray.from(["
        "26,5,48,255, 58,143,108,255, 1,2,3,255, 90,80,70,255"
        "]) };"
        "return {"
        "exact: calculateOfficialLogoPixelMatch(exact, logo),"
        "drift: calculateOfficialLogoPixelMatch(drift, logo),"
        "};"
        "})()"
    )

    assert result["exact"] == {"score": 1, "matchedPixels": 2, "comparedPixels": 2}
    assert result["drift"] == {"score": 1, "matchedPixels": 2, "comparedPixels": 2}


def test_official_logo_pixel_match_accepts_small_resampling_shift() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const width = 7; const height = 3;"
        "const logo = new Uint8ClampedArray(width * height * 4);"
        "const base = new Uint8ClampedArray(width * height * 4);"
        "for (let pixel = 0; pixel < width * height; pixel += 1) {"
        "base[pixel * 4] = 230; base[pixel * 4 + 1] = 230; base[pixel * 4 + 2] = 230; base[pixel * 4 + 3] = 255;"
        "}"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 2; x <= 4; x += 1) {"
        "const logoIndex = (y * width + x) * 4; const baseIndex = (y * width + x + 1) * 4;"
        "const red = 20 + x * 31 + y * 7; const green = 45 + x * 13 + y * 29; const blue = 70 + x * 17 + y * 11;"
        "logo[logoIndex] = red; logo[logoIndex + 1] = green; logo[logoIndex + 2] = blue; logo[logoIndex + 3] = 255;"
        "base[baseIndex] = red; base[baseIndex + 1] = green; base[baseIndex + 2] = blue;"
        "}"
        "}"
        "return calculateOfficialLogoPixelMatch({ data: base, width, height }, { data: logo, width, height });"
        "})()"
    )

    assert result == {"score": 1, "matchedPixels": 9, "comparedPixels": 9}


def test_logo_detection_scales_real_official_logo_with_result_canvas() -> None:
    source_size = (1536, 2048)
    result_size = (1024, 1365)
    source_placement = {"x": 42, "y": 42, "width": 220, "height": 68}
    expected_placement = {"x": 28, "y": 28, "width": 147, "height": 45}

    with Image.open(ROOT_DIR / "static" / "6renyou.png") as source_logo:
        logo = source_logo.convert("RGBA")
        alpha_bounds = logo.getchannel("A").getbbox()
        assert alpha_bounds is not None
        logo = logo.crop(alpha_bounds)
        scaled_source_logo = logo.resize(
            (source_placement["width"], source_placement["height"]),
            Image.Resampling.LANCZOS,
        )
        source_canvas = Image.new("RGBA", source_size, (232, 236, 234, 255))
        source_canvas.alpha_composite(scaled_source_logo, (source_placement["x"], source_placement["y"]))
        result_canvas = source_canvas.resize(result_size, Image.Resampling.LANCZOS)
        result_region = result_canvas.crop(
            (
                expected_placement["x"],
                expected_placement["y"],
                expected_placement["x"] + expected_placement["width"],
                expected_placement["y"] + expected_placement["height"],
            )
        )
        expected_logo = logo.resize(
            (expected_placement["width"], expected_placement["height"]),
            Image.Resampling.LANCZOS,
        )

    result_region_b64 = base64.b64encode(result_region.tobytes()).decode("ascii")
    expected_logo_b64 = base64.b64encode(expected_logo.tobytes()).decode("ascii")
    result = _run_logo_policy(
        "(() => {"
        f"const placements = scaleLogoDetectionPlacements([{json.dumps(source_placement)}], "
        f"{{ width: {source_size[0]}, height: {source_size[1]} }}, "
        f"{{ width: {result_size[0]}, height: {result_size[1]} }});"
        "const placement = placements[0];"
        f"const base = Uint8ClampedArray.from(Buffer.from('{result_region_b64}', 'base64'));"
        f"const logo = Uint8ClampedArray.from(Buffer.from('{expected_logo_b64}', 'base64'));"
        "return { placement, match: calculateOfficialLogoPixelMatch("
        "{ data: base, width: placement.width, height: placement.height },"
        "{ data: logo, width: placement.width, height: placement.height },"
        ") };"
        "})()"
    )

    assert result["placement"] == expected_placement
    assert result["match"]["comparedPixels"] >= 128
    assert result["match"]["score"] >= 0.9


def test_logo_detection_uses_width_ratio_for_nonuniform_canvas_drift() -> None:
    result = _run_logo_policy(
        "scaleLogoDetectionPlacements("
        "[{ x: 42, y: 42, width: 220, height: 68 }], "
        "{ width: 1536, height: 2048 }, "
        "{ width: 1024, height: 1200 })"
    )

    assert result == [{"x": 28, "y": 28, "width": 147, "height": 45}]


def test_logo_preservation_diagnostic_contains_only_safe_decision_evidence() -> None:
    result = _run_logo_policy(
        "createLogoPreservationDiagnostic("
        "{ score: 0.934567, matchedPixels: 842, comparedPixels: 901 }, 0.9, "
        "{ generatedImageId: 42, candidateIndex: 2, savedImagePath: 'outputs/20260712/result.png' })"
    )

    assert result == {
        "decision": "preserve",
        "match_rate": 0.9346,
        "matched_pixels": 842,
        "compared_pixels": 901,
        "threshold": 0.9,
        "basis": "official_logo_pixel_match",
        "generated_image_id": 42,
        "candidate_index": 2,
        "saved_image_path": "outputs/20260712/result.png",
    }
    assert not {"api_key", "token", "password", "image_data"}.intersection(result)


def test_official_logo_pixel_match_rejects_matching_colors_outside_local_radius() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const width = 15; const height = 3;"
        "const logo = new Uint8ClampedArray(width * height * 4);"
        "const base = new Uint8ClampedArray(width * height * 4);"
        "for (let pixel = 0; pixel < width * height; pixel += 1) {"
        "base[pixel * 4] = 230; base[pixel * 4 + 1] = 230; base[pixel * 4 + 2] = 230; base[pixel * 4 + 3] = 255;"
        "}"
        "for (let y = 0; y < height; y += 1) {"
        "for (let x = 2; x <= 4; x += 1) {"
        "const logoIndex = (y * width + x) * 4; const baseIndex = (y * width + x + 8) * 4;"
        "const red = 20 + x * 31 + y * 7; const green = 45 + x * 13 + y * 29; const blue = 70 + x * 17 + y * 11;"
        "logo[logoIndex] = red; logo[logoIndex + 1] = green; logo[logoIndex + 2] = blue; logo[logoIndex + 3] = 255;"
        "base[baseIndex] = red; base[baseIndex + 1] = green; base[baseIndex + 2] = blue;"
        "}"
        "}"
        "return calculateOfficialLogoPixelMatch({ data: base, width, height }, { data: logo, width, height });"
        "})()"
    )

    assert result == {"score": 0, "matchedPixels": 0, "comparedPixels": 9}


def test_official_logo_pixel_match_rejects_unrelated_or_invalid_regions() -> None:
    result = _run_logo_policy(
        "(() => {"
        "const logo = { data: Uint8ClampedArray.from(["
        "10,20,30,255, 40,160,90,255, 250,250,250,0"
        "]) };"
        "const unrelated = { data: Uint8ClampedArray.from(["
        "200,210,220,255, 180,20,30,255, 1,2,3,255"
        "]) };"
        "return {"
        "unrelated: calculateOfficialLogoPixelMatch(unrelated, logo),"
        "invalid: calculateOfficialLogoPixelMatch({ data: new Uint8ClampedArray(4) }, logo),"
        "};"
        "})()"
    )

    assert result["unrelated"] == {"score": 0, "matchedPixels": 0, "comparedPixels": 2}
    assert result["invalid"] == {"score": 0, "matchedPixels": 0, "comparedPixels": 0}


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
