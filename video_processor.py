import logging
import subprocess
import os
from moviepy.editor import VideoFileClip, concatenate_videoclips

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self, target_resolution=(1080, 1920)):
        self.target_resolution = target_resolution
    
    def extract_audio(self, video_path: str, output_audio_path: str) -> str:
        """Extract audio from video using ffmpeg"""
        try:
            logger.info(f"Extracting audio from {video_path}")
            cmd = [
                "ffmpeg", "-i", video_path,
                "-q:a", "0", "-map", "a",
                "-y", output_audio_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Audio extracted to {output_audio_path}")
            return output_audio_path
        except Exception as e:
            logger.error(f"Error extracting audio: {str(e)}")
            raise
    
    def resize_video(self, video_path: str, output_path: str) -> str:
        """Resize video to target resolution (16:9 vertical format)"""
        try:
            logger.info(f"Resizing video to {self.target_resolution}")
            video = VideoFileClip(video_path)
            
            input_w, input_h = video.size
            target_h, target_w = self.target_resolution
            
            scale_w = target_w / input_w
            scale_h = target_h / input_h
            scale = max(scale_w, scale_h)
            
            new_w = int(input_w * scale)
            new_h = int(input_h * scale)
            
            resized = video.resize((new_w, new_h))
            x_center = (new_w - target_w) // 2
            y_center = (new_h - target_h) // 2
            
            cropped = resized.crop(
                x1=x_center,
                y1=y_center,
                x2=x_center + target_w,
                y2=y_center + target_h
            )
            
            cropped.write_videofile(output_path, verbose=False, logger=None)
            video.close()
            logger.info(f"Video resized and saved to {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"Error resizing video: {str(e)}")
            raise
    
    def add_subtitles(self, video_path: str, srt_path: str, output_path: str) -> str:
        """Add subtitles to video using ffmpeg"""
        try:
            logger.info(f"Adding subtitles to video")
            
            import shutil
            video_dir = os.path.dirname(video_path)
            subtitle_filename = "subtitles.srt"
            srt_copy_path = os.path.join(video_dir, subtitle_filename)
            
            # Only copy if source and destination are different
            if os.path.abspath(srt_path) != os.path.abspath(srt_copy_path):
                shutil.copy(srt_path, srt_copy_path)
            
            # Fix Windows path for FFmpeg (use forward slashes and escape colons)
            srt_ffmpeg_path = srt_copy_path.replace("\\", "/").replace(":", "\\:")
            
            cmd = [
                "ffmpeg", "-i", video_path,
                "-vf", f"subtitles='{srt_ffmpeg_path}':force_style='FontSize=40,PrimaryColour=&H00FFFFFF&,OutlineColour=&H000000FF&'",
                "-c:a", "aac",
                "-y", output_path
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Subtitles added and video saved to {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"Error adding subtitles: {str(e)}")
            raise
    
    def create_highlight_video(self, video_path: str, highlights: list, output_path: str) -> str:
        """Create a video with only highlight segments"""
        try:
            logger.info(f"Creating highlight video from {len(highlights)} segments")
            video = VideoFileClip(video_path)
            
            clips = []
            for highlight in highlights:
                start = max(0, highlight['start'])
                end = min(video.duration, highlight['end'])
                if end - start > 0.5:
                    clip = video.subclip(start, end)
                    clips.append(clip)
            
            if clips:
                final_clip = concatenate_videoclips(clips)
                final_clip.write_videofile(output_path, verbose=False, logger=None)
                logger.info(f"Highlight video saved to {output_path}")
            
            video.close()
            return output_path
        
        except Exception as e:
            logger.error(f"Error creating highlight video: {str(e)}")
            raise