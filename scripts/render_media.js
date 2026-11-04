// Render assets/social-preview.png (1280x640) and media/linkedin-hero.mp4 (1080x1080, 10 s, H.264)
// from the generated SVGs. Usage: node scripts/render_media.js   (needs playwright + ffmpeg)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const root = path.resolve(__dirname, '..');
const fonts = path.join(root, 'src/jobpipe/site/assets/fonts');
const status = JSON.parse(fs.readFileSync(path.join(root, 'public/status.json'), 'utf8'));

(async () => {
  const browser = await chromium.launch();

  // social preview: stable facts only (company count), no daily-changing numbers
  const companies = (status.companies_tracked || 1500).toLocaleString('en-US');
  const css = `@font-face{font-family:IS;font-weight:400;src:url(file://${fonts}/instrument-sans-latin-400-normal.woff2)}
    @font-face{font-family:IS;font-weight:600;src:url(file://${fonts}/instrument-sans-latin-600-normal.woff2)}
    @font-face{font-family:PM;src:url(file://${fonts}/ibm-plex-mono-latin-400-normal.woff2)}
    body{margin:0;width:1280px;height:640px;background:#0B1416;font-family:IS;color:#EAF2F0;display:flex;flex-direction:column;justify-content:center;padding:0 96px;box-sizing:border-box}
    h1{font-size:76px;font-weight:600;line-height:1.05;margin:0 0 28px}
    .n{color:#2FBFAE}.a{color:#E9A93C}
    p{font-size:34px;color:#C9D8D5;margin:0 0 48px}
    .m{font-family:PM;font-size:26px;color:#7E9996}
    .bar{display:flex;gap:10px;margin-bottom:40px}.bar i{display:block;width:60px;height:12px;border-radius:6px;background:#2FBFAE}.bar i:last-child{background:#E9A93C}`;
  const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
  const social = path.join(root, 'data', 'social.html');
  fs.mkdirSync(path.dirname(social), { recursive: true });
  fs.writeFileSync(social, `<html><head><style>${css}</style></head><body>
    <div class="bar"><i></i><i></i><i></i><i></i></div>
    <h1>US tech hiring data,<br><span class="n">checked every day.</span></h1>
    <p>Every open job at <span class="a">${companies}</span> US tech companies, from their public job boards.</p>
    <div class="m">job-postings-pipeline · siddharthkumar.com</div></body></html>`);
  await page.goto('file://' + social);
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(root, 'assets/social-preview.png') });
  await page.close();

  // LinkedIn video: step the CSS animations of hero-square.svg frame by frame
  const svg = fs.readFileSync(path.join(root, 'assets/hero-square.svg'), 'utf8');
  const vid = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
  const html = path.join(root, 'data', 'hero-square.html');
  fs.writeFileSync(html, `<html><body style="margin:0;background:#0B1416">${svg.replace('<svg ', '<svg style="display:block;width:1080px;height:1080px" ')}</body></html>`);
  await vid.goto('file://' + html);
  await vid.waitForTimeout(500);
  const frames = path.join(root, 'data', 'frames');
  fs.rmSync(frames, { recursive: true, force: true });
  fs.mkdirSync(frames, { recursive: true });
  const fps = 30, seconds = 12;  // one 10 s loop plus 2 s more of the final frame
  for (let i = 0; i < fps * seconds; i++) {
    const t = Math.min(i / fps, 9.99) * 1000;
    await vid.evaluate((ms) => {
      for (const a of document.getAnimations()) {
        a.pause();
        const dur = a.effect.getComputedTiming().duration;
        a.currentTime = typeof dur === 'number' && dur > 0 ? ms % dur : ms;
      }
    }, t);
    await vid.screenshot({ path: path.join(frames, `f${String(i).padStart(4, '0')}.png`) });
  }
  await vid.close();
  await browser.close();
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(fps), '-i', path.join(frames, 'f%04d.png'),
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-movflags', '+faststart',
    path.join(root, 'media/linkedin-hero.mp4')]);
  console.log('social-preview.png and linkedin-hero.mp4 written');
})();
