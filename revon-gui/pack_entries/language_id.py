"""Private worker. The pinned wheel directory is supplied by the host."""
import json
import sys

if __name__ == "__main__":
    sys.path.append(sys.argv[1])
    from langdetect import DetectorFactory, detect_langs
    from langdetect.lang_detect_exception import LangDetectException

    DetectorFactory.seed = 0
    text = json.load(sys.stdin.buffer)["text"]
    try:
        candidates = [{"language": item.lang, "probability": round(item.prob, 6)} for item in detect_langs(text)]
    except LangDetectException:
        candidates = []
    print(json.dumps({"language": candidates[0]["language"] if candidates else "und", "candidates": candidates}))
