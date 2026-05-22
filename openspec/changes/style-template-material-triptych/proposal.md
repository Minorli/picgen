# Proposal: Style Template + Material Triptych Workflow

## Summary

Add a production workflow for generating three effect images from two required references:

- left reference: style template
- right reference: material/source image

The result should transfer the style template's visual treatment onto the material image while preserving the material subject. The primary transport remains Images API + `gpt-image-2`; Responses API + `gpt-5.5` remains the fallback.
When the style template contains meaningful branding or event elements, such as a `6人游` logo, `2022`, Winter Olympics copy, badges, title blocks, or layout marks, those elements should be integrated into the final material image at natural positions.

## Problem

The current reference workflow accepts one reference image. Real usage often needs at least two references: one image defines the desired style, and another contains the actual material or subject. Users also normally need three candidate outputs for review, not a single image.

## Goals

- Provide two clearly named upload slots in the web UI: `风格模板` and `素材图`.
- Send both images to `/api/edit` in a deterministic order so upstream receives style first and material second.
- Generate three candidate effect images by default for the two-reference workflow.
- Show the three outputs as selectable result candidates.
- Keep single-image generation/editing compatible with existing requests.
- Keep `gpt-image-2` as the primary image model and `gpt-5.5` as the Responses fallback model.

## Non-Goals

- Do not compose the two references into a single side-by-side bitmap before upload.
- Do not add local image compression or preprocessing.
- Do not require users to manually upload files to an external Files page.
- Do not change the normal single-image edit flow into a mandatory two-image workflow.

## Design

### API

`/api/edit` accepts either:

- legacy `image`
- new `images` array with at least one item

For the style-transfer reference workflow, the browser sends:

```json
{
  "mode": "reference",
  "sample_count": 3,
  "images": [
    { "role": "style_template", "...": "..." },
    { "role": "material", "...": "..." }
  ]
}
```

The server validates each image and maps every image to multipart field name `image`, preserving array order. It adds `n=3` for Images API. If an upstream cannot return enough images in one call, PicGen may issue additional one-image attempts and merge the candidates.

`/api/responses-image` accepts the same `images` array, uploads each file to `/v1/files` when possible, and falls back to inline image inputs when file upload fails and inline fallback is allowed.

### Prompt Handling

The browser prepends a style-transfer instruction when both slots are present. It must state that the first image provides style, layout, and meaningful brand/event elements, while the second image is the material subject. It must forbid side-by-side comparison outputs.

### Response

The response remains backward-compatible with the first candidate fields (`saved_image_url`, `image_data_url`, etc.) and additionally includes:

- `images`: ordered candidate payloads
- `sample_count`: requested count
- `candidate_count`: actual returned count

### UI

The Generate panel shows a two-slot reference area. With both slots filled, submission uses the Images Edit transport by default and requests three candidates. The result panel shows the selected candidate in the main preview and the full candidate set as thumbnails.

## Risks

- Some compatible upstreams may ignore `n=3` or reject it on `/v1/images/edits`.
- Multipart field ordering matters for style/material roles.
- Returning three images increases response size and local output storage.

## Mitigations

- Server preserves multipart order and stores role metadata.
- Server can fan out missing candidates with single-image retries.
- UI remains compatible with one-image reference requests.
