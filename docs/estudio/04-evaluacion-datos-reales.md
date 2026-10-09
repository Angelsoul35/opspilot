# 04 — Evaluación con datos reales

Los capítulos anteriores explican *qué hace* opspilot. Este explica cómo
**demostramos** que su motor de recuperación funciona sobre incidentes reales, con
métricas, fórmulas y un ejemplo trabajado con los números medidos. La idea central:
una afirmación de calidad ("el enrutado es bueno") solo vale si es **medible,
reproducible y resistente a un control** que la haría colapsar si fuera un
artefacto.

## Qué medimos y por qué

opspilot enruta un incidente a un runbook por recuperación TF-IDF
(`RunbookLibrary.rank`). Para medir eso con la verdad sobre la mesa usamos el
dataset público `Loukh1/IT-incidents`: 3252 tickets reales de soporte, cada uno
etiquetado con el **servicio** afectado (`Kubernetes`, `MySQL`, `Traefik`, ...). Ese
servicio es la **etiqueta de verdad** (*ground truth*): un enrutador que ve el
texto del ticket debería llevarlo al servicio correcto.

**Reusamos el motor tal cual.** Construimos un runbook por servicio cuyos
`symptoms` son los tickets de entrenamiento de ese servicio unidos — la firma de
cómo se ven sus incidentes, justo el campo sobre el que empareja el recuperador.
Enrutar un ticket es entonces: "¿a qué servicio-runbook lo manda `rank`?". No hay
un modelo paralelo; es el mismo `rank` que usa la aplicación.

## Las métricas y sus fórmulas

Sea un conjunto de prueba con $M$ tickets. Para el ticket $i$, $x_i$ es su texto,
$y_i$ su servicio real y $\hat{y}_i$ el servicio del runbook mejor rankeado.

### Exactitud top-1 (accuracy)

Fracción de tickets cuyo **primer** runbook es el servicio correcto:

$$\text{acc}@1 = \frac{1}{M} \sum_{i=1}^{M} \mathbb{1}\big[\hat{y}_i = y_i\big]$$

donde $\mathbb{1}[\cdot]$ vale 1 si la condición es cierta y 0 si no.

### Exactitud top-k

A veces basta con que el runbook correcto esté entre los $k$ primeros candidatos
(una vista de triage "estos son los 3 runbooks más probables"). Si
$\text{top}_k(x_i)$ es el conjunto de los $k$ servicios mejor rankeados:

$$\text{acc}@k = \frac{1}{M} \sum_{i=1}^{M} \mathbb{1}\big[y_i \in \text{top}_k(x_i)\big]$$

Por construcción $\text{acc}@k$ crece (nunca baja) con $k$, así que
$\text{acc}@3 \ge \text{acc}@1$ siempre.

### Macro-F1 (por servicio)

La exactitud global puede esconder un servicio minoritario que el modelo ignora.
Por eso medimos también **F1 por clase** y promediamos. Para el servicio $c$, con
verdaderos positivos $TP_c$, falsos positivos $FP_c$ y falsos negativos $FN_c$:

$$P_c = \frac{TP_c}{TP_c + FP_c}, \quad R_c = \frac{TP_c}{TP_c + FN_c}, \quad F1_c = \frac{2\,P_c\,R_c}{P_c + R_c}$$

El **macro-F1** es la media simple sobre las $C$ clases (cada servicio pesa igual,
grande o pequeño):

$$\text{macro-F1} = \frac{1}{C} \sum_{c=1}^{C} F1_c$$

Si una clase no recibe ninguna predicción, $P_c$ es $0/0$; la fijamos en 0
(`zero_division=0`), lo que castiga —con razón— ignorar esa clase.

### Las referencias (baselines) que hay que batir

Un número solo significa algo contra una referencia trivial:

$$\text{mayoría} = \frac{\max_c n_c}{N}, \qquad \text{azar} = \frac{1}{C}$$

donde $n_c$ es el número de tickets del servicio $c$ y $N$ el total. La de
**mayoría** es acertar siempre la clase más frecuente; la de **azar** es elegir
uniforme entre $C$ clases. Batir ambas por un margen amplio es la prueba de que el
texto, y no la frecuencia, hace el trabajo.

## El método: validación cruzada y partición held-out

Medir sobre los mismos datos con los que se construyó el índice daría una nota
inflada (**fuga de datos**, *leakage*). Lo evitamos de dos formas complementarias:

- **Partición held-out.** Separamos un 25 % de los tickets *estratificado* por
  servicio (cada servicio mantiene su proporción), construimos los runbooks con el
  75 % restante y medimos sobre el 25 % no visto.
- **Validación cruzada estratificada de 5 particiones (5-fold).** Repartimos los
  tickets en 5 bloques que preservan la proporción de clases. Cada bloque hace de
  prueba una vez mientras los otros cuatro entrenan; promediamos las 5 notas. Así
  cada ticket se evalúa exactamente una vez sin haber entrenado su propio runbook,
  y la **desviación estándar** entre particiones mide la estabilidad.

## Sobreajuste, subajuste y el *gap*

Dos fallos opuestos de generalización:

- **Sobreajuste (overfitting).** El modelo memoriza el entrenamiento y falla en lo
  nuevo: $\text{acc}_{\text{train}}$ alta pero $\text{acc}_{\text{test}}$ baja.
- **Subajuste (underfitting).** El modelo no captura ni la señal del
  entrenamiento: ambas exactitudes bajas, apenas por encima de la mayoría.

