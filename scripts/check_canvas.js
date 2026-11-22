// Canvas rule (owner decision, 22 Nov 2026).
//
//   node scripts/check_canvas.js
//
// Every image's outermost background is #F3F8F7: never pure white, never dark,
// never transparent. Cards inside stay #FFFFFF with border #E2EAE8, radius 14px.
// Screenshots of white pages are framed: the page as a card on ~40 px of canvas.
//
// Checks every tracked PNG (every edge pixel must be exactly #F3F8F7, fully
// opaque) and SVG (its first <rect> must be filled #F3F8F7). Any other image
// format must be listed in EXCEPT. No dependencies: PNGs are decoded with zlib.
// Exits 1 on any failure.
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const { execFileSync } = require("child_process");

const CANVAS = [0xf3, 0xf8, 0xf7];
const EXCEPT = [
  ["src/jobpipe/site/assets/favicon.ico", "favicon tile"],
  ["src/jobpipe/site/assets/icon.svg", "favicon tile"],
  ["src/jobpipe/site/assets/icon-192.png", "app-icon tile (web manifest)"],
  ["src/jobpipe/site/assets/logo-512.png", "app-icon tile (web manifest)"],
  ["src/jobpipe/site/assets/apple-touch-icon.png", "app-icon tile"],
  ["src/jobpipe/visuals/icons/*.svg", "technology logos drawn inside the README visuals, not standalone visuals"],
];

const root = path.resolve(__dirname, "..");
const glob = (pat) => new RegExp("^" + pat.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, "[^/]*") + "$");
const excepted = (f) => EXCEPT.some(([pat]) => glob(pat).test(f));

function decodePng(buf) {
  let p = 8, ihdr, plte, trns;
  const idat = [];
  while (p < buf.length) {
    const len = buf.readUInt32BE(p), type = buf.toString("ascii", p + 4, p + 8), data = buf.subarray(p + 8, p + 8 + len);
    if (type === "IHDR") ihdr = { w: data.readUInt32BE(0), h: data.readUInt32BE(4), depth: data[8], color: data[9], interlace: data[12] };
    else if (type === "PLTE") plte = data;
    else if (type === "tRNS") trns = data;
    else if (type === "IDAT") idat.push(data);
    p += 12 + len;
  }
  const { w, h, depth, color, interlace } = ihdr;
  if (depth !== 8 || interlace) throw new Error(`unsupported PNG (bit depth ${depth}, interlace ${interlace})`);
  const ch = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[color];
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = w * ch, out = Buffer.alloc(stride * h);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)], src = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const row = out.subarray(y * stride, (y + 1) * stride), up = y ? out.subarray((y - 1) * stride, y * stride) : null;
    for (let i = 0; i < stride; i++) {
      const a = i >= ch ? row[i - ch] : 0, b = up ? up[i] : 0, c = up && i >= ch ? up[i - ch] : 0;
      let v = src[i];
      if (f === 1) v += a;
      else if (f === 2) v += b;
      else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const q = a + b - c, pa = Math.abs(q - a), pb = Math.abs(q - b), pc = Math.abs(q - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      row[i] = v & 255;
    }
  }
  const px = (x, y) => {
    const o = (y * w + x) * ch;
    if (color === 6) return [out[o], out[o + 1], out[o + 2], out[o + 3]];
    if (color === 2) return [out[o], out[o + 1], out[o + 2], 255];
    if (color === 0) return [out[o], out[o], out[o], 255];
    if (color === 4) return [out[o], out[o], out[o], out[o + 1]];
    const k = out[o];
    return [plte[k * 3], plte[k * 3 + 1], plte[k * 3 + 2], trns && k < trns.length ? trns[k] : 255];
  };
  return { w, h, px };
}

function checkPng(file) {
  const { w, h, px } = decodePng(fs.readFileSync(file));
  const pts = [];
  for (let x = 0; x < w; x++) pts.push([x, 0], [x, h - 1]);
  for (let y = 0; y < h; y++) pts.push([0, y], [w - 1, y]);
  const bad = pts.filter(([x, y]) => { const c = px(x, y); return c[0] !== CANVAS[0] || c[1] !== CANVAS[1] || c[2] !== CANVAS[2] || c[3] !== 255; });
  if (!bad.length) return null;
  const [x, y] = bad[0], c = px(x, y);
  const hex = "#" + c.slice(0, 3).map((v) => v.toString(16).padStart(2, "0")).join("").toUpperCase();
  return `${bad.length} edge pixels off canvas, first at (${x},${y}) = ${hex} alpha ${c[3]}`;
}

function checkSvg(file) {
  const m = fs.readFileSync(file, "utf8").match(/<rect\b[^>]*>/);
  if (!m) return "no <rect> background";
  const f = m[0].match(/\bfill="([^"]+)"/) || m[0].match(/fill:\s*([^;"]+)/);
  const fill = f ? f[1].trim().toUpperCase() : "none";
  return fill === "#F3F8F7" ? null : `first <rect> fill is ${fill}`;
}

const files = execFileSync("git", ["-C", root, "ls-files"], { encoding: "utf8" }).split("\n").filter(Boolean);
let checked = 0;
const failures = [];
for (const f of files) {
  const ext = path.extname(f).slice(1).toLowerCase();
  if (!["png", "jpg", "jpeg", "webp", "gif", "svg"].includes(ext) || excepted(f)) continue;
  checked++;
  let err;
  try {
    err = ext === "svg" ? checkSvg(path.join(root, f)) : ext === "png" ? checkPng(path.join(root, f)) : `.${ext} is not checked: use PNG or add an exception`;
  } catch (e) { err = e.message; }
  if (err) failures.push(`${f}: ${err}`);
}
for (const line of failures) console.log("FAIL " + line);
console.log(`canvas rule: ${checked} images checked, ${failures.length} failing, ${EXCEPT.length} exception patterns`);
process.exit(failures.length ? 1 : 0);
