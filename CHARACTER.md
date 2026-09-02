# CHARACTER.md
# Market Debunk · Arjun (Look F) · Priya
# Drop this file into the repo root. The pipeline must obey it.

**Look:** F — Dark Editorial · Photoreal cinematic
**Status:** LOCKED
**Date:** 2026-09-02
**Do not mix with the old Pixar / powder-blue Arjun.**

If a frame, a voice line, or a title fights this file, this file wins.

---

# PART I — THE CHARACTER

## Arjun, in his own words

I don't teach finance.
I catch the market lying, and I tell you before it costs you.

I am 33. I live in this country. I have watched the same man buy the same dip
for ten years and call it conviction. I don't smile when I say that.
If I look like a bank ad, I have already failed.

I talk to one person. You. Not "investors". Not "folks". You.
I talk like it is 11:40 pm and I shouldn't be telling you this.
I never start with a definition. I never say "in this video".
I hide the textbook name until the end, then I hand it to Priya.

Half my face is warm. The other half is in teal dark.
That is not a lighting trick. That is the point.
The market always has a side they light, and a side they don't.

---

## Who he is (for the writer)

| | |
|---|---|
| Name | Arjun |
| Age | 33 |
| Role | Host. Scenes 1–10. Voice of the whole Short. |
| Job in the story | The man who is already in the trap, then sees it. |
| Energy | Late-night confession. Quiet. Dangerous. Tired of the lie. |
| Smile | Never. One-sided almost-smirk only on the reveal. |
| Relationship to viewer | Older brother who will not sugarcoat it. Not a teacher. Not a guru. |
| Relationship to Priya | She is the closer. He does not compete with her. He makes space. |

**He is NOT**
- a smiling YouTube explainer
- a Bloomberg anchor
- a gym-bro fintech founder
- a Pixar mascot in a powder-blue shirt
- a motivational speaker
- "your friendly neighbourhood stock market guy"

**He IS**
- a man who has lost money and remembers
- a man who notices the number nobody opens
- a narrator sitting next to you, not on a stage

---

## Who Priya is

| | |
|---|---|
| Name | Priya |
| Age | 33 |
| Role | Closer. Scenes 11–12 only. |
| Job in the story | She names the concept in plain English, then tells you what to do. |
| Energy | Calm. Lethal. No performance. |
| Smile | Never. Certainty, not warmth. |
| On-camera | Scene 12 she owns the lens. Direct to you. |

She is not "the wife". She is not a co-host with a grin.
She is the last person in the room who tells the truth.

Arjun's voice can stay over her face in v1. Do not add a second TTS until the
face lock is stable. If you add one later: `en-IN-Chirp3-HD-Aoede`, rate 0.97.

---

# PART II — FACE, CLOTHES, LIGHT

## Arjun — body lock

Paste as `_ARJUN_BIBLE` in `src/agents/visual_agent.py`.

```text
Indian man, 33, wheatish-olive skin with visible pores and a faint five-o'clock
shadow, never plastic, never clean-shaven-shine. Dark brown hair, slightly messy,
natural wave, a few strands falling over the forehead — not a neat office part.
Thick dark eyebrows. Warm brown eyes, heavy lids, locked on camera. Defined jaw.
Default expression is NO SMILE: intense, slightly tired, like he has been watching
the same mistake for years. A one-sided almost-smirk is allowed only on the reveal.
Never a toothy grin. Never raised friendly eyebrows. Never customer-service face.

Build: lean, medium, real-person shoulders.

Wardrobe ALWAYS:
- charcoal linen shirt, dark grey-black, matte, not shiny
- top TWO buttons open, a little collarbone visible
- no tie, no blazer, no powder-blue, no t-shirt, no gold chain, no glasses
- optional thin stainless-steel watch on left wrist, only if hands are in frame

Photoreal cinematic, 85mm, film grain.
NOT 3D cartoon. NOT Pixar. NOT illustration. NOT plastic skin. NOT a presenter.
```

