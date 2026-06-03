#!/usr/bin/env python3
"""
Accuracy test for FunASR Paraformer: batch vs streaming (1s chunk).
Uses macOS TTS-generated Chinese speech with known ground truth.
Normalizes to simplified Chinese + strips punctuation for fair comparison.
"""

import subprocess
import os
import sys
import re
import time
import glob
import soundfile as sf
import numpy as np

# ── Config ──────────────────────────────────────────────────────
SAMPLE_RATE = 16000
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_samples")
CHUNK_SECONDS = 1.0

# Traditional-to-Simplified mapping (targeted for test sentences)
_TR_MAP = {
    '語': '语', '輸': '输', '術': '术', '讓': '让', '電': '电', '腦': '脑',
    '聽': '听', '類': '类', '說': '说', '話': '话', '內': '内', '氣': '气',
    '慧': '慧', '變': '变', '們': '们', '從': '从', '助': '助', '駛': '驶',
    '發': '发', '實': '实', '際': '际', '運': '运', '過': '过', '個': '个',
    '對': '对', '開': '开', '關': '关', '機': '机', '點': '点', '會': '会',
    '時': '时', '問': '问', '題': '题', '這': '这', '為': '为', '無': '无',
    '來': '来', '給': '给', '進': '进', '還': '还', '錯': '错', '買': '买',
    '賣': '卖', '錢': '钱', '東': '东', '西': '西', '長': '长', '短': '短',
    '多': '多', '少': '少', '快': '快', '慢': '慢', '新': '新', '舊': '旧',
    '高': '高', '低': '低', '遠': '远', '近': '近', '深': '深', '淺': '浅',
    '寬': '宽', '窄': '窄', '重': '重', '輕': '轻', '強': '强', '弱': '弱',
    '軟': '软', '硬': '硬', '冷': '冷', '熱': '热', '愛': '爱', '笑': '笑',
    '哭': '哭', '明': '明', '暗': '暗', '紅': '红', '藍': '蓝', '綠': '绿',
    '黃': '黄', '紫': '紫', '買': '买', '賣': '卖', '錯': '错', '對': '对',
    '進': '进', '還': '还', '開': '开', '關': '关', '機': '机', '點': '点',
    '會': '会', '時': '时', '問': '问', '題': '题', '實': '实', '際': '际',
    '個': '个', '與': '与', '無': '无', '來': '来', '給': '给', '過': '过',
}


def to_simplified(text):
    """Convert traditional Chinese to simplified."""
    return ''.join(_TR_MAP.get(c, c) for c in text)


def strip_punct(text):
    """Remove punctuation and whitespace for character-level comparison."""
    return re.sub(r'[，。！？、；：""''（）\s,\.!?;:\'"()\[\]{}]', '', text)


# Test sentences with ground truth (traditional)
TEST_SENTENCES = {
    "short": "你好，今天天氣真好。",
    "medium": "語音輸入技術讓電腦可以聽懂人類說話的內容。",
    "long": "人工智慧正在改變我們的生活方式，從語音助理到自動駕駛，科技的發展速度超乎想像。",
}


def generate_test_audio():
    """Generate 16kHz mono WAV from macOS TTS for each test sentence."""
    os.makedirs(AUDIO_DIR, exist_ok=True)

    for name, text in TEST_SENTENCES.items():
        aiff_path = os.path.join(AUDIO_DIR, f"{name}.aiff")
        wav_path = os.path.join(AUDIO_DIR, f"{name}.wav")

        if os.path.exists(wav_path):
            print(f"  [skip] {name}.wav already exists")
            continue

        print(f"  [gen]  {name}: \"{text}\"")
        subprocess.run(
            ["say", "-v", "Tingting", "-o", aiff_path, text],
            check=True,
        )
        # Convert to 16kHz mono WAV
        subprocess.run(
            [
                "afconvert", "-f", "WAVE", "-d", "LEI16",
                "-c", "1", "-r", str(SAMPLE_RATE),
                aiff_path, wav_path,
            ],
            check=True,
        )
        os.remove(aiff_path)

    print(f"Audio samples in: {AUDIO_DIR}\n")


