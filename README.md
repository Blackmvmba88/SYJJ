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

### Duración acústica vNext.3

```sh
.venv/bin/python -m glide_arrangement duration referencia.mp3 arreglo.json duracion.json --instrument piano
.venv/bin/python -m glide_arrangement render duracion.json duracion.mid
.venv/bin/python -m glide_arrangement render duracion.json duracion.wav
```

La etapa opcional estima un cambio de pendiente en la envolvente por altura y
exige que los parciales corroboren la caída. El perfil del instrumento define
rangos plausibles de pendiente y cola. Sin evidencia suficiente conserva el
evento de A. El JSON separa el fin MIDI del fin acústico y marca si el segundo
se observó o se acotó con el modelo. Usa un piso operativo de −24 dB para
la cola, no un umbral de audibilidad universal. MIDI exporta el fin de
excitación y WAV aplica la duración de cola estimada. Si se omite
`--instrument`, se usa el perfil asignado a cada voz en el JSON.

La evaluación contra MIDI real empareja por altura exacta e inicio dentro de
100 ms. Fija las mismas parejas para A y vNext.3 y desglosa el error de fin
por registro, instrumento, pedal y repetición cercana de la misma altura.

```sh
.venv/bin/python -m pip install mido==1.3.3
.venv/bin/python -m experiments.duration_ab fragmento.wav interpretacion.mid --seconds 26 --instrument piano
```

La prueba externa usó los primeros 26 s de las tomas VuV01M y Zhang01M
de la fuga BWV 858. Audio MAESTRO y MIDI de interpretación ASAP,
distribuidos por [Matchmaker](https://github.com/pymatchmaker/matchmaker-benchmark-data/tree/main/asap).
Los archivos de terceros no se incluyen en el repositorio.

### Pedal y resonancia vNext.4

La evaluación construye los intervalos CC64 por canal, conserva el orden de
eventos simultáneos y separa el fin de tecla del retorno esperado del
amortiguador. El modelo MIDI es binario (CC64 ≥ 64) y no mide la mecánica
del instrumento ni el medio pedal. El informe excluye de la métrica de
amortiguador los finales fuera del fragmento y las rearticulaciones que
impiden atribuir una cola a una sola nota.

El JSON de duración distingue `observed` (cruce del piso operativo de
−24 dB dentro de la ventana), `extrapolated` (cruce calculado a partir de
la pendiente) y `bounded` (resultado limitado por la ventana o el perfil).
El fin acústico y el retorno del amortiguador son mediciones distintas.

```sh
.venv/bin/python -m experiments.pedal_ab /ruta/a/fragmentos TOMA1 TOMA2 --seconds 45
.venv/bin/python -m experiments.guitar_duration_ab /ruta/a/guitarset 0 120 240
```

La primera herramienta lee WAV y MIDI con el mismo nombre base. La segunda
lee el WAV de micrófono y la respuesta JSON del visor de filas de
[jhartquist/guitarset](https://huggingface.co/datasets/jhartquist/guitarset)
para cada índice. Reporta finales anotados por cuerda, cuerdas superpuestas,
repeticiones de altura y transiciones cercanas. Esas etiquetas describen
eventos acústicos, no el gesto de apagado o ligado de la mano.

La evaluación externa aplicó los perfiles de vNext.3 sin recalibrarlos. Para
piano usó 45 s iniciales de seis piezas en la revisión
`7ea5babf039a0c009050646c90ea2bfe925653f6` de
[Matchmaker/ASAP](https://github.com/pymatchmaker/matchmaker-benchmark-data/tree/main/asap)
(audio MAESTRO). Para guitarra usó las filas 0, 120 y 240 de la distribución
indicada de [GuitarSet](https://zenodo.org/records/3371780). Los intervalos
bootstrap emparejados remuestrean interpretaciones, con igual peso por toma.
Los audios y anotaciones de terceros se descargan por separado.

### Resonancia condicionada vNext.5

```sh
.venv/bin/python -m glide_arrangement resonance referencia.wav duracion.json resonancia.json --instrument piano --pedal-midi interpretacion.mid
.venv/bin/python -m glide_arrangement render resonancia.json resonancia.wav
.venv/bin/python -m glide_arrangement render resonancia.json resonancia.mid
```

La etapa conserva los eventos musicales y añade un registro de resonancia por
nota. Para piano puede leer CC64 de un MIDI alineado (`--pedal-channel`,
0 por defecto). MIDI conserva los tiempos de tecla y exporta el pedal
binario en los canales melódicos. Sin MIDI de pedal el estado queda como
desconocido. El WAV aplica un decaimiento más lento mientras el amortiguador
permanece abierto y el cierre posterior cuando hay una cola observada.

Para guitarra, `--instrument guitar` aplica la ventana de ese instrumento.
Opcionalmente `--strings cuerdas.json` acepta un mapa de voces y pistas por
cuerda, con rutas relativas al JSON. Por ejemplo,
`{"voices":{"v1":"2"},"audio":{"2":"cuerda-2.wav"}}`. Sin pistas aisladas,
el análisis mono descarta observaciones cuando otra nota puede contribuir
a la misma frecuencia. Las grabaciones de guitarra de la evaluación usan
audio mono.

Un cruce observado requiere que la fundamental y la envolvente armónica
permanezcan bajo −24 dB durante al menos 70 ms. En piano con pedal conocido,
la búsqueda empieza en el retorno previsto del amortiguador. Una nota
puede volverse inaudible antes de ese instante y quedar indeterminada.
Un final predicho se registra por separado y conserva la cola del render
anterior, al igual que un caso indeterminado.

`experiments.resonance_ab` compara tomas completas con los mismos eventos
de vNext.3 y dos renders, con y sin las colas observadas de vNext.5.
Reporta error RMS normalizado de mezcla y ventanas posteriores al fin MIDI
por estado del pedal. Es una medida de reconstrucción de la envolvente
de mezcla y no una validación independiente del final acústico por nota.
