# Guía de estudio — opspilot

Esta carpeta es una guía en español para entender opspilot a fondo. El código, los
comentarios y la documentación técnica están en inglés (nivel B2) a propósito,
para que el proyecto sea creíble y sirva para practicar. Esta guía explica el "por
qué" de cada decisión en tu idioma.

## Orden sugerido de lectura

1. **[01-grounding-y-runbooks.md](01-grounding-y-runbooks.md)** — por qué el
   consejo se funda en runbooks vetados y nunca se inventa, y la recuperación.
2. **[02-aprobacion-humana.md](02-aprobacion-humana.md)** — el gate humano para los
   pasos que cambian el sistema, por qué solo dry-run, y por qué no ejecuta.
3. **[03-preguntas-de-entrevista.md](03-preguntas-de-entrevista.md)** — preguntas
   típicas y cómo responderlas con seguridad.
4. **[04-evaluacion-datos-reales.md](04-evaluacion-datos-reales.md)** — cómo
   demostramos el motor de recuperación sobre 3252 incidentes reales: métricas y
   fórmulas (accuracy, top-k, macro-F1), sobre/subajuste y el gap, validación
   cruzada y held-out, un ejemplo trabajado con los números medidos, y el control.

## Resumen en una frase

opspilot tria un incidente contra una biblioteca de runbooks: recupera el runbook
más relevante (TF-IDF), escribe un resumen de triage fundamentado en él (LLM con
respaldo extractivo), y expone sus pasos con cada paso que cambia el sistema
bloqueado tras aprobación humana explícita y nunca ejecutado más allá de un dry-run.
