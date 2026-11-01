import sys, numpy as np, sherpa_onnx
from scipy.io import wavfile
d = sys.argv[1]
rec = sherpa_onnx.OfflineRecognizer.from_whisper(encoder=d+"/small-encoder.int8.onnx", decoder=d+"/small-decoder.int8.onnx", tokens=d+"/small-tokens.txt", language="tl", task="transcribe")
sr, a = wavfile.read(sys.argv[2]); a = a.astype(np.float32)/32768
segs = [(0,13)] + [tuple(map(float, s.split("-"))) for s in sys.argv[3:]]
for s0, s1 in segs:
    st = rec.create_stream(); st.accept_waveform(sr, a[int(s0*sr):int(s1*sr)]); rec.decode_stream(st)
    print(f"{s0:.2f}-{s1:.2f}: {st.result.text}")
