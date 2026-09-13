/* ==========================================================================
   EgoIntercept — project page
   --------------------------------------------------------------------------
   TO ADD OR CHANGE VIDEOS: edit the arrays below. Each entry is
       { file, cap }
     file – path to the .mp4, relative to the site root
     cap  – caption shown under the clip (HTML allowed)
   A poster image is looked up automatically at
       static/img/posters/<same filename>.jpg
   ========================================================================== */

/* ---- Real-world catches, slow motion ------------------------------------
   Shot at 240 fps and retimed to 30 fps, i.e. 0.125x real time.
   Shown one per row, full width. Filenames carry a -slowmo suffix.        */
const SLOWMO = [
  { file:"static/vids/catch-forward-01-slowmo.mp4",     cap:"<b>Forward</b> &middot; 0.125&times; real time" },
  { file:"static/vids/catch-front-left-01-slowmo.mp4",  cap:"<b>Front-left</b> &middot; 0.125&times; real time" },
  { file:"static/vids/catch-front-right-01-slowmo.mp4", cap:"<b>Front-right</b> &middot; 0.125&times; real time" },
  { file:"static/vids/catch-back-01-slowmo.mp4",        cap:"<b>Back</b> &middot; 0.125&times; real time" },
  { file:"static/vids/catch-back-02-slowmo.mp4",        cap:"<b>Back</b> &middot; 0.125&times; real time" },
  { file:"static/vids/catch-back-right-01-slowmo.mp4",  cap:"<b>Left</b> &middot; 0.125&times; real time" },
  { file:"static/vids/catch-near-03-slowmo.mp4",        cap:"<b>Near</b> &middot; 0.125&times; real time" },
];

/* ---- Real-world catches, full speed -------------------------------------
   Shown two per row.                                                       */
const CATCHES = [
  { file:"static/vids/catch-forward-02.mp4",     cap:"<b>Forward</b>" },
  { file:"static/vids/catch-forward-03.mp4",     cap:"<b>Forward</b>" },
  { file:"static/vids/catch-left-01.mp4",        cap:"<b>Left</b>" },
  { file:"static/vids/catch-near-01.mp4",        cap:"<b>Near</b>" },
  { file:"static/vids/catch-near-02.mp4",        cap:"<b>Near</b>" },
];

/* ---- Onboard perception (RGB | depth | third-person) --------------------- */
const ONBOARD = [
  { file:"static/vids/onboard-01.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
  // Also encoded and available:
  // { file:"static/vids/onboard-02.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
  // { file:"static/vids/onboard-03.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
  // { file:"static/vids/onboard-04.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
  // { file:"static/vids/onboard-05.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
];

/* ---- Simulation ----------------------------------------------------------
   Put clips in static/vids/sim/ and list them here. Pane labels and the
   marker legend are burned into the clips by tools/label-sim-rollout.sh.   */
const SIMS = [
  { file:"static/vids/sim/sim-rollout-01.mp4",
    cap:"Policy rollout &middot; onboard camera (left) and external view (right)" },
];

/* ---- Failure cases -------------------------------------------------------
   Put clips in static/vids/failures/ and list them here, e.g.
     { file:"static/vids/failures/fov-edge.mp4", cap:"Ball exits field of view" }, */
const FAILURES = [];

/* ========================================================================== */

const posterFor = f => "static/img/posters/" + f.split("/").pop().replace(/\.mp4$/, ".jpg");

function fill(id, list, placeholder) {
  const grid = document.getElementById(id);
  if (!grid) return;
  if (!list.length) {
    if (placeholder) {
      grid.innerHTML = Array.from({ length: 3 },
        () => `<div class="soon">${placeholder}<br>coming soon</div>`).join("");
    }
    return;
  }
  grid.innerHTML = list.map(v => `
    <div class="vitem">
      <video muted loop playsinline controls controlslist="nodownload" preload="none"
             poster="${posterFor(v.file)}" data-src="${v.file}"></video>
      <div class="cap">${v.cap}</div>
    </div>`).join("");
}

/* Load and play each clip only while it is on screen — keeps the page light. */
function lazyPlay() {
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      const v = e.target;
      if (e.isIntersecting) {
        v.dataset.vis = "1";
        if (!v.src) v.src = v.dataset.src;
        if (!v.dataset.held) start(v);
      } else {
        delete v.dataset.vis;
        if (!v.paused) {
          v.dataset.auto = "1";   /* not the viewer pausing — do not remember it */
          v.pause();
        }
      }
    });
  }, { rootMargin: "200px 0px", threshold: 0.2 });

  document.querySelectorAll("video[data-src]").forEach(v => {
    /* A pause the viewer asked for sticks: scrolling past will not restart it.
       Pauses we trigger when a clip leaves the viewport are marked first. */
    v.addEventListener("pause", () => {
      if (v.dataset.auto) delete v.dataset.auto;
      else if (!v.ended) v.dataset.held = "1";
    });
    v.addEventListener("play", () => { delete v.dataset.held; });
    io.observe(v);
  });
}

/* Setting src and calling play() in the same tick makes Chrome abort the
   request, leaving the clip stuck on its poster. Retry once it has data. */
function start(v) {
  v.play().catch(() => {
    v.addEventListener("canplay", () => {
      if (v.dataset.vis && !v.dataset.held) v.play().catch(() => {});
    }, { once: true });
  });
}

function initCopy() {
  const btn = document.getElementById("copy-bib");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(document.getElementById("bib-code").textContent.trim());
      btn.textContent = "Copied";
      setTimeout(() => (btn.textContent = "Copy"), 1600);
    } catch { btn.textContent = "Press ⌘C"; }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  fill("grid-slowmo",   SLOWMO);
  fill("grid-catches",  CATCHES);
  fill("grid-onboard",  ONBOARD);
  fill("grid-sim",      SIMS,     "Simulation rollouts");
  fill("grid-failures", FAILURES, "Failure cases");
  lazyPlay();
  initCopy();
});
