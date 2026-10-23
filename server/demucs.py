"""Local HTDemucs FT vocal specialist via a parity-tested StemSplit ONNX export.

CPU inference only, no torch import or implicit model download. Graph input includes
the waveform/spectral frontend; output rows are drums, bass, other, vocals.
Upstream architecture/export: facebookresearch/demucs and StemSplit/demucs-onnx (MIT).
"""
from pathlib import Path
import numpy as np
import onnxruntime as ort
from .separation import session_options

ROOT = Path(__file__).resolve().parents[1]

def vocal_stem(wave, progress=lambda value: None):
    model = ROOT / 'models/demucs-vocals.onnx'
    if not model.is_file():
        raise RuntimeError('Separation model is missing. Run setup.ps1 first.')
    session = ort.InferenceSession(str(model), sess_options=session_options(), providers=['CPUExecutionProvider'])
    segment = 343980  # 7.8 seconds of stereo 44100 Hz PCM, baked into this export.
    overlap = segment // 4
    stride = segment - overlap
    window = np.ones(segment, dtype=np.float32)
    fade = np.linspace(0, 1, overlap, dtype=np.float32)
    window[:overlap], window[-overlap:] = fade, fade[::-1]
    result = np.zeros_like(wave)
    weights = np.zeros(wave.shape[1], dtype=np.float32)
    for start in range(0, wave.shape[1], stride):
        end = min(start + segment, wave.shape[1])
        chunk = np.zeros((1, 2, segment), dtype=np.float32)
        chunk[0, :, :end-start] = wave[:, start:end]
        predictions = session.run(['stems'], {'mix': chunk})[0]
        if predictions.shape != (1, 4, 2, segment) or not np.isfinite(predictions).all():
            raise RuntimeError('Vocal separation failed. Please retry or choose another file.')
        weight = window[:end-start].copy()
        if start == 0:
            weight[0] = 1  # Avoid a zero normalization weight at the first audio sample.
        result[:, start:end] += predictions[0, 3, :, :end-start] * weight
        weights[start:end] += weight
        progress(min(1., end / wave.shape[1]))
    return result / np.maximum(weights, 1e-8)
