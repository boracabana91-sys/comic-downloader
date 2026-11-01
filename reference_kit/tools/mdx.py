import sys, numpy as np, onnxruntime as ort
from scipy.io import wavfile
model, inp, out = sys.argv[1:4]
sess = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
i0 = sess.get_inputs()[0]; print(i0.name, i0.shape)
n_fft, hop, dim_f, dim_t = 7680, 1024, 3072, 256
n_bins = n_fft//2+1; chunk = hop*(dim_t-1); trim = n_fft//2; gen = chunk-2*trim
win = np.hanning(n_fft+1)[:-1].astype(np.float32)
def stft(x):  # x [C, L] -> [C, n_bins, T]
    xp = np.pad(x, ((0,0),(n_fft//2,n_fft//2)), mode="reflect")
    T = 1 + (xp.shape[1]-n_fft)//hop
    idx = np.arange(n_fft)[None,:] + hop*np.arange(T)[:,None]
    fr = xp[:, idx] * win
    return np.fft.rfft(fr, axis=-1).transpose(0,2,1)
def istft(S, L):
    C, F, T = S.shape
    fr = np.fft.irfft(S.transpose(0,2,1), n=n_fft, axis=-1) * win
    outl = n_fft + hop*(T-1); y = np.zeros((C,outl)); ws = np.zeros(outl)
    for t in range(T):
        y[:, t*hop:t*hop+n_fft] += fr[:, t]; ws[t*hop:t*hop+n_fft] += win**2
    y /= np.maximum(ws, 1e-8)
    return y[:, n_fft//2:n_fft//2+L]
sr, mix = wavfile.read(inp); mix = mix.astype(np.float32)
if mix.dtype != np.float32 or np.abs(mix).max() > 2: mix = mix/32768.0
mix = mix.T if mix.ndim == 2 else np.stack([mix, mix])
n = mix.shape[1]; pad = gen - n % gen
mp = np.concatenate([np.zeros((2,trim)), mix, np.zeros((2,pad)), np.zeros((2,trim))], 1).astype(np.float32)
outs = []
for i in range(0, n+pad, gen):
    w = mp[:, i:i+chunk]
    S = stft(w)  # [2, n_bins, 256]
    X = np.stack([S.real, S.imag], -1)  # [2,F,T,2]
    X = X.transpose(0,3,1,2).reshape(1,4,n_bins,dim_t)[:, :, :dim_f].astype(np.float32)
    Y = sess.run(None, {i0.name: X})[0]
    Y = np.concatenate([Y, np.zeros((1,4,n_bins-dim_f,dim_t),np.float32)], 2).reshape(2,2,n_bins,dim_t)
    Sc = Y[:,0] + 1j*Y[:,1]
    outs.append(istft(Sc, chunk)[:, trim:-trim])
voc = np.concatenate(outs, 1)[:, :n] * 1.021
wavfile.write(out, sr, (np.clip(voc.T, -1, 1)*32767).astype(np.int16)); print("ok", voc.shape)
