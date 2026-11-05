# BlackMamba Harmonic Glide

Laboratorio local de progresiones armónicas con motor Python, visualización de voces, reproducción Web Audio y exportación MIDI.

## Ejecutar

Requiere Python 3.10 o posterior, sin dependencias externas.

```sh
python3 app.py
```

Abre http://127.0.0.1:8765 en un navegador. El HTML requiere el servidor Python; abrirlo directamente no carga el motor.

## Opciones

- Hasta 24 acordes por progresión, separados por espacios, comas o punto y coma.
- Mayores, menores, dim, aug, sus2, sus4, 6, m6, 7, maj7, m7, m7b5, dim7, 9, maj9, m9, add9, 11, 13, 7#9 y 7b9.
- Tempo entre 45 y 180 BPM, tres timbres y selección de acordes.
- Temas Oscuro, Plata, Morado y Océano con selección guardada localmente.
- El acento sigue la fundamental del acorde activo; las notas y voces usan una paleta por clase de altura basada en el círculo de quintas. Es una convención visual, sin entrada de micrófono.
- Descarga MIDI con dos tiempos por acorde y el tempo seleccionado.
- API local: `/api/progression?text=Cmaj7`, `/api/qualities`, `/api/midi?text=Cmaj7&bpm=86`.

## Validación

```sh
python3 -m unittest -v
```

La conducción busca posiciones ascendentes de menor desplazamiento entre acordes consecutivos. No implementa reglas completas de contrapunto ni optimización global de la progresión. El diagrama de guitarra es orientativo y no garantiza digitaciones ejecutables. La reproducción del navegador usa ataques separados por acorde; no sintetiza portamento continuo. El MIDI representa notas, duración y tempo.

`music.py` contiene la lógica musical; `app.py`, el servidor local; `index.html`, la interfaz.

## Reconstrucción de arreglos a partir de audio

La herramienta de arreglos se ejecuta por separado del laboratorio web. Usa un entorno
Python 3.11 con dependencias opcionales.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-arrangement.txt
.venv/bin/python -m glide_arrangement analyze referencia.mp3 arreglo.json
.venv/bin/python -m glide_arrangement render arreglo.json arreglo.wav
.venv/bin/python -m glide_arrangement render arreglo.json arreglo.mid --bpm 126
.venv/bin/python -m glide_arrangement compare referencia.mp3 arreglo.wav
.venv/bin/python -m unittest -v
```

El JSON conserva cada nota por voz con altura MIDI, inicio, fin y velocidad.
Edita `instrument` (`bass`, `soft`, `keys`, `strings`), `attack` y `release`
(en segundos), o `expression` como pares `[segundo, nivel CC11]` ordenados.
Por ejemplo, `[[0, 75], [1.5, 112], [3.8, 64]]` aplica un crescendo seguido de
un decrescendo. Los eventos de una voz pueden solaparse para producir legato
en WAV. El MIDI guarda los tiempos, las velocidades, el programa y CC11.
Usa voces separadas para duplicar una misma altura durante un solapamiento MIDI.
La exportación MIDI admite hasta 15 voces independientes.

El analizador estima notas MIDI 36–88 y agrupa eventos por registro, cercanía
y continuidad temporal. En una mezcla puede confundir parciales con notas o
agrupar dos fuentes al unísono. Las voces, los roles y los instrumentos
asignados automáticamente son propuestas editables. La velocidad se estima
a partir de la energía de cada evento. La curva de expresión queda a criterio
de quien edite el arreglo. El WAV usa síntesis sin efectos de mezcla.

A/B acepta audio y JSON, y empareja eventos con una tolerancia de inicio de
200 ms. Reporta notas sin pareja, errores de altura, inicio, duración y
distribución por octavas. Cuando A es audio, la referencia también es una
transcripción estimada. Para medir precisión frente a notas verificadas,
usa un arreglo JSON anotado como A.

### Experimento de articulación

Usa el JSON y el WAV de la reconstrucción actual como A. El detector
lee la referencia original y genera un JSON separado con las decisiones de B.

```sh
.venv/bin/python -m glide_arrangement articulate referencia.mp3 arreglo.json arreglo-b.json
.venv/bin/python -m glide_arrangement render arreglo-b.json arreglo-b.wav
.venv/bin/python -m glide_arrangement articulation-ab referencia.mp3 arreglo.json arreglo.wav arreglo-b.json arreglo-b.wav
```

El detector usa energía y flujo espectral en bandas alrededor de los armónicos
de cada altura ya estimada. Une fragmentos cercanos si se mantiene la energía
sin un ataque claro. Divide una nota existente solo ante una caída marcada
seguida de una subida con transitorio. Etiqueta como legato las transiciones
cercanas entre alturas de una misma voz con energía durante el enlace.
La etiqueta de release guarda el fin audible estimado y la caída de energía
propuesta como fin de excitación. El sintetizador usa la cola configurada
para esa voz.

El informe separa precisión y cobertura de altura, errores de inicio, fin y
duración, pausas y solapamientos por voz, y similitud de la envolvente RMS.
Los conteos de decisiones sobre el MP3 son hipótesis. Para medir precisión y
cobertura de retriggers se requieren ataques anotados por voz, altura y tiempo.
Las pruebas usan eventos conocidos para esa evaluación.

### Articulación selectiva vNext.2

Añade `--variant B1`, `--variant B2` o `--variant B3` al comando
`articulate`. B1 une solo fragmentos con continuidad de energía, perfil
armónico y ausencia de un transitorio. B2 divide eventos solo cuando la
subida de energía y el transitorio coinciden con una caída y recuperación de
la fundamental. B3 aplica ambas reglas en ese orden. Las variantes dejan en
A los casos indeterminados y los tiempos de legato o release. Omitir
`--variant` ejecuta el experimento anterior.

Para reproducir la prueba controlada independiente:

```sh
.venv/bin/python -m experiments.selective_fixture /tmp/glide-holdout
.venv/bin/python -m experiments.selective_ab /tmp/glide-holdout/holdout.wav /tmp/glide-holdout --labels /tmp/glide-holdout/holdout-labels.json
```

Para usar la reconstrucción previa como A, ejecuta el mismo experimento
con el MP3 original, otra carpeta de salida y `--baseline arreglo.json`.
El informe compara A, B1, B2 y B3 con la misma síntesis. El criterio numérico
requiere subir la correlación RMS, perder como máximo un punto porcentual
en precisión y recuperación de alturas y aumentar como máximo 10 ms el
error medio de inicio y de fin. Es una tolerancia operativa, no una prueba
de significancia. El audio de control se genera con ataques conocidos y
permite medir retriggers con una tolerancia de 75 ms. Las métricas contra
el audio original siguen dependiendo de la transcripción estimada.
