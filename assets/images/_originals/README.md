# Full-resolution image originals

**Drop new photos here.** These files are the source of truth; everything in
`assets/images/people/`, `assets/images/banner/` and `assets/images/logos/` is
generated from them and is overwritten on every build.

```
people/   individual portraits
banner/   the group photo
logos/    institutional logos, supplied by the group — never downloaded
```

## Replacing or adding a photo

1. Put the file in the right subfolder. Any filename, any size — bigger is better.
2. Point the matching `source:` in `data/images.yml` at the new filename.
3. Run the build:

   ```
   python scripts/build_images.py
   ```

4. Commit both the original and the regenerated files.

Crops in `data/images.yml` are expressed as **fractions** of the image, not
pixels, so swapping in a higher-resolution version of the *same* photo needs no
change to the crop numbers.

## What the build does

- Crops to a consistent square, converts to grayscale, and gently normalises the
  black and white points so photos shot under different lighting sit at a
  comparable tonal range. This is levelling, not retouching.
- Writes a 1x and a 2x (retina) version of each image.
- Flattens the logos onto the page colour so their backgrounds are invisible.
  Institutional marks are never recoloured, redrawn or cropped into.
- Warns when an original is too small for the size it is being displayed at.

## Current state of the source images

The portraits supplied in August 2026 are **283 x 213 px**, which leaves only
213 px after a square crop. They are being displayed at 220 px, so the 2x
versions are upscaled and slightly soft. Roughly 450 px originals would fix this.

Eight of the nine were shot as a consistent set against a plain wall. Marc
Garcia-Borràs's is an outdoor photo framed much wider; it is cropped tight to sit
alongside the others, but the ivy background still differs and it is the softest
of the nine. A portrait matching the other eight would be a real improvement.
