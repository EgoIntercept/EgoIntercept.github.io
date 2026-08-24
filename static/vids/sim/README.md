# Simulation clips

Drop web-ready `.mp4` files in this folder, then list them in the `SIMS`
array near the top of `static/js/main.js`:

```js
const SIMS = [
  { file:"static/vids/sim/rollout-01.mp4", title:"Policy rollout", sub:"Legged Gym", badge:"Sim" },
];
```

Also add a matching poster image at `static/img/posters/<same-name>.jpg`
(the page derives the poster path from the video filename):

```
ffmpeg -ss 1 -i static/vids/sim/rollout-01.mp4 -frames:v 1 -q:v 5 \
       static/img/posters/rollout-01.jpg
```

Recommended encode (keeps the page fast):

```
ffmpeg -i input.mov -vf "scale='min(1280,iw)':-2" -c:v libx264 -crf 25 \
       -preset medium -pix_fmt yuv420p -an -movflags +faststart out.mp4
```