def load_audio():
    """Load all test WAV files and return dict of {name: (audio, ground_truth)}."""
    samples = {}
    for name, ground_truth in TEST_SENTENCES.items():
        wav_path = os.path.join(AUDIO_DIR, f"{name}.wav")
        if not os.path.exists(wav_path):
            print(f"  [warn] Missing: {wav_path}")
            continue
        audio, sr = sf.read(wav_path, dtype="float32")
        if sr != SAMPLE_RATE:
            print(f"  [warn] {name}: expected {SAMPLE_RATE}Hz, got {sr}Hz")
        samples[name] = {"audio": audio, "ground_truth": ground_truth}
    return samples


def load_batch_model():
    """Load Paraformer with VAD + punctuation for batch mode."""
    print("Loading Paraformer batch model (with VAD + punctuation)...")
    from funasr import AutoModel
    t0 = time.time()
    model = AutoModel(
        model="paraformer-zh-streaming",
        vad_model="damo/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        punc_model="damo/punc_ct-transformer_cn-en-common-vocab471067-large",
        device="cpu",
        disable_update=True,
    )
    print(f"  Loaded in {time.time() - t0:.1f}s")
    return model


def load_streaming_model():
    """Load Paraformer without VAD for chunk-by-chunk streaming."""
    print("Loading Paraformer streaming model (no VAD)...")
    from funasr import AutoModel
    t0 = time.time()
    model = AutoModel(
        model="paraformer-zh-streaming",
        device="cpu",
        disable_update=True,
    )
    print(f"  Loaded in {time.time() - t0:.1f}s")
    return model


def test_batch(model, samples):
    """Test batch mode: feed entire audio, get full transcript."""
    print("\n" + "=" * 60)
    print("TEST: Paraformer BATCH MODE (accuracy)")
    print("=" * 60)

    results = {}
    for name, data in samples.items():
        audio = data["audio"]
        ground_truth = data["ground_truth"]
        duration = len(audio) / SAMPLE_RATE

        t0 = time.time()
        res = model.generate(input=audio, batch_size_s=300)
        elapsed = time.time() - t0

        recognized = res[0]["text"] if res and res[0].get("text") else ""
        char_accuracy = calc_char_accuracy(ground_truth, recognized)

        gt_simp = strip_punct(to_simplified(ground_truth))
        rec_simp = strip_punct(to_simplified(recognized))

        results[name] = {
            "ground_truth": ground_truth,
            "recognized": recognized,
            "char_accuracy": char_accuracy,
            "time": elapsed,
            "duration": duration,
        }

        print(f"\n  [{name}] {duration:.1f}s audio -> {elapsed:.2f}s processing")
        print(f"  Ground truth (繁): {ground_truth}")
        print(f"  Ground truth (简): {gt_simp}")
        print(f"  Recognized:        {recognized}")
        print(f"  Recognized (简):   {rec_simp}")
        print(f"  Char accuracy:     {char_accuracy:.1f}%")

    return results


def test_streaming(model, samples):
    """Test streaming mode: feed 1s chunks, collect incremental results."""
    print("\n" + "=" * 60)
    print("TEST: Paraformer STREAMING (1s chunk) (accuracy)")
    print("=" * 60)

    chunk_stride = int(CHUNK_SECONDS * SAMPLE_RATE)
    results = {}

    for name, data in samples.items():
        audio = data["audio"]
        ground_truth = data["ground_truth"]
        total_chunks = int((len(audio) - 1) / chunk_stride + 1)
        duration = len(audio) / SAMPLE_RATE

        print(f"\n  [{name}] {duration:.1f}s audio -> {total_chunks} chunks of {CHUNK_SECONDS}s")

        cache = {}
        chunk_texts = []
        total_time = 0

        for i in range(total_chunks):
            speech_chunk = audio[i * chunk_stride:(i + 1) * chunk_stride]
            is_final = i == total_chunks - 1

            t0 = time.time()
            res = model.generate(
                input=speech_chunk,
                cache=cache,
                is_final=is_final,
                chunk_size=[0, 10, 5],
                encoder_chunk_look_back=4,
                decoder_chunk_look_back=1,
            )
            elapsed = time.time() - t0
            total_time += elapsed

            text = res[0]["text"] if res and res[0].get("text") else ""
            chunk_texts.append(text)
            status = "OK" if elapsed < CHUNK_SECONDS else "SLOW"
            print(f"    chunk {i+1}/{total_chunks} | {elapsed:.3f}s [{status}] -> \"{text}\"")

        # The final chunk's text is usually the complete result in streaming mode
        # But intermediate chunks may have partial results
        # For accuracy, we use the last chunk's output as the full transcript
        final_text = chunk_texts[-1] if chunk_texts else ""

        # Also try combining all chunk texts (some models emit partials)
        combined_text = "".join(chunk_texts)

        char_accuracy_final = calc_char_accuracy(ground_truth, final_text)
        char_accuracy_combined = calc_char_accuracy(ground_truth, combined_text)

        gt_simp = strip_punct(to_simplified(ground_truth))
        final_simp = strip_punct(to_simplified(final_text))
        combined_simp = strip_punct(to_simplified(combined_text))

        results[name] = {
            "ground_truth": ground_truth,
            "final_chunk_text": final_text,
            "combined_text": combined_text,
            "char_accuracy_final": char_accuracy_final,
            "char_accuracy_combined": char_accuracy_combined,
            "total_time": total_time,
            "duration": duration,
            "chunk_texts": chunk_texts,
        }

        print(f"  Ground truth (繁):    {ground_truth}")
        print(f"  Ground truth (简):    {gt_simp}")
        print(f"  Last chunk text:      {final_text}")
        print(f"  Last chunk (简):      {final_simp}")
        print(f"  Combined text:        {combined_text}")
        print(f"  Combined (简):        {combined_simp}")
        print(f"  Char accuracy (last chunk):  {char_accuracy_final:.1f}%")
        print(f"  Char accuracy (combined):    {char_accuracy_combined:.1f}%")

    return results


