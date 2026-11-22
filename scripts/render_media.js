// Render assets/social-preview.png (1280x640) and media/linkedin-hero.mp4 (1080x1080, 10 s, H.264)
// from the generated SVGs. Usage: node scripts/render_media.js   (needs playwright + ffmpeg)
// Canvas rule: every image's outermost background is #F3F8F7; cards inside are #FFFFFF with
// border #E2EAE8, radius 14px. scripts/check_canvas.js checks every committed image.
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
  const css = `@font-face{font-family:PJS;font-weight:400;src:url(file://${fonts}/plus-jakarta-sans-latin-400-normal.woff2)}
    @font-face{font-family:PJS;font-weight:600;src:url(file://${fonts}/plus-jakarta-sans-latin-600-normal.woff2)}
    @font-face{font-family:PJS;font-weight:700;src:url(file://${fonts}/plus-jakarta-sans-latin-700-normal.woff2)}
    *{box-sizing:border-box}
    body{margin:0;width:1280px;height:640px;background:#F3F8F7;font-family:PJS;color:#3D4B49;font-variant-numeric:tabular-nums;display:flex;flex-direction:column;padding:40px 40px 0}
    main{flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 56px;background:#FFFFFF;border:1px solid #E2EAE8;border-radius:14px}
    .brand{display:flex;align-items:center;gap:16px;color:#0B1416;font-weight:700;font-size:30px;margin-bottom:34px}
    h1{font-size:72px;font-weight:700;line-height:1.06;letter-spacing:-0.02em;margin:0 0 28px;color:#0B1416}
    h1 span{color:#0B7468}
    p{font-size:32px;margin:0;max-width:900px}
    footer{padding:30px 56px 34px;font-size:26px;color:#3D4B49;display:flex;justify-content:space-between}
    footer b{color:#0B1416;font-weight:600}`;
  const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
  const social = path.join(root, 'data', 'social.html');
  fs.mkdirSync(path.dirname(social), { recursive: true });
  // the SteadyData mark, as on the dashboard (src/jobpipe/site/build.py MARK)
  const mark = '<svg width="46" height="52" viewBox="10 7 44 50" aria-hidden="true"><defs><linearGradient id="sdm" x1="49" x2="15" y1="12" y2="52" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#1A9486"/><stop offset="1" stop-color="#5FE8D6"/></linearGradient></defs><path fill="none" stroke="url(#sdm)" stroke-linejoin="round" stroke-width="8" d="M41 14H22l-6.5 6.5v5L22 32h20l6.5 6.5v5L42 50H23"/><path fill="#D98E14" fill-rule="evenodd" d="M40.4 14a6.6 6.6 0 1 0 13.2 0 6.6 6.6 0 1 0-13.2 0m4.1 0a2.5 2.5 0 1 1 5 0 2.5 2.5 0 1 1-5 0"/><path fill="#5FE8D6" fill-rule="evenodd" d="M10.4 50a6.6 6.6 0 1 0 13.2 0 6.6 6.6 0 1 0-13.2 0m4.1 0a2.5 2.5 0 1 1 5 0 2.5 2.5 0 1 1-5 0"/></svg>';
  fs.writeFileSync(social, `<html><head><style>${css}</style></head><body><main>
    <div class="brand">${mark}US tech hiring data</div>
    <h1>US tech hiring data,<br><span>checked every day.</span></h1>
    <p>Every open job at ${companies} US tech companies, from their public job boards.</p></main>
    <footer><span>job-postings-pipeline</span><span>Built by <b>SteadyData</b> · steadydata.co</span></footer></body></html>`);
  await page.goto('file://' + social);
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(root, 'assets/social-preview.png') });
  await page.close();

  // LinkedIn video: step the CSS animations of hero-square.svg frame by frame
  // The SVG starts on its final frame for still previews; the video plays the story from
  // the first beat instead, so the start-on-final-frame delay is removed here.
  const svg = fs.readFileSync(path.join(root, 'assets/hero-square.svg'), 'utf8')
    .replace(/\*\{animation-delay:-[\d.]+s!important\}/, '');
  const vid = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
  const html = path.join(root, 'data', 'hero-square.html');
  fs.writeFileSync(html, `<html><body style="margin:0;background:#F3F8F7">${svg.replace('<svg ', '<svg style="display:block;width:1080px;height:1080px" ')}</body></html>`);
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
