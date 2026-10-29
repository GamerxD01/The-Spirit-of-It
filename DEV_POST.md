*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26)*

## What I Built

Every family has one person who holds all the stories. They don't write memoirs. Their memories live in their voice: in Awadhi or Bhojpuri, in wedding songs that change from one village to the next, in recipes measured "by the hand". When that voice goes quiet, the stories usually go with it.

So when this week's prompt said *honor the past*, I didn't think of ghosts. I thought of all the stories we keep meaning to record "next time we're home".

**Dadi's Voice Archive** is an offline oral-history altar. It runs entirely on your own computer:

1. **Record** an elder telling a story in the browser, or drop in an old WhatsApp voice note.
2. **Whisper** (open weights, running locally) writes down every word with timestamps, in Devanagari.
3. **Gemma** (running locally through Ollama) translates it line by line into English, for the grandchildren who've lost the language. It also gives the story a title, picks out the people, places, foods and songs mentioned, and keeps one **keepsake** line in the elder's original words.
4. **Ask what they remembered.** Type *"What did she cook for Diwali?"* and the answer comes back with citations. Next to every citation is a ▶ button that plays **her actual voice** at the exact second she said it.

That last feature is the ghost in the machine, and I was deliberate about how it behaves. **The app never pretends to be her.** There's no "chat with grandma" persona and no cloned voice. It works like an archivist: it talks *about* her ("Dadi said…"), quotes her, and plays her. If she never talked about something, it says so and suggests asking someone in the family and recording the answer. A machine putting words in a dead person's mouth isn't remembering them. It's haunting them.

The theme maps onto Indian traditions surprisingly well. For Día de los Muertos, families build an *ofrenda* with marigolds and candles so the dead can find their way home. In India we light *diyas*, string *genda* (marigold) garlands, and during Pitru Paksha we remember our ancestors by name. The UI borrows from both: papel picado across the top, a flickering diya under every name, and a marigold frame around each elder on the altar.

## Demo

![Walkthrough: add an elder, upload a story, ask a question, play her voice](https://raw.githubusercontent.com/GamerxD01/The-Spirit-of-It/main/docs/demo.gif)

*The walkthrough uses a sample story and the project's demo mode (stand-in models), so it plays back instantly. On a real install, the same screens are filled by Whisper and Gemma running locally.*

**The ofrenda**, where everyone you're remembering lives:

![The ofrenda](https://raw.githubusercontent.com/GamerxD01/The-Spirit-of-It/main/docs/altar.png)

**Asking a question.** The answer is grounded in her recordings, and every source plays her voice:

![Ask what she remembered](https://raw.githubusercontent.com/GamerxD01/The-Spirit-of-It/main/docs/ask.png)

**A story page.** The keepsake line, tags, and her words line by line. The line she's speaking lights up as the audio plays:

![A story page](https://raw.githubusercontent.com/GamerxD01/The-Spirit-of-It/main/docs/story.png)

## Code

{% github GamerxD01/The-Spirit-of-It %}

## How I Built It

The whole stack is open, and it all runs on one machine:

| Piece | Job |
|---|---|
| **faster-whisper** (Whisper `small`, CTranslate2, int8 on CPU) | Speech to timestamped segments. Voice-activity detection skips the long pauses elders take mid-story. |
| **Gemma via Ollama** (`gemma3:4b` by default; the app picks whichever Gemma you have installed) | Line-by-line translation, the memory card (title, summary, people/places/foods/songs/era, keepsake), bilingual search keywords, grounded answers |
| **FastAPI + SQLite** | API and storage. A single background worker lets Whisper and Gemma take turns instead of fighting for a laptop's RAM. |
| **Vanilla JS, no CDN, no web fonts** | The UI loads with the Wi-Fi off |

A few design decisions I'm proud of:

**Translation is per segment, not per story.** Gemma receives numbered Whisper lines and returns `{"lines": {"0": "...", "1": "..."}}` using Ollama's JSON mode. Every English line stays tied to its original line *and* its timestamp. That's what lets the story page show both languages together, and highlight the line she's saying while the audio plays.

```python
TRANSLATE_SYS = (
    "You translate a grandmother's spoken memories from {lang} (often village Hindi/Awadhi, "
    "mixed with English words) into warm, plain English. Keep names, places, foods and song "
    "titles as they are (transliterated). Keep her voice: short sentences, no polishing into "
    "formal prose. Do not add anything she did not say."
)
```

**Cross-language search without an embedding model.** Questions usually come in English, but her words are in Devanagari. Rather than load a third model, I gave BM25 both sides. Each passage is indexed as *original + Gemma's translation*, and Gemma first expands the question into English and Hindi keywords ("cook" → "पकाना", "ठेकुआ"). It's tiny and fast on a laptop, and one regex handles Devanagari tokens.

**Grounding is a product decision, not just a prompt.** The answer prompt tells Gemma it is *not* her and may only use the numbered excerpts from her recordings. The UI makes any slip visible anyway: every claim cites a source, and every source plays her real voice. If retrieval finds nothing, Gemma isn't called at all, and the app says plainly that she never talked about it.

```python
ANSWER_SYS = (
    "You are a careful family archivist. You are NOT {name} and you must never speak as her "
    "or invent her words. Answer the family's question using ONLY the numbered excerpts from "
    "{name}'s own recordings below... If the excerpts do not answer the question, say plainly "
    "that she did not talk about this in the recordings."
)
```

**It degrades gracefully.** If Ollama isn't running, the story is still transcribed, saved and searchable, and you can still play the closest moments of her voice. A *Remember again* button fills in the Gemma part later. If the app is closed mid-story, the job picks up again the next time it starts.

**The export outlives the app.** One click produces a zip with a plain `index.html` and the audio files: no framework, no server, no account. It should still open in a browser decades from now.

**Tested without downloading models.** The test suite swaps in fake Whisper and Gemma models, so the whole suite runs in under a second. It covers the full record → transcribe → translate → ask → export flow, the "she never said that" case, and the Gemma-offline case.

## Why Does Open Innovation Matter?

For this project, open weights weren't a nice-to-have. Without them the project wouldn't make sense.

- **It's a grandmother's voice.** These recordings hold family names, old quarrels, health, land and money. They shouldn't be uploaded to a server the family doesn't control so a company can "improve its services". With Whisper and Gemma running locally, nothing leaves the house.
- **The people it's for are often offline.** These stories live in villages, at weddings, on a cousin's phone during a power cut. After a one-time model download, the whole app runs with the Wi-Fi off, and the exported memory book needs nothing but a browser.
- **You can swap the brain.** On a weak laptop, use `gemma3:1b` with Whisper `base`. For heavy dialect, use Whisper `medium`. When a better Gemma ships, it's one `ollama pull` and one environment variable. And if someone fine-tunes Whisper on Awadhi or Bhojpuri, which only open weights allow, this app gets better for free.
- **It can't be shut down.** Memorial products built on a closed API have a quiet expiry date: the startup pivots, the pricing changes, the model gets deprecated, and the "digital legacy" disappears with it. A family archive shouldn't depend on someone else's runway. This one is SQLite, audio files and an HTML page.
- **It costs nothing to run.** A family can record a hundred hours of stories with no meter running.

Where would a closed model have been better? A frontier API would probably translate Awadhi idioms more gracefully. For this project I'll take a slightly clumsier translation that stays in the house over a polished one that doesn't.

The marigolds on an ofrenda are there so the dead can find their way home. I think a voice does the same thing. 🪔
