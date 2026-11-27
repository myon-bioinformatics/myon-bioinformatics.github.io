import "./composition.js";
import { progressionNotes, audioPlan, createAudioPlayer } from "./studio-audio.js";

const byId = id => document.getElementById(id);
const player = createAudioPlayer(() => import("../vendor/tone-studio.min.js"));
const status = byId("song-status");
byId("song-audio").hidden = false;
let generation = 0;
function stop() {
  generation++;
  player.stop();
  status.textContent = "停止しました。";
}
byId("song-stop").onclick = stop;
window.addEventListener("pagehide", stop);
byId("song-play").onclick = async () => {
  stop();
  const current = generation;
  byId("song-arrange").click();
  const progression = byId("song-progression").value;
  if (!progression || !byId("song-bpm").reportValidity()) return;
  try {
    const notes = progressionNotes(byId("song-key").value, progression);
    const count = await player.play(audioPlan(notes.join(" "), Number(byId("song-bpm").value), 8));
    if (current === generation) status.textContent = count + "音を再生します。";
  } catch (error) {
    if (current === generation) status.textContent = "試聴できません: " + error.message;
  }
};
