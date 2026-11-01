// Vocal isolation with UVR-MDX-NET-Voc_FT (onnxruntime) — a faithful port of reference_kit/tools/mdx.py.
// n_fft=7680, hop=1024, dim_f=3072, dim_t=256, chunk=hop*(dim_t-1), Hann window, reflect padding,
// input [1,4,3072,256] (real/imag of both channels), zero-pad bins 3072..3840 on the output,
// overlap-add with window-square normalisation, trim n_fft/2 at chunk edges, ×1.021.
// No Electron here; the onnxruntime module is passed in so the engine stays testable and portable.
import type { Stereo } from '../ffmpeg'

export const MDX_MODEL_URL =
  'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR-MDX-NET-Voc_FT.onnx'
export const MDX_MODEL_SHA256 = '534b2070fcc7df514b13ef660dc8cbb328679c2374d04354a5c42bb14ecce111'
export const MDX_MODEL_BYTES = 66762490

const N_FFT = 7680
const HOP = 1024
const DIM_F = 3072
const DIM_T = 256
const N_BINS = N_FFT / 2 + 1
const CHUNK = HOP * (DIM_T - 1)
const TRIM = N_FFT / 2
const GEN = CHUNK - 2 * TRIM

// ───────────── FFT: radix-2 + Bluestein so we can do the non-power-of-two 7680 exactly ─────────────
function fftPow2(re: Float64Array, im: Float64Array, inverse: boolean) {
  const n = re.length
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1
    for (; j & bit; bit >>= 1) j ^= bit
    j ^= bit
    if (i < j) {
      let t = re[i]; re[i] = re[j]; re[j] = t
      t = im[i]; im[i] = im[j]; im[j] = t
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = ((inverse ? 2 : -2) * Math.PI) / len
    const wr = Math.cos(ang), wi = Math.sin(ang)
    const half = len >> 1
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0
      for (let k = 0; k < half; k++) {
        const a = i + k, b = a + half
        const xr = re[b] * cr - im[b] * ci
        const xi = re[b] * ci + im[b] * cr
        re[b] = re[a] - xr; im[b] = im[a] - xi
        re[a] += xr; im[a] += xi
        const ncr = cr * wr - ci * wi
        ci = cr * wi + ci * wr
        cr = ncr
      }
    }
  }
}

/** Exact DFT of length N via Bluestein's algorithm (one precomputed chirp). */
class Bluestein {
  readonly M: number
  private wr: Float64Array
  private wi: Float64Array
  private Br: Float64Array
  private Bi: Float64Array
  private ar: Float64Array
  private ai: Float64Array
  constructor(readonly N: number) {
    let M = 1
    while (M < 2 * N - 1) M <<= 1
    this.M = M
    this.wr = new Float64Array(N)
    this.wi = new Float64Array(N)
    for (let k = 0; k < N; k++) {
      const a = (Math.PI * ((k * k) % (2 * N))) / N
      this.wr[k] = Math.cos(a)
      this.wi[k] = -Math.sin(a)
    }
    this.Br = new Float64Array(M)
    this.Bi = new Float64Array(M)
    for (let k = 0; k < N; k++) {
      this.Br[k] = this.wr[k]; this.Bi[k] = -this.wi[k]
      if (k > 0) { this.Br[M - k] = this.wr[k]; this.Bi[M - k] = -this.wi[k] }
    }
    fftPow2(this.Br, this.Bi, false)
    this.ar = new Float64Array(M)
    this.ai = new Float64Array(M)
  }
  /** Forward DFT in place (re, im of length N). */
  forward(re: Float64Array, im: Float64Array) {
    const { N, M, wr, wi, Br, Bi, ar, ai } = this
    ar.fill(0); ai.fill(0)
    for (let k = 0; k < N; k++) {
      ar[k] = re[k] * wr[k] - im[k] * wi[k]
      ai[k] = re[k] * wi[k] + im[k] * wr[k]
    }
    fftPow2(ar, ai, false)
    for (let k = 0; k < M; k++) {
      const r = ar[k] * Br[k] - ai[k] * Bi[k]
      const i = ar[k] * Bi[k] + ai[k] * Br[k]
      ar[k] = r; ai[k] = i
    }
    fftPow2(ar, ai, true)
    for (let k = 0; k < N; k++) {
      const r = ar[k] / M, i = ai[k] / M
      re[k] = r * wr[k] - i * wi[k]
      im[k] = r * wi[k] + i * wr[k]
    }
  }
  /** Inverse DFT in place, including the 1/N scale. */
  inverse(re: Float64Array, im: Float64Array) {
    for (let k = 0; k < this.N; k++) im[k] = -im[k]
    this.forward(re, im)
    for (let k = 0; k < this.N; k++) { re[k] /= this.N; im[k] = -im[k] / this.N }
  }
}

