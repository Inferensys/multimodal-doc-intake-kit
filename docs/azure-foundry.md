# Azure Foundry Integration

This repository uses Azure in three roles:

1. Azure Document Intelligence for OCR, structure extraction, and layout Markdown
2. Azure OpenAI / Foundry deployments for profile-specific field normalization
3. Azure OpenAI embeddings for retrieval vectors

## Recommended Deployment Set

Minimum useful set:

- `gpt-5-mini`
- `text-embedding-3-small`

Recommended set for this repository:

- `gpt-5-mini`
- `gpt-5.4`
- `text-embedding-3-small`

Optional additions:

- `mistral-document-ai-2512`
  - useful if you want to compare Document Intelligence against a second document-specialized parser
- `Cohere-rerank-v4.0-fast`
  - useful when the project grows into retrieval/reranking benchmarks

## Deploy Missing Models

Example embedding deployment:

```bash
az cognitiveservices account deployment create \
  --resource-group "<resource-group>" \
  --name "<foundry-resource-name>" \
  --deployment-name "text-embedding-3-small" \
  --model-name "text-embedding-3-small" \
  --model-version "1" \
  --model-format "OpenAI" \
  --sku-name "GlobalStandard" \
  --sku-capacity 10
```

Check current deployments:

```bash
az cognitiveservices account deployment list \
  --resource-group "<resource-group>" \
  --name "<foundry-resource-name>" \
  -o table
```

Check available models on the resource:

```bash
az cognitiveservices account list-models \
  --resource-group "<resource-group>" \
  --name "<foundry-resource-name>" \
  -o table
```

## Environment Variables

```bash
export DOC_INTAKE_PROVIDER=azure
export AZURE_DOCINTELLIGENCE_ENDPOINT="https://<resource>.cognitiveservices.azure.com/"
export AZURE_DOCINTELLIGENCE_API_KEY="<key>"
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
export AZURE_OPENAI_API_KEY="<key>"
export AZURE_OPENAI_API_VERSION="2025-04-01-preview"
export AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-5-mini"
export AZURE_OPENAI_REASONING_DEPLOYMENT="gpt-5.4"
export AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-small"
```

## Execution Path In This Repository

The live path in [`src/multimodal_doc_intake_kit/azure_backend.py`](../src/multimodal_doc_intake_kit/azure_backend.py) does the following:

- submits the source document to `prebuilt-layout`
- requests Markdown output
- sends the layout output plus profile instructions to the chat deployment
- validates the returned fields into the local Pydantic contracts
- chunks the document
- creates embeddings for each chunk

The implementation is intentionally conservative:

- it keeps OCR/layout separate from schema normalization
- it keeps embeddings separate from extraction
- it preserves a deterministic mode for tests and contract stability

## When To Use A Different Model

Use `gpt-5.4` instead of `gpt-5-mini` when you need:

- cross-page adjudication across large packets
- explicit review note generation
- richer resolution of ambiguous handwritten or low-quality scans
- harder post-processing logic over extracted evidence

Use `text-embedding-3-large` instead of `text-embedding-3-small` when:

- retrieval quality matters more than cost/latency
- chunk count is small
- you are benchmarking downstream search quality

Keep `gpt-4o` out of new setups here. It still works for many workloads, but it is not the model this repo should lead with.

## Google Cloud Equivalent

Closest equivalent pipeline:

- OCR/layout: Google Document AI
- normalization: `gemini-2.5-pro`
- embeddings: `gemini-embedding-001`

Suggested mapping:

```text
Azure Document Intelligence     -> Google Document AI
gpt-5-mini / gpt-5.4            -> Gemini 2.5 Pro
text-embedding-3-small          -> gemini-embedding-001
```

## Generic OpenAI-Compatible Equivalent

If you are not on Azure or Google Cloud, keep the architecture split:

- provider A: OCR/layout
- provider B: schema normalization with structured outputs or tool calling
- provider C: embeddings

That separation is more robust than asking one multimodal model to do all three jobs in one shot.
