---
name: google-ai-ecosystem
description: >
  Use this skill whenever developing with Google's AI ecosystem: Gemini API,
  google-genai SDK, Gemini models (Flash, Pro, Flash-Lite), File API, thinking models,
  Google Search grounding, Google Maps grounding, URL context, Code Execution, embeddings,
  multimodal inputs (audio, image, video, PDF), structured JSON outputs, streaming, async,
  function calling, context caching, or Vertex AI. Trigger when the user mentions: Gemini,
  google-genai, GEMINI_API_KEY, gemini-flash, gemini-pro, thinking_budget, thinking_level,
  File API, generate_content, GenerateContentConfig, ThinkingConfig, google_search tool,
  or any code that imports from google.genai. Also trigger for questions about model
  selection, token counting, safety filters, or multimodal prompting with Google models.
---

# Google AI Ecosystem Skill

Everything Claude Code needs to build with the **Google Gen AI SDK** correctly and
efficiently — no trial-and-error on patterns, versions, or API quirks.

---

## 1. SDK Setup

```bash
pip install -U "google-genai>=1.51.0"
# 1.51+ required for Gemini 3 thinking_level support
```

```python
from google import genai
from google.genai import types
import os

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
```

**Never hardcode API keys.** Use environment variables or a `.env` + `python-dotenv`.

---

## 2. Model Selection Guide

| Use Case | Recommended Model | Notes |
|---|---|---|
| Fast general tasks | `gemini-3-flash-preview` | Latest generation, good default |
| Balanced speed/quality | `gemini-2.5-flash` | Stable, cost-effective |
| Best reasoning | `gemini-2.5-pro` | Slower, most accurate |
| High-volume / cheapest | `gemini-2.5-flash-lite` | Minimal cost |
| Cutting-edge Pro | `gemini-3.1-pro-preview` | Most capable, no free tier |

**All available model IDs:**
- `gemini-2.5-flash-lite`
- `gemini-2.5-flash`
- `gemini-2.5-pro`
- `gemini-3-flash-preview`
- `gemini-3.1-flash-lite-preview`
- `gemini-3.1-pro-preview`

---

## 3. Core Patterns

### 3.1 Text Generation

```python
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Your prompt here",
    config=types.GenerateContentConfig(
        system_instruction="You are a helpful assistant.",
        temperature=0.4,
        top_p=0.95,
    )
)
print(response.text)
```

### 3.2 Structured JSON Output

Always instruct the model explicitly — no markdown, no preamble:

```python
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=f"Extract data from: {text}\nReturn ONLY valid JSON. No markdown. No explanation.",
    config=types.GenerateContentConfig(temperature=0.2)
)

import json
clean = response.text.strip().removeprefix("```json").removesuffix("```").strip()
data = json.loads(clean)
```

### 3.3 File API — Audio, PDF, Images

```python
# Upload any file (audio, pdf, image, video)
file_ref = client.files.upload(
    file="audio.ogg",
    config=types.FileDict(display_name="my_file")
)

# Use in a multimodal prompt
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[file_ref, "Transcribe this audio."]
)

# File API limits:
# - Max size: 2 GB per file
# - Max storage: 20 GB per project
# - Files expire after 2 days (cannot be downloaded back)
```

**Supported audio formats:** mp3, wav, ogg, m4a, aac, flac, webm, opus

### 3.4 Thinking Models — Control

All Gemini 2.5+ models think adaptively by default. Override when needed:

```python
# Disable thinking — faster/cheaper (Flash/Flash-Lite ONLY, NOT Pro)
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0)
)

# Fixed thinking budget
# Flash/Flash-Lite: 0–24576 | Pro: 128–32768
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=4096)
)

# Gemini 3 Pro: use thinking_level (easier than budget)
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_level="high")  # low | medium | high
)

# Inspect thought process (great for debugging)
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(include_thoughts=True)
)
for part in response.parts:
    if part.thought:
        print("THOUGHT:", part.text)
    else:
        print("ANSWER:", part.text)
```

**When to think:**
- Simple transcription / formatting → `thinking_budget=0`
- Structured data extraction → default (adaptive)
- Complex reasoning / edge cases → `thinking_budget=4096+`

### 3.5 Streaming

```python
for chunk in client.models.generate_content_stream(
    model="gemini-2.5-flash",
    contents="Your prompt"
):
    print(chunk.text, end="", flush=True)
```

### 3.6 Async

