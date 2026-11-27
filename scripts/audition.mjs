// Play the frequency and timing supplied by the editor. Tone loads on first gesture.
let generation = 0;
let voice;
function stop() {
  generation++;
  voice?.dispose();
  voice = undefined;
}
document.addEventListener("studio-audio-stop", stop);
window.addEventListener("pagehide", stop);
document.addEventListener("studio-audio-play", async ({detail: {notes, report}}) => {
  stop();
  const current = generation;
  try {
    const tone = await import("../vendor/tone-studio.min.js");
    if (current !== generation) return;
    await tone.start();
    if (current !== generation) return;
    voice = new tone.Synth({volume: -18}).toDestination();
    const start = tone.now() + 0.05;
    for (const note of notes) voice.triggerAttackRelease(note.hz, note.duration, start + note.start);
    report(notes.length + "音を再生します。");
  } catch (error) {
    if (current === generation) {
      stop();
      report("試聴できません: " + error.message);
    }
  }
});
document.getElementById("song-audio").hidden = false;