def calc_char_accuracy(reference, hypothesis):
    """Character-level accuracy after normalizing to simplified + stripping punct."""
    ref = strip_punct(to_simplified(reference))
    hyp = strip_punct(to_simplified(hypothesis))

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

    distance = dp[m][n]
    max_len = max(m, n)
    return (1 - distance / max_len) * 100


def print_summary(batch_results, streaming_results):
    """Print comparative summary."""
    print("\n" + "=" * 60)
    print("ACCURACY SUMMARY")
    print("=" * 60)

    print(f"\n{'Name':<10} {'Duration':<10} {'Batch Acc':<12} {'Stream Acc':<12} {'Batch RTF':<10}")
    print("-" * 60)

    for name in batch_results:
        br = batch_results[name]
        sr = streaming_results.get(name, {})
        stream_acc = sr.get("char_accuracy_combined", sr.get("char_accuracy_final", 0))
        rtf = br["time"] / br["duration"] if br["duration"] > 0 else 0
        print(
            f"{name:<10} {br['duration']:<10.1f}s "
            f"{br['char_accuracy']:<12.1f}% "
            f"{stream_acc:<12.1f}% "
            f"{rtf:<10.2f}x"
        )

    print("\n" + "=" * 60)
    print("COMPARISON: Batch vs Streaming (1s chunk)")
    print("=" * 60)

    for name in batch_results:
        br = batch_results[name]
        sr = streaming_results.get(name, {})
        batch_acc = br["char_accuracy"]
        stream_acc_final = sr.get("char_accuracy_final", 0)
        stream_acc_combined = sr.get("char_accuracy_combined", 0)

        print(f"\n  [{name}] \"{TEST_SENTENCES[name]}\"")
        print(f"    Batch:          {batch_acc:.1f}% accuracy")
        print(f"    Streaming (last): {stream_acc_final:.1f}% accuracy")
        print(f"    Streaming (combined): {stream_acc_combined:.1f}% accuracy")


def main():
    print("FunASR Paraformer Accuracy Test")
    print(f"Device: CPU | Chunk: {CHUNK_SECONDS}s | Sample rate: {SAMPLE_RATE}Hz\n")

    # Step 1: Generate test audio
    print("Step 1: Generating test audio samples...")
    generate_test_audio()

    # Step 2: Load samples
    print("Step 2: Loading audio samples...")
    samples = load_audio()
    print(f"  Loaded {len(samples)} samples\n")

    # Step 3: Batch model + test
    batch_model = load_batch_model()
    batch_results = test_batch(batch_model, samples)
    del batch_model  # Free memory

    # Step 4: Streaming model + test
    import gc
    gc.collect()
    streaming_model = load_streaming_model()
    streaming_results = test_streaming(streaming_model, samples)

    # Step 5: Summary
    print_summary(batch_results, streaming_results)

    print("\nDone.")


if __name__ == "__main__":
    main()
