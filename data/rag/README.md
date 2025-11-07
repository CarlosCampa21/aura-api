# Contenido para RAG

Qué va aquí:
- Solo texto estructurado en Markdown canónico (`.md`).
- Dividido en secciones/chunks lógicos con `#`, `##`, `###`.
- Sin PDFs, imágenes ni binarios.

Convenciones:
- Nombres en kebab-case, sin espacios. Ej: `calendario-escolar-2025.md`.
- Español consistente; títulos claros en `#` y subsecciones en `##/###`.
- Un documento por tema; si es largo, separa en varios archivos.

Ejemplos de archivos:
- `calendario-escolar-2025.md`
- `reglamento-pp.md`
- `mision-vision-ids.md`
- `horario-base-dasc.md`

Sugerencia de chunking:
- Prefiere secciones semánticas (H2/H3) en lugar de cortar por tamaño fijo.
- Si necesitas partir archivos, usa sufijos: `reglamento-pp-1.md`, `reglamento-pp-2.md`.

Plantilla sugerida:

```markdown
# Título del documento

## Resumen
Breve síntesis (3–5 líneas) para orientar el RAG.

## Sección 1
Contenido claro, sin ruido (tablas simples en Markdown si aplica).

## Sección 2
...

## FAQs
- P: ...
  R: ...
```

