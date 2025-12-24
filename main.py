from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uuid
import logging
from datetime import datetime
import json
import asyncio
import subprocess

import config
from video_processor import VideoProcessor
from subtitle_extractor import SubtitleExtractor
from highlight_detector import HighlightDetector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(config.LOGS_DIR, 'app.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Highlight-Extractor API",
    description="Extract highlights from videos using AI and FFmpeg",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

video_processor = VideoProcessor(target_resolution=config.TARGET_RESOLUTION)
subtitle_extractor = SubtitleExtractor(api_key=config.OPENAI_API_KEY)
highlight_detector = HighlightDetector(api_key=config.OPENAI_API_KEY)

jobs = {}

class VideoURL(BaseModel):
    url: str

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
    
    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)
    
    async def disconnect(self, job_id: str, websocket: WebSocket):
        if job_id in self.active_connections:
            self.active_connections[job_id].remove(websocket)
    
    async def broadcast(self, job_id: str, message: dict):
        if job_id in self.active_connections:
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass

manager = ConnectionManager()

def download_video_from_url(url: str, output_path: str) -> str:
    """Download video from URL using yt-dlp"""
    try:
        logger.info(f"Downloading video from {url}")
        cmd = [
            "yt-dlp",
            "-f", "mp4[filesize<500M]/best[filesize<500M]/mp4/best",
            "--merge-output-format", "mp4",
            "-o", output_path,
            url
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"Video downloaded to {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Error downloading video: {e.stderr}")
        raise Exception(f"Failed to download video: {e.stderr}")
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        raise

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/process-video")
async def process_video(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    job_id = str(uuid.uuid4())
    
    try:
        if not file.filename.endswith(('.mp4', '.avi', '.mov', '.mkv')):
            raise HTTPException(status_code=400, detail="Invalid video format")
        
        upload_path = os.path.join(config.UPLOAD_DIR, f"{job_id}_{file.filename}")
        with open(upload_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > config.MAX_VIDEO_SIZE_MB:
            raise HTTPException(status_code=413, detail=f"File too large (max {config.MAX_VIDEO_SIZE_MB}MB)")
        
        jobs[job_id] = {
            "status": "processing",
            "progress": 0,
            "message": "Uploaded successfully, starting processing...",
            "created_at": datetime.now().isoformat()
        }
        
        if background_tasks:
            background_tasks.add_task(
                process_video_async,
                job_id,
                upload_path,
                file.filename
            )
        
        return {
            "job_id": job_id,
            "status": "processing",
            "message": "Video processing started"
        }
    
    except Exception as e:
        logger.error(f"Error in process_video: {str(e)}")
        jobs[job_id] = {"status": "error", "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-url")
async def process_video_url(video_url: VideoURL, background_tasks: BackgroundTasks = None):
    job_id = str(uuid.uuid4())
    
    try:
        url = video_url.url
        
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="Invalid URL format")
        
        jobs[job_id] = {
            "status": "processing",
            "progress": 0,
            "message": "Downloading video from URL...",
            "created_at": datetime.now().isoformat()
        }
        
        if background_tasks:
            background_tasks.add_task(
                process_url_async,
                job_id,
                url
            )
        
        return {
            "job_id": job_id,
            "status": "processing",
            "message": "Video download and processing started"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in process_video_url: {str(e)}")
        jobs[job_id] = {"status": "error", "message": str(e)}
        raise HTTPException(status_code=500, detail=str(e))

async def process_url_async(job_id: str, url: str):
    try:
        await update_job(job_id, "processing", 5, "Downloading video from URL...")
        
        # Download video
        upload_path = os.path.join(config.UPLOAD_DIR, f"{job_id}_video.mp4")
        download_video_from_url(url, upload_path)
        
        await update_job(job_id, "processing", 15, "Video downloaded, starting processing...")
        
        # Continue with normal processing
        await process_video_async(job_id, upload_path, "video.mp4", start_progress=15)
        
    except Exception as e:
        logger.error(f"Error processing URL {job_id}: {str(e)}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = str(e)
        await manager.broadcast(job_id, jobs[job_id])

async def process_video_async(job_id: str, video_path: str, filename: str, start_progress: int = 0):
    try:
        job_output_dir = os.path.join(config.OUTPUT_DIR, job_id)
        os.makedirs(job_output_dir, exist_ok=True)
        
        await update_job(job_id, "processing", start_progress + 20, "Extracting audio...")
        audio_path = os.path.join(job_output_dir, "audio.mp3")
        video_processor.extract_audio(video_path, audio_path)
        
        await update_job(job_id, "processing", start_progress + 35, "Extracting subtitles using Whisper...")
        subtitles = subtitle_extractor.extract_subtitles(audio_path)
        
        await update_job(job_id, "processing", start_progress + 50, "Detecting highlights with GPT-4...")
        highlights = highlight_detector.detect_highlights(
            subtitles,
            min_duration=config.MIN_HIGHLIGHT_DURATION
        )
        
        await update_job(job_id, "processing", start_progress + 60, "Resizing video to 9:16 vertical format...")
        resized_path = os.path.join(job_output_dir, "resized.mp4")
        video_processor.resize_video(video_path, resized_path)
        
        await update_job(job_id, "processing", start_progress + 70, "Embedding subtitles into video...")
        srt_path = os.path.join(job_output_dir, "subtitles.srt")
        srt_content = subtitle_extractor.generate_srt(subtitles)
        with open(srt_path, "w") as f:
            f.write(srt_content)
        
        final_path = os.path.join(job_output_dir, f"final_with_subtitles.mp4")
        video_processor.add_subtitles(resized_path, srt_path, final_path)
        
        await update_job(job_id, "processing", start_progress + 80, "Creating highlight reel...")
        highlight_path = os.path.join(job_output_dir, "highlights.mp4")
        video_processor.create_highlight_video(resized_path, highlights, highlight_path)
        
        await update_job(job_id, "processing", 95, "Finalizing results...")
        
        metadata = {
            "job_id": job_id,
            "filename": filename,
            "highlights": highlights,
            "subtitles": subtitles,
            "num_highlights": len(highlights),
            "num_subtitles": len(subtitles),
            "processed_at": datetime.now().isoformat()
        }
        
        with open(os.path.join(job_output_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)
        
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = "Processing completed successfully!"
        jobs[job_id]["output_dir"] = job_output_dir
        jobs[job_id]["metadata"] = metadata
        
        await manager.broadcast(job_id, jobs[job_id])
        logger.info(f"Job {job_id} completed successfully")
    
    except Exception as e:
        logger.error(f"Error processing video {job_id}: {str(e)}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = str(e)
        await manager.broadcast(job_id, jobs[job_id])

async def update_job(job_id: str, status: str, progress: int, message: str):
    jobs[job_id]["status"] = status
    jobs[job_id]["progress"] = min(progress, 100)
    jobs[job_id]["message"] = message
    await manager.broadcast(job_id, jobs[job_id])

@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.websocket("/ws/job/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await manager.connect(websocket, job_id)
    
    try:
        while True:
            if job_id in jobs:
                await websocket.send_json(jobs[job_id])
            
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        await manager.disconnect(job_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await manager.disconnect(job_id, websocket)

@app.get("/api/download/{job_id}/{file_type}")
async def download_file(job_id: str, file_type: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_output_dir = os.path.join(config.OUTPUT_DIR, job_id)
    
    file_mapping = {
        "final": "final_with_subtitles.mp4",
        "highlights": "highlights.mp4",
        "subtitles": "subtitles.srt",
        "metadata": "metadata.json"
    }
    
    media_types = {
        "final": "video/mp4",
        "highlights": "video/mp4",
        "subtitles": "text/plain",
        "metadata": "application/json"
    }
    
    if file_type not in file_mapping:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    file_path = os.path.join(job_output_dir, file_mapping[file_type])
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        file_path, 
        media_type=media_types[file_type],
        filename=file_mapping[file_type]
    )

@app.get("/")
async def serve_frontend():
    return FileResponse("index.html", media_type="text/html")

@app.get("/api/")
async def api_root():
    return {
        "name": "Highlight-Extractor API",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/process-video": "Upload video for processing",
            "POST /api/process-url": "Process video from URL",
            "GET /api/job/{job_id}": "Get job status",
            "WS /ws/job/{job_id}": "WebSocket for real-time updates",
            "GET /api/download/{job_id}/{file_type}": "Download processed files",
            "GET /api/health": "Health check"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("🎬 Highlight Extractor is running!")
    print(f"👉 Open: http://localhost:{config.API_PORT}")
    print("="*50 + "\n")
    uvicorn.run(
        app,
        host=config.API_HOST,
        port=config.API_PORT,
        log_level="info"
    )