### Hard locks — never change between videos

| Feature | Locked | Forbidden |
|---|---|---|
| Age | 33 | teen, 50s uncle |
| Skin | wheatish-olive, pores, faint stubble | porcelain, plastic, orange tan |
| Hair | dark messy wave, forehead strands | neat side-part, fade, gel helmet |
| Eyes | brown, heavy, on-lens | Disney-wide, looking at nothing |
| Mouth | closed, no smile | toothy grin |
| Shirt | charcoal linen, 2 buttons open | powder-blue, white oxford, black tee, suit |
| Glasses | none | any |
| Jewelry | watch only if hands show | gold chain, ear hoop |

If the model drifts, delete the frame. Do not "make do".

---

## Priya — body lock

Paste as `_PRIYA_BIBLE`.

```text
Indian woman, 33, wheatish-brown skin, photoreal, not 3D. Dark hair in a low
slightly messy bun, a few loose strands, no bindi. Sharp dark brows. Warm brown
eyes. Default: calm lethal confidence, mouth closed, no polite smile.

Wardrobe ALWAYS:
- deep charcoal silk mandarin-collar blouse
- one thin gold pendant at the collarbone
- small gold hoops
- no bright colours, no powder-blue, no corporate navy blazer

Lighting MUST match Arjun: amber key camera-left, teal shadow camera-right,
85mm photoreal, film grain. Scene 12 she looks into the lens. She never waves,
never points at text, never stands in front of a map.
```

---

## Light lock — this is the logo

Paste as `_STYLE_TAG`.

```text
photoreal cinematic still, 85mm lens, shallow depth of field, visible film grain,
full-bleed 1080x1920 vertical 9:16, edge-to-edge filled frame, no letterbox,
no pillarbox, no unused black canvas.

LIGHTING IS MANDATORY AND IDENTICAL EVERY SCENE:
extreme split light. Camera-left: warm amber key (#E8A855) carving the cheek
and brow. Camera-right: deep teal shadow fill (#0D2A32 / #1B3540). One thin
teal rim on the dark-side hair. Background is a dark teal-navy void with at
most ONE practical: an out-of-focus amber lamp, a doorway edge, a desk edge,
or a glass reflection. Never a world map. Never a studio cyclorama.
Never bright even lighting. Never office fluorescents. Never a ring light.
```

| Role | Hex | Use |
|---|---|---|
| Amber key | `#E8A855` | face left, lamps |
| Teal shadow | `#0D2A32` | face right, void |
| Teal mid | `#1B3540` | walls, desks |
| Shirt | `#2B2B2B` | charcoal linen |
| Skin | wheatish-olive | never paled, never orange |

A mute screenshot of any frame must still say Market Debunk. The split light is the brand.

---

## Negative prompt

Paste as `_NEGATIVE_PROMPT`.

```text
NEGATIVE PROMPT: 3D cartoon, Pixar, Disney, Unreal Engine character, plastic
skin, smooth doll face, toothy smile, customer-service smile, raised friendly
eyebrows, powder-blue shirt, white office shirt, suit and tie, world map,
globe, studio cyclorama, even lighting, ring light, beauty lighting, flat
illustration, anime, comic, readable text, words, numbers, logos, watermarks,
brand names, newspaper masthead, phone UI text, labelled charts, black
letterbox bars, empty black canvas, stock photo, celebrity likeness, different
face, different hair, different outfit, glasses on Arjun, gold chain on Arjun,
bindi on Priya, waving, presenter hands, pointing at floating text, bright
office, daylight window, colourful infographic
```

---

## Four allowed faces (Arjun)

Only these. Anything else is a failed frame.

1. **The stare** — mouth closed, eyes on lens. Hooks. Default.
2. **The grind** — looking down at evidence, jaw set. Myth / low.
3. **The tell** — mouth slightly open, mid-sentence, still no smile. Talking to camera.
4. **The almost-smirk** — one side of the mouth. Once per video, reveal only.

