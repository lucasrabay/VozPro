# Gemini Models — Reference

## Current Available Models (2026)

### Gemini 3 Generation (newest)
| Model ID | Type | Best For |
|---|---|---|
| `gemini-3-flash-preview` | Flash | Fast general tasks, VozPro default |
| `gemini-3.1-flash-lite-preview` | Flash Lite | High-volume, budget tasks |
| `gemini-3.1-pro-preview` | Pro | Most complex reasoning |

### Gemini 2.5 Generation (stable)
| Model ID | Type | Best For |
|---|---|---|
| `gemini-2.5-flash` | Flash | Balanced speed/quality |
| `gemini-2.5-flash-lite` | Flash Lite | Cheapest, simplest tasks |
| `gemini-2.5-pro` | Pro | Best reasoning, complex extraction |

## Thinking Budget Limits
- **Flash / Flash-Lite**: `thinking_budget` from `0` (disabled) to `24576`
- **Pro**: `thinking_budget` from `128` to `32768` (cannot disable thinking)
- **Gemini 3 Pro**: use `thinking_level` (`low` / `medium` / `high`) instead of budget

## Multimodal Support
All models support: text, image, audio, video, PDF (via File API)

## Context Windows
- Gemini 2.5 Flash: 1M tokens input
- Gemini 2.5 Pro: 2M tokens input
- Gemini 3 models: see official docs for latest limits
