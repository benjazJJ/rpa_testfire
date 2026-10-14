# Ideación de la solución creativa (IL 2.5)

Evaluación 2 – ATY1102. Módulo: `src/datos_sinteticos.py` (PASO 5B de `main.py`).

## 1. Problema detectado

Tras integrar SQLite (IL 2.3), el robot concilia cada movimiento de TestFire
y clasifica cuatro estados: *Conciliado*, *Con diferencias*, *Solo en
TestFire* y *Solo en maestro*. El reporte decía **qué** falló, pero no
**quién** debe revisarlo ni **con qué urgencia**. En una operación real, un
listado de excepciones sin dueño ni prioridad se queda sin atender.

Restricciones:

- TestFire es un sitio demo: solo expone IDs numéricos, sin personas.
- No podemos usar datos personales reales (ni del equipo ni de terceros).
- El robot no debe detenerse por un servicio externo no crítico.

## 2. Alternativas evaluadas

| Alternativa | Ventaja | Por qué se descartó / eligió |
|---|---|---|
| Lista fija de nombres en el código | Simple, sin red | No demuestra integración con datos externos |
| Librería Faker | Sin red, muy flexible | Agrega dependencia y no ejercita consumo de API |
| Usuarios de reqres.in (ya usados en IL 2.4) | Ya integrado | Solo 6 usuarios en inglés; mezcla dos propósitos en un solo módulo |
| **API RandomUser** | Datos sintéticos realistas en español (ES/MX), JSON, sin API key, reproducible con `seed` | **Elegida**, con respaldo local si la API falla |

## 3. Solución

1. **Obtener el equipo ficticio**: `GET https://randomuser.me/api/1.4/`
   con `nat=es,mx`, `seed=rpa-testfire` (mismo equipo en cada corrida) e
   `inc=name,email,nat` (no se piden contraseñas ni fotos). Los correos
   son `@example.com`, por lo que nunca llegan a una persona real.
2. **Priorizar** cada excepción con reglas de negocio:

   | Estado | Condición | Prioridad |
   |---|---|---|
   | Conciliado | – | (sin revisión) |
   | Con diferencias | difiere el **monto** | Alta |
   | Con diferencias | monto ≥ $1.000 | Alta |
   | Con diferencias | otro campo | Media |
   | Solo en TestFire / maestro | monto ≥ $1.000 | Media |
   | Solo en TestFire / maestro | monto < $1.000 | Baja |

3. **Asignar** cada excepción a un analista en *round-robin* para equilibrar
   la carga.
4. **Reportar**: el Excel agrega las columnas *Prioridad* y *Analista
   asignado* en la hoja *Conciliación*, y Google Sheets registra el evento
   "Asignar excepciones" con el conteo por prioridad.

## 4. Estructuras de control explícitas

| Estructura | Dónde | Para qué |
|---|---|---|
| `while` | `_consultar_randomuser` | Hasta 3 intentos con espera creciente (1 s, 2 s) |
| `for` | `obtener_analistas`, `asignar_excepciones` | Armar perfiles y recorrer cada resultado de conciliación |
| `if / elif / else` | `calcular_prioridad`, `obtener_analistas` | Reglas de prioridad; validar código HTTP 200; elegir API o respaldo |
| `continue` | `asignar_excepciones` | Saltar los movimientos conciliados |

## 5. Manejo de fallas

- Si RandomUser responde con error o sin conexión tras los reintentos, se
  usa un **equipo de respaldo local** y el resumen indica
  `origen: "Respaldo local"`.
- En `main.py` el paso está envuelto en `try/except`: si algo falla, se
  registra "Fallido" en la auditoría y el reporte Excel se genera igual
  (las columnas nuevas quedan vacías).

## 6. Evidencia y pruebas

- `python -m src.datos_sinteticos`: demo sin Selenium con un caso de cada estado.
- `python -m pytest tests`: prioridades, reintentos con respaldo, reparto
  round-robin y validación de parámetros (sin acceso a red).
- Con el maestro regenerado (`scripts/regenerar_master_desde_reporte.py
  --simular-diferencias 4`) la corrida produce 4 excepciones: 1 Alta,
  2 Media y 1 Baja.

## 7. Uso en Rocketbot

El módulo no depende de Selenium. Un paso "Script (Python)" de Rocketbot
puede importar `GeneradorDatosSinteticos` y llamar a
`asignar_excepciones(resultados)` sobre la lista que entrega la
conciliación.