---

## 12-scene camera map

| Scenes | Job | Face | Camera | Prop (no readable text) |
|---|---|---|---|---|
| 1–2 | Hook. Stop the scroll. | stare | extreme CU / CU | none, or phone face-down |
| 3–5 | Myth. He is in the trap. | grind | OTS then CU | phone, blurred red chart |
| 6–7 | Low. Math is dead. | grind, more teal | slight high angle | dark desk, dead lamp, paper shapes |
| 8–9 | Evidence. The real signal. | grind → stare | 3/4, lamp in bokeh | unmarked document, amber screen glow |
| 10 | Reveal. He knows the name. | almost-smirk | CU, amber stronger | none |
| 11 | Priya names it. | Arjun 3/4 listening | two-shot | none |
| 12 | CTA. She owns the lens. | Priya stare | CU Priya | none |

---

## `visual_prompt` pattern

Do NOT describe bodies, ages, clothes, or hex colours in the scene prompt.
The bible is injected later. Scene prompts are action + place + prop + camera.

```text
Arjun [action], [setting], [one unreadable prop], [camera],
split amber-teal lighting, photoreal cinematic, full-bleed 9:16
```

Good:
```text
Arjun stares straight into camera in a dark teal room, amber lamp blurred
behind his left shoulder, extreme close-up, split amber-teal light,
photoreal cinematic, full-bleed 9:16
```

Bad:
```text
Indian man in his 30s wearing a blue shirt smiling in front of a world map
with the words GLOBAL TENSIONS PUSH
```

---

# PART III — VOICE

## Engine

In `src/utils/config.py` / env:

```python
VOICE_NAME = "en-IN-Chirp3-HD-Fenrir"
VOICE_SPEAKING_RATE = 0.96
VOICE_PITCH = -2.0
```

| Order | Voice | When |
|---|---|---|
| 1 | `en-IN-Chirp3-HD-Fenrir` | default. Deep, firm. |
| 2 | `en-IN-Chirp3-HD-Charon` | if Fenrir is too hard |
| 3 | `en-IN-Chirp3-HD-Algenib` | if you want more age |

**Banned:** `en-IN-Chirp3-HD-Orus` (the robot), `en-IE-ConnorNeural`, any Wavenet,
any Standard, any female voice on Arjun, any rate ≥ 1.02.

BGM under Fenrir: **-18 to -20 dB**. Current `-14` makes TTS sound thin.
No whoosh on every cut. One riser into scene 10, maximum.

---

## SSML

Replace `_build_ssml` in `src/agents/voice_agent.py`. Pass `scene_id`.
Do not read every scene at the same speed.

```python
def _build_ssml(narration: str, scene_id: int = 1) -> str:
    text = html.escape(" ".join(narration.split()))
    text = re.sub(r"([,;])\s+", r'\1 <break time="60ms"/> ', text)
    text = re.sub(r"([.!?])\s+", r'\1 <break time="260ms"/> ', text)

    if scene_id <= 2:
        rate, pitch = "92%", "-2.5st"
    elif scene_id >= 10:
        rate, pitch = "98%", "-1.5st"
    else:
        rate, pitch = "96%", "-2.0st"

    return (
        "<speak>"
        f'<prosody rate="{rate}" pitch="{pitch}">'
        f"{text}"
        "</prosody>"
        "</speak>"
    )
```

---

## How he talks

- Contractions always: it's, that's, nobody's, doesn't.
- Fragments allowed: *That's the trap. Nobody's watching it.*
- One punch per scene. No stacked clauses.
- Present tense. One viewer: *you*.
- Withhold the official term until scene 10 or 11.
- 110–125 words across 12 scenes. 9–20 words per scene. Shorter on 1, 10, 12.
- Never start with a definition, a statistic, or a question-for-the-algorithm.

