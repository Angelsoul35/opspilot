# 03 — Preguntas de entrevista

Preguntas típicas sobre este proyecto y cómo responderlas con seguridad.
Practica diciéndolas en voz alta en inglés también.

## Sobre el enfoque

**¿Por qué fundar el consejo en runbooks y no dejar que el LLM proponga pasos?**
Porque durante un incidente un paso inventado puede ser destructivo. Recupero el
runbook relevante y construyo el plan con **sus** pasos; al LLM le pido solo un
resumen de triage, y su salida va al campo `summary`, nunca a `steps`. Así un
comando solo aparece si está en un runbook revisado por humanos.

**¿Qué pasa si ningún runbook encaja?**
La recuperación devuelve el mejor match con su confianza; si está por debajo del
umbral, marco `needs_human_triage`. Devuelvo el mejor intento como pista pero aviso
de que no estoy seguro, para que decida un humano. No disfrazo la incertidumbre.

## Sobre la seguridad

**¿Cómo evitas que se ejecute algo peligroso?**
Con un gate human-in-the-loop: un paso que cambia el sistema corre solo si un
humano aprobó su índice; si no, queda `awaiting_approval`. Y el gate hace solo
dry-run, nunca un comando real. La regla son pocas líneas, legibles y confiables.

**¿Por qué opspilot no ejecuta los comandos?**
Porque ejecutar de verdad necesita credenciales de producción, auditoría y RBAC:
un ejecutor crítico aparte. Dejándolo fuera, el asistente nunca tiene las llaves de
producción; propone y hace cumplir la aprobación, y entrega el plan aprobado a quien
las tenga. Separar aconsejar de ejecutar es más seguro.

**¿Qué diferencia un paso advisory de uno que requiere aprobación?**
`requires_approval` es verdadero si y solo si el paso es una acción (cambia el
sistema) con comando. Los diagnósticos de solo lectura son advisory y no bloquean.

## Sobre la evaluación

**¿Cómo demuestras que la recuperación funciona, y no solo sobre tus ejemplos?**
La mido sobre 3252 incidentes reales (`Loukh1/IT-incidents`): construyo un runbook
por servicio con sus tickets de entrenamiento y enruto tickets no vistos a su
servicio real. Reporto exactitud top-1/top-3 y macro-F1 con validación cruzada
estratificada y una partición held-out, contra las referencias de mayoría y azar.
Sobre los 12 servicios más frecuentes sale ~0.89 top-1 (~0.98 top-3, macro-F1
~0.92).

**¿Y cómo sabes que no está sobreajustado ni que el número es un artefacto?**
Por dos cosas. El **gap** entre entrenamiento y prueba es ≈ 0 (train 0.898 vs test
0.891) con desviación 0.008 entre particiones: generaliza, no memoriza; el
veredicto es bien ajustado. Y un **control de etiquetas barajadas** —reconstruir
los runbooks con pares (texto, servicio) revueltos— hace que la exactitud colapse a
~0.08 (azar), lo que prueba que el acierto vive en el mapeo texto→servicio y no en
la tubería. El detalle, con fórmulas, está en el capítulo 04.

## Pregunta trampa

**El umbral de confianza es un coseno fijo; ¿no es frágil?**
Sí, es coarse y depende del corpus: cerca del límite puede marcar un match bueno
como débil o al revés. Por eso **yerro hacia marcar** (needs_human_triage): es la
dirección segura, y el umbral es donde el equipo calibra según crezca su biblioteca
de runbooks. Prefiero un falso "revísalo" a un falso "confía". Pero el punto clave:
el umbral **no es la seguridad**, solo califica el match. Ningún paso que cambie el
sistema se ejecuta por confianza alta; de eso se encarga la aprobación humana, pase
lo que pase con el coseno. Lo coloqué (0,30) en el hueco medido: dominio ~0,35+,
fuera de dominio ~0,26 o menos.
