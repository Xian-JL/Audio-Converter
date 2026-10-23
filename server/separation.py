"""CPU MDX-Net inference with NumPy/librosa STFT; no training framework.

Model processing follows UVR's MDX pipeline (MIT, Anjok07/UVR contributors).
The inference adapter is implemented here without importing the UVR GUI/PyTorch.
"""
from pathlib import Path
import json
import os
import numpy as np
import librosa
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]

def session_options():
    options = ort.SessionOptions()
    options.intra_op_num_threads = min(6, max(1, (os.cpu_count() or 2) // 2))
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return options

def to_spectrum(wave, n_fft, hop, dim_f):
    spectrum = librosa.stft(wave, n_fft=n_fft, hop_length=hop, window='hann', center=True, pad_mode='reflect')
    return np.stack((spectrum[0].real, spectrum[0].imag, spectrum[1].real, spectrum[1].imag), axis=0)[None, :, :dim_f, :].astype(np.float32)

def from_spectrum(spectrum, n_fft, hop, length):
    complex_spectrum = np.stack((spectrum[0, 0] + 1j * spectrum[0, 1], spectrum[0, 2] + 1j * spectrum[0, 3]))
    complex_spectrum = np.pad(complex_spectrum, ((0, 0), (0, n_fft // 2 + 1 - complex_spectrum.shape[1]), (0, 0)))
    return librosa.istft(complex_spectrum, hop_length=hop, window='hann', center=True, length=length).astype(np.float32)

def guided_clean(carrier, reference, sr=44100):
    """Conservative spectral support; retains carrier phase and a 20% amplitude floor.

    This does not classify or delete note events. Equal stems are an identity transform.
    """
    cleaned = np.zeros_like(carrier)
    size, context, n_fft, hop = sr * 15, 4096, 2048, 512
    for start in range(0, carrier.shape[1], size):
        end = min(start + size, carrier.shape[1])
        left, right = max(0, start - context), min(carrier.shape[1], end + context)
        original_spec = librosa.stft(carrier[:, left:right], n_fft=n_fft, hop_length=hop)
        reference_spec = librosa.stft(reference[:, left:right], n_fft=n_fft, hop_length=hop)
        original_mag, reference_mag = np.abs(original_spec), np.abs(reference_spec)
        support = np.minimum(1., 2 * reference_mag / np.maximum(original_mag + reference_mag, 1e-8))
        mask = .2 + .8 * support
        reconstructed = librosa.istft(original_spec * mask, hop_length=hop, length=right - left)
        cleaned[:, start:end] = reconstructed[:, start-left:end-left]
    return cleaned

def separate(wave, progress=lambda value: None, mode='enhanced'):
    if mode == 'enhanced':
        # Different architecture, not another volume/confidence gate on detected notes.
        from .demucs import vocal_stem
        vocals = vocal_stem(wave, progress)
        return vocals, wave - vocals
    if mode != 'original':
        raise ValueError('Unknown vocal separation mode.')
    return _predict(wave, progress, 'original')

def _predict(wave, progress, mode):
    if mode not in ('vocal-ft', 'original', 'lead'):
        raise ValueError('Unknown vocal separation mode.')
    stem = {'vocal-ft': 'vocal-ft', 'original': 'mdx', 'lead': 'lead'}[mode]
    model = ROOT / f'models/{stem}.onnx'
    config_path = ROOT / f'models/{stem}-config.json'
    if not model.is_file() or not config_path.is_file():
        raise RuntimeError('Separation model is missing. Run setup.ps1 first.')
    config = json.loads(config_path.read_text())
    session = ort.InferenceSession(str(model), sess_options=session_options(), providers=['CPUExecutionProvider'])
    input_name = session.get_inputs()[0].name
    n_fft = config['mdx_n_fft_scale_set']
    dim_f = config['mdx_dim_f_set']
    frames = 2 ** config['mdx_dim_t_set']
    hop = 1024
    size = hop * (frames - 1)
    trim = n_fft // 2
    # Context padding is discarded before blending; overlap boundaries receive Hann weights.
    usable = size - 2 * trim
    step = int(usable * .75)
    padded = np.pad(wave, ((0, 0), (trim, size)))
    result = np.zeros((2, wave.shape[1] + size), dtype=np.float32)
    weight = np.zeros(wave.shape[1] + size, dtype=np.float32)
    window = np.hanning(usable).astype(np.float32)
    for start in range(0, wave.shape[1], step):
        segment = padded[:, start:start + size]
        spectrum = to_spectrum(segment, n_fft, hop, dim_f)
        spectrum[:, :, :3] = 0
        prediction = session.run(None, {input_name: spectrum})[0]
        if mode == 'vocal-ft':
            # UVR's polarity-symmetric denoise inference reduces non-symmetric model artefacts.
            np.negative(spectrum, out=spectrum)
            inverted = session.run(None, {input_name: spectrum})[0]
            prediction -= inverted
            prediction *= .5
        output = from_spectrum(prediction, n_fft, hop, size)[:, trim:trim + usable]
        result[:, start:start + usable] += output * window
        weight[start:start + usable] += window
        progress(min(1, (start + usable) / wave.shape[1]))
    result = result[:, :wave.shape[1]] / np.maximum(weight[:wave.shape[1]], 1e-6)
    result *= config.get('compensate', 1)
    if config['primary_stem'] == 'Instrumental':
        return wave - result, result
    return result, wave - result
