"""
Centralized Pydantic models for all Prompt Engineer AI outputs.
Each model is used as a Gemini response_schema so the AI returns structured,
validated data at every pipeline section.
"""
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
#  SCRIPT MODELS (existing, moved here for single source of truth)
# ──────────────────────────────────────────────

class CharacterDef(BaseModel):
    name: str = Field(description="The name of the character (e.g. Mark, Arthur)")
    visual_description: str = Field(
        description="Highly detailed visual description of the character for image generation"
    )

class Scene(BaseModel):
    scene_number: int = Field(description="Chronological scene index starting at 1")
    narration: str = Field(description="The voiceover text for this scene (around 15-25 words), compelling and storytelling style")
    visual_prompt: str = Field(
        description="Descriptive text-to-image prompt. Highly detailed, cinematic, photorealistic."
    )
    visual_category: str = Field(
        description="The visual category tag for this scene. One of: character, metaphor, landscape, object, abstract, architectural."
    )
    character_focus: list[str] = Field(
        default_factory=list,
        description="Names of the characters from the cast that are on screen in this scene."
    )
    diagram_callouts: list[str] = Field(
        default_factory=list,
        description="Short text labels to be displayed on screen during the scene (e.g. ['MARK\\'S COST', 'ARTHUR\\'S BENEFIT']). Mostly used in the explanation scene."
    )


class VideoScript(BaseModel):
    thesis: str = Field(
        description="The core topic, story, or concept this video is about. Max 15 words."
    )
    title: str = Field(description="Catchy short-form video title anchored to the thesis")
    description: str = Field(description="YouTube/Instagram description with hashtags")
    cast: list[CharacterDef] = Field(
        description="The ensemble cast of characters (usually 2+) for this parable."
    )
    scenes: list[Scene] = Field(
        description="Exactly 8 scenes following the narrative arc: "
        "1=HOOK, 2=INVESTOR INTRO, 3=FREE-RIDER INTRO, "
        "4=COMPLICATION, 5=TWIST, 6=HARVEST/PAYOFF, 7=CONCEPT DEFINED, 8=MODERN ANALOGY."
    )


# ──────────────────────────────────────────────
#  VOICE ENGINEERING MODELS
# ──────────────────────────────────────────────

class SceneVoiceConfig(BaseModel):
    scene_number: int = Field(description="Which scene this config applies to")
    ssml_text: str = Field(
        description="Full SSML-enriched text for this scene. Include <emphasis>, "
        "<break>, and <prosody> tags for dramatic pacing. "
        "Use <emphasis level='strong'> on key reveal words. "
        "Insert <break time='300ms'/> before dramatic reveals."
    )
    pacing_rate: str = Field(
        description="Prosody rate for this scene, e.g. '+10%', '+20%', '-5%'. "
        "Hooks should be faster, reveals should slow down slightly."
    )
    emphasis_words: list[str] = Field(
        description="List of 2-3 words in this scene that should get CAPS emphasis in subtitles"
    )


class VoiceConfig(BaseModel):
    voice_name: str = Field(
        description="Recommended voice. Use 'Adam' for ElevenLabs primary, "
        "'en-US-Journey-F' for Google TTS fallback."
    )
    overall_energy: str = Field(
        description="Overall energy level: 'high' for myth-busting, 'medium' for explainers"
    )
    scenes: list[SceneVoiceConfig] = Field(description="Voice config per scene, matching the exact number of scenes in the script")


# ──────────────────────────────────────────────
#  VISUAL ENGINEERING MODELS
# ──────────────────────────────────────────────

class SceneVisualConfig(BaseModel):
    scene_number: int = Field(description="Which scene this config applies to")
    animation_tag: str = Field(
        description="Animation tag for Asset Pool Strategy. Must be exactly one of: 'bullish', 'bearish', 'neutral', 'educational'."
    )
    enhanced_prompt: str = Field(
        description="Highly detailed image generation prompt. Include: subject, composition, "
        "lighting, camera angle, mood. MUST end with 'bright white and light gray studio background, "
        "cinematic lighting, 8k resolution'. Must be unique across all scenes."
    )
    negative_prompt: str = Field(
        description="What to avoid in the image: 'text, watermark, blurry, low quality, "
        "stock photo, generic, clipart, cartoon'"
    )
    category_tag: str = Field(
        description="Visual category: vaults, crowds, paperwork, growth, digital, or hands. "
        "Must NOT repeat the immediately previous scene's category."
    )
    composition_directive: str = Field(
        description="Where to keep visual weight: 'center', 'left-third', 'right-third', "
        "'top-heavy', 'bottom-heavy'. Avoids mascot/subtitle overlap zones."
    )


