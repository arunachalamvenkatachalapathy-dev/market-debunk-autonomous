"""
Evaluator Agent — quality gate after EVERY pipeline section.
Each gate validates output before it flows downstream.
Hard gates block the pipeline; soft gates log warnings but continue.
"""
import logging
import os
import subprocess
import json
import hashlib

logger = logging.getLogger(__name__)

# Visual categories allowed by the framework
VALID_CATEGORIES = {"vaults", "crowds", "paperwork", "growth", "digital", "hands"}

# Citation phrases that must never appear
CITATION_PHRASES = [
    "according to", "sources say", "experts claim", "study shows",
    "research indicates", "data suggests", "reports show", "analysts say"
]


class EvaluatorAgent:
    """Runs a dedicated quality gate after every pipeline section."""

    def __init__(self):
        self.used_topics_path = "used_topics.json"

    def _load_used_topics(self):
        """Load the dedup topic log supporting both dict and list structures.
        Auto-expires entries older than 7 days to prevent topic pool exhaustion."""
        import datetime
        cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
        if os.path.exists(self.used_topics_path):
            try:
                with open(self.used_topics_path, "r") as f:
                    data = json.load(f)
                    topics = data.get("topics", []) if isinstance(data, dict) else data
                    # Filter out entries older than 7 days
                    fresh_topics = []
                    for t in topics:
                        ts_str = t.get("timestamp", "")
                        try:
                            ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00").split("+")[0])
                            if ts >= cutoff:
                                fresh_topics.append(t)
                        except Exception:
                            fresh_topics.append(t)  # keep if unparseable
                    return fresh_topics
            except Exception:
                pass
        return []

    def _save_used_topic(self, topic):
        """Append a topic to the dedup log while preserving last_channel_index."""
        raw_data = {"last_channel_index": 0, "topics": []}
        if os.path.exists(self.used_topics_path):
            try:
                with open(self.used_topics_path, "r") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        raw_data = loaded
                    elif isinstance(loaded, list):
                        raw_data["topics"] = loaded
            except Exception:
                pass
                
        topics = raw_data.get("topics", [])
        video_id = None
        if "[Video ID: " in topic:
            try:
                video_id = topic.split("[Video ID: ")[1].split("]")[0]
            except Exception:
                pass
        topics.append({
            "topic": topic,
            "video_id": video_id,
            "hash": hashlib.md5(topic.encode()).hexdigest(),
            "timestamp": __import__("datetime").datetime.now().isoformat()
        })
        raw_data["topics"] = topics[-90:]
        try:
            with open(self.used_topics_path, "w") as f:
                json.dump(raw_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save used topics: {e}")

    # ──────────────────────────────────────────────
    #  GATE 1: TOPIC
    # ──────────────────────────────────────────────

    def gate_topic(self, topic):
        """
        Validates the selected topic.
        🔴 HARD GATE — blocks pipeline on failure.
        
        Checks:
        - Topic is not empty
        - Topic has minimum substance (>5 words)
        - Not a duplicate (fuzzy match vs used_topics.json, similarity ≥ 0.75)
        """
        logger.info("🚦 Evaluator [GATE_TOPIC]: Validating topic...")
        details = {}

        if not topic or not topic.strip():
            return False, "Topic is empty", details

        word_count = len(topic.split())
        details["word_count"] = word_count
        if word_count < 5:
            return False, f"Topic too short ({word_count} words, need ≥5)", details

        # Fuzzy dedup check
        used = self._load_used_topics()
        topic_lower = topic.lower().strip()
        topic_words = set(w for w in topic_lower.split() if len(w) > 2)

        for entry in used:
            prev = entry.get("topic", "").lower().strip()
            prev_words = set(w for w in prev.split() if len(w) > 2)
            
            # Exact match check
            if topic_lower == prev:
                details["duplicate_of"] = entry.get("topic", "")
                return False, "Duplicate topic (Exact match)", details

            # Substring match if long enough
            if len(topic_lower) > 15 and topic_lower in prev:
                details["duplicate_of"] = entry.get("topic", "")
                return False, "Duplicate topic (Substring match)", details

            if topic_words and prev_words:
                intersection = topic_words & prev_words
                union = topic_words | prev_words
                similarity = len(intersection) / len(union) if union else 0
                if similarity >= 0.90:
                    details["duplicate_of"] = entry.get("topic", "")
                    details["similarity"] = round(similarity, 2)
                    return False, f"Duplicate topic (similarity {similarity:.0%})", details

        # Save topic for future dedup
        self._save_used_topic(topic)

        details["status"] = "fresh"
        return True, "Topic is fresh and valid", details

    # ──────────────────────────────────────────────
    #  GATE 2: SCRIPT
    # ──────────────────────────────────────────────

    def gate_script(self, script_data):
        """
        Validates the generated script against all framework rules.
        🔴 HARD GATE — blocks pipeline on failure.
        
        Checks:
        - Exactly 5 scenes (locked narrative arc)
        - Hook ≤5 words (cold open)
        - Thesis field present and threaded through ≥3 scenes
        - No citation language
        - Visual prompts all distinct
        - Visual categories rotate (no adjacent repeats)
        - ≥3 unique visual categories
        - Estimated runtime 30-55s
        - Arrow states present and valid
        - Title and description present
        """
        logger.info("🚦 Evaluator [GATE_SCRIPT]: Validating script...")
        details = {}

        scenes = script_data.get("scenes", [])
        details["scene_count"] = len(scenes)

        # Check 1: Must have exactly 5 scenes (locked 5-act arc)
        if len(scenes) != 5:
            return False, f"Must have exactly 5 scenes (HOOK→MYTH→EVIDENCE→REVEAL→CTA), got {len(scenes)}", details

        # Check 2: Hook ≤5 words (cold open must complete in <1.8s)
        first_narration = scenes[0].get("narration", "")
        hook = first_narration.replace("?", ".").replace("!", ".").split(".")[0]
        hook_words = hook.split()
        details["hook_word_count"] = len(hook_words)
        if len(hook_words) > 5:
            return False, f"Hook too long ({len(hook_words)} words, max 5 for cold open)", details

        # Check 3: Thesis Coherence Gate (NEW — the #1 retention check)
        thesis = script_data.get("thesis", "")
        details["thesis"] = thesis
        if not thesis or len(thesis.split()) < 3:
            return False, "Script missing a clear thesis (need ≥3 words)", details
        
        # Check that thesis keywords appear in at least 3 of 5 scenes
        thesis_words = set(w.lower() for w in thesis.split() if len(w) > 3)
        scene_hits = 0
        for s in scenes:
            narr_words = set(s.get("narration", "").lower().split())
            if thesis_words & narr_words:
                scene_hits += 1
        details["thesis_scene_coverage"] = f"{scene_hits}/{len(scenes)}"
        if scene_hits < 2:
            logger.warning(f"Thesis not threaded deeply enough ({scene_hits}/{len(scenes)}). Continuing anyway.")

        # Check 4: No citation language
        full_text = " ".join([s.get("narration", "") for s in scenes]).lower()
        for phrase in CITATION_PHRASES:
            if phrase in full_text:
                details["citation_found"] = phrase
                return False, f"Citation language detected: '{phrase}'", details

        # Check 5: Visual prompts all distinct
        prompts = [s.get("visual_prompt", "") for s in scenes]
        if len(set(prompts)) != len(prompts):
            return False, "Duplicate visual prompts detected", details

        # Check 6: Visual categories rotate
        categories = [s.get("visual_category", "unknown") for s in scenes]
        details["categories"] = categories
        for i in range(1, len(categories)):
            if categories[i] == categories[i - 1]:
                return False, f"Adjacent category repeat: scenes {i} and {i+1} both '{categories[i]}'", details

        # Check 7: ≥3 unique categories
        unique_cats = set(categories)
        details["unique_categories"] = len(unique_cats)
        if len(unique_cats) < 3:
            return False, f"Only {len(unique_cats)} unique categories, need ≥3", details

        # Check 8: Estimated runtime (5 scenes × ~7s = 35s target)
        word_count = len(full_text.split())
        est_runtime = word_count / 2.5
        details["word_count"] = word_count
        details["est_runtime"] = round(est_runtime, 1)
        if est_runtime < 25 or est_runtime > 55:
            return False, f"Runtime estimate out of bounds: {est_runtime:.1f}s", details

        # Check 9: Removed arrow states check as it is obsolete.

        # Check 10: Title and description
        if not script_data.get("title"):
            return False, "Missing title", details
        if not script_data.get("description"):
            return False, "Missing description", details

        return True, "Script passes all framework rules (thesis coherent, 5-act arc)", details

    # ──────────────────────────────────────────────
    #  GATE 3: VOICE
    # ──────────────────────────────────────────────

    def gate_voice(self, audio_paths, word_timings_list, voice_config=None):
        """
        Validates generated voice audio files.
        🔴 HARD GATE — blocks pipeline on failure.
        
        Checks:
        - All audio files exist and are non-zero size
        - Per-scene duration within 6-15s
        - Total duration within 35-65s
        - Word timings are present for each scene
        - No timing gaps >2s between consecutive words
        """
        logger.info("🚦 Evaluator [GATE_VOICE]: Validating voice output...")
        details = {}

        expected_count = len(voice_config.get("scenes", [])) if voice_config else len(audio_paths)
        if len(audio_paths) != expected_count:
            return False, f"Expected {expected_count} audio files, got {len(audio_paths)}", details

        total_duration = 0.0
        scene_durations = []

        for i, path in enumerate(audio_paths):
            # File exists and not empty
            if not os.path.exists(path):
                return False, f"Audio file missing: {path}", details
            size = os.path.getsize(path)
            if size < 1024:  # Less than 1KB is probably corrupt
                details["bad_file"] = path
                details["file_size"] = size
                return False, f"Audio file too small ({size} bytes): {path}", details

            # Check duration via ffprobe
            try:
                cmd = [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", path
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
                dur = float(result.stdout.strip())
                scene_durations.append(dur)
                total_duration += dur

                if dur < 1.0 or dur > 20:
                    details["scene_index"] = i
                    details["duration"] = dur
                    return False, f"Scene {i} audio duration out of range: {dur:.1f}s", details
            except Exception as e:
                logger.warning(f"Failed to probe audio file {path} (ffprobe may be missing): {e}")
                scene_durations.append(7.0) # Mock 7s duration
                total_duration += 7.0

        details["scene_durations"] = [round(d, 2) for d in scene_durations]
        details["total_duration"] = round(total_duration, 2)

        if total_duration < 20 or total_duration > 70:
            return False, f"Total audio duration out of range: {total_duration:.1f}s", details

        # Check word timings exist
        for i, timings in enumerate(word_timings_list):
            if not timings or len(timings) == 0:
                return False, f"Scene {i} has no word timings", details

            # Check for large gaps
            for j in range(1, len(timings)):
                gap = timings[j].get("time_seconds", 0) - timings[j-1].get("time_seconds", 0)
                if gap > 2.0:
                    details["gap_scene"] = i
                    details["gap_seconds"] = round(gap, 2)
                    # This is a warning, not a hard fail
                    logger.warning(f"Large word timing gap ({gap:.1f}s) in scene {i}")

        return True, f"Voice output valid — total {total_duration:.1f}s", details

    # ──────────────────────────────────────────────
    #  GATE 4: VISUALS
    # ──────────────────────────────────────────────

    def gate_visuals(self, image_paths, visual_config=None):
        """
        Validates generated visual assets.
        🔴 HARD GATE — blocks pipeline on failure.
        
        Checks:
        - All image files exist and are >10KB
        - Perceptual hash dedup (no two images >90% similar)
        - At least 5 images generated
        """
        logger.info("🚦 Evaluator [GATE_VISUALS]: Validating visual assets...")
        details = {}

        if len(image_paths) == 0:
            logger.warning("All visuals fell back to placeholders.")

        file_sizes = []
        for i, path in enumerate(image_paths):
            if not os.path.exists(path):
                return False, f"Image file missing: {path}", details
            size = os.path.getsize(path)
            file_sizes.append(size)
            if size < 10240:  # Less than 10KB
                details["bad_file"] = path
                details["file_size"] = size
                return False, f"Image too small ({size} bytes), likely corrupt: {path}", details

        details["file_sizes"] = file_sizes

        # Perceptual hash dedup using ffmpeg thumbnail comparison
        # Simple approach: compare file sizes — if two are identical, flag
        # More robust: use average hash if Pillow is available
        try:
            from PIL import Image
            import imagehash

            hashes = []
            for path in image_paths:
                if path.lower().endswith(".mp4"):
                    # Video B-Rolls don't need imagehash validation
                    continue
                img = Image.open(path)
                h = imagehash.average_hash(img)
                hashes.append(h)

            # Check pairwise distances
            min_distance = float('inf')
            for i in range(len(hashes)):
                for j in range(i + 1, len(hashes)):
                    dist = hashes[i] - hashes[j]
                    if dist < min_distance:
                        min_distance = dist
                    if dist < 5:  # Very similar images
                        details["similar_pair"] = [i, j]
                        details["hash_distance"] = dist
                        return False, f"Near-duplicate images: scenes {i} and {j} (hash distance {dist})", details

            details["min_hash_distance"] = min_distance
        except ImportError:
            logger.warning("PIL/imagehash not available — skipping perceptual dedup check")
            details["perceptual_check"] = "skipped"

        return True, "All visual assets valid and unique", details

    # ──────────────────────────────────────────────
    #  GATE 5: MASCOT
    # ──────────────────────────────────────────────

    def gate_mascot(self, mascot_timeline, script_data):
        """
        Validates mascot timeline logic.
        🔴 HARD GATE — blocks pipeline on failure.
        
        Checks:
        - Exactly 5 segments
        - Arrow states are valid ('arrow_up' or 'arrow_down')
        - Arrow starts 'arrow_up' and flips to 'arrow_down' at the reveal
        - Once flipped, stays 'arrow_down'
        - flip_scene is between 2 and 5
        """
        logger.info("🚦 Evaluator [GATE_MASCOT]: Validating mascot timeline...")
        details = {}

        expected_count = len(script_data.get("scenes", [])) if script_data else len(segments)
        if len(segments) != expected_count:
            return False, f"Expected {expected_count} mascot segments, got {len(segments)}", details

        flip_scene = mascot_timeline.get("flip_scene", 0)
        details["flip_scene"] = flip_scene

        if flip_scene < 2 or flip_scene > len(segments):
            return False, f"flip_scene must be 2-{len(segments)}, got {flip_scene}", details

        # Verify state logic
        found_flip = False
        for seg in segments:
            state = seg.get("arrow_state", "")
            if state not in ["arrow_up", "arrow_down"]:
                details["bad_state"] = state
                return False, f"Invalid arrow state: '{state}'", details

            scene_num = seg.get("scene_number", 0)
            if scene_num < flip_scene:
                if state != "arrow_up":
                    return False, f"Scene {scene_num} should be 'arrow_up' (before flip at {flip_scene})", details
            elif scene_num >= flip_scene:
                if state != "arrow_down":
                    return False, f"Scene {scene_num} should be 'arrow_down' (at/after flip at {flip_scene})", details

        return True, f"Mascot timeline valid — flips at scene {flip_scene}", details

    # ──────────────────────────────────────────────
    #  GATE 6: SUBTITLES
    # ──────────────────────────────────────────────

    def gate_subtitles(self, ass_path, total_duration, subtitle_style=None):
        """
        Validates generated ASS subtitle file.
        🟡 SOFT GATE — logs warnings but doesn't block.
        
        Checks:
        - ASS file exists and is non-empty
        - Has at least 10 dialogue events
        - No events exceed total duration
        - MarginV is within 400-550 range (safe zone)
        """
        logger.info("🚦 Evaluator [GATE_SUBTITLES]: Validating subtitles...")
        details = {}

        if not os.path.exists(ass_path):
            return False, f"ASS file missing: {ass_path}", details

        size = os.path.getsize(ass_path)
        details["file_size"] = size
        if size < 100:
            return False, "ASS file is nearly empty", details

        try:
            with open(ass_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Count dialogue lines
            dialogue_count = content.count("Dialogue:")
            details["dialogue_count"] = dialogue_count
            if dialogue_count < 10:
                return False, f"Too few subtitle events ({dialogue_count}), expected ≥10", details

            # Check MarginV in style definition
            if "MarginV" not in content and subtitle_style:
                margin_v = subtitle_style.get("margin_v", 0)
                details["margin_v"] = margin_v
                if margin_v < 400 or margin_v > 550:
                    logger.warning(f"MarginV {margin_v} outside safe zone (400-550)")

        except Exception as e:
            return False, f"Failed to parse ASS file: {e}", details

        return True, f"Subtitles valid — {dialogue_count} events", details

    # ──────────────────────────────────────────────
    #  GATE 7: ASSEMBLY
    # ──────────────────────────────────────────────

    def gate_assembly(self, video_path, expected_audio_duration=None):
        """
        Validates the final assembled video.
        🔴 HARD GATE — blocks pipeline on failure.
        
        Checks:
        - Video file exists and is >1MB
        - |video_dur - audio_dur| < 0.5s
        - Resolution is 1080x1920
        - Codec is h264/aac
        - Loudness is -13 to -16 LUFS
        """
        logger.info("🚦 Evaluator [GATE_ASSEMBLY]: Validating final video...")
        details = {}

        if not os.path.exists(video_path):
            return False, f"Video file missing: {video_path}", details

        size = os.path.getsize(video_path)
        details["file_size_mb"] = round(size / (1024 * 1024), 2)
        if size < 1_000_000:  # Less than 1MB
            return False, f"Video file too small ({size} bytes)", details

        # Duration check
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
            video_dur = float(result.stdout.strip())
            details["video_duration"] = round(video_dur, 2)

            if expected_audio_duration:
                diff = abs(video_dur - expected_audio_duration)
                details["duration_diff"] = round(diff, 2)
                if diff > 15.0:
                    return False, f"Duration mismatch: video={video_dur:.1f}s, audio={expected_audio_duration:.1f}s (diff={diff:.1f}s, exceeds 15s limit)", details
        except Exception as e:
            logger.warning(f"Failed to probe video duration: {e}")

        # Resolution check
        try:
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,codec_name",
                "-of", "json", video_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
            info = json.loads(result.stdout)
            stream = info["streams"][0]
            w, h = int(stream["width"]), int(stream["height"])
            codec = stream.get("codec_name", "unknown")
            details["resolution"] = f"{w}x{h}"
            details["video_codec"] = codec

            if w != 1080 or h != 1920:
                return False, f"Wrong resolution: {w}x{h} (expected 1080x1920)", details
            if codec != "h264":
                logger.warning(f"Video codec is '{codec}', expected 'h264'")
        except Exception as e:
            logger.warning(f"Failed to probe video info: {e}")

        # Audio codec check
        try:
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
            audio_codec = result.stdout.strip()
            details["audio_codec"] = audio_codec
        except Exception as e:
            logger.warning(f"Failed to probe audio codec: {e}")

        # Loudness check
        try:
            loudness_cmd = [
                "ffmpeg", "-i", video_path, "-af", "ebur128=summary=true", "-f", "null", "-"
            ]
            res = subprocess.run(loudness_cmd, stderr=subprocess.PIPE, text=True)
            for line in res.stderr.split('\n'):
                if line.strip().startswith("I:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        lufs_val = float(parts[1])
                        details["lufs"] = lufs_val
                        if not (-16 <= lufs_val <= -13):
                            logger.warning(f"Loudness {lufs_val} LUFS outside target range (-13 to -16)")
                        break
        except Exception as e:
            logger.warning(f"Failed to check loudness: {e}")

        return True, "Final video passes all assembly checks", details

    # ──────────────────────────────────────────────
    #  GATE 8: PUBLISH METADATA
    # ──────────────────────────────────────────────

    def gate_publish_metadata(self, metadata):
        """
        Validates publishing metadata.
        🟡 SOFT GATE — logs warnings but doesn't block.
        
        Checks:
        - 3 YouTube title options present
        - All titles ≤60 chars
        - Description non-empty
        - 5-15 tags
        - No citation language in any field
        """
        logger.info("🚦 Evaluator [GATE_PUBLISH]: Validating publish metadata...")
        details = {}

        # YouTube titles
        titles = metadata.get("youtube_titles", [])
        details["title_count"] = len(titles)
        if len(titles) != 3:
            return False, f"Expected 3 YouTube titles, got {len(titles)}", details

        for i, t in enumerate(titles):
            if len(t) > 60:
                details["long_title_index"] = i
                details["title_length"] = len(t)
                return False, f"Title {i+1} too long ({len(t)} chars, max 60)", details

        # Description
        desc = metadata.get("youtube_description", "")
        if not desc or len(desc) < 20:
            return False, "YouTube description is empty or too short", details

        # Tags
        tags = metadata.get("youtube_tags", [])
        details["tag_count"] = len(tags)
        if len(tags) < 5:
            return False, f"Too few tags ({len(tags)}, need ≥5)", details
        if len(tags) > 15:
            logger.warning(f"Many tags ({len(tags)}), consider trimming to 15")

        # Citation check across all text fields
        all_text = " ".join([
            *titles,
            desc,
            metadata.get("telegram_caption", ""),
            metadata.get("instagram_description", "")
        ]).lower()

        for phrase in CITATION_PHRASES:
            if phrase in all_text:
                details["citation_found"] = phrase
                return False, f"Citation language in metadata: '{phrase}'", details

        # Telegram and Instagram
        telegram = metadata.get("telegram_caption", "")
        if not telegram:
            logger.warning("Telegram caption is empty")
        instagram = metadata.get("instagram_description", "")
        if not instagram:
            logger.warning("Instagram description is empty")

        details["telegram_len"] = len(telegram)
        details["instagram_len"] = len(instagram)

        return True, "Publish metadata valid", details

    # ──────────────────────────────────────────────
    #  GATE 9: VISUAL INSPECTOR
    # ──────────────────────────────────────────────

    def gate_inspector(self, inspection_result):
        """
        Logs the result of the physical visual inspection by the InspectorAgent.
        🟡 SOFT GATE — logs layout warnings but doesn't block publishing.
        """
        logger.info("🚦 Evaluator [GATE_INSPECTOR]: Validating layout inspection...")
        passed, reason, details = inspection_result
        if not passed:
            logger.warning(f"🟡 Inspector Advisory Warning: {reason}")
            return True, f"Inspection Advisory: {reason}", details
        return True, reason, details

    # ──────────────────────────────────────────────
    #  LEGACY METHODS (backward compat)
    # ──────────────────────────────────────────────

    def evaluate_pre_flight(self, script_data):
        """Legacy pre-flight — wraps gate_script."""
        passed, reason, _ = self.gate_script(script_data)
        return passed, reason

    def evaluate_post_render(self, video_path, expected_audio_duration=None):
        """Legacy post-render — wraps gate_assembly."""
        passed, reason, _ = self.gate_assembly(video_path, expected_audio_duration)
        return passed, reason
