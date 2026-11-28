import {startTask} from "./async-task.js";

// Synthesize the notes supplied by the editor. Load Tone on the first play gesture.
let generation = 0;
let voice;
let frame;
let clearPosition;
let startup;
function stop() {
  generation++;
  startup?.cancel();
  startup = undefined;
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
    startup = startTask(async signal => {
      const tone = await import("../vendor/tone-studio.min.js");
      signal.throwIfAborted();
      await tone.start();
      return tone;
    }, {timeoutMs: 4000});
    const tone = await startup.promise;
    if (current !== generation) return;
    startup = undefined;
    voice = new tone.Synth({volume: -18, oscillator: {type: "sine"}}).toDestination();
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
      report(error.name === "TimeoutError"
        ? "音源の起動がタイムアウトしました。"
        : "試聴できません: " + error.message);
    }
  }
});
document.getElementById("song-audio").hidden = false;