let bluestein: Bluestein | null = null
const dft = () => (bluestein ??= new Bluestein(N_FFT))

const WIN = (() => {
  const w = new Float64Array(N_FFT)
  for (let i = 0; i < N_FFT; i++) w[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / N_FFT) // np.hanning(n+1)[:-1]
  return w
})()

/** STFT of both channels of one chunk → model input [1, 4, 3072, 256] (ch0.re, ch0.im, ch1.re, ch1.im). */
export function stftChunk(x0: Float32Array, x1: Float32Array): Float32Array {
  const L = x0.length
  const P = N_FFT / 2
  const reflect = (x: Float32Array, i: number) => {
    let j = i - P
    if (j < 0) j = -j
    if (j >= L) j = 2 * (L - 1) - j
    return x[j]
  }
  const out = new Float32Array(4 * DIM_F * DIM_T)
  const re = new Float64Array(N_FFT)
  const im = new Float64Array(N_FFT)
  const F = dft()
  for (let t = 0; t < DIM_T; t++) {
    const off = t * HOP
    for (let n = 0; n < N_FFT; n++) {
      re[n] = reflect(x0, off + n) * WIN[n] // both real channels packed into one complex DFT
      im[n] = reflect(x1, off + n) * WIN[n]
    }
    F.forward(re, im)
    for (let k = 0; k < DIM_F; k++) {
      const nk = k === 0 ? 0 : N_FFT - k
      // unpack: X0 = (Z[k] + conj Z[N-k]) / 2 ; X1 = (Z[k] - conj Z[N-k]) / (2i)
      const a0 = (re[k] + re[nk]) / 2, b0 = (im[k] - im[nk]) / 2
      const a1 = (im[k] + im[nk]) / 2, b1 = (re[nk] - re[k]) / 2
      out[(0 * DIM_F + k) * DIM_T + t] = a0
      out[(1 * DIM_F + k) * DIM_T + t] = b0
      out[(2 * DIM_F + k) * DIM_T + t] = a1
      out[(3 * DIM_F + k) * DIM_T + t] = b1
    }
  }
  return out
}

