#!/usr/bin/env python3
"""
Real human speech accuracy test.
Records from microphone, then runs all 3 ASR models for comparison.
"""

import subprocess
import os
import sys
import re
import time
import soundfile as sf
import numpy as np

# ── Config ──────────────────────────────────────────────────────
SAMPLE_RATE = 16000
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_samples")
RECORD_SECONDS = 10  # max per sentence

_TR_MAP = {
    '語': '语', '輸': '输', '術': '术', '讓': '让', '電': '电', '腦': '脑',
    '聽': '听', '類': '类', '說': '说', '話': '话', '內': '内', '氣': '气',
    '慧': '慧', '變': '变', '們': '们', '從': '从', '助': '助', '駛': '驶',
    '發': '发', '實': '实', '際': '际', '運': '运', '過': '过', '個': '个',
    '對': '对', '開': '开', '關': '关', '機': '机', '點': '点', '會': '会',
    '時': '时', '問': '问', '題': '题', '這': '这', '為': '为', '無': '无',
    '來': '来', '給': '给', '進': '进', '還': '还', '錯': '错', '買': '买',
    '賣': '卖', '錢': '钱', '東': '东', '西': '西', '想像': '想象',
}


def to_simplified(text):
    return ''.join(_TR_MAP.get(c, c) for c in text)


def strip_punct(text):
    return re.sub(r'[，。！？、；：""''（）\s,\.!?;:\'"()\[\]{}]', '', text)


def calc_accuracy(ref, hyp):
    ref = strip_punct(to_simplified(ref))
    hyp = strip_punct(to_simplified(hyp))
    if not ref:
        return 100.0 if not hyp else 0.0
    if not hyp:
        return 0.0
    m, n = len(ref), len(hyp)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return (1 - dp[m][n] / max(m, n)) * 100


