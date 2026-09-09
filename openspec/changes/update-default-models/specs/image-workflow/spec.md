## MODIFIED Requirements

### Requirement: Current default models

Default image creation SHALL use gpt-image-2.5-sunburst. Responses SHALL use gpt-6-astra and explicitly select the image-generation tool model. Existing custom model settings SHALL remain available.

#### Scenario: Existing browser uses old defaults

- WHEN settings or workspace forms containing the previous default models load
- THEN those defaults use the current server model configuration
- AND historical result records remain unchanged.
