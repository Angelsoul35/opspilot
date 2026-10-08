# 02 — Aprobación humana (human-in-the-loop)

## Dos tipos de paso

La remediación incluye pasos que **cambian producción** (escalar, reiniciar, hacer
rollback, ampliar un volumen) y pasos de **diagnóstico** (solo lectura).
Automatizar los primeros sin juicio humano es como un incidente pequeño se vuelve
grande. Los segundos no deberían requerir ceremonia.

## El gate

Cada paso se marca `requires_approval` **si y solo si** es una acción con comando.
El `gate` resuelve cada paso contra el conjunto de índices que un humano ha
**aprobado explícitamente**:

- **advisory:** informativo/diagnóstico (sin comando o solo lectura) → nada que
  aprobar.
- **awaiting_approval:** una acción que cambia el sistema y **no** está aprobada.
- **approved_dry_run:** una acción cuyo índice el humano aprobó → se muestra como
  dry-run.

No hay ningún camino de código que ejecute una acción sin una decisión humana
explícita e indexada. Y el gate hace **solo dry-run**: nunca ejecuta un comando
real.

El gate es diminuto a propósito: la regla "un paso que cambia el sistema corre solo
si un humano aprobó su índice" son unas pocas líneas que se pueden leer y confiar
enteras, en vez de enterradas en un motor de ejecución grande. `pending_approvals`
lista exactamente qué pasos necesitan decisión, para que una UI o un chat los pida.

## ¿Por qué solo dry-run? ¿Por qué no ejecuta?

Ejecutar de verdad un paso aprobado necesita credenciales de producción, log de
auditoría, RBAC y un registro de cambios: un ejecutor crítico de seguridad que es
un sistema aparte. Dejarlo fuera significa que **el asistente nunca tiene las
llaves de producción**: propone y hace cumplir la aprobación, y entrega un plan
aprobado y explícito a quien sí las tenga. Esa separación es más segura que un solo
componente que aconseja y ejecuta.

## Para fijar la idea

- Diagnósticos (solo lectura) = advisory; acciones = requieren aprobación.
- El gate: una acción corre solo si su índice está aprobado; si no, espera.
- Solo dry-run: opspilot no ejecuta comandos reales ni tiene credenciales.
