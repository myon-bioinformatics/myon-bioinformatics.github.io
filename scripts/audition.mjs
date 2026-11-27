// Synthesize the notes supplied by the editor. Load Tone on the first play gesture.
let generation = 0;
let voice;
let frame;
let clearPosition;
function stop() {
  generation++;
  cancelAnimationFrame(frame);
  voice?.dispose();
  voice = undefined;
  clearPosition?.();
  clearPosition = undefined;
}
document.addEventListener("studio-audio-stop", stop);
window.addEventListener("pagehide", stop);
document.addEventListener("studio-audio-play", async ({detail: {notes, report, position}}) => {
  stop();
  const current = generation;
  try {
    const tone = await import("../vendor/tone-studio.min.js");
    if (current !== generation) return;
    await tone.start();
    if (current !== generation) return;
    voice = new tone.Synth({volume: -18}).toDestination();
    const start = tone.now() + 0.05;
    const context = tone.getContext().rawContext;
    const end = Math.max(...notes.map(note => note.start + note.duration));
    for (const note of notes) voice.triggerAttackRelease(note.hz, note.duration, start + note.start);
    clearPosition = () => position?.(null);
    function update() {
      const elapsed = context.currentTime - start;
      if (elapsed >= end) {
        clearPosition();
        clearPosition = undefined;
        report("試聴が終わりました。");
        return;
      }
      if (elapsed >= 0) position?.(elapsed);
      frame = requestAnimationFrame(update);
    }
    frame = requestAnimationFrame(update);
    report(notes.length + "音を再生します。");
  } catch (error) {
    if (current === generation) {
      stop();
      report("試聴できません: " + error.message);
    }
  }
});
document.getElementById("song-audio").hidden = false;
