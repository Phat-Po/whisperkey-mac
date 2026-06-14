"""Reproduce the app failure: feed silence through the REAL DoubaoStreamingASR
class at two cadences. If 20ms (app) closes the socket but 100ms doesn't, the
chunk size/rate is the culprit and coalescing to ~100ms is the fix."""
import sys, time, subprocess
sys.path.insert(0, "/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main")
from whisperkey_mac.config import load_config
from whisperkey_mac import doubao_asr as d

cfg = load_config()

def recv_errs():
    r = subprocess.run(["grep", "-c", "event=doubao_recv_error", "/tmp/whisperkey-diag.log"],
                       capture_output=True, text=True)
    return int((r.stdout or "0").strip() or 0)

def run(chunk_bytes, interval, secs, label):
    before = recv_errs()
    asr = d.DoubaoStreamingASR(d.DoubaoConfig(
        app_id=getattr(cfg, "doubao_app_id", ""), access_key=getattr(cfg, "doubao_access_key", "")))
    asr.start()
    chunk = b"\x00" * chunk_bytes
    for _ in range(int(secs / interval)):
        asr.feed_audio(chunk)
        time.sleep(interval)
    connected_end = asr.is_connected
    asr.finish()
    asr.stop(timeout_s=3)
    after = recv_errs()
    closed = (after - before) > 0
    print(f"{label}: chunk={chunk_bytes}B every {int(interval*1000)}ms "
          f"→ {'❌ SERVER CLOSED mid-stream' if closed else '✅ stayed open'} "
          f"(recv_errors+={after-before})")

print("Testing app cadence (20ms / 640B)...")
run(640, 0.02, 4, "APP-CADENCE  ")
time.sleep(4)
print("Testing probe cadence (100ms / 3200B)...")
run(3200, 0.10, 4, "PROBE-CADENCE")
