import os
import subprocess
import logging
from google.genai import types

logger = logging.getLogger(__name__)

class InspectorAgent:
    """
    Vision-based Inspector Agent.
    Extracts a frame from the final video and uses Gemini Vision to physically verify
    that all layout demands (e.g. mascot in top half, subtitles in safe zone) are met.
    """

    def __init__(self, gemini_client):
        self.client = gemini_client

    def inspect_layout(self, video_path: str):
        """
        Extract a frame from the middle of the video and ask Gemini to verify the layout.
        Returns (passed, reason, details)
        """
        logger.info(f"🕵️‍♂️ Inspector Agent: Extracting frame from {video_path} for visual verification...")
        
        frame_path = video_path.replace(".mp4", "_inspection_frame.jpg")
        
        # Extract a frame at the 15-second mark (or halfway)
        # Using -ss 00:00:15
        try:
            cmd = [
                "ffmpeg", "-y", "-ss", "00:00:15", "-i", video_path, 
                "-vframes", "1", "-q:v", "2", frame_path
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            logger.info("🕵️‍♂️ Inspector Agent: Frame extracted successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to extract frame: {e}")
            return False, "Failed to extract frame for inspection", {"error": str(e)}

        try:
            with open(frame_path, "rb") as f:
                image_bytes = f.read()

            system_prompt = (
                "You are the Layout Inspector Agent for a short-form vertical video.\n"
                "Your job is to rigorously enforce layout orientation demands.\n"
                "You will receive an image frame from the final video.\n"
                "Verify the following RULES:\n"
                "1. Is the mascot (an arrow) located in the TOP HALF of the video? (Yes/No)\n"
                "2. Are the subtitles located below the mascot (e.g., middle or bottom half) without overlapping it? (Yes/No)\n"
            )

            user_prompt = "Please verify the layout of this video frame according to the rules."
            
            # Use a Pydantic schema for strict JSON response (Gemini API)
            response_schema = {
                "type": "OBJECT",
                "properties": {
                    "passed": {"type": "BOOLEAN", "description": "True if both rules are perfectly met, False otherwise"},
                    "reason": {"type": "STRING", "description": "Detailed explanation of what you see and why it passed or failed"},
                    "mascot_in_top_half": {"type": "BOOLEAN"},
                    "subtitles_below_mascot": {"type": "BOOLEAN"}
                },
                "required": ["passed", "reason", "mascot_in_top_half", "subtitles_below_mascot"]
            }

            logger.info("🕵️‍♂️ Inspector Agent: Requesting Vision API layout check...")
            
            for attempt in range(1, 4):
                try:
                    response = self.client.models.generate_content(
                        model="gemini-3.1-flash-lite",
                        contents=[
                            system_prompt,
                            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                            user_prompt
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=response_schema,
                            temperature=0.1
                        )
                    )
                    break
                except Exception as e:
                    logger.warning(f"Inspector Agent API attempt {attempt} failed: {e}")
                    if attempt == 3:
                        raise e
                    import time
                    time.sleep(2)

            # Cleanup the frame
            if os.path.exists(frame_path):
                os.remove(frame_path)

            data = response.parsed if hasattr(response, "parsed") and response.parsed else __import__("json").loads(response.text)
            
            # Format output
            details = {
                "mascot_in_top_half": data.get("mascot_in_top_half"),
                "subtitles_below_mascot": data.get("subtitles_below_mascot")
            }
            
            if data.get("passed"):
                return True, "Layout orientation demands verified successfully.", details
            else:
                return False, f"Layout verification failed: {data.get('reason')}", details

        except Exception as e:
            logger.error(f"Inspector Agent API error: {e}")
            if os.path.exists(frame_path):
                os.remove(frame_path)
            return False, "Inspector API call failed", {"error": str(e)}
