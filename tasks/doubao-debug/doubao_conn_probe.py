"""Non-speaking connection probe: connect exactly like the app, feed silence,
report WHEN and WHY the server closes (close code/reason/timing)."""
import sys, time, struct, uuid
sys.path.insert(0, "/Users/pohanlee/.superset/worktrees/7bebcb78-6e19-4614-b38f-882c25c2c994/main")
import websocket
from whisperkey_mac.config import load_config
from whisperkey_mac import doubao_asr as d

cfg = load_config()
asr = d.DoubaoStreamingASR(d.DoubaoConfig(
    app_id=getattr(cfg, "doubao_app_id", ""),
    access_key=getattr(cfg, "doubao_access_key", ""),
))
init = asr._build_connect_message()
cid = str(uuid.uuid4())
headers = [
    f"X-Api-App-Key: {cfg.doubao_app_id}",
    f"X-Api-Access-Key: {cfg.doubao_access_key}",
    f"X-Api-Resource-Id: {d.RESOURCE_ID}",
    f"X-Api-Connect-Id: {cid}",
]

t0 = time.time()
closed_reason = None
ws = websocket.WebSocket()
try:
    ws.connect(d.ASR_ENDPOINT, header=headers, timeout=10)
    print(f"[{time.time()-t0:.2f}s] TCP/WS connected")
    ws.send_binary(init)
    print(f"[{time.time()-t0:.2f}s] init sent")

    silence = b"\x00" * 3200  # 100ms of 16k/16-bit silence
    ws.settimeout(0.5)
    closed_reason = None
    for i in range(40):  # up to ~4s
        try:
            ws.send_binary(d._build_message(d.MSG_TYPE_AUDIO_ONLY, silence, flags=d.NO_SEQUENCE, compress=False))
        except Exception as e:
            closed_reason = f"SEND failed: {type(e).__name__}: {e}"
            break
        try:
            data = ws.recv()
            mt, fl, payload = d._parse_message(data if isinstance(data, bytes) else data.encode())
            dur = (payload or {}).get("audio_info", {}).get("duration", "?")
            print(f"[{time.time()-t0:.2f}s] recv: dur={dur} flags={fl}")
        except websocket.WebSocketTimeoutException:
            pass
        except Exception as e:
            closed_reason = f"RECV closed: {type(e).__name__}: {e}"
            break
        time.sleep(0.1)

    print(f"[{time.time()-t0:.2f}s] loop done. closed_reason={closed_reason}")
    print(f"   close_status_code={getattr(ws,'close_status_code',None)} close_reason={getattr(ws,'close_reason',None)}")
except Exception as e:
    print(f"[{time.time()-t0:.2f}s] CONNECT failed: {type(e).__name__}: {e}")
finally:
    try: ws.close()
    except Exception: pass

if (time.time()-t0) > 3.5 and closed_reason is None:
    print("\n>>> VERDICT: connection STAYED OPEN ~4s with silence → server is healthy; app issue is timing/audio-specific.")
else:
    print("\n>>> VERDICT: connection CLOSED early → server-side rejection (concurrency/rate limit or session cap).")
