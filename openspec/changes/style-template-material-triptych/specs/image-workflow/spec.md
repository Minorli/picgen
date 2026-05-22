## ADDED Requirements

### Requirement: Dual Reference Style Transfer

The system SHALL support a style-transfer generation workflow with two explicit reference images: a style template and a material/source image.

#### Scenario: User submits style template and material image

- **GIVEN** the user has uploaded a style template image
- **AND** the user has uploaded a material image
- **WHEN** the user starts generation
- **THEN** the client SHALL submit both images to the edit transport
- **AND** the style template SHALL be ordered before the material image
- **AND** the prompt SHALL instruct the model to apply style from the first image to the subject of the second image
- **AND** the prompt SHALL instruct the model to preserve and naturally place meaningful branding or event elements from the template, including logos, year text, badges, title blocks, and event copy.

### Requirement: Three Candidate Outputs

The system SHALL request three output candidates for the dual-reference style-transfer workflow by default.

#### Scenario: Upstream returns three candidates

- **GIVEN** the request asks for three candidates
- **WHEN** the upstream returns three images
- **THEN** PicGen SHALL persist all returned images
- **AND** the response SHALL include all candidates in order
- **AND** the first candidate SHALL remain exposed through the existing single-image response fields for compatibility.

#### Scenario: Upstream returns fewer candidates

- **GIVEN** the request asks for three candidates
- **WHEN** the upstream returns fewer than three images
- **THEN** PicGen SHALL return the available candidates
- **AND** MAY issue additional single-image attempts to fill the missing candidates.

### Requirement: Backward Compatibility

The system SHALL keep existing single-image generation and edit flows operational.

#### Scenario: Legacy edit request sends `image`

- **GIVEN** a request contains the legacy `image` payload
- **WHEN** the edit endpoint receives it
- **THEN** the endpoint SHALL process it as a single-image edit request
- **AND** the response SHALL include the same first-image compatibility fields as before.

### Requirement: Responses Fallback Parity

The Responses fallback SHALL support the same ordered image references as the Images Edit workflow.

#### Scenario: Dual references use Responses fallback

- **GIVEN** the user has selected Responses fallback
- **AND** style template and material references are present
- **WHEN** the client submits the request
- **THEN** PicGen SHALL upload both files to the sibling Files endpoint when possible
- **AND** SHALL construct the Responses input with both images in style-template then material order
- **AND** SHALL use `gpt-5.5` unless the user explicitly overrides the fallback model.
