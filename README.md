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