/** Inverse STFT of the model output → two channels of length CHUNK (before the TRIM). */
export function istftChunk(Y: Float32Array): [Float64Array, Float64Array] {
  const outl = N_FFT + HOP * (DIM_T - 1)
  const y0 = new Float64Array(outl)
  const y1 = new Float64Array(outl)
  const ws = new Float64Array(outl)
  const re = new Float64Array(N_FFT)
  const im = new Float64Array(N_FFT)
  const F = dft()
  for (let t = 0; t < DIM_T; t++) {
    re.fill(0); im.fill(0)
    // Z = S0 + i·S1 with Hermitian halves rebuilt (bins ≥ 3072 are zero, as in the reference).
    for (let k = 0; k < DIM_F; k++) {
      let s0r = Y[(0 * DIM_F + k) * DIM_T + t], s0i = Y[(1 * DIM_F + k) * DIM_T + t]
      let s1r = Y[(2 * DIM_F + k) * DIM_T + t], s1i = Y[(3 * DIM_F + k) * DIM_T + t]
      if (k === 0) { s0i = 0; s1i = 0 } // irfft ignores the imaginary part of DC
      re[k] += s0r - s1i
      im[k] += s0i + s1r
      if (k > 0) {
        const nk = N_FFT - k
        re[nk] += s0r + s1i
        im[nk] += -s0i + s1r
      }
    }
    F.inverse(re, im)
    const off = t * HOP
    for (let n = 0; n < N_FFT; n++) {
      y0[off + n] += re[n] * WIN[n]
      y1[off + n] += im[n] * WIN[n]
      ws[off + n] += WIN[n] * WIN[n]
    }
  }
  const a0 = new Float64Array(CHUNK)
  const a1 = new Float64Array(CHUNK)
  for (let i = 0; i < CHUNK; i++) {
    const w = Math.max(ws[TRIM + i], 1e-8)
    a0[i] = y0[TRIM + i] / w
    a1[i] = y1[TRIM + i] / w
  }
  return [a0, a1]
}

/** The minimal onnxruntime surface we use (so tests can pass the real module). */
export interface OrtLike {
  InferenceSession: { create(path: string, opts?: unknown): Promise<{ inputNames: readonly string[]; outputNames: readonly string[]; run(feeds: Record<string, unknown>): Promise<Record<string, { data: unknown }>> }> }
  Tensor: new (type: 'float32', data: Float32Array, dims: number[]) => unknown
}

/** Isolate the vocals from `mix` (44.1 kHz stereo). Calls onProgress(0..1). */
export async function isolateVocals(ort: OrtLike, modelPath: string, mix: Stereo, onProgress?: (f: number) => void): Promise<Stereo> {
  // No memory arena / memory pattern: inside Electron (any process) the arena re-uses buffers that a previous
  // result still points to, which aborts the app on the 2nd chunk (SIGTRAP). Results are copied, then released.
  const sess = await ort.InferenceSession.create(modelPath, { executionProviders: ['cpu'], enableCpuMemArena: false, enableMemPattern: false })
  const n = mix.l.length
  const pad = GEN - (n % GEN)
  const total = TRIM + n + pad + TRIM
  const m0 = new Float32Array(total)
  const m1 = new Float32Array(total)
  m0.set(mix.l, TRIM)
  m1.set(mix.r, TRIM)
  const out0 = new Float32Array(n + pad)
  const out1 = new Float32Array(n + pad)
  const steps = (n + pad) / GEN
  for (let s = 0, i = 0; i < n + pad; i += GEN, s++) {
    const X = stftChunk(m0.subarray(i, i + CHUNK), m1.subarray(i, i + CHUNK))
    const input = new ort.Tensor('float32', X, [1, 4, DIM_F, DIM_T]) as { dispose?: () => void }
    const res = await sess.run({ [sess.inputNames[0]]: input })
    const outT = res[sess.outputNames[0]] as { data: unknown; dispose?: () => void }
    const Y = new Float32Array(outT.data as Float32Array) // copy before releasing
    outT.dispose?.()
    input.dispose?.()
    const [y0, y1] = istftChunk(Y)
    for (let k = 0; k < GEN; k++) {
      out0[i + k] = y0[TRIM + k]
      out1[i + k] = y1[TRIM + k]
    }
    onProgress?.((s + 1) / steps)
  }
  const l = new Float32Array(n)
  const r = new Float32Array(n)
  for (let k = 0; k < n; k++) {
    l[k] = Math.max(-1, Math.min(1, out0[k] * 1.021))
    r[k] = Math.max(-1, Math.min(1, out1[k] * 1.021))
  }
  return { l, r }
}

export { Bluestein as _Bluestein, N_FFT as _N_FFT }
