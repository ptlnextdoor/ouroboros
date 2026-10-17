// OpenSCAD (CADAM's vendored WASM build) in a worker: SCAD source -> coloured, crease-shaded mesh.
import OpenSCAD from './openscad/openscad.js';

const wasm = fetch(new URL('./openscad/openscad.wasm', import.meta.url)).then(r => r.arrayBuffer());

function parseOff(text) {
  const L = text.split('\n').map(s => s.trim()).filter(s => s && !s.startsWith('#'));
  let c = 0, head;
  const rest = L[0].slice(3).trim();
  if (rest) { head = rest; c = 1; } else { head = L[1]; c = 2; }
  const [nv, nf] = head.split(/\s+/).map(Number);
  const V = new Float64Array(nv * 3);
  for (let i = 0; i < nv; i++) {
    const p = L[c + i].split(/\s+/);
    V[3 * i] = +p[0]; V[3 * i + 1] = +p[1]; V[3 * i + 2] = +p[2];
  }
  c += nv;
  const T = [], C = [];
  for (let i = 0; i < nf; i++) {
    const p = L[c + i].split(/\s+/).map(Number);
    const n = p[0], idx = p.slice(1, n + 1), tr = p.slice(n + 1);
    const col = tr.length >= 3 ? [tr[0] / 255, tr[1] / 255, tr[2] / 255] : [0.6, 0.6, 0.62];
    for (let k = 1; k < n - 1; k++) { T.push(idx[0], idx[k], idx[k + 1]); C.push(col); }
  }
  return { V, T, C };
}

function build({ V, T, C }) {
  const nt = T.length / 3;
  const FN = new Float64Array(nt * 3);
  let vol = 0, area = 0;
  const lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
  for (let f = 0; f < nt; f++) {
    const a = T[3 * f] * 3, b = T[3 * f + 1] * 3, d = T[3 * f + 2] * 3;
    const ux = V[b] - V[a], uy = V[b + 1] - V[a + 1], uz = V[b + 2] - V[a + 2];
    const vx = V[d] - V[a], vy = V[d + 1] - V[a + 1], vz = V[d + 2] - V[a + 2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const m = Math.hypot(nx, ny, nz) || 1;
    area += m / 2;
    vol += (V[a] * (V[b + 1] * V[d + 2] - V[b + 2] * V[d + 1]) - V[a + 1] * (V[b] * V[d + 2] - V[b + 2] * V[d])
      + V[a + 2] * (V[b] * V[d + 1] - V[b + 1] * V[d])) / 6;
    FN[3 * f] = nx / m; FN[3 * f + 1] = ny / m; FN[3 * f + 2] = nz / m;
  }
  for (let i = 0; i < V.length; i += 3) for (let k = 0; k < 3; k++) {
    lo[k] = Math.min(lo[k], V[i + k]); hi[k] = Math.max(hi[k], V[i + k]);
  }
  // vertex -> faces, then crease-angle smoothing (40 deg) so bodies are smooth and edges stay sharp
  const adj = Array.from({ length: V.length / 3 }, () => []);
  for (let f = 0; f < nt; f++) for (let k = 0; k < 3; k++) adj[T[3 * f + k]].push(f);
  const cosC = Math.cos(40 * Math.PI / 180);
  const pos = new Float32Array(nt * 9), nor = new Float32Array(nt * 9), col = new Float32Array(nt * 9);
  for (let f = 0; f < nt; f++) {
    const fx = FN[3 * f], fy = FN[3 * f + 1], fz = FN[3 * f + 2];
    for (let k = 0; k < 3; k++) {
      const v = T[3 * f + k], o = 9 * f + 3 * k;
      pos[o] = V[3 * v]; pos[o + 1] = V[3 * v + 1]; pos[o + 2] = V[3 * v + 2];
      let sx = 0, sy = 0, sz = 0;
      for (const g of adj[v]) {
        const gx = FN[3 * g], gy = FN[3 * g + 1], gz = FN[3 * g + 2];
        if (gx * fx + gy * fy + gz * fz >= cosC) { sx += gx; sy += gy; sz += gz; }
      }
      const m = Math.hypot(sx, sy, sz) || 1;
      nor[o] = sx / m; nor[o + 1] = sy / m; nor[o + 2] = sz / m;
      col[o] = C[f][0]; col[o + 1] = C[f][1]; col[o + 2] = C[f][2];
    }
  }
  return { pos, nor, col, tris: nt, vol_mm3: Math.abs(vol), area_mm2: area, lo, hi };
}

self.onmessage = async (e) => {
  const { id, code } = e.data;
  const log = [];
  const t0 = performance.now();
  try {
    const inst = await OpenSCAD({ noInitialRun: true, wasmBinary: await wasm, print: t => log.push(t), printErr: t => log.push(t) });
    inst.FS.writeFile('/in.scad', code);
    const rc = inst.callMain(['/in.scad', '-o', '/out.off', '--backend=manifold']);
    if (rc !== 0) throw new Error('OpenSCAD exit ' + rc);
    const off = inst.FS.readFile('/out.off', { encoding: 'utf8' });
    const t1 = performance.now();
    const m = build(parseOff(off));
    self.postMessage({ id, ok: true, ...m, ms_scad: t1 - t0, ms: performance.now() - t0 },
      [m.pos.buffer, m.nor.buffer, m.col.buffer]);
  } catch (x) {
    const errs = log.filter(l => /error|warning|assert/i.test(l));
    self.postMessage({ id, ok: false, error: (errs.length ? errs : log).slice(-6).join('\n') || String(x), ms: performance.now() - t0 });
  }
};