class VisualConfig(BaseModel):
    global_style_suffix: str = Field(
        description="Color grading suffix appended to every prompt. "
        "Default: 'bright white and light gray studio background, cinematic lighting, 8k resolution'"
    )
    scenes: list[SceneVisualConfig] = Field(description="Visual config per scene, matching the exact number of scenes in the script")



# ──────────────────────────────────────────────
#  SUBTITLE STYLE MODELS
# ──────────────────────────────────────────────

class SubtitleStyle(BaseModel):
    font_name: str = Field(description="ASS font name. Recommended: 'DejaVu Sans' or 'Arial Black'")
    font_size: int = Field(description="Font size in ASS units. Recommended: 80-90 for 1080x1920")
    primary_color: str = Field(
        description="ASS hex color for normal words. Recommended: '&H0000FFFF' (yellow) "
        "or '&H00FFFFFF' (white)"
    )
    emphasis_color: str = Field(
        description="ASS hex color for CAPS emphasis words. Recommended: '&H000080FF' (orange)"
    )
    outline_color: str = Field(description="ASS outline color. Recommended: '&H00000000' (black)")
    outline_width: int = Field(description="Outline thickness. Recommended: 5-7")
    shadow_depth: int = Field(description="Shadow depth. Recommended: 2-4")
    margin_v: int = Field(
        description="Vertical margin from bottom in pixels. "
        "Must be 400-550 to hit 60-75% safe zone on 1920px frame."
    )
    alignment: int = Field(description="ASS alignment. 2 = bottom-center (recommended)")


# ──────────────────────────────────────────────
#  ASSEMBLY CONFIG MODELS
# ──────────────────────────────────────────────

class AssemblyConfig(BaseModel):
    ken_burns_zoom_rate: float = Field(
        description="Zoom increment per frame for Ken Burns effect. "
        "Recommended: 0.0003-0.0008. Lower = subtle, higher = dramatic."
    )
    loudness_target_i: float = Field(
        description="Integrated loudness target in LUFS. Must be -14."
    )
    loudness_lra: float = Field(
        description="Loudness range. Recommended: 11."
    )
    loudness_tp: float = Field(
        description="True peak ceiling. Recommended: -1.5."
    )
    logo_scale_width: int = Field(
        description="Logo overlay width in pixels. Recommended: 120-180."
    )
    logo_padding: int = Field(
        description="Logo padding from top-right corner. Recommended: 30."
    )
    suspense_bed_volume: float = Field(
        description="Background music volume ducking level. Recommended: 0.10-0.20."
    )
    output_fps: int = Field(description="Output framerate. Must be 25 or 30.")
    output_codec: str = Field(description="Video codec. Must be 'libx264'.")
    audio_codec: str = Field(description="Audio codec. Must be 'aac'.")


# ──────────────────────────────────────────────
#  PUBLISH METADATA MODELS
# ──────────────────────────────────────────────

class PublishMetadata(BaseModel):
    youtube_titles: list[str] = Field(
        description="Exactly 3 YouTube title options. Each ≤50 chars, include '#Shorts'. "
        "First should be the most clickable."
    )
    youtube_description: str = Field(
        description="YouTube description. Must be highly engaging, SEO-optimized targeting relevant keywords, and include 5-8 hashtags at the end. No citations. Max 600 chars."
    )
    youtube_tags: list[str] = Field(
        description="5-15 YouTube tags for SEO. Include: shorts, finance, market, myth, India"
    )
    telegram_caption: str = Field(
        description="Telegram caption. SEO-optimized and highly engaging with emojis and 3-5 hashtags. Max 250 chars."
    )
    instagram_description: str = Field(
        description="Instagram caption. SEO-optimized and highly engaging with emojis and 10-15 hashtags. Max 600 chars."
    )
    pinned_comment: str = Field(
        default="Are you holding or panic selling at these levels? Drop your strategy below 👇",
        description="A highly engaging, polarizing or curiosity-driven discussion question to pin as the top comment to boost algorithmic engagement."
    )
    category_id: str = Field(
        description="YouTube category ID. '27' for Education, '25' for News. Recommended: '27'."
    )

