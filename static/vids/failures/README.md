# Failure-case clips

Drop web-ready `.mp4` files in this folder, then list them in the `FAILURES`
array near the top of `static/js/main.js`:

```js
const FAILURES = [
  { file:"static/vids/failures/fov-edge-01.mp4", title:"Ball exits field of view", sub:"Detection dropout", badge:"Failure" },
];
```

Also add a matching poster image at `static/img/posters/<same-name>.jpg`
(the page derives the poster path from the video filename):

```
ffmpeg -ss 1 -i static/vids/failures/fov-edge-01.mp4 -frames:v 1 -q:v 5 \
       static/img/posters/fov-edge-01.jpg
```

Recommended encode (keeps the page fast):

```
ffmpeg -i input.mov -vf "scale='min(1280,iw)':-2" -c:v libx264 -crf 25 \
       -preset medium -pix_fmt yuv420p -an -movflags +faststart out.mp4
```
