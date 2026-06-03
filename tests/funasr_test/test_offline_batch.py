#!/usr/bin/env python3
"""
Accuracy test for FunASR Paraformer OFFLINE batch model (paraformer-zh).
Compares with streaming model results from test_accuracy.py.
"""

import subprocess
import os
import re
import time
import soundfile as sf
import numpy as np

# ── Config ──────────────────────────────────────────────────────
SAMPLE_RATE = 16000
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio_samples")

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

TEST_SENTENCES = {
    "short": "你好，今天天氣真好。",
    "medium": "語音輸入技術讓電腦可以聽懂人類說話的內容。",
    "long": "人工智慧正在改變我們的生活方式，從語音助理到自動駕駛，科技的發展速度超乎想像。",
}


def to_simplified(text):
    return ''.join(_TR_MAP.get(c, c) for c in text)


def strip_punct(text):
    return re.sub(r'[，。！？、；：""''（）\s,\.!?;:\'"()\[\]{}]', '', text)


def calc_char_accuracy(reference, hypothesis):
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


def main():
    print("FunASR Paraformer OFFLINE BATCH Accuracy Test")
    print(f"Model: paraformer-zh (offline batch) | Device: CPU\n")

    # Load model
    print("Loading offline batch model...")
    from funasr import AutoModel
    t0 = time.time()
    model = AutoModel(
        model="paraformer-zh",
        vad_model="damo/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        punc_model="damo/punc_ct-transformer_cn-en-common-vocab471067-large",
        device="cpu",
        disable_update=True,
    )
    print(f"  Loaded in {time.time() - t0:.1f}s\n")

    # Test each sentence
    print("=" * 60)
    print("OFFLINE BATCH MODEL RESULTS")
    print("=" * 60)

    results = {}
    for name, ground_truth in TEST_SENTENCES.items():
        wav_path = os.path.join(AUDIO_DIR, f"{name}.wav")
        if not os.path.exists(wav_path):
            print(f"  [skip] {name}.wav not found")
            continue

        audio, sr = sf.read(wav_path, dtype="float32")
        duration = len(audio) / sr

        # Warm up on first run
        if not results:
            print("  Warm-up...")
            _ = model.generate(input=audio, batch_size_s=300)

        t0 = time.time()
        res = model.generate(input=audio, batch_size_s=300)
        elapsed = time.time() - t0

        recognized = res[0]["text"] if res and res[0].get("text") else ""
        accuracy = calc_char_accuracy(ground_truth, recognized)
        rtf = elapsed / duration if duration > 0 else 0

        gt_simp = strip_punct(to_simplified(ground_truth))
        rec_simp = strip_punct(to_simplified(recognized))

        results[name] = {
            "ground_truth": ground_truth,
            "recognized": recognized,
            "accuracy": accuracy,
            "time": elapsed,
            "duration": duration,
            "rtf": rtf,
        }

        print(f"\n  [{name}] {duration:.1f}s audio -> {elapsed:.2f}s processing (RTF {rtf:.2f}x)")
        print(f"  Ground truth (繁): {ground_truth}")
        print(f"  Ground truth (简): {gt_simp}")
        print(f"  Recognized:        {recognized}")
        print(f"  Recognized (简):   {rec_simp}")
        print(f"  Char accuracy:     {accuracy:.1f}%")

    # Summary comparison
    print("\n" + "=" * 60)
    print("COMPARISON: Offline Batch vs Streaming (1s chunk combined)")
    print("=" * 60)

    # Previous streaming results (from test_accuracy.py run)
    streaming_combined = {
        "short": "你好今天天气真好",
        "medium": "语音输入技术让电脑可以听懂人类说话的内容",
        "long": "人工智慧正在改变我们的生活方式从语音助理到自动驾驶科技的发展速度超乎想象",
    }

    print(f"\n{'Name':<10} {'Duration':<10} {'Offline Batch':<15} {'Stream Combined':<15} {'Batch RTF':<10}")
    print("-" * 60)

    for name in results:
        r = results[name]
        stream_text = streaming_combined.get(name, "")
        stream_acc = calc_char_accuracy(TEST_SENTENCES[name], stream_text)
        print(
            f"{name:<10} {r['duration']:<10.1f}s "
            f"{r['accuracy']:<15.1f}% "
            f"{stream_acc:<15.1f}% "
            f"{r['rtf']:<10.2f}x"
        )

    print("\n" + "=" * 60)
    print("DETAILED COMPARISON")
    print("=" * 60)

    for name in results:
        r = results[name]
        gt_simp = strip_punct(to_simplified(TEST_SENTENCES[name]))
        rec_simp = strip_punct(to_simplified(r["recognized"]))
        stream_text = streaming_combined.get(name, "")

        print(f"\n  [{name}]")
        print(f"    Ground truth (简): {gt_simp}")
        print(f"    Offline batch:     {rec_simp}")
        print(f"    Stream combined:   {stream_text}")
        print(f"    Offline accuracy:  {r['accuracy']:.1f}%")
        stream_acc = calc_char_accuracy(TEST_SENTENCES[name], stream_text)
        print(f"    Stream accuracy:   {stream_acc:.1f}%")

    print("\nDone.")


if __name__ == "__main__":
    main()