La herramienta de diagnóstico es el **gap** (brecha) entre entrenamiento y prueba:

$$\text{gap} = \text{acc}_{\text{train}} - \text{acc}_{\text{test}}$$

- gap **grande y positivo** → sobreajuste (alta varianza).
- test **apenas por encima de la mayoría** → subajuste (alto sesgo).
- gap **cercano a 0** y test **muy por encima de la mayoría**, con poca desviación
  entre particiones → **bien ajustado** (*well-fit*): generaliza, no memoriza.

El código (`classify_fit`) aplica justo esta lógica con dos umbrales:
`UNDERFIT_MARGIN = 0.10` (margen mínimo sobre la mayoría) y `WELL_FIT_MAX_GAP =
0.15` (gap máximo tolerable).

## El control: etiquetas barajadas

Un buen número puede ser un artefacto de la tubería (del vectorizador, del reparto)
y no de la relación texto→servicio. Para descartarlo, **barajamos las etiquetas**
de los tickets de entrenamiento y reconstruimos los runbooks con esos pares
(texto, servicio) revueltos. Si la señal fuera real y estuviera en el texto, al
romper esa correspondencia la exactitud debe **colapsar al azar** ($\approx 1/C$).
Si no colapsara, el número original no significaría nada. Es el experimento que
convierte "sale alto" en "sale alto *por la razón correcta*".

## Ejemplo trabajado con los números reales

Sobre los **12 servicios más frecuentes** (2214 tickets; el más frecuente es
`Docker` con 303):

$$\text{mayoría} = \frac{303}{2214} \approx 0.137, \qquad \text{azar} = \frac{1}{12} \approx 0.083$$

| Métrica                        | CV 5-fold (media ± sd) | Held-out (25 %) |
| ------------------------------ | ---------------------- | --------------- |
| Exactitud top-1                | **0.891 ± 0.008**      | **0.906**       |
| Exactitud top-3                | **0.975**              | **0.987**       |
| Macro-F1                       | **0.920**              | **0.932**       |
| Exactitud top-1 en train       | 0.898                  | 0.894           |
| gap (train − test)             | **+0.007**             | −0.012          |
| Control de etiquetas barajadas | —                      | **0.076**       |

Cómo se lee:

- **Bate las referencias por mucho.** 0.891 frente a 0.137 (mayoría) y 0.083
  (azar): un margen de ~0.75. La señal no es la frecuencia de clase.
- **Generaliza, no memoriza.** El gap es +0.007 en CV y −0.012 en held-out, es
  decir **≈ 0**: la nota en train y en datos no vistos coinciden hasta la centésima.
  Con una desviación entre particiones de solo 0.008, el veredicto es
  **bien ajustado**. (Que train ≈ test tiene sentido: cada ticket es uno entre
  cientos promediados en la firma de su servicio, así que no recibe trato de favor;
  su enrutado depende de lo representativo que sea, igual que uno de prueba.)
- **No es un 1.0 sospechoso.** Con 12 servicios reales que comparten vocabulario
  (varias bases de datos, varios orquestadores), ~0.89 es el techo realista y
  correcto; un 1.0 delataría fuga de datos.
- **El control colapsa.** Con etiquetas barajadas la top-1 cae a 0.076 ≈ azar
  (0.083): confirma que el acierto vive en el mapeo texto→servicio.
- **top-3 ≈ 0.98.** El runbook correcto casi siempre está entre los tres primeros
  candidatos: base ideal para una vista "los 3 runbooks más probables".

Reprodúcelo con `python -m opspilot.real_benchmark`.

## Mini-ejemplo numérico: por qué macro-F1 y no solo exactitud

Imagina un test de 10 tickets con dos servicios: **A** (8 tickets) y **B** (2). Un
enrutador perezoso manda *todo* a A. Entonces para A: $TP_A = 8$, $FP_A = 2$ (los
dos B mal mandados), $FN_A = 0$; para B: $TP_B = 0$, $FP_B = 0$, $FN_B = 2$.

$$P_A = \tfrac{8}{10} = 0.8, \; R_A = \tfrac{8}{8} = 1.0 \Rightarrow F1_A = \tfrac{2(0.8)(1.0)}{0.8+1.0} \approx 0.889$$
$$P_B = 0, \; R_B = 0 \Rightarrow F1_B = 0$$
$$\text{acc} = \tfrac{8}{10} = 0.80, \qquad \text{macro-F1} = \tfrac{0.889 + 0}{2} \approx 0.444$$

La exactitud (0.80) parece buena, pero el macro-F1 (0.44) delata que el servicio B
se ignora por completo. Por eso reportamos ambos: en los números reales, un
macro-F1 de 0.920 muy cercano a la exactitud de 0.906 confirma que el motor es
fuerte en **todos** los servicios, no solo en los frecuentes.

## Para fijar la idea

- Enrutar un ticket real a su servicio mide el motor de recuperación sobre datos
  reales, reusando `rank`.
- top-1/top-k + macro-F1, contra las referencias de mayoría y azar; macro-F1 evita
  que un servicio grande tape a uno pequeño.
- Validación cruzada estratificada + held-out, sin fuga de datos; el **gap** separa
  bien ajustado de sobre/subajuste.
- Números reales: top-1 ≈ 0.89, top-3 ≈ 0.98, macro-F1 ≈ 0.92, gap ≈ 0 →
  bien ajustado; el control barajado colapsa a ≈ 0.08.
