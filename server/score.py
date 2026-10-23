"""Shared notation/harmony primitives for the active score pipeline."""
import math
import xml.etree.ElementTree as ET


MAJOR_KEYS = ['Cb', 'Gb', 'Db', 'Ab', 'Eb', 'Bb', 'F', 'C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#']

MINOR_KEYS = ['Ab', 'Eb', 'Bb', 'F', 'C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#', 'G#', 'D#', 'A#']

KEYS = {f'{name} {mode}': index - 7 for mode, names in [('major', MAJOR_KEYS), ('minor', MINOR_KEYS)] for index, name in enumerate(names)}

METERS = {'2/4', '3/4', '4/4', '5/4', '6/8', '7/8', '9/8', '12/8'}

SETTINGS_ERROR = 'Please provide BPM (30–300), a supported time signature and key.'

def validate_settings(bpm, meter, key):
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        raise ValueError(SETTINGS_ERROR) from None
    if not math.isfinite(bpm) or not 30 <= bpm <= 300 or meter not in METERS or key not in KEYS:
        raise ValueError(SETTINGS_ERROR)
    return bpm, meter, key

def tag(parent, name, value=None, **attributes):
    element = ET.SubElement(parent, name, {key: str(value) for key, value in attributes.items()})
    if value is not None:
        element.text = str(value)
    return element

def spell_pitch(midi, fifths):
    """Prefer the provided key's diatonic spelling without changing sounding MIDI pitch."""
    alterations = {step: 0 for step in 'CDEFGAB'}
    for step in ('FCGDAEB' if fifths >= 0 else 'BEADGCF')[:abs(fifths)]:
        alterations[step] = 1 if fifths >= 0 else -1
    candidates = []
    for step, natural in zip('CDEFGAB', [0, 2, 4, 5, 7, 9, 11]):
        for alter in range(-2, 3):
            if (natural + alter) % 12 == midi % 12:
                cost = 4 * abs(alter - alterations[step]) + .35 * abs(alter)
                if alter * (1 if fifths >= 0 else -1) < 0:
                    cost += .1
                candidates.append((cost, step, alter, (midi - natural - alter) // 12 - 1))
    _, step, alter, octave = min(candidates)
    return step, alter, octave

def timestamp(seconds):
    tenths = int(round(seconds * 10))
    return f'{tenths // 600:02d}:{(tenths % 600) // 10:02d}.{tenths % 10}'
