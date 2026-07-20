import { readonly, ref } from "vue";

/**
 * Module-level state driving a thin top-of-page progress bar during router
 * navigations (route guards awaiting `auth.init`, lazy-loaded view chunks, ...).
 * Kept out of a component so a single instance is shared by the bar and by the
 * router hooks that start/finish it.
 */
const active = ref(false);
const progress = ref(0);

let trickleTimer: ReturnType<typeof setInterval> | undefined;
let doneTimer: ReturnType<typeof setTimeout> | undefined;

function clearTimers(): void {
  if (trickleTimer !== undefined) {
    clearInterval(trickleTimer);
    trickleTimer = undefined;
  }
  if (doneTimer !== undefined) {
    clearTimeout(doneTimer);
    doneTimer = undefined;
  }
}

/** Begin a navigation: show the bar and ease it towards ~90%. */
function start(): void {
  clearTimers();
  active.value = true;
  progress.value = 0.08;
  trickleTimer = setInterval(() => {
    const remaining = 0.9 - progress.value;
    if (remaining > 0.01) {
      progress.value += Math.min(0.02 + Math.random() * 0.03, remaining);
    }
  }, 200);
}

/** Finish the current navigation: fill the bar, then fade it out. */
function done(): void {
  clearTimers();
  if (!active.value) {
    return;
  }
  progress.value = 1;
  doneTimer = setTimeout(() => {
    active.value = false;
    progress.value = 0;
  }, 250);
}

export function useNavigationProgress() {
  return {
    active: readonly(active),
    progress: readonly(progress),
    start,
    done,
  };
}