def record_audio(filename, max_seconds=10):
    """Record from microphone using sounddevice, save as 16kHz WAV."""
    import sounddevice as sd

    wav_path = os.path.join(AUDIO_DIR, filename)
    print(f"  Recording up to {max_seconds}s... (speak, then press Ctrl+C when done)")
    print(f"  (or wait {max_seconds}s for auto-stop)")

    try:
        audio = sd.rec(
            int(max_seconds * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )
        sd.wait()
    except KeyboardInterrupt:
        pass

    # Find actual end (trim silence)
    audio = audio.flatten()
    # Find last non-silence sample
    threshold = 0.01
    non_silent = np.where(np.abs(audio) > threshold)[0]
    if len(non_silent) > 0:
        end = non_silent[-1] + int(0.5 * SAMPLE_RATE)  # add 0.5s padding
        end = min(end, len(audio))
        audio = audio[:end]

    sf.write(wav_path, audio, SAMPLE_RATE)
    duration = len(audio) / SAMPLE_RATE
    print(f"  Saved: {wav_path} ({duration:.1f}s)")
    return wav_path, duration


def test_faster_whisper(wav_path):
    """Test with faster-whisper small."""
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    t0 = time.time()
    segments, info = model.transcribe(wav_path, language="zh")
    text = "".join(seg.text for seg in segments)
    elapsed = time.time() - t0
    return text, elapsed


def test_paraformer_offline(wav_path):
    """Test with Paraformer offline batch."""
    from funasr import AutoModel
    model = AutoModel(
        model="paraformer-zh",
        vad_model="damo/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        punc_model="damo/punc_ct-transformer_cn-en-common-vocab471067-large",
        device="cpu",
        disable_update=True,
    )
    audio, sr = sf.read(wav_path, dtype="float32")
    t0 = time.time()
    res = model.generate(input=audio, batch_size_s=300)
    elapsed = time.time() - t0
    text = res[0]["text"] if res and res[0].get("text") else ""
    return text, elapsed


def test_paraformer_streaming(wav_path):
    """Test with Paraformer streaming (1s chunks, combined)."""
    from funasr import AutoModel
    model = AutoModel(
        model="paraformer-zh-streaming",
        device="cpu",
        disable_update=True,
    )
    audio, sr = sf.read(wav_path, dtype="float32")
    chunk_stride = int(1.0 * sr)
    total_chunks = int((len(audio) - 1) / chunk_stride + 1)

    cache = {}
    chunk_texts = []
    for i in range(total_chunks):
        chunk = audio[i * chunk_stride:(i + 1) * chunk_stride]
        is_final = i == total_chunks - 1
        t0 = time.time()
        res = model.generate(
            input=chunk,
            cache=cache,
            is_final=is_final,
            chunk_size=[0, 10, 5],
            encoder_chunk_look_back=4,
            decoder_chunk_look_back=1,
        )
        text = res[0]["text"] if res and res[0].get("text") else ""
        chunk_texts.append(text)

    combined = "".join(chunk_texts)
    return combined, chunk_texts


SENTENCES = {
    "real1": None,  # user fills in
    "real2": None,
    "real3": None,
}


def main():
    print("=" * 60)
    print("REAL SPEECH ACCURACY TEST")
    print("=" * 60)
    print()
    print("You will record 3 sentences. For each:")
    print("  1. I'll prompt you to speak")
    print("  2. Press Enter to start recording")
    print("  3. Speak the sentence")
    print("  4. Press Ctrl+C to stop recording")
    print()

    os.makedirs(AUDIO_DIR, exist_ok=True)

    # Check microphone
    try:
        import sounddevice as sd
        print("Available audio devices:")
        print(sd.query_devices())
        print()
    except Exception as e:
        print(f"ERROR: Cannot access microphone: {e}")
        print("Make sure microphone permission is granted.")
        sys.exit(1)

    # Step 1: Record
    print("=" * 60)
    print("STEP 1: RECORD AUDIO")
    print("=" * 60)

    recordings = []
    prompts = [
        ("real1", "Sentence 1: Say any short Chinese sentence (e.g. 你好今天天气怎么样)"),
        ("real2", "Sentence 2: Say a medium sentence (e.g. 我想用语音输入法打字)"),
        ("real3", "Sentence 3: Say a longer sentence (e.g. 人工智能正在改变我们的生活方式)"),
    ]

    for name, prompt in prompts:
        print(f"\n  {prompt}")
        input("  Press Enter when ready to speak...")
        wav_path, duration = record_audio(f"{name}.wav")
        recordings.append((name, wav_path, duration))

    # Step 2: Get ground truth
    print("\n" + "=" * 60)
    print("STEP 2: ENTER GROUND TRUTH")
    print("=" * 60)
    print("For each recording, type exactly what you said (in traditional or simplified Chinese):")

    ground_truths = {}
    for name, wav_path, duration in recordings:
        print(f"\n  [{name}] ({duration:.1f}s)")
        gt = input("  What did you say? > ").strip()
        ground_truths[name] = gt

    # Step 3: Run all models
    print("\n" + "=" * 60)
    print("STEP 3: RUN ASR MODELS")
    print("=" * 60)

    results = {}
    for name, wav_path, duration in recordings:
        gt = ground_truths[name]
        print(f"\n  [{name}] Ground truth: {gt}")
        print(f"  Duration: {duration:.1f}s")

        # faster-whisper
        print("    Running faster-whisper...")
        fw_text, fw_time = test_faster_whisper(wav_path)
        fw_acc = calc_accuracy(gt, fw_text)
        print(f"      Result: {fw_text}")
        print(f"      Accuracy: {fw_acc:.1f}% ({fw_time:.2f}s)")

        # Paraformer offline batch
        print("    Running Paraformer offline batch...")
        pf_text, pf_time = test_paraformer_offline(wav_path)
        pf_acc = calc_accuracy(gt, pf_text)
        print(f"      Result: {pf_text}")
        print(f"      Accuracy: {pf_acc:.1f}% ({pf_time:.2f}s)")

        # Paraformer streaming
        print("    Running Paraformer streaming (1s chunks)...")
        ps_text, ps_chunks = test_paraformer_streaming(wav_path)
        ps_acc = calc_accuracy(gt, ps_text)
        print(f"      Combined: {ps_text}")
        print(f"      Chunks: {ps_chunks}")
        print(f"      Accuracy: {ps_acc:.1f}%")

        results[name] = {
            "ground_truth": gt,
            "duration": duration,
            "faster_whisper": {"text": fw_text, "accuracy": fw_acc, "time": fw_time},
            "paraformer_batch": {"text": pf_text, "accuracy": pf_acc, "time": pf_time},
            "paraformer_stream": {"text": ps_text, "accuracy": ps_acc, "chunks": ps_chunks},
        }

    # Step 4: Summary
    print("\n" + "=" * 60)
    print("ACCURACY SUMMARY")
    print("=" * 60)

    print(f"\n{'Name':<8} {'Duration':<10} {'faster-whisper':<15} {'Paraformer Batch':<17} {'Paraformer Stream':<17}")
    print("-" * 70)

    for name in results:
        r = results[name]
        print(
            f"{name:<8} {r['duration']:<10.1f}s "
            f"{r['faster_whisper']['accuracy']:<15.1f}% "
            f"{r['paraformer_batch']['accuracy']:<17.1f}% "
            f"{r['paraformer_stream']['accuracy']:<17.1f}%"
        )

    print("\n" + "=" * 60)
    print("DETAILED RESULTS")
    print("=" * 60)

    for name in results:
        r = results[name]
        print(f"\n  [{name}] ({r['duration']:.1f}s)")
        print(f"    Ground truth: {r['ground_truth']}")
        print(f"    faster-whisper:   {r['faster_whisper']['text']}  ({r['faster_whisper']['accuracy']:.1f}%, {r['faster_whisper']['time']:.2f}s)")
        print(f"    Paraformer batch: {r['paraformer_batch']['text']}  ({r['paraformer_batch']['accuracy']:.1f}%, {r['paraformer_batch']['time']:.2f}s)")
        print(f"    Paraformer stream: {r['paraformer_stream']['text']}  ({r['paraformer_stream']['accuracy']:.1f}%)")

    print("\nDone.")


if __name__ == "__main__":
    main()
