RAG CLI (wrappers finos)

Objetivo: exponer desde línea de comandos las 3 operaciones básicas del RAG
del backend sin duplicar lógica.

Requisitos
- Estar en el directorio `aura-api/` para que Python resuelva el paquete `app`.
- Variables de entorno en `.env` (MongoDB, OpenAI embeddings, etc.).

Comandos
- Ingestar un documento por id:
  - `python -m rag.ingest --doc-id <id>`
- Ingestar todos los activos (hasta 100):
  - `python -m rag.ingest --all --limit 100`
- Recuperar (KNN) sin redacción, para inspeccionar evidencia:
  - `python -m rag.retrieve --q "pregunta" --k 5`
- Responder con RAG (redacción breve con LLM):
  - `python -m rag.answer --q "pregunta" --k 5`

Notas
- Los embeddings se almacenan en MongoDB Atlas Vector Search (no en disco).
- Los documentos a ingestar deben existir en `library_doc` con `url` y
  `content_type`. Usa la API del backend o scripts propios para registrar.

