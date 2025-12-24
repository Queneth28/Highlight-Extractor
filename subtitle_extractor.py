import os
from datetime import timedelta
from openai import OpenAI
import json
import logging

logger = logging.getLogger(__name__)

class SubtitleExtractor:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)
    
    def extract_subtitles(self, audio_path: str, language: str = None) -> list:
        """Extract subtitles from audio using Whisper API"""
        try:
            logger.info(f"Extracting subtitles from {audio_path}")
            
            with open(audio_path, "rb") as audio_file:
                # Build request parameters
                params = {
                    "model": "whisper-1",
                    "file": audio_file,
                    "response_format": "verbose_json"
                }
                
                # Add language if specified (not auto)
                if language and language != "auto":
                    params["language"] = language
                
                transcript = self.client.audio.transcriptions.create(**params)
            
            subtitles = []
            for segment in transcript.segments:
                subtitle = {
                    "id": segment.id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "confidence": getattr(segment, 'confidence', 0)
                }
                subtitles.append(subtitle)
            
            logger.info(f"Extracted {len(subtitles)} subtitle segments")
            return subtitles
        
        except Exception as e:
            logger.error(f"Error extracting subtitles: {str(e)}")
            raise
    
    def filter_subtitles_for_highlights(self, subtitles: list, highlights: list) -> list:
        """Filter subtitles to only include those within highlight segments"""
        filtered = []
        subtitle_id = 0
        
        for highlight in highlights:
            h_start = highlight['start']
            h_end = highlight['end']
            
            # Calculate offset for this highlight segment
            if filtered:
                # Get the end time of the last subtitle
                offset = filtered[-1]['end']
            else:
                offset = 0
            
            for sub in subtitles:
                # Check if subtitle overlaps with highlight
                if sub['end'] > h_start and sub['start'] < h_end:
                    # Adjust timing relative to highlight reel
                    new_start = max(0, sub['start'] - h_start) + offset
                    new_end = min(sub['end'] - h_start, h_end - h_start) + offset
                    
                    filtered.append({
                        "id": subtitle_id,
                        "start": new_start,
                        "end": new_end,
                        "text": sub['text'],
                        "confidence": sub.get('confidence', 0)
                    })
                    subtitle_id += 1
        
        return filtered
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """Convert seconds to SRT format (HH:MM:SS,mmm)"""
        td = timedelta(seconds=seconds)
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        secs = td.seconds % 60
        milliseconds = td.microseconds // 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def generate_srt(self, subtitles: list) -> str:
        """Convert subtitle list to SRT format"""
        srt_content = ""
        for idx, sub in enumerate(subtitles, 1):
            srt_content += f"{idx}\n"
            srt_content += f"{self.format_time(sub['start'])} --> {self.format_time(sub['end'])}\n"
            srt_content += f"{sub['text']}\n\n"
        return srt_content