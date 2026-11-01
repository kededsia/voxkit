#!/usr/bin/env bash
# Render every module to mp4, then join them into one film.
#
# `vox render <module>` gates the module first and refuses to draw a film that
# cannot pass its own checks, so this script is also the final audit: a module
# that fails appears in the log as REFUSED and its chapter is missing from the
# join. That is deliberate — a silently short film is worse than a loud refusal.
set -u

export PYTHONPATH=/d/VOX-PLUGIN-3
cd /d/VOX-PLUGIN-3/film || exit 1

LOG=build/_render.log
: > "$LOG"
say() { echo "$(date +%H:%M:%S)  $*" >> "$LOG"; }

MODULES="m01 m02 m03 m04 m05 m06 m07 m08 m09 m10 m11 m12 m13 m14 m15 m16 m17 m18 m19 m20 m21 m22"

# Resumable, but not gullible: a chapter is reused only if it is *newer* than the
# program it was drawn from. Rendering the film takes about an hour and a run that
# dies at chapter 20 must not start again at chapter 1 — but a chapter rendered
# before the last `emit` is a picture of a film that no longer exists, and reusing
# it would put a stale minute inside a fresh film. FORCE=1 redraws regardless.
for m in $MODULES; do
  out="remotion/out/$m-final.mp4"
  src="remotion/src/shots/$(echo "$m" | tr 'm' 'M').tsx"
  if [ -f "$out" ] && [ -f "$src" ] && [ "${FORCE:-0}" != "1" ] \
     && [ "$out" -nt "$src" ]; then
    say "$m already rendered and newer than its program — skipped"
    continue
  fi
  say "===== $m render START ====="
  py -u -m voxkit.cli render "$m" >> "$LOG" 2>&1
  say "===== $m render exit $? ====="
done

# Join the chapters that actually rendered, in module order.
#
# The paths in a concat list are resolved relative to the *list file*, not the
# shell's working directory — `file 'remotion/out/m01-final.mp4'` inside
# `build/_chapters.txt` looks for `build/remotion/out/...`. And a Git Bash path
# (`/d/VOX-PLUGIN-3/...`) is not a path ffmpeg understands on Windows. Both were
# wrong the first time this ran, and the failure is quiet: the join exits 127 and
# the film is simply not there. So the list is written with Windows absolute
# paths, and ffmpeg is required to exist before the loop starts.
FFMPEG=${FFMPEG:-ffmpeg}
FFPROBE=${FFPROBE:-ffprobe}
if ! command -v "$FFMPEG" >/dev/null 2>&1; then
  say "FATAL: $FFMPEG is not on PATH — the chapters rendered but cannot be joined"
  exit 1
fi
ROOT=$(pwd -W 2>/dev/null || pwd)

LIST=build/_chapters.txt
: > "$LIST"
for m in $MODULES; do
  f="remotion/out/$m-final.mp4"
  if [ -f "$f" ]; then
    echo "file '$ROOT/$f'" >> "$LIST"
  else
    say "MISSING chapter $m — not in the join"
  fi
done

if [ "$(grep -c "^file" "$LIST")" -gt 0 ]; then
  n=$(grep -c "^file" "$LIST")
  say "joining $n chapter(s)"
  "$FFMPEG" -hide_banner -loglevel error -y -f concat -safe 0 -i "$LIST" \
    -c copy remotion/out/tanah-air-full.mp4 >> "$LOG" 2>&1
  code=$?
  # A copy-join is only honest if the film is as long as its chapters. Stream
  # copy across chapters with different parameters does not fail — it truncates
  # or drifts, and a silently short film is exactly what this script exists to
  # avoid. So measure, and re-encode if the numbers disagree.
  # `ffprobe` cannot report a duration for a concat list — it answers N/A, and an
  # N/A compared against the joined film always "disagrees", which is how a
  # perfectly good copy-join gets re-encoded for no reason. The sum of the
  # chapters is the number that matters, and it is one ffprobe per chapter.
  want=$(grep "^file" "$LIST" | sed "s/^file '//; s/'$//" | while read -r f; do
           "$FFPROBE" -v error -i "$f" -show_entries format=duration -of csv=p=0
         done | awk '{s += $1} END {printf "%.2f", s}')
  got=$("$FFPROBE" -v error -i remotion/out/tanah-air-full.mp4 -show_entries format=duration \
        -of csv=p=0 2>/dev/null)
  say "join exit $code · wanted ${want}s · got ${got}s"
  if [ "$code" -ne 0 ] || [ -z "$got" ] || \
     ! awk -v a="$want" -v b="$got" 'BEGIN{exit !(b > a - 1.0)}'; then
    say "copy-join did not hold — re-encoding the join"
    ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$LIST" \
      -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
      -c:a aac -b:a 192k -movflags +faststart \
      remotion/out/tanah-air-full.mp4 >> "$LOG" 2>&1
    say "re-encode exit $?"
  fi
else
  say "nothing to join"
fi

say "ALL DONE"