```python
async def call_gemini(prompt: str) -> str:
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text
```

### 3.7 Multi-turn Chat

```python
chat = client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(system_instruction="Be concise.")
)

r1 = chat.send_message("Hello, I need help.")
r2 = chat.send_message("What did I just say?")  # full history is kept automatically
```

### 3.8 Google Search Grounding

```python
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="What are the latest job market trends in Brazil?",
    config={"tools": [{"google_search": {}}]},
)

# Access grounding metadata
meta = response.candidates[0].grounding_metadata
print(meta.web_search_queries)
print([chunk.web.title for chunk in meta.grounding_chunks])
```

> ⚠️ Cannot combine grounding + structured JSON output in the same call.

### 3.9 Google Maps Grounding

```python
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Find coffee shops within 20 min walk",
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_maps=types.GoogleMaps())],
        tool_config=types.ToolConfig(
            retrieval_config=types.RetrievalConfig(
                lat_lng=types.LatLng(latitude=-23.5505, longitude=-46.6333)  # São Paulo
            )
        ),
    ),
)
```

### 3.10 URL Context

```python
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part(uri="https://example.com/article"),
        "Summarize this page."
    ]
)
```

### 3.11 Function Calling

```python
get_weather = types.FunctionDeclaration(
    name="get_weather",
    description="Returns weather for a city",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"]
    }
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="What's the weather in São Paulo?",
    config=types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[get_weather])]
    )
)

if response.candidates[0].content.parts[0].function_call:
    call = response.candidates[0].content.parts[0].function_call
    print(call.name, call.args)  # "get_weather", {"city": "São Paulo"}
```

### 3.12 Code Execution Tool

```python
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Calculate the first 20 prime numbers and plot them.",
    config=types.GenerateContentConfig(
        tools=[types.Tool(code_execution=types.ToolCodeExecution)]
    )
)

for part in response.candidates[0].content.parts:
    if part.text:                  print("Text:", part.text)
    if part.executable_code:       print("Code:", part.executable_code.code)
    if part.code_execution_result: print("Result:", part.code_execution_result.output)
    if part.inline_data:           print("Image data available")
```

### 3.13 Embeddings

```python
result = client.models.embed_content(
    model="text-embedding-004",
    contents=["Text to embed", "Another text"],
)
vectors = [e.values for e in result.embeddings]
```

### 3.14 Token Counting (estimate cost before calling)

```python
count = client.models.count_tokens(
    model="gemini-2.5-flash",
    contents=[file_ref, "Your prompt"]
)
print(f"Total tokens: {count.total_tokens}")
```

### 3.15 Safety Filters

```python
config = types.GenerateContentConfig(
    safety_settings=[
        types.SafetySetting(
            category="HARM_CATEGORY_HARASSMENT",
            threshold="BLOCK_ONLY_HIGH"
        )
    ]
)
```

---

## 4. Error Handling

```python
from google.api_core import exceptions as google_exceptions
import time, json

def call_with_retry(prompt: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return response.text
        except google_exceptions.ResourceExhausted:
            wait = 2 ** attempt * 10
            print(f"Rate limit — waiting {wait}s")
            time.sleep(wait)
        except google_exceptions.InvalidArgument as e:
            raise ValueError(f"Bad request: {e}")
    raise RuntimeError("Max retries exceeded")
```

---

## 5. Vertex AI vs Developer API

Same SDK, same code — only the client changes:

```python
# Developer API (prototyping, free tier available)
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Vertex AI (production, GCP billing)
client = genai.Client(
    vertexai=True,
    project="your-gcp-project-id",
    location="us-central1"
)
```

---

## 6. Key Gotchas

1. **`google-genai>=1.51.0`** — required for Gemini 3 `thinking_level`.
2. **`thinking_budget=0` only on Flash/Flash-Lite** — Pro models cannot disable thinking.
3. **File API files expire in 2 days** — never persist `file_ref` objects.
4. **JSON output**: always strip ` ```json ` fences before `json.loads()`.
5. **Temperature 0.1–0.3** for structured outputs; **0.7–1.0** for creative text.
6. **Grounding + structured output** cannot be used in the same API call.
7. **Multimodal**: pass as list `[file_ref, "text"]`, never concatenate to a string.
8. **Async**: use `client.aio.models.generate_content(...)` — don't wrap sync in `asyncio.run()`.

---

## 7. Reference Files

- `references/models.md` — Model capabilities, context windows, thinking budget limits