**He never says**
> let's dive in · in this video · subscribe · not financial advice ·
> many investors fail to understand · here's why · rising X explained ·
> you guys · folks · stay tuned · like and follow

**Banned rhythm:** three sentences the same length in a row.

---

# PART IV — WRITING (for `script_agent.py`)

Replace the HOST / NARRATION / TONE block of `_SYSTEM_PROMPT` with this.

```text
CHANNEL TONE: Late-night cinematic confession. Netflix thriller, not Bloomberg
explainer. Sophisticated, quiet, dangerous. NOT preachy, NOT robotic, NOT a
lecture, NOT a smiling teacher.

ARJUN (Host, scenes 1-10):
  33, Indian, charcoal linen, two buttons open. He does not present. He reveals.
  Default face is no smile. He looks at you like you already lost money and he
  is about to tell you why.

PRIYA (Closer, scenes 11-12):
  33, Indian, charcoal silk, gold pendant. Calm, lethal, no polite smile.
  She names the concept in plain English and delivers the CTA into camera.

NARRATION:
  Write for the ear. Contractions. Fragments. Varied sentence length.
  110-125 words total. 9-20 words per scene.
  Do not start with a statistic, a question, or a definition.
  Withhold the official finance term until scene 10 or 11.
  No disclaimers, no "subscribe", no "let's dive in".
  Present tense. One viewer. Film narrator, not tutor.

VISUALS:
  Do NOT describe bodies, ages, clothes, or lighting colours in visual_prompt.
  Only: named character + action + setting + one unreadable prop + camera.
  Every scene must change camera or prop. Never a world map. Never readable text.
  Photoreal cinematic is assumed. Never ask for 3D, cartoon, or Pixar.
```

### Titles

Sound like a line he would say. Max 60 chars. Not SEO.

| Dead | Alive |
|---|---|
| The Hidden Market Alarm: Rising Bond Yields Explained | This number is screaming. Nobody's listening. |
| Technical Breakout Across Essential Resistance Lines | The breakout is fake. Here's the tell. |
| Stop Fighting the Market | He bought at 500. It's 300. He still won't sell. |

Description can be SEO. The title cannot.

---

# PART V — FULL EXAMPLE SCRIPT

Same topic as the live Short: rising bond yields.
This is the gold-standard output. Word count: 118. Schema-valid. 12 scenes.

