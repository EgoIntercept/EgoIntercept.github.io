# EgoIntercept.github.io

Project page for **EgoIntercept: Egocentric Object Interception with a Quadruped Robot**.

Static site — no build step. Open `index.html`, or serve locally with:

```
python3 -m http.server 8000
```

## Layout

```
index.html                  the whole page
static/css/style.css        styles
static/js/main.js           video lists + YouTube embed + BibTeX copy
static/vids/                web-encoded clips used by the page
static/vids/sim/            <- drop simulation clips here
static/vids/failures/       <- drop failure-case clips here
static/img/posters/         one .jpg poster per clip (same filename)
static/img/figs/            figures pulled from the paper
media/                      raw capture originals (git-ignored, too large to commit)
```

## Things to fill in

| What | Where |
|---|---|
| Paper link | `index.html`, the `Paper (coming soon)` button (the PDF is git-ignored for now) |
| Author names / affiliations | `index.html`, search for `Anonymous Authors` |
| YouTube video | `YOUTUBE_ID` at the top of `static/js/main.js` |
| arXiv link | `index.html`, the `arXiv (coming soon)` button |
| Code link | `index.html`, the `Code (coming soon)` button |
| Simulation clips | `SIMS` array in `static/js/main.js` |
| Failure clips | `FAILURES` array in `static/js/main.js` |
| BibTeX | `index.html`, `#bib-code` |

## Adding a video

1. Encode it small enough for GitHub Pages:

   ```
   ffmpeg -i input.mov -vf "scale='min(1280,iw)':-2" -c:v libx264 -crf 25 \
          -preset medium -pix_fmt yuv420p -an -movflags +faststart \
          static/vids/sim/my-clip.mp4
   ```

2. Make a poster with the **same filename**:

   ```
   ffmpeg -ss 1 -i static/vids/sim/my-clip.mp4 -frames:v 1 -q:v 5 \
          static/img/posters/my-clip.jpg
   ```

3. Add an entry to the matching array in `static/js/main.js`:

   ```js
   { file:"static/vids/sim/my-clip.mp4", cap:"Policy rollout" },
   ```

Clips load and play only while they are on screen, so the page stays light.

## Notes

- Raw `.mov` originals in `media/vids/` are git-ignored — several exceed GitHub's
  100 MB file limit.
- `static/vids/hero-reel.mp4` is the 12 catch clips concatenated (stream copy, no
  re-encode). Regenerate it with `ffmpeg -f concat -safe 0 -i list.txt -c copy
  -movflags +faststart hero-reel.mp4`.
- `static/img/figs/` also contains figures not currently used on the page
  (`teaser`, `sensor-model`, `throw-dist`, `ood`, `heat-*`, `rollout-*`, `filmstrip`) if you
  ever want to add more sections.
