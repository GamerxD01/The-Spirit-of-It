"""Fake Whisper + Gemma so tests (and screenshot demos) run without model downloads."""
from app import asr, llm

LINES = [
    (0.0, 6.2, "जब हम छोटे थे, दिवाली पर अम्मा ठेकुआ बनाती थीं, गुड़ और आटे वाला।"),
    (6.2, 12.8, "पूरा आँगन घी की खुशबू से भर जाता था, और हम चूल्हे के पास बैठे रहते थे।"),
    (12.8, 19.5, "फिर रात को सब औरतें मिलकर सोहर गाती थीं, ढोलक बजती थी।"),
    (19.5, 26.0, "हमारा गाँव फैज़ाबाद के पास था, बिजली तो बहुत बाद में आई।"),
    (26.0, 31.0, "दीया जलाना कभी मत भूलना, बेटा। अंधेरे में भी कोई याद करता है।"),
]
EN = {
    0: "When we were little, on Diwali Amma made thekua, with jaggery and flour.",
    1: "The whole courtyard filled with the smell of ghee, and we sat by the clay stove.",
    2: "Then at night all the women sang sohar together, and the dholak played.",
    3: "Our village was near Faizabad, electricity came much later.",
    4: "Never forget to light the diya, child. Even in the dark, someone remembers.",
}


def fake_transcribe(path, language=None):
    return asr.Transcript("hi", 31.0, [asr.Segment(a, b, t) for a, b, t in LINES])


def fake_chat_json(system, user):
    if "translate" in system.lower():
        return {"lines": {str(k): v for k, v in EN.items()}}
    if "ofrenda" in system:
        return {"title": "Thekua on Diwali Night", "summary": "Dadi remembered her mother making thekua for Diwali in their "
                "village near Faizabad, and the women singing sohar to the dholak late into the night.",
                "people": ["Amma"], "places": ["Faizabad", "the courtyard"], "foods": ["thekua", "jaggery", "ghee"],
                "songs": ["sohar"], "era": "1950s", "keepsake": "दीया जलाना कभी मत भूलना, बेटा। अंधेरे में भी कोई याद करता है।"}
    if "keywords" in system:
        return {"keywords": ["diwali", "दिवाली", "cook", "ठेकुआ", "food"]}
    return {}


def fake_chat(system, user, **kw):
    return ("Dadi said that on Diwali her Amma made thekua from jaggery and flour [1], and the courtyard smelled of ghee "
            "(\"पूरा आँगन घी की खुशबू से भर जाता था\" [the whole courtyard filled with the smell of ghee]) [1].")


def install(monkeypatch=None):
    targets = [(asr, "transcribe", fake_transcribe), (llm, "chat_json", fake_chat_json), (llm, "chat", fake_chat),
               (llm, "model_name", lambda: "gemma3:4b (demo)")]
    for mod, name, fn in targets:
        if monkeypatch:
            monkeypatch.setattr(mod, name, fn)
        else:
            setattr(mod, name, fn)
