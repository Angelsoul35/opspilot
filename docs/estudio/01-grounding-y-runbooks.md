# 01 — Grounding y runbooks

## El peligro de un LLM suelto en un incidente

Un LLM al que preguntas "¿cómo arreglo esta caída?" produce con gusto comandos
plausibles... incluidos los que están mal, son peligrosos o están inventados
(alucinados). Durante un incidente, actuar sobre un `kubectl delete` o un
`DROP TABLE` inventado es justo el fallo que debe ser **imposible**.

## La decisión: fundar el consejo en runbooks

Un **runbook** es un procedimiento vetado: un título, los síntomas y una lista de
pasos (algunos con comando, algunos marcados como *acción* porque cambian el
sistema). opspilot:

1. **Recupera** el runbook más relevante al incidente (TF-IDF + similitud coseno),
   con una puntuación de confianza.
2. **Construye el plan a partir de ese runbook**: los pasos salen del runbook, no
   del modelo.
3. Al LLM le da el incidente y el runbook y le pide **solo** un resumen de triage
   de dos frases, diciéndole explícitamente que no invente pasos. Y
   estructuralmente, su salida va al campo `summary`, nunca a `steps`.

Resultado: **un comando solo puede aparecer en un plan si está en un runbook que
un humano escribió y revisó.** El LLM mejora la lectura (un triage conciso) sin
que se confíe en él para decidir qué hacer.

## La recuperación y la confianza

`RunbookLibrary` ajusta TF-IDF sobre el título, los síntomas y las descripciones
de pasos de cada runbook, y empareja el incidente por coseno. El match trae una
**puntuación**. Si está por debajo de `OP_MIN_CONFIDENCE`, el plan marca
`needs_human_triage`: devuelve igual el mejor intento (puede ser una pista útil)
pero avisa de que no está seguro de haber encontrado el runbook correcto, para que
decida un humano. Es la misma postura que otros proyectos de recuperación: mostrar
la incertidumbre, no esconderla.

## Para fijar la idea

- Un LLM suelto puede inventar comandos peligrosos; eso debe ser imposible.
- El plan se funda en runbooks vetados; el LLM solo resume, no añade pasos.
- La confianza baja se marca (needs_human_triage), no se disfraza.
