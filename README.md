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
- Descarga MIDI con dos tiempos por acorde y el tempo seleccionado.
- API local: `/api/progression?text=Cmaj7`, `/api/qualities`, `/api/midi?text=Cmaj7&bpm=86`.

## Validación

```sh
python3 -m unittest -v
```

La conducción busca posiciones ascendentes de menor desplazamiento entre acordes consecutivos. No implementa reglas completas de contrapunto ni optimización global de la progresión. El diagrama de guitarra es orientativo y no garantiza digitaciones ejecutables. La reproducción del navegador usa ataques separados por acorde; no sintetiza portamento continuo. El MIDI representa notas, duración y tempo.

`music.py` contiene la lógica musical; `app.py`, el servidor local; `index.html`, la interfaz.
