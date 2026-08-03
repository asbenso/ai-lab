<!-- source: https://privacy.anthropic.com/en/articles/10023580-anthropic-s-data-handling-practices -->

# Anthropic API data handling

Anthropic does not use prompts or completions submitted via the API to train its models, unless the customer explicitly opts in. Inputs are retained for up to 30 days for safety review and are stored encrypted in transit and at rest.

## Trust and Safety

A separate Trust and Safety team may review flagged content. Reviews focus on classification of policy-relevant content; the team does not contribute the content to training data.

## Zero data retention

Enterprise customers can request a Zero Data Retention (ZDR) configuration in which prompts and completions are not retained beyond the duration of the request. ZDR requires a separate agreement and is reviewed case by case.

## Comparison

Compared with OpenAI's default API retention (30 days, no training) and Google's Gemini for Vertex (no training by default for enterprise tier), Anthropic sits in the same category. Differences appear in retention defaults, opt-in mechanisms for fine-tuning, and the surface area covered by Trust and Safety review.
