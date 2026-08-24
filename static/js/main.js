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

/* ---- YouTube -------------------------------------------------------------
   Paste the 11-character video ID here once the video is up, e.g.
       const YOUTUBE_ID = "dQw4w9WgXcQ";
   Leave it "" and the page shows a "coming soon" panel instead.            */
const YOUTUBE_ID = "";

/* ---- Real-world catches -------------------------------------------------- */
const CATCHES = [
  { file:"static/vids/catch-forward-01.mp4",     cap:"<b>Forward</b>" },
  { file:"static/vids/catch-forward-02.mp4",     cap:"<b>Forward</b>" },
  { file:"static/vids/catch-forward-03.mp4",     cap:"<b>Forward</b>" },
  { file:"static/vids/catch-front-left-01.mp4",  cap:"<b>Front-left</b>" },
  { file:"static/vids/catch-left-01.mp4",        cap:"<b>Left</b>" },
  { file:"static/vids/catch-front-right-01.mp4", cap:"<b>Front-right</b>" },
  { file:"static/vids/catch-near-01.mp4",        cap:"<b>Near</b>" },
  { file:"static/vids/catch-near-02.mp4",        cap:"<b>Near</b>" },
  { file:"static/vids/catch-near-03.mp4",        cap:"<b>Near</b> &middot; extended sequence" },
  { file:"static/vids/catch-back-01.mp4",        cap:"<b>Back</b>" },
  { file:"static/vids/catch-back-02.mp4",        cap:"<b>Back</b>" },
  { file:"static/vids/catch-back-right-01.mp4",  cap:"<b>Back-right</b>" },
];

/* ---- Onboard perception (RGB | depth | third-person) --------------------- */
const ONBOARD = [
  { file:"static/vids/onboard-01.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
  { file:"static/vids/onboard-02.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
  { file:"static/vids/onboard-03.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
  // Also encoded and available:
  // { file:"static/vids/onboard-04.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
  // { file:"static/vids/onboard-05.mp4", cap:"Onboard RGB &middot; aligned depth &middot; third-person view" },
];

/* ---- Simulation ----------------------------------------------------------
   Put clips in static/vids/sim/ and list them here, e.g.
     { file:"static/vids/sim/rollout-01.mp4", cap:"Policy rollout" },        */
const SIMS = [];

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
      <video muted loop playsinline preload="none"
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
        if (!v.src) v.src = v.dataset.src;
        v.play().catch(() => {});
      } else {
        v.pause();
      }
    });
  }, { rootMargin: "200px 0px", threshold: 0.2 });
  document.querySelectorAll("video[data-src]").forEach(v => io.observe(v));
}

function initYouTube() {
  const host = document.getElementById("yt");
  if (!host || !YOUTUBE_ID) return;
  host.innerHTML = `
    <div class="facade" role="button" tabindex="0" aria-label="Play the overview video">
      <img src="https://i.ytimg.com/vi/${YOUTUBE_ID}/maxresdefault.jpg" alt="">
      <div class="play"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>
    </div>`;
  const load = () => {
    host.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${YOUTUBE_ID}?autoplay=1&rel=0"
      title="EgoIntercept overview video"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen></iframe>`;
  };
  const f = host.querySelector(".facade");
  f.addEventListener("click", load);
  f.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); load(); }
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
  fill("grid-catches",  CATCHES);
  fill("grid-onboard",  ONBOARD);
  fill("grid-sim",      SIMS,     "Simulation rollouts");
  fill("grid-failures", FAILURES, "Failure cases");
  lazyPlay();
  initYouTube();
  initCopy();
});
