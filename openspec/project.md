# PicGen OpenSpec

## Purpose

PicGen is a local web console and proxy for OpenAI-compatible image generation and editing. The primary workflow uses OpenAI Images API with `gpt-image-2`; Responses API with `gpt-5.5` is kept as a compatibility fallback for upstreams that cannot reliably handle Images Edit.

## Conventions

- Changes that alter user-facing image workflows should include an OpenSpec change under `openspec/changes/<change-id>/`.
- Each change should include `proposal.md`, `tasks.md`, and spec deltas under `specs/`.
- Runtime behavior must stay testable through FastAPI route tests and front-end syntax checks.

## Current Guarantees

- Default image model: `gpt-image-2`.
- Default Responses fallback model: `gpt-5.5`.
- Image inputs are sent at original quality; PicGen does not compress user-provided reference images.
- Generated output images may be saved locally with metadata for user download and follow-up editing.
