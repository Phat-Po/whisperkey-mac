"""End-to-end verification of the Doubao ASR fix.

Uses the REAL DoubaoStreamingASR class (not a reimplementation), feeding mic
audio in ~100ms chunks just like the app does. Speak when prompted.
"""
import sys
import time

# This script may be launched from /tmp; force the `main`-branch worktree onto
# sys.path[0] so we import the fixed doubao_asr.py (the shared .venv's editable
# install points at a different branch checkout that lacks it).
sys.path.insert(0, "/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main")

import numpy as np
import sounddevice as sd

from whisperkey_mac.config import load_config
from whisperkey_mac.doubao_asr import DoubaoConfig, DoubaoStreamingASR, is_configured

RECORD_SECONDS = 5
SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1600  # 100ms

cfg = load_config()
dcfg = DoubaoConfig(
    app_id=getattr(cfg, "doubao_app_id", ""),
    access_key=getattr(cfg, "doubao_access_key", ""),
    cluster=getattr(cfg, "doubao_cluster", "volc.bigasr.sauc.duration"),
)
if not is_configured(dcfg):
    print("ERROR: Doubao credentials not configured in settings.")
    sys.exit(1)

asr = DoubaoStreamingASR(dcfg)
asr.on_partial = lambda t: print(f"  [partial] {t!r}")
asr.on_final = lambda t: print(f"  [final]   {t!r}")
asr.on_error = lambda m: print(f"  [error]   {m}")

print("Connecting...")
if not asr.start():
    print("ERROR: connection failed.")
    sys.exit(1)
print("Connected.\n")

print(f">>> SPEAK NOW (recording {RECORD_SECONDS}s) <<<\n")
audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE,
               channels=1, dtype="float32")

# Feed in real-time ~100ms chunks while recording, like the app's recorder.
fed = 0
for _ in range(int(RECORD_SECONDS * SAMPLE_RATE / CHUNK_SAMPLES)):
    time.sleep(CHUNK_SAMPLES / SAMPLE_RATE)
    block = audio[fed:fed + CHUNK_SAMPLES]
    fed += CHUNK_SAMPLES
    pcm = (np.nan_to_num(block.flatten()) * 32767).astype(np.int16).tobytes()
    asr.feed_audio(pcm)
sd.wait()

asr.finish()
final_text = asr.stop(timeout_s=6.0)

print("\n" + "=" * 50)
if final_text.strip():
    print(f"✅ SUCCESS — recognized: {final_text!r}")
else:
    print("❌ STILL EMPTY — server returned no text.")
print("=" * 50)