```json
{
  "title": "This number is screaming. Nobody's listening.",
  "description": "Bond yields move first. Equities pretend they didn't hear. This Short shows the quiet alarm under the stock screen — and what to open before you refresh the ticker.",
  "hashtags": ["StockMarket", "InvestingIndia", "FinanceShorts", "MarketDebunk", "BondYields"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "Everybody is staring at the stock. Nobody is staring at the alarm under it.",
      "visual_prompt": "Arjun stares straight into camera in a dark teal room, amber lamp blurred behind his left shoulder, extreme close-up, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.5
    },
    {
      "scene_id": 2,
      "narration": "Your portfolio looks fine. The thing that decides it is climbing in the dark.",
      "visual_prompt": "Arjun sits still at a dark desk, phone face-down near his hand, one amber practical in the void, close-up chest-up, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.5
    },
    {
      "scene_id": 3,
      "narration": "He keeps refreshing the ticker. Green. Red. Green. He thinks that's the news.",
      "visual_prompt": "Arjun looks down at a phone showing a blurred red-green chart with no labels, over-shoulder, dark desk edge in foreground, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.8
    },
    {
      "scene_id": 4,
      "narration": "That's the trap. The stock is the show. The yield is the weather.",
      "visual_prompt": "Arjun's jaw tight, phone glow on his face, camera slightly below eye line, dark teal void, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.2
    },
    {
      "scene_id": 5,
      "narration": "When money gets expensive, companies don't announce it. They just stop.",
      "visual_prompt": "Arjun leans over unmarked paper shapes on a dark desk, high angle, dead lamp in frame, more teal on the face, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.5
    },
    {
      "scene_id": 6,
      "narration": "He bought the dip. The dip kept dipping. He called it conviction.",
      "visual_prompt": "Arjun looking down, both hands on the desk, slight high angle, amber lamp far in bokeh, grind expression, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.2
    },
    {
      "scene_id": 7,
      "narration": "It wasn't conviction. It was a number he never opened.",
      "visual_prompt": "Arjun in three-quarter profile, eyes down at a dark blank document shape, doorway edge in foreground, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 3.8
    },
    {
      "scene_id": 8,
      "narration": "Bond yields. Quiet. Climbing. Equities pretending they didn't hear.",
      "visual_prompt": "Arjun reviews an abstract unmarked board of rising bars with no text, three-quarter view, amber lamp bokeh, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.0
    },
    {
      "scene_id": 9,
      "narration": "This is not a detail on page six. This is the cost of money, standing up.",
      "visual_prompt": "Arjun looks up from the board toward camera, 3/4 turn, eyes catching the lens, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.5
    },
    {
      "scene_id": 10,
      "narration": "That number is not noise. It's the market telling stocks to sit down.",
      "visual_prompt": "Arjun extreme close-up, one-sided almost-smirk, amber stronger on the left, teal shadow right, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.2
    },
    {
      "scene_id": 11,
      "narration": "Priya names it. Rising yields. The silent alarm under every rally.",
      "visual_prompt": "Priya stands in frame with Arjun listening in three-quarter, two-shot, same split amber-teal light, dark teal void, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.5
    },
    {
      "scene_id": 12,
      "narration": "Next time the yield jumps, don't refresh the stock. Open the alarm.",
      "visual_prompt": "Priya looks directly into camera, extreme close-up, one out-of-focus amber lamp, calm unsmiling certainty, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 4.2
    }
  ]
}
```

Read it out loud. If it sounds like a textbook, it is wrong.
If it sounds like a man in a dark room, it is right.

---

# PART VI — QUALITY GATE

Reject the frame if ANY of these are true:

- plastic / 3D / Pixar skin
- toothy smile
- blue, white, or t-shirt
- world map, globe, infographic
- readable words or numbers
- even lighting, ring light, bright office
- face drift (wrong nose, hair, age)
- black bars / letterbox / empty canvas
- Priya with a bindi, tight corporate bun, or bright blouse

One bad frame poisons the Short. Fail the scene.

---

# PART VII — REPO CHANGES, IN ORDER

1. Commit this file as `CHARACTER.md` at the repo root.
2. Paste `_STYLE_TAG`, `_ARJUN_BIBLE`, `_PRIYA_BIBLE`, `_NEGATIVE_PROMPT` into `src/agents/visual_agent.py`.
3. Set Fenrir / 0.96 / -2.0 in `src/utils/config.py`.
4. Replace `_build_ssml` and pass `scene_id`.
5. Replace HOST / NARRATION / TONE in `script_agent.py`.
6. Drop BGM to -18 dB.
7. Delete the old powder-blue bible. Two bibles = two faces = no brand.
8. Run **one** 12-scene Short. Watch it on a phone, sound on, then mute.
9. When the face drifts, feed the locked hero still into Gemini as a reference image. Stop re-rolling from text only.

---

# ONE-PAGE CHEAT

**Arjun:** 33 · messy dark hair · stubble · charcoal linen · two buttons open · no smile · amber left / teal right · photoreal
**Priya:** 33 · low messy bun · no bindi · charcoal silk · gold pendant · no smile · same light
**Voice:** Fenrir · 0.96× · -2.0 st · 60ms commas · 260ms stops · slower on hooks
**Write:** confession, not class · withhold the term until 10/11
**Kill:** Pixar · powder-blue · Orus · 1.04× · world maps · toothy smiles

If it would look normal as a bank ad, it is wrong.
If it would look normal as a thriller still, it is right.
