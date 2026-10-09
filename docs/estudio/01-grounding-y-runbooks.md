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

`RunbookLibrary` ajusta TF-IDF sobre el **título y los síntomas** de cada runbook
—la firma reconocible del incidente—, y empareja el incidente por coseno. Fíjate
en lo que **no** se indexa: las descripciones de los pasos. Esas son el remedio
("rotar los logs", "identificar el proceso más caliente"), y meterlas en el corpus
hacía que incidentes no relacionados chocaran por verbos operativos (una pregunta
sobre la "rotación" de guardias emparejaba con el runbook de rotación de logs). Un
incidente se describe por **qué le pasa**, no por cómo se arregla, así que el
emparejamiento síntoma-con-síntoma es más preciso y con menos ruido.

Además el vectorizador es un `FeatureUnion` de una vista de palabra (1–2 gramas) y
una de carácter (`char_wb` 3–5 gramas). Los n-gramas de carácter emparejan *dentro*
de las palabras, así que la forma en que un operador escribe ("503s" por "503")
encuentra igual el runbook correcto; un modelo solo de palabras lo fallaba.

El match trae una **puntuación**. En esta biblioteca un incidente del dominio
puntúa ~0,35 o más y uno fuera de dominio ~0,26 o menos, así que
`OP_MIN_CONFIDENCE` (0,30) cae en el hueco. Si está por debajo, el plan marca
`needs_human_triage`: devuelve igual el mejor intento (puede ser una pista útil)
pero avisa de que no está seguro de haber encontrado el runbook correcto, para que
decida un humano. Dos matices precisos: un incidente del dominio descrito de forma
**muy escueta** (una sola palabra en común) puede caer por debajo y se deriva —el
resultado seguro—; y el umbral **no es el mecanismo de seguridad**, solo califica
el *match*. Ningún paso que cambie el sistema se ejecuta por confianza alta: de eso
se encarga la aprobación humana. Es la misma postura que otros proyectos de
recuperación: mostrar la incertidumbre, no esconderla.

## Para fijar la idea

- Un LLM suelto puede inventar comandos peligrosos; eso debe ser imposible.
- El plan se funda en runbooks vetados; el LLM solo resume, no añade pasos.
- El emparejamiento es síntoma-con-síntoma (no con los pasos) y robusto a la
  forma de escribir (palabra + carácter).
- La confianza baja se marca (needs_human_triage), no se disfraza; y el umbral
  califica el match, no sustituye a la aprobación humana.

El motor de recuperación no se queda en los runbooks de ejemplo: está **medido
sobre 3252 incidentes reales** (dataset `Loukh1/IT-incidents`), enrutando cada
ticket a su servicio. Cómo se mide eso —con fórmulas, validación cruzada y un
control— está en el capítulo
[04-evaluacion-datos-reales.md](04-evaluacion-datos-reales.md).
