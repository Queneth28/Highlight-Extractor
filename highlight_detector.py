from openai import OpenAI
import json
import logging

logger = logging.getLogger(__name__)

class HighlightDetector:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)
    
    def detect_highlights(self, subtitles: list, min_duration: int = 2) -> list:
        try:
            subtitle_text = "\n".join([
                f"[{s['start']:.1f}s - {s['end']:.1f}s]: {s['text']}"
                for s in subtitles
            ])
            
            prompt = f"""Analyze the following video subtitles and identify the most engaging and important highlight segments. For each highlight, provide:
1. Start time (in seconds)
2. End time (in seconds)
3. Why it's a good highlight
4. Engagement score (0-100)

Focus on:
- Interesting statements or insights
- Emotional moments
- Important conclusions
- Entertaining exchanges
- Key takeaways

Format your response as a JSON array with objects containing: start, end, reason, score

Subtitles:
{subtitle_text}

Minimum highlight duration: {min_duration} seconds

JSON Response:"""

            response = self.client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are a video editor expert at finding engaging highlights."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            json_start = content.find('[')
            json_end = content.rfind(']') + 1
            json_str = content[json_start:json_end]
            
            highlights = json.loads(json_str)
            logger.info(f"Detected {len(highlights)} highlights")
            
            return highlights
        
        except Exception as e:
            logger.error(f"Error detecting highlights: {str(e)}")
            raise
